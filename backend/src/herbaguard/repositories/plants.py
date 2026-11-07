"""Taxa, names and herbal substances.

A *herb* in the API is the group of curated herbal substances that share an EMA pharmaceutical
name (e.g. "Crataegi folium cum flore" groups four *Crataegus* species). This is the unit that
regulatory statements apply to.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from herbaguard.domain.name_overrides import OVERRIDES
from herbaguard.ingestion.normalize.names import normalize_for_lookup
from herbaguard.models import HerbalSubstance, Taxon, TaxonName

# Higher = better name match type when ranking search results.
NAME_TYPE_RANK = {"accepted": 4, "pharmaceutical": 3, "common": 2, "synonym": 1}


@dataclass(frozen=True, slots=True)
class NameMatch:
    taxon_id: uuid.UUID
    name: str
    name_type: str
    source_code: str
    exact: bool


def match_names(
    session: Session, query: str, *, exact_only: bool = False, limit: int = 200
) -> list[NameMatch]:
    """Name rows matching a query (exact normalised match, else substring), best first."""
    key = normalize_for_lookup(query)
    if not key:
        return []
    condition = TaxonName.normalized_name == key
    if not exact_only:
        escaped = key.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        condition = or_(condition, TaxonName.normalized_name.like(f"%{escaped}%", escape="\\"))
    exact = TaxonName.normalized_name == key
    prefix = TaxonName.normalized_name.like(f"{key}%")
    rank = case((exact, 0), (prefix, 1), else_=2)
    rows = session.execute(
        select(
            TaxonName.taxon_id,
            TaxonName.name,
            TaxonName.name_type,
            TaxonName.source_code,
            exact,
            TaxonName.normalized_name,
            Taxon.scientific_name,
        )
        .join(Taxon, Taxon.id == TaxonName.taxon_id)
        .where(condition, TaxonName.taxon_id.is_not(None))
        .order_by(rank, func.length(TaxonName.normalized_name))
        .limit(limit)
    ).all()
    return [
        NameMatch(r[0], r[1], r[2], r[3], bool(r[4]))
        for r in rows
        if r[0] is not None and not excluded_by_override(r[5], r[6])
    ]


def excluded_by_override(normalized_name: str, scientific_name: str) -> bool:
    """True if a reviewed override says this name row must not identify this taxon
    (``domain.name_overrides``; the stored row is kept)."""
    override = OVERRIDES.get(normalized_name)
    return (
        override is not None
        and override.action == "not_this_taxon"
        and scientific_name in override.excluded_taxa
    )


def search_taxa(
    session: Session, query: str | None, *, limit: int, offset: int
) -> tuple[list[tuple[Taxon, NameMatch | None]], int]:
    """Taxa for the plant explorer; without a query all taxa ordered by name."""
    if not query:
        total = session.scalar(select(func.count()).select_from(Taxon)) or 0
        taxa = session.scalars(
            select(Taxon).order_by(Taxon.scientific_name).limit(limit).offset(offset)
        ).all()
        return [(t, None) for t in taxa], total
    best: dict[uuid.UUID, NameMatch] = {}
    for match in match_names(session, query):
        current = best.get(match.taxon_id)
        if current is None or (match.exact, NAME_TYPE_RANK[match.name_type]) > (
            current.exact,
            NAME_TYPE_RANK[current.name_type],
        ):
            best[match.taxon_id] = match
    ordered = sorted(
        best.values(), key=lambda m: (not m.exact, -NAME_TYPE_RANK[m.name_type], m.name)
    )
    page = ordered[offset : offset + limit]
    by_id = {
        t.id: t
        for t in session.scalars(select(Taxon).where(Taxon.id.in_([m.taxon_id for m in page])))
    }
    return [(by_id[m.taxon_id], m) for m in page], len(ordered)


def get_taxon(session: Session, wfo_id: str) -> Taxon | None:
    return session.scalar(select(Taxon).where(Taxon.wfo_id == wfo_id))


def names_for_taxon(session: Session, taxon_id: uuid.UUID) -> list[TaxonName]:
    return list(
        session.scalars(
            select(TaxonName)
            .where(TaxonName.taxon_id == taxon_id)
            .order_by(TaxonName.name_type, TaxonName.name)
        )
    )


def substances_for_taxa(session: Session, taxon_ids: list[uuid.UUID]) -> list[HerbalSubstance]:
    return list(
        session.scalars(
            select(HerbalSubstance).where(
                HerbalSubstance.taxon_id.in_(taxon_ids), HerbalSubstance.in_curated_scope.is_(True)
            )
        )
    )


def herb_group(session: Session, pharmaceutical_name: str) -> list[HerbalSubstance]:
    """All curated substances sharing an EMA pharmaceutical name."""
    return list(
        session.scalars(
            select(HerbalSubstance)
            .where(
                HerbalSubstance.pharmaceutical_name == pharmaceutical_name,
                HerbalSubstance.in_curated_scope.is_(True),
            )
            .order_by(HerbalSubstance.id)
        )
    )


def taxa_by_ids(session: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, Taxon]:
    return {t.id: t for t in session.scalars(select(Taxon).where(Taxon.id.in_(ids)))}
