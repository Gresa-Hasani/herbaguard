"""Evidence listing/detail, sources and per-herb coverage."""

from __future__ import annotations

import uuid
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from herbaguard.api.schemas.resources import (
    ChunkOut,
    CoverageRow,
    EvidenceDetail,
    EvidenceSummary,
    SourceOut,
)
from herbaguard.core.errors import NotFoundError
from herbaguard.models import (
    EvidenceItem,
    HerbalSubstance,
    HerbalSubstanceEvidence,
    IngestionRun,
    InteractionAssertion,
    SourceRecord,
)
from herbaguard.repositories import evidence as repo
from herbaguard.repositories import interactions as interaction_repo
from herbaguard.repositories import plants as plant_repo
from herbaguard.services.mappers import evidence_ref, provenance_out
from herbaguard.services.plants import herb_ref

# Metadata keys that are safe and useful to expose per source (verified against Phase 2 data).
PUBLIC_METADATA = {
    "ema_hmpc": (
        "document",
        "section",
        "section_title",
        "use_category",
        "pages",
        "footnotes",
        "section_statement",
        "inventory",
        "herb_page",
    ),
    "nccih": ("section", "last_updated"),
    "openfda_label": (
        "set_id",
        "version",
        "effective_time",
        "generic_name",
        "brand_name",
        "manufacturer",
    ),
    "pubmed": ("journal", "publication_types", "mesh_terms", "language", "has_abstract"),
}


def _summaries(session: Session, items: list[EvidenceItem]) -> list[EvidenceSummary]:
    links = repo.substance_links(session, [i.id for i in items])
    substance_ids = {link.herbal_substance_id for link in links}
    names = (
        {
            s.id: s.pharmaceutical_name or ""
            for s in session.scalars(
                select(HerbalSubstance).where(HerbalSubstance.id.in_(substance_ids))
            )
        }
        if substance_ids
        else {}
    )
    by_item: dict[uuid.UUID, list[HerbalSubstanceEvidence]] = {}
    for link in links:
        by_item.setdefault(link.evidence_item_id, []).append(link)
    out = []
    for item in items:
        item_links = by_item.get(item.id, [])
        keys = PUBLIC_METADATA.get(item.source_code, ())
        out.append(
            EvidenceSummary(
                **evidence_ref(item).model_dump(),
                herbs=sorted(
                    {names.get(link.herbal_substance_id, "") for link in item_links} - {""}
                ),
                relations=sorted({link.relation for link in item_links}),
                metadata={k: item.metadata_[k] for k in keys if k in item.metadata_},
            )
        )
    return out


def list_evidence(
    session: Session,
    *,
    wfo_id: str | None,
    herb: str | None,
    source_code: str | None,
    evidence_types: list[str] | None,
    relation: str | None,
    year_from: int | None,
    year_to: int | None,
    query: str | None,
    limit: int,
    offset: int,
) -> tuple[list[EvidenceSummary], int]:
    substance_ids: list[uuid.UUID] | None = None
    if wfo_id:
        taxon = plant_repo.get_taxon(session, wfo_id)
        if taxon is None:
            raise NotFoundError(f"No plant with WFO ID {wfo_id}.")
        substance_ids = [s.id for s in plant_repo.substances_for_taxa(session, [taxon.id])]
    if herb:
        group = [s.id for s in plant_repo.herb_group(session, herb)]
        if not group:
            raise NotFoundError(f"No curated herb with pharmaceutical name '{herb}'.")
        substance_ids = group if substance_ids is None else [s for s in substance_ids if s in group]
    filters = repo.EvidenceFilters(
        substance_ids=substance_ids,
        source_code=source_code,
        evidence_types=evidence_types,
        relation=relation,
        year_from=year_from,
        year_to=year_to,
        query=query,
    )
    items, total = repo.list_evidence(session, filters, limit=limit, offset=offset)
    return _summaries(session, items), total


def detail(session: Session, evidence_id: uuid.UUID) -> EvidenceDetail:
    item = repo.get_evidence(session, evidence_id)
    if item is None:
        raise NotFoundError(f"No evidence item {evidence_id}.")
    summary = _summaries(session, [item])[0]
    prov = repo.provenance_for(session, "evidence_item", [str(item.id)]).get(str(item.id), [])
    return EvidenceDetail(
        **summary.model_dump(),
        content=[
            ChunkOut(section=c.section, text=c.text) for c in repo.chunks_for(session, item.id)
        ],
        provenance=[provenance_out(p) for p in prov],
    )


def sources(session: Session) -> list[SourceOut]:
    latest = {
        r.source_code: r
        for r in session.scalars(
            select(IngestionRun)
            .distinct(IngestionRun.source_code)
            .order_by(IngestionRun.source_code, IngestionRun.started_at.desc())
        )
    }
    count_rows = session.execute(
        select(SourceRecord.source_code, func.count()).group_by(SourceRecord.source_code)
    ).all()
    counts: dict[str, int] = {code: int(n) for code, n in count_rows}
    latest_record = {
        r.source_code: r
        for r in session.scalars(
            select(SourceRecord)
            .distinct(SourceRecord.source_code)
            .order_by(SourceRecord.source_code, SourceRecord.retrieved_at.desc())
        )
    }
    return [
        SourceOut(
            code=s.code,
            name=s.name,
            provider=s.provider,
            homepage_url=s.homepage_url,
            is_official=s.is_official,
            licence=s.licence,
            licence_status=s.licence_status,
            redistributable=s.redistributable,
            last_run_status=latest[s.code].status if s.code in latest else None,
            last_run_finished_at=latest[s.code].finished_at if s.code in latest else None,
            records=int(counts.get(s.code, 0)),
            licence_url=s.licence_url,
            attribution=s.attribution,
            access_method=s.access_method,
            latest_retrieved_at=(
                latest_record[s.code].retrieved_at if s.code in latest_record else None
            ),
            latest_source_version=(
                latest_record[s.code].source_version if s.code in latest_record else None
            ),
        )
        for s in repo.sources(session)
    ]


def coverage(session: Session) -> list[CoverageRow]:
    groups: dict[str, list[HerbalSubstance]] = {}
    for substance in session.scalars(
        select(HerbalSubstance).where(HerbalSubstance.in_curated_scope.is_(True))
    ):
        groups.setdefault(substance.pharmaceutical_name or "", []).append(substance)
    rows = []
    for _name, members in sorted(groups.items(), key=lambda kv: kv[1][0].common_name_en or kv[0]):
        ids = [s.id for s in members]
        linked = list(
            session.execute(
                select(EvidenceItem, HerbalSubstanceEvidence.relation)
                .join(
                    HerbalSubstanceEvidence,
                    HerbalSubstanceEvidence.evidence_item_id == EvidenceItem.id,
                )
                .where(HerbalSubstanceEvidence.herbal_substance_id.in_(ids))
                .distinct()
            ).all()
        )
        monograph = next(
            (e for e, rel in linked if rel == "monograph" and "extraction" in e.metadata_), None
        )
        statements = Counter(
            t
            for (t,) in session.execute(
                select(InteractionAssertion.statement_type).where(
                    InteractionAssertion.herbal_substance_id == ids[0],
                    InteractionAssertion.status == "active",
                )
            ).all()
        )
        herb_key = monograph.metadata_.get("herb_key") if monograph else None
        coverage_issue = (
            interaction_repo.label_coverage(session, str(herb_key)) if herb_key else None
        )
        rows.append(
            CoverageRow(
                herb=herb_ref(members[0]),
                taxa=len(members),
                monograph=monograph.external_id if monograph else None,
                monograph_date=monograph.document_date if monograph else None,
                fact_sheet=any(rel == "fact_sheet" for _, rel in linked),
                label_coverage=coverage_issue.message if coverage_issue else None,
                evidence_items=dict(Counter(rel for _, rel in linked)),
                active_statements=dict(statements),
                pubmed_by_type=dict(
                    Counter(e.evidence_type for e, rel in linked if e.source_code == "pubmed")
                ),
            )
        )
    return rows
