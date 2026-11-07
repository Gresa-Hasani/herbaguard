"""Retrieval index (Phase 5): segments cut from stored chunks, and their embeddings.

Both tables are a *derived index* of ``chunk`` text. They can be rebuilt at any time and hold no
scientific statements of their own; citations always point to the evidence item and its stored
provenance.

* ``retrieval_segment`` stores character offsets into ``chunk.text`` (no copy of the text), the
  segmentation strategy and version, a hash of the chunk text it was cut from (stale detection) and
  a full-text vector of title + segment text.
* ``segment_embedding`` stores one vector per (segment, embedding model). The vector column has no
  fixed dimension, so models of different sizes can coexist; ``dimension`` and ``model_version``
  are stored with every row and similarity search always filters on model, version and dimension,
  so vectors of different models are never compared. A per-model HNSW index on
  ``embedding::vector(<dimension>)`` is created by ``herbaguard ai index``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from herbaguard.models.base import Base, created_at_column, uuid_pk


class RetrievalSegment(Base):
    __tablename__ = "retrieval_segment"
    __table_args__ = (
        UniqueConstraint("chunk_id", "strategy", "strategy_version", "ordinal"),
        CheckConstraint("char_end > char_start AND char_start >= 0", "offsets_valid"),
        Index("ix_retrieval_segment_search_vector", "search_vector", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chunk.id", ondelete="CASCADE"), index=True
    )
    evidence_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_item.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    strategy: Mapped[str] = mapped_column(String(64))
    strategy_version: Mapped[str] = mapped_column(String(64))
    chunk_text_sha256: Mapped[str] = mapped_column(String(64))
    text_sha256: Mapped[str] = mapped_column(String(64))  # of the text that is embedded
    search_vector: Mapped[str] = mapped_column(TSVECTOR)
    created_at: Mapped[datetime] = created_at_column()


class SegmentEmbedding(Base):
    __tablename__ = "segment_embedding"
    __table_args__ = (
        CheckConstraint("dimension > 0", "dimension_positive"),
        CheckConstraint("vector_dims(embedding) = dimension", "dimension_matches_vector"),
        Index("ix_segment_embedding_model", "model", "model_version", "dimension"),
    )

    segment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("retrieval_segment.id", ondelete="CASCADE"), primary_key=True
    )
    model: Mapped[str] = mapped_column(String(128), primary_key=True)
    model_version: Mapped[str] = mapped_column(String(128))
    provider: Mapped[str] = mapped_column(String(32))
    dimension: Mapped[int] = mapped_column(Integer)
    text_sha256: Mapped[str] = mapped_column(String(64))
    embedding: Mapped[list[float]] = mapped_column(Vector())
    embedded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
