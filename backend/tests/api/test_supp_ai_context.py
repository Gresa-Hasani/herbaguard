"""SUPP.AI supplementary interaction mentions (U# items) in the AI layer, on the seeded test database.

The SUPP.AI fixture (tests/fixtures/supp_ai) is copied and extended at test time for St John's wort +
warfarin: the fixture's clinical-study mention (PMID 900001) and retracted mention (PMID 900002), plus
an animal-study mention (PMID 900003) and a negated mention whose paper has no study flags (PMID
900004). St John's wort + sertraline has one mention whose paper metadata is missing. SUPP.AI
"Hawthorn" is ambiguous and "Black Cohosh Extract" a candidate.
"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from herbaguard.ai import service
from herbaguard.ai.context import ContextItem, mention_item
from herbaguard.ai.mentions import study_type
from herbaguard.ai.providers.base import GenerationRequest
from herbaguard.ai.providers.mock import ScriptedProvider
from herbaguard.ai.providers.registry import GenerationChain
from herbaguard.ai.validation import mention_issue
from herbaguard.api.routes.ai import get_embedding_provider, get_generation_chain
from herbaguard.core.config import LLMProviderName, Settings
from herbaguard.ingestion.context import run_ingestion
from herbaguard.ingestion.loaders import ensure_sources
from herbaguard.ingestion.pipelines import ddid, livertox, supp_ai
from herbaguard.models import ExternalEntity, InteractionAssertion, Target
from tests.api.test_external_datasets import write_master_list

pytestmark = pytest.mark.db
FIXTURES = Path(__file__).parents[1] / "fixtures"
PAIR = "C0813171-C0043031"  # St John's wort – warfarin


def _sentence(uid: int, paper_id: str, text: str) -> dict[str, Any]:
    return {"arg1": {"id": "C0813171", "span": [0, 14]}, "arg2": {"id": "C0043031", "span": [text.find("warfarin"),
            text.find("warfarin") + 8]}, "confidence": None, "paper_id": paper_id, "sentence": text,
            "sentence_id": 2, "uid": uid}  # fmt: skip


def extended_fixture(folder: Path) -> None:
    shutil.copytree(FIXTURES / "supp_ai", folder)
    sentences = json.loads((folder / "sentence_dict.json").read_text(encoding="utf-8"))
    sentences[PAIR] += [
        _sentence(300, "900003", "St John's wort decreased warfarin exposure in rats."),
        _sentence(301, "900004", "St John's wort did not alter warfarin pharmacokinetics."),
    ]
    papers = json.loads((folder / "paper_metadata.json").read_text(encoding="utf-8"))
    papers["900004"] = {"animal_study": False, "authors": [], "clinical_study": False, "doi": None,
                        "fields_of_study": [], "human_study": False, "pmid": 900004, "retraction": False,
                        "title": "Synthetic study without study flags", "venue": "Test Journal", "year": 2015}  # fmt: skip
    for name, data in (("sentence_dict.json", sentences), ("paper_metadata.json", papers)):
        (folder / name).write_text(json.dumps(data, indent=4), encoding="utf-8")  # release layout


def _import(session: Session, source: str, run: Callable[..., None], folder: Path) -> None:
    ensure_sources(session)
    with run_ingestion(session, source, Settings(_env_file=None)) as ctx:  # type: ignore[call-arg]
        run(ctx, folder)


@pytest.fixture
def imported(db_session: Session, seeded: dict[str, object], tmp_path: Path) -> None:
    extended_fixture(tmp_path / "supp_ai")
    _import(db_session, "supp_ai", supp_ai.run, tmp_path / "supp_ai")


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


def mentions(request: GenerationRequest) -> dict[str, str]:
    """U# id → its rendered block (text and qualifiers)."""
    return dict(
        re.findall(
            r'<evidence id="(U\d+)"[^>]*>\n(.*?)\n</evidence>', request.messages[0].content, re.S
        )
    )


def find(request: GenerationRequest, needle: str) -> str:
    return next(k for k, v in mentions(request).items() if needle in v)


QUESTION = "Does St John's wort interact with warfarin?"


# --------------------------------------------------------------------------- retrieval and labels


def test_eligible_mentions_are_labelled_with_study_type_negation_and_provenance(
    api: TestClient, imported: None
) -> None:
    client, provider = _client(api, lambda r: answer([("A SUPP.AI machine-extracted mention reports that St John's "
                                                        "wort reduced the anticoagulant effect of warfarin.",
                                                        [find(r, "PMID 900001")])]))  # fmt: skip
    body = ask(client, QUESTION)
    request = provider.requests[0]
    found = mentions(request)
    # At most one mention is included in a context (context.MENTION_LIMIT): the pair's highest-ranked
    # eligible mention, the clinical-study paper. The labels of the other study types are covered by
    # test_supp_ai_audit_fixes.test_every_mention_keeps_its_safety_labels.
    assert len(found) == 1
    clinical = next(iter(found.values()))
    assert "PMID 900001" in clinical
    assert (
        "study type: clinical study" in clinical
        and "Negation applying to this pair: none detected" in clinical
    )
    # retracted paper excluded (only the exclusion count is mentioned)
    assert "Retracted synthetic report" not in clinical and "900002" not in clinical
    for block in found.values():
        assert "SUPP.AI machine-extracted supplementary interaction mention" in block
        assert "NOT a confirmed interaction" in block and "never sent to cloud models" in block
    prompt = request.messages[0].content
    assert 'role="supplementary_mention"' in prompt and 'source="supp_ai"' in prompt
    assert "SUPP.AI holds 3 eligible machine-extracted mention(s)" in prompt
    assert "1 mention(s) from retracted papers" in prompt
    assert "3c." in request.system

    cited = next(c for c in body["citations"] if c["kind"] == "mention")
    assert cited["role"] == "supplementary_mention" and cited["external_id"] == "PMID:900001"
    assert cited["url"] == "https://pubmed.ncbi.nlm.nih.gov/900001/"
    (prov,) = cited["provenance"]
    assert prov["source_code"] == "supp_ai" and prov["extraction_method"] == "supp_ai_json_v1"
    assert prov["licence_status"] == "to_verify" and "sentence uid 100" in prov["location"]
    assert prov["source_version"] and prov["retrieved_url"]
    assert not {i["rule"] for i in body["validation"]} & {
        "supp_ai_mention_as_confirmed",
        "negated_mention_as_positive",
    }
    assert body["classification"][0]["interaction_class"] == "A"


def test_candidate_supplement_mapping_is_not_used(
    api: TestClient, db_session: Session, imported: None
) -> None:
    db_session.execute(update(ExternalEntity).where(ExternalEntity.source_code == "supp_ai",
                                                    ExternalEntity.external_id == "C0813171")
                       .values(mapping_status="candidate"))  # fmt: skip
    client, provider = _client(
        api, lambda r: answer([("HerbaGuard gives class A for this pair.", ["C1"])])
    )
    ask(client, QUESTION)
    assert (
        not mentions(provider.requests[0])
        and "SUPP.AI" not in provider.requests[0].messages[0].content
    )


def test_unresolved_drug_mapping_is_not_used(
    api: TestClient, db_session: Session, imported: None
) -> None:
    db_session.execute(update(ExternalEntity).where(ExternalEntity.source_code == "supp_ai",
                                                    ExternalEntity.external_id == "C0043031")
                       .values(mapping_status="ambiguous"))  # fmt: skip
    client, provider = _client(
        api, lambda r: answer([("HerbaGuard gives class A for this pair.", ["C1"])])
    )
    ask(client, QUESTION)
    assert not mentions(provider.requests[0])


def test_ambiguous_supplement_is_not_used(api: TestClient, imported: None) -> None:
    """SUPP.AI 'Hawthorn' is ambiguous (two seeded Crataegus species): its mention never appears."""
    client, provider = _client(api, lambda r: answer([]))
    ask(client, "Does hawthorn interact with warfarin?")
    for request in provider.requests:
        assert (
            not mentions(request) and "altered warfarin response" not in request.messages[0].content
        )


def test_mentions_without_paper_metadata_are_excluded_without_implying_no_interaction(
    api: TestClient, imported: None
) -> None:
    client, provider = _client(api, lambda r: answer([]))
    ask(client, "Does St John's wort interact with sertraline?")
    prompt = provider.requests[0].messages[0].content
    assert not mentions(provider.requests[0])
    assert "SUPP.AI holds no eligible machine-extracted mention" in prompt
    assert "1 without paper metadata" in prompt
    assert "This does not show that no interaction exists." in prompt


def test_supp_ai_mentions_never_reach_cloud_models() -> None:
    from herbaguard.ai.context import assemble

    item = mention_item(text="m", study_type="clinical", negation_cue=None, external_id=None, url=None, title=None,
                        location="l", provenance=[], priority=28)  # fmt: skip
    context = assemble([item], max_tokens=5000, max_items=5, redistributable={"supp_ai": False},
                       cloud_only_redistributable=True)  # fmt: skip
    assert context.items == [] and context.excluded_for_licence == 1


# --------------------------------------------------------------------------- validation


def _forced_mention(
    monkeypatch: pytest.MonkeyPatch, *, needle: str, study_type_key: str, cue: str | None = None
) -> None:
    """Supply one SUPP.AI item for the request instead of reading SUPP.AI from the database.

    Only the pair's highest-ranked eligible mention reaches a context now, so the validator is
    exercised here with a non-clinical or negated mention supplied directly; the ingested fixture
    data (study types, negation labels, provenance) is covered by the label test above.
    """
    pmid = needle.split()[1]

    def build(*args: Any, **kwargs: Any) -> list[ContextItem]:
        return [
            mention_item(
                text=f'SUPP.AI machine-extracted mention: "Synthetic sentence." Paper: Synthetic study; '
                f"PMID {pmid}.",
                study_type=study_type_key, negation_cue=cue, external_id=f"PMID:{pmid}",
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", title="Synthetic study", location="l",
                provenance=[], priority=service.MENTION_PRIORITY,
            )
        ]  # fmt: skip

    monkeypatch.setattr(service, "_supplementary_mentions", build)


@pytest.mark.parametrize(("needle", "text", "rule", "study_type_key", "cue"), [
    ("PMID 900001", "St John's wort interacts with warfarin; this is a confirmed interaction.",
     "supp_ai_mention_as_confirmed", "clinical", None),
    ("PMID 900001", "It is established that St John's wort reduces the effect of warfarin.",
     "supp_ai_mention_as_confirmed", "clinical", None),
    ("PMID 900003", "This interaction is clinically significant in patients.", "supp_ai_mention_as_confirmed",
     "animal", None),
    ("PMID 900004", "St John's wort alters warfarin pharmacokinetics.", "negated_mention_as_positive",
     "unknown", "did not"),
])  # fmt: skip
def test_unsupported_claims_from_mentions_are_rejected(
    api: TestClient, imported: None, monkeypatch: pytest.MonkeyPatch, needle: str, text: str, rule: str,
    study_type_key: str, cue: str | None,
) -> None:  # fmt: skip
    _forced_mention(monkeypatch, needle=needle, study_type_key=study_type_key, cue=cue)
    client, _ = _client(api, lambda r: answer([(text, [find(r, needle)])]))
    body = ask(client, QUESTION)
    assert rule in {i["rule"] for i in body["validation"]}
    assert all(text not in p["text"] for p in body["paragraphs"])


def test_negated_mention_reported_as_negative_is_accepted(
    api: TestClient, imported: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    text = "One machine-extracted SUPP.AI mention, from a paper without a stated study type, says St John's wort did not alter warfarin pharmacokinetics."
    _forced_mention(monkeypatch, needle="PMID 900004", study_type_key="unknown", cue="did not")
    client, _ = _client(api, lambda r: answer([(text, [find(r, "PMID 900004")])]))
    body = ask(client, QUESTION)
    assert not {i["rule"] for i in body["validation"]} & {
        "supp_ai_mention_as_confirmed",
        "negated_mention_as_positive",
    }
    assert any("did not alter" in p["text"] for p in body["paragraphs"])


def _mention(cue: str | None = None) -> ContextItem:
    return mention_item(text="m", study_type="clinical", negation_cue=cue, external_id=None, url=None, title=None,
                        location="l", provenance=[], priority=28)  # fmt: skip


@pytest.mark.parametrize(("text", "rule"), [
    ("St John's wort interacts with warfarin.", "supp_ai_mention_as_confirmed"),
    ("SUPP.AI confirms the interaction.", "supp_ai_mention_as_confirmed"),
    ("The interaction is proven.", "supp_ai_mention_as_confirmed"),
    ("St John's wort may interact with warfarin, according to one machine-extracted mention.", None),
    ("A mention reports that St John's wort interacts with warfarin; this is not confirmed.", None),
    ("This is not a confirmed interaction.", None),
])  # fmt: skip
def test_mention_rule(text: str, rule: str | None) -> None:
    issue = mention_issue(text, [_mention()])
    assert (issue[0] if issue else None) == rule


def test_mention_rule_ignores_paragraphs_with_other_evidence() -> None:
    statement = ContextItem(label="S1", kind="statement", role="direct_evidence", text="t")
    assert mention_issue("St John's wort interacts with warfarin.", [_mention(), statement]) is None
    assert (
        mention_issue("It increases levels.", [_mention("not")])[0] == "negated_mention_as_positive"
    )  # type: ignore[index]
    assert mention_issue("It did not increase levels.", [_mention("not")]) is None
    assert mention_issue("It increases levels.", [_mention("not"), _mention()]) is None


@pytest.mark.parametrize(("paper", "expected"), [
    ({"clinical_study": True, "human_study": True, "animal_study": False}, "clinical"),
    ({"clinical_study": True, "human_study": False, "animal_study": True}, "conflicting"),  # dog study, real data
    ({"clinical_study": True, "human_study": False, "animal_study": False}, "conflicting"),
    ({"clinical_study": False, "human_study": True, "animal_study": False}, "human"),
    ({"clinical_study": False, "human_study": True, "animal_study": True}, "animal_and_human"),
    ({"clinical_study": False, "human_study": False, "animal_study": True}, "animal"),
    ({"clinical_study": False, "human_study": False, "animal_study": False}, "unknown"),
    ({}, "unknown"),
    (None, "unknown"),
])  # fmt: skip
def test_study_type_from_paper_flags(paper: dict[str, bool] | None, expected: str) -> None:
    assert study_type(paper) == expected


# --------------------------------------------------------------------------- separation


def test_supp_ai_ddid_and_livertox_stay_separate_and_the_class_is_unchanged(
    api: TestClient, db_session: Session, imported: None, tmp_path: Path
) -> None:
    def snapshot() -> list[Any]:
        return sorted(db_session.execute(select(
            InteractionAssertion.id, InteractionAssertion.statement_type, InteractionAssertion.evidence_type,
            InteractionAssertion.status)).all())  # fmt: skip

    before = snapshot()
    db_session.add(Target(id=uuid.uuid4(), symbol="CYP2C9", name="Cytochrome P450 2C9", target_type="enzyme",
                          uniprot_accession="P11712"))  # fmt: skip
    db_session.flush()
    _import(db_session, "ddid", ddid.run, FIXTURES / "ddid")
    shutil.copytree(FIXTURES / "livertox", tmp_path / "livertox")
    write_master_list(tmp_path / "livertox")
    _import(db_session, "livertox", livertox.run, tmp_path / "livertox")

    def reply(request: GenerationRequest) -> str:
        labels = re.findall(r'id="([XHU]\d+)"', request.messages[0].content)
        return answer([("HerbaGuard gives class A for this pair.", ["C1"]),
                       ("Separately, a DDID record, LiverTox and a SUPP.AI machine-extracted mention are "
                        "listed as context.", labels)])  # fmt: skip

    client, provider = _client(api, reply)
    body = ask(client, "Can St John's wort with warfarin harm the liver?")
    prompt = provider.requests[0].messages[0].content
    assert re.search(r'id="X\d+" role="experimental_evidence" source="ddid"', prompt)
    assert re.search(r'id="H\d+" role="hepatotoxicity_evidence" source="livertox"', prompt)
    assert re.search(r'id="U\d+" role="supplementary_mention" source="supp_ai"', prompt)
    by_kind = {"observation": "ddid", "hepatotoxicity": "livertox", "mention": "supp_ai"}
    seen = set()
    for citation in body["citations"]:
        if citation["kind"] in by_kind:
            seen.add(citation["kind"])
            assert citation["source_code"] == by_kind[citation["kind"]]
            assert {p["source_code"] for p in citation["provenance"]} == {by_kind[citation["kind"]]}
    assert seen == set(by_kind)
    assert body["classification"][0]["interaction_class"] == "A"
    assert snapshot() == before
