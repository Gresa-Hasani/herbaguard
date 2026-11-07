"""Anthropic Messages API adapter (optional cloud provider).

Structured output uses a forced tool call whose ``input_schema`` is the requested JSON schema. The
model identifier and the API key come only from configuration; nothing here names a model.
"""

from __future__ import annotations

import json
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

API_VERSION = "2023-06-01"
TOOL_NAME = "herbaguard_answer"


class AnthropicProvider:
    name = "anthropic"
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
                f"Anthropic is not configured: no {' or '.join(missing)} is set "
                "(HERBAGUARD_ANTHROPIC_API_KEY, HERBAGUARD_ANTHROPIC_MODEL).",
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
            "system": request.system,
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        }
        if request.json_schema is not None:
            body["tools"] = [
                {
                    "name": TOOL_NAME,
                    "description": "Return the answer in HerbaGuard's structured format.",
                    "input_schema": request.json_schema,
                }
            ]
            body["tool_choice"] = {"type": "tool", "name": TOOL_NAME}
        headers = {
            "x-api-key": self._key.get_secret_value(),
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }
        started = time.perf_counter()
        try:
            with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                response = client.post(f"{self.base_url}/v1/messages", json=body, headers=headers)
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise http_error(self.name, exc) from None
        blocks = data.get("content") if isinstance(data, dict) else None
        if not isinstance(blocks, list):
            raise ProviderError(
                self.name, ProviderErrorKind.BAD_RESPONSE, "No content in the reply."
            )
        if request.json_schema is not None:
            tool = next((b for b in blocks if b.get("type") == "tool_use"), None)
            if tool is None or not isinstance(tool.get("input"), dict):
                raise ProviderError(
                    self.name, ProviderErrorKind.BAD_RESPONSE, "No structured answer in the reply."
                )
            text = json.dumps(tool["input"])
        else:
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        usage = data.get("usage") or {}
        return GenerationResult(
            provider=self.name,
            model=str(data.get("model") or self.model),
            text=text,
            finish_reason=data.get("stop_reason"),
            usage=Usage(usage.get("input_tokens"), usage.get("output_tokens")),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    def status(self, *, probe: bool) -> ProviderStatus:
        return ProviderStatus(self.name, self.model, configured=True, reachable=None,
                              detail="Cloud provider; not called by status checks.")  # fmt: skip
