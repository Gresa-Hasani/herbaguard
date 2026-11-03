"""Drugs, drug classes, constituents, targets and the mechanism edges between them.

These tables are HerbaGuard's knowledge graph (Neo4j is deferred — see
``docs/architecture/decisions.md``, ADR-002). Every edge row is backed by provenance.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from herbaguard.domain.enums import (
    DrugTargetRole,
    EvidenceType,
    ModulationEffect,
    Potency,
    TargetType,
)
from herbaguard.models.base import Base, created_at_column, enum_check, updated_at_column, uuid_pk


class Drug(Base):
    """A drug at RxNorm ingredient level (TTY ``IN``), e.g. warfarin → RxCUI 11289."""

    __tablename__ = "drug"

    id: Mapped[uuid.UUID] = uuid_pk()
    rxcui: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    rxnorm_tty: Mapped[str] = mapped_column(String(8), default="IN")
    unii: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class DrugClass(Base):
    """A drug class, normally an ATC code (e.g. ``B01AA`` vitamin K antagonists)."""

    __tablename__ = "drug_class"
    __table_args__ = (CheckConstraint("level BETWEEN 1 AND 5", "level_range"),)

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    system: Mapped[str] = mapped_column(String(16), default="ATC")
    name: Mapped[str] = mapped_column(String(255))
    level: Mapped[int] = mapped_column(Integer)


class DrugClassMembership(Base):
    __tablename__ = "drug_class_membership"

    drug_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("drug.id", ondelete="CASCADE"), primary_key=True
    )
    drug_class_code: Mapped[str] = mapped_column(
        ForeignKey("drug_class.code", ondelete="CASCADE"), primary_key=True
    )
    source_code: Mapped[str] = mapped_column(ForeignKey("source.code"))


class Constituent(Base):
    """A chemical constituent. InChIKey is the join key across ChEBI, PubChem and COCONUT."""

    __tablename__ = "constituent"
    __table_args__ = (
        CheckConstraint(r"inchikey ~ '^[A-Z]{14}-[A-Z]{10}-[A-Z]$'", "inchikey_format"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    inchikey: Mapped[str] = mapped_column(String(27), unique=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    chebi_id: Mapped[str | None] = mapped_column(String(32))  # e.g. "CHEBI:5834"
    pubchem_cid: Mapped[int | None] = mapped_column(Integer)
    molecular_formula: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = created_at_column()


class HerbalSubstanceConstituent(Base):
    __tablename__ = "herbal_substance_constituent"

    herbal_substance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("herbal_substance.id", ondelete="CASCADE"), primary_key=True
    )
    constituent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("constituent.id", ondelete="CASCADE"), primary_key=True
    )
    is_marker: Mapped[bool] = mapped_column(default=False)  # named in the monograph
    source_code: Mapped[str] = mapped_column(ForeignKey("source.code"))


class Target(Base):
    """An enzyme, transporter or receptor, e.g. CYP3A4 (UniProt P08684), P-gp (P08183)."""

    __tablename__ = "target"
    __table_args__ = (enum_check("target_type", TargetType),)

    id: Mapped[uuid.UUID] = uuid_pk()
    uniprot_accession: Mapped[str | None] = mapped_column(String(16), unique=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True)  # e.g. "CYP3A4", "ABCB1"
    name: Mapped[str] = mapped_column(String(255))
    target_type: Mapped[str] = mapped_column(String(16))


class TargetModulation(Base):
    """Herbal substance (or constituent) induces/inhibits a target — one premise of class B.

    Phase 4: ``evidence_item_id`` names the citable unit the statement comes from (e.g. EMA
    monograph section 4.5 for one use category, or the FDA CYP/transporter table), and
    ``potency`` relays the source's own strength category (FDA: strong / moderate / weak).
    """

    __tablename__ = "target_modulation"
    __table_args__ = (
        enum_check("effect", ModulationEffect),
        enum_check("evidence_type", EvidenceType),
        enum_check("potency", Potency),
        CheckConstraint(
            "(herbal_substance_id IS NOT NULL) <> (constituent_id IS NOT NULL)",
            "exactly_one_subject",
        ),
        UniqueConstraint(
            "herbal_substance_id",
            "constituent_id",
            "target_id",
            "effect",
            "source_code",
            "evidence_item_id",
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    herbal_substance_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("herbal_substance.id", ondelete="CASCADE"), index=True
    )
    constituent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("constituent.id", ondelete="CASCADE"), index=True
    )
    target_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("target.id", ondelete="CASCADE"))
    effect: Mapped[str] = mapped_column(String(16))
    evidence_type: Mapped[str] = mapped_column(String(8))  # EvidenceType value
    conditions: Mapped[str | None] = mapped_column(Text)  # e.g. dose threshold wording
    source_code: Mapped[str] = mapped_column(ForeignKey("source.code"))
    potency: Mapped[str | None] = mapped_column(String(16))  # Potency value, as stated
    # Modal word before the effect verb in the source ("may", "might"); NULL = stated plainly.
    hedge_wording: Mapped[str | None] = mapped_column(String(32))  # migration 0004
    evidence_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evidence_item.id", ondelete="CASCADE"), index=True
    )


class DrugTargetRoleLink(Base):
    """Drug is a substrate/inhibitor/inducer of a target — the other premise of class B.

    Phase 4: ``potency`` (inhibitors/inducers: strong / moderate / weak, as stated by the
    source), ``conditions`` (source footnotes, e.g. "S-warfarin") and ``evidence_item_id``.
    """

    __tablename__ = "drug_target_role"
    __table_args__ = (
        enum_check("role", DrugTargetRole),
        enum_check("potency", Potency),
        UniqueConstraint("drug_id", "target_id", "role", "source_code"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    drug_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("drug.id", ondelete="CASCADE"), index=True
    )
    target_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("target.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(32))
    source_code: Mapped[str] = mapped_column(ForeignKey("source.code"))
    potency: Mapped[str | None] = mapped_column(String(16))
    conditions: Mapped[str | None] = mapped_column(Text)
    evidence_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evidence_item.id", ondelete="CASCADE"), index=True
    )
