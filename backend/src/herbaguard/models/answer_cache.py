"""Persistent cache of validated Evidence Assistant answers (suggested questions only).

One row per normalised question. A row is only a *candidate*: it is served when, and only when, its
``fingerprint`` equals the fingerprint recomputed from the current evidence context, prompts,
validation code and generator configuration (see ``herbaguard.ai.answer_cache``). The table holds
no scientific statements of its own beyond the validated response that the normal pipeline produced,
and nothing is ever written here for a failed or rejected generation.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from herbaguard.models.base import Base, created_at_column, updated_at_column, uuid_pk


class AnswerCache(Base):
    __tablename__ = "answer_cache"
    __table_args__ = (
        UniqueConstraint("question_id"),
        CheckConstraint("validation_status = 'passed'", "only_validated_answers"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    question_id: Mapped[str] = mapped_column(String(64))  # sha256 of the normalised question
    question_text: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64))  # evidence + prompts + validation + config
    schema_version: Mapped[int] = mapped_column(Integer)
    validation_version: Mapped[str] = mapped_column(String(64))
    validation_status: Mapped[str] = mapped_column(String(16))  # always "passed"
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(255))
    prompts: Mapped[list[str]] = mapped_column(JSONB)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    generation_ms: Mapped[int] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    citation_labels: Mapped[list[str]] = mapped_column(JSONB)
    response: Mapped[dict[str, Any]] = mapped_column(JSONB)  # the complete AskResponse payload
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
