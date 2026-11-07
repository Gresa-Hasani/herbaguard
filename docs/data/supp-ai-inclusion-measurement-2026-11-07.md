# SUPP.AI Context Inclusion Measurement — 2026-11-07

Read-only measurement on the real HerbaGuard database after the conditional single-mention policy
(commit state `58a3981` plus the uncommitted inclusion policy). No source changes, no writes, no
model calls.

## Summary

| Measure | Value |
|---|---|
| Pairs evaluated | **97** |
| Pairs with an eligible SUPP.AI candidate | **97** (100 %) |
| Pairs with a mention included | **0** |
| Mentions included | **0** |
| Inclusion rate | **0.0 %** |
| Excluded: 8-item limit exhausted | **95** (97.9 %) |
| Excluded: token budget exhausted | **2** (2.1 %) |
| Excluded: no eligible mention | **0** |
| Excluded by the global one-mention cap | **0** |

At the default limits (8 items, 2,600 tokens) no SUPP.AI mention reaches a real context for these
pairs. Capacity, not the new one-mention cap, is the binding constraint.

## 1. Scope and method

**Evaluation set.** The same real pairs as the P2 audit. From the database:

* `external_relation` with `source_code = 'supp_ai'`, `predicate = 'interaction_mentioned'`:
  **1,658** stored sentences.
* With paper metadata and not retracted: **1,656**.
* With the supplement resolved to a taxon and the drug resolved to a HerbaGuard drug, and the taxon
  belonging to a curated herbal substance: **350** eligible sentences (matches the audit).
* Distinct (curated herb group, drug) pairs: **97** (matches the audit).

The set was reconstructed before measuring; all 97 pairs resolved through the production
question-understanding path (0 resolution failures), so no substitute evaluation set was used.

**Assembly reproduction.** For each pair, steps 1–4 of `ai.service._ask` were replayed with the
production functions:

1. `ai.query.analyse` on the question `"Does <EMA pharmaceutical name> interact with <drug name>?"`
   (`allow_remote_drug_lookup = False`).
2. `services.interactions.check` → `C#` classification, decisive statements (`S#`, priority 5),
   context statements, mechanism paths (`M#`).
3. `service._experimental_observations` (DDID `X#`) and `service._supplementary_mentions`
   (SUPP.AI, now one candidate per pair).
4. `ai.retrieval.retrieve` with the production pipeline query and **no embedding provider**
   (keyword-only fallback; see limitations), then `context.assemble` with
   `max_items = 8`, `max_tokens = 2,600`, the stored source licence map, and the local-provider
   licence setting (`cloud_only_redistributable = False`).

Each pair was assembled twice from identical deep copies — with the SUPP.AI candidates and without
them — so the effect of adding mentions can be isolated. All database work ran inside a
`default_transaction_read_only=on` connection. No Ollama call, no generation, no ingestion.

**Candidate selection.** After the policy change one candidate is built per pair
(`MAX_MENTIONS_PER_PAIR = 1`), so the 350 eligible sentences yield 97 candidates. The global
`MENTION_LIMIT = 1` applies to a whole assembled context, not per pair.

## 2. Results

### Inclusion and exclusion

| Outcome | Pairs | Share |
|---|---|---|
| Mention included | 0 | 0.0 % |
| Excluded — 8-item limit already full | 95 | 97.9 % |
| Excluded — token budget already full | 2 | 2.1 % |
| Excluded — no eligible mention existed | 0 | 0.0 % |
| Excluded — global one-mention cap | 0 | 0.0 % |

Included pairs: **none**.

### Capacity at the moment SUPP.AI was considered

Capacity was measured on the mention-free assembly under the same limits.

| Remaining capacity | Contexts |
|---|---|
| Free item slot **and** enough tokens for the candidate | **0** |
| Free item slot, **insufficient** tokens | **2** |
| **No** free item slot, enough tokens | **35** |
| **No** free item slot, **insufficient** tokens | **60** |

| Context measure | Value |
|---|---|
| Evidence items in the mention-free context | 8 in 95 contexts, 7 in 2 |
| Tokens used by the mention-free context | 1,624 – 2,599 of 2,600 |
| Tokens left for a candidate | 1 – 976 |
| Candidate mention size | 317 – 469 tokens |
| Contexts over either limit after assembly | 0 |
| Retrieval mode used | keyword in 97/97 |

The two token-limited contexts kept one free item slot but had fewer tokens left than the
candidate requires; the other 95 contexts had no free slot at all. That is why the global cap could
not bind: no context had room for even one mention.

## 3. Evidence-priority verification

For all 97 contexts, the mention-free assembly and the non-mention items of the assembly that
included the candidates were compared on label, kind, text, qualifiers, source code, evidence id,
external id, redistributable flag and priority.

| Check | Result |
|---|---|
| Non-Supp.AI items identical (identity, order, content, labels) | **97 / 97** |
| Evidence count changed by adding candidates | **0 / 97** |
| Context exceeded 8 items or 2,600 tokens | **0 / 97** |
| U# placement after existing evidence | not observable — no U# was included |
| U# label, provenance and safety metadata retained | not observable — no U# was included |

Because nothing was included, the last two checks are vacuous here. They are covered by the
regression tests added with the policy (`test_one_mention_is_included_when_genuine_free_capacity_exists`,
`test_including_a_mention_never_changes_other_evidence`,
`test_every_mention_keeps_its_safety_labels`), not by this measurement.

**Evidence present in the mention-free contexts (all retained):**

| Evidence | Contexts |
|---|---|
| Decisive statements (`S#`, priority 5) | 49 — EMA monograph 34, NCCIH 20, FDA label 25 (a context can have several) |
| Any source statement (`S#`) | 49 |
| DDID records (`X#`) | 39 |
| Mechanism paths (`M#`) | 21 |
| Retrieved excerpts (`E#`) | 94 — PubMed 90, EMA 35, NCCIH 21, FDA label 9 |
| LiverTox hepatotoxicity items (`H#`) | 0 |

No decisive statement, DDID record or excerpt was dropped or replaced by SUPP.AI candidates; the
absence of LiverTox items is a property of the question type (H# items are added only to
liver-injury questions, which these interaction questions are not), not a context-selection loss.
Retrieval absence upstream is unchanged and out of scope; no item present before assembly was
excluded afterwards.

## 4. Multi-pair probe (supplementary)

The 97 pairs include five herbs with more than one drug pair (garlic, green tea, St John's wort,
senna, ginger). For each, one production question naming two drugs was assembled the same way:

| Measure | Value |
|---|---|
| Multi-pair contexts | 5 |
| Candidates (one per pair) | 10 |
| Mentions included | 0 |
| Candidates excluded by the global one-mention cap | **0** |
| Excluded by the 8-item limit | 4 |
| Excluded by the token budget | 1 |
| Non-mention evidence identical | 5 / 5 |

No pair supplied a mention in these contexts, so there is no "selected pair versus unselected
pairs" to report: all ten candidates were excluded by capacity before the one-mention cap could
apply. The probe confirms that the global cap is not what removes mentions in current real
questions.

## 5. Observations

* **The policy is safe but currently provides no real-world SUPP.AI coverage.** With the default
  limits, inclusion is 0/97. The single-mention rule guarantees that a mention can never displace
  stronger evidence; it does not create room for one.
* **The item limit is the dominant constraint.** 95 of 97 mention-free contexts already hold 8
  items. A further 35 contexts have enough tokens for a mention but no free item slot; only 2 are
  token-bound. Raising the token budget alone would not change inclusion.
* **The reconstruction matches the previous audit.** The mention-free assembly ends by token budget
  (7 items) in exactly the two pairs the audit reported as "2 without U#" (its "5 with U#" came
  from the removed reserved mentions). This supports that the same 97 pairs and the same assembly
  behaviour were reproduced.
* **No decisive evidence was displaced**, and the earlier defect (U# items taking slots ahead of
  decisive statements) cannot recur with the deferred pass: every non-mention item is byte-for-byte
  identical with and without SUPP.AI candidates in all 97 contexts.
* At these limits, SUPP.AI remains effectively invisible to real answers. Making it contribute
  would require a deliberate capacity or ranking decision (for example a larger item limit or a
  reserved slot), which would be a policy change and was not made here.

## 6. Limitations

* **Keyword-only retrieval.** No embedding provider was used (no Ollama call was permitted), so the
  hybrid semantic branch was inactive and `retrieval.mode_used` was `keyword` for all 97 pairs.
  Production with stored embeddings could rank different excerpts and therefore change capacity.
  The audit's exact question strings and retrieval configuration were not stored in the repository,
  so exact rank parity with it cannot be claimed; only the pair set, the pipeline functions and the
  token-budget behaviour were reproduced.
* **Question template.** Questions use the EMA pharmaceutical name ("Hyperici herba") to guarantee
  exact, non-fuzzy herb resolution; real users may phrase questions differently, which can change
  keyword retrieval ranks.
* **One candidate per pair.** The 350 eligible sentences were not all assembled; only the
  highest-ranked eligible mention of each pair was a candidate, by design.
* **Assembly only.** This measures context selection, not retrieval quality, answer generation or
  validation. No model was invoked.
* **Snapshot.** The database was read once on 2026-11-07; nothing was written.
* **Licensing.** SUPP.AI remains `to_verify`; no SUPP.AI sentence text is reproduced in this report.

## 7. Verdict

The conditional single-mention policy behaves as specified on real data: 0 of 97 contexts include a
mention because none has genuine free capacity, 95 are stopped by the 8-item limit and 2 by the
token budget, and existing evidence is unchanged in every context. The policy provides no
meaningful real-world SUPP.AI coverage at the current limits. Whether to create capacity for
supplementary evidence is a separate product and safety decision, not part of this measurement.
