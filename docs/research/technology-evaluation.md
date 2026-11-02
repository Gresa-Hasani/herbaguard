# Technology Evaluation and Architecture Recommendations

**Project:** HerbaGuard — EthnoHack 2026, Track 04
**Phase:** 0 — Research and Dataset Audit (input for Phase 1)
**Date:** 2026-11-02

The master prompt lists technologies as *initial recommendations*. This document evaluates each one against HerbaGuard's actual needs as identified in the audit: small curated data volume (16 herbs, thousands — not millions — of evidence items), heavy provenance requirements, a public repository, roughly 5.5 days of build time, and a video-based demo.

**Guiding rule:** choose the simplest stack that meets the scientific requirements, and justify every component.

---

## 1. Development environment (✔ checked 2026-11-02)

| Tool | Found | Implication |
|---|---|---|
| Docker / Compose | 29.8.0 / v5.5.1 | Compose-based local stack is feasible |
| Node.js / npm | v22.17.0 / 10.9.2 | Modern React tooling is fine |
| Python | 3.13.1 (host) | Containers will pin Python 3.12 (master prompt: 3.12+) |
| uv | not installed | Optional; `pip` works. Recommend installing uv for lockfile speed — user decision |
| PostgreSQL client | not installed | Not needed on host; runs in Docker |
| Ollama | 0.40.13 | Local LLM is possible, but **no NVIDIA GPU** detected → CPU-only inference (slow for >3B models) |
| CPU | 16 logical cores | Local embedding models on CPU are fine |
| Git | 2.55 | User controls all commits |

---

## 2. Recommended architecture (overview)

```
                 ┌──────────────────────────────────────────────┐
                 │                 web (React + TS)             │
                 │  Explorer · Interaction check · Evidence ·   │
                 │  Assistant · Safety dashboard                │
                 └───────────────────────┬──────────────────────┘
                                         │ JSON / REST (OpenAPI)
                 ┌───────────────────────▼──────────────────────┐
                 │              api (FastAPI, Python 3.12)      │
                 │  routers → services → repositories           │
                 │  interaction rules engine (deterministic)    │
                 │  retrieval (FTS + vector, RRF)  → LLM client │
                 └───────────────────────┬──────────────────────┘
                                         │ SQLAlchemy
                 ┌───────────────────────▼──────────────────────┐
                 │  PostgreSQL 16 + pgvector                    │
                 │  canonical entities · edges · evidence ·     │
                 │  provenance · chunks/embeddings · raw index  │
                 └───────────────────────▲──────────────────────┘
                                         │
                 ┌───────────────────────┴──────────────────────┐
                 │  ingestion CLI (same Python package)         │
                 │  connectors → raw snapshots → adapters →     │
                 │  validation → normalisation → load           │
                 └───────────────────────┬──────────────────────┘
                                         │ HTTPS
      ETHCSTWIN wrappers · EMA · openFDA · RxNav · PubMed · NCCIH · FDA CYP table · …
```

**One modular monolith** (API + ingestion share one Python package) plus one frontend and one database. No microservices: the data volume and team size do not justify them.

---

## 3. Component decisions

### 3.1 Backend — **FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic** (accept)

| Criterion | Assessment |
|---|---|
| Fit | The ingestion stack is naturally Python (PDF parsing, scientific clients, embeddings). Sharing one language between ingestion and API avoids duplicated models. |
| Validation | Pydantic models double as API schemas and ingestion validators, so the same rules apply to data coming in and going out. |
| OpenAPI | Generated automatically and used for the frontend client and API docs (Phase 3). |
| Precedent | The ETHCSTWIN wrappers are themselves FastAPI apps (OpenAPI 3.1, ✔ observed) — a familiar shape for the jury's technical reviewers. |
| Alternatives | Django (heavier ORM/admin, slower to adapt), Node/NestJS (splits the language from ingestion). Rejected. |

Supporting libraries: `httpx` (HTTP client, async-capable), `tenacity` (retry/backoff), `pydantic-settings` (env config), `structlog` (structured JSON logs), `typer` (ingestion CLI).

### 3.2 Database — **PostgreSQL 16 with pgvector** (accept)

| Need | How PostgreSQL covers it |
|---|---|
| Canonical relational entities with strict integrity | Tables, FKs, unique constraints on source IDs |
| Provenance and lineage | `source`, `source_record` (raw payload hash, URL, retrieved_at), `provenance` link tables |
| Raw JSON preservation | `JSONB` columns |
| Keyword search | Built-in full-text search (`tsvector`, `ts_rank`), `pg_trgm` for fuzzy names |
| Semantic search | `pgvector` extension (HNSW index) |
| Graph-style traversal | Edge tables + recursive CTEs (see §4) |

**Why not a separate vector database** (Qdrant, Weaviate, Chroma): the corpus is small (estimated 2–10k chunks). A second datastore would add sync logic, a container and failure modes with no measurable benefit. pgvector keeps chunk, metadata and provenance in one transaction.

### 3.3 Knowledge graph — **Neo4j: not for the MVP** (decision record)

See §4 for the full evaluation.

### 3.4 Data engineering — **Python connectors + adapters, CLI-orchestrated** (accept)

| Layer | Responsibility |
|---|---|
| **Connector** (per source) | HTTP access, auth, pagination, rate limiting (token bucket), retry with exponential backoff (`tenacity`), conditional requests where supported |
| **Raw snapshot** | Each response saved unchanged (`data/raw/<source>/<date>/<hash>.json|pdf`), git-ignored, indexed in `source_record` with SHA-256, URL, params, HTTP status, retrieved_at |
| **Adapter** | Source-specific parsing into Pydantic *source models* (e.g., `EmaMonographSection`, `FdaLabelInteractionSentence`) |
| **Validation** | Pydantic + explicit data-quality checks (required IDs, enum values, date sanity); failures go to a `data_quality_issue` table instead of being dropped silently |
| **Normalisation / entity resolution** | Names → `wfo_id`; drugs → RxCUI; compounds → InChIKey; deterministic rules + curated override tables (committed) |
| **Load** | Idempotent upserts keyed on `(source, source_record_id)`; conflicting values are stored as separate assertions, never overwritten |

**Orchestration:** a `typer` CLI (`herbaguard ingest ema|wfo|fda-labels|… [--since]`, `herbaguard build-index`) plus a `make`/`just` target for the full rebuild. **Airflow, Dagster and Prefect are rejected** — scheduling and distributed execution are not needed for a one-shot reproducible build.

**PDF extraction (EMA):** `pdftotext -layout` already extracted §4.5 successfully (✔ tested). For column separation, `pdfplumber` (MIT, pure Python) supports cropping by page coordinates, which handles the WEU/TU two-column layout. Recommend `pdfplumber` with a `pdftotext` cross-check, plus a committed **human QA checklist** for each curated monograph.

**Provenance model:** adopt the *concepts* of W3C PROV-O (Entity / Activity / Agent: raw record → extraction run → assertion) recommended by the organizers, implemented as relational tables. Export to PROV-O RDF is a "Could".

### 3.5 AI and retrieval

| Decision | Recommendation | Reason |
|---|---|---|
| Architecture | **RAG with deterministic classification** | The interaction class is computed by rules (see `scientific-and-ethical-considerations.md` §2). The LLM only explains retrieved, already-classified evidence. This removes the main hallucination risk from the safety-critical part. |
| Retrieval | **Hybrid:** PostgreSQL FTS + pgvector, merged with Reciprocal Rank Fusion, filtered by resolved entity IDs (herb `wfo_id`, drug RxCUI) | Entity filters keep retrieval on-topic; FTS catches exact drug names that embeddings blur; vectors catch paraphrases |
| Graph retrieval | Use relational edges to *expand* the query (herb → marker constituent → enzyme → drug class), not a graph DB | Enough for the mechanism-based class B |
| Embeddings | Local open model via `sentence-transformers` on CPU — candidates: `BAAI/bge-small-en-v1.5` (MIT, 384-d, fast) or a biomedical model; choose by a small retrieval test in Phase 5 | Free, offline, reproducible; corpus is small |
| Chunking | Structure-aware: one chunk per monograph subsection (4.3, 4.4, 4.5, 4.8…), per label interaction paragraph, per abstract; metadata = source, section, herb/drug IDs, evidence type, date | Citations point to meaningful units |
| Citation integrity | Post-generation validator: every `[n]` must map to a retrieved chunk ID; otherwise regenerate once, then fall back to extractive output | Satisfies "never fabricate references" |
| Evaluation | Fixed question set with expected sources; metrics: citation precision, unsupported-claim rate (manual), refusal correctness | Data-science-quality criterion |

**LLM provider — decision needed from the user.**

| Option | Quality for cited scientific summaries | Cost | Setup / risk |
|---|---|---|---|
| A. Hosted model API (e.g., Anthropic Claude) | High | Low for a demo (pay-per-use), but paid; requires an API key in `.env` | Data leaves the machine; needs a disclosure in the UI |
| B. Local model via Ollama (installed) | Lower; CPU-only inference is slow for models large enough to follow citation instructions reliably | Free | Demo latency risk on CPU |
| C. No generation — extractive answers only | Lowest fluency, **zero hallucination** | Free | Always available |

**Recommendation:** a provider-agnostic `LLMClient` interface with **C as the always-available fallback**, **A as the default when a key is configured**, and **B as an optional free mode**. The app must work end-to-end with no API key (judges can run it). The user should decide whether a paid key is acceptable.

### 3.6 Frontend — **React + TypeScript + Vite** (accept, with specifics)

| Choice | Reason |
|---|---|
| Vite SPA (not Next.js) | The backend is a separate FastAPI service; server-side rendering and Next's routing/server features add complexity without benefit. Vite gives a fast dev server and a static build served by nginx or the API. |
| Tailwind CSS + shadcn/ui (Radix primitives) | Accessible primitives (keyboard, ARIA) out of the box; components are copied into the repo (no runtime lock-in) |
| TanStack Query | Caching, loading/error states for API calls |
| React Router | Simple client routing |
| OpenAPI-generated TS client (`openapi-typescript`) | Keeps frontend types in sync with Pydantic schemas |
| Charts: a small library (e.g., Recharts) only for the Safety Dashboard | Minimal dependency |

### 3.7 Infrastructure

| Component | Decision |
|---|---|
| Docker Compose | Services: `db` (postgres + pgvector image), `api`, `web`; optional `ollama` profile. One command start. |
| Configuration | `.env` with `.env.example` committed; `pydantic-settings`; no secrets in code |
| Logging | `structlog` JSON logs with request ID; ingestion runs log source, counts, issues |
| CI (GitHub Actions) | Backend: `ruff` (lint+format), `mypy`, `pytest` with a Postgres service container. Frontend: `eslint`, `tsc`, `vitest`, production build. CI runs on push/PR; **it never commits or pushes**. |
| Python packaging | `pyproject.toml`; lockfile via `uv` if the user installs it, otherwise `pip-tools` |
| Deployment | Not required by organizers (video demo). Optional free hosting can be evaluated in Phase 8 if time allows. |

### 3.8 Testing strategy

| Level | Tooling | Notes |
|---|---|---|
| Unit | `pytest` | Rules engine (class A–E), normalisers, adapters on fixture payloads |
| Ingestion | `pytest` + recorded fixtures (`respx` for `httpx` mocking) | Fixtures are **real responses captured in this audit**, trimmed; clearly separated from live checks |
| Live integration | `pytest -m live` (opt-in, not in default CI) | Calls real APIs to detect drift; results reported separately |
| API | FastAPI `TestClient` against a test database | Contract and error-format tests |
| Data validation | Assertions in the build: every finding has provenance; each curated herb has exactly one `wfo_id`; no superseded EMA docs used | Fails the build on violation |
| RAG evaluation | Scripted evaluation set (Phase 5) | Citation validity is a hard gate |
| Frontend | `vitest` + Testing Library; Playwright for 2–3 critical journeys if time allows | |

---

## 4. Knowledge graph evaluation (Neo4j)

### 4.1 What relationships HerbaGuard needs

```
Taxon ─has_part→ HerbalSubstance ─contains→ Constituent ─modulates(induces/inhibits)→ Enzyme/Transporter
                                                                                           ↑
Drug ─is_substrate_of──────────────────────────────────────────────────────────────────────┘
Drug ─member_of→ DrugClass(ATC)
HerbalSubstance ─interacts_with{class, conditions}→ Drug | DrugClass
every edge ─supported_by→ EvidenceItem ─derived_from→ SourceRecord
```

### 4.2 Assessment

| Factor | Neo4j | PostgreSQL edge tables |
|---|---|---|
| Max path length needed | 3–4 hops (herb → constituent → enzyme ← drug) | Recursive CTE or fixed joins handle this easily |
| Data size | ~16 herbs, ~100 constituents, ~20 enzymes/transporters, ~hundreds of drugs | Trivial for Postgres |
| Provenance per edge | Possible (properties) but provenance is relational (many-to-many) | Native FKs, constraints |
| Extra service, second source of truth, sync code | Yes | No |
| Licensing | Neo4j Community is GPLv3 — fine for local use | — |
| ETHCSTWIN Neo4j import | **Admin-only** (HTTP 401 without credentials ✔ tested) — no shortcut available | — |
| Demo value ("knowledge graph" in pitch) | Visual browser | Same visual effect from a JSON graph endpoint + frontend graph view |
| Time cost | ~0.5–1 day (schema, loader, queries, tests, Docker) | Included in Phase 1–3 work |

### 4.3 Recommendation

**Do not adopt Neo4j for the MVP.** Model the graph as typed edge tables in PostgreSQL, expose `GET /graph/...` endpoints that return nodes and edges, and render them in the frontend (a "Could" feature).

Phase 4 then becomes a **short phase**: finalise the edge schema, implement the mechanism-path query used by class B, add a graph JSON export (and optionally RDF/Turtle using organizer-recommended vocabularies), with tests. The decision is documented and reversible: the edge tables can be loaded into Neo4j later without changes to the canonical model.

---

## 5. Canonical entity sketch (input for Phase 1)

| Entity | Key | Important attributes |
|---|---|---|
| `Taxon` | `wfo_id` | accepted name, authorship, family, rank, status; xrefs: IPNI, WCVP `plant_name_id`, GBIF key, NCBI tax_id, POWO |
| `TaxonName` | id | name string, type (accepted / synonym / common / pharmaceutical), language, source |
| `HerbalSubstance` | id | taxon_id, plant part (Plant Ontology term where possible), EMA Latin name |
| `Drug` | RxCUI (ingredient) | name, synonyms, ATC codes |
| `DrugClass` | ATC code | name, level |
| `Constituent` | InChIKey | name, ChEBI ID, PubChem CID |
| `Target` | UniProt accession | gene symbol (e.g., CYP3A4 `P08684`), type (enzyme / transporter) |
| `Indication` | id | text, use category (WEU / TU), MeSH ID (optional) |
| `InteractionAssertion` | id | herbal_substance_id, drug_id or drug_class_id, direction, mechanism, conditions (dose, use category), source wording of severity |
| `InteractionResult` | computed | class A–E per (herb, drug) with contributing assertions — computed, not stored as fact |
| `EvidenceItem` | id | evidence type (REG/GOV/SR/RCT/…), title, year, identifiers (PMID, DOI, EMA doc no., set_id), URL |
| `Source` | code | name, provider, licence, licence URL, attribution text, access method |
| `SourceRecord` | id | source, source-native ID, URL, request params, retrieved_at, SHA-256, raw path, HTTP status |
| `Provenance` | id | links any assertion / evidence item to source records + extraction activity (method, version, run ID) |
| `DataQualityIssue` | id | source record, rule, severity, message |
| `Chunk` | id | evidence item, section, text (if licence permits) or pointer, embedding, metadata |

---

## 6. Proposed repository structure (Phase 1)

```
herbaguard/
├── backend/
│   ├── pyproject.toml
│   ├── src/herbaguard/
│   │   ├── api/            # routers, schemas, error handlers
│   │   ├── core/           # config, logging, db session
│   │   ├── domain/         # entities, interaction rules engine
│   │   ├── repositories/
│   │   ├── services/
│   │   ├── ingestion/
│   │   │   ├── connectors/ # one module per source
│   │   │   ├── adapters/
│   │   │   ├── normalize/
│   │   │   └── cli.py
│   │   └── ai/             # retrieval, llm client, citation validator
│   ├── alembic/
│   └── tests/ (unit, ingestion, api, live)
├── frontend/               # Vite + React + TS
├── data/
│   ├── curated/            # committed: name mappings, herb list, QA checklists
│   └── raw/                # git-ignored snapshots
├── docs/ (research/, architecture/, api/)
├── prompts/
├── docker-compose.yml
├── .env.example
└── .github/workflows/ci.yml
```

---

## 7. Decisions requested from the user before Phase 1

1. **LLM provider:** hosted API key (paid, best quality), local Ollama (free, slower), or extractive-only — the app will support the fallback in every case.
2. **Neo4j:** accept the recommendation to defer it (relational edges + graph view), or require Neo4j for the pitch.
3. **Python tooling:** install `uv` (recommended) or use plain `pip`.
4. **MVP herb list:** approve the 16 candidates in `mvp-scope.md` or adjust.
5. **Team and eligibility:** confirm Devpost registration (cut-off was 31 Oct 23:00).
