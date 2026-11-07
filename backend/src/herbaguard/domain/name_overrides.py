"""Reviewed plant-name overrides (P0.1 of the 2026-11-07 dataset audit).

Exact-name lookup (``repositories.plants.match_names``) trusts every row of ``taxon_name``. Some
vernacular names from GBIF are not proof of identity (docs/data/sources.md): a name can belong to a
different plant, or be shared by several plants of which HerbaGuard holds only one. These reviewed
overrides correct that at lookup time, for every consumer (``/plants/resolve``, the interaction and
mechanism checks, the AI's question analysis, and the bulk mapping of external datasets).

The stored ``taxon_name`` rows are never deleted or changed, so the source names and their
provenance stay intact; an override only decides how a looked-up name may be used.

* ``not_this_taxon`` — the name must not resolve to the listed taxa (the stored row is wrong for
  that plant). If nothing else matches, the name is unresolved; the reason says what it refers to.
* ``ambiguous`` — the name is used for several plants; it is never resolved to one taxon, even when
  HerbaGuard holds only one of them. Use a specific name (scientific, pharmaceutical or qualified
  common name) instead.

Every entry records its evidence. Add an entry only after review; never by fuzzy matching.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from herbaguard.ingestion.normalize.names import normalize_for_lookup

OverrideAction = Literal["not_this_taxon", "ambiguous"]


@dataclass(frozen=True, slots=True)
class NameOverride:
    name: str
    action: OverrideAction
    reason: str
    evidence: tuple[str, ...]
    excluded_taxa: tuple[str, ...] = ()  # scientific names (not_this_taxon)
    refers_to: tuple[str, ...] = ()  # plants the name is used for (accepted names)


_OVERRIDES = (
    NameOverride(
        name="blessed thistle",
        action="not_this_taxon",
        excluded_taxa=("Silybum marianum",),
        refers_to=("Centaurea benedicta (L.) L.",),
        reason=(
            "'Blessed thistle' is Centaurea benedicta (L.) L. (syn. Cnicus benedictus L.), not "
            "Silybum marianum (milk thistle). Centaurea benedicta is not in HerbaGuard's taxonomy, "
            "so the name stays unresolved."
        ),
        evidence=(
            "POWO: Cnicus benedictus L. is a synonym of Centaurea benedicta "
            "(https://powo.science.kew.org/taxon/urn:lsid:ipni.org:names:196589-1)",
            "IPNI: Centaurea benedicta (L.) L., basionym Cnicus benedictus L. "
            "(https://www.ipni.org/n/190024-1)",
            "UMLS C1015220 'Centaurea Benedicta' lists 'blessed thistle' and 'Cnicus benedictus' "
            "(SUPP.AI cui_metadata.json, release 2021-10-20); milk thistle is a separate concept (C0937640)",
            "Source row: GBIF vernacular name 'Blessed thistle' on Silybum marianum",
        ),
    ),
    NameOverride(
        name="holy thistle",
        action="ambiguous",
        refers_to=("Silybum marianum (L.) Gaertn.", "Centaurea benedicta (L.) L."),
        reason=(
            "'Holy thistle' is used for both milk thistle (Silybum marianum) and blessed thistle "
            "(Centaurea benedicta); it does not identify one plant."
        ),
        evidence=(
            "UMLS C1015220 'Centaurea Benedicta' lists 'holy thistle' (SUPP.AI cui_metadata.json)",
            "Source row: GBIF vernacular name 'Holy Thistle' on Silybum marianum",
            "Found by the 2026-11-07 scan of UMLS names shared with curated taxa",
        ),
    ),
    NameOverride(
        name="neapolitan medlar",
        action="ambiguous",
        refers_to=("Crataegus azarolus L.", "Crataegus monogyna Jacq."),
        reason=(
            "'Neapolitan medlar' is given to Crataegus azarolus by UMLS but to Crataegus monogyna by "
            "GBIF; it does not identify one species."
        ),
        evidence=(
            "UMLS C1651460 'Crataegus Azarolus' lists 'Neapolitan medlar' (SUPP.AI cui_metadata.json)",
            "Source row: GBIF vernacular name 'Neapolitan medlar' on Crataegus monogyna",
            "Found by the 2026-11-07 scan of UMLS names shared with curated taxa",
        ),
    ),
    NameOverride(
        name="ginseng",
        action="ambiguous",
        refers_to=(
            "Panax ginseng C.A.Mey.",
            "Panax quinquefolius L.",
            "Eleutherococcus senticosus (Rupr. & Maxim.) Maxim.",
        ),
        reason=(
            "Bare 'ginseng' is used for Asian ginseng (Panax ginseng), American ginseng (Panax "
            "quinquefolius) and Siberian ginseng (Eleutherococcus senticosus). Name the species, "
            "the pharmaceutical name (Ginseng radix) or a qualified name (e.g. Asian ginseng)."
        ),
        evidence=(
            "UMLS C1119918 'Ginseng' is defined as the root of Panax quinquefolius but lists Asian "
            "and Chinese ginseng root as synonyms (SUPP.AI cui_metadata.json)",
            "NIH DSLD labels list 'American Ginseng' and 'Siberian Ginseng'/'Eleutherococcus "
            "senticosus' as separate ingredients (download 2026-01-10)",
            "HerbaGuard's own test rule: 'ginseng' must be ambiguous (tests/api/test_interactions_api.py)",
        ),
    ),
    NameOverride(
        name="black snakeroot",
        action="ambiguous",
        refers_to=("Actaea racemosa L.", "Asarum canadense L."),
        reason=(
            "'Black snakeroot' is used for black cohosh (Actaea racemosa) and for wild ginger "
            "(Asarum canadense); it does not identify one plant."
        ),
        evidence=(
            "UMLS C0771967 (black cohosh) and C0330224 (Asarum canadense, 'wild ginger / black "
            "snakeroot') both list the name (SUPP.AI cui_metadata.json)",
            "Source row: GBIF vernacular name 'black snakeroot' on Actaea racemosa",
        ),
    ),
)

OVERRIDES: dict[str, NameOverride] = {normalize_for_lookup(o.name): o for o in _OVERRIDES}


def override_for(name: str | None) -> NameOverride | None:
    """The reviewed override for a name (compared after ``normalize_for_lookup``), if any."""
    return OVERRIDES.get(normalize_for_lookup(name or "")) if name else None
