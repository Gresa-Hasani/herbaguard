"""Embedding provider contract (mocked Ollama /api/embed and /api/tags)."""

from __future__ import annotations

import json
import math

import httpx
import pytest

from herbaguard.ai.embeddings import EmbeddingError, OllamaEmbeddings, build_embeddings, normalise
from herbaguard.core.config import Settings

TAGS = {"models": [{"name": "bge-m3:latest", "digest": "790764642607abcdef0123"}]}


def provider(vectors: list[list[float]] | None = None, *, seen: list[httpx.Request] | None = None,
             tags: dict[str, object] = TAGS, prefix: str = "") -> OllamaEmbeddings:  # fmt: skip
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json=tags)
        texts = json.loads(request.content)["input"]
        if vectors is None or texts == ["dimension probe"]:
            return httpx.Response(200, json={"embeddings": [[3.0, 4.0, 0.0]] * len(texts)})
        return httpx.Response(200, json={"embeddings": vectors})

    return OllamaEmbeddings(base_url="http://ollama.test", model="bge-m3", timeout=5,
                            query_prefix=prefix, transport=httpx.MockTransport(handler))  # fmt: skip


def test_vectors_are_l2_normalised_and_model_identity_is_recorded() -> None:
    p = provider()
    [vector] = p.embed(["Hyperici herba induces CYP3A4."], "document")
    assert vector == pytest.approx([0.6, 0.8, 0.0])
    info = p.info()
    assert (info.model, info.dimension, info.version) == ("bge-m3", 3, "790764642607abcd")


def test_query_prefix_is_applied() -> None:
    seen: list[httpx.Request] = []
    provider(seen=seen, prefix="search_query: ").embed(["warfarin"], "query")
    bodies = [json.loads(r.content) for r in seen if r.url.path == "/api/embed"]
    assert ["search_query: warfarin"] in [b["input"] for b in bodies]


def test_empty_text_is_rejected_before_any_request() -> None:
    seen: list[httpx.Request] = []
    with pytest.raises(EmbeddingError, match="empty"):
        provider(seen=seen).embed(["  "], "document")
    assert seen == []


def test_dimension_mismatch_is_detected() -> None:
    p = provider([[1.0, 0.0, 0.0], [1.0, 0.0]])
    p.info()  # probe returns 3-d
    with pytest.raises(EmbeddingError, match="different dimension"):
        p.embed(["a", "b"], "document")


def test_missing_model_and_unreachable_service() -> None:
    with pytest.raises(EmbeddingError, match="ollama pull bge-m3"):
        provider(tags={"models": []}).info()

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    p = OllamaEmbeddings(
        base_url="http://x", model="bge-m3", timeout=1, transport=httpx.MockTransport(down)
    )
    with pytest.raises(EmbeddingError, match="could not be reached"):
        p.embed(["text"], "query")


@pytest.mark.parametrize("bad", [[], [math.nan, 1.0], [0.0, 0.0]])
def test_invalid_vectors_are_rejected(bad: list[float]) -> None:
    with pytest.raises(EmbeddingError):
        normalise(bad)


def test_configuration() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert build_embeddings(Settings(_env_file=None, embedding_provider="none")) is None  # type: ignore[call-arg]
    nomic = build_embeddings(s, model="nomic-embed-text")
    assert isinstance(nomic, OllamaEmbeddings)
    assert nomic.prefixes == {"query": "search_query: ", "document": "search_document: "}
