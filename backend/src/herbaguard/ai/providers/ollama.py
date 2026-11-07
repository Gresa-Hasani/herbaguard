"""Local generation through Ollama (default provider; no API key).

API: ``POST /api/chat`` with ``format`` = JSON schema for structured output. Thinking is switched
off (``think: false``) because HerbaGuard needs a short, structured, cited answer and CPU time is
scarce; Qwen3 supports this switch.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from herbaguard.ai.providers.base import (
    GenerationRequest,
    GenerationResult,
    ProviderError,
    ProviderErrorKind,
    ProviderStatus,
    Usage,
    http_error,
)


class OllamaProvider:
    name = "ollama"
    is_cloud = False

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout: float,
        num_ctx: int = 8192,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not model:
            raise ProviderError(
                self.name, ProviderErrorKind.NOT_CONFIGURED, "No Ollama model is configured."
            )
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.num_ctx = num_ctx
        self._transport = transport

    def _client(self, timeout: float | None = None) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url, timeout=timeout or self.timeout, transport=self._transport
        )

    def generate(self, request: GenerationRequest) -> GenerationResult:
        options: dict[str, Any] = {
            "temperature": request.temperature,
            "num_ctx": self.num_ctx,
            "num_predict": request.max_output_tokens,
        }
        if request.seed is not None:
            options["seed"] = request.seed
        body: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "think": False,
            "options": options,
            "messages": [
                {"role": "system", "content": request.system},
                *({"role": m.role, "content": m.content} for m in request.messages),
            ],
        }
        if request.json_schema is not None:
            body["format"] = request.json_schema
        started = time.perf_counter()
        try:
            with self._client() as client:
                response = client.post("/api/chat", json=body)
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise http_error(self.name, exc) from None
        message = data.get("message") if isinstance(data, dict) else None
        text = message.get("content") if isinstance(message, dict) else None
        if not isinstance(text, str):
            raise ProviderError(
                self.name, ProviderErrorKind.BAD_RESPONSE, "No message content in the reply."
            )
        return GenerationResult(
            provider=self.name,
            model=str(data.get("model") or self.model),
            text=text,
            finish_reason=data.get("done_reason"),
            usage=Usage(data.get("prompt_eval_count"), data.get("eval_count")),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    def status(self, *, probe: bool) -> ProviderStatus:
        if not probe:
            return ProviderStatus(self.name, self.model, configured=True, reachable=None)
        try:
            with self._client(timeout=3.0) as client:
                response = client.get("/api/tags")
                response.raise_for_status()
                names = {m.get("name") for m in response.json().get("models", [])}
        except (httpx.HTTPError, ValueError):
            return ProviderStatus(self.name, self.model, True, False, "Ollama is not reachable.")
        installed = self.model in names or f"{self.model}:latest" in names
        detail = (
            None
            if installed
            else f"Model '{self.model}' is not installed (ollama pull {self.model})."
        )
        return ProviderStatus(self.name, self.model, True, installed, detail)
