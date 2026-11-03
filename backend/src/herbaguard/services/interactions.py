"""Herb–drug interaction check and per-herb interaction overview."""

from __future__ import annotations

import re
import uuid
from collections import Counter
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from herbaguard.api.schemas.mechanism_core import MechanismAssessmentOut, MechanismPathOut
from herbaguard.api.schemas.resources import (
    ClassificationOut,
    DrugCheckResult,
    HerbInteractionGroup,
    InteractionCheckResponse,
    SourceSearched,
    StatementOut,
)
from herbaguard.core.config import DISCLAIMER, Settings
from herbaguard.core.errors import AmbiguousEntityError, NotFoundError
from herbaguard.domain.enums import EvidenceType, StatementType
from herbaguard.domain.interactions import Classification, MechanismPath, Statement, classify
from herbaguard.models import EvidenceItem, HerbalSubstanceEvidence, SourceRecord
from herbaguard.repositories import drugs as drug_repo
from herbaguard.repositories import evidence as evidence_repo
from herbaguard.repositories import interactions as repo
from herbaguard.repositories import plants as plant_repo
from herbaguard.services import drugs as drug_service
from herbaguard.services import mechanisms as mechanism_service
from herbaguard.services import plants as plant_service
from herbaguard.services.mappers import (
    STATEMENT_TYPE_NOTES,
    class_out,
    evidence_ref,
    provenance_out,
)

CLASSIFYING_RELATIONS = ("monograph", "fact_sheet", "label_mention")


# --------------------------------------------------------------------------- statements

LABEL_INTERACTION_SECTIONS = frozenset({"drug_interactions", "contraindications", "boxed_warning"})
SUBJECT_NOTES = {
    "named_in_sentence": "The sentence names the label's drug.",
    "interaction_section": "The sentence is in the label's drug-interaction, contraindication or boxed-warning "
    "section, which is about the label's drug.",
    "not_verified": "Counted as context only: the sentence does not name the label's drug and is not in an "
    "interaction-specific section, so the drug may not be the subject (e.g. an isotretinoin label sentence about "
    "St John's wort and hormonal contraceptives).",
}


def label_subject_check(row: repo.AssertionRow, excerpt: str | None) -> str:
    """For FDA label statements: is the label's drug confirmed as the subject of the sentence?"""
    if row.assertion.source_code != "openfda_label" or row.assertion.drug_id is None:
        return "not_applicable"
    text = (excerpt or "").lower()
    meta = row.evidence.metadata_
    names = {row.drug_name or ""}
    for key in ("generic_name", "brand_name"):
        value = str(meta.get(key) or "").strip().lower()
        if value:
            names.add(value.split()[0].strip(",;"))
    if any(
        n and len(n) >= 3 and re.search(rf"(?<![a-z]){re.escape(n.lower())}", text) for n in names
    ):
        return "named_in_sentence"
    if (row.assertion.source_section or "") in LABEL_INTERACTION_SECTIONS:
        return "interaction_section"
    return "not_verified"


def _group_key(row: repo.AssertionRow, excerpt: str | None) -> tuple[object, ...]:
    a = row.assertion
    return (
        a.source_code,
        row.evidence.id,
        a.drug_id,
        a.drug_class_code,
        a.use_category,
        a.source_section,
        excerpt,
    )


def build_statements(
    session: Session, rows: list[repo.AssertionRow], *, drug_matched_id: uuid.UUID | None
) -> tuple[list[Statement], dict[str, StatementOut]]:
    """Merge rows that are the same statement for several species of one herb; map to domain and
    API objects (same id)."""
    prov = evidence_repo.provenance_for(
        session, "interaction_assertion", [str(r.assertion.id) for r in rows]
    )
    groups: dict[tuple[object, ...], list[repo.AssertionRow]] = {}
    for row in rows:
        rows_prov = prov.get(str(row.assertion.id), [])
        excerpt = next((p.excerpt for p in rows_prov if p.excerpt), None)
        groups.setdefault(_group_key(row, excerpt), []).append(row)

    domain: list[Statement] = []
    api: dict[str, StatementOut] = {}
    herb_names = _pharmaceutical_names(session, [r.assertion.herbal_substance_id for r in rows])
    for members in groups.values():
        first = members[0]
        a = first.assertion
        statement_id = str(a.id)
        matched_via = (
            "drug"
            if a.drug_id is not None and (drug_matched_id is None or a.drug_id == drug_matched_id)
            else "class"
        )
        provenance = [p for m in members for p in prov.get(str(m.assertion.id), [])]
        unique_prov = {(p.record_url, p.location): p for p in provenance}.values()
        excerpt = next((p.excerpt for p in provenance if p.excerpt), None)
        subject = label_subject_check(first, excerpt)
        domain.append(
            Statement(
                id=statement_id,
                source_code=a.source_code,
                evidence_type=EvidenceType(a.evidence_type),
                statement_type=StatementType(a.statement_type),
                matched_via=matched_via,
                drug_class_code=a.drug_class_code,
                conditions=a.conditions,
                severity_wording=a.severity_wording,
                use_category=a.use_category,
                subject_verified=subject != "not_verified",
            )
        )
        drug = drug_repo.drug_by_rxcui(session, first.drug_rxcui) if first.drug_rxcui else None
        cls = drug_repo.get_class(session, a.drug_class_code) if a.drug_class_code else None
        api[statement_id] = StatementOut(
            id=statement_id,
            role="context",
            statement_type=StatementType(a.statement_type),
            statement_type_note=STATEMENT_TYPE_NOTES[a.statement_type],
            source_code=a.source_code,
            source_section=a.source_section,
            use_category=a.use_category,
            matched_via=matched_via,
            drug=drug_service.as_out(session, drug) if drug else None,
            drug_class=class_out(cls) if cls else None,
            object_label_verbatim=a.object_label_verbatim,
            subject_label_verbatim=a.subject_label_verbatim,
            severity_wording=a.severity_wording,
            conditions=a.conditions,
            mechanism=a.mechanism,
            excerpt=excerpt,
            subject_check=subject,
            subject_check_note=SUBJECT_NOTES.get(subject),
            evidence=evidence_ref(first.evidence),
            provenance=[provenance_out(p) for p in unique_prov],
            herbs=sorted(
                {herb_names.get(m.assertion.herbal_substance_id, "") for m in members} - {""}
            ),
        )
    return domain, api


def _pharmaceutical_names(session: Session, substance_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    from herbaguard.models import HerbalSubstance

    if not substance_ids:
        return {}
    return {
        s.id: f"{s.pharmaceutical_name}"
        for s in session.scalars(
            select(HerbalSubstance).where(HerbalSubstance.id.in_(set(substance_ids)))
        )
    }


def _with_role(statement: StatementOut, role: str) -> StatementOut:
    return statement.model_copy(update={"role": role})


# --------------------------------------------------------------------------- herb context


def _herb_key(session: Session, pharmaceutical_name: str) -> str | None:
    return session.scalar(
        select(EvidenceItem.metadata_["herb_key"].astext)
        .where(
            EvidenceItem.source_code == "ema_hmpc",
            EvidenceItem.metadata_["ema_latin_name"].astext == pharmaceutical_name,
        )
        .limit(1)
    )


def _retrieved_at(session: Session, evidence_id: uuid.UUID) -> datetime | None:
    from herbaguard.models import Provenance

    return session.scalar(
        select(func.max(SourceRecord.retrieved_at))
        .join(Provenance, Provenance.source_record_id == SourceRecord.id)
        .where(Provenance.entity_table == "evidence_item", Provenance.entity_id == str(evidence_id))
    )


def sources_searched(
    session: Session, substance_ids: list[uuid.UUID], pharmaceutical_name: str
) -> list[SourceSearched]:
    out: list[SourceSearched] = []
    linked = list(
        session.execute(
            select(EvidenceItem, HerbalSubstanceEvidence.relation)
            .join(
                HerbalSubstanceEvidence, HerbalSubstanceEvidence.evidence_item_id == EvidenceItem.id
            )
            .where(HerbalSubstanceEvidence.herbal_substance_id.in_(substance_ids))
            .distinct()
        ).all()
    )
    monographs = [e for e, rel in linked if rel == "monograph" and "extraction" in e.metadata_]
    for doc in monographs:
        categories = ", ".join(
            c.replace("_", " ") for c in doc.metadata_["extraction"].get("use_categories", [])
        )
        out.append(
            SourceSearched(
                source_code="ema_hmpc",
                description=f"EU herbal monograph {doc.external_id} ({doc.document_date}); sections 4.3 Contraindications, "
                f"4.4 Warnings and 4.5 Interactions; use categories: {categories}.",
                retrieved_at=_retrieved_at(session, doc.id),
                used_for_classification=True,
            )
        )
    if not monographs:
        out.append(
            SourceSearched(
                source_code="ema_hmpc",
                description="No EU herbal monograph for this herb.",
                retrieved_at=None,
                used_for_classification=True,
            )
        )
    sheets = [e for e, rel in linked if rel == "fact_sheet"]
    if sheets:
        updated = sheets[0].metadata_.get("last_updated")
        out.append(
            SourceSearched(
                source_code="nccih",
                description=f"NCCIH fact sheet (last updated {updated}); section 'What Do We Know About Safety?'.",
                retrieved_at=_retrieved_at(session, sheets[0].id),
                used_for_classification=True,
            )
        )
    else:
        out.append(
            SourceSearched(
                source_code="nccih",
                description="No NCCIH fact sheet for this herb.",
                retrieved_at=None,
                used_for_classification=True,
            )
        )
    key = _herb_key(session, pharmaceutical_name)
    coverage = repo.label_coverage(session, key) if key else None
    out.append(
        SourceSearched(
            source_code="openfda_label",
            description=(
                f"openFDA drug labels (interaction, contraindication and warning sections): {coverage.message}"
                if coverage
                else "openFDA drug labels: not searched for this herb."
            ),
            retrieved_at=coverage.created_at if coverage else None,
            used_for_classification=coverage is not None,
        )
    )
    out += _mechanism_sources(session, substance_ids)
    articles = sum(1 for _, rel in linked if rel.startswith("literature"))
    out.append(
        SourceSearched(
            source_code="pubmed",
            description=f"{articles} PubMed records linked to this herb. Shown as related literature; "
            "not used for classification (records are linked to the herb, not to specific drugs).",
            retrieved_at=None,
            used_for_classification=False,
        )
    )
    return out


def _mechanism_sources(session: Session, substance_ids: list[uuid.UUID]) -> list[SourceSearched]:
    """Phase 4: the mechanism layer, reported only once it has been ingested."""
    from herbaguard.repositories import mechanisms as mechanism_repo

    table = mechanism_repo.fda_table_item(session)
    if table is None:
        return []
    effects = mechanism_repo.herb_effects(session, substance_ids)
    herb_side = sorted(
        {f"{e.modulation.effect} {e.target.symbol} [{e.modulation.source_code}]" for e in effects}
    )
    return [
        SourceSearched(
            source_code="fda_cyp_table",
            description=(
                f"FDA table of drugs interacting with CYP enzymes and transporters (content current as of "
                f"{table.document_date}); drug roles used for mechanism-based class B only. Stored effects of "
                f"this herb on enzymes/transporters: {', '.join(herb_side) if herb_side else 'none'}."
            ),
            retrieved_at=_retrieved_at(session, table.id),
            used_for_classification=True,
        )
    ]


def _herb_has_sources(session: Session, substance_ids: list[uuid.UUID]) -> bool:
    return bool(
        session.scalar(
            select(func.count())
            .select_from(HerbalSubstanceEvidence)
            .where(
                HerbalSubstanceEvidence.herbal_substance_id.in_(substance_ids),
                HerbalSubstanceEvidence.relation.in_(CLASSIFYING_RELATIONS),
            )
        )
    )


def _none_reported_descriptions(session: Session, substance_ids: list[uuid.UUID]) -> list[str]:
    return sorted(
        {
            f'{s.document} §4.5 ({s.use_category.replace("_", " ")}, {s.document_date}): "{s.text}"'
            for s in repo.none_reported_sections(session, substance_ids)
        }
    )


def classification_out(c: Classification) -> ClassificationOut:
    return ClassificationOut(
        interaction_class=c.interaction_class,
        class_label=c.class_label,
        finding=c.finding,
        finding_label=c.finding_label,
        explanation=c.explanation,
        reasons=c.reasons,
        severity_wordings=c.severity_wordings,
        caveats=c.caveats,
    )


# --------------------------------------------------------------------------- check


def check(
    session: Session,
    settings: Settings,
    *,
    herb_query: str,
    drug_queries: list[str],
    allow_remote: bool,
) -> InteractionCheckResponse:
    herb = plant_service.resolve_herb(session, herb_query)
    if herb.status == "ambiguous":
        raise AmbiguousEntityError(
            f"'{herb_query}' matches more than one herb; choose one.",
            details={"candidates": [c.model_dump() for c in herb.candidates]},
        )
    substance_ids: list[uuid.UUID] = []
    if herb.herb is not None:
        substance_ids = [
            s.id for s in plant_repo.herb_group(session, herb.herb.pharmaceutical_name)
        ]
    herb_ok = herb.status == "resolved" and bool(substance_ids)
    has_sources = _herb_has_sources(session, substance_ids) if herb_ok else False
    searched = (
        sources_searched(session, substance_ids, herb.herb.pharmaceutical_name)
        if herb_ok and herb.herb
        else []
    )
    none_reported = _none_reported_descriptions(session, substance_ids) if herb_ok else []
    literature = (
        session.scalar(
            select(func.count(func.distinct(HerbalSubstanceEvidence.evidence_item_id))).where(
                HerbalSubstanceEvidence.herbal_substance_id.in_(substance_ids),
                HerbalSubstanceEvidence.relation.like("literature%"),
            )
        )
        if herb_ok
        else 0
    )

    results = []
    for query in dict.fromkeys(drug_queries):  # de-duplicate, keep order
        resolution = drug_service.resolve(session, settings, query, allow_remote=allow_remote)
        drug_ok = resolution.status == "resolved" and resolution.drug is not None
        domain: list[Statement] = []
        api: dict[str, StatementOut] = {}
        mechanisms: list[MechanismPath] = []
        mechanism_paths: list[MechanismPathOut] = []
        mechanism_assessment: MechanismAssessmentOut = mechanism_service.not_assessed()
        if herb_ok and drug_ok:
            assert resolution.drug is not None  # noqa: S101
            drug = drug_repo.drug_by_rxcui(session, resolution.drug.rxcui)
            assert drug is not None  # noqa: S101
            codes = drug_repo.atc_prefixes([c.code for c in resolution.drug.atc_classes])
            rows = repo.active_assertions(
                session, substance_ids, drug_id=drug.id, class_codes=codes
            )
            domain, api = build_statements(session, rows, drug_matched_id=drug.id)
            mechanisms, mechanism_paths, mechanism_assessment = mechanism_service.paths_for_pair(
                session, substance_ids, drug.id
            )
        result = classify(
            herb_resolved=herb_ok,
            drug_resolved=drug_ok,
            herb_has_sources=has_sources,
            statements=domain,
            mechanisms=mechanisms,
            herb_level_none_reported=none_reported,
        )
        results.append(
            DrugCheckResult(
                drug=resolution,
                classification=classification_out(result),
                decisive_statements=[
                    _with_role(api[i], "decisive") for i in result.decisive_statement_ids
                ],
                context_statements=[
                    _with_role(api[i], "context") for i in result.context_statement_ids
                ],
                sources_searched=searched,
                mechanism_paths=mechanism_paths,
                mechanism_assessment=mechanism_assessment,
                related_literature={
                    "count": literature or 0,
                    "used_for_classification": False,
                    "note": "PubMed records about this herb (not specific to this drug). Evidence types describe study "
                    "design, not quality.",
                    "href": f"/api/v1/evidence?herb={herb.herb.pharmaceutical_name}&relation=literature_interaction"
                    if herb.herb
                    else None,
                },
            )
        )
    return InteractionCheckResponse(herb=herb, results=results, disclaimer=DISCLAIMER)


def herb_overview(
    session: Session, wfo_id: str, *, statement_types: list[str] | None, source_code: str | None
) -> list[HerbInteractionGroup]:
    taxon = plant_repo.get_taxon(session, wfo_id)
    if taxon is None:
        raise NotFoundError(f"No plant with WFO ID {wfo_id}.")
    substance_ids = [s.id for s in plant_repo.substances_for_taxa(session, [taxon.id])]
    rows = repo.active_assertions(session, substance_ids)
    if statement_types:
        rows = [r for r in rows if r.assertion.statement_type in statement_types]
    if source_code:
        rows = [r for r in rows if r.assertion.source_code == source_code]
    _, api = build_statements(session, rows, drug_matched_id=None)
    groups: dict[tuple[str, str], list[StatementOut]] = {}
    for statement in api.values():
        if statement.drug is not None:
            key = ("drug", statement.drug.rxcui)
        else:
            key = ("class", statement.drug_class.code if statement.drug_class else "?")
        groups.setdefault(key, []).append(statement)
    out = []
    for (kind, ident), statements in groups.items():
        first = statements[0]
        out.append(
            HerbInteractionGroup(
                target=first.drug.name
                if kind == "drug" and first.drug
                else (first.drug_class.name if first.drug_class else ident),
                target_kind=kind,
                rxcui=ident if kind == "drug" else None,
                atc_code=ident if kind == "class" else None,
                statement_types=dict(Counter(s.statement_type.value for s in statements)),
                statements=statements,
            )
        )
    return sorted(out, key=lambda g: (g.target_kind, g.target.lower()))
