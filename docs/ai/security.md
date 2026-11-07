# AI Security, Privacy and Reliability (Phase 5)

## 1. Secrets

* API keys are read only from environment variables (`HERBAGUARD_ANTHROPIC_API_KEY`, `HERBAGUARD_OPENAI_API_KEY`) as `SecretStr`; `.env` is git-ignored; `.env.example` contains no values; tests use fake values.
* Keys appear only in the outgoing HTTP header. Provider errors are normalised without request headers or response bodies; `GET /ai/providers` reports *configured / reachable* only. Tests assert that a configured key never appears in responses or error messages.

## 2. Privacy and logging

* Questions and answers are **not stored** and **not logged**. The `ai_request` log event contains: intent, status, provider, model, mode, durations (total, retrieval, generation), number of citations and sources, token counts, validation issue counts and failed attempts — plus the request id from the existing middleware.
* No new table stores user input. Indexing writes only derived data (segments, embeddings) of stored sources.
* With the default local provider nothing leaves the machine. Cloud providers: see the licensing guard in [llm-providers.md](llm-providers.md) §4; the question itself is sent to the cloud provider when one is selected.

## 3. Prompt injection and untrusted documents

Retrieved text is untrusted data:

1. It is wrapped in `<evidence>` blocks; `<`, `>` and `"` inside it are replaced, so it cannot close the block or forge attributes or new blocks (tested with a hostile abstract).
2. The system prompt states that block content is data and must not be followed.
3. The model has **no tools**: it cannot query the database, call APIs or write anything. Its only output is JSON that is parsed and validated.
4. Code-level validation catches the typical goals of an injection — claiming safety, changing the class, giving directives, citing invented sources — and rejects the answer.

## 4. What validation checks — and what it does not

Checked deterministically (`ai/validation.py`): every citation id exists in the context; paragraphs without valid citations are removed; class letters match the deterministic class; no "safe/harmless/no risk/no danger/there is no interaction" assertions (negated forms allowed; see the attributed-safety exception below); no direct medical instructions; enzymes/transporters and dose-like numbers in a paragraph occur in the items it cites; a PMID, DOI or URL in a paragraph must occur in the context, otherwise the paragraph is removed (`unsupported_reference`); hedged graph statements are not stated without the hedge. Citation URLs and excerpts are always taken from the database. Also checked (2026-11-07): the direction of a claimed effect (increase/decrease, bleeding) must match the cited items (`effect_direction_unsupported`), and strength wording such as "clinically significant" or "well-documented" needs an affirmative cited source (`unsupported_strength_claim`). Rejected and removed text is kept in the internal audit trail (`Issue.text`) but is never returned by the API.

**Corrections after the 2026-11-07 evaluation.** They were re-evaluated on generation the same day (v1 35/35 and v2.1 11/11 questions, no errors). Results and remaining false positives are in [evaluation.md](evaluation.md) section 6.

- *Limitation disclaimers.* A limitation may deny or limit a safety conclusion ("The absence of reported interactions does not mean the combination is safe.", "There is no evidence that the combination is safe.", "It is unclear whether…"). Safety wording in a limitation is checked within its own sentence and clause and accepted only when a denial construction governs it directly. Reassurance ("The combination is safe."), personal reassurance ("You can safely take both.", now matched as safety wording everywhere), absence-of-risk wording and a negation in another clause ("No interactions were reported, so it is safe.") stay critical. The paragraph-level safety check and the attributed-safety exception are unchanged.
- *Clinical-risk claims.* Claims of a higher or lower adverse-event risk (bleeding, thrombosis, toxicity, adverse effects, rejection) need a cited, non-negated statement of the same risk change in the same direction. They are never derived from a mechanism or an exposure change: lower exposure does not imply lower risk. Exposure, pharmacological-effect and risk claims are checked separately.
- *Statements about the herb.* In a herb–drug answer, a sentence about the herb (or with an unspecified subject) is checked only against cited statements about the herb: herb-specific items in full, and from drug labels and the FDA table only the sentences that name the herb. A label's own bleeding warning or its inhibitor sentence cannot support a claim about the herb. Sentences about the drug alone, and answers without a herb–drug pair, use all cited text as before.

**Attributed-safety exception (approved 2026-11-07).** Safety wording stays a critical `safety_claim` by default. It is allowed, and recorded as an `attributed_safety_statement` warning, only when all of the following hold:

- the sentence reports a named source (NCCIH, EMA/HMPC monograph, FDA label, …) with a reporting verb, so it is never HerbaGuard's own assessment;
- a cited direct-evidence statement or excerpt contains a safety sentence with the same certainty ("likely safe" cannot become "safe", and no "completely/proven/…");
- every material qualifier in that source sentence is kept: hedging, uncertainty ("research suggests"), population, duration, route/use and quantity;
- the subject matches what the cited source is about (a swapped herb is rejected as incorrect attribution);
- it is not addressed to a person or phrased as advice, and does not mention a combination, an interaction or the drug being asked about.

Absence-of-risk wording ("no risk", "risk-free", "no safety concerns", "safe to take/use/combine") is always rejected. Whenever attribution or evidence matching cannot be established, the answer is rejected. Cases are covered by `tests/ai/test_attributed_safety.py`.

**Not proven:** that every sentence is a faithful paraphrase of its cited text. A paragraph can cite the right item and still misstate it in ways these rules do not detect (e.g. reversed direction of an effect expressed in other words). This is why answers always come with the verbatim excerpts, why generation is evaluated with a manual review procedure ([evaluation.md](evaluation.md) §3), and why the classification is shown separately from the generated text.

## 5. Limits and reliability

| Limit | Default | Setting |
|---|---|---|
| Question length | 1,000 characters | `ai_question_max_chars` (API schema max 1,000) |
| Context sent to the model | ≈ 2,600 tokens, ≤ 8 evidence items | `ai_context_max_tokens`, `ai_context_max_items` |
| Output | 900 tokens; truncated output is rejected | `llm_max_output_tokens` |
| Provider timeout | 240 s (generation), 120 s (embeddings) | `llm_timeout_seconds`, `embedding_timeout_seconds` |
| Concurrent `/ai/ask` | 2 (HTTP 429 beyond) | `ai_max_concurrent_requests` |
| Brand-name lookups per question | 3 RxNav calls | fixed |

General rate limiting is not part of the existing backend (local deployment, ADR in Phase 1); the concurrency limit protects local inference. A production deployment needs request rate limiting at the gateway.

## 6. Screening before retrieval

Fixed patterns (`ai/guardrails.py`) run before anything else: emergency wording (overdose, poisoning, acute severe symptoms happening now, self-harm) returns a referral message only — no retrieval, no model call (`status = emergency_referral`); individual dosing questions return a decline plus official posology passages quoted verbatim (`declined_dosing`, no model call). Questions *about* evidence ("can ginkgo lower the seizure threshold?", "what doses were used in studies?") are not refused, and a dosing decline needs an amount to be asked about, so "Can I take ginseng with my blood pressure tablets?" is an evidence question; any mention of "overdose" is screened conservatively as an emergency.

## 7. No autonomous actions

The AI layer never writes to scientific tables, never runs SQL from model output, never changes classifications or the knowledge graph, and makes no medical decisions. Personal-advice questions are answered with what the evidence says plus an explicit statement that a doctor or pharmacist must decide (`personal_advice_requested: true`).
