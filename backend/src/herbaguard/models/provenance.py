"""Sources, ingestion runs, raw source records, provenance links and data-quality issues.

Modelled on the W3C PROV concepts recommended by the organizers:
``SourceRecord`` ≈ prov:Entity (what was retrieved), ``IngestionRun`` ≈ prov:Activity
(what produced derived data), and ``Provenance`` links a derived row to both.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from herbaguard.domain.enums import IssueSeverity, LicenceStatus, RunStatus
from herbaguard.models.base import Base, created_at_column, enum_check, updated_at_column, uuid_pk


class Source(Base):
    """A data source (API, document collection or dataset) with its licence information."""

    __tablename__ = "source"
    __table_args__ = (enum_check("licence_status", LicenceStatus),)

    code: Mapped[str] = mapped_column(String(64), primary_key=True)  # e.g. "ema_hmpc", "wfo"
    name: Mapped[str] = mapped_column(String(255))
    provider: Mapped[str] = mapped_column(String(255))
    homepage_url: Mapped[str | None] = mapped_column(Text)
    access_method: Mapped[str] = mapped_column(String(64))  # api | download | web_page | pdf
    is_official: Mapped[bool] = mapped_column(default=True)  # False for hackathon wrappers
    licence: Mapped[str | None] = mapped_column(String(255))
    licence_url: Mapped[str | None] = mapped_column(Text)
    licence_status: Mapped[str] = mapped_column(String(16), default=LicenceStatus.TO_VERIFY.value)
    attribution: Mapped[str | None] = mapped_column(Text)
    redistributable: Mapped[bool] = mapped_column(default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class IngestionRun(Base):
    __tablename__ = "ingestion_run"
    __table_args__ = (enum_check("status", RunStatus),)

    id: Mapped[uuid.UUID] = uuid_pk()
    source_code: Mapped[str] = mapped_column(ForeignKey("source.code"), index=True)
    started_at: Mapped[datetime] = created_at_column()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default=RunStatus.RUNNING.value)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    statistics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    code_version: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)


class SourceRecord(Base):
    """One retrieved artefact (API response, PDF, spreadsheet) exactly as received.

    The raw bytes live on disk under ``raw_path``; ``content_sha256`` makes re-ingestion
    idempotent and detects upstream changes.
    """

    __tablename__ = "source_record"
    __table_args__ = (
        UniqueConstraint("source_code", "native_id", "content_sha256"),
        CheckConstraint("http_status IS NULL OR (http_status BETWEEN 100 AND 599)", "http_status"),
        Index("ix_source_record_source_native", "source_code", "native_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    source_code: Mapped[str] = mapped_column(ForeignKey("source.code"))
    ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ingestion_run.id", ondelete="SET NULL"), index=True
    )
    native_id: Mapped[str] = mapped_column(String(512))  # identifier in the source's own terms
    url: Mapped[str] = mapped_column(Text)
    request_parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    http_status: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(String(255))
    content_sha256: Mapped[str] = mapped_column(String(64))
    raw_path: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # small JSON responses only
    source_version: Mapped[str | None] = mapped_column(String(128))  # e.g. WFO "2026-06"
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Provenance(Base):
    """Links any derived row (``entity_table`` + ``entity_id``) to the record it came from.

    A polymorphic link keeps provenance uniform across all entity tables; the trade-off
    (no FK on ``entity_id``) is covered by data-validation tests.
    """

    __tablename__ = "provenance"
    __table_args__ = (
        UniqueConstraint("entity_table", "entity_id", "source_record_id", "extraction_method"),
        Index("ix_provenance_entity", "entity_table", "entity_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    entity_table: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64))  # UUID or natural key as text
    source_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_record.id", ondelete="CASCADE"), index=True
    )
    ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ingestion_run.id", ondelete="SET NULL")
    )
    extraction_method: Mapped[str] = mapped_column(String(128))  # e.g. "ema_pdf_section_v1"
    extraction_version: Mapped[str | None] = mapped_column(String(64))
    location: Mapped[str | None] = mapped_column(Text)  # page/section/JSON path within record
    verbatim_excerpt: Mapped[str | None] = mapped_column(Text)  # only if the licence permits
    created_at: Mapped[datetime] = created_at_column()

    source_record: Mapped[SourceRecord] = relationship()


class DataQualityIssue(Base):
    """Validation problems are recorded, not silently dropped."""

    __tablename__ = "data_quality_issue"
    __table_args__ = (enum_check("severity", IssueSeverity),)

    id: Mapped[uuid.UUID] = uuid_pk()
    ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ingestion_run.id", ondelete="CASCADE"), index=True
    )
    source_record_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_record.id", ondelete="CASCADE")
    )
    rule: Mapped[str] = mapped_column(String(128))
    severity: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(Text)
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = created_at_column()
