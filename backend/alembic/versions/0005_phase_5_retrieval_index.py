"""Phase 5: model-independent retrieval index (segments + embeddings).

- ``retrieval_segment``: retrieval units cut from ``chunk.text`` (character offsets, no text copy),
  with segmentation strategy/version, chunk-text hash for stale detection and a full-text vector.
- ``segment_embedding``: one vector per (segment, embedding model) with model version, provider,
  dimension, text hash and timestamp. The vector column has no fixed dimension so models can be
  changed or compared without a migration; a CHECK keeps ``dimension`` equal to the vector size.
- ``chunk.embedding`` / ``chunk.embedding_model`` (fixed ``vector(384)``, never populated) and their
  HNSW index are removed. The downgrade refuses to run while segment embeddings exist, so vectors
  are never dropped silently.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-03 12:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "retrieval_segment",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("chunk_id", sa.UUID(), nullable=False),
        sa.Column("evidence_item_id", sa.UUID(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("strategy", sa.String(length=64), nullable=False),
        sa.Column("strategy_version", sa.String(length=64), nullable=False),
        sa.Column("chunk_text_sha256", sa.String(length=64), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_end > char_start AND char_start >= 0",
            name=op.f("ck_retrieval_segment_offsets_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["chunk.id"],
            name=op.f("fk_retrieval_segment_chunk_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_item_id"],
            ["evidence_item.id"],
            name=op.f("fk_retrieval_segment_evidence_item_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_retrieval_segment")),
        sa.UniqueConstraint(
            "chunk_id",
            "strategy",
            "strategy_version",
            "ordinal",
            name=op.f("uq_retrieval_segment_chunk_id"),
        ),
    )
    op.create_index(op.f("ix_retrieval_segment_chunk_id"), "retrieval_segment", ["chunk_id"])
    op.create_index(
        op.f("ix_retrieval_segment_evidence_item_id"), "retrieval_segment", ["evidence_item_id"]
    )
    op.create_index(
        "ix_retrieval_segment_search_vector",
        "retrieval_segment",
        ["search_vector"],
        postgresql_using="gin",
    )

    op.create_table(
        "segment_embedding",
        sa.Column("segment_id", sa.UUID(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("model_version", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("dimension", sa.Integer(), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(), nullable=False),
        sa.Column(
            "embedded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("dimension > 0", name=op.f("ck_segment_embedding_dimension_positive")),
        sa.CheckConstraint(
            "vector_dims(embedding) = dimension",
            name=op.f("ck_segment_embedding_dimension_matches_vector"),
        ),
        sa.ForeignKeyConstraint(
            ["segment_id"],
            ["retrieval_segment.id"],
            name=op.f("fk_segment_embedding_segment_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("segment_id", "model", name=op.f("pk_segment_embedding")),
    )
    op.create_index(
        "ix_segment_embedding_model", "segment_embedding", ["model", "model_version", "dimension"]
    )

    op.drop_index("ix_chunk_embedding_hnsw", table_name="chunk")
    op.drop_column("chunk", "embedding")
    op.drop_column("chunk", "embedding_model")


def downgrade() -> None:
    bind = op.get_bind()
    count = bind.execute(sa.text("SELECT count(*) FROM segment_embedding")).scalar_one()
    if count:
        msg = (
            f"segment_embedding holds {count} vectors; downgrading would drop them. Delete them "
            "explicitly first (they can be regenerated with `herbaguard ai index`)."
        )
        raise RuntimeError(msg)
    op.add_column("chunk", sa.Column("embedding_model", sa.String(length=128), nullable=True))
    op.add_column("chunk", sa.Column("embedding", pgvector.sqlalchemy.Vector(384), nullable=True))
    op.create_index(
        "ix_chunk_embedding_hnsw",
        "chunk",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_index("ix_segment_embedding_model", table_name="segment_embedding")
    op.drop_table("segment_embedding")
    op.drop_index("ix_retrieval_segment_search_vector", table_name="retrieval_segment")
    op.drop_index(op.f("ix_retrieval_segment_evidence_item_id"), table_name="retrieval_segment")
    op.drop_index(op.f("ix_retrieval_segment_chunk_id"), table_name="retrieval_segment")
    op.drop_table("retrieval_segment")
