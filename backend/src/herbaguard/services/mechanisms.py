"""Mechanism layer services: paths for a herb–drug pair, targets, herb mechanism graphs."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from herbaguard.api.schemas.common import Page
from herbaguard.api.schemas.mechanism_core import (
    ROLE_LABELS,
    DrugRef,
    DrugRoleOut,
    HerbEffectOut,
    MechanismAssessmentOut,
    MechanismPathOut,
    TargetOut,
    TargetRef,
)
from herbaguard.api.schemas.mechanisms import (
    GraphEdge,
    GraphNode,
    HerbDrugPair,
    HerbDrugPairs,
    HerbMechanismGraph,
    MechanismPathsResponse,
    TargetDetail,
)
from herbaguard.api.schemas.provenance import EvidenceTypeInfo
from herbaguard.core.config import DISCLAIMER, Settings
from herbaguard.core.errors import AmbiguousEntityError, NotFoundError
from herbaguard.domain.enums import SUBSTRATE_ROLES
from herbaguard.domain.interactions import MechanismPath
from herbaguard.domain.mechanisms import (
    MATCH_GROUP,
    MECHANISM_CAVEAT,
    RULES_VERSION,
    AssessedPath,
    DrugRole,
    HerbEffect,
    MechanismAssessment,
    assess_mechanism,
    assess_paths,
    describe,
)
from herbaguard.models import Target
from herbaguard.repositories import drugs as drug_repo
from herbaguard.repositories import evidence as evidence_repo
from herbaguard.repositories import mechanisms as repo
from herbaguard.repositories import plants as plant_repo
from herbaguard.services import drugs as drug_service
from herbaguard.services import plants as plant_service
from herbaguard.services.mappers import evidence_ref, provenance_out

UNIPROT_URL = "https://www.uniprot.org/uniprotkb/{}/entry"
GRAPH_DRUG_LIMIT = 200
PATHS_NOTE = (
    "A path joins a stored herb effect with a stored drug role on the same enzyme or transporter. "
    "Paths that do not qualify are shown for transparency and are never used for classification."
)


def target_ref(target: Target) -> TargetRef:
    return TargetRef(symbol=target.symbol, name=target.name, target_type=target.target_type)


def target_out(target: Target, effects: int, roles: int) -> TargetOut:
    return TargetOut(
        symbol=target.symbol,
        name=target.name,
        target_type=target.target_type,
        uniprot_accession=target.uniprot_accession,
        uniprot_url=UNIPROT_URL.format(target.uniprot_accession)
        if target.uniprot_accession
        else None,
        herb_effects=effects,
        drug_roles=roles,
    )


def _effects_out(session: Session, rows: Sequence[repo.EffectRow]) -> list[HerbEffectOut]:
    provenance = evidence_repo.provenance_for(
        session, "target_modulation", [str(r.modulation.id) for r in rows]
    )
    substances = repo.substances_by_ids(session, [r.herbal_substance_id for r in rows])
    out = []
    for row in rows:
        m = row.modulation
        substance = substances.get(row.herbal_substance_id)
        out.append(
            HerbEffectOut(
                id=str(m.id),
                herb=(substance.pharmaceutical_name or "") if substance else "",
                subject_kind=row.subject_kind,
                subject_label=row.subject_label,
                target=target_ref(row.target),
                effect=m.effect,
                potency=m.potency,
                hedge_wording=m.hedge_wording,
                evidence_type=EvidenceTypeInfo.of(m.evidence_type, m.source_code),
                source_code=m.source_code,
                conditions=m.conditions,
                evidence=evidence_ref(row.evidence) if row.evidence else None,
                provenance=[provenance_out(p) for p in provenance.get(str(m.id), [])],
            )
        )
    return out


def _roles_out(session: Session, rows: Sequence[repo.RoleRow]) -> list[DrugRoleOut]:
    provenance = evidence_repo.provenance_for(
        session, "drug_target_role", [str(r.role.id) for r in rows]
    )
    return [
        DrugRoleOut(
            id=str(r.role.id),
            drug=DrugRef(rxcui=r.drug.rxcui, name=r.drug.name),
            target=target_ref(r.target),
            role=r.role.role,
            role_label=ROLE_LABELS.get(r.role.role, r.role.role),
            potency=r.role.potency,
            conditions=r.role.conditions,
            source_code=r.role.source_code,
            evidence=evidence_ref(r.evidence) if r.evidence else None,
            provenance=[provenance_out(p) for p in provenance.get(str(r.role.id), [])],
        )
        for r in rows
    ]


def _domain_effect(row: repo.EffectRow) -> HerbEffect:
    m = row.modulation
    return HerbEffect(
        id=str(m.id),
        target_symbol=row.target.symbol,
        effect=m.effect,
        potency=m.potency,
        evidence_type=m.evidence_type,
        source_code=m.source_code,
        subject_kind=row.subject_kind,
        subject_label=row.subject_label,
        conditions=m.conditions,
        hedge=m.hedge_wording,
    )


def _domain_role(row: repo.RoleRow) -> DrugRole:
    r = row.role
    return DrugRole(
        id=str(r.id),
        target_symbol=row.target.symbol,
        role=r.role,
        potency=r.potency,
        source_code=r.source_code,
        conditions=r.conditions,
    )


def assessment_out(
    assessment: MechanismAssessment, *, herb_effects: int, drug_roles: int
) -> MechanismAssessmentOut:
    return MechanismAssessmentOut(
        finding=assessment.finding.value,
        label=assessment.label,
        explanation=assessment.explanation,
        paths_total=assessment.paths_total,
        qualifying_paths=assessment.qualifying_paths,
        herb_effects_stored=herb_effects,
        drug_roles_stored=drug_roles,
        rules=RULES_VERSION,
    )


def not_assessed() -> MechanismAssessmentOut:
    """For a pair whose herb or drug is not identified."""
    result = assess_mechanism(
        herb_resolved=False,
        drug_resolved=False,
        herb_effects_stored=0,
        drug_roles_stored=0,
        paths=[],
    )
    return assessment_out(result, herb_effects=0, drug_roles=0)


def paths_for_pair(
    session: Session, substance_ids: list[uuid.UUID], drug_id: uuid.UUID
) -> tuple[list[MechanismPath], list[MechanismPathOut], MechanismAssessmentOut]:
    """All assessed paths for a herb–drug pair: the qualifying ones as domain input for
    ``classify``, every path for the API response, and the pair's mechanism finding."""
    effect_rows = repo.herb_effects(session, substance_ids)
    role_rows = repo.drug_roles(session, drug_id=drug_id)
    return _pair(session, effect_rows, role_rows)


def _pair(
    session: Session, effect_rows: Sequence[repo.EffectRow], role_rows: Sequence[repo.RoleRow]
) -> tuple[list[MechanismPath], list[MechanismPathOut], MechanismAssessmentOut]:
    """A herb with several species (e.g. hawthorn) has one effect row per substance; paths are
    de-duplicated on (source statement wording, target, effect, drug role)."""
    distinct_effects = {
        (r.subject_label, r.target.symbol, r.modulation.effect, r.modulation.source_code,
         r.modulation.evidence_item_id)
        for r in effect_rows
    }  # fmt: skip

    def finish(
        unique: list[AssessedPath], api: list[MechanismPathOut]
    ) -> tuple[list[MechanismPath], list[MechanismPathOut], MechanismAssessmentOut]:
        assessment = assess_mechanism(
            herb_resolved=True,
            drug_resolved=True,
            herb_effects_stored=len(distinct_effects),
            drug_roles_stored=len(role_rows),
            paths=unique,
        )
        domain = [
            MechanismPath(
                target_symbol=p.target_symbols,
                herb_effect=p.herb.effect,
                drug_role=p.drug.role,
                source=f"{p.herb.source_code} + {p.drug.source_code}",
                description=describe(p),
            )
            for p in unique
            if p.qualifies
        ]
        out = assessment_out(
            assessment, herb_effects=len(distinct_effects), drug_roles=len(role_rows)
        )
        return domain, api, out

    if not effect_rows or not role_rows:
        return finish([], [])
    effects_by_id = {str(r.modulation.id): r for r in effect_rows}
    roles_by_id = {str(r.role.id): r for r in role_rows}
    assessed = assess_paths(
        [_domain_effect(r) for r in effect_rows], [_domain_role(r) for r in role_rows]
    )
    unique: list[AssessedPath] = []
    seen: set[tuple[object, ...]] = set()
    for path in assessed:
        key = (
            path.herb.subject_label,
            path.herb.target_symbol,
            path.herb.effect,
            path.herb.source_code,
            path.herb.conditions,
            effects_by_id[path.herb.id].modulation.evidence_item_id,
            path.drug.id,
        )
        if key not in seen:
            seen.add(key)
            unique.append(path)
    effects_out = {
        e.id: e for e in _effects_out(session, [effects_by_id[p.herb.id] for p in unique])
    }
    roles_out = {r.id: r for r in _roles_out(session, [roles_by_id[p.drug.id] for p in unique])}
    api = [
        MechanismPathOut(
            target_symbols=p.target_symbols,
            herb_effect=effects_out[p.herb.id],
            drug_role=roles_out[p.drug.id],
            qualifies_for_class_b=p.qualifies,
            reasons_not_qualifying=list(p.reasons_not_qualifying),
            conflicting=p.conflicting,
            experimental=p.experimental,
            description=describe(p),
        )
        for p in unique
    ]
    return finish(unique, api)


# --------------------------------------------------------------------------- endpoints


def list_targets(session: Session) -> list[TargetOut]:
    return [target_out(t, e, r) for t, e, r in repo.targets_with_counts(session)]


def target_detail(session: Session, symbol: str, *, role: str | None, limit: int) -> TargetDetail:
    target = repo.get_target(session, symbol)
    if target is None:
        raise NotFoundError(f"No enzyme or transporter with symbol {symbol}.")
    counts = {t.id: (e, r) for t, e, r in repo.targets_with_counts(session)}
    effects, roles = counts.get(target.id, (0, 0))
    role_rows = repo.drug_roles(session, target_ids=[target.id])
    if role:
        role_rows = [r for r in role_rows if r.role.role == role]
    return TargetDetail(
        **target_out(target, effects, roles).model_dump(),
        herb_effect_statements=_effects_out(session, repo.effects_on_targets(session, [target.id])),
        drug_role_statements=_roles_out(session, role_rows[:limit]),
        drug_roles_total=len(role_rows),
        note="FDA lists examples, not every drug that uses this enzyme or transporter. A drug that is "
        "not listed may still be affected.",
    )


def herb_graph(session: Session, wfo_id: str, *, include_drugs: bool) -> HerbMechanismGraph:
    taxon = plant_repo.get_taxon(session, wfo_id)
    if taxon is None:
        raise NotFoundError(f"No plant with WFO ID {wfo_id}.")
    substances = plant_repo.substances_for_taxa(session, [taxon.id])
    if not substances:
        raise NotFoundError(f"No herbal substance for {wfo_id}.")
    herb = plant_service.herb_ref(substances[0])
    group = plant_repo.herb_group(session, substances[0].pharmaceutical_name or "")
    effect_rows = repo.herb_effects(session, [s.id for s in group] or [s.id for s in substances])
    effects = _effects_out(session, effect_rows)

    herb_id = f"herb:{herb.pharmaceutical_name}"
    nodes: dict[str, GraphNode] = {
        herb_id: GraphNode(id=herb_id, kind="herb", label=herb.pharmaceutical_name)
    }
    edges: dict[str, GraphEdge] = {}
    for row, out in zip(effect_rows, effects, strict=True):
        target_id = f"target:{row.target.symbol}"
        nodes[target_id] = GraphNode(
            id=target_id,
            kind="target",
            label=row.target.symbol,
            data={"name": row.target.name, "type": row.target.target_type},
        )
        source = herb_id
        if row.subject_kind == "constituent":
            source = f"constituent:{row.subject_label}"
            nodes[source] = GraphNode(id=source, kind="constituent", label=row.subject_label)
            contains = f"{herb_id}->{source}"
            edges.setdefault(
                contains,
                GraphEdge(
                    id=contains, source=herb_id, target=source, kind="contains", label="contains",
                    statement_ids=[],
                ),
            )  # fmt: skip
        edge_id = f"{source}-{out.effect}->{target_id}#{out.source_code}#{out.evidence_type.code}"
        edge = edges.get(edge_id)
        if edge is None:
            label = f"{out.effect}{f' ({out.potency})' if out.potency else ''} [{out.source_code}]"
            edge = GraphEdge(
                id=edge_id,
                source=source,
                target=target_id,
                kind=out.effect if out.effect in ("induces", "inhibits", "activates") else "other",
                label=label,
                evidence_type=out.evidence_type.code.value,
                statement_ids=[],
            )
            edges[edge_id] = edge
        edge.statement_ids.append(out.id)

    truncated = False
    if include_drugs and effect_rows:
        target_ids = list({row.target.id for row in effect_rows})
        targets = (
            repo.targets_by_symbols(session, ["CYP3A"])
            if any(row.target.symbol in ("CYP3A4", "CYP3A5") for row in effect_rows)
            else []
        )
        target_ids += [t.id for t in targets if t.id not in target_ids]
        role_rows = [
            r
            for r in repo.drug_roles(session, target_ids=target_ids)
            if r.role.role in SUBSTRATE_ROLES
        ]
        truncated = len(role_rows) > GRAPH_DRUG_LIMIT
        for r in role_rows[:GRAPH_DRUG_LIMIT]:
            target_id = f"target:{r.target.symbol}"
            nodes.setdefault(
                target_id,
                GraphNode(id=target_id, kind="target", label=r.target.symbol,
                          data={"name": r.target.name, "type": r.target.target_type}),
            )  # fmt: skip
            drug_id = f"drug:{r.drug.rxcui}"
            nodes[drug_id] = GraphNode(
                id=drug_id, kind="drug", label=r.drug.name, data={"rxcui": r.drug.rxcui}
            )
            edge_id = f"{drug_id}-substrate_of->{target_id}"
            edges.setdefault(
                edge_id,
                GraphEdge(id=edge_id, source=drug_id, target=target_id, kind="substrate_of",
                          label=ROLE_LABELS.get(r.role.role, r.role.role), statement_ids=[]),
            ).statement_ids.append(str(r.role.id))  # fmt: skip
    for symbol, group_symbol in MATCH_GROUP.items():
        member, grouped = f"target:{symbol}", f"target:{group_symbol}"
        if member in nodes and grouped in nodes:
            edge_id = f"{member}-grouped_as->{grouped}"
            edges[edge_id] = GraphEdge(
                id=edge_id,
                source=member,
                target=grouped,
                kind="grouped_as",
                label=f"{symbol} is part of FDA's grouped {group_symbol}",
                statement_ids=[],
            )
    return HerbMechanismGraph(
        herb=herb,
        nodes=list(nodes.values()),
        edges=list(edges.values()),
        herb_effects=effects,
        drugs_truncated=truncated,
        note="Graph of stored statements only. An edge is not a prediction: herb → enzyme edges come from "
        "regulatory or government sources (or are labelled with their study type); drug → enzyme edges from "
        "the FDA table. Constituent effects are context and do not show that the herbal preparation has them.",
        rules=RULES_VERSION,
    )


def paths(
    session: Session, settings: Settings, *, herb_query: str, drug_query: str, allow_remote: bool
) -> MechanismPathsResponse:
    herb = plant_service.resolve_herb(session, herb_query)
    if herb.status == "ambiguous":
        raise AmbiguousEntityError(
            f"'{herb_query}' matches more than one herb; choose one.",
            details={"candidates": [c.model_dump() for c in herb.candidates]},
        )
    drug = drug_service.resolve(session, settings, drug_query, allow_remote=allow_remote)
    api: list[MechanismPathOut] = []
    assessment = not_assessed()
    if herb.status == "resolved" and herb.herb is not None and drug.drug is not None:
        substance_ids = [
            s.id for s in plant_repo.herb_group(session, herb.herb.pharmaceutical_name)
        ]
        stored = drug_repo.drug_by_rxcui(session, drug.drug.rxcui)
        if stored is not None:
            _, api, assessment = paths_for_pair(session, substance_ids, stored.id)
    qualifying = sum(1 for p in api if p.qualifies_for_class_b)
    return MechanismPathsResponse(
        herb=herb,
        drug=drug,
        assessment=assessment,
        paths=api,
        qualifying_paths=qualifying,
        rules=RULES_VERSION,
        note=f"{PATHS_NOTE} {MECHANISM_CAVEAT}" if qualifying else PATHS_NOTE,
        disclaimer=DISCLAIMER,
    )


# --------------------------------------------------------------------------- graph queries


def list_herb_effects(
    session: Session,
    *,
    target: str | None,
    evidence_types: list[str] | None,
    effect: str | None,
    subject_kind: str | None,
    wfo_id: str | None,
    limit: int,
    offset: int,
) -> Page[HerbEffectOut]:
    """Every stored herb/constituent effect on an enzyme or transporter, filterable — e.g. all
    effects on CYP3A4, or all effects that rest only on in-vitro evidence."""
    if wfo_id is not None:
        taxon = plant_repo.get_taxon(session, wfo_id)
        if taxon is None:
            raise NotFoundError(f"No plant with WFO ID {wfo_id}.")
        substances = plant_repo.substances_for_taxa(session, [taxon.id])
        group = (
            plant_repo.herb_group(session, substances[0].pharmaceutical_name or "")
            if substances
            else []
        )
        rows = repo.herb_effects(session, [s.id for s in group])
    else:
        rows = repo.effects_on_targets(
            session, [t.id for t, _, _ in repo.targets_with_counts(session)]
        )
    if target is not None:
        wanted = target.upper()
        if repo.get_target(session, wanted) is None:
            raise NotFoundError(f"No enzyme or transporter with symbol {target}.")
        rows = [r for r in rows if r.target.symbol.upper() == wanted]
    if evidence_types:
        rows = [r for r in rows if r.modulation.evidence_type in evidence_types]
    if effect is not None:
        rows = [r for r in rows if r.modulation.effect == effect]
    if subject_kind is not None:
        rows = [r for r in rows if r.subject_kind == subject_kind]
    # one item per stored statement (species of one herb share the statement)
    unique: dict[uuid.UUID, repo.EffectRow] = {}
    for row in sorted(rows, key=lambda r: (r.subject_label, r.target.symbol, str(r.modulation.id))):
        unique.setdefault(row.modulation.id, row)
    ordered = list(unique.values())
    return Page[HerbEffectOut](
        items=_effects_out(session, ordered[offset : offset + limit]),
        total=len(ordered),
        limit=limit,
        offset=offset,
    )


def herb_drug_pairs(
    session: Session, wfo_id: str, *, qualifying_only: bool, limit: int, offset: int
) -> HerbDrugPairs:
    """Drugs that share an enzyme/transporter with this herb's stated effects, each with its
    mechanism finding. Answers "which herb–drug pairs have mechanism evidence" for one herb."""
    taxon = plant_repo.get_taxon(session, wfo_id)
    if taxon is None:
        raise NotFoundError(f"No plant with WFO ID {wfo_id}.")
    substances = plant_repo.substances_for_taxa(session, [taxon.id])
    if not substances:
        raise NotFoundError(f"No herbal substance for {wfo_id}.")
    herb = plant_service.herb_ref(substances[0])
    group = plant_repo.herb_group(session, substances[0].pharmaceutical_name or "")
    effect_rows = repo.herb_effects(session, [s.id for s in group] or [s.id for s in substances])
    symbols = {r.target.symbol for r in effect_rows}
    symbols |= {MATCH_GROUP[s] for s in symbols if s in MATCH_GROUP}
    symbols |= {member for member, grouped in MATCH_GROUP.items() if grouped in symbols}
    role_rows = repo.drug_roles(
        session, target_ids=[t.id for t in repo.targets_by_symbols(session, sorted(symbols))]
    )
    by_drug: dict[uuid.UUID, list[repo.RoleRow]] = {}
    for row in role_rows:
        by_drug.setdefault(row.drug.id, []).append(row)
    pairs: list[HerbDrugPair] = []
    for rows in by_drug.values():
        # all roles of the drug, so "the drug is an inhibitor, not a substrate" stays visible
        _, api, assessment = _pair(
            session, effect_rows, repo.drug_roles(session, drug_id=rows[0].drug.id)
        )
        if not api or (qualifying_only and not assessment.qualifying_paths):
            continue
        pairs.append(
            HerbDrugPair(
                drug=DrugRef(rxcui=rows[0].drug.rxcui, name=rows[0].drug.name),
                targets=sorted({p.target_symbols for p in api}),
                assessment=assessment,
                paths=api,
            )
        )
    pairs.sort(key=lambda p: (-p.assessment.qualifying_paths, p.drug.name))
    return HerbDrugPairs(
        herb=herb,
        items=pairs[offset : offset + limit],
        total=len(pairs),
        limit=limit,
        offset=offset,
        note="Drugs FDA lists as substrates, inhibitors or inducers of an enzyme/transporter this herb "
        "affects. Sharing an enzyme or transporter alone does not establish an interaction: only "
        "pairs whose assessment is 'mechanism_supported' meet the rules. FDA lists examples only; a "
        "drug that is not listed may still be affected.",
        rules=RULES_VERSION,
    )
