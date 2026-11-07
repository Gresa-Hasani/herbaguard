"""NIH DSLD product-label information (P# items) in the AI layer, on the seeded test database.

The DSLD fixture (tests/fixtures/nih_dsld) has St John's wort resolved on products 1001 (SJW 300,
with a "Precautions" statement) and 1004 (Calm Combo), Hawthorn ambiguous and a ginkgo leaf extract
name that does not match exactly. Labels are product information only: they never feed the A–E
classification and never establish an interaction or safety.
"""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from herbaguard.ai import context as ctx
from herbaguard.ai import service
from herbaguard.ai.providers.base import GenerationRequest
from herbaguard.ai.providers.mock import ScriptedProvider
from herbaguard.ai.providers.registry import GenerationChain
from herbaguard.api.routes.ai import get_embedding_provider, get_generation_chain
from herbaguard.core.config import LLMProviderName, Settings
from herbaguard.ingestion.context import run_ingestion
from herbaguard.ingestion.loaders import ensure_sources
from herbaguard.ingestion.pipelines import nih_dsld
from herbaguard.models import ExternalEntity, HerbalSubstance, InteractionAssertion

pytestmark = pytest.mark.db
FIXTURES = Path(__file__).parents[1] / "fixtures" / "nih_dsld"
QUESTION = "Is St John's wort safe?"
LABEL_RULES = {"product_label_as_clinical", "product_label_as_efficacy", "product_label_dosing"}


@pytest.fixture
def imported(db_session: Session, seeded: dict[str, object], tmp_path: Path) -> None:
    folder = tmp_path / "nih_dsld"
    shutil.copytree(FIXTURES, folder)
    ensure_sources(db_session)
    with run_ingestion(db_session, "nih_dsld", Settings(_env_file=None)) as context:  # type: ignore[call-arg]
        nih_dsld.run(context, folder)


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


def ask(client: TestClient, question: str, status: int = 200) -> dict[str, Any]:
    response = client.post(
        "/api/v1/ai/ask", json={"question": question, "allow_remote_drug_lookup": False}
    )
    assert response.status_code == status, response.text
    body: dict[str, Any] = response.json()
    return body


def blocks(request: GenerationRequest) -> dict[str, str]:
    """P# id → its rendered block (text and qualifiers)."""
    return dict(
        re.findall(
            r'<evidence id="(P\d+)"[^>]*>\n(.*?)\n</evidence>', request.messages[0].content, re.S
        )
    )


def p_ids(request: GenerationRequest) -> list[str]:
    return list(blocks(request))


def find(request: GenerationRequest, needle: str) -> str:
    return next(k for k, v in blocks(request).items() if needle in v)


def as_found(substance: HerbalSubstance) -> Any:
    """The subset of a resolved herb that _product_label_items reads."""
    return SimpleNamespace(
        substance_ids=[substance.id],
        herb=SimpleNamespace(
            common_name=substance.common_name_en,
            pharmaceutical_name=substance.pharmaceutical_name,
        ),
    )


# --------------------------------------------------------------------------- context and provenance


def test_herb_question_gets_a_labelled_product_label_with_identifiers(
    api: TestClient, imported: None
) -> None:
    def reply(request: GenerationRequest) -> str:
        label_id = find(request, "SJW 300")
        return answer([("The product label for 'SJW 300' lists 300 mg of St John's wort per serving "
                        "and a manufacturer's precaution about anticoagulants.", [label_id])])  # fmt: skip

    client, provider = _client(api, reply)
    body = ask(client, QUESTION)
    request = provider.requests[0]
    prompt = request.messages[0].content

    assert 'role="product_label_information"' in prompt
    assert "NIH DSLD product-label information" in prompt
    assert "NOT clinical evidence" in prompt
    assert "licence not verified" in prompt
    assert "SJW 300" in prompt and "DSLD ID: 1001" in prompt
    assert "300 mg per serving" in prompt
    assert "Consult your physician if you take anticoagulants." in prompt
    assert "3d." in request.system and 'role="product_label_information"' in request.system

    assert body["classification"] == []
    cited = [c for c in body["citations"] if c["kind"] == "product_label"]
    product = next(c for c in cited if c["external_id"] == "1001")
    assert product["role"] == "product_label_information"
    assert product["source_code"] == "nih_dsld"
    assert product["url"] == "https://dsld.od.nih.gov/label/1001"
    assert product["evidence_item_id"] is None  # structured data, not an evidence item
    assert product["provenance"]
    assert {p["source_code"] for p in product["provenance"]} == {"nih_dsld"}
    assert {p["licence_status"] for p in product["provenance"]} == {"to_verify"}
    assert {p["extraction_method"] for p in product["provenance"]} == {"dsld_csv_v1"}
    assert not {i["rule"] for i in body["validation"]} & LABEL_RULES


def test_ambiguous_ingredient_is_not_used(
    db_session: Session, seeded: dict[str, object], imported: None
) -> None:
    hawthorn = cast(HerbalSubstance, seeded["hawthorn"])
    assert service._product_label_items(db_session, as_found(hawthorn)) == []


def test_candidate_ingredient_is_not_used(
    db_session: Session, seeded: dict[str, object], imported: None
) -> None:
    db_session.execute(
        update(ExternalEntity)
        .where(
            ExternalEntity.source_code == "nih_dsld",
            ExternalEntity.kind == "dsld_ingredient",
            ExternalEntity.external_id == "st john's wort",
        )
        .values(mapping_status="candidate")
    )
    db_session.flush()
    sjw = cast(HerbalSubstance, seeded["sjw"])
    assert service._product_label_items(db_session, as_found(sjw)) == []


def test_product_labels_are_not_used_for_interaction_questions(
    api: TestClient, imported: None
) -> None:
    client, provider = _client(api, lambda r: answer([]))
    ask(client, "Does St John's wort interact with warfarin?")
    assert "product_label_information" not in provider.requests[0].messages[0].content


def test_product_labels_do_not_change_the_classification_or_assertions(
    api: TestClient, db_session: Session, imported: None
) -> None:
    before = sorted(
        db_session.execute(select(InteractionAssertion.id, InteractionAssertion.status)).all()
    )
    client, provider = _client(api, lambda r: answer([("The product label lists 300 mg of "
                                                        "St John's wort per serving.",
                                                        p_ids(r)[:1])]))  # fmt: skip
    body = ask(client, QUESTION)
    assert p_ids(provider.requests[0])
    assert body["classification"] == []
    after = sorted(
        db_session.execute(select(InteractionAssertion.id, InteractionAssertion.status)).all()
    )
    assert before == after


def test_product_labels_are_not_sent_to_cloud_models() -> None:
    item = ctx.product_label_item(
        text="NIH DSLD label text.", title="NIH DSLD: test", location="test",
        url=None, external_id="1001", provenance=[],
    )  # fmt: skip
    local = ctx.assemble([item], max_tokens=2600, max_items=8)
    assert [i.kind for i in local.items] == ["product_label"]
    assert local.items[0].redistributable is False
    cloud = ctx.assemble([item], max_tokens=2600, max_items=8, cloud_only_redistributable=True)
    assert cloud.items == [] and cloud.excluded_for_licence == 1


# --------------------------------------------------------------------------- validation


@pytest.mark.parametrize(("text", "rule"), [
    ("St John's wort interacts with warfarin.", "product_label_as_clinical"),
    ("This product is safe to take with warfarin.", "product_label_as_clinical"),
    ("This product treats depression.", "product_label_as_efficacy"),
    ("Take 300 mg daily.", "product_label_dosing"),
])  # fmt: skip
def test_clinical_conclusions_from_labels_only_are_rejected(
    api: TestClient, imported: None, text: str, rule: str
) -> None:
    client, _ = _client(api, lambda r: answer([(text, p_ids(r)[:1])]))
    body = ask(client, QUESTION)
    issues = {(i["rule"], i["severity"]) for i in body["validation"]}
    assert (rule, "critical") in issues
    assert all(text not in p["text"] for p in body["paragraphs"])


def test_attributed_label_wording_is_allowed(api: TestClient, imported: None) -> None:
    client, _ = _client(api, lambda r: answer([
        ("The product label states: 'Consult your physician if you take anticoagulants.'",
         p_ids(r)[:1]),
    ]))  # fmt: skip
    body = ask(client, QUESTION)
    assert body["status"] == "answered"
    assert not {i["rule"] for i in body["validation"]} & LABEL_RULES
    assert body["citations"] and body["citations"][0]["kind"] == "product_label"
