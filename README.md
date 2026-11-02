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
| 3 | Backend and core APIs | Not started |
| 4 | Knowledge graph (relational edges) | Not started |
| 5 | AI evidence assistant | Not started |
| 6 | Frontend modules | Not started — module pages are placeholders |
| 7 | Integration and validation | Not started |
| 8 | Submission | Not started |

**Implemented now:** project structure; database schema with provenance tables (migrations 0001–0002); FastAPI service (health, readiness, metadata, standard error format, request IDs, structured logging); React application shell with the persistent disclaimer; Docker Compose stack; tests and CI; and a **data pipeline** that ingests the 16 curated herbs from WFO/WCVP/NCBI/GBIF/Wikidata, EMA herbal monographs, NCCIH fact sheets, openFDA drug labels, RxNorm/ATC and PubMed with full provenance and validation. The API does not serve this data yet (Phase 3), and the web app shows no findings.

## Quick start (Docker)

Requirements: Docker with Compose v2.

```bash
cp .env.example .env
docker compose up --build
```

| Service | URL |
|---|---|
| Web app | http://localhost:18080 |
| API docs (OpenAPI) | http://localhost:18010/api/docs |
| Readiness | http://localhost:18010/api/v1/health/ready |
| PostgreSQL | `127.0.0.1:5455` (user/password/db `herbaguard`) |

Ports can be changed in `.env` (`HERBAGUARD_DB_HOST_PORT`, `HERBAGUARD_API_HOST_PORT`, `HERBAGUARD_WEB_HOST_PORT`). Migrations run automatically when the API starts.

## Data pipeline

With the database running (`docker compose up -d db`) and the backend installed (see below):

```bash
cd backend
herbaguard ingest all      # ~5 minutes; fetches live data, stores raw snapshots in data/raw/
herbaguard validate        # post-ingestion checks
herbaguard report          # counts and data-quality issues
```

Details: [`docs/data/pipeline.md`](docs/data/pipeline.md) · sources and licences: [`docs/data/sources.md`](docs/data/sources.md) · latest results: [`docs/data/ingestion-results.md`](docs/data/ingestion-results.md).

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
data/curated/   Curated herb list and interaction lexicon (committed)
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
