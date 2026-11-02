"""Taxonomic normalisation of the curated herbs.

For every accepted name in ``data/curated/herbs.yaml``:

1. WFO (ETHCSTWIN wrapper; official WFO matching API as fallback) → ``wfo_id``, family, IPNI ID.
2. WCVP → ``plant_name_id``, POWO ID, native range, NCBI tax_id, and the synonym list.
3. NCBI TaxTree → ``tax_id`` (cross-checked against WCVP).
4. GBIF → backbone key (exact accepted match required) and English vernacular names.
5. Wikidata → QID and an independent crosswalk check of IPNI / GBIF / NCBI identifiers.

Disagreements are recorded as data-quality issues; nothing is silently overwritten.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from herbaguard.domain.enums import IssueSeverity, NameType
from herbaguard.ingestion.context import Fetched, IngestionContext
from herbaguard.ingestion.curation import CURATED_DIR, HerbEntry, load_herbs
from herbaguard.ingestion.loaders import add_taxon_name, upsert_substance, upsert_taxon
from herbaguard.ingestion.normalize.names import (
    canonical_binomial,
    format_wfo_id,
    normalize_for_lookup,
)

METHOD = "taxonomy_v1"
ETHCSTWIN = "ethcstwin.di.uoa.gr:65000"
WFO_WRAPPER = f"https://wfo.{ETHCSTWIN}"
WCVP_WRAPPER = f"https://wcvp.{ETHCSTWIN}"
TAXTREE_WRAPPER = f"https://taxtree.{ETHCSTWIN}"
WFO_OFFICIAL = "https://list.worldfloraonline.org/matching_rest.php"
GBIF = "https://api.gbif.org/v1"
WIKIDATA = "https://query.wikidata.org/sparql"
SYNONYM_STATUSES = {"Synonym", "Orthographic", "Illegitimate", "Invalid"}  # never "Misapplied"


@dataclass(slots=True)
class WfoMatch:
    wfo_id: str
    name: str
    full_name: str
    family: str | None
    role: str
    ipni: str | None
    record: Fetched


def wfo_lookup(ctx: IngestionContext, name: str) -> WfoMatch | None:
    """Find the WFO record for a name (without authors).

    WFO can hold several records for one name string with different authorships, e.g.
    *Glycyrrhiza uralensis* Fisch. (unplaced, wfo-0000186028) and *G. uralensis* Fisch. ex DC.
    (accepted, wfo-0001053609). The wrapper's ``first_hit`` returns whichever comes first, so all
    records are retrieved and the single accepted one is chosen. Several accepted records →
    ambiguous (recorded, not guessed). No accepted record → a synonym record is returned so the
    caller can resolve it through WCVP. Falls back to the official WFO matching API.
    """
    try:
        fetched = ctx.fetch(
            f"{WFO_WRAPPER}/names/",
            params={"full_name_no_authors": name, "limit": 50},
            native_id=f"names:{name}",
            source_code="wfo_ethcstwin",
        )
        rows = (fetched.json().get("results") or []) if fetched.ok else []
    except Exception as exc:
        ctx.issue("wfo_wrapper_unavailable", f"WFO wrapper failed for '{name}': {exc}", name=name)
        rows, fetched = [], None
    accepted = [r for r in rows if r.get("role") == "accepted"]
    if len(accepted) > 1:
        ctx.issue(
            "wfo_ambiguous_name",
            f"'{name}' matches {len(accepted)} accepted WFO records; none chosen.",
            severity=IssueSeverity.ERROR,
            record=fetched.record if fetched else None,
            wfo_ids=[r["id"] for r in accepted],
        )
        return None
    if len(rows) > 1 and accepted:
        ctx.stats["wfo_homonym_records_disambiguated"] += 1
    chosen = (
        accepted[0]
        if accepted
        else next((r for r in rows if r.get("role") == "synonym"), rows[0] if rows else None)
    )
    if chosen and fetched:
        family = chosen.get("family")
        return WfoMatch(
            wfo_id=format_wfo_id(chosen["id"]),
            name=chosen["full_name_no_authors"],
            full_name=chosen["full_name_plain"],
            family=family.get("name") if isinstance(family, dict) else family,
            role=chosen.get("role") or "unknown",
            ipni=chosen.get("ipni"),
            record=fetched,
        )
    try:
        official = ctx.fetch(
            WFO_OFFICIAL,
            params={"input_string": name},
            native_id=f"match:{name}",
            source_code="wfo",
        )
    except Exception as exc:
        ctx.issue(
            "wfo_official_unavailable", f"Official WFO API failed for '{name}': {exc}", name=name
        )
        return None
    match = (official.json() or {}).get("match") if official.ok else None
    if not match:
        return None
    ctx.issue(
        "wfo_official_fallback_used",
        f"Official WFO API used for '{name}'.",
        severity=IssueSeverity.INFO,
        record=official.record,
    )
    full = match.get("full_name_plain", name)
    return WfoMatch(
        wfo_id=format_wfo_id(match["wfo_id"]),
        name=canonical_binomial(full) or name,
        full_name=full,
        family=None,
        role=match.get("role", "accepted"),
        ipni=None,
        record=official,
    )


def wcvp_by_name(ctx: IngestionContext, name: str) -> tuple[dict[str, Any] | None, Fetched]:
    fetched = ctx.fetch(
        f"{WCVP_WRAPPER}/plants/",
        params={"taxon_name": name, "limit": 20},
        native_id=f"plants:{name}",
        source_code="wcvp_ethcstwin",
    )
    rows = (fetched.json().get("results") or []) if fetched.ok else []
    rows = [r for r in rows if r.get("taxon_rank") == "Species"]
    accepted = [r for r in rows if r.get("taxon_status") == "Accepted"]
    if accepted:
        return accepted[0], fetched
    return (rows[0] if rows else None), fetched


def resolve_to_accepted(ctx: IngestionContext, name: str) -> tuple[str | None, str]:
    wfo_id, how, _ = resolve_to_accepted_name(ctx, name)
    return wfo_id, how


def resolve_to_accepted_name(
    ctx: IngestionContext, name: str
) -> tuple[str | None, str, str | None]:
    """Like ``resolve_to_accepted`` but also returns the accepted name (e.g. an infraspecific
    taxon such as 'Senna alexandrina var. alexandrina')."""
    wfo_id, how, accepted = _resolve(ctx, name)
    return wfo_id, how, accepted


def _resolve(ctx: IngestionContext, name: str) -> tuple[str | None, str, str | None]:
    """Resolve any botanical name (accepted or synonym) to an accepted ``wfo_id``.

    Returns (wfo_id or None, explanation). Synonyms go via WCVP ``accepted_plant_name_id``,
    because WFO first-hit records of synonyms do not name the accepted taxon.
    """
    binomial = canonical_binomial(name) or name
    match = wfo_lookup(ctx, binomial)
    if match is None:
        return None, "no WFO match", None
    if match.role == "accepted":
        return match.wfo_id, f"WFO accepted ({match.wfo_id})", match.name
    row, _ = wcvp_by_name(ctx, binomial)
    accepted_id = row.get("accepted_plant_name_id") if row else None
    if not accepted_id:
        return None, f"WFO role '{match.role}', no WCVP accepted name", None
    accepted_fetch = ctx.fetch(
        f"{WCVP_WRAPPER}/plants/",
        params={"plant_name_id": accepted_id},
        native_id=f"plant_name_id:{accepted_id}",
        source_code="wcvp_ethcstwin",
    )
    accepted_rows = (accepted_fetch.json().get("results") or []) if accepted_fetch.ok else []
    if not accepted_rows:
        return None, f"WCVP accepted id {accepted_id} not found", None
    accepted_match = wfo_lookup(ctx, accepted_rows[0]["taxon_name"])
    if accepted_match is None or accepted_match.role != "accepted":
        return None, f"accepted name '{accepted_rows[0]['taxon_name']}' not accepted in WFO", None
    return (
        accepted_match.wfo_id,
        f"synonym of {accepted_rows[0]['taxon_name']} (WCVP {accepted_id}) → {accepted_match.wfo_id}",
        accepted_match.name,
    )


def _ncbi_tax_id(ctx: IngestionContext, name: str) -> tuple[int | None, Fetched]:
    fetched = ctx.fetch(
        f"{TAXTREE_WRAPPER}/names/search/",
        params={"name_txt": name, "name_class": "scientific name", "limit": 5},
        native_id=f"names:{name}",
        source_code="taxtree_ethcstwin",
    )
    rows = (fetched.json().get("results") or []) if fetched.ok else []
    ids = {r["tax_id"] for r in rows if r.get("name_txt") == name}
    return (ids.pop() if len(ids) == 1 else None), fetched


def _gbif(ctx: IngestionContext, name: str) -> tuple[int | None, Fetched, list[str]]:
    fetched = ctx.fetch(
        f"{GBIF}/species/match",
        params={"name": name, "kingdom": "Plantae", "strict": "true"},
        native_id=f"match:{name}",
        source_code="gbif",
    )
    data = fetched.json() if fetched.ok else {}
    key = (
        data.get("usageKey")
        if data.get("status") == "ACCEPTED" and data.get("matchType") == "EXACT"
        else None
    )
    vernacular: list[str] = []
    if key:
        names = ctx.fetch(
            f"{GBIF}/species/{key}/vernacularNames",
            params={"limit": 300},
            native_id=f"vernacular:{key}",
            source_code="gbif",
        )
        seen: set[str] = set()
        for row in (names.json().get("results") or []) if names.ok else []:
            if row.get("language") == "eng" and row.get("vernacularName"):
                normalized = normalize_for_lookup(row["vernacularName"])
                if normalized not in seen:
                    seen.add(normalized)
                    vernacular.append(row["vernacularName"])
    return key, fetched, vernacular


def _wikidata(ctx: IngestionContext, wfo_id: str) -> tuple[dict[str, str], Fetched]:
    query = (
        'SELECT ?item ?ipni ?gbif ?ncbi WHERE { ?item wdt:P7715 "' + wfo_id + '" . '
        "OPTIONAL { ?item wdt:P961 ?ipni } OPTIONAL { ?item wdt:P846 ?gbif } OPTIONAL { ?item wdt:P685 ?ncbi } }"
    )
    fetched = ctx.fetch(
        WIKIDATA,
        params={"query": query, "format": "json"},
        native_id=f"wfo:{wfo_id}",
        source_code="wikidata",
    )
    bindings = (fetched.json().get("results") or {}).get("bindings") or [] if fetched.ok else []
    if not bindings:
        return {}, fetched
    first = bindings[0]
    return {k: v["value"] for k, v in first.items()}, fetched


def ingest_taxon(ctx: IngestionContext, herb: HerbEntry, name: str) -> uuid.UUID | None:
    match = wfo_lookup(ctx, name)
    if match is None or match.role != "accepted":
        ctx.issue(
            "curated_taxon_not_accepted",
            f"Curated name '{name}' ({herb.key}) is not an accepted WFO name (role: {match.role if match else 'no match'}).",
            severity=IssueSeverity.ERROR,
            herb=herb.key,
        )
        return None
    wcvp, wcvp_fetch = wcvp_by_name(ctx, match.name)
    tax_id, taxtree_fetch = _ncbi_tax_id(ctx, match.name)
    gbif_key, gbif_fetch, vernacular = _gbif(ctx, match.name)
    wikidata, wikidata_fetch = _wikidata(ctx, match.wfo_id)

    wcvp_tax = wcvp.get("tax_id") if wcvp else None
    if tax_id is None and wcvp_tax:
        tax_id = int(wcvp_tax)
        ctx.issue(
            "ncbi_from_wcvp",
            f"TaxTree had no unique match for '{match.name}'; NCBI id taken from WCVP.",
            severity=IssueSeverity.INFO,
            herb=herb.key,
        )
    checks = {
        "ipni (WFO vs WCVP)": (match.ipni, wcvp.get("ipni_id") if wcvp else None),
        "ncbi (TaxTree vs WCVP)": (tax_id, int(wcvp_tax) if wcvp_tax else None),
        "ipni (WFO vs Wikidata)": (match.ipni, wikidata.get("ipni")),
        "gbif (GBIF vs Wikidata)": (
            gbif_key,
            int(wikidata["gbif"]) if wikidata.get("gbif") else None,
        ),
        "ncbi (TaxTree vs Wikidata)": (
            tax_id,
            int(wikidata["ncbi"]) if wikidata.get("ncbi") else None,
        ),
    }
    for label, (a, b) in checks.items():
        if a is not None and b is not None and str(a) != str(b):
            ctx.issue(
                "identifier_mismatch",
                f"{match.name}: {label} disagree ({a} vs {b}).",
                herb=herb.key,
                check=label,
                values=[str(a), str(b)],
            )
        elif a is None or b is None:
            ctx.stats[f"crosscheck_incomplete:{label}"] += 1
        else:
            ctx.stats["crosscheck_agree"] += 1
    if wcvp is None:
        ctx.issue("wcvp_no_match", f"No WCVP species record for '{match.name}'.", herb=herb.key)

    authorship = match.full_name[len(match.name) :].strip() or None
    taxon_id = upsert_taxon(
        ctx.session,
        wfo_id=match.wfo_id,
        scientific_name=match.name,
        authorship=authorship,
        family=match.family or (wcvp.get("family") if wcvp else None),
        rank="species",
        taxonomic_status="accepted",
        ipni_id=match.ipni or (wcvp.get("ipni_id") if wcvp else None),
        wcvp_plant_name_id=wcvp.get("plant_name_id") if wcvp else None,
        gbif_key=gbif_key,
        ncbi_tax_id=tax_id,
        powo_id=wcvp.get("powo_id") if wcvp else None,
        wikidata_id=wikidata.get("item", "").rsplit("/", 1)[-1] or None,
        native_range=wcvp.get("geographic_area") if wcvp else None,
    )
    for fetched, location in (
        (match.record, "wfo_id, scientific_name, family, ipni_id"),
        (wcvp_fetch, "wcvp_plant_name_id, powo_id, native_range"),
        (taxtree_fetch, "ncbi_tax_id"),
        (gbif_fetch, "gbif_key"),
        (wikidata_fetch, "wikidata_id (crosswalk check)"),
    ):
        ctx.provenance("taxon", taxon_id, fetched.record, METHOD, location=location)

    add_taxon_name(
        ctx.session,
        taxon_id=taxon_id,
        name=match.name,
        name_type=NameType.ACCEPTED,
        language="la",
        source_code=match.record.record.source_code,
        source_native_id=match.wfo_id,
    )
    if wcvp and wcvp.get("plant_name_id"):
        # The WCVP wrapper caps `limit` at 100 (HTTP 422 above that), so page through.
        offset, total = 0, None
        while total is None or offset < total:
            synonyms = ctx.fetch(
                f"{WCVP_WRAPPER}/plants/",
                params={
                    "accepted_plant_name_id": wcvp["plant_name_id"],
                    "limit": 100,
                    "offset": offset,
                },
                native_id=f"synonyms:{wcvp['plant_name_id']}:{offset}",
                source_code="wcvp_ethcstwin",
            )
            if not synonyms.ok:
                ctx.issue(
                    "wcvp_synonyms_failed",
                    f"HTTP {synonyms.result.status_code} for synonyms of {match.name}.",
                    record=synonyms.record,
                    herb=herb.key,
                )
                break
            body = synonyms.json()
            total = int(body.get("count") or 0)
            rows = body.get("results") or []
            for row in rows:
                if row.get("taxon_status") in SYNONYM_STATUSES and row.get("taxon_name"):
                    add_taxon_name(
                        ctx.session,
                        taxon_id=taxon_id,
                        name=row["taxon_name"],
                        name_type=NameType.SYNONYM,
                        language="la",
                        source_code="wcvp_ethcstwin",
                        source_native_id=str(row["plant_name_id"]),
                    )
                    ctx.stats["synonyms"] += 1
                elif row.get("taxon_status") == "Misapplied":
                    ctx.stats["misapplied_names_excluded"] += 1
            if not rows:
                break
            offset += len(rows)
    for vernacular_name in vernacular:
        add_taxon_name(
            ctx.session,
            taxon_id=taxon_id,
            name=vernacular_name,
            name_type=NameType.COMMON,
            language="en",
            source_code="gbif",
        )
        ctx.stats["gbif_vernacular_names"] += 1
    ctx.stats["taxa"] += 1
    return taxon_id


def run(ctx: IngestionContext, herb_keys: list[str] | None = None) -> None:
    herbs = load_herbs()
    curation = ctx.register_local_file(
        CURATED_DIR / "herbs.yaml",
        source_code="herbaguard_curated",
        native_id="data/curated/herbs.yaml",
    )
    for herb in herbs.herbs:
        if herb_keys and herb.key not in herb_keys:
            continue
        with ctx.per_item(f"taxonomy:{herb.key}"):
            _ingest_herb(ctx, herb, curation)


def _ingest_herb(ctx: IngestionContext, herb: HerbEntry, curation: object) -> None:
    from herbaguard.models import SourceRecord

    assert isinstance(curation, SourceRecord)  # noqa: S101
    if True:
        for name in herb.taxa:
            taxon_id = ingest_taxon(ctx, herb, name)
            if taxon_id is None:
                continue
            substance_id = upsert_substance(
                ctx.session,
                taxon_id=taxon_id,
                plant_part=herb.plant_part,
                pharmaceutical_name=herb.ema_latin_name,
                common_name_en=herb.common_name,
                in_curated_scope=True,
            )
            ctx.provenance(
                "herbal_substance", substance_id, curation, METHOD, location=f"herbs[{herb.key}]"
            )
            add_taxon_name(
                ctx.session,
                taxon_id=taxon_id,
                name=herb.common_name,
                name_type=NameType.COMMON,
                language="en",
                source_code="herbaguard_curated",
            )
            add_taxon_name(
                ctx.session,
                taxon_id=taxon_id,
                name=herb.ema_latin_name,
                name_type=NameType.PHARMACEUTICAL,
                language="la",
                source_code="herbaguard_curated",
            )
            ctx.stats["substances"] += 1
