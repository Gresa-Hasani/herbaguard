"""LiverTox hepatotoxicity context (H# items) in the AI layer, on the seeded test database.

The LiverTox fixture (tests/fixtures/livertox + the master list written by ``write_master_list``)
has St John's wort resolved with master-list score D and chapter score E (they disagree), Hawthorn
ambiguous (two seeded Crataegus species) and nothing for Black cohosh.
"""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from herbaguard.ai.providers.base import GenerationRequest
from herbaguard.ai.providers.mock import ScriptedProvider
from herbaguard.ai.providers.registry import GenerationChain
from herbaguard.api.routes.ai import get_embedding_provider, get_generation_chain
from herbaguard.core.config import LLMProviderName, Settings
from herbaguard.ingestion.context import run_ingestion
from herbaguard.ingestion.loaders import ensure_sources
from herbaguard.ingestion.pipelines import livertox
from herbaguard.models import ExternalEntity, InteractionAssertion
from tests.api.test_external_datasets import write_master_list

pytestmark = pytest.mark.db
FIXTURES = Path(__file__).parents[1] / "fixtures" / "livertox"
NO_RECORD = "HerbaGuard has no LiverTox record mapped to"


@pytest.fixture
def imported(db_session: Session, seeded: dict[str, object], tmp_path: Path) -> None:
    folder = tmp_path / "livertox"
    shutil.copytree(FIXTURES, folder)
    write_master_list(folder)
    ensure_sources(db_session)
    with run_ingestion(db_session, "livertox", Settings(_env_file=None)) as ctx:  # type: ignore[call-arg]
        livertox.run(ctx, folder)


def answer(paragraphs: list[tuple[str, list[str]]]) -> str:
    return json.dumps({"paragraphs": [{"text": t, "citations": c} for t, c in paragraphs],
                       "limitations": [], "insufficient_evidence": False})  # fmt: skip


def _client(
    api: TestClient, reply: Callable[[GenerationRequest], str]
) -> tuple[TestClient, ScriptedProvider]:
    provider = ScriptedProvider(reply, name="ollama", model="qwen3:4b")
    chain = GenerationChain((LLMProviderName.OLLAMA,), (provider,))
    api.app.dependency_overrides[get_generation_chain] = lambda: chain  # type: ignore[attr-defined]
    api.app.dependency_overrides[get_embedding_provider] = lambda: None  # type: ignore[attr-defined]
    return api, provider


def h_ids(request: GenerationRequest) -> list[str]:
    return re.findall(r'id="(H\d+)"', request.messages[0].content)


def ask(client: TestClient, question: str, status: int = 200) -> dict[str, Any]:
    response = client.post(
        "/api/v1/ai/ask", json={"question": question, "allow_remote_drug_lookup": False}
    )
    assert response.status_code == status, response.text
    body: dict[str, Any] = response.json()
    return body


def careful(request: GenerationRequest) -> str:
    ids = h_ids(request)
    return answer([("LiverTox gives St John's wort a master list likelihood score of D and a chapter likelihood "
                    "score of E; LiverTox publishes both.", ids[:1])]) if ids else answer([])  # fmt: skip


def test_liver_question_gets_labelled_livertox_items_with_both_scores(
    api: TestClient, imported: None
) -> None:
    client, provider = _client(api, careful)
    body = ask(client, "Does St John's wort cause liver injury?")
    prompt = provider.requests[0].messages[0].content
    assert 'role="hepatotoxicity_evidence"' in prompt
    assert "LiverTox (NIDDK/NLM) hepatotoxicity evidence" in prompt
    assert "it is NOT a HerbaGuard interaction class" in prompt
    assert "'unlikely cause of liver injury' does not mean safe" in prompt
    assert "LiverTox master list likelihood score: D" in prompt
    assert "Likelihood score: E (unlikely cause of clinically apparent liver injury)" in prompt
    assert "The master list and the chapter give different scores" in prompt
    assert "Synthetic hepatotoxicity text" in prompt  # verbatim chapter passage
    assert (
        "3b." in provider.requests[0].system
        and "never call it a class" in provider.requests[0].system
    )

    cited = [c for c in body["citations"] if c["kind"] == "hepatotoxicity"]
    assert cited and cited[0]["role"] == "hepatotoxicity_evidence"
    provenance = cited[0]["provenance"]
    assert {p["source_code"] for p in provenance} == {"livertox"}
    assert {p["extraction_method"] for p in provenance} == {
        "livertox_masterlist_v1",
        "livertox_nxml_v1",
    }
    assert not {i["rule"] for i in body["validation"]} & {
        "livertox_score_as_class",
        "hepatotoxicity_overstated",
    }


def test_question_not_about_the_liver_gets_no_livertox_context(
    api: TestClient, imported: None
) -> None:
    client, provider = _client(
        api, lambda r: answer([("HerbaGuard gives class A for this pair.", ["C1"])])
    )
    ask(client, "Does St John's wort interact with warfarin?")
    prompt = provider.requests[0].messages[0].content
    assert "hepatotoxicity_evidence" not in prompt and "LiverTox" not in prompt


def test_livertox_does_not_change_the_classification(
    api: TestClient, db_session: Session, imported: None
) -> None:
    before = sorted(
        db_session.execute(
            select(
                InteractionAssertion.id,
                InteractionAssertion.statement_type,
                InteractionAssertion.evidence_type,
                InteractionAssertion.status,
            )
        ).all()
    )
    client, provider = _client(api, careful)
    body = ask(client, "Can St John's wort with warfarin harm the liver?")
    assert body["classification"][0]["interaction_class"] == "A"
    assert h_ids(provider.requests[0])
    after = sorted(
        db_session.execute(
            select(
                InteractionAssertion.id,
                InteractionAssertion.statement_type,
                InteractionAssertion.evidence_type,
                InteractionAssertion.status,
            )
        ).all()
    )
    assert before == after


def test_herb_without_a_livertox_record_gets_the_absence_fact(
    api: TestClient, imported: None
) -> None:
    client, provider = _client(api, lambda r: answer([]))
    ask(client, "Is black cohosh toxic to the liver?")
    prompt = provider.requests[0].messages[0].content
    assert NO_RECORD in prompt and "does not show that the herb is safe for the liver" in prompt
    assert not h_ids(provider.requests[0])


def test_ambiguous_livertox_agent_is_not_used(api: TestClient, imported: None) -> None:
    """LiverTox 'Hawthorn' matches two seeded Crataegus species → ambiguous → absence fact only."""
    client, provider = _client(api, lambda r: answer([]))
    ask(client, "Can hawthorn damage the liver?")
    prompt = provider.requests[0].messages[0].content
    assert NO_RECORD in prompt and not h_ids(provider.requests[0])


def test_candidate_livertox_agent_is_not_used(
    api: TestClient, db_session: Session, imported: None
) -> None:
    db_session.execute(update(ExternalEntity).where(ExternalEntity.source_code == "livertox",
                                                    ExternalEntity.external_id == "stjohnswort")
                       .values(mapping_status="candidate"))  # fmt: skip
    client, provider = _client(api, lambda r: answer([]))
    ask(client, "Does St John's wort cause liver injury?")
    prompt = provider.requests[0].messages[0].content
    assert NO_RECORD in prompt and not h_ids(provider.requests[0])


def test_ambiguous_herb_name_is_not_resolved_for_a_liver_question(
    api: TestClient, imported: None
) -> None:
    client, provider = _client(api, lambda r: answer([]))
    ask(client, "Can ginseng damage the liver?", status=409)
    assert provider.requests == []


@pytest.mark.parametrize(("text", "rule"), [
    ("St John's wort is LiverTox class E, so it is fine.", "livertox_score_as_class"),
    ("LiverTox classifies St John's wort as E for the liver.", "livertox_score_as_class"),
    ("St John's wort does not cause liver damage.", "hepatotoxicity_overstated"),
    ("St John's wort is safe for the liver.", "hepatotoxicity_overstated"),
])  # fmt: skip
def test_overstated_livertox_answers_are_rejected(
    api: TestClient, imported: None, text: str, rule: str
) -> None:
    client, _ = _client(api, lambda r: answer([(text, h_ids(r)[:1])]))
    body = ask(client, "Does St John's wort cause liver injury?")
    issues = {(i["rule"], i["severity"]) for i in body["validation"]}
    assert (rule, "critical") in issues
    assert all(text not in p["text"] for p in body["paragraphs"])
