# HerbaGuard — Phase 1 Prompt: Architecture and Project Foundation

**Project:** HerbaGuard — EthnoHack 2026, Track 04: Digital Health & Phytotherapy
**Phase:** 1 of 8
**Depends on:** Phase 0 deliverables in `docs/research/` (approved by the user on 2026-11-02)

---

## Role

You are acting as Senior Software Architect, Senior Data Engineer and Full-Stack Developer for HerbaGuard, an evidence-based herb–drug interaction and phytotherapy evidence platform. Phase 0 research is complete and approved.

## Objective

Establish a professional, maintainable project foundation on which Phases 2–8 can be built quickly: architecture, module boundaries, canonical data model and database schema v1, API conventions, backend and frontend skeletons, Docker Compose, configuration, logging, error handling, automated tests and CI.

## Binding decisions carried over from Phase 0

Use these unless the user overrides them:

1. **Modular monolith:** one Python package (`herbaguard`) holds the API, domain logic, ingestion and AI modules; one React frontend; one PostgreSQL database.
2. **PostgreSQL 16 + pgvector** is the only datastore. **Neo4j is deferred**: graph relationships are explicit edge tables (`technology-evaluation.md` §4).
3. **Backend:** Python ≥3.12, FastAPI, Pydantic v2, pydantic-settings, SQLAlchemy 2 (typed ORM), Alembic, psycopg 3, structlog, httpx, tenacity, typer.
4. **Frontend:** Vite + React + TypeScript, Tailwind CSS, React Router, TanStack Query, Vitest + Testing Library. Not Next.js.
5. **Python packaging:** `pyproject.toml` with pip (uv is not installed; do not install system tools without the user's consent).
6. **Interaction classes A–E** are computed by deterministic rules, never by an LLM (`scientific-and-ethical-considerations.md` §2). Phase 1 only defines the enums and storage for them.
7. **Provenance is first-class:** every assertion and evidence item must be linkable to `source_record` rows and an `ingestion_run`.
8. **LLM provider:** still undecided by the user — Phase 1 must not depend on it.

## Tasks

1. **Architecture documentation** in `docs/architecture/`: system overview and module boundaries; data model (entities, relationships, keys, constraints, provenance model); API conventions (versioning, naming, pagination, error envelope, provenance shape, disclaimers); architecture decision records.
2. **Repository structure** as proposed in `technology-evaluation.md` §6 (`backend/`, `frontend/`, `data/curated/`, `data/raw/` git-ignored, `docs/`, `prompts/`).
3. **Backend foundation:**
   - Settings via environment variables with validation; `.env.example`; no secrets in code.
   - Structured logging (JSON in production, readable console in development) with a request-ID middleware.
   - Consistent error envelope `{"error": {"code", "message", "details", "request_id"}}` for HTTP, validation and unhandled errors.
   - App factory, `/api/v1` router, endpoints: liveness `GET /api/v1/health`, readiness `GET /api/v1/health/ready` (checks the database), `GET /api/v1/meta` (name, version, environment, disclaimer).
   - SQLAlchemy models for **schema v1** and an Alembic initial migration (enables `vector` extension).
   - Ingestion CLI entry point (`herbaguard` command) with a stub showing configured sources — no real ingestion yet.
4. **Schema v1 entities:** source, ingestion_run, source_record, data_quality_issue, provenance, taxon, taxon_name, herbal_substance, drug, drug_class, drug_class_membership, constituent, herbal_substance_constituent, target, target_modulation (herbal substance or constituent → target), drug_target_role, indication, interaction_assertion, evidence_item, interaction_assertion_evidence, chunk (with embedding vector and generated full-text column). Preserve source identifiers, use constraints to enforce integrity, never overwrite conflicting assertions.
5. **Frontend foundation:** Vite React TS app with routing, layout shell (navigation for Explorer, Interactions, Evidence, Assistant, Safety), persistent medical disclaimer, API client with typed error handling, a backend status indicator, placeholder pages clearly marked "coming in Phase 6", an error boundary, and at least one component test.
6. **Docker:** `docker-compose.yml` with `db` (pgvector image), `api` (runs migrations then serves), `web` (built static site via nginx, proxying `/api` to the API). Health checks. Development instructions.
7. **CI:** `.github/workflows/ci.yml` — backend: ruff lint + format check, mypy, pytest with a Postgres+pgvector service; frontend: lint, typecheck, test, build. CI must never commit or push.
8. **Tests:** unit tests (settings, error envelope, request ID, health/meta), a database test that runs the migration against PostgreSQL and checks key constraints, frontend component test.
9. Update the root `README.md` with project summary, status, and quick start.
10. Save this prompt as `prompts/phase-1-architecture-and-foundation.md` **before** implementation starts.

## Constraints

- No data ingestion, no domain endpoints (plants, drugs, interactions), no AI features — those are Phases 2–5.
- No placeholder data presented as real findings. Placeholder pages must say so.
- English for all code comments and documentation.
- Keep dependencies minimal and justified.
- **Git:** never commit, push, amend, rebase, tag or create branches. Leave all changes uncommitted.

## Expected deliverables

- `docs/architecture/overview.md`, `data-model.md`, `api-conventions.md`, `decisions.md`
- `backend/` package with config, logging, errors, API, models, Alembic migration, CLI stub, tests
- `frontend/` app shell with tests
- `docker-compose.yml`, Dockerfiles, `.env.example`, updated `.gitignore`
- `.github/workflows/ci.yml`
- Updated `README.md`
- This prompt file

## Validation criteria

- `ruff check`, `ruff format --check`, `mypy` pass on the backend.
- `pytest` passes, including the migration test against a real PostgreSQL + pgvector instance.
- Frontend lint, typecheck, tests and production build pass.
- `docker compose up --build` starts all services; readiness endpoint reports the database as reachable; the web app loads and shows backend status.
- `alembic upgrade head` and `alembic downgrade base` both succeed.
- Report honestly anything not run (e.g., the GitHub Actions workflow cannot run locally).

## Stopping condition

Produce the mandatory Phase 1 completion report (overview, work, files, decisions, data sources, testing and validation with actual results, known issues, git status, next-phase preview, suggested commit message and description). State that no commit or push was performed. **Stop and wait for explicit approval before Phase 2.**
