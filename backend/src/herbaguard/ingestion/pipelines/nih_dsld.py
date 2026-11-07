"""NIH Dietary Supplement Label Database (DSLD) ingestion — product labels and ingredient composition.

Input: the DSLD bulk download in ``data/raw/nih_dsld/`` (CSV parts ``ProductOverview_*``,
``DietarySupplementFacts_*``, ``LabelStatements_*``, ``OtherIngredients_*``, ``CompanyInformation_*``
and ``ReadMe_*``; never modified; SHA-256 recorded per file). NIH Office of Dietary Supplements,
https://dsld.od.nih.gov/.

Scope and rules (docs/data/external-datasets.md):

* Only labels that list at least one ingredient whose name exactly matches a HerbaGuard herb name
  are imported (``repositories.plants.match_names`` rule). Other labels are counted and skipped.
* ``dsld_product`` — one entity per label (DSLD ID): the product overview row, every Supplement
  Facts row, the other-ingredients text and every label statement, all verbatim.
* ``dsld_ingredient`` — one entity per distinct matched ingredient name, mapped to a taxon
  (resolved / candidate / ambiguous, never by partial match). ``lists_ingredient`` relations from
  products carry the Supplement Facts row (amount, unit, category) verbatim.
* Labels are manufacturer statements, not evidence of an interaction: nothing is written to
  ``interaction_assertion`` or read by the A–E classification. Company contact data is not needed
  and is skipped.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from herbaguard.ingestion.context import IngestionContext
from herbaguard.ingestion.normalize.names import normalize_for_lookup
from herbaguard.ingestion.pipelines.external_common import (
    UNRESOLVED,
    ExternalWriter,
    HerbMatcher,
    Mapping,
    delete_stale,
)
from herbaguard.models import SourceRecord

SOURCE = "nih_dsld"
DOWNLOAD_PAGE = "https://dsld.od.nih.gov/"
LABEL_URL = "https://dsld.od.nih.gov/label/{}"
PARTS = ("ProductOverview", "DietarySupplementFacts", "LabelStatements", "OtherIngredients")
SKIPPED_PARTS = ("CompanyInformation", "ReadMe")


def read_rows(path: Path) -> Iterator[tuple[int, dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        yield from enumerate(csv.DictReader(handle), start=2)


def run(ctx: IngestionContext, directory: Path) -> None:
    writer = ExternalWriter(ctx, SOURCE, DOWNLOAD_PAGE)
    stats: Counter[str] = ctx.stats
    herbs = HerbMatcher(ctx.session)
    files: dict[str, list[tuple[Path, SourceRecord]]] = {}
    for part in (*PARTS, *SKIPPED_PARTS):
        paths = sorted(directory.glob(f"{part}_*.csv"))
        if part in PARTS and not paths:
            msg = f"DSLD files {part}_*.csv missing in {directory}"
            raise FileNotFoundError(msg)
        files[part] = [
            (p, writer.register(p, f"data/raw/nih_dsld/{p.name}", "text/csv")) for p in paths
        ]
    stats["files_skipped_company_information"] = len(files["CompanyInformation"])

    # 1. labels with at least one curated-herb ingredient (exact name)
    mapping_cache: dict[str, Mapping] = {}
    kept: set[str] = set()
    for path, _ in files["DietarySupplementFacts"]:
        for _, row in read_rows(path):
            stats["facts_rows"] += 1
            name = (row.get("Ingredient") or "").strip()
            if not name:
                continue
            key = normalize_for_lookup(name)
            if key not in mapping_cache:
                mapping_cache[key] = herbs.map(name)
            if mapping_cache[key].status != UNRESOLVED and (row.get("DSLD ID") or "").strip():
                kept.add(row["DSLD ID"].strip())
    stats["labels_with_curated_herb"] = len(kept)

    # 2. everything printed on those labels
    products: dict[str, dict[str, Any]] = defaultdict(lambda: {"overview": None, "supplement_facts": [],
                                                               "other_ingredients": [], "label_statements": []})  # fmt: skip
    rows_of: dict[str, list[int]] = defaultdict(list)
    record_of: dict[str, SourceRecord] = {}
    labels_seen: set[str] = set()
    for path, record in files["ProductOverview"]:
        for number, row in read_rows(path):
            dsld_id = (row.get("DSLD ID") or "").strip()
            if not dsld_id:
                stats["overview_rows_rejected_no_id"] += 1
                continue
            labels_seen.add(dsld_id)
            if dsld_id not in kept:
                continue
            if products[dsld_id]["overview"] is not None:
                stats["overview_duplicate_rows"] += 1
                continue
            products[dsld_id]["overview"] = row
            rows_of[dsld_id].append(number)
            record_of[dsld_id] = record
    stats["labels_in_download"] = len(labels_seen)
    stats["labels_skipped_no_curated_herb"] = len(labels_seen - kept)
    links: list[tuple[str, str, dict[str, str], SourceRecord, int]] = []
    for path, record in files["DietarySupplementFacts"]:
        for number, row in read_rows(path):
            dsld_id = (row.get("DSLD ID") or "").strip()
            if dsld_id not in kept:
                continue
            products[dsld_id]["supplement_facts"].append(row)
            key = normalize_for_lookup((row.get("Ingredient") or "").strip())
            if key and mapping_cache.get(key, Mapping(UNRESOLVED)).status != UNRESOLVED:
                links.append((dsld_id, key, row, record, number))
    for part, field in (
        ("OtherIngredients", "other_ingredients"),
        ("LabelStatements", "label_statements"),
    ):
        for path, _ in files[part]:
            for _, row in read_rows(path):
                dsld_id = (row.get("DSLD ID") or "").strip()
                if dsld_id in kept:
                    products[dsld_id][field].append(row)

    # 3. entities and relations
    product_rows: list[dict[str, Any]] = []
    for dsld_id in sorted(kept, key=lambda x: (len(x), x)):
        data = products[dsld_id]
        overview = data["overview"] or {}
        if not overview:
            stats["labels_without_overview_row"] += 1
        stats["label_statements_stored"] += len(data["label_statements"])
        product_rows.append(writer.entity("dsld_product", dsld_id, overview.get("Product Name") or None, data,
                                          {"dsld_id": dsld_id, "upc": overview.get("Bar Code"),
                                           "url": LABEL_URL.format(dsld_id)},
                                          record_of.get(dsld_id) or files["DietarySupplementFacts"][0][1],
                                          rows_of[dsld_id], Mapping("not_applicable", note="A product label.")))  # fmt: skip
    writer.upsert_entities(product_rows)
    ingredient_rows: dict[str, dict[str, Any]] = {}
    relations: list[dict[str, Any]] = []
    for dsld_id, key, row, record, number in links:
        if key not in ingredient_rows:
            ingredient_rows[key] = writer.entity("dsld_ingredient", key, row.get("Ingredient", "").strip(),
                                                 {"ingredient_name": row.get("Ingredient", "").strip(),
                                                  "dsld_ingredient_categories": row.get("DSLD Ingredient Categories")},
                                                 {}, record, [], mapping_cache[key])  # fmt: skip
        relations.append(writer.relation(writer.entity_id("dsld_product", dsld_id), "lists_ingredient",
                                         writer.entity_id("dsld_ingredient", key), row, record, [number]))  # fmt: skip
    writer.upsert_entities(list(ingredient_rows.values()))
    stats["relations_stored"] = writer.upsert_relations(relations)
    stats["relations_duplicate_rows"] = len(relations) - stats["relations_stored"]
    stats["ingredient_names_unmatched"] = sum(
        1 for m in mapping_cache.values() if m.status == UNRESOLVED
    )

    # 4. stale rows of earlier downloads (only after an error-free run)
    delete_stale(
        ctx,
        SOURCE,
        {e["id"] for e in [*product_rows, *ingredient_rows.values()]},
        {r["id"] for r in relations},
    )
    ctx.session.flush()
