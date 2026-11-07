"""Validated answer cache for the suggested Evidence Assistant questions.

``answer_cache`` stores, per normalised question, the complete validated ``AskResponse`` payload
together with the fingerprint (evidence context, prompts, validation code, generator configuration)
it was generated under. Only answers that passed validation are written (CHECK constraint), and a row
is served only while its fingerprint still matches. The table is derived data: it can be emptied at
any time and is rebuilt with ``herbaguard ai prepare-answers``.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-08 09:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "answer_cache",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("question_id", sa.String(length=64), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("validation_version", sa.String(length=64), nullable=False),
        sa.Column("validation_status", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("prompts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generation_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("citation_labels", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "validation_status = 'passed'", name=op.f("ck_answer_cache_only_validated_answers")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_answer_cache")),
        sa.UniqueConstraint("question_id", name=op.f("uq_answer_cache_question_id")),
    )


def downgrade() -> None:
    op.drop_table("answer_cache")
