"""Plant search, herb resolution and plant detail."""

from __future__ import annotations

import uuid
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from herbaguard.api.schemas.resources import (
    Candidate,
    HerbRef,
    HerbResolution,
    Identifiers,
    IndicationOut,
    MonographSummary,
    PlantCoverage,
    TaxonCoverage,
    TaxonDetail,
    TaxonSummary,
)
from herbaguard.core.errors import NotFoundError
from herbaguard.domain.name_overrides import override_for
from herbaguard.models import (
    EvidenceItem,
    ExternalEntity,
    ExternalRelation,
    HerbalSubstance,
    HerbalSubstanceEvidence,
    Indication,
    InteractionAssertion,
    Taxon,
)
from herbaguard.repositories import evidence as evidence_repo
from herbaguard.repositories import plants as repo
from herbaguard.repositories.external import NIH_DSLD
from herbaguard.services.mappers import evidence_ref, name_out, provenance_out

COMMON_NAME_NOTE = (
    "Matched a common name. Common names can refer to different species; check the scientific name."
)
PARTIAL_NOTE = "No exact name match; resolved from a partial match to a single herb. Check the scientific name."


def herb_ref(substance: HerbalSubstance) -> HerbRef:
    return HerbRef(
        pharmaceutical_name=substance.pharmaceutical_name or "",
        common_name=substance.common_name_en,
        plant_part=substance.plant_part,
    )


def _herbs_for(session: Session, taxon_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[HerbRef]]:
    out: dict[uuid.UUID, list[HerbRef]] = {t: [] for t in taxon_ids}
    for substance in repo.substances_for_taxa(session, taxon_ids):
        out.setdefault(substance.taxon_id, []).append(herb_ref(substance))
    return out


def taxon_summary(
    taxon: Taxon, herbs: list[HerbRef], matched: repo.NameMatch | None = None
) -> TaxonSummary:
    from herbaguard.api.schemas.resources import NameOut

    return TaxonSummary(
        wfo_id=taxon.wfo_id,
        scientific_name=taxon.scientific_name,
        authorship=taxon.authorship,
        family=taxon.family,
        herbs=herbs,
        matched_name=NameOut(
            name=matched.name,
            name_type=matched.name_type,
            language=None,
            source_code=matched.source_code,
        )
        if matched
        else None,
    )


def search(
    session: Session, query: str | None, *, limit: int, offset: int
) -> tuple[list[TaxonSummary], int]:
    rows, total = repo.search_taxa(session, query, limit=limit, offset=offset)
    herbs = _herbs_for(session, [t.id for t, _ in rows])
    return [taxon_summary(t, herbs.get(t.id, []), m) for t, m in rows], total


def resolve_herb(session: Session, query: str) -> HerbResolution:
    """Resolve free text to one curated herb (group of substances sharing an EMA name)."""
    from herbaguard.api.schemas.resources import NameOut

    override = override_for(query)  # reviewed name overrides (domain.name_overrides)
    matches = repo.match_names(session, query, exact_only=True)
    partial = False
    if not matches and len(query.strip()) >= 4 and override is None:
        matches = repo.match_names(session, query, exact_only=False, limit=50)
        partial = True
    if not matches:
        note = override.reason if override else "No curated herb matches this name."
        return HerbResolution(query=query, status="not_found", note=note)

    substances = repo.substances_for_taxa(session, list({m.taxon_id for m in matches}))
    groups: dict[str, list[HerbalSubstance]] = {}
    for substance in substances:
        groups.setdefault(substance.pharmaceutical_name or "", []).append(substance)
    match_by_taxon = {m.taxon_id: m for m in matches}

    def name(match: repo.NameMatch) -> NameOut:
        return NameOut(
            name=match.name, name_type=match.name_type, language=None, source_code=match.source_code
        )

    reviewed_ambiguous = override is not None and override.action == "ambiguous"
    if len(groups) > 1 or (reviewed_ambiguous and groups):
        candidates = []
        for pharmaceutical, members in sorted(groups.items()):
            first = next(
                match_by_taxon[s.taxon_id] for s in members if s.taxon_id in match_by_taxon
            )
            candidates.append(
                Candidate(
                    pharmaceutical_name=pharmaceutical,
                    common_name=members[0].common_name_en,
                    taxa=sorted(
                        {
                            repo.taxa_by_ids(session, [s.taxon_id])[s.taxon_id].wfo_id
                            for s in members
                        }
                    ),
                    matched_name=name(first),
                )
            )
        return HerbResolution(
            query=query,
            status="ambiguous",
            candidates=candidates,
            note=override.reason
            if reviewed_ambiguous and override is not None
            else "The name matches more than one herb.",
        )
    if not groups:
        return HerbResolution(
            query=query, status="not_found", note="The name matches no curated herbal substance."
        )

    pharmaceutical, _ = next(iter(groups.items()))
    group = repo.herb_group(session, pharmaceutical)
    taxa = repo.taxa_by_ids(session, [s.taxon_id for s in group])
    first_match = next(
        (match_by_taxon[s.taxon_id] for s in group if s.taxon_id in match_by_taxon), matches[0]
    )
    notes = []
    if partial:
        notes.append(PARTIAL_NOTE)
    if first_match.name_type == "common":
        notes.append(COMMON_NAME_NOTE)
    if first_match.name_type == "synonym":
        accepted = taxa[next(s.taxon_id for s in group if s.taxon_id == first_match.taxon_id)]
        notes.append(
            f"'{first_match.name}' is a synonym; the accepted name is {accepted.scientific_name} "
            f"{accepted.authorship or ''} ({accepted.wfo_id}).".replace("  ", " ")
        )
    return HerbResolution(
        query=query,
        status="resolved",
        herb=herb_ref(group[0]),
        taxa=[taxon_summary(taxa[s.taxon_id], [herb_ref(s)]) for s in group],
        matched_name=name(first_match),
        note=" ".join(notes) or None,
    )


def detail(session: Session, wfo_id: str) -> TaxonDetail:
    taxon = repo.get_taxon(session, wfo_id)
    if taxon is None:
        raise NotFoundError(f"No plant with WFO ID {wfo_id}.")
    substances = repo.substances_for_taxa(session, [taxon.id])
    substance_ids = [s.id for s in substances]

    indications = list(
        session.execute(
            select(Indication, EvidenceItem)
            .join(EvidenceItem, EvidenceItem.id == Indication.evidence_item_id)
            .where(Indication.herbal_substance_id.in_(substance_ids))
            .order_by(Indication.use_category, Indication.text)
        ).all()
    )
    indication_prov = evidence_repo.provenance_for(
        session, "indication", [str(i.id) for i, _ in indications]
    )

    monographs = list(
        session.scalars(
            select(EvidenceItem)
            .join(
                HerbalSubstanceEvidence, HerbalSubstanceEvidence.evidence_item_id == EvidenceItem.id
            )
            .where(
                HerbalSubstanceEvidence.herbal_substance_id.in_(substance_ids),
                EvidenceItem.source_code == "ema_hmpc",
                EvidenceItem.metadata_.has_key("extraction"),
            )
            .distinct()
        )
    )
    from herbaguard.repositories.interactions import none_reported_sections

    none_by_doc: dict[str, list[str]] = {}
    for section in none_reported_sections(session, substance_ids):
        none_by_doc.setdefault(section.document, []).append(section.use_category)

    relation_counts = Counter(
        relation
        for (relation,) in session.execute(
            select(HerbalSubstanceEvidence.relation)
            .where(HerbalSubstanceEvidence.herbal_substance_id.in_(substance_ids))
            .distinct(HerbalSubstanceEvidence.evidence_item_id, HerbalSubstanceEvidence.relation)
        ).all()
    )
    statements = session.scalar(
        select(func.count())
        .select_from(InteractionAssertion)
        .where(
            InteractionAssertion.herbal_substance_id.in_(substance_ids),
            InteractionAssertion.status == "active",
        )
    )

    taxon_prov = evidence_repo.provenance_for(session, "taxon", [str(taxon.id)]).get(
        str(taxon.id), []
    )
    return TaxonDetail(
        wfo_id=taxon.wfo_id,
        scientific_name=taxon.scientific_name,
        authorship=taxon.authorship,
        family=taxon.family,
        herbs=[herb_ref(s) for s in substances],
        identifiers=Identifiers(
            wfo_id=taxon.wfo_id,
            ipni_id=taxon.ipni_id,
            wcvp_plant_name_id=taxon.wcvp_plant_name_id,
            gbif_key=taxon.gbif_key,
            ncbi_tax_id=taxon.ncbi_tax_id,
            powo_id=taxon.powo_id,
            wikidata_id=taxon.wikidata_id,
        ),
        native_range=taxon.native_range,
        names=[name_out(n) for n in repo.names_for_taxon(session, taxon.id)],
        indications=[
            IndicationOut(
                text=ind.text,
                use_category=ind.use_category,
                evidence=evidence_ref(ev),
                provenance=[provenance_out(p) for p in indication_prov.get(str(ind.id), [])],
            )
            for ind, ev in indications
        ],
        monographs=[
            MonographSummary(
                document=m.external_id,
                title=m.title,
                url=m.url,
                document_date=m.document_date,
                use_categories=list(m.metadata_["extraction"].get("use_categories", [])),
                section_completeness=dict(m.metadata_["extraction"].get("completeness", {})),
                interactions_section_states_none_reported=sorted(
                    none_by_doc.get(m.external_id, [])
                ),
            )
            for m in monographs
        ],
        provenance=[provenance_out(p) for p in taxon_prov],
        counts={
            **{f"evidence_{k}": v for k, v in relation_counts.items()},
            "active_interaction_statements": statements or 0,
        },
    )


# Supplementary research sources whose taxon mappings are reported (never as evidence of a class).
SUPPLEMENTARY_SOURCES = ("ddid", "supp_ai", "livertox")


def plant_coverage(session: Session) -> PlantCoverage:
    """Per-taxon coverage by kind of material, from the stored records (no estimates).

    Counting follows ``plant_detail``: distinct evidence items per relation over the taxon's
    curated substances. A taxonomic record, a product label and a clinical record are reported
    separately and never summed.
    """
    taxa = list(session.scalars(select(Taxon).order_by(Taxon.scientific_name)))

    relation_rows = session.execute(
        select(
            HerbalSubstance.taxon_id,
            HerbalSubstanceEvidence.relation,
            func.count(func.distinct(HerbalSubstanceEvidence.evidence_item_id)),
        )
        .join(HerbalSubstance, HerbalSubstance.id == HerbalSubstanceEvidence.herbal_substance_id)
        .where(HerbalSubstance.in_curated_scope.is_(True))
        .group_by(HerbalSubstance.taxon_id, HerbalSubstanceEvidence.relation)
    ).all()
    relations: dict[uuid.UUID, dict[str, int]] = {}
    for taxon_id, relation, n in relation_rows:
        relations.setdefault(taxon_id, {})[relation] = int(n)

    monograph_rows = session.execute(
        select(HerbalSubstance.taxon_id, func.count(func.distinct(EvidenceItem.id)))
        .join(
            HerbalSubstanceEvidence,
            HerbalSubstanceEvidence.herbal_substance_id == HerbalSubstance.id,
        )
        .join(EvidenceItem, EvidenceItem.id == HerbalSubstanceEvidence.evidence_item_id)
        .where(
            HerbalSubstance.in_curated_scope.is_(True),
            EvidenceItem.source_code == "ema_hmpc",
            EvidenceItem.metadata_.has_key("extraction"),
        )
        .group_by(HerbalSubstance.taxon_id)
    ).all()
    monographs = {taxon_id: int(n) for taxon_id, n in monograph_rows}

    statement_rows = session.execute(
        select(HerbalSubstance.taxon_id, func.count(InteractionAssertion.id))
        .join(InteractionAssertion, InteractionAssertion.herbal_substance_id == HerbalSubstance.id)
        .where(HerbalSubstance.in_curated_scope.is_(True), InteractionAssertion.status == "active")
        .group_by(HerbalSubstance.taxon_id)
    ).all()
    statements = {taxon_id: int(n) for taxon_id, n in statement_rows}

    ingredient = aliased(ExternalEntity)
    product = aliased(ExternalEntity)
    dsld_rows = session.execute(
        select(ingredient.mapped_id, func.count(func.distinct(ExternalRelation.subject_id)))
        .join(ingredient, ingredient.id == ExternalRelation.object_id)
        .join(product, product.id == ExternalRelation.subject_id)
        .where(
            ExternalRelation.source_code == NIH_DSLD,
            ExternalRelation.predicate == "lists_ingredient",
            ingredient.mapped_table == "taxon",
            ingredient.mapping_status == "resolved",
            product.kind == "dsld_product",
        )
        .group_by(ingredient.mapped_id)
    ).all()
    dsld = {taxon_id: int(n) for taxon_id, n in dsld_rows}

    supplementary: dict[uuid.UUID, dict[str, str]] = {}
    for source_code, mapped_id, status in session.execute(
        select(ExternalEntity.source_code, ExternalEntity.mapped_id, ExternalEntity.mapping_status)
        .where(
            ExternalEntity.source_code.in_(SUPPLEMENTARY_SOURCES),
            ExternalEntity.mapped_table == "taxon",
            ExternalEntity.mapping_status.in_(("resolved", "candidate")),
        )
        .distinct()
    ).all():
        current = supplementary.setdefault(mapped_id, {})
        # a resolved mapping outranks a candidate one; a candidate is never shown as resolved
        if current.get(source_code) != "resolved":
            current[source_code] = status

    items = []
    for taxon in taxa:
        rel = relations.get(taxon.id, {})
        items.append(
            TaxonCoverage(
                wfo_id=taxon.wfo_id,
                scientific_name=taxon.scientific_name,
                family=taxon.family,
                taxonomic_status=taxon.taxonomic_status,
                monograph_documents=monographs.get(taxon.id, 0),
                fact_sheet_items=rel.get("fact_sheet", 0),
                drug_label_mentions=rel.get("label_mention", 0),
                literature_clinical_items=rel.get("literature_clinical", 0),
                literature_interaction_items=rel.get("literature_interaction", 0),
                dsld_products=dsld.get(taxon.id, 0),
                supplementary_sources=supplementary.get(taxon.id, {}),
                active_interaction_statements=statements.get(taxon.id, 0),
            )
        )
    return PlantCoverage(total=len(items), items=items)
