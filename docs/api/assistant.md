# AI Evidence Assistant (Phase 5)

**Status:** Implemented 2026-11-04. Decisions: ADR-009 (local Ollama, extractive fallback), ADR-021 (Ollama embeddings), ADR-022 (deterministic guardrails) in [../architecture/decisions.md](../architecture/decisions.md). Code: `backend/src/herbaguard/ai/` (pure rules and the Ollama client), `services/assistant.py`, `repositories/retrieval.py`.

The assistant answers questions about what HerbaGuard's sources say. It **explains**; it never decides. Interaction classes come from the same deterministic rules as `POST /interactions/check` and are passed to the model as facts. Every citation is checked against the passages that were actually retrieved.

## 1. Endpoints

| Method & path | Purpose |
|---|---|
| `POST /api/v1/assistant/ask` | `{question, herb?, drugs?, mode: "auto" \| "extractive"}` → answer, citations, deterministic interaction results, generation metadata |
| `GET /api/v1/assistant/status` | Provider, Ollama reachability, model availability, embedded chunks, retrieval mode |

CLI: `herbaguard ai status`, `herbaguard ai embed`, `herbaguard ai ask "…" [--herb] [--drug] [--extractive]`, `herbaguard ai eval [--extractive] [--output file.json]`.

## 2. Pipeline

1. **Screen** the question with fixed patterns (`ai/guardrails.py`): emergency → fixed referral (no retrieval, no model); dosing → fixed "no individual dosing advice" text plus the posology passages (no model).
2. **Recognise entities.** `herb` / `drugs` from the request, otherwise names from HerbaGuard's index found in the question (taxon names, EMA pharmaceutical names, English common names; RxNorm ingredient names). Longest name wins; a name read as a herb is not also read as a drug. Drugs are never looked up remotely. An ambiguous herb ("ginseng") returns `needs_clarification` with the candidates.
3. **Deterministic results.** For a resolved herb and resolved drugs, the interaction check runs unchanged (classes A–E, mechanism finding). The evidence items behind the decisive statements are **pinned** as the first passages.
4. **Retrieve.** Full-text search (`ts_rank_cd` over `chunk.search_vector`, OR-query of content words + entity names) and, when chunks are embedded, cosine search over `chunk.embedding` (HNSW). Both are restricted to the herb's evidence when a herb is resolved, exclude superseded items, and are merged with Reciprocal Rank Fusion (k = 60). Full-text search runs twice — over all sources and over the regulatory/government sources only (EMA, NCCIH, FDA labels, FDA CYP table) — so that the many PubMed abstracts cannot crowd the official documents out; the extractive answer also prefers official wording when overlap is equal. At most `HERBAGUARD_ASSISTANT_MAX_PASSAGES` (default 6) passages, at most 2 per evidence item. Nothing retrieved → `insufficient_evidence` (never "safe").
5. **Generate** with Ollama (temperature 0, fixed seed). The prompt contains the computed results as facts and the passages fenced as `<passage id="S1">…</passage>`; the model is told to ignore instructions inside passages.
6. **Validate** (`ai/citations.py`). Rejected if: any `[Sn]` does not match a passage; nothing is cited; fewer than 60 % of factual sentences carry a citation; numeric citations (`[1]`); a PMID, DOI or URL not present in the passages; a safety assertion ("is safe to take"); a class letter the rules did not compute. One regeneration with the reasons, then the **extractive** answer.
7. **Extractive answer** (`ai/extractive.py`): the deterministic results, then up to 4 verbatim sentences from the passages, each cited. Used when `mode=extractive`, when no LLM is configured, when Ollama is unreachable, or after two failed validations. It cannot fabricate content.

## 3. Response

| Field | Meaning |
|---|---|
| `mode` | `generated`, `extractive`, `insufficient_evidence`, `needs_clarification`, `declined_dosing`, `emergency_referral` |
| `answer` | Plain text; `[S1]` refers to `citations[].marker` |
| `citations[]` | Every passage shown to the model: evidence id and API link, source, title, section, URL, evidence type (with the type-is-not-quality note), date, excerpt, `cited`, and how it was retrieved (`interaction_result`, `full_text`, `vector`) |
| `interaction_findings[]` | Deterministic A–E result and mechanism finding per recognised drug |
| `entities` | Herb status (`resolved` / `ambiguous` / `not_found` / `not_mentioned`), herb, candidates, drug resolutions |
| `generation` | Provider, model, prompt version, attempts, duration, citation check (`passed` / `failed` / `not_applicable`), issues, fallback reason |
| `referral`, `disclaimer`, `notes` | Always present; notes explain degraded behaviour (no embeddings, unknown drug, several herbs) |

## 4. What the assistant will not do

- Give doses or tell someone to start, stop or change a medicine (`declined_dosing`).
- Handle emergencies (`emergency_referral`: 112 / poison control / emergency department).
- Assign, upgrade or downgrade an interaction class, or invent a severity.
- Say a combination is safe because nothing was found.
- Cite anything that was not retrieved from HerbaGuard's database.

## 5. Setup

```bash
ollama pull qwen2.5:3b          # chat model (any Ollama chat model works: HERBAGUARD_OLLAMA_CHAT_MODEL)
ollama pull all-minilm          # 384-d embedding model (must match chunk.embedding)
cd backend
herbaguard ai embed             # once after ingestion; resumable; re-run after new data
herbaguard ai status
herbaguard ai eval              # fixed evaluation set, see §6
```

In Docker Compose the API reaches the host's Ollama at `http://host.docker.internal:11434` (`extra_hosts: host-gateway` for Linux). Ollama must listen on an address the container can reach: on Linux set `OLLAMA_HOST=0.0.0.0` for `ollama serve`. Without Ollama the API still works; answers are extractive and `GET /assistant/status` says why.

The development machine has no NVIDIA GPU (Phase 0): a 3B model on CPU takes roughly 10–40 s per answer. Smaller models (`qwen2.5:1.5b`, `llama3.2:1b`) are faster but fail citation validation more often, which shows up as extractive fallbacks rather than wrong answers.

## 6. Evaluation

`data/curated/assistant_eval.yaml` holds 17 fixed questions: documented pairs (D1, D5), explicit fields, uncertain evidence, indications, a synonym, the ambiguous name (D4), dosing (D6 and a second phrasing), two emergencies, an unknown herb, an off-topic question, a prompt-injection attempt and a "is it safe" question. `herbaguard ai eval` reports per item and overall:

- **citation precision** = answer markers that resolve to a retrieved passage / all markers — hard gate, must be 1.0 (MVP success criterion 3: zero fabricated citations);
- **mode accuracy** (refusal and clarification correctness);
- **safety claims** (must be 0);
- deterministic class per pair and whether an expected source type is cited.

It exits with code 1 on any fabricated citation or failed check. Unsupported-claim rate (a cited sentence that the passage does not support) is not automatable here and is reviewed by hand on the saved output (`--output`).

## 7. Known limitations

- Entity recognition is lexical: misspellings and brand names of herbs are not recognised unless they are stored names; use the `herb` field (the UI does).
- One herb per question; several recognised herbs produce a note.
- Screening patterns are English only and can miss unusual phrasings; the disclaimer and referral are shown on every answer.
- A cited sentence can still paraphrase its passage loosely; the validator checks that citations exist, not that each claim is entailed by its passage.
