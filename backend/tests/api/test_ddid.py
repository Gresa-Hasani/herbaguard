"""DDID ingestion and its use in the AI layer, on the seeded test database.

Fixture CSVs in tests/fixtures/ddid/ use the exact headers of the real DDID files (copied from the
downloaded files) with synthetic rows modelled on real patterns: human, rat and unstated species;
an exact duplicate row; a food row; ids missing from the herb/drug files; TTD targets; duplicate NP
rows. The real files are never read by the tests.
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
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from herbaguard.ai.context import assemble
from herbaguard.ai.providers.base import GenerationRequest
from herbaguard.ai.providers.mock import ScriptedProvider
from herbaguard.ai.providers.registry import GenerationChain
from herbaguard.api.routes.ai import get_embedding_provider, get_generation_chain
from herbaguard.core.config import LLMProviderName, Settings
from herbaguard.ingestion.context import run_ingestion
from herbaguard.ingestion.loaders import ensure_sources
from herbaguard.ingestion.pipelines import ddid
from herbaguard.models import (
    DataQualityIssue,
    EvidenceItem,
    ExperimentalObservation,
    ExternalEntity,
    ExternalRelation,
    Target,
)

pytestmark = pytest.mark.db
FIXTURES = Path(__file__).parents[1] / "fixtures" / "ddid"


def run_import(session: Session, directory: Path = FIXTURES) -> dict[str, int]:
    ensure_sources(session)
    with run_ingestion(session, "ddid", Settings(_env_file=None)) as ctx:  # type: ignore[call-arg]
        ddid.run(ctx, directory)
        return dict(ctx.stats)


@pytest.fixture
def imported(db_session: Session, seeded: dict[str, object]) -> dict[str, int]:
    db_session.add(Target(id=uuid.uuid4(), symbol="CYP2C9", name="Cytochrome P450 2C9", target_type="enzyme",
                          uniprot_accession="P11712"))  # fmt: skip
    db_session.flush()
    return run_import(db_session)


def entity(session: Session, kind: str, external_id: str) -> ExternalEntity:
    return session.scalars(select(ExternalEntity).where(ExternalEntity.kind == kind,
                                                        ExternalEntity.external_id == external_id)).one()  # fmt: skip


def observations(session: Session) -> list[ExperimentalObservation]:
    return list(
        session.scalars(
            select(ExperimentalObservation).order_by(ExperimentalObservation.source_row_numbers)
        )
    )


def test_counts_duplicates_and_rejections(db_session: Session, imported: dict[str, int]) -> None:
    assert (
        imported["interaction_rows"] == 7 and imported["interaction_rows_rejected"] == 1
    )  # Drug_ID NA
    assert imported["interaction_exact_duplicates"] == 1
    assert imported["observations_stored"] == 5
    dup = next(o for o in observations(db_session) if o.species == "Rat")
    assert dup.source_row_numbers == [3, 4]  # one record, both CSV lines kept
    assert imported["np_rows"] == 3 and imported["np_duplicate_rows"] == 1
    assert db_session.scalar(select(func.count()).select_from(ExternalRelation)
                             .where(ExternalRelation.predicate == "contains_natural_product")) == 2  # fmt: skip
    issue_rules = set(db_session.scalars(select(DataQualityIssue.rule)))
    assert "ddid_row_without_id" in issue_rules


def test_original_values_are_kept_and_derivations_are_separate(
    db_session: Session, imported: dict[str, int]
) -> None:
    by_species = {o.species: o for o in observations(db_session) if o.interactant_kind == "herb"}
    human, rat, unknown = by_species["Homo Sapiens"], by_species["Rat"], by_species[None]
    assert (human.derived_study_context, human.derived_evidence_type) == ("human", "CLIN")
    assert (rat.derived_study_context, rat.derived_evidence_type) == ("animal", "ANIMAL")
    assert (unknown.derived_study_context, unknown.derived_evidence_type) == (
        "unknown",
        "OTHER",
    )  # never human
    assert unknown.original["Experimental_Species"] == "NA"  # source value untouched
    assert (
        human.effect_label == "Negative" and rat.effect_label == "Possible"
    )  # DDID labels verbatim
    assert human.original["Result"] == "AUC of S-warfarin decreased"
    assert human.derivation_rule == "ddid_species_v1"
    dog = next(o for o in observations(db_session) if o.species == "Dog")
    assert dog.derived_study_context == "animal"


def test_entity_mapping_is_explicit_and_unresolved_is_kept(
    db_session: Session, imported: dict[str, int]
) -> None:
    sjw = entity(db_session, "herb", "H00100")
    assert (sjw.mapping_status, sjw.mapped_table, sjw.mapping_method) == (
        "resolved",
        "taxon",
        "exact_accepted_name",
    )
    assert "plant part" in (sjw.mapping_note or "") and sjw.identifiers["ncbi_taxonomy"] == "65561"
    assert entity(db_session, "herb", "H00200").mapping_status == "unresolved"
    assert entity(db_session, "herb", "H00300").mapping_note == "No Latin name in DDID."
    assert entity(db_session, "herb", "H05555").mapping_note.startswith(
        "Referenced only by the interaction file"
    )  # type: ignore[union-attr]
    assert entity(db_session, "herb", "H09999").mapping_note == "Referenced only by the NP file."
    assert entity(db_session, "food", "F00001").mapping_status == "not_applicable"
    warfarin = entity(db_session, "drug", "D00001")
    assert (warfarin.mapping_status, warfarin.mapping_method) == ("resolved", "exact_name")
    assert warfarin.identifiers["drugbank"] == "DB00682"
    sertraline = entity(db_session, "drug", "D00002")
    assert (sertraline.mapping_status, sertraline.mapping_method) == ("resolved", "exact_synonym")
    assert entity(db_session, "drug", "D00003").mapping_status == "unresolved"
    assert entity(db_session, "natural_product", "NPC1").mapping_status == "unresolved"


def test_targets_only_join_within_the_uniprot_namespace(
    db_session: Session, imported: dict[str, int]
) -> None:
    human = next(o for o in observations(db_session) if o.species == "Homo Sapiens")
    cyp2c9 = db_session.scalars(select(Target).where(Target.symbol == "CYP2C9")).one()
    assert human.target_accessions == ["P11712"] and human.mapped_target_ids == [str(cyp2c9.id)]
    ttd = entity(db_session, "ttd_target", "T27812")
    assert (
        ttd.mapping_status == "unresolved"
        and ttd.mapped_id is None
        and "not joined" in (ttd.mapping_note or "")
    )
    relation = db_session.scalars(
        select(ExternalRelation).where(ExternalRelation.predicate == "has_therapeutic_target")
    ).one()
    assert relation.source_row_numbers == [2, 3]


def test_reimport_is_idempotent(db_session: Session, imported: dict[str, int]) -> None:
    before = (
        len(observations(db_session)),
        db_session.scalar(select(func.count()).select_from(ExternalEntity)),
    )
    second = run_import(db_session)
    assert second.get("source_records_new", 0) == 0
    after = (
        len(observations(db_session)),
        db_session.scalar(select(func.count()).select_from(ExternalEntity)),
    )
    assert before == after
    dup = next(o for o in observations(db_session) if o.species == "Rat")
    assert dup.source_row_numbers == [3, 4]  # not appended twice


def test_changed_file_removes_stale_records(
    db_session: Session, imported: dict[str, int], tmp_path: Path
) -> None:
    copy = tmp_path / "ddid"
    shutil.copytree(FIXTURES, copy)
    lines = (
        (copy / "Interaction Information.csv").read_text(encoding="utf-8").splitlines(keepends=True)
    )
    (copy / "Interaction Information.csv").write_text(
        "".join(lines[:2]), encoding="utf-8"
    )  # header + 1 row
    stats = run_import(db_session, copy)
    assert stats["observations_stale_removed"] == 4 and len(observations(db_session)) == 1


def test_evidence_reuses_existing_pmid_and_types_from_species(
    db_session: Session, imported: dict[str, int]
) -> None:
    rat = next(o for o in observations(db_session) if o.species == "Rat")
    item = db_session.get(EvidenceItem, rat.evidence_item_id)
    assert item is not None and item.source_code == "ddid" and item.evidence_type == "ANIMAL"
    assert item.url == "https://pubmed.ncbi.nlm.nih.gov/20000001/"
    unknown = next(
        o for o in observations(db_session) if o.species is None and o.interactant_kind == "herb"
    )
    assert db_session.get(EvidenceItem, unknown.evidence_item_id).evidence_type == "OTHER"  # type: ignore[union-attr]


# --------------------------------------------------------------------------- separation from A–E and AI use


def test_classification_is_unchanged_by_ddid(
    check: Callable[..., dict[str, Any]], db_session: Session
) -> None:
    before = check("St John's wort", ["warfarin", "sertraline"])["results"]
    run_import(db_session)
    after = check("St John's wort", ["warfarin", "sertraline"])["results"]
    assert [r["classification"] for r in before] == [r["classification"] for r in after]


def _client(
    api: TestClient, reply: Callable[[GenerationRequest], str]
) -> tuple[TestClient, ScriptedProvider]:
    provider = ScriptedProvider(reply, name="ollama", model="qwen3:4b")
    chain = GenerationChain((LLMProviderName.OLLAMA,), (provider,))
    api.app.dependency_overrides[get_generation_chain] = lambda: chain  # type: ignore[attr-defined]
    api.app.dependency_overrides[get_embedding_provider] = lambda: None  # type: ignore[attr-defined]
    return api, provider


def answer(paragraphs: list[tuple[str, list[str]]]) -> str:
    return json.dumps({"paragraphs": [{"text": t, "citations": c} for t, c in paragraphs],
                       "limitations": [], "insufficient_evidence": False})  # fmt: skip


def test_ai_receives_labelled_experimental_records(
    api: TestClient, imported: dict[str, int]
) -> None:
    def reply(request: GenerationRequest) -> str:
        ids = re.findall(r'id="(X\d+)"', request.messages[0].content)
        return answer([("HerbaGuard gives class A for this pair.", ["C1"]),
                       ("A rat study in DDID reported increased clearance; animal data are not human evidence.", ids[:1])])  # fmt: skip

    client, provider = _client(api, reply)
    body = client.post("/api/v1/ai/ask", json={"question": "Does St John's wort interact with warfarin?",
                                               "allow_remote_drug_lookup": False}).json()  # fmt: skip
    prompt = provider.requests[0].messages[0].content
    assert 'role="experimental_evidence"' in prompt
    assert "NOT human clinical evidence" in prompt and "not a HerbaGuard A-E class" in prompt
    assert "Rule 3a" in provider.requests[0].system or "3a." in provider.requests[0].system
    observation = next(c for c in body["citations"] if c["kind"] == "observation")
    assert (
        observation["role"] == "experimental_evidence"
        and observation["provenance"][0]["source_code"] == "ddid"
    )
    assert body["classification"][0]["interaction_class"] == "A"  # unchanged by DDID


def test_animal_records_presented_as_clinical_are_removed(
    api: TestClient, imported: dict[str, int]
) -> None:
    def reply(request: GenerationRequest) -> str:
        content = request.messages[0].content
        rat = re.search(r'<evidence id="(X\d+)"[^>]*>\nDDID record: [^\n]*Species: Rat', content)
        assert rat is not None
        return answer([("HerbaGuard gives class A.", ["C1"]),
                       ("This is a clinically significant interaction in patients.", [rat.group(1)])])  # fmt: skip

    client, _ = _client(api, reply)
    body = client.post("/api/v1/ai/ask", json={"question": "Does St John's wort interact with warfarin?",
                                               "allow_remote_drug_lookup": False}).json()  # fmt: skip
    assert "experimental_as_clinical" in {i["rule"] for i in body["validation"]}
    assert all("clinically significant" not in p["text"] for p in body["paragraphs"])


def test_ddid_records_never_reach_cloud_models(
    db_session: Session, imported: dict[str, int]
) -> None:
    from herbaguard.ai.context import observation_item

    item = observation_item(text="DDID record", study_context="animal", effect_label="Possible", evidence_item_id=None,
                            external_id=None, url=None, title=None, location="row 2", provenance=[],
                            plant_part_note=None, priority=24)  # fmt: skip
    context = assemble([item], max_tokens=5000, max_items=5, redistributable={"ddid": False},
                       cloud_only_redistributable=True)  # fmt: skip
    assert context.items == [] and context.excluded_for_licence == 1


def test_synonym_only_match_is_a_candidate_not_used_by_the_ai(db_session: Session, seeded: dict[str, object],
                                                             tmp_path: Path) -> None:  # fmt: skip
    """'Cimicifuga racemosa' is listed only as a synonym (seed: wcvp_ethcstwin) → candidate for review."""
    copy = tmp_path / "ddid"
    shutil.copytree(FIXTURES, copy)
    herb_file = copy / "Herb Information.csv"
    herb_file.write_text(herb_file.read_text(encoding="utf-8").replace("Unobtainium officinale", "Cimicifuga racemosa"),
                         encoding="utf-8")  # fmt: skip
    run_import(db_session, copy)
    candidate = entity(db_session, "herb", "H00200")
    assert (candidate.mapping_status, candidate.mapping_method) == (
        "candidate",
        "exact_synonym_needs_review",
    )
    assert candidate.mapped_id is not None and "needs review" in (candidate.mapping_note or "")
