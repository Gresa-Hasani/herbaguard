"""Indications, interaction assertions, evidence items and retrieval chunks."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Computed,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from herbaguard.domain.enums import (
    AssertionStatus,
    EvidenceRelation,
    EvidenceType,
    StatementType,
    UseCategory,
)
from herbaguard.models.base import Base, created_at_column, enum_check, updated_at_column, uuid_pk

# Dimension of the embedding model planned for Phase 5 (bge-small-en-v1.5 = 384).
# Changing the model to a different dimension requires a migration.
EMBEDDING_DIMENSION = 384


class EvidenceItem(Base):
    """A citable unit of evidence: monograph section, label section, article or fact sheet."""

    __tablename__ = "evidence_item"
    __table_args__ = (
        enum_check("evidence_type", EvidenceType),
        UniqueConstraint("source_code", "external_id"),
        CheckConstraint(
            "publication_year IS NULL OR publication_year BETWEEN 1500 AND 2100", "year"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    source_code: Mapped[str] = mapped_column(ForeignKey("source.code"), index=True)
    external_id: Mapped[str] = mapped_column(String(255))  # PMID, EMA doc no. + section, set_id…
    evidence_type: Mapped[str] = mapped_column(String(8), index=True)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    pmid: Mapped[str | None] = mapped_column(String(16), index=True)
    doi: Mapped[str | None] = mapped_column(String(255))
    publication_year: Mapped[int | None] = mapped_column(Integer)
    document_date: Mapped[date | None] = mapped_column(Date)  # e.g. monograph adoption date
    is_superseded: Mapped[bool] = mapped_column(default=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class Indication(Base):
    """A therapeutic indication of a herbal substance, always tagged with its EMA use category."""

    __tablename__ = "indication"
    __table_args__ = (enum_check("use_category", UseCategory),)

    id: Mapped[uuid.UUID] = uuid_pk()
    herbal_substance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("herbal_substance.id", ondelete="CASCADE"), index=True
    )
    evidence_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_item.id", ondelete="CASCADE")
    )
    text: Mapped[str] = mapped_column(Text)
    use_category: Mapped[str] = mapped_column(String(32))
    mesh_id: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = created_at_column()


class InteractionAssertion(Base):
    """One statement from one source that a herbal substance interacts with a drug or drug class.

    Assertions from different sources are never merged or overwritten; the interaction class
    shown to users is computed from all active assertions at query time.
    """

    __tablename__ = "interaction_assertion"
    __table_args__ = (
        enum_check("use_category", UseCategory),
        enum_check("status", AssertionStatus),
        enum_check("evidence_type", EvidenceType),
        enum_check("statement_type", StatementType),
        CheckConstraint(
            "(drug_id IS NOT NULL) <> (drug_class_code IS NOT NULL)", "exactly_one_object"
        ),
        Index("ix_interaction_assertion_pair", "herbal_substance_id", "drug_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    herbal_substance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("herbal_substance.id", ondelete="CASCADE")
    )
    drug_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("drug.id", ondelete="CASCADE"))
    drug_class_code: Mapped[str | None] = mapped_column(
        ForeignKey("drug_class.code", ondelete="CASCADE"), index=True
    )
    # The source's own wording for the drug or class (e.g. "coumarin-type anticoagulants").
    object_label_verbatim: Mapped[str] = mapped_column(Text)
    # The source's own wording for the herb (labels often say just "ginseng"). NULL when the
    # source document is about the herb itself (EMA monograph, NCCIH fact sheet).
    subject_label_verbatim: Mapped[str | None] = mapped_column(Text)
    statement_type: Mapped[str] = mapped_column(
        String(32), default=StatementType.UNCLASSIFIED.value
    )
    source_code: Mapped[str] = mapped_column(ForeignKey("source.code"))
    evidence_type: Mapped[str] = mapped_column(String(8))
    source_section: Mapped[str | None] = mapped_column(
        String(64)
    )  # e.g. "4.5", "drug_interactions"
    use_category: Mapped[str] = mapped_column(String(32), default=UseCategory.NOT_APPLICABLE.value)
    mechanism: Mapped[str | None] = mapped_column(Text)
    conditions: Mapped[str | None] = mapped_column(Text)  # dose, duration, route qualifiers
    severity_wording: Mapped[str | None] = mapped_column(String(255))  # relayed, never computed
    status: Mapped[str] = mapped_column(String(16), default=AssertionStatus.ACTIVE.value)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class InteractionAssertionEvidence(Base):
    __tablename__ = "interaction_assertion_evidence"

    interaction_assertion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interaction_assertion.id", ondelete="CASCADE"), primary_key=True
    )
    evidence_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_item.id", ondelete="CASCADE"), primary_key=True
    )


class Chunk(Base):
    """A retrieval unit for the AI assistant (hybrid full-text + vector search).

    ``text`` is stored only when the source licence allows local storage; the database is never
    committed to Git.
    """

    __tablename__ = "chunk"
    __table_args__ = (
        UniqueConstraint("evidence_item_id", "ordinal"),
        Index("ix_chunk_search_vector", "search_vector", postgresql_using="gin"),
        Index(
            "ix_chunk_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    evidence_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_item.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(128))
    text: Mapped[str] = mapped_column(Text)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSION))
    embedding_model: Mapped[str | None] = mapped_column(String(128))
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', coalesce(text, ''))", persisted=True)
    )
    created_at: Mapped[datetime] = created_at_column()


class HerbalSubstanceEvidence(Base):
    """Links evidence items (monograph sections, fact sheets, articles, labels) to substances."""

    __tablename__ = "herbal_substance_evidence"
    __table_args__ = (enum_check("relation", EvidenceRelation),)

    herbal_substance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("herbal_substance.id", ondelete="CASCADE"), primary_key=True
    )
    evidence_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_item.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    relation: Mapped[str] = mapped_column(String(32), primary_key=True)
