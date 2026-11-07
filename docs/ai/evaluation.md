# AI Evaluation (Phase 5) — BASELINE

> **This is a baseline on the initial corpus** (2026-11-03: 16 curated herbs; 5,106 segments from EMA monographs, NCCIH fact sheets, openFDA labels, PubMed abstracts and the FDA CYP/transporter table). It does **not** represent final system performance. Retrieval quality must be re-assessed — and the question set extended — after the dataset expansion (IMPPAT, LOTUS, KNApSAcK, COCONUT, ChEBI/PubChem, …). Ranking weights and the embedding model were not tuned to this set beyond the comparison reported here.

## 1. Dataset

`data/evaluation/rag_baseline_v1.yaml` — 30 questions in 13 categories: botanical synonyms, plant safety, EMA monographs, herb–drug interactions, FDA labels, CYP enzymes, transporters, active constituents, NCCIH, PubMed, conflicting evidence, missing evidence (incl. two questions about plants HerbaGuard does not cover).

**Relevance is declared as rules** resolved against the database at run time (`assertion_pair`, `herb_sections`, `herb_source`, `herb_text`, `text`, `external_ids`; see the file header). The relevant set therefore grows when new evidence is linked to the same herbs and drugs, and no metric depends on hard-coded corpus counts. Relevance is binary at evidence-item level.

Limitations of the dataset:

* 30 questions, written by the implementer; no independent annotation and no inter-annotator agreement.
* Text rules (`herb_text`) match words, which favours keyword retrieval; structural rules are used where possible.
* Some relevant sets are very large (e.g. St John's wort + CYP3A4: 141 label passages), so Recall@10 is necessarily low for them; Hit@k and MRR are more informative there.
* Questions are English only.

## 2. Retrieval evaluation

`herbaguard ai evaluate-retrieval [--embedding-model M …] [--output report.json]`

* Runs the **production retrieval query** (`service.pipeline_query`: question understanding, entity scoping, entity-name expansions) in keyword, semantic and hybrid mode, for each embedding model.
* Metrics at evidence-item level over the ranked segments: Recall@k, Precision@k, Hit@k (any relevant item in top k), MRR, duplicate rate (segments of an already-seen evidence item), sources@k (distinct sources), latency (median, p95). Questions marked `expect_no_evidence` are excluded from these metrics.
* Each report records the corpus snapshot and the retrieval/segmentation settings.

Results: [embedding-models.md](embedding-models.md) §3 (model comparison) and §4 below.

## 3. Generation evaluation

`herbaguard ai evaluate-generation [--question ID …] [--output report.json]` sends each question through the full `/ai/ask` pipeline with the configured provider and records deterministic checks:

| Check | Definition |
|---|---|
| Classification matches service | The classes in the response equal those of `POST /interactions/check` for the same pairs |
| Class mentions consistent | Any "class X" in the answer text is one of the deterministic classes |
| Citation validity | Every cited id exists among the response's citations (built from the database) |
| Removed paragraphs | Paragraphs removed by validation (uncited, unsupported enzyme/dose, dropped hedge) — a proxy for unsupported claims |
| Critical issues | `classification_conflict`, `safety_claim`, `medical_directive`, `no_supported_content` → answer rejected |
| Insufficient evidence | For questions about uncovered entities: the response reports insufficient evidence |
| Latency, tokens | From the provider response |

Automated tests (`tests/ai`, `tests/api/test_ai_api.py`) cover the same behaviour with scripted providers and never call a model.

**Manual review procedure (scientific quality).** Automated checks cannot establish faithfulness or correctness. For every evaluated answer a reviewer (ideally a pharmacist or pharmacologist) opens the response JSON and checks, per paragraph: (1) every statement is supported by the cited excerpts; (2) qualifiers, conditions and hedges are kept; (3) traditional use, in-vitro/animal findings and mechanism-only relationships are not presented as clinical efficacy or established interactions; (4) absence of evidence is not presented as safety; (5) conflicting sources are described; (6) no advice, dose or treatment recommendation. Each paragraph is graded *supported / partly supported / unsupported*; results are recorded next to the report. An LLM judge is not used as the measure of correctness.

**Provider comparison.** The same command runs with any configured provider (`HERBAGUARD_LLM_PROVIDER`), so reports for Ollama, Anthropic and OpenAI can be compared on the checks above, latency and tokens. Only Ollama/Qwen3-4B was run in Phase 5 (no cloud keys); no claim is made about other providers.

## 4. Results (2026-11-06, live Qwen3-4B Q4_K_M via Ollama, nomic-embed-text, CPU only)

Reports: `docs/ai/results/{retrieval,generation}_{baseline_v1,expanded_v2}_2026-11-06.json`. v1 and v2 are reported separately and never combined. The 16 non-HerbaGuard containers on the machine were stopped during the runs.

### Retrieval

Baseline v1 (31 scored questions): see [embedding-models.md](embedding-models.md) section 3. Hybrid with nomic-embed-text: Hit@5 0.871, Recall@10 0.635, MRR 0.759, Precision@10 0.300, median 0.36 s. Expanded v2 (**2 scored questions**: only v2-ginseng-warfarin-mixed and v2-sjw-imatinib have relevance rules; most v2 evidence is DDID records, which are structured context and not retrieval segments): hybrid Hit@5 0.50, Recall@10 0.60, MRR 0.31. Two questions cannot support any comparison; the v2 retrieval numbers are not an evaluation result. (Corrected 2026-11-07; an earlier version of this page said 6.) RxNav was reachable during these runs, so no question was externally blocked.

### Generation

| Check | Baseline v1 (35 q.) | Expanded v2 (11 q.) |
|---|---|---|
| Status | 22 answered, 5 insufficient evidence, 7 rejected by validation, 1 ambiguous (409) | 4 answered, 3 insufficient evidence, 1 rejected, 1 ambiguous (409), 1 declined dosing, 1 emergency referral |
| Errors | 0 | 0 |
| Classification identical to the deterministic service | 100 % | 100 % |
| Class mentions consistent with it | 100 % | 100 % |
| Citation validity (every cited id exists, hydrated from the database) | 100 % | 100 % |
| Paragraphs removed per answer (unsupported claims) | 0.09 | 0.13 |
| Regenerations | 8 | 1 |
| Uncovered entities reported as insufficient | 2 / 2 | grapefruit question answered (see below) |
| Median latency / output tokens | 110 s / 349 | 130 s / 401 |

v2 experimental-record checks: in every answer that used DDID records, the non-human status of animal or unstated-species records was stated (6/6 where records were in context); no paragraph had to be removed for presenting animal records as clinical evidence.

### Findings that need decisions

1. **All 8 rejections are `safety_claim` on safety-themed questions.** NCCIH safety sections themselves say "considered safe" (licorice), "generally safe" (valerian), "is safe" (black cohosh); the validator rejects any such wording, also when it is attributed to the source. Conservative by design, but it withholds correct, attributed answers. Possible fix: allow source-attributed safety wording that keeps the source's own qualifier. This needs a review of the scientific rule before changing. **Update 2026-11-07:** the reviewed exception is implemented (see [security.md](security.md) §4). It has not yet been re-evaluated on generation, so the results above still describe the old rule.
2. **DDID records can be crowded out of the context.** Observation items rank after retrieved excerpts; with the 8-item limit, St John's wort + rivaroxaban and ginkgo + midazolam got no DDID record although the import holds 5 and 4. Possible fix: a reserved slot for observation items, or a priority above lower-ranked excerpts.
3. **Model-made mechanism inference.** For grapefruit juice + felodipine (a food, not a HerbaGuard entity) the model combined two FDA-table facts (moderate CYP3A inhibitor; sensitive CYP3A substrate) into a hedged "this interaction may occur". The facts are cited correctly, but the inference is the model's, not a deterministic HerbaGuard result. The v2 expectation ("no evidence") was wrong: the evidence exists.

Automated checks do not establish that every sentence is faithful to its sources; the manual review procedure (section 3) has not been carried out yet.

## 5. Results (2026-11-07, after the validation corrections and the attributed-safety exception)

Same setup as section 4 (Qwen3-4B Q4_K_M via Ollama, nomic-embed-text, CPU only, no fallback provider). Reports: `results/generation_baseline_v1_2026-11-07.json`, `results/generation_expanded_v2_1_2026-11-07.json`, `results/retrieval_expanded_v2_1_2026-11-07.json`. The 2026-11-06 reports are unchanged.

**Run conditions.** The v1 run was interrupted by a laptop sleep (about 8.5 h) during `black-cohosh-liver` and then continued. Its recorded latency (30,435 s) is kept in the raw report but **excluded from the latency statistics below**. Just after the sleep, prompt processing ran at about half speed (about 21 vs 38–51 tokens/s) with little free memory; `sjw-warfarin` and `sjw-cyclosporine` hit the 240 s model timeout. Both are recorded as errors and were not retried. They reflect the environment, not the model, so they are not comparable with section 4.

| Check | v1 (35 q.) | v2.1 (11 q.) |
|---|---|---|
| Status | 20 answered, 5 insufficient evidence, 7 rejected, 1 ambiguous (409), 2 errors (timeout) | 4 answered, 2 insufficient evidence, 2 rejected, 1 ambiguous (409), 1 declined dosing, 1 emergency referral |
| Classification identical to the deterministic service / class mentions consistent | 100 % / 100 % | 100 % / 100 % |
| Citation validity | 100 % | 100 % |
| Paragraphs removed per answer | 0.25 | 0.50 |
| Regenerations | 7 | 2 |
| Median latency (excl. errors, 409 and the sleep-affected question) | 123.5 s (n=31; mean 131.7 s, range 42–324 s) | 131.2 s (n=8) |

`unknown_entity_reported_insufficient` is 0.0 in the v2.1 summary only because v2.1 has no question marked `expected_insufficient`; the metric is not applicable there.

Retrieval v2.1 (3 scored questions, including the corrected grapefruit–felodipine question, which ranks the FDA table first): hybrid Recall@10 0.73, MRR 0.54, Hit@5 0.67. Still too few scored questions for an evaluation result.

### Findings from this run (not yet acted on)

1. **The attributed-safety exception was never applied.** No answer produced an allowed `attributed_safety_statement`. The 7 v1 rejections are all `safety_claim`. Most are correctly rejected: unattributed or generically attributed wording ("A systematic review indicates…", "Government sources indicate…"), certainty changes ("may be safe"), absence-of-risk wording ("no safety concerns"), and in `compare-valerian-sources` NCCIH wording attributed to the EU monograph. `syn-cimicifuga-interactions` was answered on 2026-11-06 and is now rejected.
2. **Validator false positive in limitations.** HerbaGuard's own class D/E wording "The absence of reported interactions does not mean the combination is safe." is rejected as "A limitation claims safety" (v2.1 `v2-milk-thistle-cyclosporine-animal`, `v2-ginkgo-midazolam-dose-context`). Cause: the limitation check applies the negation pattern to the whole sentence, and the pattern cannot match across the final full stop. *Corrected after this run* (see [security.md](security.md) §4).
3. **Reversed effect direction passed validation.** In `v2-sjw-rivaroxaban-unknown-species` the answer says the regulatory document states St John's wort "may increase the risk of bleeding" with rivaroxaban. The label says to avoid combined P-gp and strong CYP3A *inducers*, which lower exposure. The bleeding check accepted it because the cited label mentions bleeding in another context. One other paragraph of the same answer was removed by the direction check. *Corrected after this run:* risk claims now need a direct statement about the herb (see [security.md](security.md) §4).
4. **Removed paragraphs need manual review.** The direction check removed 6 paragraphs and the strength check 2. Several look correct, e.g. the imatinib "clinically significant" claim and an invented "no interactions reported" statement for the unknown plant. Others may be false positives, e.g. negated bleeding wording in `garlic-anticoagulants` and "may slightly reduce the chance of catching a cold" in `pubmed-echinacea-colds`.
5. **DDID usage.** Records were in context and cited in 6 answers (2/2 each): v1 `ginkgo-warfarin` and `brand-coumadin`; v2.1 ginseng–warfarin, ginkgo–cyclosporine, St John's wort–rivaroxaban and green tea–rosuvastatin. There were no `experimental_as_clinical` removals. `v2-sjw-imatinib` had no DDID record in context this time (2 on 2026-11-06); its human data came from a retrieved excerpt. The cause is not yet investigated. The evaluator flag `nonhuman_stated_as_such` is false for the rivaroxaban answer although the answer states the record "does not specify the species, so it is not human clinical evidence". The flag's wording match needs checking.

The two corrections above were made after this run and have unit and regression tests. They have not been re-evaluated on generation, so the numbers in this section describe the validator before the corrections. The manual review procedure (section 3) has still not been carried out.

*See section 6 for the post-fix evaluation results.*

## 6. Results (2026-11-07, after the two validator corrections)

These runs re-evaluate the validator after the two corrections recorded in section 5 (limitation disclaimers; clinical-risk claims), described in [security.md](security.md) §4. Sections 4 and 5 are unchanged and remain the historical record. Reports: `results/generation_baseline_v1_2026-11-07_validator-fix.json` and `results/generation_expanded_v2_1_2026-11-07_validator-fix.json`. No retrieval evaluation was run, because retrieval is unchanged.

### Run details

Same model and configuration as section 5: Qwen3-4B Q4_K_M via Ollama, nomic-embed-text, CPU only, no fallback provider, 240 s model timeout. Unrelated local containers were stopped during the runs, as in section 5, and restored afterwards. Datasets and all earlier reports were unchanged (checked by hash before and after).

| Run | Questions completed | Errors | Timeouts | Started | Finished (report `generated_at`) |
|---|---|---|---|---|---|
| v1 (`rag_baseline_v1.yaml`) | 35 / 35 | 0 | 0 | 2026-11-07 14:01:32 CET | 15:15:45 CET (14:15:45 UTC), about 74 min |
| v2.1 (`rag_expanded_v2_1.yaml`) | 11 / 11 | 0 | 0 | 2026-11-07 15:15:45 CET | 15:32:57 CET (14:32:56 UTC), about 17 min |

### Measured results and comparison

For v2.1 the historical comparison is the **2026-11-06 v2 report** (`generation_expanded_v2_2026-11-06.json`), because no `generation_expanded_v2_1_2026-11-06.json` exists. v2.1 differs from v2 in one question: the corrected grapefruit–felodipine question, which replaces the v2 grapefruit question.

| Check | v1 11-06 | v1 11-07 | **v1 post-fix** | v2 11-06 | v2.1 11-07 | **v2.1 post-fix** |
|---|---|---|---|---|---|---|
| Answered | 22 | 20 | **22** | 4 | 4 | **4** |
| Rejected by validation | 7 | 7 | **7** | 1 | 2 | **0** |
| Insufficient evidence | 5 | 5 | **5** | 3 | 2 | **4** |
| Ambiguous (409) / declined dosing / emergency referral | 1 / – / – | 1 / – / – | **1 / – / –** | 1 / 1 / 1 | 1 / 1 / 1 | **1 / 1 / 1** |
| Errors (timeouts) | 0 | 2 | **0** | 0 | 0 | **0** |
| Regenerations | 8 | 7 | **7** | 1 | 2 | **0** |
| Paragraphs removed per answer | 0.09 | 0.25 | **0.35** | 0.13 | 0.50 | **0.63** |
| Classification identical to the deterministic service / class mentions consistent | 100 % / 100 % | 100 % / 100 % | **100 % / 100 %** | 100 % / 100 % | 100 % / 100 % | **100 % / 100 %** |
| Citation validity | 100 % | 100 % | **100 %** | 100 % | 100 % | **100 %** |
| Median latency | 110.4 s | 123.5 s* | **126.3 s** | 130.0 s | 131.2 s | **132.1 s** |

\* Excluding errors, the 409 and the sleep-affected question (section 5). Post-fix latency, measured over questions that called the model: v1 n=34, mean 130.1 s, range 43–262 s; v2.1 n=8, mean 127.5 s, range 57–159 s.

Post-fix validation issues (counted from the reports):
- **v1:** 11 critical `safety_claim` issues across the 7 rejected questions. Paragraphs removed: 8 `effect_direction_unsupported`, 2 `unsupported_strength_claim`, 2 `unsupported_target`.
- **v2.1:** no critical issues. Paragraphs removed: 3 `effect_direction_unsupported`, 1 `unsupported_strength_claim`, 1 `uncited_paragraph`.

The status changes since 2026-11-07:
- `sjw-warfarin` and `sjw-cyclosporine` (timeouts on 2026-11-07) are now answered.
- `v2-milk-thistle-cyclosporine-animal` and `v2-ginkgo-midazolam-dose-context` (rejected on 2026-11-07) now report insufficient evidence.

All other questions have the same status as on 2026-11-07.

### The two corrected defects in the live runs

1. **Disclaimer false positive: corrected in both affected questions.**
   - `v2-milk-thistle-cyclosporine-animal`: rejected on 2026-11-07 for "The absence of reported interactions does not mean the combination is safe." It now passes as insufficient evidence, with the same disclaimer in the answer. The answer reports the rat data as animal evidence, notes that the warfarin case report is not about cyclosporine, and states that no human trials were found.
   - `v2-ginkgo-midazolam-dose-context`: rejected for the same disclaimer. It now passes as insufficient evidence. It reports one human study (midazolam AUC +25 %, oral clearance −26 %) and one study without effect, and keeps the "does not imply safety" wording. One uncited paragraph was removed.
   - Neither answer turns the absence of evidence into a safety statement.
2. **Unsupported rivaroxaban bleeding paragraph: removed.** In `v2-sjw-rivaroxaban-unknown-species`, "The regulatory document states that St John's wort may increase the risk of bleeding when used with rivaroxaban" passed on 2026-11-07. It is now removed with "Claims a higher risk of bleeding that no cited statement directly supports". So is a second paragraph that inferred a bleeding risk from CYP3A4 induction.

### Qualitative observations (manual reading of the reports; not measured)

- **Constituent-level vs whole-herb attribution (rivaroxaban).** The rivaroxaban answer still says St John's wort "may increase the plasma concentration of rivaroxaban, which could raise the risk of bleeding". It labels this as a database record without stated species. The DDID records for this pair support this only at constituent level, and none of them states a species:
- The rutin record describes a possible rise in the plasma concentration of direct oral anticoagulants (DOACs) and a possible rise in bleeding risk.
- The quercetin record describes only a possible rise in bleeding risk.
- Both records give the constituent's enzyme or transporter inhibition and antiplatelet activity as the mechanism.
- The hyperforin and hypericin records describe lower DOAC plasma concentrations, with enzyme and P-gp induction as the mechanism.

The answer's "conflicting evidence" paragraph reflects both directions. The validator accepted the text because the cited records contain this wording. However, the answer attributes constituent-level records to the whole herb, which no cited record states.
- **`sjw-warfarin`: model-answer error, not a validator result.** The answer states that a human study's DDID label "Negative" indicates "no confirmed clinical interaction". The record's conclusion reports that St John's wort significantly increased the apparent clearance of both warfarin enantiomers and thereby significantly reduced the pharmacological effect of racemic warfarin. The same record reports that INR and platelet aggregation were not affected. The record therefore describes a pharmacokinetic interaction, and calling it "no confirmed clinical interaction" misstates it. The record does not define what DDID's "Negative" label means, so the model's reading of the label is not supported by the record. The validator does not check the meaning of DDID labels, so this error passed. It shows a gap in what validation covers, not a malfunction of the corrected rules.
- **`sjw-cyclosporine`** (now answered) correctly reports the contraindication and that the herb lowers cyclosporine plasma concentrations.

### Remaining validator limitations and false positives (not corrected)

1. **`safety_claim` attribution.** The attributed-safety exception still never applied, and the 7 v1 rejections are unchanged.
   - Most are correct rejections: misattribution in `compare-valerian-sources`, changed certainty in `ginger-pregnancy`, reassurance in `black-cohosh-liver`, a generic attribution with a dropped qualifier in `common-valerian-warnings`, and absence-of-risk wording, rejected by design, in `nccih-green-tea-safety`.
   - Likely false positive: `nccih-licorice-safety`. "NCCIH acknowledges that licorice root is generally considered safe as a food ingredient" keeps the source wording, but "acknowledges" and "highlights" are not recognised attribution verbs.
   - Borderline: `syn-cimicifuga-interactions`, attributed only to "A systematic review".
   - In `ginger-pregnancy`, "has been used safely in research studies" is treated as advice by the existing personal/advice check.
2. **Direction and negation handling in the new risk check.**
   - `syn-hypericum-contraindications`: "to prevent reduced therapeutic activity or adverse effects" is read as a claim of lower adverse-effect risk, because the nearest direction word belongs to a different noun.
   - `garlic-anticoagulants`: "no direct evidence … that increases bleeding risk" is removed because the negation is too far from the verb. "do not directly address bleeding risk" is removed by the bleeding-mention rule, which became stricter now that the evidence is limited to statements about the herb.
   - `hyperforin-constituent`: the vague "increase the risk of interactions" is removed.
   - `senna-digoxin`: a supported effect claim ("increasing their effects") shares a sentence with an unsupported risk wording, and the paragraph is removed. A second removal ("increase the risk of arrhythmias") is a model inference that the sources do not state, so it is correct under the rule.
3. **Exposure/effect check (older rule).** `pubmed-echinacea-colds` still loses "may slightly reduce the chance of catching a cold".
4. **Strength check (older rule).** "rather than a confirmed interaction" is not recognised as a negation, which caused removals in `sjw-warfarin` and `missing-unknown-plant-general`. In the second case the removed paragraph was also invented.

Paragraphs removed per answer rose from 0.25 to 0.35 in v1 and from 0.50 to 0.63 in v2.1. Part of the rise comes from the stricter risk check, including the false positives above.

### Scope of these results

These are automated checks on 46 questions with one local model. They show:
- classification consistency
- citation validity
- that the two corrected defects no longer occur in these runs

They do **not** establish clinical correctness, and they do not prove that every generated claim is supported by its cited evidence. The manual review procedure (section 3) has still not been carried out. Not all validator false positives are fixed.
