# HerbaGuard — Phase 5: AI Evidence Assistant

**Date:** 2026-11-04. **Baseline:** `origin/main` = `0788b62` (Phase 4 and its audit completion merged).

## Request (recorded from chat)

The team chose to continue with Phase 5 (AI evidence assistant) before Phase 6, and resolved ADR-009: **local Ollama** as the LLM provider.

## Scope taken from the earlier phases

- MVP M6 (`docs/research/mvp-scope.md`): question → grounded answer with validated citations, explicit insufficient-evidence and referral behaviour; demo scenarios D5 (St John's wort + contraceptive pill) and D6 (valerian dosing, declined).
- `docs/research/technology-evaluation.md` §3.5: RAG with deterministic classification; hybrid retrieval (PostgreSQL FTS + pgvector, Reciprocal Rank Fusion, entity filters); structure-aware chunks (already stored in Phases 2/4); citation validator with one regeneration and an extractive fallback; fixed evaluation set (citation precision, unsupported-claim rate, refusal correctness).
- `docs/research/scientific-and-ethical-considerations.md` §6: the LLM explains, never classifies; citations validated against the store; evaluation covers documented pairs, no-evidence pairs, unknown herbs, ambiguous names, dosing questions and prompt-injection attempts.
- ADR-003: classes A–E only from `domain/interactions.py`.

## Rules followed

Phase 1–4 behaviour unchanged (no edits to domain rules, ingestion pipelines or existing endpoints); tests for every new rule; documentation and ADRs updated; no commit, no push; Phase 6 not started.

## Validation status at hand-over

- Pure tests (`tests/ai/test_assistant_rules.py`, 33 tests), `ruff check`, `ruff format --check` and `mypy --strict` on the pure `ai/` modules: run and passing in the development sandbox.
- Not run in the sandbox (no package registry, PostgreSQL or Ollama there): `tests/ai/test_ollama_client.py` (needs httpx), `tests/api/test_assistant_api.py` (needs the test database), full `mypy`, `herbaguard ai embed` and `herbaguard ai eval` on real data. Run these locally before committing.
