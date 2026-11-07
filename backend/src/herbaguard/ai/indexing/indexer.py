"""Incremental retrieval indexing: segments and embeddings.

Runs inside an ``ingestion_run`` of source ``herbaguard_ai_index`` so every run, its statistics and
its failures (``data_quality_issue``) are recorded like any other pipeline run.

* ``sync_segments`` — for every chunk of a current (not superseded) evidence item, (re)builds its
  segments only if the chunk text hash or the configured strategy/version changed. Segments of
  superseded evidence are removed from the index (the evidence item, its chunks, its provenance and
  any statements stay untouched). New sources are picked up automatically.
* ``embed_pending`` — embeds only segments that have no vector for the configured model, or whose
  vector is stale (different text hash, model version or dimension). Failed batches are retried one
  segment at a time; remaining failures are recorded and retried by the next run. Re-running is
  idempotent: rows are keyed by (segment, model).
* ``ensure_vector_index`` — one partial HNSW index per (model, dimension).
"""

from __future__ import annotations

import hashlib
import re
import uuid
from collections import defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, and_, delete, func, literal, literal_column, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from herbaguard.ai.embeddings import EmbeddingError, EmbeddingProvider
from herbaguard.ai.indexing.segmenter import StrategyParams, segment, strategy_version
from herbaguard.core.config import Settings
from herbaguard.domain.enums import IssueSeverity
from herbaguard.ingestion.context import IngestionContext, stable_id
from herbaguard.models import Chunk, EvidenceItem, RetrievalSegment, SegmentEmbedding

_WEIGHT_A: ColumnElement[str] = literal_column("'A'::\"char\"")
_WEIGHT_B: ColumnElement[str] = literal_column("'B'::\"char\"")
SAFE_MODEL_NAME = re.compile(r"^[A-Za-z0-9._:/\-]{1,128}$")


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def embedding_input(title: str | None, section: str | None, segment_text: str) -> str:
    """The exact text that is embedded (and hashed). The evidence title carries the herb/drug and
    document name; it is part of the retrieval unit, never part of a citation excerpt."""
    header = " | ".join(p for p in (title, section) if p)
    return f"{header}\n{segment_text}" if header else segment_text


@dataclass(frozen=True, slots=True)
class StrategyChoice:
    name: str
    params: StrategyParams
    version: str


def strategy_for(source_code: str, settings: Settings) -> StrategyChoice:
    name = settings.segment_strategy_by_source.get(source_code, settings.segment_strategy)
    params = StrategyParams(
        max_chars=settings.segment_max_chars_by_source.get(source_code, settings.segment_max_chars),
        overlap_sentences=settings.segment_overlap_sentences,
    )
    return StrategyChoice(name, params, strategy_version(name, params))


def _source_filter(sources: Sequence[str] | None):  # type: ignore[no-untyped-def]
    return EvidenceItem.source_code.in_(sources) if sources else literal(True)


def sync_segments(
    ctx: IngestionContext, settings: Settings, *, sources: Sequence[str] | None = None
) -> None:
    session = ctx.session
    # 1. invalidate: superseded evidence leaves the index
    superseded = select(EvidenceItem.id).where(
        EvidenceItem.is_superseded.is_(True), _source_filter(sources)
    )
    result: CursorResult[Any] = session.execute(  # type: ignore[assignment]
        delete(RetrievalSegment).where(RetrievalSegment.evidence_item_id.in_(superseded))
    )
    ctx.stats["segments_removed_superseded"] += result.rowcount or 0

    # 2. current state per chunk
    existing: dict[uuid.UUID, set[tuple[str, str, str]]] = defaultdict(set)
    for chunk_id, strategy, version, chunk_hash in session.execute(
        select(
            RetrievalSegment.chunk_id,
            RetrievalSegment.strategy,
            RetrievalSegment.strategy_version,
            RetrievalSegment.chunk_text_sha256,
        )
        .join(EvidenceItem, EvidenceItem.id == RetrievalSegment.evidence_item_id)
        .where(_source_filter(sources))
    ):
        existing[chunk_id].add((strategy, version, chunk_hash))

    rows = session.execute(
        select(Chunk.id, Chunk.evidence_item_id, Chunk.text, Chunk.section, EvidenceItem.title,
               EvidenceItem.source_code)
        .join(EvidenceItem, EvidenceItem.id == Chunk.evidence_item_id)
        .where(EvidenceItem.is_superseded.is_(False), _source_filter(sources))
        .order_by(Chunk.evidence_item_id, Chunk.ordinal)
    ).all()  # fmt: skip
    for chunk_id, evidence_id, chunk_text, section, title, source_code in rows:
        ctx.stats["chunks_seen"] += 1
        choice = strategy_for(source_code, settings)
        chunk_hash = sha256(chunk_text)
        if existing.get(chunk_id) == {(choice.name, choice.version, chunk_hash)}:
            ctx.stats["chunks_unchanged"] += 1
            continue
        if chunk_id in existing:
            session.execute(delete(RetrievalSegment).where(RetrievalSegment.chunk_id == chunk_id))
            ctx.stats["chunks_resegmented"] += 1
        spans = segment(chunk_text, choice.name, choice.params)
        if not spans:
            ctx.issue("segment_empty_chunk", "Chunk has no text to index.",
                      severity=IssueSeverity.INFO, chunk_id=str(chunk_id))  # fmt: skip
            continue
        for ordinal, (start, end) in enumerate(spans):
            piece = chunk_text[start:end]
            session.add(
                RetrievalSegment(
                    id=stable_id(
                        "retrieval_segment", chunk_id, choice.name, choice.version, ordinal
                    ),
                    chunk_id=chunk_id,
                    evidence_item_id=evidence_id,
                    ordinal=ordinal,
                    char_start=start,
                    char_end=end,
                    strategy=choice.name,
                    strategy_version=choice.version,
                    chunk_text_sha256=chunk_hash,
                    text_sha256=sha256(embedding_input(title, section, piece)),
                    search_vector=func.setweight(
                        func.to_tsvector("english", title or ""), _WEIGHT_A
                    ).op("||")(func.setweight(func.to_tsvector("english", piece), _WEIGHT_B)),
                )
            )
            ctx.stats["segments_created"] += 1
        ctx.session.flush()
    ctx.session.commit()


@dataclass(frozen=True, slots=True)
class PendingSegment:
    id: uuid.UUID
    text: str
    text_sha256: str


def _pending(
    session: Session, model: str, version: str, dimension: int, sources: Sequence[str] | None
) -> list[PendingSegment]:
    stmt = (
        select(RetrievalSegment.id, RetrievalSegment.char_start, RetrievalSegment.char_end,
               RetrievalSegment.text_sha256, Chunk.text, Chunk.section, EvidenceItem.title)
        .join(Chunk, Chunk.id == RetrievalSegment.chunk_id)
        .join(EvidenceItem, EvidenceItem.id == RetrievalSegment.evidence_item_id)
        .outerjoin(SegmentEmbedding, and_(SegmentEmbedding.segment_id == RetrievalSegment.id,
                                          SegmentEmbedding.model == model))
        .where(
            EvidenceItem.is_superseded.is_(False),
            _source_filter(sources),
            or_(
                SegmentEmbedding.segment_id.is_(None),
                SegmentEmbedding.text_sha256 != RetrievalSegment.text_sha256,
                SegmentEmbedding.model_version != version,
                SegmentEmbedding.dimension != dimension,
            ),
        )
        .order_by(RetrievalSegment.id)
    )  # fmt: skip
    return [
        PendingSegment(seg_id, embedding_input(title, section, chunk_text[start:end]), digest)
        for seg_id, start, end, digest, chunk_text, section, title in session.execute(stmt)
    ]


def _batches(items: list[PendingSegment], size: int) -> Iterator[list[PendingSegment]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def embed_pending(
    ctx: IngestionContext,
    provider: EmbeddingProvider,
    settings: Settings,
    *,
    sources: Sequence[str] | None = None,
    limit: int | None = None,
) -> None:
    info = provider.info()
    session = ctx.session
    pending = _pending(session, info.model, info.version, info.dimension, sources)
    ctx.stats["segments_pending"] = len(pending)
    if limit is not None:
        pending = pending[:limit]

    def store(batch: list[PendingSegment], vectors: list[list[float]]) -> None:
        for item, vector in zip(batch, vectors, strict=True):
            values = {
                "segment_id": item.id, "model": info.model, "model_version": info.version,
                "provider": info.provider, "dimension": info.dimension,
                "text_sha256": item.text_sha256, "embedding": vector,
            }  # fmt: skip
            stmt = insert(SegmentEmbedding).values(**values)
            session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["segment_id", "model"],
                    set_={**{k: v for k, v in values.items() if k not in ("segment_id", "model")},
                          "embedded_at": func.now()},
                )
            )  # fmt: skip
            ctx.stats["segments_embedded"] += 1

    for batch in _batches(pending, settings.embedding_batch_size):
        try:
            store(batch, provider.embed([b.text for b in batch], "document"))
        except EmbeddingError:
            for item in batch:  # retry one by one so one bad input does not block a batch
                try:
                    store([item], provider.embed([item.text], "document"))
                except EmbeddingError as exc:
                    ctx.issue("embedding_failed", str(exc), segment_id=str(item.id),
                              model=info.model)  # fmt: skip
                    ctx.stats["segments_failed"] += 1
        session.commit()
    ensure_vector_index(session, info.model, info.dimension)
    session.commit()


def index_name(model: str, dimension: int) -> str:
    return f"ix_segment_embedding_hnsw_{hashlib.sha1(f'{model}|{dimension}'.encode()).hexdigest()[:12]}"  # noqa: S324 - name only


def ensure_vector_index(session: Session, model: str, dimension: int) -> str | None:
    """Partial HNSW index for one model; queries use the same cast and predicate. Skipped for model
    names that are not plain identifiers (they cannot be bound as parameters in DDL)."""
    if not SAFE_MODEL_NAME.fullmatch(model) or not 0 < dimension <= 2000:
        return None
    name = index_name(model, dimension)
    session.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS {name} ON segment_embedding USING hnsw "
            f"((embedding::vector({dimension})) vector_cosine_ops) "
            f"WHERE model = '{model}' AND dimension = {dimension}"
        )
    )
    return name


@dataclass(frozen=True, slots=True)
class IndexStatus:
    segments: int
    evidence_items_indexed: int
    evidence_items_current: int
    embedded: int
    stale_or_missing: int
    model: str | None
    model_version: str | None
    dimension: int | None


def index_status(
    session: Session, *, model: str | None, version: str | None, dimension: int | None
) -> IndexStatus:
    current = select(EvidenceItem.id).where(EvidenceItem.is_superseded.is_(False))
    segments = session.scalar(
        select(func.count()).select_from(RetrievalSegment).where(RetrievalSegment.evidence_item_id.in_(current))
    ) or 0  # fmt: skip
    items_indexed = (
        session.scalar(
            select(func.count(func.distinct(RetrievalSegment.evidence_item_id))).where(
                RetrievalSegment.evidence_item_id.in_(current)
            )
        )
        or 0
    )
    items_current = session.scalar(
        select(func.count(func.distinct(Chunk.evidence_item_id))).where(Chunk.evidence_item_id.in_(current))
    ) or 0  # fmt: skip
    embedded = 0
    if model and version and dimension:
        embedded = (
            session.scalar(
                select(func.count())
                .select_from(SegmentEmbedding)
                .join(RetrievalSegment, RetrievalSegment.id == SegmentEmbedding.segment_id)
                .where(
                    RetrievalSegment.evidence_item_id.in_(current),
                    SegmentEmbedding.model == model,
                    SegmentEmbedding.model_version == version,
                    SegmentEmbedding.dimension == dimension,
                    SegmentEmbedding.text_sha256 == RetrievalSegment.text_sha256,
                )
            )
            or 0
        )
    return IndexStatus(segments, items_indexed, items_current, embedded, segments - embedded,
                       model, version, dimension)  # fmt: skip
