"""Chunk retrieval for the assistant: full-text and vector search, lexicons, embedding upkeep."""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy.orm import Session

from herbaguard.models import (
    Chunk,
    Drug,
    EvidenceItem,
    HerbalSubstance,
    HerbalSubstanceEvidence,
    Source,
    TaxonName,
)

_LEXEME = re.compile(r"[a-z0-9]+")


def tsquery_text(terms: Sequence[str]) -> str | None:
    """OR-query of sanitised terms for ``to_tsquery`` (questions rarely contain every word)."""
    words = list(dict.fromkeys(w for t in terms for w in _LEXEME.findall(t.lower()) if len(w) > 1))
    return " | ".join(words) if words else None


def _filters(substance_ids: Sequence[uuid.UUID] | None) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [EvidenceItem.is_superseded.is_(False)]
    if substance_ids:
        linked = select(HerbalSubstanceEvidence.evidence_item_id).where(
            HerbalSubstanceEvidence.herbal_substance_id.in_(list(substance_ids))
        )
        conditions.append(Chunk.evidence_item_id.in_(linked))
    return conditions


def full_text_search(
    session: Session,
    terms: Sequence[str],
    *,
    substance_ids: Sequence[uuid.UUID] | None,
    limit: int,
    source_codes: Sequence[str] | None = None,
) -> list[uuid.UUID]:
    """Chunk ids, best first, ranked by ``ts_rank_cd`` over the generated tsvector;
    optionally only chunks of evidence from ``source_codes``."""
    text = tsquery_text(terms)
    if text is None:
        return []
    query = func.to_tsquery("english", text)
    rank = func.ts_rank_cd(Chunk.search_vector, query)
    conditions = _filters(substance_ids)
    if source_codes:
        conditions.append(EvidenceItem.source_code.in_(list(source_codes)))
    stmt = (
        select(Chunk.id)
        .join(EvidenceItem, EvidenceItem.id == Chunk.evidence_item_id)
        .where(Chunk.search_vector.op("@@")(query), *conditions)
        .order_by(rank.desc(), Chunk.id)
        .limit(limit)
    )
    return list(session.scalars(stmt))


def vector_search(
    session: Session,
    embedding: Sequence[float],
    *,
    model: str,
    substance_ids: Sequence[uuid.UUID] | None,
    limit: int,
) -> list[uuid.UUID]:
    """Chunk ids, nearest first (cosine distance, HNSW index), embedded with ``model`` only."""
    distance = Chunk.embedding.cosine_distance(list(embedding))
    stmt = (
        select(Chunk.id)
        .join(EvidenceItem, EvidenceItem.id == Chunk.evidence_item_id)
        .where(
            Chunk.embedding.is_not(None),
            Chunk.embedding_model == model,
            *_filters(substance_ids),
        )
        .order_by(distance, Chunk.id)
        .limit(limit)
    )
    return list(session.scalars(stmt))


def chunks_for_evidence(session: Session, evidence_ids: Sequence[uuid.UUID]) -> list[uuid.UUID]:
    if not evidence_ids:
        return []
    return list(
        session.scalars(
            select(Chunk.id)
            .where(Chunk.evidence_item_id.in_(list(evidence_ids)))
            .order_by(Chunk.evidence_item_id, Chunk.ordinal)
        )
    )


@dataclass(frozen=True, slots=True)
class PassageRow:
    chunk: Chunk
    evidence: EvidenceItem
    source_name: str
    source_is_official: bool


def passages(session: Session, chunk_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, PassageRow]:
    if not chunk_ids:
        return {}
    rows = session.execute(
        select(Chunk, EvidenceItem, Source.name, Source.is_official)
        .join(EvidenceItem, EvidenceItem.id == Chunk.evidence_item_id)
        .join(Source, Source.code == EvidenceItem.source_code)
        .where(Chunk.id.in_(list(chunk_ids)))
    ).all()
    return {row[0].id: PassageRow(row[0], row[1], row[2], bool(row[3])) for row in rows}


def herb_names(session: Session) -> list[str]:
    """Names that identify a herb in free text: accepted/synonym/common taxon names of taxa with
    a herbal substance, plus EMA pharmaceutical and English common names."""
    taxon_names = session.scalars(
        select(TaxonName.name)
        .join(HerbalSubstance, HerbalSubstance.taxon_id == TaxonName.taxon_id)
        .distinct()
    ).all()
    substance_names = session.execute(
        select(HerbalSubstance.pharmaceutical_name, HerbalSubstance.common_name_en)
    ).all()
    names = {n for n in taxon_names if n}
    for pharmaceutical, common in substance_names:
        names.update(n for n in (pharmaceutical, common) if n)
    return sorted(names)


def drug_names(session: Session) -> dict[str, str]:
    """Drug ingredient name → RxCUI for every drug in the index."""
    return dict(session.execute(select(Drug.name, Drug.rxcui)).tuples().all())


# --------------------------------------------------------------------------- embeddings


def chunks_to_embed(
    session: Session, *, model: str, limit: int, force: bool = False
) -> list[tuple[uuid.UUID, str, str | None, str]]:
    """(chunk id, text, section, evidence title) for chunks lacking an embedding from ``model``."""
    stmt = select(Chunk.id, Chunk.text, Chunk.section, EvidenceItem.title).join(
        EvidenceItem, EvidenceItem.id == Chunk.evidence_item_id
    )
    if not force:
        stmt = stmt.where(
            (Chunk.embedding.is_(None))
            | (Chunk.embedding_model.is_(None))
            | (Chunk.embedding_model != model)
        )
    rows = session.execute(stmt.order_by(Chunk.id).limit(limit)).all()
    return [(r[0], r[1], r[2], r[3]) for r in rows]


def store_embeddings(
    session: Session, vectors: Sequence[tuple[uuid.UUID, Sequence[float]]], *, model: str
) -> None:
    for chunk_id, vector in vectors:
        session.execute(
            update(Chunk)
            .where(Chunk.id == chunk_id)
            .values(embedding=list(vector), embedding_model=model)
        )


def embedding_counts(session: Session, *, model: str) -> tuple[int, int]:
    """(chunks embedded with ``model``, all chunks)."""
    total = session.scalar(select(func.count()).select_from(Chunk)) or 0
    embedded = (
        session.scalar(
            select(func.count())
            .select_from(Chunk)
            .where(Chunk.embedding.is_not(None), Chunk.embedding_model == model)
        )
        or 0
    )
    return embedded, total
