"""Provider-independent contract for text generation.

The RAG pipeline depends only on :class:`LLMProvider`, :class:`GenerationRequest` and
:class:`GenerationResult`. Vendor details (endpoints, payload shapes, error formats) stay inside
the adapter modules. Adapters use plain HTTP (httpx), so they share one timeout and error path and
can be tested with recorded or mocked responses without vendor SDKs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal, Protocol, runtime_checkable

import httpx


class ProviderErrorKind(StrEnum):
    NOT_CONFIGURED = "not_configured"
    UNAVAILABLE = "unavailable"  # connection refused, DNS, 5xx
    TIMEOUT = "timeout"
    AUTHENTICATION = "authentication"  # 401/403 (the key itself is never echoed)
    RATE_LIMITED = "rate_limited"
    MODEL_NOT_FOUND = "model_not_found"
    BAD_REQUEST = "bad_request"
    BAD_RESPONSE = "bad_response"  # unparseable or incomplete output
    REFUSED = "refused"  # policy refusal by HerbaGuard (e.g. licensing guard)


class ProviderError(Exception):
    """Normalised provider failure. ``message`` is safe to log and to return to clients."""

    def __init__(self, provider: str, kind: ProviderErrorKind, message: str) -> None:
        super().__init__(f"{provider}: {kind.value}: {message}")
        self.provider = provider
        self.kind = kind
        self.message = message


@dataclass(frozen=True, slots=True)
class Message:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    system: str
    messages: tuple[Message, ...]
    json_schema: dict[str, Any] | None = None  # structured output when the provider supports it
    temperature: float = 0.0
    max_output_tokens: int = 900
    seed: int | None = None
    # True if the messages contain source text; cloud adapters refuse such requests unless the
    # licensing guard allows them (see registry.check_cloud_policy).
    contains_source_text: bool = True


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class GenerationResult:
    provider: str
    model: str
    text: str
    finish_reason: str | None
    usage: Usage = field(default_factory=Usage)
    duration_ms: int = 0

    @property
    def complete(self) -> bool:
        """False when the model stopped because of the token limit (partial output)."""
        return self.finish_reason not in {"length", "max_tokens"}


@dataclass(frozen=True, slots=True)
class ProviderStatus:
    name: str
    model: str | None
    configured: bool
    reachable: bool | None  # None = not probed (cloud providers are never called by health checks)
    detail: str | None = None


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    model: str
    is_cloud: bool

    def generate(self, request: GenerationRequest) -> GenerationResult: ...

    def status(self, *, probe: bool) -> ProviderStatus: ...


def http_error(provider: str, exc: Exception) -> ProviderError:
    """Map httpx exceptions and HTTP status codes to :class:`ProviderError` without leaking
    request headers (API keys) or response bodies."""
    if isinstance(exc, httpx.TimeoutException):
        return ProviderError(
            provider, ProviderErrorKind.TIMEOUT, "The provider did not answer in time."
        )
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403):
            kind = ProviderErrorKind.AUTHENTICATION
            message = f"The provider rejected the credentials (HTTP {code})."
        elif code == 404:
            kind = ProviderErrorKind.MODEL_NOT_FOUND
            message = "The provider does not know the configured model (HTTP 404)."
        elif code == 429:
            kind = ProviderErrorKind.RATE_LIMITED
            message = "The provider is rate limiting requests (HTTP 429)."
        elif 400 <= code < 500:
            kind = ProviderErrorKind.BAD_REQUEST
            message = f"The provider rejected the request (HTTP {code})."
        else:
            kind = ProviderErrorKind.UNAVAILABLE
            message = f"The provider failed (HTTP {code})."
        return ProviderError(provider, kind, message)
    if isinstance(exc, httpx.HTTPError):
        return ProviderError(
            provider, ProviderErrorKind.UNAVAILABLE, "The provider could not be reached."
        )
    return ProviderError(
        provider, ProviderErrorKind.BAD_RESPONSE, "The provider returned an unusable response."
    )
