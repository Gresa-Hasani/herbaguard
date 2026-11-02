"""EMA HMPC: herbal inventory → herb page → final EU herbal monograph PDF → sections → evidence.

Steps per curated herb:

1. Find the inventory row by exact Latin name (non-combination); check that every EMA
   botanical name resolves (WFO/WCVP) to one of the curated accepted taxa.
2. Discover the final, non-draft, non-superseded monograph on the herb page.
3. Parse the PDF (``ema_monograph``), verify it against PDFium (``ema_crosscheck``) and record
   per-section completeness. Extraction warnings become data-quality issues.
4. Store each (section, use category) of section 4 as an evidence item with a retrieval chunk,
   plus one document-level evidence item holding completeness and extraction metrics.
5. Indications (4.1) → ``indication`` rows; drug/class mentions in 4.3–4.5 → interaction
   assertions with verbatim excerpts (checked to be substrings of the stored section text).

A missing or empty section is recorded as such and never interpreted as "no interactions".
"""

from __future__ import annotations

import re
import uuid
from datetime import date

from herbaguard.domain.enums import EvidenceRelation, EvidenceType, IssueSeverity, UseCategory
from herbaguard.ingestion.context import IngestionContext
from herbaguard.ingestion.curation import CURATED_DIR, HerbEntry, load_herbs, load_lexicon
from herbaguard.ingestion.drugs import DrugResolver
from herbaguard.ingestion.extraction import SECTION_USE, extract_from_monograph_text, none_reported
from herbaguard.ingestion.loaders import (
    link_substance_evidence,
    replace_chunks,
    substances_for_herb,
    supersede_missing_assertions,
    upsert_assertion,
    upsert_evidence,
    upsert_indication,
)
from herbaguard.ingestion.normalize.lexicon import LexiconMatcher
from herbaguard.ingestion.normalize.names import canonical_binomial, split_ema_botanical_names
from herbaguard.ingestion.parsers.ema_crosscheck import crosscheck, document_token_coverage
from herbaguard.ingestion.parsers.ema_inventory import (
    InventoryRow,
    find_monograph_links,
    parse_inventory,
)
from herbaguard.ingestion.parsers.ema_monograph import (
    PARSER_VERSION,
    REQUIRED_SECTIONS,
    Monograph,
    parse_monograph,
)
from herbaguard.ingestion.pipelines.taxonomy import resolve_to_accepted_name
from herbaguard.models import Taxon

SOURCE = "ema_hmpc"
BASE = "https://www.ema.europa.eu"
INVENTORY_URL = f"{BASE}/en/documents/report/medicines-output-herbal_medicines-report_en.xlsx"
METHOD = "ema_pipeline_v1"
ASSERTION_SECTIONS = ("4.3", "4.4", "4.5")
CLINICAL_SECTIONS = ("4.1", "4.2", "4.3", "4.4", "4.5", "4.6", "4.7", "4.8", "4.9")
_ERROR_WARNINGS = {"required_section_missing", "required_section_empty", "no_use_columns"}


def _evidence_type(section: str, category: UseCategory) -> EvidenceType:
    # Traditional-use indications are accepted on long-standing use, not clinical efficacy.
    if section == "4.1" and category is UseCategory.TRADITIONAL:
        return EvidenceType.TRADITIONAL_USE
    return EvidenceType.REGULATORY


def _split_indications(text: str) -> list[str]:
    parts = re.split(r"\n\n(?=Indications? \d)", text)
    return [p.strip() for p in parts if p.strip()]


def _check_botanical_names(
    ctx: IngestionContext,
    herb: HerbEntry,
    botanical: str | None,
    curated_ids: set[str],
    record_id: object,
) -> None:
    if not botanical:
        ctx.issue(
            "ema_botanical_name_missing",
            f"No botanical name in EMA inventory for {herb.ema_latin_name}.",
            herb=herb.key,
        )
        return
    for name in split_ema_botanical_names(botanical):
        wfo_id, how, accepted_name = resolve_to_accepted_name(ctx, name)
        species = canonical_binomial(accepted_name) if accepted_name else None
        if wfo_id in curated_ids:
            ctx.stats["ema_botanical_names_verified"] += 1
        elif species and species != accepted_name and species in herb.taxa:
            # e.g. 'Cassia angustifolia Vahl' -> Senna alexandrina var. alexandrina: an
            # infraspecific taxon of a curated species is within that species' herbal substance.
            ctx.stats["ema_botanical_names_verified"] += 1
            ctx.issue(
                "ema_name_resolves_to_infraspecific_taxon",
                f"EMA botanical name '{name}' resolves to '{accepted_name}' ({how}), an infraspecific "
                f"taxon of curated species '{species}'.",
                severity=IssueSeverity.INFO,
                herb=herb.key,
                ema_name=name,
            )
        else:
            ctx.issue(
                "ema_botanical_name_not_in_curated_taxa",
                f"EMA botanical name '{name}' for {herb.ema_latin_name} resolves to {wfo_id or 'nothing'} ({how}), "
                "which is not one of the curated taxa.",
                severity=IssueSeverity.ERROR if wfo_id else IssueSeverity.WARNING,
                herb=herb.key,
                ema_name=name,
                inventory_record=str(record_id),
            )


def _record_extraction_quality(
    ctx: IngestionContext, herb: HerbEntry, monograph: Monograph, pdf: bytes, record: object
) -> dict[str, object]:
    from herbaguard.models import SourceRecord

    assert isinstance(record, SourceRecord)  # noqa: S101
    for warning in monograph.warnings:
        severity = IssueSeverity.ERROR if warning.code in _ERROR_WARNINGS else IssueSeverity.WARNING
        if (
            warning.code in {"complex_table", "duplicate_footnote_number"}
            and warning.section is None
        ):
            severity = IssueSeverity.INFO
        ctx.issue(
            f"ema_extraction:{warning.code}",
            warning.message,
            severity=severity,
            record=record,
            herb=herb.key,
            page=warning.page,
            section=warning.section,
            text=warning.text,
        )
    checks = crosscheck(pdf, monograph)
    coverage = document_token_coverage(pdf, monograph)
    for check in checks:
        if check.status == "mismatch":
            ctx.issue(
                "ema_crosscheck_mismatch",
                f"Section {check.section} ({check.use_category.value}) differs from PDFium: recall "
                f"{check.recall:.3f}, precision {check.precision:.3f}, order {check.sequence_ratio:.3f}.",
                severity=IssueSeverity.ERROR,
                record=record,
                herb=herb.key,
                section=check.section,
            )
    if coverage < 0.99:
        ctx.issue(
            "ema_low_token_coverage",
            f"Only {coverage:.4f} of PDF tokens accounted for.",
            severity=IssueSeverity.ERROR,
            record=record,
            herb=herb.key,
        )
    ctx.stats["ema_columns_verified"] += sum(c.status == "verified" for c in checks)
    ctx.stats["ema_columns_both_empty"] += sum(c.status == "both_empty" for c in checks)
    ctx.stats["ema_columns_mismatch"] += sum(c.status == "mismatch" for c in checks)
    return {
        "parser": PARSER_VERSION,
        "use_categories": [c.value for c in monograph.use_categories],
        "completeness": monograph.completeness(),
        "document_token_coverage": round(coverage, 4),
        "crosscheck": [
            {
                "section": c.section,
                "use_category": c.use_category.value,
                "status": c.status,
                "recall": round(c.recall, 4),
                "precision": round(c.precision, 4),
                "sequence_ratio": round(c.sequence_ratio, 4),
            }
            for c in checks
        ],
        "warnings": [w.code for w in monograph.warnings],
    }


def ingest_herb(
    ctx: IngestionContext,
    herb: HerbEntry,
    inventory: list[InventoryRow],
    inventory_record: object,
    resolver: DrugResolver,
    matcher: LexiconMatcher,
) -> None:
    from herbaguard.models import SourceRecord

    assert isinstance(inventory_record, SourceRecord)  # noqa: S101
    substances = substances_for_herb(ctx.session, herb.key)
    if not substances:
        ctx.issue(
            "herb_without_substances",
            f"Run taxonomy first: no substances for {herb.key}.",
            severity=IssueSeverity.ERROR,
            herb=herb.key,
        )
        return
    substance_ids = [s.id for s in substances]
    kept: set[uuid.UUID] = set()
    curated_ids = {ctx.session.get(Taxon, s.taxon_id).wfo_id for s in substances}  # type: ignore[union-attr]

    rows = [r for r in inventory if r.latin_name == herb.ema_latin_name and not r.combination]
    if len(rows) != 1:
        ctx.issue(
            "ema_inventory_row_count",
            f"{len(rows)} non-combination inventory rows for '{herb.ema_latin_name}'.",
            severity=IssueSeverity.ERROR if not rows else IssueSeverity.WARNING,
            herb=herb.key,
        )
        if not rows:
            return
    row = rows[0]
    _check_botanical_names(ctx, herb, row.botanical_name, curated_ids, inventory_record.id)

    page = ctx.fetch(row.url, native_id=row.url)
    finals, all_links = find_monograph_links(page.content.decode("utf-8", "replace"))
    if len(finals) != 1:
        ctx.issue(
            "ema_final_monograph_count",
            f"{len(finals)} final monograph links on {row.url}.",
            severity=IssueSeverity.ERROR if not finals else IssueSeverity.WARNING,
            record=page.record,
            herb=herb.key,
            links=finals,
        )
        if not finals:
            return
    pdf_url = f"{BASE}{finals[0]}"
    pdf = ctx.fetch(pdf_url, native_id=pdf_url)
    if not pdf.ok:
        ctx.issue(
            "ema_pdf_unavailable",
            f"HTTP {pdf.result.status_code} for {pdf_url}.",
            severity=IssueSeverity.ERROR,
            record=pdf.record,
            herb=herb.key,
        )
        return
    monograph = parse_monograph(pdf.content)
    pdf.record.source_version = monograph.document_number
    quality = _record_extraction_quality(ctx, herb, monograph, pdf.content, pdf.record)

    doc = monograph.document_number or pdf_url.rsplit("/", 1)[-1]
    common = {
        "url": pdf_url,
        "document_date": monograph.document_date
        if isinstance(monograph.document_date, date)
        else None,
        "publication_year": monograph.document_date.year if monograph.document_date else None,
        "is_superseded": False,
    }
    document_id = upsert_evidence(
        ctx.session,
        source_code=SOURCE,
        external_id=doc,
        evidence_type=EvidenceType.REGULATORY.value,
        title=monograph.title or f"EU herbal monograph {doc}",
        metadata_={
            "herb_key": herb.key,
            "ema_latin_name": herb.ema_latin_name,
            "herb_page": row.url,
            "inventory": {
                "status": row.status,
                "outcome": row.outcome,
                "last_updated": row.last_updated,
                "botanical_name": row.botanical_name,
            },
            "other_monograph_documents": [link for link in all_links if link != finals[0]],
            "footnotes": {k: f.text for k, f in monograph.footnotes.items()},
            "extraction": quality,
        },
        **common,
    )
    link_substance_evidence(
        ctx.session, substance_ids, document_id, EvidenceRelation.MONOGRAPH.value
    )
    ctx.provenance(
        "evidence_item",
        document_id,
        pdf.record,
        METHOD,
        version=PARSER_VERSION,
        location="whole document",
    )
    ctx.provenance(
        "evidence_item", document_id, page.record, METHOD, location="final monograph link"
    )

    for section in monograph.sections:
        if section.number not in CLINICAL_SECTIONS:
            continue
        for category, text in section.texts.items():
            if not text.strip():
                continue
            use = SECTION_USE[category]
            footnotes = {
                ref: monograph.footnotes[ref].text
                for ref in section.footnote_refs
                if ref in monograph.footnotes
            }
            evidence_id = upsert_evidence(
                ctx.session,
                source_code=SOURCE,
                external_id=f"{doc}#{section.number}#{use}",
                evidence_type=_evidence_type(section.number, category).value,
                title=f"{monograph.title or doc} — {section.number} {section.title} ({category.value.replace('_', ' ')})",
                metadata_={
                    "herb_key": herb.key,
                    "document": doc,
                    "section": section.number,
                    "section_title": section.title,
                    "use_category": category.value,
                    "pages": [section.first_page, section.last_page],
                    "footnotes": footnotes,
                    "section_statement": "none_reported" if none_reported(text) else None,
                },
                **common,
            )
            chunk_text = text + "".join(f"\n\n[{ref}] {note}" for ref, note in footnotes.items())
            replace_chunks(
                ctx.session,
                evidence_id,
                [
                    (
                        f"{section.number} {section.title}",
                        chunk_text,
                        {"use_category": category.value, "herb_key": herb.key},
                    )
                ],
            )
            link_substance_evidence(
                ctx.session, substance_ids, evidence_id, EvidenceRelation.MONOGRAPH.value
            )
            ctx.provenance(
                "evidence_item",
                evidence_id,
                pdf.record,
                METHOD,
                version=PARSER_VERSION,
                location=f"section {section.number}, {category.value}, pages {section.first_page}-{section.last_page}",
            )
            ctx.stats["ema_section_evidence"] += 1

            if section.number == "4.1":
                for indication in _split_indications(text):
                    for substance_id in substance_ids:
                        indication_id = upsert_indication(
                            ctx.session,
                            herbal_substance_id=substance_id,
                            evidence_item_id=evidence_id,
                            text=indication,
                            use_category=category.value,
                        )
                        ctx.provenance(
                            "indication",
                            indication_id,
                            pdf.record,
                            METHOD,
                            location=f"section 4.1, {category.value}",
                            excerpt=indication,
                        )
                    ctx.stats["indications"] += 1
            if section.number in ASSERTION_SECTIONS:
                _assertions(
                    ctx,
                    herb,
                    substance_ids,
                    evidence_id,
                    pdf.record,
                    section.number,
                    section.title,
                    category,
                    text,
                    resolver,
                    matcher,
                    kept,
                )

    ctx.stats["assertions_superseded"] += supersede_missing_assertions(
        ctx.session, source_code=SOURCE, substance_ids=substance_ids, kept_ids=kept
    )
    completeness = quality["completeness"]
    assert isinstance(completeness, dict)  # noqa: S101 - built by _record_extraction_quality
    for number, status in completeness.items():
        ctx.stats[f"section_{number}_{status}"] += 1
    ctx.stats["monographs"] += 1


def _assertions(
    ctx: IngestionContext,
    herb: HerbEntry,
    substance_ids: list[uuid.UUID],
    evidence_id: uuid.UUID,
    record: object,
    number: str,
    title: str,
    category: UseCategory,
    text: str,
    resolver: DrugResolver,
    matcher: LexiconMatcher,
    kept: set[uuid.UUID],
) -> None:
    from herbaguard.models import SourceRecord

    assert isinstance(record, SourceRecord)  # noqa: S101
    result = extract_from_monograph_text(matcher, text, section_title=title, section_number=number)
    flat_text = re.sub(r"\s+", " ", text)
    for phrase, sentence in result.unmapped:
        ctx.issue(
            "lexicon_term_unmapped",
            f"'{phrase}' recognised but has no drug/ATC mapping.",
            severity=IssueSeverity.INFO,
            record=record,
            herb=herb.key,
            section=number,
            sentence=sentence,
        )
    ctx.stats["descriptive_class_mentions_skipped"] += result.descriptive_skipped
    for candidate in result.candidates:
        if candidate.sentence not in flat_text:
            ctx.issue(
                "excerpt_not_in_source",
                "Extracted sentence is not a substring of the section text.",
                severity=IssueSeverity.ERROR,
                record=record,
                herb=herb.key,
                sentence=candidate.sentence,
            )
            continue
        objects: list[dict[str, object]] = []
        if candidate.hit.kind == "drug":
            ingredient = resolver.by_name(candidate.hit.key)
            if ingredient is None:
                continue
            objects.append({"drug_id": ingredient.drug_id})
        else:
            for code in candidate.hit.atc:
                if resolver.drug_class(code):
                    objects.append({"drug_class_code": code})
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
                    evidence_type=EvidenceType.REGULATORY.value,
                    source_section=number,
                    use_category=category.value,
                    mechanism=candidate.mechanism,
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
                    record,
                    "lexicon_extraction_v1",
                    location=f"section {number}, {category.value}",
                    excerpt=candidate.sentence,
                )
                ctx.stats[f"assertions_{candidate.statement_type.value}"] += 1


def run(ctx: IngestionContext, herb_keys: list[str] | None = None) -> None:
    ctx.register_local_file(
        CURATED_DIR / "interaction_lexicon.yaml",
        source_code="herbaguard_curated",
        native_id="data/curated/interaction_lexicon.yaml",
    )
    inventory_fetch = ctx.fetch(INVENTORY_URL, native_id="herbal_medicines_report")
    if not inventory_fetch.ok:
        ctx.issue(
            "ema_inventory_unavailable",
            f"HTTP {inventory_fetch.result.status_code}",
            severity=IssueSeverity.ERROR,
            record=inventory_fetch.record,
        )
        return
    inventory = parse_inventory(inventory_fetch.content)
    ctx.stats["inventory_rows"] = len(inventory)
    resolver = DrugResolver(ctx)
    matcher = LexiconMatcher(load_lexicon())
    for herb in load_herbs().herbs:
        if herb_keys and herb.key not in herb_keys:
            continue
        with ctx.per_item(f"ema:{herb.key}", resolver.reset):
            ingest_herb(ctx, herb, inventory, inventory_fetch.record, resolver, matcher)

    covered = set(REQUIRED_SECTIONS)
    ctx.stats["required_sections_checked"] = len(covered)
