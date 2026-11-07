"""Provider selection from configuration.

* The primary provider is ``llm_provider``. A fallback is used only if ``llm_fallback_provider`` is
  set; the response then records which provider produced it. HerbaGuard never switches on its own.
* ``extractive`` is not a model: answers are composed from stored excerpts (see generation).
* A selected cloud provider that is not configured fails clearly (``not_configured``); an
  unselected, unconfigured provider is simply reported as such and never breaks start-up.
* Adding a provider = one adapter module + one entry in ``_BUILDERS``; the RAG pipeline is
  unchanged.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import httpx

from herbaguard.ai.providers.anthropic import AnthropicProvider
from herbaguard.ai.providers.base import LLMProvider, ProviderError, ProviderStatus
from herbaguard.ai.providers.ollama import OllamaProvider
from herbaguard.ai.providers.openai import OpenAIProvider
from herbaguard.core.config import LLMProviderName, Settings

Builder = Callable[[Settings, httpx.BaseTransport | None], LLMProvider]

_BUILDERS: dict[LLMProviderName, Builder] = {
    LLMProviderName.OLLAMA: lambda s, t: OllamaProvider(
        base_url=s.ollama_base_url, model=s.llm_model, timeout=s.llm_timeout_seconds,
        num_ctx=s.ollama_num_ctx, keep_alive=s.ollama_keep_alive, transport=t,
    ),
    LLMProviderName.ANTHROPIC: lambda s, t: AnthropicProvider(
        api_key=s.anthropic_api_key, model=s.anthropic_model, base_url=s.anthropic_base_url,
        timeout=s.llm_timeout_seconds, transport=t,
    ),
    LLMProviderName.OPENAI: lambda s, t: OpenAIProvider(
        api_key=s.openai_api_key, model=s.openai_model, base_url=s.openai_base_url,
        timeout=s.llm_timeout_seconds, transport=t,
    ),
}  # fmt: skip


def build_provider(
    name: LLMProviderName, settings: Settings, transport: httpx.BaseTransport | None = None
) -> LLMProvider | None:
    """The adapter for ``name``; ``None`` for the extractive mode. Raises ``ProviderError``
    (``not_configured``) when required settings are missing."""
    if name is LLMProviderName.EXTRACTIVE:
        return None
    return _BUILDERS[name](settings, transport)


@dataclass(frozen=True, slots=True)
class GenerationChain:
    """Ordered generators: primary, then the explicitly configured fallback. ``None`` entries stand
    for the extractive mode."""

    names: tuple[LLMProviderName, ...]
    providers: tuple[LLMProvider | None, ...]


def generation_chain(
    settings: Settings,
    *,
    overrides: dict[LLMProviderName, LLMProvider | None] | None = None,
    transport: httpx.BaseTransport | None = None,
) -> GenerationChain:
    names = [settings.llm_provider]
    if settings.llm_fallback_provider is not None:
        names.append(settings.llm_fallback_provider)
    providers: list[LLMProvider | None] = []
    for name in names:
        if overrides and name in overrides:
            providers.append(overrides[name])
        else:
            providers.append(build_provider(name, settings, transport))
    return GenerationChain(tuple(names), tuple(providers))


def provider_statuses(
    settings: Settings, *, probe_local: bool, transport: httpx.BaseTransport | None = None
) -> list[tuple[ProviderStatus, bool, bool]]:
    """(status, selected, fallback) for every known generator. Secrets are never included; cloud
    providers are never called."""
    out: list[tuple[ProviderStatus, bool, bool]] = []
    for name in LLMProviderName:
        selected = name == settings.llm_provider
        fallback = name == settings.llm_fallback_provider
        if name is LLMProviderName.EXTRACTIVE:
            out.append((ProviderStatus(name.value, None, True, True, "No model; composes answers from stored excerpts."), selected, fallback))  # fmt: skip
            continue
        try:
            provider = build_provider(name, settings, transport)
        except ProviderError as exc:
            out.append(
                (ProviderStatus(name.value, None, False, None, exc.message), selected, fallback)
            )
            continue
        assert provider is not None  # noqa: S101 - only extractive builds None
        out.append(
            (provider.status(probe=probe_local and not provider.is_cloud), selected, fallback)
        )
    return out
