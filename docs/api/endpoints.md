# API Endpoints (v1)

**Status:** Implemented in Phase 3. Interactive documentation: `http://localhost:18010/api/docs`; schema: `/api/openapi.json`. Conventions (errors, pagination, provenance): [../architecture/api-conventions.md](../architecture/api-conventions.md). Classification rules: [interaction-classification.md](interaction-classification.md).

All list endpoints return `{items, total, limit, offset}` with `limit` 1–100 (default 20). All errors use `{"error": {code, message, details, request_id}}`. Requests that carry medication names use POST.

## Plants and herbs

| Method & path | Purpose | Parameters | Notes |
|---|---|---|---|
| `GET /api/v1/plants` | Search taxa by any name type | `q` (1–200 chars), `limit`, `offset` | Ranks exact > prefix > substring, accepted > pharmaceutical > common > synonym; returns `matched_name` |
| `GET /api/v1/plants/resolve` | Resolve a name to one curated herb | `name` | `status`: resolved / ambiguous (with candidates) / not_found; notes for common-name, synonym and partial matches |
| `GET /api/v1/plants/{wfo_id}` | Plant detail | `wfo_id` = `wfo-NNNNNNNNNN` | Identifiers (WFO, IPNI, WCVP, GBIF, NCBI, POWO, Wikidata), names, native range, indications (WEU/TU separate, with provenance), monograph completeness and "None reported" sections, counts, taxon provenance |
| `GET /api/v1/plants/{wfo_id}/interactions` | All active statements for the plant, grouped by drug or ATC class | `statement_type` (repeatable), `source` | Each statement with excerpt, conditions, severity wording, subject check, evidence and provenance |

## Drugs

| Method & path | Purpose | Notes |
|---|---|---|
| `GET /api/v1/drugs?q=` | Search the drug index | Ingredient level, with ATC classes |
| `GET /api/v1/drugs/{rxcui}` | Drug detail | With provenance (RxNav records) |
| `POST /api/v1/drugs/resolve` | `{name, allow_remote}` → RxNorm ingredient | Database first; RxNav live lookup recorded as an `rxnav` ingestion run with raw snapshots. Brand names resolve (e.g. "Coumadin" → warfarin). Status: resolved / not_found / lookup_failed |
| `GET /api/v1/drug-classes/{code}` | ATC class and drugs in it | `code` validated as an ATC code |

## Evidence

| Method & path | Parameters | Notes |
|---|---|---|
| `GET /api/v1/evidence` | `wfo_id`, `herb` (pharmaceutical name), `source` (ema_hmpc, nccih, openfda_label, pubmed), `evidence_type` (repeatable), `relation`, `year_from`, `year_to`, `q` (title + full-text search of stored text), `limit`, `offset` | Each item has `evidence_type: {code, label, basis, quality_assessed: false, note}` — **type is study design / document kind, never a quality rating** |
| `GET /api/v1/evidence/{id}` | — | Stored text (local database only), linked herbs and relations, provenance |

## Interactions

| Method & path | Body | Response |
|---|---|---|
| `POST /api/v1/interactions/check` | `{herb: str, drugs: [str] (1–20), allow_remote_drug_lookup: bool}` | Herb resolution; per drug: resolution, classification (class, finding, labels, explanation, reasons, verbatim severity wordings, caveats, method), decisive and context statements with full provenance, sources searched (with `used_for_classification`), related literature (not used for classification). **409** if the herb name is ambiguous (candidates in `error.details`). |

Example (abridged, real data):

```json
{
  "herb": {"query": "St John's wort", "status": "resolved", "herb": {"pharmaceutical_name": "Hyperici herba"}},
  "results": [{
    "drug": {"query": "warfarin", "status": "resolved", "resolved_via": "database", "drug": {"rxcui": "11289", "name": "warfarin"}},
    "classification": {
      "interaction_class": "A", "finding": "documented_interaction",
      "severity_wordings": ["Contraindications", "is contraindicated"],
      "method": "deterministic rules v1 (docs/api/interaction-classification.md); no machine learning or LLM"
    },
    "decisive_statements": [{
      "statement_type": "interaction", "source_code": "ema_hmpc", "source_section": "4.5",
      "use_category": "traditional_use", "matched_via": "class", "drug_class": {"code": "B01AA"},
      "conditions": "Indications 1), 3) and 4); Daily dose of hyperforin > 1 mg",
      "excerpt": "Concomitant use with coumarin-type anticoagulants, cyclosporine, …",
      "subject_check": "not_applicable",
      "evidence": {"external_id": "EMA/HMPC/7695/2021#4.5#TU", "evidence_type": {"code": "REG", "quality_assessed": false}},
      "provenance": [{"source_code": "ema_hmpc", "retrieved_url": "https://www.ema.europa.eu/…pdf", "retrieved_at": "2026-11-02T12:53:…", "location": "section 4.5, traditional_use"}]
    }]
  }]
}
```

## Mechanism layer (Phase 4)

| Method & path | Purpose | Notes |
|---|---|---|
| `GET /api/v1/targets` | Enzymes and transporters | UniProt accession and link, counts of herb effects and drug roles |
| `GET /api/v1/targets/{symbol}` | One target | `role` filter, `limit` (≤500); herb effects and drug roles with provenance; note that FDA lists examples only |
| `GET /api/v1/plants/{wfo_id}/mechanisms` | Knowledge-graph JSON for a herb | Nodes herb / constituent / target / drug, edges contains / induces / inhibits / substrate_of with statement ids; `include_drugs` (default true, ≤200 drugs) |
| `POST /api/v1/mechanisms/paths` | Paths between one herb and one drug | `{herb, drug, allow_remote_drug_lookup}`; each path with `qualifies_for_class_b` and `reasons_not_qualifying`; **409** for ambiguous herbs |

The interaction check (`POST /api/v1/interactions/check`) returns `mechanism_paths` per drug. Rules: [mechanism-paths.md](mechanism-paths.md).

## Sources and coverage

| Method & path | Purpose |
|---|---|
| `GET /api/v1/sources` | Registered sources: provider, licence, licence verification status, redistributable, last run status/time, number of raw records |
| `GET /api/v1/coverage` | Per curated herb: species count, monograph and date, fact sheet, openFDA label coverage, evidence counts by relation, active statement counts by type, PubMed records by type (with the type-is-not-quality note) |

## Health and metadata (Phase 1)

`GET /api/v1/health`, `GET /api/v1/health/ready`, `GET /api/v1/meta` (includes the canonical disclaimer).
