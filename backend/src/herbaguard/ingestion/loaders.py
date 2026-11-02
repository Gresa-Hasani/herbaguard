"""Idempotent upserts for canonical entities. Natural keys or deterministic IDs only."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import CursorResult, inspect, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapper, Session

from herbaguard.ingestion.context import stable_id
from herbaguard.ingestion.normalize.names import normalize_for_lookup
from herbaguard.ingestion.sources import SOURCES
from herbaguard.models import (
    Chunk,
    Drug,
    DrugClass,
    DrugClassMembership,
    EvidenceItem,
    HerbalSubstance,
    HerbalSubstanceEvidence,
    Indication,
    InteractionAssertion,
    InteractionAssertionEvidence,
    Source,
    Taxon,
    TaxonName,
)


def _set_clause(model: type, values: dict[str, Any]) -> dict[str, Any]:
    """ON CONFLICT ... SET needs column names, not ORM attribute names (e.g. ``metadata_`` →
    ``metadata``)."""
    mapper: Mapper[Any] = inspect(model)
    return {mapper.attrs[key].columns[0].name: value for key, value in values.items()}


def ensure_sources(session: Session) -> int:
    """Insert or update every registered source (licence info lives in sources.py)."""
    for definition in SOURCES:
        values = {
            "code": definition.code,
            "name": definition.name,
            "provider": definition.provider,
            "homepage_url": definition.homepage_url,
            "access_method": definition.access_method,
            "is_official": definition.is_official,
            "licence": definition.licence,
            "licence_status": definition.licence_status.value,
            "redistributable": definition.redistributable,
            "notes": f"priority {definition.priority}",
        }
        stmt = insert(Source).values(**values)
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=["code"], set_={k: v for k, v in values.items() if k != "code"}
            )
        )
    session.flush()
    return len(SOURCES)


def upsert_taxon(session: Session, **values: Any) -> uuid.UUID:
    base = insert(Taxon).values(id=stable_id("taxon", values["wfo_id"]), **values)
    stmt = base.on_conflict_do_update(
        index_elements=["wfo_id"], set_={k: v for k, v in values.items() if k != "wfo_id"}
    ).returning(Taxon.id)
    return session.execute(stmt).scalar_one()


def add_taxon_name(
    session: Session,
    *,
    taxon_id: uuid.UUID | None,
    name: str,
    name_type: str,
    source_code: str,
    language: str | None = None,
    source_native_id: str | None = None,
) -> uuid.UUID | None:
    stmt = (
        insert(TaxonName)
        .values(
            id=uuid.uuid4(),
            taxon_id=taxon_id,
            name=name,
            normalized_name=normalize_for_lookup(name),
            name_type=name_type,
            language=language,
            source_code=source_code,
            source_native_id=source_native_id,
        )
        .on_conflict_do_nothing(constraint="uq_taxon_name_normalized_name")
        .returning(TaxonName.id)
    )
    return session.execute(stmt).scalar_one_or_none()


def upsert_substance(
    session: Session, *, taxon_id: uuid.UUID, plant_part: str, **values: Any
) -> uuid.UUID:
    base = insert(HerbalSubstance).values(
        id=stable_id("herbal_substance", taxon_id, plant_part),
        taxon_id=taxon_id,
        plant_part=plant_part,
        **values,
    )
    stmt = base.on_conflict_do_update(
        index_elements=["taxon_id", "plant_part"], set_=_set_clause(HerbalSubstance, values)
    ).returning(HerbalSubstance.id)
    return session.execute(stmt).scalar_one()


def substances_for_herb(session: Session, herb_key: str) -> list[HerbalSubstance]:
    """Substances created for a curated herb (linked via the curated common name)."""
    from herbaguard.ingestion.curation import load_herbs

    herb = load_herbs().get(herb_key)
    return list(
        session.scalars(
            select(HerbalSubstance).where(
                HerbalSubstance.pharmaceutical_name == herb.ema_latin_name,
                HerbalSubstance.in_curated_scope.is_(True),
            )
        )
    )


def upsert_drug(session: Session, *, rxcui: str, name: str, tty: str) -> uuid.UUID:
    base = insert(Drug).values(id=stable_id("drug", rxcui), rxcui=rxcui, name=name, rxnorm_tty=tty)
    stmt = base.on_conflict_do_update(
        index_elements=["rxcui"], set_={"name": name, "rxnorm_tty": tty}
    ).returning(Drug.id)
    return session.execute(stmt).scalar_one()


def upsert_drug_class(session: Session, *, code: str, name: str) -> None:
    level = {1: 1, 3: 2, 4: 3, 5: 4, 7: 5}[len(code)]
    stmt = insert(DrugClass).values(code=code, system="ATC", name=name, level=level)
    session.execute(
        stmt.on_conflict_do_update(index_elements=["code"], set_={"name": name, "level": level})
    )


def add_class_membership(
    session: Session, *, drug_id: uuid.UUID, code: str, source_code: str
) -> None:
    stmt = insert(DrugClassMembership).values(
        drug_id=drug_id, drug_class_code=code, source_code=source_code
    )
    session.execute(stmt.on_conflict_do_nothing())


def upsert_evidence(
    session: Session, *, source_code: str, external_id: str, **values: Any
) -> uuid.UUID:
    base = insert(EvidenceItem).values(
        id=stable_id("evidence_item", source_code, external_id),
        source_code=source_code,
        external_id=external_id,
        **values,
    )
    stmt = base.on_conflict_do_update(
        index_elements=["source_code", "external_id"], set_=_set_clause(EvidenceItem, values)
    ).returning(EvidenceItem.id)
    return session.execute(stmt).scalar_one()


def replace_chunks(
    session: Session,
    evidence_item_id: uuid.UUID,
    texts: Iterable[tuple[str | None, str, dict[str, Any]]],
) -> int:
    """Replace an evidence item's chunks (section, text, metadata). Embeddings come in Phase 5."""
    session.query(Chunk).filter(Chunk.evidence_item_id == evidence_item_id).delete()
    count = 0
    for ordinal, (section, text, metadata) in enumerate(texts):
        if not text.strip():
            continue
        session.add(
            Chunk(
                id=stable_id("chunk", evidence_item_id, ordinal),
                evidence_item_id=evidence_item_id,
                ordinal=ordinal,
                section=section,
                text=text,
                metadata_=metadata,
            )
        )
        count += 1
    session.flush()
    return count


def link_substance_evidence(
    session: Session, substance_ids: Iterable[uuid.UUID], evidence_item_id: uuid.UUID, relation: str
) -> None:
    for substance_id in substance_ids:
        stmt = insert(HerbalSubstanceEvidence).values(
            herbal_substance_id=substance_id, evidence_item_id=evidence_item_id, relation=relation
        )
        session.execute(stmt.on_conflict_do_nothing())


def upsert_indication(session: Session, **values: Any) -> uuid.UUID:
    indication_id = stable_id(
        "indication",
        values["herbal_substance_id"],
        values["evidence_item_id"],
        values["use_category"],
        values["text"],
    )
    stmt = insert(Indication).values(id=indication_id, **values)
    session.execute(stmt.on_conflict_do_nothing())
    return indication_id


def upsert_assertion(
    session: Session, *, evidence_item_id: uuid.UUID, key_text: str, **values: Any
) -> uuid.UUID:
    """One row per (substance, object, source, use category, sentence). Re-runs update in place."""
    assertion_id = stable_id(
        "interaction_assertion",
        values["herbal_substance_id"],
        values.get("drug_id") or values.get("drug_class_code"),
        values["source_code"],
        values.get("use_category"),
        values.get("source_section"),
        key_text,
    )
    stmt = insert(InteractionAssertion).values(id=assertion_id, **values)
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=["id"], set_=_set_clause(InteractionAssertion, values)
        )
    )
    link = insert(InteractionAssertionEvidence).values(
        interaction_assertion_id=assertion_id, evidence_item_id=evidence_item_id
    )
    session.execute(link.on_conflict_do_nothing())
    return assertion_id


def supersede_missing_assertions(
    session: Session,
    *,
    source_code: str,
    substance_ids: Iterable[uuid.UUID],
    kept_ids: set[uuid.UUID],
) -> int:
    """Mark active assertions of this source for these substances that the current run did not
    produce as ``superseded`` (kept for lineage, never deleted). Returns the number changed."""
    from sqlalchemy import update

    ids = list(substance_ids)
    if not ids:
        return 0
    conditions = [
        InteractionAssertion.source_code == source_code,
        InteractionAssertion.herbal_substance_id.in_(ids),
        InteractionAssertion.status == "active",
    ]
    if kept_ids:
        conditions.append(InteractionAssertion.id.not_in(kept_ids))
    stmt = update(InteractionAssertion).where(*conditions).values(status="superseded")
    result: CursorResult[Any] = session.execute(stmt)  # type: ignore[assignment]
    return result.rowcount or 0
