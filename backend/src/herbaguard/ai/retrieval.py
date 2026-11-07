"""Hybrid retrieval over the segment index: PostgreSQL full-text search + pgvector, fused by RRF.

Design rules (docs/ai/hybrid-retrieval.md):

* Retrieval works on ``retrieval_segment`` rows of **current** evidence (superseded evidence is
  never returned). Every hit is hydrated from the database: verbatim excerpt (a slice of the stored
  chunk text), evidence item, source licence and provenance. Nothing is copied from model output.
* Filters are generic: source codes, evidence types, and entity scopes resolved through the existing
  link tables (herb → ``herbal_substance_evidence``; drug → ``interaction_assertion`` and
  ``drug_target_role``; enzyme/transporter → ``target_modulation`` and ``drug_target_role``). New
  sources that use these tables are filterable without code changes.
* Semantic search only compares vectors of the configured model, model version and dimension whose
  text hash matches the current segment (stale vectors are ignored). If no embedding provider is
  configured or reachable, retrieval falls back to keyword search and says so.
* Scores are reported for transparency; they rank text similarity, not evidence quality.
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from pgvector.sqlalchemy import Vector
from sqlalchemy import ColumnElement, Text, bindparam, cast, func, intersect, select, union
from sqlalchemy.dialects.postgresql import TSQUERY
from sqlalchemy.orm import Session

from herbaguard.ai.embeddings import EmbeddingError, EmbeddingProvider
from herbaguard.ai.fusion import rrf
from herbaguard.core.config import Settings
from herbaguard.models import (
    Chunk,
    DrugTargetRoleLink,
    EvidenceItem,
    HerbalSubstance,
    HerbalSubstanceEvidence,
    InteractionAssertion,
    InteractionAssertionEvidence,
    RetrievalSegment,
    SegmentEmbedding,
    Source,
    TargetModulation,
)
from herbaguard.repositories import evidence as evidence_repo
from herbaguard.repositories.evidence import ProvenanceRow

Mode = Literal["keyword", "semantic", "hybrid"]


@dataclass(frozen=True, slots=True)
class RetrievalFilters:
    sources: tuple[str, ...] = ()
    evidence_types: tuple[str, ...] = ()
    herb_substance_ids: tuple[uuid.UUID, ...] = ()
    drug_ids: tuple[uuid.UUID, ...] = ()
    target_ids: tuple[uuid.UUID, ...] = ()
    # Entity scopes combine with OR when ``entity_match`` is "any" (e.g. herb OR drug evidence for
    # an interaction question) and with AND when "all".
    entity_match: Literal["any", "all"] = "any"
    redistributable_only: bool = False


@dataclass(frozen=True, slots=True)
class RetrievalQuery:
    text: str
    expansions: tuple[str, ...] = ()  # entity names added to the keyword query (synonyms, aliases)
    filters: RetrievalFilters = field(default_factory=RetrievalFilters)
    mode: Mode = "hybrid"
    top_k: int | None = None


@dataclass(frozen=True, slots=True)
class RetrievedEvidence:
    segment_id: uuid.UUID
    evidence_item_id: uuid.UUID
    external_id: str
    source_code: str
    source_name: str
    licence: str | None
    licence_status: str
    redistributable: bool
    evidence_type: str
    title: str
    url: str | None
    document_date: date | None
    publication_year: int | None
    section: str | None
    excerpt: str  # verbatim slice of the stored chunk text
    char_start: int
    char_end: int
    herbs: tuple[str, ...]
    provenance: tuple[ProvenanceRow, ...]
    fused_score: float
    ranks: dict[str, int]
    similarity: float | None
    keyword_score: float | None


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    items: list[RetrievedEvidence]
    mode_requested: Mode
    mode_used: Mode
    notes: list[str]
    embedding_model: str | None
    candidates: dict[str, int]
    duration_ms: int


# --------------------------------------------------------------------------- scopes


def _scope(filters: RetrievalFilters) -> Any | None:
    """Evidence ids allowed by the entity filters (a subquery), or None (no entity filter).

    Every scope is resolved through the generic link tables, so evidence of future sources is
    filterable as soon as it is linked to herbs, drugs or targets."""
    parts: list[Any] = []
    if filters.herb_substance_ids:
        parts.append(
            select(HerbalSubstanceEvidence.evidence_item_id).where(
                HerbalSubstanceEvidence.herbal_substance_id.in_(filters.herb_substance_ids)
            )
        )
    if filters.drug_ids:
        parts.append(
            union(
                select(InteractionAssertionEvidence.evidence_item_id)
                .join(
                    InteractionAssertion,
                    InteractionAssertion.id
                    == InteractionAssertionEvidence.interaction_assertion_id,
                )
                .where(InteractionAssertion.drug_id.in_(filters.drug_ids)),
                select(DrugTargetRoleLink.evidence_item_id).where(
                    DrugTargetRoleLink.drug_id.in_(filters.drug_ids),
                    DrugTargetRoleLink.evidence_item_id.is_not(None),
                ),
            )
        )
    if filters.target_ids:
        parts.append(
            union(
                select(TargetModulation.evidence_item_id).where(
                    TargetModulation.target_id.in_(filters.target_ids),
                    TargetModulation.evidence_item_id.is_not(None),
                ),
                select(DrugTargetRoleLink.evidence_item_id).where(
                    DrugTargetRoleLink.target_id.in_(filters.target_ids),
                    DrugTargetRoleLink.evidence_item_id.is_not(None),
                ),
            )
        )
    if not parts:
        return None
    if len(parts) == 1:
        combined: Any = parts[0]
    elif filters.entity_match == "any":
        combined = union(*parts)
    else:
        combined = intersect(*parts)
    sub = combined.subquery()
    return select(sub.c[0])


def _base_conditions(filters: RetrievalFilters) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [EvidenceItem.is_superseded.is_(False)]
    if filters.sources:
        conditions.append(EvidenceItem.source_code.in_(filters.sources))
    if filters.evidence_types:
        conditions.append(EvidenceItem.evidence_type.in_(filters.evidence_types))
    if filters.redistributable_only:
        conditions.append(
            EvidenceItem.source_code.in_(
                select(Source.code).where(Source.redistributable.is_(True))
            )
        )
    scope = _scope(filters)
    if scope is not None:
        conditions.append(RetrievalSegment.evidence_item_id.in_(scope))
    return conditions


# --------------------------------------------------------------------------- retrievers


def keyword_search(
    session: Session, query: RetrievalQuery, limit: int
) -> list[tuple[uuid.UUID, float]]:
    """Segments matching any query term (OR), ranked by ``ts_rank_cd`` with length normalisation.
    Entity names are added as phrases, so synonyms and aliases match even if the question uses
    another name."""
    tsquery: ColumnElement[str] | None = None
    for index, term in enumerate([query.text, *query.expansions]):
        if not term.strip():
            continue
        bound = bindparam(f"term_{index}", term, type_=Text)
        # any word of the term (OR), plus the exact phrase for entity names
        any_word = cast(
            func.replace(cast(func.plainto_tsquery("english", bound), Text), "&", "|"), TSQUERY
        )
        piece = (
            any_word if index == 0 else any_word.op("||")(func.phraseto_tsquery("english", bound))
        )
        tsquery = piece if tsquery is None else tsquery.op("||")(piece)
    if tsquery is None:
        return []
    rank = func.ts_rank_cd(RetrievalSegment.search_vector, tsquery, 1)
    stmt = (
        select(RetrievalSegment.id, rank)
        .join(EvidenceItem, EvidenceItem.id == RetrievalSegment.evidence_item_id)
        .where(RetrievalSegment.search_vector.op("@@")(tsquery), *_base_conditions(query.filters))
        .order_by(rank.desc(), RetrievalSegment.id)
        .limit(limit)
    )
    return [(row[0], float(row[1])) for row in session.execute(stmt)]


def vector_search(
    session: Session,
    query: RetrievalQuery,
    vector: list[float],
    *,
    model: str,
    version: str,
    limit: int,
    min_similarity: float,
) -> list[tuple[uuid.UUID, float]]:
    dim = len(vector)
    # Same cast and predicate as the per-model partial HNSW index (indexer.ensure_vector_index).
    distance = cast(SegmentEmbedding.embedding, Vector(dim)).cosine_distance(
        cast(bindparam("query_vector", str(vector), type_=Text), Vector(dim))
    )
    stmt = (
        select(RetrievalSegment.id, (1 - distance).label("similarity"))
        .join(SegmentEmbedding, SegmentEmbedding.segment_id == RetrievalSegment.id)
        .join(EvidenceItem, EvidenceItem.id == RetrievalSegment.evidence_item_id)
        .where(
            SegmentEmbedding.model == model,
            SegmentEmbedding.model_version == version,
            SegmentEmbedding.dimension == dim,
            SegmentEmbedding.text_sha256 == RetrievalSegment.text_sha256,
            *_base_conditions(query.filters),
        )
        .order_by(distance, RetrievalSegment.id)
        .limit(limit)
    )
    rows = session.execute(stmt).all()
    return [(r[0], float(r[1])) for r in rows if float(r[1]) >= min_similarity]


# --------------------------------------------------------------------------- orchestration


def retrieve(
    session: Session,
    settings: Settings,
    query: RetrievalQuery,
    embeddings: EmbeddingProvider | None,
) -> RetrievalResult:
    started = time.perf_counter()
    notes: list[str] = []
    ranked: dict[str, list[uuid.UUID]] = {}
    keyword_scores: dict[uuid.UUID, float] = {}
    similarities: dict[uuid.UUID, float] = {}
    mode_used: Mode = query.mode
    model_name: str | None = None

    if query.mode in ("keyword", "hybrid"):
        hits = keyword_search(session, query, settings.retrieval_keyword_top_k)
        ranked["keyword"] = [h for h, _ in hits]
        keyword_scores = dict(hits)
    if query.mode in ("semantic", "hybrid"):
        if embeddings is None:
            notes.append("No embedding model is configured: keyword search only.")
        else:
            try:
                info = embeddings.info()
                vector = embeddings.embed([query.text], "query")[0]
                model_name = info.model
                hits = vector_search(
                    session, query, vector, model=info.model, version=info.version,
                    limit=settings.retrieval_vector_top_k, min_similarity=settings.retrieval_min_similarity,
                )  # fmt: skip
                ranked["semantic"] = [h for h, _ in hits]
                similarities = dict(hits)
                if not hits:
                    notes.append(
                        f"No segment has a current embedding for model '{info.model}' within the "
                        "filters; run `herbaguard ai index` to embed new or changed evidence."
                    )
            except EmbeddingError as exc:
                notes.append(f"Semantic search unavailable ({exc}); keyword search only.")
        if not ranked.get("semantic"):  # no model, provider down, or no current vectors for it
            ranked.pop("semantic", None)
            mode_used = "keyword"
            if query.mode == "semantic":
                ranked["keyword"] = [
                    h for h, _ in keyword_search(session, query, settings.retrieval_keyword_top_k)
                ]

    candidates = {name: len(items) for name, items in ranked.items()}
    source_of = _source_codes(session, {i for items in ranked.values() for i in items})
    multipliers = {
        seg: settings.retrieval_source_weights.get(source_of.get(seg, ""), 1.0) for seg in source_of
    }
    fused = rrf(
        ranked,
        k=settings.retrieval_rrf_k,
        weights={"keyword": settings.retrieval_keyword_weight,
                 "semantic": settings.retrieval_vector_weight},
        multipliers=multipliers,
    )  # fmt: skip
    top_k = query.top_k or settings.retrieval_top_k
    chosen = _diversify(session, fused, top_k, settings.retrieval_max_per_evidence_item)
    items = _hydrate(session, chosen, keyword_scores, similarities)
    return RetrievalResult(
        items=items,
        mode_requested=query.mode,
        mode_used=mode_used,
        notes=notes,
        embedding_model=model_name,
        candidates=candidates,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )


def _source_codes(session: Session, segment_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not segment_ids:
        return {}
    rows = session.execute(
        select(RetrievalSegment.id, EvidenceItem.source_code)
        .join(EvidenceItem, EvidenceItem.id == RetrievalSegment.evidence_item_id)
        .where(RetrievalSegment.id.in_(segment_ids))
    )
    return {r[0]: r[1] for r in rows}


def _diversify(session, fused, top_k: int, per_item: int):  # type: ignore[no-untyped-def]
    """Keep the fused order but at most ``per_item`` segments per evidence item, and never two
    overlapping segments of the same chunk (de-duplication)."""
    if not fused:
        return []
    meta = {
        r[0]: (r[1], r[2], r[3], r[4])
        for r in session.execute(
            select(RetrievalSegment.id, RetrievalSegment.evidence_item_id, RetrievalSegment.chunk_id,
                   RetrievalSegment.char_start, RetrievalSegment.char_end)
            .where(RetrievalSegment.id.in_([f.key for f in fused]))
        )
    }  # fmt: skip
    per_evidence: dict[uuid.UUID, int] = defaultdict(int)
    taken_ranges: dict[uuid.UUID, list[tuple[int, int]]] = defaultdict(list)
    out = []
    for f in fused:
        evidence_id, chunk_id, start, end = meta[f.key]
        if per_evidence[evidence_id] >= per_item:
            continue
        if any(start < e and s < end for s, e in taken_ranges[chunk_id]):
            continue
        per_evidence[evidence_id] += 1
        taken_ranges[chunk_id].append((start, end))
        out.append(f)
        if len(out) >= top_k:
            break
    return out


def _hydrate(session, chosen, keyword_scores, similarities) -> list[RetrievedEvidence]:  # type: ignore[no-untyped-def]
    if not chosen:
        return []
    ids = [f.key for f in chosen]
    rows = {
        r.RetrievalSegment.id: r
        for r in session.execute(
            select(RetrievalSegment, Chunk.text, Chunk.section, EvidenceItem, Source)
            .join(Chunk, Chunk.id == RetrievalSegment.chunk_id)
            .join(EvidenceItem, EvidenceItem.id == RetrievalSegment.evidence_item_id)
            .join(Source, Source.code == EvidenceItem.source_code)
            .where(RetrievalSegment.id.in_(ids))
        )
    }
    evidence_ids = list({rows[i].EvidenceItem.id for i in ids})
    provenance = evidence_repo.provenance_for(
        session, "evidence_item", [str(e) for e in evidence_ids]
    )
    herbs: dict[uuid.UUID, set[str]] = defaultdict(set)
    for evidence_id, name in session.execute(
        select(HerbalSubstanceEvidence.evidence_item_id, HerbalSubstance.pharmaceutical_name)
        .join(HerbalSubstance, HerbalSubstance.id == HerbalSubstanceEvidence.herbal_substance_id)
        .where(HerbalSubstanceEvidence.evidence_item_id.in_(evidence_ids))
    ):
        if name:
            herbs[evidence_id].add(name)
    out: list[RetrievedEvidence] = []
    for f in chosen:
        row = rows[f.key]
        seg, item, source = row.RetrievalSegment, row.EvidenceItem, row.Source
        prov = tuple(provenance.get(str(item.id), []))
        out.append(
            RetrievedEvidence(
                segment_id=seg.id,
                evidence_item_id=item.id,
                external_id=item.external_id,
                source_code=item.source_code,
                source_name=source.name,
                licence=source.licence,
                licence_status=source.licence_status,
                redistributable=source.redistributable,
                evidence_type=item.evidence_type,
                title=item.title,
                url=item.url or (prov[0].record_url if prov else None),
                document_date=item.document_date,
                publication_year=item.publication_year,
                section=row.section,
                excerpt=row.text[seg.char_start : seg.char_end],
                char_start=seg.char_start,
                char_end=seg.char_end,
                herbs=tuple(sorted(herbs.get(item.id, set()))),
                provenance=prov,
                fused_score=round(f.score, 6),
                ranks=dict(f.ranks),
                similarity=round(similarities[f.key], 4) if f.key in similarities else None,
                keyword_score=round(keyword_scores[f.key], 4) if f.key in keyword_scores else None,
            )
        )
    return out
