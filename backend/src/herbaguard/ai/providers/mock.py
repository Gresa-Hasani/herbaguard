"""Scripted provider for tests and offline pipeline runs. Never selected by configuration."""

from __future__ import annotations

from collections.abc import Callable

from herbaguard.ai.providers.base import (
    GenerationRequest,
    GenerationResult,
    ProviderError,
    ProviderStatus,
    Usage,
)


class ScriptedProvider:
    """Returns ``reply(request)`` (or raises the error it returns)."""

    is_cloud = False

    def __init__(
        self,
        reply: Callable[[GenerationRequest], str | ProviderError],
        *,
        name: str = "mock",
        model: str = "scripted",
        finish_reason: str = "stop",
        is_cloud: bool = False,
    ) -> None:
        self.name = name
        self.model = model
        self.is_cloud = is_cloud
        self._reply = reply
        self._finish_reason = finish_reason
        self.requests: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self.requests.append(request)
        out = self._reply(request)
        if isinstance(out, ProviderError):
            raise out
        return GenerationResult(self.name, self.model, out, self._finish_reason, Usage(10, 5), 1)

    def status(self, *, probe: bool) -> ProviderStatus:
        return ProviderStatus(self.name, self.model, configured=True, reachable=True)
