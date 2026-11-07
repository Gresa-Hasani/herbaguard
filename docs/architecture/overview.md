# Architecture Overview

**Status:** Foundation (Phase 1), ingestion (Phase 2), core API (Phase 3), mechanism layer (Phase 4) and AI layer (Phase 5) implemented. Modules marked *planned* do not exist yet.

HerbaGuard is a **modular monolith**: one Python package serves the API and runs the data pipeline, one React single-page app is the user interface, and one PostgreSQL database (with pgvector) stores everything. The reasons are recorded in [decisions.md](decisions.md).

## 1. Runtime view

```
 Browser ──► web (nginx :80, host 18080)
               │  static React build (SPA fallback)
               └─ /api/* ──► api (FastAPI/uvicorn :8000, host 18010)
                                 │ SQLAlchemy 2 + psycopg 3
                                 ▼
                             db (PostgreSQL 16 + pgvector :5432, host 5455)
                                 ▲
 herbaguard CLI (ingestion) ─────┘   ──► external sources (ETHCSTWIN, EMA, openFDA, RxNav, PubMed, NCCIH)
                                     ──► data/raw/ (snapshots, git-ignored)
```

| Service | Image | Host port (default) | Health check |
|---|---|---|---|
| `db` | `pgvector/pgvector:pg16` | `127.0.0.1:5455` | `pg_isready` |
| `api` | built from `backend/` (Python 3.12) | `127.0.0.1:18010` | `GET /api/v1/health/ready` |
| `web` | built from `frontend/` (nginx 1.27) | `127.0.0.1:18080` | — |

Host ports are unusual on purpose: on the development machine, 5432, 5433, 8000 and 8010 were already taken by other projects. All ports are configurable in `.env` and bound to `127.0.0.1` only.

The API container runs `alembic upgrade head` before starting, so the schema is always current.

## 2. Backend module boundaries

```
backend/src/herbaguard/
├── main.py            App factory: middleware, error handlers, routers
├── core/              Cross-cutting: config, logging, db engine/session, domain exceptions
├── api/               HTTP only: routes, request/response schemas, middleware, error mapping
├── domain/            Vocabularies and the interaction classification rules (interactions.py) — no I/O
├── models/            SQLAlchemy ORM tables (schema v1)
├── ingestion/         Source registry, CLI; connectors/adapters/normalisers from Phase 2
├── repositories/      Data access (SQL only): plants, drugs, evidence, interactions
├── services/          Use cases: herb/drug resolution, evidence, coverage, interaction check
└── ai/                Phase 5: providers, embeddings, retrieval index, hybrid retrieval, evidence assembly,
                       generation, validation, evaluation (docs/ai/architecture.md)
```

Dependency rules:

| Module | May depend on | Must not depend on |
|---|---|---|
| `domain` | standard library only | anything else |
| `models` | `domain`, `core` | `api`, `services`, `ingestion` |
| `repositories` | `models`, `domain`, `core` | `api` |
| `services` | `repositories`, `domain`, `core`, `ai` | `api` |
| `api` | `services`, `core`, `domain` (schemas) | `ingestion` |
| `ingestion` | `models`, `domain`, `core` | `api`, `services` |
| `ai` | `repositories`, `domain`, `core` | `api` |

The key rule is that the **interaction class (A–E) is computed in `domain`** by deterministic code, so neither the HTTP layer nor the AI layer can change a scientific classification.

## 3. Frontend structure

```
frontend/src/
├── main.tsx / App.tsx   Router + TanStack Query provider; routes
├── components/          Layout, DisclaimerBanner, BackendStatus, ErrorBoundary
├── pages/               Home, placeholders for the five modules (Phase 6), NotFound
├── hooks/               Data hooks wrapping the API (useMeta, useReadiness)
├── lib/                 API client (ApiError), types, constants, router flags
└── test/                Vitest setup, render helpers, tests
```

- Development: `npm run dev` on port 5173 proxies `/api` to the API on `127.0.0.1:18010`.
- Production: nginx serves the build and proxies `/api` to the `api` container (same origin, so no CORS needed).
- The medical disclaimer is rendered on every page. It falls back to a built-in copy of the text if the API is unreachable, so the warning is never missing.

## 4. Cross-cutting concerns

| Concern | Implementation |
|---|---|
| Configuration | `pydantic-settings`, prefix `HERBAGUARD_`, reads repository-root `.env`; real env vars win. Validated at start-up (e.g. the database URL must be PostgreSQL; the log level must be known). |
| Logging | `structlog`; JSON in production/Docker, readable console in development. Each request is logged once with method, path, status, duration and `request_id`. **Query strings, request bodies and local variables are never logged** (they may contain medication names). Uvicorn's access log is disabled for the same reason. |
| Request IDs | `X-Request-ID` accepted if it matches `[A-Za-z0-9._-]{1,64}`, otherwise generated; echoed on every response, including 500 errors. |
| Errors | One envelope for every error, see [api-conventions.md](api-conventions.md). Unhandled exceptions return a generic message; details go to the log only. |
| Security | CORS restricted to configured origins; nginx sets `nosniff`, `no-referrer` and `DENY` framing headers; containers run as non-root (API); ports bound to localhost. No authentication in the MVP (no personal data is stored). |
| Provenance | Every derived row links to `source_record` and `ingestion_run` through `provenance`; see [data-model.md](data-model.md). |

## 5. Testing and CI

| Layer | Tooling | Where |
|---|---|---|
| Backend unit/API | pytest, FastAPI TestClient | `backend/tests/test_api.py`, `test_config_and_cli.py` |
| Database | pytest against a throwaway `herbaguard_test` database, migrated with Alembic | `backend/tests/test_database.py` (marker `db`) |
| Frontend | Vitest, Testing Library, jsdom | `frontend/src/test/` |
| Static checks | ruff (lint + format), mypy `--strict`, ESLint, `tsc` | CI |
| CI | GitHub Actions: backend job with a pgvector service container, frontend job, Docker image build | `.github/workflows/ci.yml` |

CI fails if any database test is skipped. External APIs are not called in CI. Opt-in live tests use the `live` marker from Phase 2.
