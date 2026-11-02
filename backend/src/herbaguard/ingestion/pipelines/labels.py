"""openFDA drug labels that mention a curated herb in interaction-related sections.

The label's own drug is the interacting drug; the herb is identified by the curated search
terms. Rules:

* Most recent labels first (``sort=effective_time:desc``), at most ``max_pages`` × 100 labels per
  herb (openFDA without an API key allows 1,000 requests/day). Coverage is reported against the
  number of distinct generic names openFDA counts for the same query.
* One label per generic name (the most recent).
* Multi-ingredient products are skipped: a statement on a combination label cannot be attributed
  to one ingredient.
* Sentences naming an excluded plant (e.g. "Siberian ginseng") are not attributed to the herb.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from herbaguard.domain.enums import EvidenceRelation, EvidenceType, IssueSeverity, UseCategory
from herbaguard.ingestion.context import IngestionContext
from herbaguard.ingestion.curation import HerbEntry, load_herbs
from herbaguard.ingestion.drugs import DrugResolver
from herbaguard.ingestion.loaders import (
    link_substance_evidence,
    replace_chunks,
    substances_for_herb,
    supersede_missing_assertions,
    upsert_assertion,
    upsert_evidence,
)
from herbaguard.ingestion.normalize.statements import classify_statement, split_sentences

SOURCE = "openfda_label"
URL = "https://api.fda.gov/drug/label.json"
FIELDS = (
    "drug_interactions",
    "contraindications",
    "warnings_and_cautions",
    "warnings",
    "precautions",
    "boxed_warning",
)
PAGE_SIZE = 100
MAX_EXCERPT = 600
METHOD = "openfda_label_v1"


def search_query(herb: HerbEntry) -> str:
    clauses = [f'{field}:"{term}"' for field in FIELDS for term in herb.openfda_terms]
    return "(" + " OR ".join(clauses) + ")"


def _term_pattern(terms: list[str]) -> re.Pattern[str]:
    variants = []
    for term in terms:
        escaped = (
            re.escape(term).replace(r"\.", r"\.?").replace("'", "['’]?").replace(r"\ ", r"\s+")
        )
        variants.append(escaped)
    return re.compile(r"(?<![\w-])(" + "|".join(variants) + r")(?![\w-])", re.IGNORECASE)


def mentioning_sentences(text: str, herb: HerbEntry) -> list[tuple[str, str]]:
    """(excerpt, matched herb wording) for sentences naming the herb and no excluded plant."""
    include = _term_pattern(herb.openfda_terms)
    exclude = _term_pattern(herb.openfda_exclude) if herb.openfda_exclude else None
    results = []
    for sentence in split_sentences(text):
        match = include.search(sentence)
        if not match or (exclude and exclude.search(sentence)):
            continue
        if len(sentence) > MAX_EXCERPT:
            # Flattened label tables produce run-on "sentences"; keep a verbatim window.
            start = max(0, match.start() - MAX_EXCERPT // 2)
            sentence = sentence[start : start + MAX_EXCERPT]
        results.append((sentence, match.group(0)))
    return results


def sentence_chunks(text: str, max_chars: int = 1500) -> list[str]:
    """Group sentences into chunks of at most ~max_chars without splitting a sentence."""
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for sentence in split_sentences(text):
        if current and size + len(sentence) > max_chars:
            chunks.append(" ".join(current))
            current, size = [], 0
        current.append(sentence)
        size += len(sentence) + 1
    if current:
        chunks.append(" ".join(current))
    return chunks


def _label_ingredient(
    ctx: IngestionContext, resolver: DrugResolver, label: dict[str, Any]
) -> tuple[Any, str]:
    openfda = label.get("openfda") or {}
    generic = (openfda.get("generic_name") or [""])[0]
    # A label may list several product RxCUIs (e.g. an oral-contraceptive pack with iron
    # placebo tablets). Ingredients are collected across ALL of them; anything other than exactly
    # one ingredient means the statement cannot be attributed to a single drug.
    ingredients: dict[str, Any] = {}
    resolved_any = False
    for rxcui in openfda.get("rxcui") or []:
        product = resolver.by_product_rxcui(rxcui, label=generic)
        if product is None:
            continue
        resolved_any = True
        if product.multi_ingredient:
            return None, "multi_ingredient"
        for ingredient in product.ingredients:
            ingredients[ingredient.rxcui] = ingredient
    if len(ingredients) > 1:
        return None, "multi_ingredient"
    if len(ingredients) == 1:
        return next(iter(ingredients.values())), "ok"
    if resolved_any:
        return None, "unresolved"
    if generic and " AND " not in generic.upper() and "," not in generic:
        by_name = resolver.by_name(generic)
        if by_name:
            return by_name, "ok"
    return None, "unresolved"


def ingest_herb(
    ctx: IngestionContext, herb: HerbEntry, resolver: DrugResolver, max_pages: int
) -> None:
    substance_ids = [s.id for s in substances_for_herb(ctx.session, herb.key)]
    kept: set[uuid.UUID] = set()
    query = search_query(herb)
    count = ctx.fetch(
        URL,
        params={"search": query, "count": "openfda.generic_name.exact", "limit": 1000},
        native_id=f"count:{herb.key}",
    )
    # openFDA answers 404 to a count when no matching label has harmonised `openfda` fields.
    generics_total: int | None = len(count.json().get("results") or []) if count.ok else None
    labels: list[dict[str, Any]] = []
    for page in range(max_pages):
        fetched = ctx.fetch(
            URL,
            params={
                "search": query,
                "sort": "effective_time:desc",
                "limit": PAGE_SIZE,
                "skip": page * PAGE_SIZE,
            },
            native_id=f"labels:{herb.key}:{page}",
        )
        if fetched.result.status_code == 404:
            break  # openFDA answers 404 NOT_FOUND when nothing matches
        if not fetched.ok:
            ctx.issue(
                "openfda_error",
                f"HTTP {fetched.result.status_code}",
                severity=IssueSeverity.ERROR,
                record=fetched.record,
                herb=herb.key,
            )
            break
        results = fetched.json().get("results") or []
        labels += [dict(r, _record=fetched.record) for r in results]
        if len(results) < PAGE_SIZE:
            break

    seen_generic: set[str] = set()
    captured = 0
    for label in labels:
        record = label.pop("_record")
        openfda = label.get("openfda") or {}
        generic = ((openfda.get("generic_name") or ["(no generic name)"])[0]).strip()
        if generic.lower() in seen_generic:
            ctx.stats["labels_duplicate_generic"] += 1
            continue
        seen_generic.add(generic.lower())
        sections = {f: " ".join(label.get(f) or []) for f in FIELDS if label.get(f)}
        hits = {f: mentioning_sentences(text, herb) for f, text in sections.items()}
        hits = {f: v for f, v in hits.items() if v}
        if not hits:
            ctx.stats["labels_no_attributable_sentence"] += (
                1  # e.g. only an excluded plant is named
            )
            continue
        ingredient, status = _label_ingredient(ctx, resolver, label)
        if ingredient is None:
            ctx.stats[f"labels_skipped_{status}"] += 1
            ctx.issue(
                f"label_{status}",
                f"Label for '{generic}' skipped ({status.replace('_', ' ')}).",
                severity=IssueSeverity.INFO,
                record=record,
                herb=herb.key,
                set_id=label.get("set_id"),
            )
            continue
        captured += 1
        brand = (openfda.get("brand_name") or [None])[0]
        for field, sentences in hits.items():
            evidence_id = upsert_evidence(
                ctx.session,
                source_code=SOURCE,
                external_id=f"{label['set_id']}#{field}",
                evidence_type=EvidenceType.REGULATORY.value,
                title=f"FDA label: {brand or generic} ({generic}) — {field.replace('_', ' ')}",
                url=f"https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={label['set_id']}",
                publication_year=int(str(label.get("effective_time", "0"))[:4]) or None,
                metadata_={
                    "set_id": label.get("set_id"),
                    "label_id": label.get("id"),
                    "version": label.get("version"),
                    "effective_time": label.get("effective_time"),
                    "generic_name": generic,
                    "brand_name": brand,
                    "manufacturer": (openfda.get("manufacturer_name") or [None])[0],
                    "product_rxcuis": openfda.get("rxcui"),
                },
            )
            # The whole section is stored (U.S. government text), split at sentence boundaries.
            # One label section can name several herbs; storing only one herb's sentences would
            # let the next herb's run overwrite the text that earlier excerpts point to.
            replace_chunks(
                ctx.session,
                evidence_id,
                [
                    (field, chunk, {"drug": ingredient.name})
                    for chunk in sentence_chunks(sections[field])
                ],
            )
            link_substance_evidence(
                ctx.session, substance_ids, evidence_id, EvidenceRelation.LABEL_MENTION.value
            )
            ctx.provenance(
                "evidence_item",
                evidence_id,
                record,
                METHOD,
                location=f"set_id={label['set_id']} {field}",
            )
            for sentence, herb_words in sentences:
                cues = classify_statement(sentence)
                for substance_id in substance_ids:
                    assertion_id = upsert_assertion(
                        ctx.session,
                        evidence_item_id=evidence_id,
                        key_text=sentence,
                        herbal_substance_id=substance_id,
                        drug_id=ingredient.drug_id,
                        object_label_verbatim=generic,
                        subject_label_verbatim=herb_words,
                        source_code=SOURCE,
                        evidence_type=EvidenceType.REGULATORY.value,
                        source_section=field,
                        use_category=UseCategory.NOT_APPLICABLE.value,
                        mechanism=None,
                        conditions=None,
                        severity_wording=cues.severity_wording,
                        statement_type=cues.statement_type.value,
                        status="active",
                    )
                    kept.add(assertion_id)
                    ctx.provenance(
                        "interaction_assertion",
                        assertion_id,
                        record,
                        METHOD,
                        location=f"set_id={label['set_id']} {field}",
                        excerpt=sentence,
                    )
                    ctx.stats[f"assertions_{cues.statement_type.value}"] += 1
    ctx.stats["assertions_superseded"] += supersede_missing_assertions(
        ctx.session, source_code=SOURCE, substance_ids=substance_ids, kept_ids=kept
    )
    ctx.stats["labels_fetched"] += len(labels)
    ctx.stats["labels_captured"] += captured
    ctx.issue(
        "openfda_coverage",
        f"{herb.key}: {len(labels)} labels fetched (cap {max_pages * PAGE_SIZE}), {len(seen_generic)} distinct generic names "
        f"seen of {generics_total if generics_total is not None else 'an uncountable number (labels lack openFDA harmonised fields)'} "
        f"counted by openFDA; {captured} single-ingredient labels with attributable sentences.",
        severity=IssueSeverity.INFO,
        record=count.record,
        herb=herb.key,
        labels_fetched=len(labels),
        generics_seen=len(seen_generic),
        generics_total=generics_total,
        captured=captured,
    )


def run(ctx: IngestionContext, herb_keys: list[str] | None = None, max_pages: int = 5) -> None:
    resolver = DrugResolver(ctx)
    for herb in load_herbs().herbs:
        if herb_keys and herb.key not in herb_keys:
            continue
        with ctx.per_item(f"labels:{herb.key}", resolver.reset):
            ingest_herb(ctx, herb, resolver, max_pages)
