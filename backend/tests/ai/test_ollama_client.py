"""Ollama HTTP client (ADR-009) against a mocked transport: request shape and failure handling."""

from __future__ import annotations

import json

import httpx
import pytest

from herbaguard.ai.llm import (
    ChatMessage,
    LLMUnavailableError,
    OllamaChatModel,
    OllamaEmbedder,
    ollama_status,
)
from herbaguard.core.config import Settings

SETTINGS = Settings(environment="test", ollama_chat_model="qwen2.5:3b")  # type: ignore[arg-type]


def _client(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(base_url="http://ollama.test", transport=handler)


def test_chat_request_is_deterministic_and_parsed() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        assert request.url.path == "/api/chat"
        return httpx.Response(
            200,
            json={
                "model": "qwen2.5:3b",
                "message": {"role": "assistant", "content": " Answer [S1]. "},
                "prompt_eval_count": 900,
                "eval_count": 40,
                "total_duration": 2_500_000_000,
            },
        )

    model = OllamaChatModel(SETTINGS, client=_client(httpx.MockTransport(handler)))
    completion = model.chat([ChatMessage("system", "s"), ChatMessage("user", "u")])
    assert completion.text == "Answer [S1]."
    assert (completion.prompt_tokens, completion.completion_tokens) == (900, 40)
    assert completion.duration_ms == 2500
    assert seen["stream"] is False
    options = seen["options"]
    assert isinstance(options, dict) and options["temperature"] == 0 and "seed" in options


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(404, json={"error": "model 'qwen2.5:3b' not found"}),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"done": True}),
    ],
)
def test_chat_failures_raise_unavailable(response: httpx.Response) -> None:
    model = OllamaChatModel(
        SETTINGS, client=_client(httpx.MockTransport(lambda _request: response))
    )
    with pytest.raises(LLMUnavailableError):
        model.chat([ChatMessage("user", "u")])


def test_connection_error_raises_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    model = OllamaChatModel(SETTINGS, client=_client(httpx.MockTransport(handler)))
    with pytest.raises(LLMUnavailableError, match="ConnectError"):
        model.chat([ChatMessage("user", "u")])


def test_embedder_checks_dimension() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        texts = json.loads(request.content)["input"]
        return httpx.Response(200, json={"embeddings": [[0.1] * 384 for _ in texts]})

    embedder = OllamaEmbedder(SETTINGS, dimension=384, client=_client(httpx.MockTransport(handler)))
    assert len(embedder.embed(["a", "b"])) == 2
    assert embedder.embed([]) == []

    wrong = OllamaEmbedder(SETTINGS, dimension=768, client=_client(httpx.MockTransport(handler)))
    with pytest.raises(LLMUnavailableError, match="384 dimensions"):
        wrong.embed(["a"])


def test_status_lists_models() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"models": [{"name": "qwen2.5:3b"}, {"name": "all-minilm:latest"}]}
        )

    state = ollama_status(SETTINGS, client=_client(httpx.MockTransport(handler)))
    assert state.reachable and state.has("qwen2.5:3b") and state.has("all-minilm")
    assert not state.has("llama3.2:3b")

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    assert not ollama_status(SETTINGS, client=_client(httpx.MockTransport(down))).reachable
