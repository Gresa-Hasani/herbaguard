# LLM Providers (Phase 5)

HerbaGuard depends on a provider **interface**, not on a vendor. Implementation: `backend/src/herbaguard/ai/providers/`.

## 1. Contract

```python
class LLMProvider(Protocol):
    name: str; model: str; is_cloud: bool
    def generate(self, request: GenerationRequest) -> GenerationResult: ...
    def status(self, *, probe: bool) -> ProviderStatus: ...
```

`GenerationRequest`: system instructions, messages, JSON schema (structured output), temperature, max output tokens, seed. `GenerationResult`: provider, model (as reported), text, finish reason, token usage, duration. Errors are normalised to `ProviderError(kind)`: `not_configured`, `unavailable`, `timeout`, `authentication`, `rate_limited`, `model_not_found`, `bad_request`, `bad_response`, `refused`. Messages never contain keys or response bodies.

Adapters use plain HTTP through `httpx` (no vendor SDKs): one timeout and error path, and contract tests with mocked HTTP.

## 2. Implemented providers

| Provider | Endpoint | Structured output | Key | Model | Verified |
|---|---|---|---|---|---|
| **Ollama** (default) | `POST {base}/api/chat`, `think: false` | `format` = JSON schema | none | `HERBAGUARD_LLM_MODEL` (default `qwen3:4b`) | **Live** on the development machine (Qwen3-4B Q4_K_M) and mocked |
| Anthropic | `POST {base}/v1/messages` | forced tool call with `input_schema` | `HERBAGUARD_ANTHROPIC_API_KEY` | `HERBAGUARD_ANTHROPIC_MODEL` (no default) | **Mocked only** (no key available) |
| OpenAI | `POST {base}/chat/completions` | `response_format: json_schema` | `HERBAGUARD_OPENAI_API_KEY` | `HERBAGUARD_OPENAI_MODEL` (no default) | **Mocked only** (no key available). `HERBAGUARD_OPENAI_BASE_URL` allows OpenAI-compatible servers |
| `extractive` | — | — | — | — | Deterministic answer from stored excerpts, no model |

No model identifier is hard-coded in business logic; the only default is the local `qwen3:4b` tag requested for this phase.

**Not verified against live cloud APIs.** Request and response shapes follow the providers' public API documentation and are pinned by contract tests (`tests/ai/test_providers.py`); a live call should be made once keys are available.

## 3. Selection and fallback

```
HERBAGUARD_LLM_PROVIDER=ollama            # ollama | anthropic | openai | extractive
HERBAGUARD_LLM_MODEL=qwen3:4b
HERBAGUARD_LLM_FALLBACK_PROVIDER=         # optional; e.g. extractive or ollama
```

* Switching provider = changing configuration; the pipeline, API and validation are unchanged.
* A fallback is used **only if configured**. It receives the same evidence context. The response records the provider that answered (`generation.provider`, `generation.model`) and every failed attempt (`generation.failed_attempts`). A token-limited (partial) or invalid answer is a failure, never an answer.
* Unselected providers without configuration are simply reported as not configured (`GET /api/v1/ai/providers`); a selected one fails clearly with 503 on the AI endpoints only.
* Adding a provider: one adapter module and one entry in `registry._BUILDERS`.

## 4. Licensing guard for cloud providers

Stored source text (PubMed abstracts, EMA monograph text, label text) has its own licence (`source.licence_status`, `source.redistributable`). Cloud providers therefore receive source text **only** if `HERBAGUARD_AI_CLOUD_SEND_SOURCE_TEXT=true`, and then only items from sources registered as redistributable; excluded items are counted in the answer's limitations. With the default (`false`) a selected cloud provider refuses (`refused`). Check each source's licence before enabling. The local default (Ollama) sends nothing off the machine.

## 5. Running locally

```bash
# 1. Install Ollama (https://ollama.com) and start it.
ollama pull qwen3:4b              # ~2.5 GB, Q4_K_M; or use an installed Qwen3-4B tag via HERBAGUARD_LLM_MODEL
ollama pull nomic-embed-text       # default embedding model (see embedding-models.md)
# 2. Build the retrieval index (incremental; re-run after any ingestion)
cd backend && herbaguard ai index
# 3. Check
curl http://127.0.0.1:18010/api/v1/ai/providers
curl http://127.0.0.1:18010/api/v1/ai/health
```

Anthropic / OpenAI: set the key and the model in `.env` (never commit it), set `HERBAGUARD_LLM_PROVIDER`, and decide on `HERBAGUARD_AI_CLOUD_SEND_SOURCE_TEXT` (§4).

## 6. Measured performance (development machine, CPU only)

AMD Ryzen 7 5700U (8 cores), 14 GB RAM, no discrete GPU, Ollama 0.40.13, Qwen3-4B Q4_K_M, `think: false`, `num_ctx` 8192:

| Measurement | Value |
|---|---|
| Model load (cold) | 11 s |
| Prompt processing | ≈ 52 tokens/s |
| Generation | ≈ 8.3 tokens/s |

End-to-end answer latencies on the evaluation set are in [evaluation.md](evaluation.md). Context is therefore capped at ~2,600 tokens by default (`HERBAGUARD_AI_CONTEXT_MAX_TOKENS`) and the timeout is 240 s; concurrent questions are limited to 2 (429 beyond).

## 7. Cost

Local inference has no per-request cost. Cloud usage is billed by the provider per token; `generation.input_tokens` / `output_tokens` are returned with every answer and logged (`ai_request` event) so cost can be computed; HerbaGuard does not price tokens itself.
