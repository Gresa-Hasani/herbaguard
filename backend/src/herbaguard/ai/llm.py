"""LLM and embedding clients (ADR-009: local Ollama; extractive mode is always available).

Only the Ollama HTTP API is used (``/api/chat``, ``/api/embed``, ``/api/tags``); no third-party
SDK. Questions never leave the machine Ollama runs on. Any transport or protocol problem is
raised as :class:`LLMUnavailableError`, which the assistant service turns into the extractive
fallback instead of an error response.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from herbaguard.core.config import Settings


class LLMUnavailableError(RuntimeError):
    """The model server could not be reached or returned an unusable response."""


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True, slots=True)
class Completion:
    text: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    duration_ms: int | None = None


class ChatModel(Protocol):
    name: str

    def chat(self, messages: Sequence[ChatMessage]) -> Completion: ...


class Embedder(Protocol):
    name: str
    dimension: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def _client(settings: Settings, timeout: float) -> httpx.Client:
    return httpx.Client(
        base_url=str(settings.ollama_base_url).rstrip("/"),
        timeout=httpx.Timeout(timeout, connect=5.0),
        headers={"User-Agent": settings.http_user_agent},
    )


def _post(client: httpx.Client, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        response = client.post(path, json=payload)
    except httpx.HTTPError as exc:
        msg = f"Ollama request to {path} failed: {type(exc).__name__}"
        raise LLMUnavailableError(msg) from exc
    if response.status_code != 200:
        detail = response.text[:300]
        msg = f"Ollama {path} returned HTTP {response.status_code}: {detail}"
        raise LLMUnavailableError(msg)
    try:
        data = response.json()
    except ValueError as exc:
        msg = f"Ollama {path} returned invalid JSON"
        raise LLMUnavailableError(msg) from exc
    if not isinstance(data, dict):
        msg = f"Ollama {path} returned an unexpected payload"
        raise LLMUnavailableError(msg)
    return data


class OllamaChatModel:
    """Chat completion with temperature 0 and a fixed seed, so answers are reproducible."""

    def __init__(self, settings: Settings, *, client: httpx.Client | None = None) -> None:
        self.name = settings.ollama_chat_model
        self._settings = settings
        self._client = client or _client(settings, settings.ollama_timeout_seconds)

    def chat(self, messages: Sequence[ChatMessage]) -> Completion:
        data = _post(
            self._client,
            "/api/chat",
            {
                "model": self.name,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "stream": False,
                "keep_alive": self._settings.ollama_keep_alive,
                "options": {
                    "temperature": 0,
                    "seed": 7,
                    "num_ctx": self._settings.ollama_num_ctx,
                    "num_predict": self._settings.ollama_max_answer_tokens,
                },
            },
        )
        message = data.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            msg = "Ollama /api/chat response has no message content"
            raise LLMUnavailableError(msg)
        duration = data.get("total_duration")
        return Completion(
            text=content.strip(),
            model=str(data.get("model") or self.name),
            prompt_tokens=_int(data.get("prompt_eval_count")),
            completion_tokens=_int(data.get("eval_count")),
            duration_ms=int(duration) // 1_000_000 if isinstance(duration, int) else None,
        )


class OllamaEmbedder:
    """Sentence embeddings from an Ollama embedding model (default ``all-minilm``, 384-d)."""

    def __init__(
        self, settings: Settings, *, dimension: int, client: httpx.Client | None = None
    ) -> None:
        self.name = settings.ollama_embed_model
        self.dimension = dimension
        self._client = client or _client(settings, settings.ollama_timeout_seconds)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        data = _post(
            self._client, "/api/embed", {"model": self.name, "input": list(texts), "truncate": True}
        )
        vectors = data.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            msg = "Ollama /api/embed returned the wrong number of embeddings"
            raise LLMUnavailableError(msg)
        out: list[list[float]] = []
        for vector in vectors:
            if not isinstance(vector, list) or len(vector) != self.dimension:
                size = len(vector) if isinstance(vector, list) else "?"
                msg = (
                    f"Embedding model '{self.name}' returned {size} dimensions; the chunk table "
                    f"stores {self.dimension} (choose a {self.dimension}-d model or migrate)"
                )
                raise LLMUnavailableError(msg)
            out.append([float(x) for x in vector])
        return out


@dataclass(frozen=True, slots=True)
class OllamaStatus:
    reachable: bool
    models: list[str]
    error: str | None = None

    def has(self, model: str) -> bool:
        wanted = model if ":" in model else f"{model}:latest"
        return any(m in {model, wanted} for m in self.models)


def ollama_status(settings: Settings, *, client: httpx.Client | None = None) -> OllamaStatus:
    http = client or _client(settings, 3.0)
    try:
        response = http.get("/api/tags")
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return OllamaStatus(False, [], f"{type(exc).__name__}: {exc}"[:300])
    models = data.get("models", []) if isinstance(data, dict) else []
    names = [str(m.get("name")) for m in models if isinstance(m, dict) and m.get("name")]
    return OllamaStatus(True, sorted(names))


def _int(value: object) -> int | None:
    return value if isinstance(value, int) else None
