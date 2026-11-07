"""Provider contract, selection and error normalisation. No real API is called: every HTTP
exchange goes through ``httpx.MockTransport``. Response shapes follow the providers' documented
formats (Ollama /api/chat, Anthropic Messages with tool use, OpenAI Chat Completions)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from herbaguard.ai.providers.anthropic import AnthropicProvider
from herbaguard.ai.providers.base import (
    GenerationRequest,
    LLMProvider,
    Message,
    ProviderError,
    ProviderErrorKind,
)
from herbaguard.ai.providers.ollama import OllamaProvider
from herbaguard.ai.providers.openai import OpenAIProvider
from herbaguard.ai.providers.registry import build_provider, generation_chain, provider_statuses
from herbaguard.core.config import LLMProviderName, Settings

SECRET = "sk-test-secret-value-never-shown"  # noqa: S105 - fake value
SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}
REQUEST = GenerationRequest(
    system="Answer from the evidence only.",
    messages=(Message("user", "Question?"),),
    json_schema=SCHEMA,
    max_output_tokens=200,
    seed=7,
)

Handler = Callable[[httpx.Request], httpx.Response]


def transport(handler: Handler, seen: list[httpx.Request] | None = None) -> httpx.MockTransport:
    def wrapped(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return handler(request)

    return httpx.MockTransport(wrapped)


def settings(**values: Any) -> Settings:
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def ollama(handler: Handler, seen: list[httpx.Request] | None = None) -> OllamaProvider:
    return OllamaProvider(base_url="http://ollama.test", model="qwen3:4b", timeout=5,
                          transport=transport(handler, seen))  # fmt: skip


def anthropic(handler: Handler, seen: list[httpx.Request] | None = None) -> AnthropicProvider:
    return AnthropicProvider(api_key=SecretStr(SECRET), model="configured-model",
                             base_url="https://anthropic.test", timeout=5, transport=transport(handler, seen))  # fmt: skip


def openai(handler: Handler, seen: list[httpx.Request] | None = None) -> OpenAIProvider:
    return OpenAIProvider(api_key=SecretStr(SECRET), model="configured-model",
                          base_url="https://openai.test/v1", timeout=5, transport=transport(handler, seen))  # fmt: skip


# --------------------------------------------------------------------------- contract


def test_ollama_contract() -> None:
    seen: list[httpx.Request] = []
    reply = {"model": "qwen3:4b", "message": {"role": "assistant", "content": '{"answer": "x"}'},
             "done_reason": "stop", "prompt_eval_count": 120, "eval_count": 9}  # fmt: skip
    result = ollama(lambda r: httpx.Response(200, json=reply), seen).generate(REQUEST)
    body = json.loads(seen[0].content)
    assert seen[0].url.path == "/api/chat"
    assert body["format"] == SCHEMA and body["think"] is False and body["stream"] is False
    assert body["messages"][0] == {"role": "system", "content": REQUEST.system}
    assert body["options"]["seed"] == 7 and body["options"]["num_predict"] == 200
    assert (result.provider, result.model, result.text) == ("ollama", "qwen3:4b", '{"answer": "x"}')
    assert (result.usage.input_tokens, result.usage.output_tokens, result.complete) == (
        120,
        9,
        True,
    )


def test_anthropic_contract_uses_forced_tool_for_structured_output() -> None:
    seen: list[httpx.Request] = []
    reply = {"model": "configured-model", "stop_reason": "tool_use",
             "content": [{"type": "tool_use", "name": "herbaguard_answer", "input": {"answer": "x"}}],
             "usage": {"input_tokens": 50, "output_tokens": 4}}  # fmt: skip
    result = anthropic(lambda r: httpx.Response(200, json=reply), seen).generate(REQUEST)
    body = json.loads(seen[0].content)
    assert seen[0].headers["x-api-key"] == SECRET
    assert seen[0].headers["anthropic-version"]
    assert body["model"] == "configured-model" and body["system"] == REQUEST.system
    assert body["tool_choice"] == {"type": "tool", "name": "herbaguard_answer"}
    assert body["tools"][0]["input_schema"] == SCHEMA
    assert json.loads(result.text) == {"answer": "x"}
    assert (result.usage.input_tokens, result.usage.output_tokens) == (50, 4)


def test_openai_contract_uses_json_schema_response_format() -> None:
    seen: list[httpx.Request] = []
    reply = {"model": "configured-model", "usage": {"prompt_tokens": 70, "completion_tokens": 6},
             "choices": [{"finish_reason": "stop", "message": {"content": '{"answer": "x"}'}}]}  # fmt: skip
    result = openai(lambda r: httpx.Response(200, json=reply), seen).generate(REQUEST)
    body = json.loads(seen[0].content)
    assert seen[0].url.path == "/v1/chat/completions"
    assert seen[0].headers["authorization"] == f"Bearer {SECRET}"
    assert body["response_format"]["json_schema"]["schema"] == SCHEMA
    assert body["messages"][0]["role"] == "system" and body["seed"] == 7
    assert result.text == '{"answer": "x"}' and result.usage.output_tokens == 6


def test_truncated_output_is_marked_incomplete() -> None:
    reply = {"message": {"content": '{"answer": "trunc'}, "done_reason": "length"}
    result = ollama(lambda r: httpx.Response(200, json=reply)).generate(REQUEST)
    assert result.complete is False


# --------------------------------------------------------------------------- errors


def _raise(exc: Exception) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    return handler


@pytest.mark.parametrize("factory", [ollama, anthropic, openai])
@pytest.mark.parametrize(
    ("handler", "kind"),
    [
        (_raise(httpx.ReadTimeout("slow")), ProviderErrorKind.TIMEOUT),
        (_raise(httpx.ConnectError("refused")), ProviderErrorKind.UNAVAILABLE),
        (lambda r: httpx.Response(401, json={"error": SECRET}), ProviderErrorKind.AUTHENTICATION),
        (lambda r: httpx.Response(404), ProviderErrorKind.MODEL_NOT_FOUND),
        (lambda r: httpx.Response(429), ProviderErrorKind.RATE_LIMITED),
        (lambda r: httpx.Response(503), ProviderErrorKind.UNAVAILABLE),
        (lambda r: httpx.Response(200, text="not json"), ProviderErrorKind.BAD_RESPONSE),
        (lambda r: httpx.Response(200, json={"unexpected": True}), ProviderErrorKind.BAD_RESPONSE),
    ],
)
def test_errors_are_normalised_and_never_leak_secrets(
    factory: Callable[[Handler], LLMProvider], handler: Handler, kind: ProviderErrorKind
) -> None:
    with pytest.raises(ProviderError) as info:
        factory(handler).generate(REQUEST)
    assert info.value.kind is kind
    assert SECRET not in str(info.value) and SECRET not in info.value.message


# --------------------------------------------------------------------------- selection


def test_default_is_local_ollama_and_needs_no_key() -> None:
    chain = generation_chain(settings())
    assert chain.names == (LLMProviderName.OLLAMA,)
    assert isinstance(chain.providers[0], OllamaProvider)
    assert chain.providers[0].model == "qwen3:4b"


@pytest.mark.parametrize("name", [LLMProviderName.ANTHROPIC, LLMProviderName.OPENAI])
def test_selected_cloud_provider_without_key_fails_clearly(name: LLMProviderName) -> None:
    with pytest.raises(ProviderError) as info:
        generation_chain(settings(llm_provider=name))
    assert info.value.kind is ProviderErrorKind.NOT_CONFIGURED
    assert "API key" in info.value.message


def test_cloud_provider_without_model_fails_clearly() -> None:
    with pytest.raises(ProviderError, match="model"):
        build_provider(LLMProviderName.OPENAI, settings(openai_api_key=SECRET))


def test_switching_provider_is_configuration_only() -> None:
    s = settings(llm_provider="anthropic", anthropic_api_key=SECRET, anthropic_model="m")
    chain = generation_chain(s)
    assert isinstance(chain.providers[0], AnthropicProvider) and chain.providers[0].model == "m"


def test_fallback_only_when_configured() -> None:
    plain = generation_chain(settings())
    assert len(plain.providers) == 1
    with_fallback = generation_chain(settings(llm_fallback_provider="extractive"))
    assert with_fallback.names == (LLMProviderName.OLLAMA, LLMProviderName.EXTRACTIVE)
    assert with_fallback.providers[1] is None  # extractive mode, no model


def test_fallback_must_differ_from_primary() -> None:
    with pytest.raises(ValidationError):
        settings(llm_provider="ollama", llm_fallback_provider="ollama")


def test_invalid_provider_name_is_rejected() -> None:
    with pytest.raises(ValidationError):
        settings(llm_provider="not-a-provider")


def test_statuses_never_expose_secrets_or_call_cloud() -> None:
    calls: list[httpx.Request] = []
    tags = {"models": [{"name": "qwen3:4b"}]}
    s = settings(openai_api_key=SECRET, openai_model="m")
    rows = provider_statuses(s, probe_local=True,
                             transport=transport(lambda r: httpx.Response(200, json=tags), calls))  # fmt: skip
    by_name = {status.name: (status, selected) for status, selected, _ in rows}
    assert by_name["ollama"][0].reachable is True and by_name["ollama"][1] is True
    assert by_name["openai"][0].configured is True and by_name["openai"][0].reachable is None
    assert by_name["anthropic"][0].configured is False
    assert {r.url.host for r in calls} == {"127.0.0.1"}  # only the local Ollama was probed
    assert SECRET not in repr(rows)


def test_ollama_status_reports_missing_model() -> None:
    provider = ollama(lambda r: httpx.Response(200, json={"models": [{"name": "other:1b"}]}))
    status = provider.status(probe=True)
    assert status.reachable is False and "ollama pull qwen3:4b" in (status.detail or "")


def test_ollama_status_when_not_running() -> None:
    status = ollama(_raise(httpx.ConnectError("refused"))).status(probe=True)
    assert (status.configured, status.reachable) == (True, False)


def test_empty_environment_values_mean_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Docker Compose passes unset optional variables as empty strings."""
    for name in (
        "LLM_FALLBACK_PROVIDER",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_MODEL",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
    ):
        monkeypatch.setenv(f"HERBAGUARD_{name}", "")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert (s.llm_fallback_provider, s.anthropic_api_key, s.openai_model) == (None, None, None)
    assert len(generation_chain(s).providers) == 1
