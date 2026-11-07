# AI Endpoints (v1, Phase 5)

Conventions as in [../architecture/api-conventions.md](../architecture/api-conventions.md) (error envelope, request ids). Architecture: [../ai/architecture.md](../ai/architecture.md).

## `POST /api/v1/ai/ask`

Body: `{"question": str (3–1000), "allow_remote_drug_lookup": bool = true}`.

| Status | When |
|---|---|
| 200 | `status`: `answered`, `insufficient_evidence` (nothing citable found — no model call — or the model says the items do not answer), `rejected_by_validation` (answer withheld; classification and evidence still returned) |
| 200 | also `emergency_referral` (referral message only; no retrieval, no model) and `declined_dosing` (no generated text; official posology passages quoted) |
| 400 `bad_request` | The question contains no words, or exceeds `ai_question_max_chars` |
| 409 `ambiguous_entity` | A herb or drug name matches several entities (`details.candidates`); nothing is guessed |
| 422 `validation_error` | Empty or too long question |
| 429 `too_many_requests` | More than `ai_max_concurrent_requests` questions in progress |
| 503 `service_unavailable` | The configured generator is not configured or not reachable (`details.provider`, `details.kind`, `details.hint` → `/ai/retrieve`) |

Response (abridged, real structure):

```json
{
  "status": "answered",
  "intent": "herb_drug_interaction",
  "answer": "HerbaGuard classifies … as class A …",
  "paragraphs": [{"text": "…", "citations": ["C1"]}, {"text": "…", "citations": ["S1", "S2"]}],
  "classification": [{
    "herb": "St John's wort", "drug": "warfarin", "interaction_class": "A",
    "finding": "documented_interaction", "explanation": "…", "caveats": ["…"],
    "mechanism_assessment": {"finding": "mechanism_supported", "…": "…"},
    "method": "deterministic rules v1 …; no machine learning or LLM",
    "source": "HerbaGuard deterministic interaction classification (POST /api/v1/interactions/check)"
  }],
  "citations": [{
    "label": "S1", "kind": "statement", "role": "direct_evidence",
    "evidence_item_id": "…", "external_id": "EMA/HMPC/7695/2021#4.5#WEU", "source_code": "ema_hmpc",
    "evidence_type": {"code": "REG", "quality_assessed": false, "…": "…"},
    "url": "https://www.ema.europa.eu/…pdf", "location": "section 4.5",
    "excerpt": "Concomitant use with coumarin-type anticoagulants … is contraindicated …",
    "qualifiers": ["use category: well established use", "conditions: …"], "provenance": [{"…": "…"}]
  }],
  "limitations": ["…"], "insufficient_evidence": false,
  "entities": [{"kind": "herb", "mention": "st john's wort", "name": "St John's wort", "identifier": "Hyperici herba"}],
  "personal_advice_requested": false,
  "validation": [{"rule": "invalid_citation", "severity": "removed", "message": "…", "paragraph": 1}],
  "generation": {"mode": "model", "provider": "ollama", "model": "qwen3:4b", "prompts": ["system_v1", "interaction_v1"],
                 "input_tokens": 2950, "output_tokens": 210, "duration_ms": 95000, "failed_attempts": []},
  "retrieval": {"mode_requested": "hybrid", "mode_used": "hybrid", "embedding_model": "nomic-embed-text", "candidates": {"keyword": 40, "semantic": 40}, "…": "…"},
  "disclaimer": "…"
}
```

`classification` is copied from the interaction service and is identical to `POST /interactions/check` for the same pair. `citations` are built from stored rows only (`url` from provenance, `excerpt` = stored text, or for `graph_context` items the deterministic relationship description). Citation labels: `C` classification, `S` source statement, `M` graph relationship, `E` retrieved excerpt, `F` catalogue fact, `X` experimental record from an external dataset (DDID; role `experimental_evidence`, with species, study context and the dataset's own label — never an A–E class), `P` NIH DSLD product label (herb-only questions; role `product_label_information`, manufacturer wording, never clinical evidence or an A–E class). `generation.regenerations` counts corrected re-requests after a failed check.

## `POST /api/v1/ai/retrieve`

Retrieval without a language model (debugging, evaluation, clients that only want evidence).

Body: `{"query": str, "mode": "keyword"|"semantic"|"hybrid" = "hybrid", "top_k": 1–50, "sources": [..], "evidence_types": [..], "herb": str?, "drug": str?, "target": str?}` — `herb`/`drug`/`target` restrict to evidence linked to that entity (combined with AND); unknown → 404, ambiguous herb → 409.

Items: segment and evidence ids, external id, source with licence status and `redistributable`, evidence type (`quality_assessed: false`), title, URL, dates, section, verbatim `excerpt` with character offsets, linked herbs, provenance, `fused_score`, per-retriever `ranks`, `similarity`, `keyword_score`. `retrieval.mode_used` is `keyword` when no embedding model is available (with a note).

## `GET /api/v1/ai/providers`

Every generation provider with `selected`, `fallback`, `configured`, `reachable` (`null` = not probed; cloud providers are never called), `detail`; the embedding model with dimension and version; `cloud_source_text_allowed`. Never contains keys.

## `GET /api/v1/ai/health`

Components `database`, `embedding`, `retrieval`, `generation` with `ok` / `degraded` / `unavailable` / `not_configured`, and index coverage (`segments`, `evidence_items_indexed`, `embedded_current`, `stale_or_missing`, model, version, dimension). Probes only the local Ollama; never calls a paid API.
