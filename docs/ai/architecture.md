# AI Layer — Architecture (Phase 5)

**Status:** Implemented in Phase 5 (`backend/src/herbaguard/ai/`). Decisions: ADR-009 (resolved), ADR-020–ADR-023 in [../architecture/decisions.md](../architecture/decisions.md).

The AI layer explains evidence that HerbaGuard already stores. It is an extra service layer on top of the Phase 1–4 backend: no new datastore, no graph database, no microservice, and **no influence on the A–E classification**.

## 1. Pipeline

```
question ─► screening (ai/guardrails.py)                emergency → referral only (no retrieval, no model);
   │                                                    dosing → decline + official posology passages quoted
   ▼
query understanding (ai/query.py)            deterministic: n-gram lookup in name tables,
   │           entities + intent + "personal advice?"      existing resolvers, fixed intent rules
   │                    │ ambiguous entity → HTTP 409 with candidates (never a guess)
   ▼
deterministic classification (services/interactions.check)   ← Phases 3–4, unchanged, authoritative
   │  class, finding, decisive statements, mechanism paths, mechanism finding
   ▼
graph context (services/mechanisms)       herb effects (with hedging, study type), target facts
   +  experimental records (DDID, X# items)  species, study context, dataset label (never an A–E class)
   +  SUPP.AI mentions (U# items)             herb–drug questions; resolved herb AND drug mappings only;
                                            no retracted papers; study type and negation labelled;
                                            machine-extracted, never a confirmed interaction or a class
   +  LiverTox hepatotoxicity (H# items)      liver questions only; resolved herb mappings only; LiverTox
                                            likelihood score as published (never an A–E class)
   ▼
hybrid retrieval (ai/retrieval.py)         FTS + pgvector over retrieval_segment, RRF, scoped to
   │                                       the recognised herbs/drugs/targets, current evidence only
   ▼
evidence assembly (ai/context.py)          labelled items C#/S#/M#/E#/F#/X#/H#/U#, priority, de-duplication,
   │                                       token budget without truncation, licensing guard
   ▼
generation (ai/generation.py)              versioned prompts, provider interface, JSON schema,
   │                                       explicit fallback only, extractive mode
   ▼
validation (ai/validation.py)              citations, class consistency, safety claims, directives,
   │                                       unsupported enzymes/doses, dropped hedging
   ▼
AskResponse                                 classification (copied from the service), paragraphs,
                                            citations hydrated from the database, limitations,
                                            validation report, provider/model, retrieval info
```

## 2. Modules and responsibilities

| Module | Responsibility | Depends on |
|---|---|---|
| `ai/providers/` | `LLMProvider` contract; Ollama, Anthropic, OpenAI adapters (plain HTTP); registry; scripted provider for tests | `core.config` |
| `ai/embeddings.py` | `EmbeddingProvider` contract; Ollama embeddings; L2 normalisation; model identity (name, digest, dimension) | `core.config` |
| `ai/indexing/` | Segmentation strategies (pure); incremental indexer (segments, embeddings, HNSW index, status) | models, ingestion context |
| `ai/retrieval.py` | Keyword and vector retrievers, entity scopes, RRF, de-duplication, hydration with provenance | repositories, models |
| `ai/fusion.py` | Reciprocal Rank Fusion (pure) | — |
| `ai/query.py` | Entities and intent (deterministic) | existing plant/drug services, Phase 4 target table |
| `ai/context.py` | Evidence assembly and prompt rendering | API schemas of Phases 3–4 |
| `ai/generation.py` | Prompts, provider chain, extractive mode | providers, validation |
| `ai/validation.py` | Output parsing and validation (pure), incl. `experimental_as_clinical` | — |
| `ai/guardrails.py` | Emergency / dosing / empty-question screening before any retrieval or model call (patterns from the earlier Evidence Assistant on `main`, e491d02 and 3861b91, including the narrower dosing patterns) | — |
| `ai/service.py` | Orchestration, concurrency limit, metrics logging | all of the above, existing services |
| `ai/evaluation.py`, `ai/cli.py` | Evaluation framework; `herbaguard ai index/status/evaluate-*` | — |
| `api/routes/ai.py` | `/api/v1/ai/ask`, `/retrieve`, `/providers`, `/health` | service, registry |

Retrieval, evidence assembly, model invocation and validation are separate modules with separate tests; the service only wires them.

## 3. Rules enforced in code (not only in prompts)

| Rule | Where |
|---|---|
| A–E class comes from the interaction service | `service._pair` copies `check()` output; `validation` rejects any other class letter |
| No safety claims, no medical directives | `validation` (`safety_claim`, `medical_directive` → answer rejected; narrow source-attributed exception, see [security.md](security.md) §4) |
| Citations only to context items; URLs and excerpts from the database | `validation` removes unknown ids; `service._citations` builds every citation from stored rows |
| Source hedging kept ("may inhibit") | stored as `target_modulation.hedge_wording`, shown in context; `hedge_dropped` check |
| No partial answers | token-limited output (`finish_reason=length`) is treated as a failure |
| No silent provider switch | only `llm_fallback_provider` is tried; the response names the provider used and failed attempts |
| Documents are data | angle brackets in source text are escaped; system prompt rule; obeying injected text is caught by validation |
| Cloud licensing | cloud providers receive no source text unless `ai_cloud_send_source_text=true`, and then only from redistributable sources |
| LiverTox likelihood score is not an interaction class; LiverTox never shows liver safety | `service._hepatotoxicity_items` labels every H# item and shows master-list and chapter scores side by side; `validation.hepatotoxicity_issue` (`livertox_score_as_class`, `hepatotoxicity_overstated` → critical) |
| SUPP.AI mentions never confirm an interaction, never show "no interaction", never displace other evidence | U# items have no reserved slot and rank last (priority 60+); `ai/mentions` derives the study type (flags plus in-vitro/animal downgrades) and clause-aware, pair-specific negation and warnings; `validation.mention_issue`: `supp_ai_absence_as_no_interaction` and `supp_ai_mention_as_confirmed` → critical for SUPP.AI-only paragraphs, `mention_nonhuman_as_clinical` and `negated_mention_as_positive` → paragraph removed; `experimental_as_clinical` also covers U# items |
| Model writes nothing | the AI layer has no write path to scientific tables; only indexing (CLI) writes segments/embeddings |

## 4. Degradation

| Condition | Behaviour |
|---|---|
| Ollama not running / model missing | `/ai/ask` → 503 with a hint to `/ai/retrieve`; `/ai/retrieve` falls back to keyword search; rest of the API unaffected |
| Embedding model missing | keyword retrieval only, reported in `retrieval.notes` and `/ai/health` |
| Segments not yet embedded (new data) | semantic search covers embedded segments; keyword search covers all; `/ai/health` shows the number missing |
| Cloud provider selected without key/model | 503 `not_configured` on AI endpoints only; application starts normally |
| No citable evidence | no model call; `status = insufficient_evidence` |
| Model answer fails validation | `status = rejected_by_validation`, no answer text; classification and evidence still returned (or explicit fallback) |
| Too many concurrent questions | 429 (`ai_max_concurrent_requests`, default 2; CPU inference) |

## 5. Expansion compatibility

See [hybrid-retrieval.md](hybrid-retrieval.md) §6 and [embedding-models.md](embedding-models.md) §5: no source list, corpus size or model is hard-coded; new sources become searchable after `herbaguard ai index`.

## 6. Replacement of the earlier Evidence Assistant from `main`

`main` (commits e491d02, 3861b91) contained an earlier assistant (`/assistant`, `ai/llm.py`, `services/assistant.py`, vector search over `chunk.embedding`). When the branches were merged, this AI layer replaced it; one AI pipeline remains (`/api/v1/ai/*`, one `herbaguard ai` command group). What it covered is kept or ported:

- **Kept from the 2026-11-06 reconciliation:** emergency screening, the dosing decline with quoted posology, and one controlled regeneration with the validation problems fed back (`llm_max_regenerations`, default 1).
- **Ported at the merge:** the narrower dosing patterns (an amount must be asked about, so "Can I take ginseng with my blood pressure tablets?" is an evidence question); the fabricated-reference check (a PMID, DOI or URL not present in the context removes the paragraph, `unsupported_reference`); the safety phrasings "no danger …" and "there is no interaction"; and the original screening, reference and safety test cases (`tests/ai/test_ported_assistant_rules.py`).
- **Already covered:** evidence pinning (decisive statements always enter the context), prompt-injection rule for passages, deterministic classes, ambiguity handling (409 with candidates), several herbs per question, citation checks against context ids.
- **Not carried over:** the Ollama-only client and extractive quote composer (replaced by the provider layer and the `extractive` provider); vector search over `chunk.embedding` (removed by migration 0005, ADR-021); the separate full-text ranking for official sources; the sentence-level citation share; the `herbaguard ai embed/ask/eval` commands and their 17-question evaluation file. Decisions: ADR-025 and ADR-026.

