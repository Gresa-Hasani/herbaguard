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
