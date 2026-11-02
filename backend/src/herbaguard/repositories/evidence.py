"""Evidence items, chunks, substance links and provenance."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from herbaguard.models import (
    Chunk,
    EvidenceItem,
    HerbalSubstanceEvidence,
    Provenance,
    Source,
    SourceRecord,
)


@dataclass(frozen=True, slots=True)
class EvidenceFilters:
    substance_ids: list[uuid.UUID] | None = None
    source_code: str | None = None
    evidence_types: list[str] | None = None
    relation: str | None = None
    year_from: int | None = None
    year_to: int | None = None
    query: str | None = None


def list_evidence(
    session: Session, filters: EvidenceFilters, *, limit: int, offset: int
) -> tuple[list[EvidenceItem], int]:
    stmt = select(EvidenceItem)
    if filters.substance_ids is not None or filters.relation:
        link = select(HerbalSubstanceEvidence.evidence_item_id)
        if filters.substance_ids is not None:
            link = link.where(
                HerbalSubstanceEvidence.herbal_substance_id.in_(filters.substance_ids)
            )
        if filters.relation:
            link = link.where(HerbalSubstanceEvidence.relation == filters.relation)
        stmt = stmt.where(EvidenceItem.id.in_(link))
    if filters.source_code:
        stmt = stmt.where(EvidenceItem.source_code == filters.source_code)
    if filters.evidence_types:
        stmt = stmt.where(EvidenceItem.evidence_type.in_(filters.evidence_types))
    if filters.year_from is not None:
        stmt = stmt.where(EvidenceItem.publication_year >= filters.year_from)
    if filters.year_to is not None:
        stmt = stmt.where(EvidenceItem.publication_year <= filters.year_to)
    if filters.query:
        tsquery = func.plainto_tsquery("english", filters.query)
        in_chunks = select(Chunk.evidence_item_id).where(Chunk.search_vector.op("@@")(tsquery))
        title = EvidenceItem.title.ilike(f"%{filters.query.replace('%', '')}%")
        stmt = stmt.where(or_(title, EvidenceItem.id.in_(in_chunks)))
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.scalars(
        stmt.order_by(EvidenceItem.publication_year.desc().nulls_last(), EvidenceItem.title)
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total


def get_evidence(session: Session, evidence_id: uuid.UUID) -> EvidenceItem | None:
    return session.get(EvidenceItem, evidence_id)


def chunks_for(session: Session, evidence_id: uuid.UUID) -> list[Chunk]:
    return list(
        session.scalars(
            select(Chunk).where(Chunk.evidence_item_id == evidence_id).order_by(Chunk.ordinal)
        )
    )


def substance_links(
    session: Session, evidence_ids: list[uuid.UUID]
) -> list[HerbalSubstanceEvidence]:
    if not evidence_ids:
        return []
    return list(
        session.scalars(
            select(HerbalSubstanceEvidence).where(
                HerbalSubstanceEvidence.evidence_item_id.in_(evidence_ids)
            )
        )
    )


@dataclass(frozen=True, slots=True)
class ProvenanceRow:
    entity_id: str
    source_code: str
    source_name: str
    licence: str | None
    licence_status: str
    record_url: str
    retrieved_at: datetime
    source_version: str | None
    extraction_method: str
    location: str | None
    excerpt: str | None


def provenance_for(
    session: Session, entity_table: str, entity_ids: list[str]
) -> dict[str, list[ProvenanceRow]]:
    if not entity_ids:
        return {}
    rows = session.execute(
        select(
            Provenance.entity_id,
            SourceRecord.source_code,
            Source.name,
            Source.licence,
            Source.licence_status,
            SourceRecord.url,
            SourceRecord.retrieved_at,
            SourceRecord.source_version,
            Provenance.extraction_method,
            Provenance.location,
            Provenance.verbatim_excerpt,
        )
        .join(SourceRecord, SourceRecord.id == Provenance.source_record_id)
        .join(Source, Source.code == SourceRecord.source_code)
        .where(and_(Provenance.entity_table == entity_table, Provenance.entity_id.in_(entity_ids)))
        .order_by(SourceRecord.retrieved_at.desc())
    ).all()
    out: dict[str, list[ProvenanceRow]] = {}
    for row in rows:
        out.setdefault(row[0], []).append(ProvenanceRow(*row))
    return out


def sources(session: Session) -> list[Source]:
    return list(session.scalars(select(Source).order_by(Source.code)))
