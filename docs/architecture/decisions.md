# Architecture Decision Records

Short records of decisions that shape HerbaGuard. Status values: *Accepted*, *Superseded*, *Pending*.

---

## ADR-001 — Modular monolith

- **Status:** Accepted (Phase 1)
- **Context:** One small team, ~5.5 days to the deadline, small curated dataset, one-command local demo required.
- **Decision:** One Python package (`herbaguard`) for API, domain logic, ingestion and AI; one React SPA; one database. Module boundaries are enforced by package structure and documented dependency rules ([overview.md](overview.md) §2).
- **Alternatives:** Microservices (ingestion, API, AI as separate services) — rejected: more deployment and integration work, no scaling need.
- **Consequences:** Simple deployment and shared models; must keep dependency rules disciplined so modules could be split later.

## ADR-002 — PostgreSQL with pgvector; Neo4j deferred

- **Status:** Accepted (Phase 1). The user did not object to the Phase 0 recommendation; can be revisited.
- **Context:** Needed: relational integrity with provenance, keyword search, semantic search, and 3–4-hop relationship queries (herb → constituent → enzyme ← drug) over a few hundred nodes. The organizers' Neo4j import endpoints are admin-only (HTTP 401).
- **Decision:** One PostgreSQL 16 database with the pgvector extension. Graph relationships are explicit edge tables (`target_modulation`, `drug_target_role`, `herbal_substance_constituent`, `drug_class_membership`, `interaction_assertion`). Graph views will be served as JSON nodes/edges.
- **Alternatives:** Neo4j (second datastore, sync code, ~1 day of work); a separate vector database (Qdrant/Chroma) — both rejected for the MVP.
- **Consequences:** One transaction boundary for data, provenance and embeddings. The edge tables can be exported to Neo4j or RDF later without changing the canonical model.

## ADR-003 — Deterministic interaction classification

- **Status:** Accepted (Phase 0 framework, Phase 1 schema)
- **Decision:** Interaction classes A–E are computed by rule-based code in `herbaguard.domain` from stored assertions and mechanism edges. The LLM (Phase 5) may only explain an already-computed result and must cite retrieved sources.
- **Consequences:** Reproducible, testable classifications; the AI cannot raise or lower a safety class.

## ADR-004 — Text + CHECK constraints instead of native ENUM types

- **Status:** Accepted (Phase 1)
- **Decision:** Vocabulary columns are `varchar` with CHECK constraints generated from Python `StrEnum`s.
- **Consequences:** Easier migrations when vocabularies grow (alter the CHECK, no `ALTER TYPE`). Values are defined once in `domain/enums.py`.

## ADR-005 — Synchronous SQLAlchemy with psycopg 3

- **Status:** Accepted (Phase 1)
- **Decision:** Synchronous engine and sessions for API, ingestion and Alembic.
- **Alternatives:** asyncpg/async SQLAlchemy — rejected; adds complexity without a throughput need. FastAPI runs sync dependencies in a thread pool.

## ADR-006 — Vite SPA instead of Next.js

- **Status:** Accepted (Phase 1)
- **Decision:** React 18 + TypeScript + Vite; Tailwind CSS v4; React Router 6 (v7 future flags on); TanStack Query 5; Vitest 3.
- **Reason:** The backend is a separate service; server-side rendering adds nothing for this app. nginx serves the static build and proxies `/api` (same origin).

## ADR-007 — Privacy-preserving logging

- **Status:** Accepted (Phase 1)
- **Decision:** Log one line per request with method, path, status, duration and request ID. Do not log query strings, bodies or traceback local variables; disable uvicorn's access log.
- **Reason:** Users will type medication and herb names; these are health data.

## ADR-008 — Non-default host ports

- **Status:** Accepted (Phase 1)
- **Context:** On the development machine, ports 5432, 5433, 8000 and 8010 were taken by other projects' containers.
- **Decision:** Defaults `5455` (db), `18010` (api), `18080` (web), bound to `127.0.0.1`, all overridable in `.env`. Connection strings use `127.0.0.1`, not `localhost`: on Windows, `localhost` resolved to IPv6 first and each connection stalled about 5 seconds before falling back.

## ADR-009 — LLM provider: local Ollama, extractive fallback

- **Status:** Accepted (Phase 5; was pending since Phase 0).
- **Decision:** A provider-independent interface (`ai/providers/`) with three adapters over plain HTTP: **Ollama (default, local, `qwen3:4b`)**, Anthropic and OpenAI (optional; key and model only from configuration). An `extractive` mode composes answers from stored excerpts without a model. Provider and optional fallback are chosen by configuration only; HerbaGuard never switches provider on its own and records which provider answered. Details: [../ai/llm-providers.md](../ai/llm-providers.md).
- **Reason:** The platform must run end to end without paid services (judges, local development), while allowing a stronger hosted model when available.
- **Consequences:** CPU-only inference is slow (~1–2 min per answer on the development machine); cloud adapters are contract-tested with mocked HTTP until keys are available; cloud providers receive source text only under the licensing guard.
- **History:** An earlier variant on `main` (2026-11-04) used local Ollama (`qwen2.5:3b`) behind a `ChatModel` protocol with an automatic extractive fallback for the Evidence Assistant (`/assistant`). It was replaced by this provider-independent interface when the Phase 5 AI/RAG branch was merged; see ADR-025 and ADR-026.

## ADR-010 — Python packaging with pip

- **Status:** Accepted (Phase 1), revisit if the user installs `uv`.
- **Decision:** `pyproject.toml` (hatchling) with `pip install -e ".[dev]"`. No lockfile yet; dependency ranges are bounded by major version.
- **Consequences:** Builds are less reproducible than with a lockfile — listed as a known issue.

## ADR-011 — Ship missing TLS intermediate certificates instead of disabling verification

- **Status:** Accepted (Phase 2)
- **Context:** `*.ethcstwin.di.uoa.gr:65000` and `list.worldfloraonline.org` send only their leaf certificate. Windows `curl` fetches the missing intermediate itself, Python/OpenSSL (and therefore CI and Docker) do not.
- **Decision:** Ship the two public intermediate certificates in `backend/src/herbaguard/ingestion/certs/` (source URL, validity and SHA-256 fingerprint in each file), after verifying that each chains to a root already in `certifi`. Load them in addition to `certifi`. TLS verification is never disabled.
- **Consequences:** The intermediates expire 2027 (GeoTrust) and 2037 (HARICA) and must be refreshed if the servers change CA. The organizers could fix the server configuration; this is reported in the Phase 2 report.

## ADR-012 — Deterministic, typed interaction statements from a curated lexicon

- **Status:** Accepted (Phase 2)
- **Decision:** Interaction statements are extracted with a committed lexicon (`data/curated/interaction_lexicon.yaml`) and deterministic sentence rules, not with an LLM or a general NER model. Each statement keeps the verbatim sentence, the source's own drug/herb wording, conditions, mechanism sentence and severity wording, and gets a `statement_type` (`interaction`, `precaution`, `no_interaction_reported`, `uncertain`, `unclassified`).
- **Reason:** Reproducibility and auditability for a safety-relevant output; every lexicon entry records the source wording that motivated it.
- **Consequences:** Recall is limited to lexicon terms (unmapped terms are logged, not lost). Phase 3 computes interaction classes from these typed statements.

## ADR-013 — Independent verification of PDF extraction

- **Status:** Accepted (Phase 2)
- **Decision:** EMA monograph text extracted with pdfplumber (word coordinates) is cross-checked against PDFium (pypdfium2), per section and per use-category column, on recall, precision and token-order similarity. Results are stored with each document and checked by `herbaguard validate`.
- **Consequences:** Column mixing or lost text in future monograph layouts is detected automatically instead of silently degrading interaction data.

## ADR-014 — Rule-based interaction classes with a finer "finding"

- **Status:** Accepted (Phase 3)
- **Decision:** The A–E class is computed by a pure function (`domain/interactions.py`) with a fixed decision order. Each result also carries a `finding` (documented interaction / documented precaution / potential / uncertain / label subject not confirmed / mentioned without interaction wording / no interaction reported / no evidence found / insufficient information), so precautions, uncertain findings and "nothing found" are never merged. Severity is relayed verbatim, never computed. Only REG/GOV statements can give class A; PubMed records are never used for classification.
- **Reason:** Auditability for a safety-relevant output. A model cannot be cited, but a rule can.
- **Consequences:** Rules are documented in `docs/api/interaction-classification.md` and pinned by tests. Class B from mechanisms waits for Phase 4.

## ADR-015 — Label statements must be about the label's drug

- **Status:** Accepted (Phase 3)
- **Context:** On real data, an isotretinoin label sentence about St John's wort and *hormonal contraceptives* made "St John's wort + isotretinoin" class A.
- **Decision:** An openFDA statement can be decisive only if the sentence names the label's drug, or if it sits in the `drug_interactions`, `contraindications` or `boxed_warning` section. Otherwise it is context, and alone it gives class C `label_subject_not_confirmed`.
- **Consequences:** 7 of 156 real pairs move from A to C. Probably 6 of them are under-classified; the sentence stays visible. A Phase 4/5 refinement (e.g. reviewed exceptions) could restore them with an audit trail.
## ADR-016 — Drug-side mechanism data from FDA's healthcare-professional CYP/transporter table
- **Status:** Accepted (Phase 4)
- **Context:** Class B needs "drug D is a substrate of enzyme/transporter E" from an authoritative, redistributable source. DrugBank (licence) and PharmGKB (pharmacogenomic focus, share-alike) were excluded; FDA's drug-*development* table lists only index drugs (≈15 substrates). FDA's *For Healthcare Professionals* table (245 rows, content current as of 2026-05-29) lists clinical substrates, inhibitors and inducers with potency categories for 7 CYPs and 9 transporters ([../data/mechanism-sources.md](../data/mechanism-sources.md)).
- **Decision:** Ingest that table (`fda_cyp_table`, evidence type GOV). The column defines role and potency; footnotes are kept as conditions; non-drug rows are mapped explicitly in `data/curated/mechanism_sources.yaml`; drug names go through RxNorm as in Phase 2. A browser-saved copy can be ingested when fda.gov refuses automated clients (recorded as such).
- **Consequences:** Drug-side coverage is "examples", not exhaustive — stated in every response. Re-running replaces edges the current page no longer supports.
## ADR-017 — Deterministic, conservative rules for mechanism-based class B
- **Status:** Accepted (Phase 4)
- **Decision:** A herb → enzyme ← drug path supports class B only if the effect is stated for the herbal substance (not a constituent), by a REG/GOV source (in-vitro/animal sentences are stored with that study type), is induction or inhibition not graded weak, and the drug is a substrate per the FDA table. CYP3A4/5 match FDA's grouped CYP3A; nothing else is cross-matched. All paths are shown; non-qualifying ones with reasons. Mechanism-only results carry an explicit "size of effect unknown" caveat. Rules: [../api/mechanism-paths.md](../api/mechanism-paths.md).
- **Alternatives:** Any shared enzyme → B (rejected: would mark most drugs "potential" for St John's wort and turmeric); computing a risk score from potencies (rejected: HerbaGuard never computes severity).
## ADR-018 — Herb effects extracted from stored monograph text by narrow sentence rules
- **Status:** Accepted (Phase 4)
- **Decision:** EU monograph section 4.5 text stored in Phase 2 is re-read; an effect is stored only for a verb form ("induce(s)", "inhibit(s)", "is an inducer of") whose subject is the herbal preparation, with the targets after the verb read from a fixed table. Relative clauses about other medicines, negations and unclear subjects never produce an edge and are logged (`ema_mechanism_sentence_not_used`) for review. Provenance points to the monograph PDF record and quotes the sentence; `herbaguard validate` checks every quote against the stored section text.
- **Consequences:** Precision over recall; the logged sentences show what is missed.
## ADR-019 — Mechanism edges are re-derived, not versioned row by row
- **Status:** Accepted (Phase 4)
- **Decision:** Each `mechanisms` run upserts the edges it derives (deterministic UUIDs) and deletes edges of the same source that it no longer derives, together with their provenance links — only if the run had no error-level issues. The source documents themselves keep full lineage in `source_record` (every page version is kept).
- **Alternatives:** A `status` column with `superseded` as for interaction assertions (rejected for now: edges are a derived index of stored documents, not statements users cite on their own).
## ADR-020 — Explicit mechanism finding per herb–drug pair
- **Status:** Accepted (Phase 4 audit, 2026-11-03)
- **Context:** Phase 4 returned paths and a count of qualifying paths. An empty list could mean "herb not identified", "no herb effect stored", "drug not in FDA's table" or "no shared target", and the paths endpoint showed the mechanism-finding caveat even when there was no path. Opposite statements (induction and inhibition) were not detected.
- **Decision:** A pure function `assess_mechanism` gives each pair one finding: `mechanism_supported`, `conflicting_mechanism_evidence`, `experimental_mechanism_evidence_only`, `insufficient_mechanism_evidence`, `no_documented_mechanism_found` or `not_assessed`, with an explanation that never implies safety. Rule 7 makes conflicting targets non-qualifying. Only `mechanism_supported` can influence the A–E class (unchanged: B when no statement gives A). Hedged source wording is stored and shown, not scored.
- **Consequences:** No change to any Phase 3 result. Users can see why a mechanism result is empty. Rules: [../api/mechanism-paths.md](../api/mechanism-paths.md).

## ADR-021 — Model-independent retrieval index (segments + per-model embeddings)

- **Status:** Accepted (Phase 5)
- **Context:** Phase 1 reserved `chunk.embedding vector(384)` (never populated). A fixed column ties the schema to one model, cannot hold a benchmark of several models, and gives no stale detection. Chunks are also the canonical citation text used by Phase 2 validation, so they cannot be re-cut for retrieval.
- **Decision:** Migration 0005 adds `retrieval_segment` (character ranges of chunk text, strategy + version, chunk/text hashes, full-text vector) and `segment_embedding` (one vector per segment and model, unconstrained dimension with a CHECK against `dimension`, model version, provider, hash, timestamp; partial HNSW index per model). The unused chunk vector column is dropped. Indexing is an incremental CLI run (`herbaguard ai index`) recorded as an ingestion run.
- **Consequences:** Models and dimensions can be changed or compared without migrations; vectors of different models/versions are never compared; only new or changed text is re-embedded; the index is derived data and can be rebuilt. The Phase 1 vector test was ported to the new tables (same intent, plus a two-model check).

## ADR-022 — The language model explains; code decides and validates

- **Status:** Accepted (Phase 5)
- **Decision:** The AI layer never classifies. `/ai/ask` calls the existing interaction service and returns its classification unchanged; the model receives it as context. Model output is structured JSON citing context ids and is validated in code: invalid citations and unsupported paragraphs are removed; a different class letter, a safety claim, a medical directive, or nothing left → the answer is rejected (`rejected_by_validation`) and not shown. Citation URLs and excerpts are always taken from the database. Token-limited (partial) output is a failure.
- **Alternatives:** Trusting prompt instructions alone (rejected: not verifiable); an LLM judge (rejected as sole check: not deterministic, same failure modes).
- **Consequences:** Some correct answers are rejected (conservative patterns); validation does not prove paraphrase faithfulness — answers always ship with verbatim excerpts and manual review is part of the evaluation.

## ADR-023 — Deterministic question understanding

- **Status:** Accepted (Phase 5)
- **Decision:** Entities are found by n-gram lookup in the existing name tables and resolved with the existing services (ambiguity → HTTP 409 with candidates, never a guess; brand names through RxNav, at most three lookups); intent comes from fixed rules. No LLM is involved in entity resolution.
- **Consequences:** Reproducible scoping of retrieval and classification; misspellings and names not in the tables are not recognised (the question is then answered only from high-similarity passages or reported as insufficient).

## ADR-024 — No storage of questions or answers

- **Status:** Accepted (Phase 5)
- **Decision:** `/ai/ask` stores nothing about the request; the `ai_request` log event holds only metrics (intent, status, provider, model, durations, counts, tokens, validation issue counts). Evaluation reports are files produced on demand.
- **Consequences:** No retention or deletion obligations for user questions in the MVP; usage analytics beyond these metrics are not possible.

## ADR-025 — Embeddings from Ollama (`all-minilm`, 384-d) instead of sentence-transformers
- **Status:** Superseded by ADR-021 (migration 0005 removed `chunk.embedding`). Recorded on `main` as ADR-021 on 2026-11-04; renumbered when the branches were merged.
- **Context:** The schema reserved `chunk.embedding vector(384)` for `bge-small-en-v1.5` via sentence-transformers. That adds PyTorch (~1 GB) to the API image, and ADR-009 already requires Ollama.
- **Decision:** Embed with an Ollama embedding model returning 384 dimensions (default `all-minilm`), so no migration is needed. `herbaguard ai embed` fills the column (resumable; records `embedding_model`); vector search only uses chunks embedded with the configured model. Until chunks are embedded, retrieval is full-text only and the status endpoint says so.
- **Consequences:** One runtime dependency (Ollama) for generation and embeddings. `all-minilm` is a general-domain model; full-text search (exact drug names) and entity filtering compensate. Changing to a model with another dimension needs a migration.

## ADR-026 — Assistant guardrails are deterministic and run before the model
- **Status:** Superseded by ADR-022 for the `/ai` endpoints; the guardrails themselves (emergency referral, dosing decline with the narrower dosing patterns, clarification of ambiguous names, classes only from the interaction service) are kept in `ai/guardrails.py` and `ai/service.py`. The `/assistant` endpoint was removed. Recorded on `main` as ADR-022 on 2026-11-04; renumbered when the branches were merged.
- **Decision:** (1) Emergency wording → fixed referral text, no retrieval or generation. (2) Dosing questions → fixed "no individual dosing advice" text plus the posology passages, no generation. (3) Ambiguous herb names → clarification with candidates. (4) Interaction classes come only from `domain/interactions.py` via the interaction check and are given to the model as facts; an answer that names a class the rules did not compute is rejected. (5) Every citation must resolve to a retrieved passage, ≥60 % of factual sentences must be cited, and PMIDs/DOIs/URLs must appear in the passages; safety assertions ("is safe to take") are rejected. One regeneration, then the extractive answer. (6) Retrieved text is fenced as data and the model is told to ignore instructions in it.
- **Consequences:** Behaviour on the safety-relevant paths does not depend on the model and is pinned by tests (`tests/ai`, `tests/api/test_assistant_api.py`). Pattern-based screening can miss unusual phrasings; the persistent disclaimer and referral text are shown on every answer.
