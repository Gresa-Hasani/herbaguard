"""AI evidence assistant end-to-end (API → service → retrieval → seeded database), Phase 5.

Uses the synthetic seed of tests/api/conftest.py. The LLM and the embedding model are replaced by
deterministic fakes, so these tests check HerbaGuard's own logic (entity recognition, the
deterministic interaction result, retrieval, citation validation, fallbacks), not a model.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from herbaguard.ai.llm import ChatMessage, Completion, LLMUnavailableError
from herbaguard.api.routes.assistant import get_chat_model, get_embedder
from herbaguard.core.config import AssistantProvider, Settings, get_settings
from herbaguard.models import Chunk
from herbaguard.models.evidence import EMBEDDING_DIMENSION
from herbaguard.repositories import retrieval

pytestmark = pytest.mark.db

GOOD_ANSWER = (
    "HerbaGuard's rules classify St John's wort with warfarin as class A, a documented "
    "interaction [S1]. The EU herbal monograph states that concomitant use with coumarin-type "
    "anticoagulants is contraindicated [S1]. Please talk to your doctor or pharmacist."
)


class FakeChat:
    def __init__(self, *answers: str | Exception) -> None:
        self.name = "fake-model"
        self.answers = list(answers)
        self.calls: list[list[ChatMessage]] = []

    def chat(self, messages: Sequence[ChatMessage]) -> Completion:
        self.calls.append(list(messages))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return Completion(text=answer, model=self.name, duration_ms=5)


class FakeEmbedder:
    name = "fake-embed"
    dimension = EMBEDDING_DIMENSION

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [_vector(t) for t in texts]


def _vector(text: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSION
    for word in text.lower().split():
        vector[hash(word.strip(".,?")) % EMBEDDING_DIMENSION] += 1.0
    return vector


def _ask(
    api: TestClient,
    question: str,
    *,
    chat: FakeChat | None = None,
    embedder: FakeEmbedder | None = None,
    **extra: Any,
) -> dict[str, Any]:
    api.app.dependency_overrides[get_chat_model] = lambda: chat  # type: ignore[attr-defined]
    api.app.dependency_overrides[get_embedder] = lambda: embedder  # type: ignore[attr-defined]
    response = api.post("/api/v1/assistant/ask", json={"question": question, **extra})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_generated_answer_with_deterministic_class_and_pinned_source(api: TestClient) -> None:
    chat = FakeChat(GOOD_ANSWER)
    body = _ask(api, "Does St John's wort interact with warfarin?", chat=chat)
    assert body["mode"] == "generated"
    assert body["generation"]["citation_check"] == "passed"
    assert body["generation"]["attempts"] == 1
    assert body["entities"]["herb_status"] == "resolved"
    assert [d["drug"]["name"] for d in body["entities"]["drugs"]] == ["warfarin"]
    [finding] = body["interaction_findings"]
    assert finding["classification"]["interaction_class"] == "A"
    first = body["citations"][0]
    assert first["marker"] == "S1" and first["cited"] is True
    assert "interaction_result" in first["retrieval"]
    assert first["title"] == "EU monograph Hypericum — 4.5 Interactions (WEU)"
    assert first["href"] == f"/api/v1/evidence/{first['evidence_id']}"
    # The model saw the computed class as a fact and the passage fenced as data.
    prompt = chat.calls[0][1].content
    assert "class A" in prompt and '<passage id="S1">' in prompt
    assert body["disclaimer"] and body["referral"]


def test_invalid_citations_are_retried_then_replaced_by_quotes(api: TestClient) -> None:
    chat = FakeChat("Warfarin is affected [S9].", "Still wrong [S9].")
    body = _ask(api, "Does St John's wort interact with warfarin?", chat=chat)
    assert body["mode"] == "extractive"
    assert body["generation"]["attempts"] == 2
    assert body["generation"]["citation_check"] == "failed"
    assert any("S9" in issue for issue in body["generation"]["citation_issues"])
    assert "rejected by HerbaGuard's citation check" in chat.calls[1][-1].content
    # Extractive answer: deterministic lead + verbatim quotes, every marker resolves.
    assert body["answer"].startswith("HerbaGuard's interaction check")
    markers = {c["marker"] for c in body["citations"]}
    assert "[S" in body["answer"]
    assert all(c["marker"] in markers for c in body["citations"] if c["cited"])


def test_retry_succeeds_on_second_attempt(api: TestClient) -> None:
    chat = FakeChat("No citations at all in this long sentence about warfarin.", GOOD_ANSWER)
    body = _ask(api, "Does St John's wort interact with warfarin?", chat=chat)
    assert body["mode"] == "generated" and body["generation"]["attempts"] == 2


def test_answer_changing_the_class_is_rejected(api: TestClient) -> None:
    wrong = GOOD_ANSWER.replace("class A", "class C")
    body = _ask(api, "Does St John's wort interact with warfarin?", chat=FakeChat(wrong, wrong))
    assert body["mode"] == "extractive"
    assert any("class C" in i for i in body["generation"]["citation_issues"])


def test_unreachable_llm_falls_back_to_extractive(api: TestClient) -> None:
    chat = FakeChat(LLMUnavailableError("connection refused"))
    body = _ask(api, "Can I take St John's wort with my contraceptive pill?", chat=chat)
    assert body["mode"] == "extractive"
    assert "unavailable" in body["generation"]["fallback_reason"]
    assert any(c["cited"] for c in body["citations"])


def test_extractive_mode_never_calls_the_llm(api: TestClient) -> None:
    chat = FakeChat()
    body = _ask(
        api,
        "What do the sources say?",
        chat=chat,
        herb="St John's wort",
        drugs=["sertraline"],
        mode="extractive",
    )
    assert body["mode"] == "extractive" and chat.calls == []
    assert body["interaction_findings"][0]["drug"]["drug"]["name"] == "sertraline"


def test_ambiguous_herb_asks_for_clarification(api: TestClient) -> None:
    chat = FakeChat()
    body = _ask(api, "Can I take ginseng with warfarin?", chat=chat)
    assert body["mode"] == "needs_clarification"
    assert body["entities"]["herb_status"] == "ambiguous"
    assert len(body["entities"]["herb_candidates"]) == 2
    assert chat.calls == [] and body["citations"] == []


def test_dosing_question_is_declined_with_sources(api: TestClient) -> None:
    chat = FakeChat()
    body = _ask(api, "How much St John's wort should I take per day?", chat=chat)
    assert body["mode"] == "declined_dosing" and chat.calls == []
    assert "does not give individual dosing advice" in body["answer"]
    assert all(not c["cited"] for c in body["citations"])


def test_emergency_gets_referral_only(api: TestClient) -> None:
    body = _ask(api, "I took St John's wort and now I have chest pain", chat=FakeChat())
    assert body["mode"] == "emergency_referral"
    assert "112" in body["answer"] and body["citations"] == []


def test_no_relevant_passage_is_insufficient_evidence(api: TestClient) -> None:
    body = _ask(api, "What is the capital of France?", chat=FakeChat())
    assert body["mode"] == "insufficient_evidence"
    assert "does not mean" in body["answer"]
    assert body["entities"]["herb_status"] == "not_mentioned"


def test_unknown_drug_is_reported_not_looked_up(api: TestClient) -> None:
    body = _ask(api, "Anything known?", chat=None, herb="St John's wort", drugs=["unobtainol"])
    assert body["entities"]["drugs"][0]["status"] == "not_found"
    assert any("unobtainol" in note for note in body["notes"])


def test_vector_search_joins_hybrid_retrieval(api: TestClient, db_session: Session) -> None:
    rows = db_session.execute(select(Chunk.id, Chunk.text)).all()
    retrieval.store_embeddings(
        db_session, [(r[0], _vector(r[1])) for r in rows], model=FakeEmbedder.name
    )
    db_session.flush()
    body = _ask(
        api,
        "serotonin syndrome with St John's wort",
        chat=None,
        embedder=FakeEmbedder(),
    )
    assert body["mode"] == "extractive"
    assert any("vector" in c["retrieval"] for c in body["citations"])
    assert any("full_text" in c["retrieval"] for c in body["citations"])


def test_status_without_llm(api: TestClient) -> None:
    api.app.dependency_overrides[get_settings] = lambda: Settings(  # type: ignore[attr-defined]
        environment="test",  # type: ignore[arg-type]
        assistant_provider=AssistantProvider.NONE,
    )
    body = api.get("/api/v1/assistant/status").json()
    assert body["provider"] == "none"
    assert body["chunks_total"] > 0 and body["retrieval"] == "full_text_only"
