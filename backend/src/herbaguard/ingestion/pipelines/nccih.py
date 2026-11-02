"""NCCIH "Herbs at a Glance" fact sheets → evidence items (GOV) and safety-section assertions."""

from __future__ import annotations

import re
import uuid

from herbaguard.domain.enums import EvidenceRelation, EvidenceType, IssueSeverity, UseCategory
from herbaguard.ingestion.context import IngestionContext
from herbaguard.ingestion.curation import HerbEntry, load_herbs, load_lexicon
from herbaguard.ingestion.drugs import DrugResolver
from herbaguard.ingestion.extraction import ExtractionResult, extract_from_sentence
from herbaguard.ingestion.loaders import (
    link_substance_evidence,
    replace_chunks,
    substances_for_herb,
    supersede_missing_assertions,
    upsert_assertion,
    upsert_evidence,
)
from herbaguard.ingestion.normalize.lexicon import LexiconMatcher
from herbaguard.ingestion.normalize.statements import split_sentences
from herbaguard.ingestion.parsers.nccih_html import SAFETY_SECTION, parse_fact_sheet

SOURCE = "nccih"
BASE = "https://www.nccih.nih.gov/health"
METHOD = "nccih_pipeline_v1"


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def run(ctx: IngestionContext, herb_keys: list[str] | None = None) -> None:
    resolver = DrugResolver(ctx)
    matcher = LexiconMatcher(load_lexicon())
    for herb in load_herbs().herbs:
        if herb_keys and herb.key not in herb_keys:
            continue
        if not herb.nccih_slug:
            ctx.issue(
                "no_fact_sheet",
                f"No NCCIH fact sheet for {herb.common_name}.",
                severity=IssueSeverity.INFO,
                herb=herb.key,
            )
            continue
        with ctx.per_item(f"nccih:{herb.key}", resolver.reset):
            _ingest_sheet(ctx, herb, resolver, matcher)


def _ingest_sheet(
    ctx: IngestionContext, herb: HerbEntry, resolver: DrugResolver, matcher: LexiconMatcher
) -> None:
    if True:
        assert herb.nccih_slug is not None  # noqa: S101
        substance_ids = [s.id for s in substances_for_herb(ctx.session, herb.key)]
        kept: set[uuid.UUID] = set()
        url = f"{BASE}/{herb.nccih_slug}"
        page = ctx.fetch(url, native_id=herb.nccih_slug)
        if not page.ok:
            ctx.issue(
                "fact_sheet_unavailable",
                f"HTTP {page.result.status_code} for {url}.",
                severity=IssueSeverity.ERROR,
                record=page.record,
                herb=herb.key,
            )
            return
        sheet = parse_fact_sheet(page.content.decode("utf-8", "replace"))
        page.record.source_version = sheet.last_updated
        if sheet.section(SAFETY_SECTION) is None:
            ctx.issue(
                "fact_sheet_no_safety_section",
                f"'{SAFETY_SECTION}' not found on {url}.",
                severity=IssueSeverity.WARNING,
                record=page.record,
                herb=herb.key,
            )
        for section in sheet.sections:
            evidence_id = upsert_evidence(
                ctx.session,
                source_code=SOURCE,
                external_id=f"{herb.nccih_slug}#{_slug(section.title)}",
                evidence_type=EvidenceType.GOVERNMENT_SUMMARY.value,
                title=f"NCCIH: {sheet.title or herb.common_name} — {section.title}",
                url=url,
                metadata_={
                    "herb_key": herb.key,
                    "section": section.title,
                    "last_updated": sheet.last_updated,
                },
            )
            replace_chunks(
                ctx.session, evidence_id, [(section.title, section.text, {"herb_key": herb.key})]
            )
            link_substance_evidence(
                ctx.session, substance_ids, evidence_id, EvidenceRelation.FACT_SHEET.value
            )
            ctx.provenance(
                "evidence_item", evidence_id, page.record, METHOD, location=section.title
            )
            ctx.stats["fact_sheet_sections"] += 1
            if section.title != SAFETY_SECTION:
                continue
            result = ExtractionResult()
            for block in section.blocks:
                sentences = [block.text] if block.is_list_item else split_sentences(block.text)
                for sentence in sentences:
                    extract_from_sentence(
                        matcher,
                        sentence,
                        context=block.lead_in if block.is_list_item else None,
                        conditions=f"List introduced by: '{block.lead_in}'"
                        if block.is_list_item and block.lead_in
                        else None,
                        result=result,
                    )
            for phrase, sentence in result.unmapped:
                ctx.issue(
                    "lexicon_term_unmapped",
                    f"'{phrase}' recognised but has no drug/ATC mapping.",
                    severity=IssueSeverity.INFO,
                    record=page.record,
                    herb=herb.key,
                    sentence=sentence,
                )
            ctx.stats["descriptive_class_mentions_skipped"] += result.descriptive_skipped
            for candidate in result.candidates:
                if candidate.sentence not in re.sub(r"\s+", " ", section.text):
                    ctx.issue(
                        "excerpt_not_in_source",
                        "Excerpt not found in section text.",
                        severity=IssueSeverity.ERROR,
                        record=page.record,
                        herb=herb.key,
                    )
                    continue
                objects: list[dict[str, object]] = []
                if candidate.hit.kind == "drug":
                    ingredient = resolver.by_name(candidate.hit.key)
                    if ingredient:
                        objects.append({"drug_id": ingredient.drug_id})
                else:
                    objects += [
                        {"drug_class_code": c} for c in candidate.hit.atc if resolver.drug_class(c)
                    ]
                for obj in objects:
                    for substance_id in substance_ids:
                        assertion_id = upsert_assertion(
                            ctx.session,
                            evidence_item_id=evidence_id,
                            key_text=f"{candidate.sentence}|{candidate.hit.matched_text}",
                            herbal_substance_id=substance_id,
                            object_label_verbatim=candidate.hit.matched_text,
                            subject_label_verbatim=None,
                            source_code=SOURCE,
                            evidence_type=EvidenceType.GOVERNMENT_SUMMARY.value,
                            source_section=SAFETY_SECTION[:64],
                            use_category=UseCategory.NOT_APPLICABLE.value,
                            mechanism=None,
                            conditions=candidate.conditions,
                            severity_wording=candidate.severity_wording,
                            statement_type=candidate.statement_type.value,
                            status="active",
                            **obj,
                        )
                        kept.add(assertion_id)
                        ctx.provenance(
                            "interaction_assertion",
                            assertion_id,
                            page.record,
                            "lexicon_extraction_v1",
                            location=SAFETY_SECTION,
                            excerpt=candidate.sentence,
                        )
                        ctx.stats[f"assertions_{candidate.statement_type.value}"] += 1
        ctx.stats["assertions_superseded"] += supersede_missing_assertions(
            ctx.session, source_code=SOURCE, substance_ids=substance_ids, kept_ids=kept
        )
        ctx.stats["fact_sheets"] += 1
