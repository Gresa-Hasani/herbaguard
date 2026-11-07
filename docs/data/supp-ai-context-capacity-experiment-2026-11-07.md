# SUPP.AI Context Capacity Experiment — 2026-11-07

Read-only comparison of context assembly at **8, 9 and 10 items**, with the token budget fixed at
**2,600 tokens**. Same 97 real SUPP.AI herb–drug pairs as the inclusion measurement. No production
code or configuration was changed; the limit was passed as a parameter to a scratch measurement
script (removed after the run). Database access was read-only; no model was called.

## Summary

| Measure | 8 items (baseline) | 9 items (A) | 10 items (B) |
|---|---|---|---|
| SUPP.AI mentions included | **0 / 97** | **0 / 97** | **0 / 97** |
| Inclusion rate | 0.0 % | 0.0 % | 0.0 % |
| Candidates excluded by the one-mention cap | 0 | 0 | 0 |
| Contexts using the extra slot(s) | — | **54** | **54** (33 reach 10 items) |
| Contexts held back by the token budget | 2 | 43 | 64 |
| Mean tokens used (of 2,600) | 2,224.0 | 2,364.7 | 2,447.6 |
| Contexts over the token budget | 0 | 0 | 0 |
| Baseline evidence retained (content / order / labels) | — | 97 / 97 / 97 | 97 / 97 / 97 |
| Contexts at the configuration's item maximum | 95 | 54 | 33 |

Neither 9 nor 10 items produces any real SUPP.AI coverage.

## 1. Method

**Evaluation set.** Reconstructed exactly as in the inclusion measurement and the P2 audit:
1,658 stored SUPP.AI sentences → 1,656 with paper metadata and not retracted → **350** eligible with
both entities resolved → **97** distinct curated-herb–drug pairs. All 97 resolved through the
production question-understanding path (0 failures).

**Identical inputs.** For each pair, steps 1–4 of `ai.service._ask` were executed **once**: the
interaction service (classification, decisive and context statements, mechanism paths), DDID
observations, SUPP.AI candidates (one per pair), and production retrieval (keyword fallback, no
embedding provider), producing one item list. That list was deep-copied and assembled three times
with `max_items` 8, 9 and 10, the token budget fixed at 2,600, the stored source licence map, and
the local-provider licence setting. Every configuration therefore saw byte-identical inputs.
No reserved-slot rule or evidence priority was modified.

**Retention checks.** Baseline items were compared with the 9- and 10-item contexts on identity
(kind, text, qualifiers, source, evidence id, external id, priority), order (is the baseline
sequence a subsequence?), and label. "Displaced" means a baseline item absent from the larger
context.

## 2. Results per configuration

### 2.1 Item counts and Supp.AI

| Evidence items in context | 8 items | 9 items | 10 items |
|---|---|---|---|
| 7 | 2 | 2 | 2 |
| 8 | 95 | 41 | 41 |
| 9 | — | 54 | 21 |
| 10 | — | — | 33 |
| **Contexts using the additional slot(s)** | — | **54** | **54** |

All 97 pairs have between **10 and 31 non-mention items** available before assembly
(minimum 10, maximum 31). Because mentions rank last (priority 60, after statements, mechanisms,
excerpts, DDID, facts and context statements), a mention can only enter after **all** stronger items
already fit. At 10 items the pair with the smallest pool still has one stronger item left over. That
is why inclusion stays at **0/97** at both larger limits: the global one-mention cap is never the
reason a mention is absent (0 cap-excluded); capacity always is.

### 2.2 What the extra slots admitted

| Added item kind | 9 items | 10 items |
|---|---|---|
| Retrieved excerpt (`E#`) | 48 | 71 |
| Source statement (`S#`, context statement) | 0 | 1 |
| DDID observation (`X#`) | 2 | 2 |
| Mechanism path (`M#`) | 1 | 1 |
| Catalogue/role fact (`F#`) | 3 | 12 |
| SUPP.AI mention (`U#`) | **0** | **0** |

By source: PubMed +45 (9 items) / +65 (10 items); EMA +4 / +7; DDID +5 / +14; NCCIH 0 / +1.
The extra capacity is absorbed almost entirely by additional PubMed excerpts, then facts and DDID
records — never by SUPP.AI.

### 2.3 Token usage

| Measure | 8 items | 9 items | 10 items |
|---|---|---|---|
| Tokens, minimum | 1,624 | 1,807 | 2,072 |
| Tokens, maximum | 2,599 | 2,600 | 2,600 |
| Tokens, mean | 2,224.0 | 2,364.7 | 2,447.6 |
| Mean change vs baseline | — | +140.6 | +223.6 |
| Contexts stopped by tokens before the item limit | 2 | 43 | 64 |
| Contexts over 2,600 tokens | 0 | 0 | 0 |

The item limits are partly self-cancelling: at 10 items, 64 of 97 contexts cannot reach 10 items
because the token budget runs out first. At 9 items the token ceiling binds in 43 contexts.

### 2.4 Evidence retention and displacement

| Check | 9 items | 10 items |
|---|---|---|
| Baseline items retained by content | **97 / 97** | **97 / 97** |
| Baseline order preserved (subsequence) | **97 / 97** | **97 / 97** |
| Baseline items whose label changed | **0** | **0** |
| Contexts where a baseline item is missing | **0** | **0** |
| Newly admitted items placed before a baseline item | 21 contexts | 27 contexts |

No existing evidence is displaced, reordered relative to itself, or relabelled. In 21 (9 items) and
27 (10 items) contexts a newly admitted excerpt or fact sits before a reserved DDID record in the
final priority order, so the baseline sequence is a subsequence rather than a prefix; this is a
positional effect of the existing reserved-slot pass, not a change to the retained items.

Capacity omissions fall as limits rise: **694 → 640 → 607** whole items left out (the assembler's
own count). These include supplementary mentions, excerpts and other items that still do not fit.

### 2.5 Decisive and source evidence

| Evidence in context | 8 items | 9 items | 10 items |
|---|---|---|---|
| Contexts with decisive statements (priority 5) | 49 | 49 | 49 |
| Decisive statement items | 138 | 138 | **138** |
| — EMA monograph (`ema_hmpc`) contexts | 34 | 34 | 34 |
| — NCCIH contexts | 20 | 20 | 20 |
| — FDA label (`openfda_label`) contexts | 25 | 25 | 25 |
| DDID contexts / items | 39 / 52 | 39 / 54 | 39 / 54 |
| Mechanism contexts / items | 21 / 55 | 21 / 56 | 21 / 56 |
| Excerpt contexts / items | 94 / 505 | 96 / 553 | 97 / 576 |
| — PubMed contexts | 90 | 94 | 95 |
| — EMA excerpt contexts | 35 | 35 | 35 |
| — NCCIH excerpt contexts | 21 | 21 | 21 |
| — FDA label excerpt contexts | 9 | 9 | 9 |
| Source statement items (all types) | 138 | 138 | 139 |
| Fact items | 24 | 27 | 36 |
| LiverTox hepatotoxicity items (`H#`) | 0 | 0 | 0 |

All decisive FDA, EMA and NCCIH statements present at 8 items are still present at 9 and 10; not one
additional decisive statement is admitted (the only new statement at 10 items is a context
statement). LiverTox items are absent by question design: `H#` is added only to liver-injury
questions, and these are interaction questions.

## 3. Retrieval absence versus assembly omission

**Absent before assembly (upstream/retrieval or repository coverage):**

| Evidence not produced for a pair | Pairs |
|---|---|
| No decisive statement at all | 48 |
| No DDID record | 58 |
| No mechanism path | 76 |
| No retrieved excerpt | 0 |

**Not in the assembled context (capacity or de-duplication), produced vs included:**

| Item kind | Produced | 8 items | 9 items | 10 items |
|---|---|---|---|---|
| Decisive statements | 183 | 138 | 138 | 138 |
| DDID records | 65 | 52 | 54 | 54 |
| Mechanism paths | 126 | 55 | 56 | 56 |
| Retrieved excerpts | 969 | 505 | 553 | 576 |

The difference between produced and included mixes capacity omissions with text de-duplication
(identical item text is dropped by design), so it is not a pure capacity count. It shows clearly
that the extra slots recovered **no decisive statements**, 2 DDID records and 1 mechanism path,
while adding 48 / 71 excerpts. The assembler's own capacity-omission count is 694 / 640 / 607.

## 4. Assessment

| Question | Answer |
|---|---|
| Does 9 items provide meaningful SUPP.AI coverage? | **No** — 0/97 mentions included. |
| Does 10 items provide meaningful SUPP.AI coverage? | **No** — 0/97 mentions included. |
| Are there unacceptable evidence trade-offs? | No displacement, no lost decisive evidence, no limit violation. The cost is context growth (+141 / +224 mean tokens) spent on stronger evidence. |
| Is the extra capacity useful at all? | It admits more PubMed excerpts, some DDID records and facts; that may be useful for answer richness, but it does not surface SUPP.AI. |
| Would a larger item limit surface SUPP.AI? | Not at these sizes. Every pair has 10–31 stronger items, so a mention needs at least 11 items (for the single smallest pool) and 12+ for the 31 pairs with an 11-item pool. Because mentions rank last, no modest increase can reach them. |

**Recommendation.** Do not change the production limit on the basis of this experiment: 9 and 10
items deliver **0 %** SUPP.AI inclusion while increasing prompt size. Supp.AI visibility would
require a deliberate policy decision that changes evidence ranking or reserves capacity, which would
trade against stronger evidence and needs explicit approval and safety review. The production
context limit remains **8 items**; this experiment changed nothing.

## 5. Limitations

* **Keyword-only retrieval.** No embedding provider was used (no Ollama call permitted), so the
  hybrid semantic branch was inactive in all three configurations. Production with embeddings could
  rank different excerpts and therefore change which items use the extra capacity.
* **Question template.** Questions use the EMA pharmaceutical name to guarantee exact herb
  resolution; real user phrasing may change keyword retrieval ranks. The previous audit's exact
  question strings were not stored.
* **One candidate per pair.** Only the highest-ranked eligible mention of each pair was a candidate
  (350 eligible sentences → 97 candidates), by design of the current policy.
* **Single snapshot.** The database was read once on 2026-11-07; nothing was written.
* **Assembly only.** No generation, retrieval-quality or validator behaviour was evaluated.
  LiverTox `H#` evidence was not exercised because the questions are not liver questions.
* **Licensing.** SUPP.AI remains `to_verify`; no SUPP.AI sentence text is reproduced here.
