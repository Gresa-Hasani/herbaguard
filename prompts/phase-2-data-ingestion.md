# HerbaGuard — Phase 2 Prompt: Data Ingestion and Normalization

**Project:** HerbaGuard — EthnoHack 2026, Track 04: Digital Health & Phytotherapy
**Phase:** 2 of 8
**Depends on:** Phase 0 research (`docs/research/`) and the Phase 1 foundation (`docs/architecture/`, schema v1). Both approved by the user on 2026-11-02.

---

## Role

You are acting as Senior Data Engineer, Bioinformatics Engineer and Software Architect for HerbaGuard, an evidence-based herb–drug interaction and phytotherapy evidence platform.

## Objective

Implement reliable, reproducible, provenance-preserving ingestion of the **P0 data sources** selected in Phase 0 for the **curated MVP herb set** (16 herbs, `docs/research/mvp-scope.md` §4.1). Normalise plants to WFO identifiers and drugs to RxNorm ingredients, preserve every source identifier, store raw snapshots, record lineage, and validate the result.

## Sources in scope (P0)

| Source | What to ingest |
|---|---|
| WFO (ETHCSTWIN wrapper; official WFO matching API as fallback) | Accepted name, `wfo_id`, IPNI ID for each curated herb |
| WCVP, NCBI TaxTree (ETHCSTWIN wrappers), GBIF Species API, Wikidata | Cross-references (WCVP plant_name_id, NCBI tax_id, GBIF key, POWO, Wikidata QID), synonyms, native range, English vernacular names; Wikidata used as an independent crosswalk check |
| EMA HMPC | Herbal inventory spreadsheet; final, non-superseded EU herbal monograph PDF per herb; sections 4.1, 4.3, 4.4, 4.5, 4.6, 4.8 split by use category (well-established vs traditional use) |
| openFDA drug labels | Labels whose interaction-related sections mention a curated herb; drug-specific sentences |
| RxNorm / RxClass (RxNav) | Ingredient-level RxCUI for drugs; ATC classes and memberships |
| PubMed (E-utilities) | Herb–drug interaction literature and high-level clinical evidence per herb; evidence type derived deterministically from MeSH publication types |
| NCCIH Herbs at a Glance | Fact-sheet sections per herb, including safety text |

P1/P2 sources (FDA CYP table, CAERS, EFSA, ChEBI, ClinicalTrials.gov, etc.) and mechanism edges (`target_modulation`, `drug_target_role`) are **out of scope** for Phase 2 unless needed by a P0 task; document deferrals.

## Tasks

1. Save this prompt as `prompts/phase-2-data-ingestion.md` before implementation.
2. **Probe the real APIs first.** Record actual response structures for every endpoint used. Never infer a structure from documentation alone.
3. **Ingestion framework:**
   - HTTP client with polite User-Agent, timeouts, retry with exponential backoff on network errors / 429 / 5xx (tenacity), and per-host rate limiting.
   - Content-addressed raw snapshot store (`data/raw/`, git-ignored) and `source_record` rows (URL, parameters, HTTP status, content type, SHA-256, retrieval time, source version).
   - `ingestion_run` lifecycle (running → succeeded / partial / failed) with statistics.
   - `provenance` rows for every derived entity (extraction method and version, location, verbatim excerpt where the licence permits).
   - `data_quality_issue` rows instead of silently dropping problems.
   - Idempotent loading (re-running produces no duplicates); deterministic IDs for derived rows.
4. **Source connectors and adapters** for each P0 source, separating fetching (connector) from parsing (adapter) from loading.
5. **Taxonomic normalisation:** clean source name strings (e.g. EMA `Hypericum perforatumL.`), resolve to WFO accepted names, convert numeric WFO IDs to `wfo-NNNNNNNNNN`, resolve synonyms to accepted names, store synonyms / common / pharmaceutical names, and cross-check identifiers between backbones. Ambiguous or unresolved names must be recorded, never guessed.
6. **Drug normalisation:** RxNorm ingredient (TTY `IN`) RxCUIs; ATC classes via RxClass. Multi-ingredient label products must not be attributed to a single ingredient.
7. **EMA monograph processing:** discover the final monograph from the herb's EMA page; parse the two-column (WEU/TU) layout; remove running headers/footers; extract numbered sections; store each (section, use category) as an evidence item with retrieval chunks.
8. **Interaction assertions:** extract from EMA §4.3/§4.5, openFDA label sentences and NCCIH safety text using a **curated, committed lexicon** of drug and drug-class phrases (mapped to RxNorm/ATC). Keep the source's verbatim wording, sentence excerpt, use category and severity wording. Skip negated statements ("no interactions reported…") and count them. Every assertion's excerpt must be verifiable against stored source text.
9. **PubMed:** classify evidence type from publication types and MeSH (SR, RCT, CLIN, CASE, ANIMAL, INVITRO); store metadata and abstracts in the local database only (never committed).
10. **Herb ↔ evidence links:** schema migration for a substance–evidence association if required.
11. **Validation command** (`herbaguard validate`): every derived row has provenance; no orphan provenance; each curated herb resolves to exactly one accepted WFO taxon; no superseded EMA documents used as evidence; assertion excerpts found in source text; cross-backbone identifier agreement.
12. **Tests:** unit tests for normalisers, classifiers, parsers and the lexicon matcher; connector tests using **real responses captured from the APIs** (trimmed, with retrieval date; copyrighted abstract text removed); database integration tests for idempotency and provenance; opt-in `live` tests that call the real APIs.
13. **Run the real ingestion end-to-end** into the development database and report actual counts, issues and timings.
14. Document source-specific limitations, licences and the pipeline (`docs/data/`), and update the README.

## Constraints

- Do not present mocked or synthetic data as real integrations. Test fixtures must be labelled as captured (real, trimmed) or synthetic.
- Do not bypass CAPTCHAs, bot protection or authentication. Do not call admin endpoints of the ETHCSTWIN wrappers.
- Respect API limits (openFDA without key: 240 requests/minute, 1,000/day; NCBI without key: 3 requests/second).
- Never commit raw snapshots, PDFs, abstracts or restricted data. Curated tables authored by the project are committed.
- No API endpoints for domain data, no interaction classification logic, no AI — those are Phases 3–5.
- English for all documentation and comments.
- **Git:** never commit, push, amend, rebase, tag or create branches.

## Expected deliverables

- `backend/src/herbaguard/ingestion/` framework, connectors, adapters, normalisers, loaders, CLI commands (`ingest …`, `validate`, `report`)
- `data/curated/` committed curation files (herb list, interaction lexicon)
- Alembic migration(s) if the schema needs extending
- Tests (unit, connector with captured fixtures, database, live)
- `docs/data/` pipeline and source documentation
- Updated README
- This prompt

## Validation criteria

- Backend lint, format, `mypy --strict`, `alembic check` and the full test suite pass.
- Live tests pass against the real APIs (or failures are reported with the exact error).
- A real end-to-end ingestion run completes; counts per table and data-quality issues are reported.
- `herbaguard validate` passes or every failure is explained.
- Re-running ingestion creates no duplicates.

## Stopping condition

Produce the mandatory Phase 2 completion report (overview, implemented work, files, decisions, data sources with real verification, testing with actual results, known issues, git status, next-phase preview, suggested commit message and description). State that no commit or push was performed. **Stop and wait for explicit approval before Phase 3.**
