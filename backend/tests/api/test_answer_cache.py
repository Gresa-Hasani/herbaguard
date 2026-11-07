"""Validated-answer cache for the suggested questions.

The language model is a scripted provider (never a real model). These tests check the cache's
behaviour, not model quality: what is stored, when it is served, when it is ignored, and that the
normal pipeline is used for everything else.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from herbaguard.ai import answer_cache
from herbaguard.ai.answer_prepare import prepare_answers
from herbaguard.ai.providers.base import GenerationRequest, ProviderError, ProviderErrorKind
from herbaguard.ai.providers.mock import ScriptedProvider
from herbaguard.ai.providers.registry import GenerationChain
from herbaguard.api.routes.ai import get_embedding_provider, get_generation_chain
from herbaguard.api.schemas.ai import AskResponse
from herbaguard.core.config import LLMProviderName, Settings
from herbaguard.models import AnswerCache, EvidenceItem
from tests.api.test_ai_api import HashEmbeddings, ai, answer, ask, grounded, index, provider_of

__all__ = ["ai", "index"]  # fixtures re-exported for pytest

pytestmark = pytest.mark.db

REAL_QUESTIONS = (
    "What does the evidence say about St John’s wort and warfarin?",
    "Which sources support the use of ginger for nausea?",
    "What interactions are documented for ginkgo?",
)
# The test database does not contain ginger or ginkgo, so the end-to-end tests below register three
# questions that do resolve there. The real strings are covered by the matching tests.
SEEDED = (
    REAL_QUESTIONS[0],
    "What does the evidence say about black cohosh and warfarin?",
    "What does the evidence say about St John's wort and docetaxel?",
)


@pytest.fixture
def suggested(monkeypatch: pytest.MonkeyPatch) -> tuple[str, ...]:
    monkeypatch.setattr(answer_cache, "SUGGESTED_QUESTIONS", SEEDED)
    monkeypatch.setattr(
        answer_cache, "_SUGGESTED_IDS", {answer_cache.question_id(q): q for q in SEEDED}
    )
    return SEEDED


@pytest.fixture
def client(ai: Callable[..., TestClient]) -> TestClient:
    return ai()


def rows(session: Session) -> list[AnswerCache]:
    return list(session.scalars(select(AnswerCache)))


def calls(client: TestClient) -> int:
    return len(provider_of(client).requests)


# --------------------------------------------------------------------------- question matching


@pytest.mark.parametrize("question", REAL_QUESTIONS)
def test_each_suggested_question_is_recognised_exactly(question: str) -> None:
    qid = answer_cache.suggested_question_id(question)
    assert qid == answer_cache.question_id(question) and qid is not None
    # Only typography and spacing are normalised.
    assert answer_cache.suggested_question_id(f"  {question.upper()} ") == qid
    assert answer_cache.suggested_question_id(question.replace("’", "'")) == qid
    assert answer_cache.suggested_question_id(question.replace(" ", "  ")) == qid


@pytest.mark.parametrize("question", REAL_QUESTIONS)
def test_close_variants_are_not_treated_as_suggested(question: str) -> None:
    assert answer_cache.suggested_question_id(question.rstrip("?")) is None
    assert answer_cache.suggested_question_id(question + " Please be brief.") is None
    assert answer_cache.suggested_question_id(question.replace(" ", " really ", 1)) is None
    assert answer_cache.suggested_question_id("Does St John's wort interact with warfarin?") is None


def test_backend_and_frontend_suggestions_are_identical() -> None:
    source = (
        Path(__file__).parents[3] / "frontend" / "src" / "pages" / "AssistantPage.tsx"
    ).read_text(encoding="utf-8")
    start = source.index("const EXAMPLES = [")
    block = source[start : source.index("]", start)]
    shown = [line.strip().strip(",").strip("'") for line in block.splitlines()[1:] if line.strip()]
    assert tuple(shown) == answer_cache.SUGGESTED_QUESTIONS == REAL_QUESTIONS


# --------------------------------------------------------------------------- storing and serving


@pytest.mark.parametrize("position", [0, 1, 2])
def test_each_suggested_question_is_cached_then_served_without_the_model(
    client: TestClient, db_session: Session, suggested: tuple[str, ...], position: int
) -> None:
    question = suggested[position]
    first = ask(client, question)
    assert first["status"] == "answered" and first["cache"] is None
    assert calls(client) == 1

    [row] = rows(db_session)
    assert row.question_id == answer_cache.question_id(question)
    assert (
        row.validation_status == "passed" and row.provider == "ollama" and row.model == "qwen3:4b"
    )
    assert row.generated_at <= datetime.now(UTC) and row.prompts and row.citation_labels

    second = ask(client, question)
    assert calls(client) == 1  # served from the cache: no language-model request
    assert second["cache"]["served_from_cache"] is True
    assert second["cache"]["validation_status"] == "passed"
    assert second["cache"]["generated_at"] is not None


def test_cached_response_keeps_the_complete_contract_and_all_evidence(
    client: TestClient, suggested: tuple[str, ...]
) -> None:
    first = ask(client, suggested[0])
    second = ask(client, suggested[0])

    AskResponse.model_validate(second)  # same response schema as a normal answer
    for field in (
        "status", "question", "intent", "answer", "paragraphs", "classification", "citations",
        "limitations", "insufficient_evidence", "entities", "personal_advice_requested",
        "validation", "disclaimer",
    ):  # fmt: skip
        assert second[field] == first[field], field
    # citations, provenance and classification are intact
    assert second["citations"] and all(
        c["provenance"] for c in second["citations"] if c["source_code"]
    )
    assert (
        second["classification"][0]["interaction_class"]
        == first["classification"][0]["interaction_class"]
    )
    assert second["generation"]["model"] == first["generation"]["model"]
    assert second["generation"]["prompts"] == first["generation"]["prompts"]


def test_cached_response_does_not_present_old_generation_time_as_its_own(
    client: TestClient, suggested: tuple[str, ...]
) -> None:
    first = ask(client, suggested[0])
    second = ask(client, suggested[0])
    assert second["generation"]["duration_ms"] == 0
    assert second["cache"]["original_generation_ms"] == first["generation"]["duration_ms"]
    # retrieval information is this request's own
    assert second["retrieval"] is not None and second["retrieval"]["mode_used"]


def test_the_returned_question_is_the_one_just_asked(
    client: TestClient, suggested: tuple[str, ...]
) -> None:
    ask(client, suggested[0])
    straight = suggested[0].replace("’", "'")
    again = ask(client, straight)
    assert again["cache"] is not None and again["question"] == straight


# --------------------------------------------------------------------------- invalid and outdated


def test_changed_evidence_makes_the_cached_answer_unservable(
    client: TestClient, db_session: Session, suggested: tuple[str, ...]
) -> None:
    first = ask(client, suggested[0])
    old = rows(db_session)[0].fingerprint
    cited = next(c for c in first["citations"] if c["kind"] == "statement")
    db_session.execute(
        update(EvidenceItem)
        .where(EvidenceItem.title == cited["title"])
        .values(title=cited["title"] + " (revised edition)")
    )
    db_session.flush()

    third = ask(client, suggested[0])
    assert third["cache"] is None and calls(client) == 2  # fell back to the normal pipeline
    [row] = rows(db_session)  # the new validated answer replaced the stale entry
    assert row.fingerprint != old
    assert ask(client, suggested[0])["cache"] is not None and calls(client) == 2


def test_unrelated_evidence_changes_do_not_invalidate(
    client: TestClient, db_session: Session, suggested: tuple[str, ...]
) -> None:
    ask(client, suggested[0])
    ask(client, suggested[1])
    first_row = next(r for r in rows(db_session) if r.question_text == suggested[0])
    second_fingerprint = next(
        r for r in rows(db_session) if r.question_text == suggested[1]
    ).fingerprint
    # change something that is not part of the first question's evidence context
    db_session.execute(
        update(EvidenceItem).where(EvidenceItem.title.ilike("%cohosh%")).values(title="Cohosh edit")
    )
    db_session.flush()
    again = ask(client, suggested[0])
    assert again["cache"] is not None and calls(client) == 2
    assert (
        first_row.fingerprint
        == next(r for r in rows(db_session) if r.question_text == suggested[0]).fingerprint
    )
    assert second_fingerprint  # untouched entry stays on file


def test_prompt_validation_and_generator_changes_invalidate(
    client: TestClient,
    db_session: Session,
    suggested: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ask(client, suggested[0])
    assert calls(client) == 1

    monkeypatch.setattr(answer_cache, "validation_version", lambda: "changed-rules")
    assert ask(client, suggested[0])["cache"] is None and calls(client) == 2
    monkeypatch.undo()
    monkeypatch.setattr(answer_cache, "SUGGESTED_QUESTIONS", SEEDED)
    monkeypatch.setattr(
        answer_cache, "_SUGGESTED_IDS", {answer_cache.question_id(q): q for q in SEEDED}
    )

    # the validation rules are back to what the entry was written under only after a rewrite
    entry = rows(db_session)[0]
    assert entry.validation_version == "changed-rules"
    assert ask(client, suggested[0])["cache"] is None  # stale rule version is not served

    original_load = answer_cache.load_prompt

    def edited(name: str, version: int = 1) -> Any:
        prompt = original_load(name, version)
        return type(prompt)(prompt.id, prompt.version, prompt.text + "\nEdited.")

    ask(client, suggested[0])  # make sure a current-rules entry exists
    assert ask(client, suggested[0])["cache"] is not None
    monkeypatch.setattr(answer_cache, "load_prompt", edited)
    assert ask(client, suggested[0])["cache"] is None


def test_fingerprint_depends_on_model_and_generation_settings() -> None:
    def fingerprint(settings: Settings) -> str:
        from herbaguard.ai import context as ctx
        from herbaguard.ai.query import Intent

        return answer_cache.compute_fingerprint(
            settings=settings, chain_names=("ollama",), qid="q", intent=Intent.GENERAL,
            expected=set(), personal_advice=False, partial=False,
            context=ctx.EvidenceContext(items=[]), citations=[], classifications=[],
        )  # fmt: skip

    base = Settings(_env_file=None)  # type: ignore[call-arg]
    same = Settings(_env_file=None)  # type: ignore[call-arg]
    assert fingerprint(base) == fingerprint(same)
    for change in ({"llm_model": "other:model"}, {"llm_seed": 7}, {"llm_temperature": 0.5},
                   {"ai_context_max_items": 6}, {"llm_max_output_tokens": 700}):  # fmt: skip
        assert fingerprint(base) != fingerprint(base.model_copy(update=change)), change


def test_expired_entries_are_not_served(
    client: TestClient, db_session: Session, suggested: tuple[str, ...]
) -> None:
    ask(client, suggested[0])
    [row] = rows(db_session)
    row.generated_at = datetime.now(UTC) - timedelta(days=400)
    db_session.flush()
    assert ask(client, suggested[0])["cache"] is None and calls(client) == 2


def test_a_payload_that_no_longer_fits_the_contract_is_never_served(
    client: TestClient, db_session: Session, suggested: tuple[str, ...]
) -> None:
    ask(client, suggested[0])
    [row] = rows(db_session)
    row.response = {"status": "answered"}
    db_session.flush()
    assert ask(client, suggested[0])["cache"] is None and calls(client) == 2


def test_a_disabled_cache_neither_serves_nor_stores(
    client: TestClient, db_session: Session, suggested: tuple[str, ...]
) -> None:
    from herbaguard.api.routes.ai import get_settings

    client.app.dependency_overrides[get_settings] = lambda: Settings(  # type: ignore[attr-defined]
        environment="test", ai_answer_cache_enabled=False
    )  # type: ignore[call-arg]
    ask(client, suggested[0])
    ask(client, suggested[0])
    assert calls(client) == 2 and rows(db_session) == []


# --------------------------------------------------------------------------- nothing unvalidated is stored


def test_rejected_generation_is_not_cached(
    ai: Callable[..., TestClient], db_session: Session, suggested: tuple[str, ...]
) -> None:
    def wrong_class(request: GenerationRequest) -> str:
        return answer([("HerbaGuard classifies this pair as class E.", ["C1"])])

    client = ai(wrong_class)
    body = ask(client, suggested[0])
    assert body["status"] == "rejected_by_validation"
    assert rows(db_session) == []


def test_insufficient_provider_failure_and_extractive_fallback_are_not_cached(
    ai: Callable[..., TestClient], db_session: Session, suggested: tuple[str, ...]
) -> None:
    failing = ai(
        lambda r: ProviderError("ollama", ProviderErrorKind.UNAVAILABLE, "down"), fallback=True
    )
    body = ask(failing, suggested[0])
    assert body["generation"]["mode"] == "extractive" and rows(db_session) == []

    nothing = ai(lambda r: ProviderError("ollama", ProviderErrorKind.UNAVAILABLE, "down"))
    ask(nothing, suggested[0], status=503)
    assert rows(db_session) == []

    insufficient = ai(lambda r: answer([], insufficient=True))
    ask(insufficient, suggested[0])
    assert rows(db_session) == []


def test_a_failed_regeneration_leaves_the_previous_valid_entry_alone(
    ai: Callable[..., TestClient], db_session: Session, suggested: tuple[str, ...]
) -> None:
    ask(ai(), suggested[0])
    [before] = rows(db_session)
    old_fingerprint, old_response = before.fingerprint, dict(before.response)

    broken = ai(lambda r: ProviderError("ollama", ProviderErrorKind.TIMEOUT, "slow"))
    from herbaguard.ai import service as ai_service

    with pytest.raises(Exception, match="not available"):
        ai_service.ask(
            db_session, Settings(environment="test"),  # type: ignore[call-arg]
            question=suggested[0], allow_remote_drug_lookup=False,
            chain=broken.app.dependency_overrides[get_generation_chain](),  # type: ignore[attr-defined]
            embeddings=broken.app.dependency_overrides[get_embedding_provider](),  # type: ignore[attr-defined]
            refresh_answer_cache=True,
        )  # fmt: skip
    [after] = rows(db_session)
    assert (after.fingerprint, after.response) == (old_fingerprint, old_response)


# --------------------------------------------------------------------------- other questions


def test_arbitrary_questions_always_use_the_normal_pipeline(
    client: TestClient, db_session: Session, suggested: tuple[str, ...]
) -> None:
    other = "Does St John's wort interact with warfarin?"
    assert answer_cache.suggested_question_id(other) is None
    a = ask(client, other)
    b = ask(client, other)
    assert a["cache"] is None and b["cache"] is None
    assert calls(client) == 2 and rows(db_session) == []


def test_a_cache_miss_never_fails_the_request(
    client: TestClient, db_session: Session, suggested: tuple[str, ...]
) -> None:
    assert rows(db_session) == []
    body = ask(client, suggested[1])
    assert body["status"] == "answered" and body["paragraphs"] and calls(client) == 1


# --------------------------------------------------------------------------- preparation


class RecordingProvider(ScriptedProvider):
    """Tracks which questions were generated and whether two generations ever overlapped."""

    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.order: list[str] = []
        self.lock = threading.Lock()
        super().__init__(self._reply_slowly, name="ollama", model="qwen3:4b")

    def _reply_slowly(self, request: GenerationRequest) -> str:
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.order.append(request.messages[0].content.split("\n")[1])
        time.sleep(0.02)
        with self.lock:
            self.active -= 1
        return grounded(request)


def test_preparation_runs_questions_one_after_another_and_skips_valid_entries(
    db_session: Session, index: HashEmbeddings, suggested: tuple[str, ...]
) -> None:
    provider = RecordingProvider()
    chain = GenerationChain((LLMProviderName.OLLAMA,), (provider,))
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    started: list[int] = []

    first = prepare_answers(
        lambda: db_session, settings, chain, index, questions=suggested,
        on_start=lambda i, q: started.append(i),
    )  # fmt: skip
    assert [r.outcome for r in first] == ["generated"] * 3
    assert started == [1, 2, 3]
    assert provider.max_active == 1  # never two generations at once
    assert [q.split("QUESTION")[0] for q in provider.order] == provider.order
    assert [s in o for s, o in zip(suggested, provider.order, strict=True)] == [True] * 3
    assert len(rows(db_session)) == 3

    again = prepare_answers(lambda: db_session, settings, chain, index, questions=suggested)
    assert [r.outcome for r in again] == ["already_valid"] * 3
    assert len(provider.order) == 3  # nothing regenerated

    refreshed = prepare_answers(
        lambda: db_session, settings, chain, index, questions=suggested[:1], refresh=True
    )
    assert [r.outcome for r in refreshed] == ["generated"] and len(provider.order) == 4
    assert provider.max_active == 1


def test_preparation_reports_failures_and_keeps_going(
    db_session: Session, index: HashEmbeddings, suggested: tuple[str, ...]
) -> None:
    calls_seen = {"n": 0}

    def flaky(request: GenerationRequest) -> str | ProviderError:
        calls_seen["n"] += 1
        if calls_seen["n"] == 1:
            return ProviderError("ollama", ProviderErrorKind.TIMEOUT, "slow")
        return grounded(request)

    chain = GenerationChain((LLMProviderName.OLLAMA,), (ScriptedProvider(flaky, name="ollama"),))
    results = prepare_answers(
        lambda: db_session,
        Settings(_env_file=None),
        chain,
        index,
        questions=suggested,  # type: ignore[call-arg]
    )
    assert [r.outcome for r in results] == ["failed", "generated", "generated"]
    assert len(rows(db_session)) == 2
