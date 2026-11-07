# Evidence Assistant — request timeouts

`POST /api/v1/ai/ask` runs a local CPU language model, so it is the only slow request in HerbaGuard. Every layer between the browser and Ollama must wait at least as long as the layer behind it, otherwise a request the backend is still serving is cut off and the user sees a failure for an answer that would have been valid.

## Measured latency (CPU-only development machine, Qwen3-4B Q4_K_M, exact question "What does the evidence say about St John's wort and warfarin?")

| Run | Total | Generation | Retrieval | Tokens in / out | Result |
|---|---|---|---|---|---|
| Model not loaded | 227.5 s | 224.3 s | 2.4 s | 3,627 / 450 | answered, 5 citations |
| Model already loaded | 118.9 s | 116.8 s | 1.6 s | 3,627 / 463 | answered, 5 citations |

Both runs returned HTTP 200 with `status = answered`. The difference between them (about 107 s) is the model load that follows Ollama's default 5-minute idle unload; the remaining ~117 s is inference on ~3.6k prompt tokens plus ~450 generated tokens with 0 GPU layers. Retrieval, classification and validation together are under 3 s. Thinking is already off (`think: false`). Free memory was about 3.8 GB, so resource pressure may add to the figures but was not isolated. These are single measurements on one machine, not a benchmark.

## Root cause of the reported timeout

The browser gave up after 120 s (`useAsk`, `timeoutMs: 120_000`). Warm generation needs about 119 s and cold generation about 227 s, while the backend allows 240 s per attempt. The backend succeeded; the frontend abandoned it. The Docker nginx proxy had the same 120 s limit on `/api/`.

## Layers

| Layer | Setting | Value | Rationale |
|---|---|---|---|
| Ollama keep-alive | `HERBAGUARD_OLLAMA_KEEP_ALIVE` | `30m` | Avoids the ~107 s reload between questions. Does not change output. |
| Backend, per attempt | `HERBAGUARD_LLM_TIMEOUT_SECONDS` | 240 s (unchanged) | Cold run measured at 224 s, so there is only a small margin on slow hardware. |
| Backend, attempts | `HERBAGUARD_LLM_MAX_REGENERATIONS` | 1 (unchanged) | One controlled regeneration after a failed validation: worst case 2 × 240 s. Validation and regeneration stay on. |
| Dev proxy (Vite) | `HERBAGUARD_PROXY_TIMEOUT_MS` | 600 s | Above the browser wait. |
| Production proxy (nginx) | `location /api/v1/ai/` | 600 s | Same; other `/api/` routes keep 120 s. |
| Browser | `VITE_ASK_TIMEOUT_MS` | 540 s | 2 × 240 s + 60 s margin for retrieval, validation and hops. |

Rule: browser (540 s) < proxies (600 s), and browser ≥ backend worst case (480 s + retrieval). Change them together.

## Behaviour in the interface

- One request at a time: a synchronous guard prevents a double submit from starting two generations.
- Progress shows only elapsed seconds measured in the browser; no stage timings are invented.
- The user can cancel; leaving the page also cancels.
- The question stays in the box after any failure, and a Retry button appears for retryable failures. Nothing is retried automatically.
- Distinct states: browser timeout, cancelled, service unreachable, backend generator timeout (503, `details.kind = timeout`), model unavailable (other 503), busy (429), ambiguous entity (409), other backend error. A validation rejection is a successful response with `status = rejected_by_validation` and is shown as such.
- No failure is presented as evidence of safety, and no partial text is displayed.
