"""OpenAI Chat Completions adapter (optional cloud provider).

Structured output uses ``response_format = {"type": "json_schema", ...}``. The base URL is
configurable, so OpenAI-compatible servers can be used without another adapter. The model and key
come only from configuration.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from pydantic import SecretStr

from herbaguard.ai.providers.base import (
    GenerationRequest,
    GenerationResult,
    ProviderError,
    ProviderErrorKind,
    ProviderStatus,
    Usage,
    http_error,
)


class OpenAIProvider:
    name = "openai"
    is_cloud = True

    def __init__(
        self,
        *,
        api_key: SecretStr | None,
        model: str | None,
        base_url: str,
        timeout: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        missing = [
            n
            for n, v in (("API key", api_key), ("model", model))
            if not v or (isinstance(v, SecretStr) and not v.get_secret_value())
        ]
        if missing:
            raise ProviderError(
                self.name,
                ProviderErrorKind.NOT_CONFIGURED,
                f"OpenAI is not configured: no {' or '.join(missing)} is set "
                "(HERBAGUARD_OPENAI_API_KEY, HERBAGUARD_OPENAI_MODEL).",
            )
        assert api_key is not None  # noqa: S101 - checked above
        assert model is not None  # noqa: S101
        self._key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._transport = transport

    def generate(self, request: GenerationRequest) -> GenerationResult:
        body: dict[str, Any] = {
            "model": self.model,
            "temperature": request.temperature,
            "max_completion_tokens": request.max_output_tokens,
            "messages": [
                {"role": "system", "content": request.system},
                *({"role": m.role, "content": m.content} for m in request.messages),
            ],
        }
        if request.seed is not None:
            body["seed"] = request.seed
        if request.json_schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "herbaguard_answer", "schema": request.json_schema},
            }
        headers = {"authorization": f"Bearer {self._key.get_secret_value()}"}
        started = time.perf_counter()
        try:
            with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions", json=body, headers=headers
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise http_error(self.name, exc) from None
        try:
            choice = data["choices"][0]
            text = choice["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise ProviderError(
                self.name, ProviderErrorKind.BAD_RESPONSE, "No choice in the reply."
            ) from None
        if not isinstance(text, str):
            raise ProviderError(
                self.name, ProviderErrorKind.BAD_RESPONSE, "Empty message in the reply."
            )
        usage = data.get("usage") or {}
        return GenerationResult(
            provider=self.name,
            model=str(data.get("model") or self.model),
            text=text,
            finish_reason=choice.get("finish_reason"),
            usage=Usage(usage.get("prompt_tokens"), usage.get("completion_tokens")),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    def status(self, *, probe: bool) -> ProviderStatus:
        return ProviderStatus(self.name, self.model, configured=True, reachable=None,
                              detail="Cloud provider; not called by status checks.")  # fmt: skip
