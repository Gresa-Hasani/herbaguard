"""Records of external research datasets (Phase 5 expansion; first dataset: DDID).

Generic by design, so further datasets (SUPP.AI, NaPDI, COCONUT, …) need no new tables:

* ``external_entity`` — an entity as a dataset defines it (herb, food, drug, natural product,
  target, …). All original columns are kept verbatim in ``attributes``; identifiers in other
  namespaces are copied to ``identifiers``. A mapping to a HerbaGuard entity is recorded only when
  it was established by an explicit rule (``mapping_method``); otherwise the entity stays
  ``unresolved`` or ``ambiguous`` for review. Nothing is mapped silently.
* ``external_relation`` — a relation between two external entities exactly as the dataset states
  it (e.g. herb contains natural product; drug has therapeutic target), with its attributes.
* ``experimental_observation`` — one experimental record (e.g. a herb–drug PK study arm) with the
  complete original row in ``original``, typed copies of the fields needed for queries, and
  *derived* fields in separate columns that never overwrite source values.

These tables never feed the deterministic A–E classification (``domain.interactions``): that
uses only ``interaction_assertion``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from herbaguard.domain.enums import EvidenceType
from herbaguard.models.base import Base, created_at_column, enum_check, updated_at_column, uuid_pk


class ExternalEntity(Base):
    __tablename__ = "external_entity"
    __table_args__ = (
        UniqueConstraint("source_code", "kind", "external_id"),
        Index("ix_external_entity_mapping", "mapped_table", "mapped_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    source_code: Mapped[str] = mapped_column(ForeignKey("source.code"))
    kind: Mapped[str] = mapped_column(
        String(32)
    )  # herb | food | drug | natural_product | ttd_target …
    external_id: Mapped[str] = mapped_column(String(128))
    label: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # original columns
    identifiers: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # namespace → value(s)
    mapping_status: Mapped[str] = mapped_column(
        String(16)
    )  # resolved|candidate|ambiguous|unresolved|not_applicable
    mapped_table: Mapped[str | None] = mapped_column(String(32))  # taxon | drug | target | …
    mapped_id: Mapped[uuid.UUID | None] = mapped_column()
    mapping_method: Mapped[str | None] = mapped_column(String(64))
    mapping_note: Mapped[str | None] = mapped_column(Text)
    source_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_record.id", ondelete="RESTRICT")
    )
    source_row_numbers: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class ExternalRelation(Base):
    __tablename__ = "external_relation"
    __table_args__ = (
        UniqueConstraint(
            "source_code", "subject_id", "predicate", "object_id", "attributes_sha256"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    source_code: Mapped[str] = mapped_column(ForeignKey("source.code"))
    subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("external_entity.id", ondelete="CASCADE"), index=True
    )
    predicate: Mapped[str] = mapped_column(
        String(64)
    )  # e.g. contains_natural_product, has_therapeutic_target
    object_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("external_entity.id", ondelete="CASCADE"), index=True
    )
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    attributes_sha256: Mapped[str] = mapped_column(String(64))
    source_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_record.id", ondelete="RESTRICT")
    )
    source_row_numbers: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)
    created_at: Mapped[datetime] = created_at_column()


class ExperimentalObservation(Base):
    __tablename__ = "experimental_observation"
    __table_args__ = (
        UniqueConstraint("source_code", "record_sha256"),
        enum_check("derived_evidence_type", EvidenceType),
        Index("ix_experimental_observation_pair", "interactant_entity_id", "drug_entity_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    source_code: Mapped[str] = mapped_column(ForeignKey("source.code"))
    record_sha256: Mapped[str] = mapped_column(String(64))  # hash of the complete original row
    original: Mapped[dict[str, Any]] = mapped_column(JSONB)  # every original column, verbatim
    interactant_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("external_entity.id", ondelete="RESTRICT")
    )
    drug_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("external_entity.id", ondelete="RESTRICT")
    )
    interactant_kind: Mapped[str] = mapped_column(
        String(16)
    )  # herb | food (as stated by the source)
    effect_label: Mapped[str] = mapped_column(String(32))  # verbatim source label, e.g. "Possible"
    species: Mapped[str | None] = mapped_column(
        String(64)
    )  # verbatim; None when the source says NA
    result: Mapped[str | None] = mapped_column(Text)
    conclusion: Mapped[str | None] = mapped_column(Text)
    pmid: Mapped[str | None] = mapped_column(String(16), index=True)
    doi: Mapped[str | None] = mapped_column(String(255))
    reference: Mapped[str | None] = mapped_column(Text)
    target_accessions: Mapped[list[str]] = mapped_column(
        ARRAY(String(16)), default=list
    )  # as stated (UniProt)
    mapped_target_ids: Mapped[list[str]] = mapped_column(ARRAY(String(36)), default=list)
    # Derived (never overwrites the fields above); rule version in derivation_rule.
    derived_study_context: Mapped[str] = mapped_column(String(16))  # human | animal | unknown
    derived_evidence_type: Mapped[str] = mapped_column(String(8))  # CLIN | ANIMAL | OTHER
    derivation_rule: Mapped[str] = mapped_column(String(64))
    evidence_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evidence_item.id", ondelete="SET NULL"), index=True
    )
    source_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_record.id", ondelete="RESTRICT")
    )
    source_row_numbers: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
