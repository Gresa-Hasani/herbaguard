"""Embedding providers (independent of the generation provider).

Contract: :class:`EmbeddingProvider`. Retrieval and indexing depend only on it, never on a model.
Vectors are L2-normalised here (cosine similarity = dot product, and models that do not normalise
behave the same as those that do). Every vector is checked for a consistent dimension and finite
values; empty input is rejected before any request.

Model identity stored with every vector: ``model`` (configured name), ``version`` (the provider's
content digest, so an updated model is detected as a different version) and ``dimension``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

import httpx

from herbaguard.core.config import EmbeddingProviderName, Settings

Kind = Literal["query", "document"]


class EmbeddingError(Exception):
    """Safe-to-show failure of an embedding provider."""


@dataclass(frozen=True, slots=True)
class EmbeddingModelInfo:
    provider: str
    model: str
    version: str
    dimension: int


@runtime_checkable
class EmbeddingProvider(Protocol):
    name: str
    model: str

    def info(self) -> EmbeddingModelInfo: ...

    def embed(self, texts: list[str], kind: Kind) -> list[list[float]]: ...


def normalise(vector: list[float]) -> list[float]:
    if not vector or any(not math.isfinite(v) for v in vector):
        msg = "The embedding model returned an empty or non-finite vector."
        raise EmbeddingError(msg)
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        msg = "The embedding model returned a zero vector."
        raise EmbeddingError(msg)
    return [v / norm for v in vector]


class OllamaEmbeddings:
    """``POST /api/embed`` (batched). The version is the model digest from ``/api/tags``."""

    name = "ollama"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout: float,
        query_prefix: str = "",
        document_prefix: str = "",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.prefixes = {"query": query_prefix, "document": document_prefix}
        self._transport = transport
        self._info: EmbeddingModelInfo | None = None

    def _client(self, timeout: float | None = None) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url, timeout=timeout or self.timeout, transport=self._transport
        )

    def _post(self, texts: list[str]) -> list[list[float]]:
        try:
            with self._client() as client:
                response = client.post("/api/embed", json={"model": self.model, "input": texts})
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException:
            msg = "The embedding model did not answer in time."
            raise EmbeddingError(msg) from None
        except httpx.HTTPStatusError as exc:
            hint = f" (ollama pull {self.model})" if exc.response.status_code == 404 else ""
            msg = f"The embedding model failed (HTTP {exc.response.status_code}){hint}."
            raise EmbeddingError(msg) from None
        except (httpx.HTTPError, ValueError):
            msg = "The embedding service could not be reached."
            raise EmbeddingError(msg) from None
        vectors = data.get("embeddings") if isinstance(data, dict) else None
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            msg = "The embedding service returned a different number of vectors than texts."
            raise EmbeddingError(msg)
        return vectors

    def info(self) -> EmbeddingModelInfo:
        if self._info is None:
            try:
                with self._client(timeout=5.0) as client:
                    response = client.get("/api/tags")
                    response.raise_for_status()
                    models = response.json().get("models", [])
            except (httpx.HTTPError, ValueError):
                msg = "The embedding service could not be reached."
                raise EmbeddingError(msg) from None
            entry = next(
                (m for m in models if m.get("name") in (self.model, f"{self.model}:latest")), None
            )
            if entry is None:
                msg = f"Embedding model '{self.model}' is not installed (ollama pull {self.model})."
                raise EmbeddingError(msg)
            dimension = len(self._post(["dimension probe"])[0])
            self._info = EmbeddingModelInfo(
                self.name, self.model, str(entry.get("digest") or "unknown")[:16], dimension
            )
        return self._info

    def embed(self, texts: list[str], kind: Kind) -> list[list[float]]:
        if not texts or any(not t or not t.strip() for t in texts):
            msg = "Cannot embed empty text."
            raise EmbeddingError(msg)
        prefix = self.prefixes[kind]
        vectors = [normalise(v) for v in self._post([prefix + t for t in texts])]
        expected = self.info().dimension
        if any(len(v) != expected for v in vectors):
            msg = f"The embedding model returned vectors of a different dimension (expected {expected})."
            raise EmbeddingError(msg)
        return vectors


# Task prefixes required by some models (model card instructions). Used when no prefix is configured.
MODEL_PREFIXES: dict[str, tuple[str, str]] = {
    "nomic-embed-text": ("search_query: ", "search_document: "),
}


def build_embeddings(
    settings: Settings,
    *,
    model: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> EmbeddingProvider | None:
    """The configured embedding provider, or ``None`` (keyword retrieval only)."""
    if settings.embedding_provider is EmbeddingProviderName.NONE:
        return None
    name = model or settings.embedding_model
    default_query, default_document = MODEL_PREFIXES.get(name.split(":")[0], ("", ""))
    return OllamaEmbeddings(
        base_url=settings.ollama_base_url,
        model=name,
        timeout=settings.embedding_timeout_seconds,
        query_prefix=settings.embedding_query_prefix or default_query,
        document_prefix=settings.embedding_document_prefix or default_document,
        transport=transport,
    )
