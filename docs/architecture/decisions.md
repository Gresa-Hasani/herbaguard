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

## ADR-009 — LLM provider

- **Status:** **Pending** — user decision required before Phase 5 (hosted API key, local Ollama, or extractive-only). The architecture supports all three behind one interface; extractive-only mode will always be available.

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

