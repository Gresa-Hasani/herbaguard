"""Mechanism edges: enzymes/transporters, herb effects and drug roles (Phase 4)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from herbaguard.models import (
    Constituent,
    Drug,
    DrugTargetRoleLink,
    EvidenceItem,
    HerbalSubstance,
    HerbalSubstanceConstituent,
    Target,
    TargetModulation,
)


@dataclass(frozen=True, slots=True)
class EffectRow:
    modulation: TargetModulation
    target: Target
    evidence: EvidenceItem | None
    subject_kind: str  # "herbal_substance" | "constituent"
    subject_label: str  # pharmaceutical name or constituent name
    herbal_substance_id: (
        uuid.UUID
    )  # the substance the effect was found for (directly or via constituent)


@dataclass(frozen=True, slots=True)
class RoleRow:
    role: DrugTargetRoleLink
    target: Target
    drug: Drug
    evidence: EvidenceItem | None


def herb_effects(session: Session, substance_ids: list[uuid.UUID]) -> list[EffectRow]:
    """Effects stated for these substances, and for constituents linked to them."""
    if not substance_ids:
        return []
    out: list[EffectRow] = []
    direct = session.execute(
        select(TargetModulation, Target, EvidenceItem, HerbalSubstance.pharmaceutical_name)
        .join(Target, Target.id == TargetModulation.target_id)
        .join(HerbalSubstance, HerbalSubstance.id == TargetModulation.herbal_substance_id)
        .outerjoin(EvidenceItem, EvidenceItem.id == TargetModulation.evidence_item_id)
        .where(TargetModulation.herbal_substance_id.in_(substance_ids))
    ).all()
    for modulation, target, evidence, name in direct:
        assert modulation.herbal_substance_id is not None  # noqa: S101 - filtered above
        substance_id = modulation.herbal_substance_id
        out.append(
            EffectRow(modulation, target, evidence, "herbal_substance", name or "", substance_id)
        )
    via_constituent = session.execute(
        select(
            TargetModulation,
            Target,
            EvidenceItem,
            Constituent.name,
            HerbalSubstanceConstituent.herbal_substance_id,
        )
        .join(Target, Target.id == TargetModulation.target_id)
        .join(Constituent, Constituent.id == TargetModulation.constituent_id)
        .join(
            HerbalSubstanceConstituent,
            HerbalSubstanceConstituent.constituent_id == Constituent.id,
        )
        .outerjoin(EvidenceItem, EvidenceItem.id == TargetModulation.evidence_item_id)
        .where(HerbalSubstanceConstituent.herbal_substance_id.in_(substance_ids))
    ).all()
    for modulation, target, evidence, name, substance_id in via_constituent:
        out.append(EffectRow(modulation, target, evidence, "constituent", name, substance_id))
    return out


def drug_roles(
    session: Session, *, drug_id: uuid.UUID | None = None, target_ids: list[uuid.UUID] | None = None
) -> list[RoleRow]:
    stmt = (
        select(DrugTargetRoleLink, Target, Drug, EvidenceItem)
        .join(Target, Target.id == DrugTargetRoleLink.target_id)
        .join(Drug, Drug.id == DrugTargetRoleLink.drug_id)
        .outerjoin(EvidenceItem, EvidenceItem.id == DrugTargetRoleLink.evidence_item_id)
    )
    if drug_id is not None:
        stmt = stmt.where(DrugTargetRoleLink.drug_id == drug_id)
    if target_ids is not None:
        stmt = stmt.where(DrugTargetRoleLink.target_id.in_(target_ids))
    rows = session.execute(stmt.order_by(Drug.name, Target.symbol, DrugTargetRoleLink.role)).all()
    return [RoleRow(*row) for row in rows]


def targets_with_counts(session: Session) -> list[tuple[Target, int, int]]:
    """Every target with its number of herb effects and drug roles."""
    effects = (
        select(TargetModulation.target_id, func.count().label("n"))
        .group_by(TargetModulation.target_id)
        .subquery()
    )
    roles = (
        select(DrugTargetRoleLink.target_id, func.count().label("n"))
        .group_by(DrugTargetRoleLink.target_id)
        .subquery()
    )
    rows = session.execute(
        select(Target, func.coalesce(effects.c.n, 0), func.coalesce(roles.c.n, 0))
        .outerjoin(effects, effects.c.target_id == Target.id)
        .outerjoin(roles, roles.c.target_id == Target.id)
        .order_by(Target.target_type, Target.symbol)
    ).all()
    return [(t, int(e), int(r)) for t, e, r in rows]


def targets_by_symbols(session: Session, symbols: list[str]) -> list[Target]:
    if not symbols:
        return []
    return list(session.scalars(select(Target).where(Target.symbol.in_(symbols))))


def get_target(session: Session, symbol: str) -> Target | None:
    return session.scalar(select(Target).where(func.upper(Target.symbol) == symbol.upper()))


def effects_on_targets(session: Session, target_ids: list[uuid.UUID]) -> list[EffectRow]:
    """Herb (and constituent) effects on these targets, for the target detail view."""
    if not target_ids:
        return []
    substance_ids = list(
        session.scalars(
            select(TargetModulation.herbal_substance_id).where(
                TargetModulation.target_id.in_(target_ids),
                TargetModulation.herbal_substance_id.is_not(None),
            )
        )
    )
    constituent_substances = list(
        session.scalars(
            select(HerbalSubstanceConstituent.herbal_substance_id)
            .join(
                TargetModulation,
                TargetModulation.constituent_id == HerbalSubstanceConstituent.constituent_id,
            )
            .where(TargetModulation.target_id.in_(target_ids))
        )
    )
    ids = list({i for i in [*substance_ids, *constituent_substances] if i is not None})
    wanted = set(target_ids)
    return [e for e in herb_effects(session, ids) if e.target.id in wanted]


def substances_by_ids(session: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, HerbalSubstance]:
    if not ids:
        return {}
    return {
        s.id: s for s in session.scalars(select(HerbalSubstance).where(HerbalSubstance.id.in_(ids)))
    }


def edge_counts(session: Session) -> dict[str, int]:
    return {
        "targets": session.scalar(select(func.count()).select_from(Target)) or 0,
        "herb_effects": session.scalar(select(func.count()).select_from(TargetModulation)) or 0,
        "drug_roles": session.scalar(select(func.count()).select_from(DrugTargetRoleLink)) or 0,
    }


def fda_table_item(session: Session) -> EvidenceItem | None:
    return session.scalar(
        select(EvidenceItem)
        .where(EvidenceItem.source_code == "fda_cyp_table")
        .order_by(EvidenceItem.document_date.desc().nulls_last())
        .limit(1)
    )


def has_any_role(session: Session, drug_id: uuid.UUID) -> bool:
    return bool(
        session.scalar(
            select(func.count())
            .select_from(DrugTargetRoleLink)
            .where(DrugTargetRoleLink.drug_id == drug_id)
        )
    )
