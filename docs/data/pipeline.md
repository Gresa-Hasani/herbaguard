# Data Pipeline (Phase 2)

**Status:** Implemented and run end-to-end against the live sources on 2026-11-02. Actual results are in [ingestion-results.md](ingestion-results.md); EMA extraction validation is in [ema-extraction-validation.md](ema-extraction-validation.md); per-source notes and licences are in [sources.md](sources.md).

## 1. Running it

Requires the database from Docker Compose (`docker compose up -d db`) and the backend virtualenv.

```bash
cd backend
herbaguard ingest all            # sources → taxonomy → ema → nccih → labels → pubmed → mechanisms (~5–7 min)
herbaguard validate              # post-ingestion checks; exit code 1 on failure
herbaguard report                # counts, latest runs, data-quality issues
herbaguard ema-report            # per-monograph, per-section extraction table (Markdown)
```

Individual steps: `herbaguard ingest taxonomy|ema|nccih|labels|pubmed|mechanisms [--herb st_johns_wort ...]`, `herbaguard ingest mechanisms --fda-html-file page.html` (Phase 4; a browser-saved copy of the FDA CYP/transporter page if fda.gov refuses automated requests), `herbaguard ingest labels --max-pages N` (openFDA pages of 100 labels per herb; default 5). External datasets from local downloads (no network access): `herbaguard ingest ddid|supp-ai|livertox|nih-dsld [--directory …]` — see [ddid.md](ddid.md) and [external-datasets.md](external-datasets.md).

Optional environment: `NCBI_API_KEY` (raises the E-utilities limit from 3 to 10 requests/s), `HERBAGUARD_CONTACT_EMAIL` (sent as `From`).

Re-running is safe: every step upserts on natural keys or deterministic UUIDs (UUIDv5 of the identifying fields), so a re-run updates rows in place and creates no duplicates (tested).

## 2. Architecture

```
            ┌──────────── data/curated/ (committed) ────────────┐
            │ herbs.yaml (16 herbs)   interaction_lexicon.yaml   │
            └────────────────────────────┬──────────────────────┘
                                         │ registered as source_record (herbaguard_curated)
 HTTP (retries, rate limits,  ──►  IngestionContext.fetch()  ──►  data/raw/<source>/<sha>.<ext>[.gz]
 verified TLS)                      │ source_record (URL, params, status, SHA-256, retrieved_at)
                                    ▼
                       parsers (pure functions, no I/O)
        ema_inventory · ema_monograph (+ ema_crosscheck) · nccih_html · pubmed_xml
                                    ▼
             normalisers: names · statements · lexicon · evidence_type
                                    ▼
                loaders (idempotent upserts) + provenance + data_quality_issue
                                    ▼
            PostgreSQL (schema v1 + migration 0002) ──► herbaguard validate
```

| Module | Responsibility |
|---|---|
| `ingestion/http.py` | `httpx` client: User-Agent with contact URL, timeouts, per-host minimum intervals, retries (tenacity, exponential backoff with jitter) on network errors / 429 / 5xx; 4xx returned to the caller. TLS verification always on (see §5). |
| `ingestion/raw_store.py` | Content-addressed snapshots; text formats gzip-compressed; hash of the uncompressed bytes. |
| `ingestion/context.py` | `run_ingestion` (run lifecycle), `fetch` (snapshot + `source_record`), `provenance`, `issue`, `per_item` (isolates one herb: network failure → rollback of that herb, error issue, run continues as `partial`). |
| `ingestion/curation.py` | Pydantic validation of the curated YAML files. |
| `ingestion/drugs.py` | RxNav: names and product RxCUIs → RxNorm ingredients; ATC classes and memberships via RxClass. Multi-ingredient products are detected and never attributed to one ingredient. |
| `ingestion/extraction.py` | Lexicon-based candidate statements with verbatim excerpts, conditions, mechanism, severity wording. |
| `ingestion/pipelines/*.py` | One pipeline per source (below). |
| `ingestion/validate.py` | Read-only checks after ingestion. |

## 3. Pipelines

| Order | Command | Sources | Produces |
|---|---|---|---|
| 1 | `ingest taxonomy` | WFO (ETHCSTWIN, official fallback), WCVP, TaxTree, GBIF, Wikidata | `taxon` (WFO ID + IPNI, WCVP, GBIF, NCBI, POWO, Wikidata IDs, native range), `taxon_name` (accepted, WCVP synonyms, GBIF English vernacular, curated common and pharmaceutical names), `herbal_substance` |
| 2 | `ingest ema` | EMA inventory spreadsheet, herb pages, final monograph PDFs, RxNav | Document- and section-level `evidence_item`s with chunks, `indication`s (WEU/TU kept apart), `interaction_assertion`s from §4.3–4.5, `drug`/`drug_class` |
| 3 | `ingest nccih` | NCCIH fact sheets, RxNav | `evidence_item` per section (GOV), assertions from the safety section |
| 4 | `ingest labels` | openFDA drug labels, RxNav | `evidence_item` per label section mentioning a herb, drug-specific assertions |
| 5 | `ingest pubmed` | PubMed E-utilities | `evidence_item` per article (evidence type from publication types/MeSH), title+abstract chunk (local only) |

### 3.1 Taxonomic normalisation rules

1. Names from sources are cleaned (`Hypericum perforatumL.` → `Hypericum perforatum L.`; glued parentheses; non-breaking spaces).
2. WFO lookup retrieves **all** records for the name and selects the single *accepted* one. WFO holds duplicate name strings with different authors (e.g. *Glycyrrhiza uralensis* Fisch. — unplaced — and *G. uralensis* Fisch. ex DC. — accepted); the wrapper's `first_hit` returned the unplaced one. Several accepted records → error, nothing chosen.
3. Synonyms resolve through WCVP `accepted_plant_name_id` (WFO synonym records do not name the accepted taxon).
4. Cross-checks: IPNI (WFO vs WCVP, WFO vs Wikidata), NCBI (TaxTree vs WCVP, vs Wikidata), GBIF (GBIF vs Wikidata). Disagreements → `identifier_mismatch` warnings; the WFO/primary value is kept, never overwritten.
5. EMA botanical names (often synonyms, e.g. *Cimicifuga racemosa*, *Cassia senna*) must resolve to one of the curated taxa, or to an infraspecific taxon of one (recorded as info).
6. WCVP "Misapplied" names are never stored as synonyms.

### 3.2 Drug normalisation rules

- Lexicon drug names → RxNorm `rxcui.json?search=2` → properties; non-ingredient concepts → related `IN`/`MIN`.
- Label drugs → the label's `openfda.rxcui` → related ingredients. A related `MIN` or more than one `IN` = multi-ingredient → label skipped (counted and recorded).
- ATC classes come from RxClass (`byRxcui`, `byId`); unknown ATC codes are errors, never invented.

### 3.3 Interaction statements

Extraction is deterministic and conservative (rules and tests in `extraction.py` / `test_extraction.py`):

- Matches come only from the curated lexicon; unmapped drug references are logged (`lexicon_term_unmapped`).
- `statement_type`: `interaction`, `precaution`, `no_interaction_reported`, `uncertain`, `unclassified` — from sentence cues (negation, contraindication, caution, effect, uncertainty), with generic boilerplate ("some herbs and medicines interact in harmful ways") removed first.
- Class words used as descriptions of a named drug ("Warfarin, an anticoagulant (blood thinner)") are not generalised to the class; class references qualified by "some/certain/other" or "metabolised by …" are recorded as *partial* in `conditions`.
- EMA sub-headings ("Indications 1), 3) and 4)", "Daily dose of hyperforin > 1 mg") become `conditions`; the enzyme sentence of the paragraph becomes `mechanism`; in §4.3 the heading "Contraindications" is relayed as severity wording when a sentence has none.
- Every assertion's excerpt is checked to be a verbatim substring of the stored source text (at extraction time and again by `herbaguard validate`).
- Sections whose whole text is "None reported" / "None known" are stored with `section_statement = none_reported` — distinct from a section that was not extracted.

## 4. Provenance and lineage

| Table | Meaning |
|---|---|
| `ingestion_run` | One execution per source: parameters, statistics, status (`succeeded` / `partial` / `failed`), code version |
| `source_record` | Every HTTP response (any status) and every committed curation file, with SHA-256 and path to the raw snapshot |
| `provenance` | Links each derived row to the record(s) it came from: extraction method + version, location (e.g. "section 4.5, traditional_use, pages 9-10"), verbatim excerpt |
| `data_quality_issue` | Every problem, with rule, severity, message and context |

## 5. Operational notes discovered during implementation

| Issue | Handling |
|---|---|
| ETHCSTWIN wrappers and `list.worldfloraonline.org` do not send their TLS intermediate certificate (OpenSSL: "unable to verify the first certificate"; Windows curl hides this by fetching it itself) | The two public intermediates (HARICA Institutional TLS RSA 2; GeoTrust TLS RSA CA G1) were downloaded from the URLs in the servers' own certificates, verified to chain to roots already in `certifi`, and shipped in `ingestion/certs/` with fingerprints. Verification is never disabled. |
| Wikidata Query Service returns HTTP 403 to User-Agents without contact information | User-Agent includes the repository URL |
| WCVP wrapper rejects `limit` > 100 (HTTP 422) | Pagination |
| RxNav returns HTTP 400 for `tty=IN%2BMIN` | Literal `+` in the URL; RxNav errors are recorded as errors (previously misread as "multi-ingredient") |
| openFDA without API key: 1,000 requests/day | ≤ 5 pages × 100 labels per herb; coverage reported per herb |
| openFDA `count` returns 404 when no matching label has harmonised `openfda` fields | Reported as "uncountable", not as zero |
| Windows `localhost` resolves to IPv6 first | Connection strings use `127.0.0.1` |

## 6. What is stored where

| Data | Location | In Git? |
|---|---|---|
| Curated herb list, lexicon | `data/curated/` | Yes |
| Raw snapshots (JSON, XML, HTML, PDF, XLSX) | `data/raw/` | **No** (git-ignored) |
| PubMed abstracts, EMA/NCCIH/label text chunks | PostgreSQL `chunk` table | **No** |
| Test fixtures (captured, trimmed real responses) | `backend/tests/fixtures/captured/` | Yes — see its README for what was changed |
