"""Plant taxa, their names, and herbal substances (taxon + plant part)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from herbaguard.domain.enums import NameType
from herbaguard.models.base import Base, created_at_column, enum_check, updated_at_column, uuid_pk


class Taxon(Base):
    """An accepted plant taxon. ``wfo_id`` (e.g. ``wfo-0000728093``) is the primary identifier,
    as recommended by the organizers; other backbone identifiers are cross-references."""

    __tablename__ = "taxon"
    __table_args__ = (CheckConstraint(r"wfo_id ~ '^wfo-[0-9]{10}$'", "wfo_id_format"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    wfo_id: Mapped[str] = mapped_column(String(16), unique=True)
    scientific_name: Mapped[str] = mapped_column(String(255), index=True)  # without authors
    authorship: Mapped[str | None] = mapped_column(String(255))
    family: Mapped[str | None] = mapped_column(String(128))
    rank: Mapped[str] = mapped_column(String(32), default="species")
    taxonomic_status: Mapped[str] = mapped_column(String(32), default="accepted")
    # Cross-references; nullable because not every backbone covers every taxon.
    ipni_id: Mapped[str | None] = mapped_column(String(32), index=True)
    wcvp_plant_name_id: Mapped[int | None] = mapped_column(index=True)
    gbif_key: Mapped[int | None] = mapped_column(index=True)
    ncbi_tax_id: Mapped[int | None] = mapped_column(index=True)
    powo_id: Mapped[str | None] = mapped_column(String(64))
    wikidata_id: Mapped[str | None] = mapped_column(String(32))
    native_range: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    names: Mapped[list[TaxonName]] = relationship(back_populates="taxon")
    herbal_substances: Mapped[list[HerbalSubstance]] = relationship(back_populates="taxon")


class TaxonName(Base):
    """Any name string that resolves to a taxon: accepted, synonym, common or pharmaceutical.

    ``taxon_id`` may be NULL for names seen in a source that could not (yet) be resolved;
    those must never be guessed.
    """

    __tablename__ = "taxon_name"
    __table_args__ = (
        enum_check("name_type", NameType),
        UniqueConstraint(
            "normalized_name",
            "name_type",
            "language",
            "taxon_id",
            "source_code",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_taxon_name_normalized", "normalized_name"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    taxon_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("taxon.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(512))
    normalized_name: Mapped[str] = mapped_column(String(512))  # lower-case, collapsed spaces
    name_type: Mapped[str] = mapped_column(String(16))
    language: Mapped[str | None] = mapped_column(String(8))  # BCP-47, e.g. "en", "la"
    source_code: Mapped[str] = mapped_column(ForeignKey("source.code"))
    source_native_id: Mapped[str | None] = mapped_column(String(128))  # e.g. WFO id of a synonym
    created_at: Mapped[datetime] = created_at_column()

    taxon: Mapped[Taxon | None] = relationship(back_populates="names")


class HerbalSubstance(Base):
    """A taxon + plant part as used in medicine, e.g. *Hyperici herba* (aerial parts of
    *Hypericum perforatum*). Regulatory statements apply to substances, not to taxa."""

    __tablename__ = "herbal_substance"
    __table_args__ = (UniqueConstraint("taxon_id", "plant_part"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    taxon_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("taxon.id", ondelete="RESTRICT"))
    plant_part: Mapped[str] = mapped_column(String(64))  # e.g. "herba", "radix", "folium"
    plant_part_ontology_id: Mapped[str | None] = mapped_column(String(32))  # e.g. PO:0009006
    pharmaceutical_name: Mapped[str | None] = mapped_column(String(255), index=True)
    common_name_en: Mapped[str | None] = mapped_column(String(255))
    ema_url: Mapped[str | None] = mapped_column(Text)
    ema_outcome: Mapped[str | None] = mapped_column(String(128))  # e.g. "EU herbal monograph"
    in_curated_scope: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    taxon: Mapped[Taxon] = relationship(back_populates="herbal_substances")
