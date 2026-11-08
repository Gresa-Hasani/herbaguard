# HerbaGuard

Evidence-based phytotherapy platform combining medicinal plant knowledge, scientific research, herb–drug interaction analysis, and AI-powered safety intelligence.

**EthnoHack 2026 — Track 04: Digital Health & Phytotherapy**

> **Disclaimer.** HerbaGuard provides information from scientific and regulatory sources. It is not medical advice and does not replace your doctor or pharmacist. The absence of a reported interaction does not mean a combination is safe.

## What HerbaGuard answers

> *"What is known about combining herb Y with drug X — how strong is that evidence, and where exactly does it come from?"*

HerbaGuard combines herb-side regulatory monographs (EMA HMPC), drug-side labels (openFDA), government fact sheets (NCCIH) and the literature (PubMed). Every finding gets an evidence class (documented / potential / suspected / no evidence found / insufficient information) and links back to its source.

## Project status

| Phase | Scope | Status |
|---|---|---|
| 0 | Research and dataset audit | Done — see [`docs/research/`](docs/research/) |
| 1 | Architecture and foundation | Done — see [`docs/architecture/`](docs/architecture/) |
| 2 | Data ingestion and normalisation | Done — see [`docs/data/`](docs/data/) |
| 3 | Backend and core APIs | Done — see [`docs/api/`](docs/api/) |
| 4 | Knowledge graph and mechanism integration | Done — see [`docs/api/mechanism-paths.md`](docs/api/mechanism-paths.md), [`docs/data/mechanism-sources.md`](docs/data/mechanism-sources.md) |
| 5 | AI, hybrid RAG and multi-provider LLM | Done — see [`docs/ai/`](docs/ai/) |
| 5+ | Dataset expansion (DDID, SUPP.AI, LiverTox, NIH DSLD) | Done — see [`docs/data/external-datasets.md`](docs/data/external-datasets.md), [`docs/data/ddid.md`](docs/data/ddid.md) |
| 6 | Frontend modules | Done — Interaction Checker, Herb Explorer, Evidence Assistant, Sources, About; see [`docs/frontend/`](docs/frontend/) |
| 7 | Integration and validation | Done for the hackathon scope — live AI evaluation runs in [`docs/ai/evaluation.md`](docs/ai/evaluation.md); manual expert review still open (see *Limitations*) |
| 8 | Submission | Devpost page, pitch video and slide deck |

**What is implemented:**

- **Data pipeline** — ingests the 16 curated herbs (21 taxa) from WFO/WCVP/NCBI/GBIF/Wikidata, EMA herbal monographs, NCCIH fact sheets, openFDA drug labels, RxNorm/ATC and PubMed, with raw snapshots, full provenance and validation (`herbaguard validate`). Expanded with DDID (herb–drug interaction records), SUPP.AI (ML-extracted interaction sentences), LiverTox (hepatotoxicity) and NIH DSLD (product labels), each kept as its own evidence kind.
- **REST API** (FastAPI, PostgreSQL + pgvector; migrations 0001–0007) — plants, drugs, evidence, sources and coverage, and a deterministic herb–drug **interaction check (classes A–E)** with source quotes and provenance.
- **Mechanism layer** — 18 enzymes/transporters, drug roles from FDA's CYP/transporter table, herb effects from EU monographs, graph and path endpoints, conservative mechanism-based class B.
- **AI Evidence Assistant** — hybrid retrieval (PostgreSQL full-text + pgvector, RRF), a provider-independent LLM interface (local Ollama/Qwen3-4B by default; Anthropic/OpenAI optional), citations validated in code, and the A–E class always taken from the deterministic service, never from the model. A validated answer cache serves the suggested questions instantly.
- **Web app** (React + TypeScript) — public site (landing, About, Sources & methodology with licence details) and a workspace with:
  - **Interaction Checker** — one herb + one or more drugs → class A–E per pair, evidence with source quotes, mechanism assessment and a short explanation of what the class means;
  - **Herb Explorer** — all 21 taxa with identifiers, EMA status, indications, warnings and per-source coverage, including product-label coverage;
  - **Evidence Assistant** — cited answers with source pills and tooltips; emergency and dosing questions are referred, not answered;
  - a persistent medical disclaimer on every page.
- **Engineering** — Docker Compose stack, backend and frontend test suites, ruff + strict mypy, ESLint, CI on every push.

## Results

All numbers below are measured, and come from the linked reports.

**Data quality** (Phase 2 run, [`docs/data/ingestion-results.md`](docs/data/ingestion-results.md)):

- every curated taxon resolves to exactly one accepted WFO record;
- 100 % provenance coverage on all core tables; 545/545 interaction excerpts are verbatim in the stored source text;
- EMA PDF extraction cross-checked against a second extractor: 256 columns, 0 mismatches;
- 1,219 evidence items and 545 interaction statements (EMA 172, NCCIH 48, openFDA 307 active).

**AI Evidence Assistant** (local Qwen3-4B via Ollama, CPU only; 46 questions in two evaluation sets; [`docs/ai/evaluation.md`](docs/ai/evaluation.md) §6, reports in [`docs/ai/results/`](docs/ai/results/)):

| Check | Baseline set (35 q.) | Expanded set (11 q.) |
|---|---|---|
| Interaction class identical to the deterministic service | 100 % | 100 % |
| Citation validity (every cited id exists in the database) | 100 % | 100 % |
| Answered / insufficient evidence / rejected by validation | 22 / 5 / 7 | 4 / 4 / 0 |
| Errors | 0 | 0 |
| Median latency | 126 s | 132 s |

Retrieval (baseline set, hybrid with nomic-embed-text): Hit@5 0.871, Recall@10 0.635, MRR 0.759 ([`docs/ai/embedding-models.md`](docs/ai/embedding-models.md)).

Rejections are deliberate: the validator refuses any answer that turns source wording into a safety claim, and questions about plants or entities not covered return "insufficient evidence" instead of a guess.

## Limitations

- **Coverage is curated:** 16 herbs (21 taxa). A herb outside this set is reported as not covered, never as "no interaction".
- **No interaction found ≠ safe.** Classes D/E mean the sources reviewed say nothing; the UI and API say so explicitly.
- **AI checks are automated, not clinical.** They show class consistency and citation validity; they do not prove that every sentence is faithful to its sources. The manual review by a pharmacist/pharmacologist described in the evaluation doc has not been done. Known validator false positives and one model misreading (St John's wort + warfarin DDID record) are listed in [`docs/ai/evaluation.md`](docs/ai/evaluation.md) §6.
- **Small evaluation sets,** written by the team, English only, no independent annotation.
- **Evidence kinds differ in strength:** SUPP.AI sentences are ML-selected mentions, CAERS/spontaneous reports do not show causation, DDID animal or unstated-species records are not clinical evidence; each is labelled as such.
- **DDID licence is not yet verified,** so DDID text is never sent to cloud models and is not redistributed.
- **Local model latency** is about 2 minutes per answer on a CPU-only laptop; the suggested questions are served from the validated cache.

## Future work

- Expert (pharmacist) review of AI answers and a larger, independently annotated evaluation set.
- Extend coverage from the curated set to all EMA herbal entries; the connectors are not herb-specific.
- Safety-signal dashboard (CAERS, non-causal framing) and monograph → ICD-11 / MeSH mapping of indications and contraindications.
- Fix the documented validator false positives; GPU or hosted model for faster answers.
- Multilingual interface (Albanian, Greek, German, Italian) for the partner countries.

## Quick start (Docker)

Requirements: Docker with Compose v2.

```bash
cp .env.example .env
docker compose up --build
```

| Service | URL |
|---|---|
| Web app | http://localhost:18080 (Interaction Checker, Herb Explorer, Evidence Assistant) |
| API docs (OpenAPI) | http://localhost:18010/api/docs |
| Readiness | http://localhost:18010/api/v1/health/ready |
| PostgreSQL | `127.0.0.1:5455` (user/password/db `herbaguard`) |

Ports can be changed in `.env` (`HERBAGUARD_DB_HOST_PORT`, `HERBAGUARD_API_HOST_PORT`, `HERBAGUARD_WEB_HOST_PORT`). Migrations run automatically when the API starts.

## Data pipeline

With the database running (`docker compose up -d db`) and the backend installed (see below):

```bash
cd backend
herbaguard ingest all      # ~6 minutes; fetches live data (incl. Phase 4 mechanisms), stores raw snapshots in data/raw/
herbaguard validate        # post-ingestion checks
herbaguard report          # counts and data-quality issues
```


Details: [`docs/data/pipeline.md`](docs/data/pipeline.md) · sources and licences: [`docs/data/sources.md`](docs/data/sources.md) · latest results: [`docs/data/ingestion-results.md`](docs/data/ingestion-results.md).

### AI layer (Phase 5)

Needs [Ollama](https://ollama.com) running locally (no API key):

```bash
ollama pull qwen3:4b          # answer model (~2.5 GB); any Qwen3-4B tag via HERBAGUARD_LLM_MODEL
ollama pull nomic-embed-text  # embedding model (benchmark choice)
cd backend
herbaguard ai index           # incremental: segments + embeddings for new/changed evidence
herbaguard ai status
herbaguard ai evaluate-retrieval   # keyword vs semantic vs hybrid on data/evaluation/
```

Then `POST /api/v1/ai/ask` with `{"question": "Does St John's wort interact with warfarin?"}`; `POST /api/v1/ai/retrieve` returns evidence without a model. Providers (Ollama, Anthropic, OpenAI, extractive), configuration and limits: [`docs/ai/`](docs/ai/).

## Local development

Backend (Python ≥ 3.12), with the database from Compose running (`docker compose up -d db`):

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows; use `source .venv/bin/activate` on Linux/macOS
pip install -e ".[dev]"
alembic upgrade head
uvicorn herbaguard.main:app --reload --port 18010
```

Frontend (Node 22):

```bash
cd frontend
npm ci
npm run dev                   # http://localhost:5173, proxies /api to 127.0.0.1:18010
```

### Checks

```bash
cd backend && ruff check . && ruff format --check . && mypy && pytest
```

```bash
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
```

Database tests create and drop a separate `herbaguard_test` database; they are skipped if PostgreSQL is unreachable locally. In CI they must run. Tests that call the real external APIs are opt-in: `pytest -m live`.

## Repository layout

```
backend/        FastAPI app, domain vocabulary, ORM models, Alembic migrations, ingestion CLI, tests
frontend/       React + TypeScript (Vite) single-page app, tests, nginx config
data/curated/   Curated herb list, interaction lexicon, mechanism sources and targets (committed)
data/raw/       Raw source snapshots — git-ignored (licences may forbid redistribution)
docs/research/  Phase 0: requirements, dataset and API audits, scientific framework, MVP scope
docs/architecture/  System overview, data model, API conventions, decision records
docs/data/      Data pipeline, source notes and licences, ingestion and extraction results
prompts/        The prompt used for each development phase
```

## Data sources and licences

The selected sources, their priority and licence status are documented in [`docs/research/dataset-audit.md`](docs/research/dataset-audit.md) and registered in `backend/src/herbaguard/ingestion/sources.py` (`herbaguard sources`). Restricted content (DrugBank, UMLS, SNOMED CT, MedDRA, copyrighted abstracts and PDFs) is never committed to this repository.

## Responsible use

- Traditional use is not evidence of efficacy; in-vitro results are not clinical evidence; spontaneous adverse-event reports do not show causation.
- HerbaGuard never labels a combination as "safe" and never computes severity — it relays the wording of its sources.
- No personal data is stored. Request logs do not contain query strings or request bodies.
- Community and Indigenous knowledge is not included in the MVP; see [`docs/research/scientific-and-ethical-considerations.md`](docs/research/scientific-and-ethical-considerations.md).

## Licence

Code: [MIT](LICENSE). Data obtained from third-party sources remains under the terms of each source.
