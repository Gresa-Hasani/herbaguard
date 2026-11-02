# HerbaGuard — Phase 3 Prompt: Backend and Core APIs

**Project:** HerbaGuard — EthnoHack 2026, Track 04: Digital Health & Phytotherapy
**Phase:** 3 of 8
**Depends on:** Phase 0 research, Phase 1 foundation, Phase 2 ingestion (approved 2026-11-02). The development database holds the Phase 2 data for the 16 curated herbs.

---

## Role

Senior Software Architect and Backend Engineer for HerbaGuard, an evidence-based herb–drug interaction platform.

## Objective

Expose the ingested, provenance-tracked data through a clean, validated, tested REST API and implement the **deterministic herb–drug interaction classification (classes A–E)** defined in `docs/research/scientific-and-ethical-considerations.md` §2, using the statement types produced in Phase 2.

## Binding inputs from earlier phases

- API conventions: `docs/architecture/api-conventions.md` (`/api/v1`, error envelope, pagination envelope, provenance object, POST for requests carrying medication names, no "safe" field, no computed severity).
- Module boundaries: `domain` (pure rules, no I/O) ← `services` ← `api`; `repositories` own SQL.
- Phase 2 caveats that the classification must honour:
  1. `unclassified` label statements are **context only**; they must not produce class A.
  2. EMA "None reported/known" (`section_statement = none_reported`) is the regulator's statement at the monograph date, not proof of safety.
  3. `superseded` assertions are never used.
  4. Partial-class references ("Applies to part of the class only …") must not be treated as statements about the whole class.
  5. Traditional-use and well-established-use statements stay separate and visible.
  6. PubMed records are linked to herbs, not to herb–drug pairs; they are shown as related literature, not used for classification.
  7. Mechanism edges (FDA CYP table) arrive in Phase 4; the engine must support class B from them without requiring them now.

## Explicit requirements from the user (2026-11-02)

1. Implement the deterministic A–E interaction classification. Define and document the exact criteria. No LLM may determine a classification.
2. Treat `unclassified` openFDA label statements as contextual information only; never present them as confirmed herb–drug interactions.
3. Preserve source provenance in every API response; every scientific statement must be traceable to its original source.
4. Distinguish documented interactions, potential interactions, precautions, uncertain findings, "no interaction reported", and insufficient evidence. (Design: the A–E class is refined by a `finding` field — `documented_interaction`, `documented_precaution`, `potential_interaction`, `uncertain_evidence`, `mentioned_without_interaction_wording`, `no_interaction_reported`, `no_evidence_found`, `insufficient_information`.)
5. Never interpret missing data or an empty search result as proof of safety.
6. Distinguish evidence *type* from evidence *quality*: PubMed publication types are study designs, not quality scores, and must never be presented as such.
7. Appropriate filtering, pagination, search, validation and consistent error handling.
8. Comprehensive API, integration and classification tests, including negative and insufficient-evidence scenarios.
9. Verify against the actual Phase 2 schema and ingested records; introduce no assumptions about data that is not present.

## Tasks

1. Save this prompt as `prompts/phase-3-backend-development.md` before implementation.
2. **Domain rules** (`herbaguard.domain.interactions`): pure, documented, exhaustively tested function mapping a herb, a drug and the matching statements to a class (A documented, B potential, C suspected, D no evidence found, E insufficient information), a plain-language label, the reasons, the supporting statements and the relayed severity wordings.
3. **Repositories and services**: plant search and resolution (accepted, synonym, common, pharmaceutical names; ambiguity detection), plant detail, drug search and resolution (database first, optional live RxNav normalisation with provenance), evidence listing and detail, interaction check (single herb, one or more drugs), herb interaction overview, source/coverage information.
4. **Endpoints** under `/api/v1`: plants (search, resolve, detail, indications, evidence, interactions), drugs (search, detail, resolve), drug classes, evidence (list with filters, detail), interactions (POST check), sources/coverage. OpenAPI documented with examples.
5. **Validation and errors**: Pydantic request/response models, limits on list sizes and string lengths, the standard error envelope, `409 ambiguous_entity` with candidates.
6. **Provenance in every scientific response**: source, document/record identifier, location, URL, retrieval time, licence status, verbatim excerpt.
7. **Tests**: rule unit tests (every class and edge case), service and API tests against a seeded test database (seed data clearly labelled), API contract checks (OpenAPI), error cases.
8. **Verification on real data**: run the demo scenarios from `docs/research/mvp-scope.md` §7 against the development database through the running API and report the actual responses.
9. Document API contracts (`docs/api/`), update architecture docs and README.

## Constraints

- No frontend work (Phase 6), no AI/RAG (Phase 5), no mechanism ingestion (Phase 4).
- Never return "safe"; never compute severity; never present unvalidated content as fact.
- Do not log medication names or free-text queries.
- English documentation; no commits or pushes.

## Deliverables

- `backend/src/herbaguard/domain/interactions.py`, `repositories/`, `services/`, `api/routes/*`, `api/schemas/*`
- Tests under `backend/tests/api/`, `backend/tests/domain/`
- `docs/api/endpoints.md`, `docs/api/interaction-classification.md`
- Updated architecture docs and README; this prompt

## Validation criteria

- ruff, ruff format, mypy --strict, alembic check, full test suite pass.
- Demo scenarios produce the expected classes on the real data, or deviations are explained.
- OpenAPI schema generated and reviewed.

## Stopping condition

Produce the mandatory Phase 3 completion report. No commit or push. **Stop and wait for explicit approval before Phase 4.**
