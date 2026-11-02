"""Schema v1 against a real PostgreSQL + pgvector database (marker ``db``).

These tests check that integrity rules from docs/architecture/data-model.md are enforced by
the database itself, not only by application code.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from herbaguard.models import (
    Chunk,
    Constituent,
    Drug,
    DrugClass,
    DrugTargetRoleLink,
    EvidenceItem,
    HerbalSubstance,
    InteractionAssertion,
    Source,
    SourceRecord,
    Target,
    TargetModulation,
    Taxon,
    TaxonName,
)
from herbaguard.models.evidence import EMBEDDING_DIMENSION

pytestmark = pytest.mark.db


def _source(session: Session, code: str = "test_source") -> Source:
    source = Source(code=code, name="Test source", provider="Tests", access_method="api")
    session.add(source)
    session.flush()
    return source


def _st_johns_wort(session: Session) -> HerbalSubstance:
    taxon = Taxon(wfo_id="wfo-0000728093", scientific_name="Hypericum perforatum", authorship="L.")
    session.add(taxon)
    session.flush()
    substance = HerbalSubstance(
        taxon_id=taxon.id, plant_part="herba", pharmaceutical_name="Hyperici herba"
    )
    session.add(substance)
    session.flush()
    return substance


def test_all_tables_created(migrated_engine: Engine) -> None:
    tables = set(inspect(migrated_engine).get_table_names())
    expected = {
        "source", "ingestion_run", "source_record", "provenance", "data_quality_issue",
        "taxon", "taxon_name", "herbal_substance", "drug", "drug_class",
        "drug_class_membership", "constituent", "herbal_substance_constituent", "target",
        "target_modulation", "drug_target_role", "indication", "interaction_assertion",
        "evidence_item", "interaction_assertion_evidence", "chunk",
    }  # fmt: skip
    assert expected <= tables


def test_vector_extension_installed(db_session: Session) -> None:
    installed = db_session.execute(
        text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
    ).scalar_one_or_none()
    assert installed == "vector"


def test_wfo_id_format_is_enforced(db_session: Session) -> None:
    db_session.add(Taxon(wfo_id="728093", scientific_name="Hypericum perforatum"))
    with pytest.raises(IntegrityError, match="ck_taxon_wfo_id_format"):
        db_session.flush()


def test_inchikey_format_is_enforced(db_session: Session) -> None:
    db_session.add(Constituent(inchikey="not-an-inchikey", name="hyperforin"))
    with pytest.raises(IntegrityError, match="ck_constituent_inchikey_format"):
        db_session.flush()


def test_interaction_assertion_needs_exactly_one_object(db_session: Session) -> None:
    source = _source(db_session)
    substance = _st_johns_wort(db_session)
    drug = Drug(rxcui="11289", name="warfarin")
    drug_class = DrugClass(code="B01AA", name="Vitamin K antagonists", level=4)
    db_session.add_all([drug, drug_class])
    db_session.flush()

    db_session.add(
        InteractionAssertion(
            herbal_substance_id=substance.id,
            drug_id=drug.id,
            drug_class_code="B01AA",
            object_label_verbatim="coumarin-type anticoagulants",
            source_code=source.code,
            evidence_type="REG",
        )
    )
    with pytest.raises(IntegrityError, match="exactly_one_object"):
        db_session.flush()


def test_valid_class_level_interaction_assertion(db_session: Session) -> None:
    source = _source(db_session)
    substance = _st_johns_wort(db_session)
    db_session.add(DrugClass(code="B01AA", name="Vitamin K antagonists", level=4))
    db_session.flush()
    assertion = InteractionAssertion(
        herbal_substance_id=substance.id,
        drug_class_code="B01AA",
        object_label_verbatim="coumarin-type anticoagulants",
        source_code=source.code,
        evidence_type="REG",
        source_section="4.5",
        use_category="well_established_use",
        severity_wording="contraindicated",
    )
    db_session.add(assertion)
    db_session.flush()
    assert assertion.status == "active"


def test_unknown_evidence_type_is_rejected(db_session: Session) -> None:
    source = _source(db_session)
    db_session.add(
        EvidenceItem(source_code=source.code, external_id="x", evidence_type="BLOG", title="t")
    )
    with pytest.raises(IntegrityError, match="evidence_type_valid"):
        db_session.flush()


def test_taxon_name_uniqueness_treats_null_language_as_equal(db_session: Session) -> None:
    source = _source(db_session)
    for _ in range(2):
        db_session.add(
            TaxonName(
                name="Ginseng",
                normalized_name="ginseng",
                name_type="common",
                language=None,
                taxon_id=None,
                source_code=source.code,
            )
        )
    with pytest.raises(IntegrityError, match="uq_taxon_name_normalized_name"):
        db_session.flush()


def test_source_record_is_idempotent_on_content_hash(db_session: Session) -> None:
    source = _source(db_session)
    record = {
        "source_code": source.code,
        "native_id": "Hypericum perforatum",
        "url": "https://example.org",
        "content_sha256": "a" * 64,
        "retrieved_at": datetime.now(UTC),
    }
    db_session.add(SourceRecord(**record))
    db_session.flush()
    db_session.add(SourceRecord(**record))
    with pytest.raises(IntegrityError, match="uq_source_record_source_code"):
        db_session.flush()


def test_chunk_full_text_and_vector_search(db_session: Session) -> None:
    source = _source(db_session)
    item = EvidenceItem(
        source_code=source.code,
        external_id=f"EMA/HMPC/7695/2021#4.5-{uuid.uuid4()}",
        evidence_type="REG",
        title="EU herbal monograph on Hypericum perforatum L., herba — section 4.5",
    )
    db_session.add(item)
    db_session.flush()
    near = [1.0] + [0.0] * (EMBEDDING_DIMENSION - 1)
    far = [0.0, 1.0] + [0.0] * (EMBEDDING_DIMENSION - 2)
    texts = [
        ("Hyperici herba preparations induce CYP3A4.", near),
        ("Unrelated text about storage conditions.", far),
    ]
    db_session.add_all(
        Chunk(evidence_item_id=item.id, ordinal=i, text=body, embedding=vector)
        for i, (body, vector) in enumerate(texts)
    )
    db_session.flush()

    keyword_hit = db_session.scalars(
        select(Chunk.ordinal).where(
            Chunk.search_vector.op("@@")(text("plainto_tsquery('english', 'induces cyp3a4')"))
        )
    ).all()
    assert keyword_hit == [0]

    nearest = db_session.scalars(
        select(Chunk.ordinal).order_by(Chunk.embedding.cosine_distance(near)).limit(1)  # type: ignore[union-attr]
    ).one()
    assert nearest == 0


def test_migration_downgrade_and_upgrade_round_trip(
    migrated_engine: Engine, alembic_config: Config
) -> None:
    command.downgrade(alembic_config, "base")
    assert "taxon" not in inspect(migrated_engine).get_table_names()
    command.upgrade(alembic_config, "head")
    assert "taxon" in inspect(migrated_engine).get_table_names()


# --------------------------------------------------------------------------- Phase 4 (migration 0003)


def _target_and_drug(session: Session) -> tuple[Source, Target, Drug]:
    source = _source(session)
    target = Target(symbol="CYP3A", name="Cytochrome P450 3A", target_type="enzyme")
    drug = Drug(rxcui="6960", name="midazolam")
    session.add_all([target, drug])
    session.flush()
    return source, target, drug


def test_drug_role_accepts_moderately_sensitive_and_rejects_unknown_potency(
    db_session: Session,
) -> None:
    source, target, drug = _target_and_drug(db_session)
    db_session.add(DrugTargetRoleLink(drug_id=drug.id, target_id=target.id, role="moderately_sensitive_substrate",
                                      source_code=source.code))  # fmt: skip
    db_session.flush()
    db_session.add(DrugTargetRoleLink(drug_id=drug.id, target_id=target.id, role="inhibitor",
                                      potency="very strong", source_code=source.code))  # fmt: skip
    with pytest.raises(IntegrityError, match="ck_drug_target_role_potency_valid"):
        db_session.flush()


def test_same_effect_from_two_evidence_items_is_kept_twice(db_session: Session) -> None:
    source, target, _ = _target_and_drug(db_session)
    substance = _st_johns_wort(db_session)
    items = [
        EvidenceItem(
            source_code=source.code, external_id=f"doc#{use}", evidence_type="REG", title=use
        )
        for use in ("WEU", "TU")
    ]
    db_session.add_all(items)
    db_session.flush()
    for item in items:
        db_session.add(TargetModulation(herbal_substance_id=substance.id, target_id=target.id, effect="induces",
                                        evidence_type="REG", source_code=source.code, evidence_item_id=item.id))  # fmt: skip
    db_session.flush()
    db_session.add(TargetModulation(herbal_substance_id=substance.id, target_id=target.id, effect="induces",
                                    evidence_type="REG", source_code=source.code, evidence_item_id=items[0].id))  # fmt: skip
    with pytest.raises(IntegrityError, match="uq_target_modulation_herbal_substance_id"):
        db_session.flush()
