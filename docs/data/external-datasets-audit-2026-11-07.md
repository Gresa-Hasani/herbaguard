# Post-ingestion audit: SUPP.AI, LiverTox, NIH DSLD (2026-11-07)

Branch `feat/dataset-expansion`. Read-only audit of the development database (SELECT queries) and the code. No code, data, schema or import was changed. Ingestion design: [external-datasets.md](external-datasets.md).

## 1. Verified vs reported counts

All counts in the database match the import report.

| Item | Reported | In database |
|---|---|---|
| SUPP.AI supplements: resolved / candidate / ambiguous | 11 / 10 / 1 | 11 / 10 / 1 |
| SUPP.AI drugs: resolved / unresolved | 87 / 272 | 87 / 272 |
| SUPP.AI sentences (`interaction_mentioned`) / distinct pairs / retracted | 1,661 / 684 / 2 | 1,661 / 684 / 2 |
| LiverTox chapters (with likelihood / overview) | 1,388 (1,170 / 218) | 1,388 (1,170 / 218) |
| LiverTox agents: resolved / ambiguous / unresolved | 330 / 2 / 1,363 | 330 / 2 / 1,363 |
| LiverTox `described_in` links | 1,450 | 1,450 |
| DSLD products / label statements / Supplement Facts rows kept | 15,621 / 106,063 / — | 15,621 / 106,063 / 353,616 |
| DSLD ingredient names: resolved / ambiguous / candidate | 44 / 5 / 1 | 44 / 5 / 1 |
| DSLD `lists_ingredient` links | 22,792 | 22,792 |
| Source records (SUPP.AI / LiverTox / DSLD) | 5 / 1,391 / 48 | 5 / 1,391 / 48 |

The first LiverTox run (1,341 chapters, 1,410 links) was superseded by the corrected re-run. The same counts were confirmed by a third, idempotent run. All 7 ingestion runs succeeded.

## 2. Provenance and mapping integrity

- **Provenance:**
  - All 19,088 entities and 25,903 relations reference a `source_record` with a SHA-256, raw path and ingestion run (0 missing).
  - All 1,661 SUPP.AI sentences have a PMID, paper metadata and a SUPP.AI `uid`.
  - LiverTox chapters keep their URL, update date and cited PMIDs.
  - DSLD products keep the DSLD ID, label URL and UPC.
- **Mapping integrity:**
  - Every `unresolved` and `ambiguous` entity has no mapping (0 exceptions).
  - Every `resolved` entity has a `mapped_table` and `mapped_id`, and every mapped id exists in `taxon` or `drug`.
- **Minor gaps:**
  - SUPP.AI entities (JSON objects) and DSLD ingredient entities (derived from names) carry no row numbers. Their sentence and composition relations do.
  - As for DDID, the generic `provenance` table is not used: provenance is `source_record` plus row numbers.

## 3. Data-quality issues

| # | Severity | Issue | Impact |
|---|---|---|---|
| Q1 | **High** | **"Blessed Thistle" is resolved to *Silybum marianum* (milk thistle).** Blessed thistle is normally *Cnicus benedictus*. The cause is a GBIF vernacular name in the existing `taxon_name` table, so the existing `/plants/resolve` endpoint makes the same mistake. | 531 DSLD products wrongly linked to milk thistle. (SUPP.AI's own "Centaurea Benedicta" entry is a *candidate*, not resolved.) |
| Q2 | Medium–High | **Generic "Ginseng" is resolved to *Panax ginseng*** through a GBIF-only name. On labels and in papers it can mean American (*P. quinquefolius*) or Siberian ginseng (*Eleutherococcus*). | 338 DSLD products, 367 SUPP.AI sentences, 1 LiverTox agent |
| Q3 | Medium | 20 resolved names rest only on a GBIF vernacular name. Most are correct ("St. John's Wort", "Korean Ginseng", "Black Tea"); "Black Snakeroot" (3 products) is also used for other plants. | GBIF names are documented as "not proof of identity" (sources.md) |
| Q4 | Medium | **Candidates store a `mapped_id`**, as DDID does: 10 SUPP.AI supplements and 1 DSLD ingredient. Any consumer that ignores `mapping_status` would treat them as resolved. The existing AI lookup filters on `resolved`. | Future-code risk |
| Q5 | Medium | **LiverTox scores disagree** between the master list and the chapter for 110 agents. St John's wort is D in the master list and E in its chapter. 10 agents have conflicting duplicate master-list rows (first kept). | Which score to show must be decided before display |
| Q6 | Medium | **SUPP.AI evidence profile:** only 54 sentences (3 %) come from papers flagged clinical; 820 (49 %) are animal studies; 304 (18 %) have no study type; 228 (14 %) contain negation ("no", "did not"); 2 come from retracted papers. | Mentions are weak and mixed evidence |
| Q7 | Medium | **DSLD content:** 7,867 of 15,621 products (50 %) are off market. 17,418 label statements mention drugs or medication, and 402 contain marketing claims ("safe", "clinically shown"). | Label text is promotional or precautionary, not evidence |
| Q8 | Low | **Coverage:** 272 of 359 SUPP.AI drugs and 1,363 of 1,695 LiverTox agents are unresolved, because HerbaGuard's drug index is small; 245 agents have no chapter file; DSLD matches exact names only (e.g. "Turmeric root extract" is not matched). | Incomplete, but not wrong |

## 4. Separation from interaction evidence (confirmed)

- **No rows in the evidence tables.** `interaction_assertion` (through `interaction_assertion_evidence`), `evidence_item`, `chunk`, `retrieval_segment` and `experimental_observation` contain **0 rows** from the three sources.
- **Unchanged data.** The hashes of every id in those tables, and in DDID's tables, are identical before and after the imports.
- **Classification.** The A–E classification reads only `interaction_assertion`. A test confirms identical classes before and after all imports.
- **No endpoint.** No API endpoint exposes the new records.
- **One latent dependency.** The only non-ingestion code that reads `external_entity` is the AI's DDID lookup (`ai/service.py:277`). It filters on `mapping_status = 'resolved'` but **not on source**, and it is safe only because it then requires `experimental_observation` rows, which these sources do not have.
- **What each record is labelled as.**
  - SUPP.AI relations are labelled "automatic (SUPP.AI model); an interaction mention, not a confirmed interaction".
  - LiverTox likelihood scores are stored only as LiverTox fields.
  - DSLD records are products and ingredients with mapping status `not_applicable` for products.

## 5. Licensing

| Source | Status | Basis | Use allowed now |
|---|---|---|---|
| `livertox` | **verified**, redistributable | Downloaded `license.txt`: documents without a licence statement are public domain. 0 of 1,389 chapters has one. Book abstract: "copyright free", acknowledgement requested. Verified from the downloaded files, not re-checked online. | Local and cloud models, with acknowledgement |
| `supp_ai` | **to_verify**, not redistributable | No licence in the downloaded files | Local only; never committed or sent to cloud models |
| `nih_dsld` | **to_verify**, not redistributable | No licence in the download; label text and trademarks belong to manufacturers | Local only; never committed or sent to cloud models |

The database `source` rows, `docs/data/sources.md` and `external-datasets.md` all state the same.

## 6. Risks of misleading AI answers (if used without safeguards)

1. **Letter confusion (LiverTox).** The likelihood scores A–E look like HerbaGuard's interaction classes A–E. "St John's wort: E" could be read as "class E", and the scores disagree between sources (Q5).
2. **Liver to general safety (LiverTox).** "Unlikely cause of liver injury" could be turned into "safe".
3. **Mention to interaction (SUPP.AI).** A model-selected sentence can describe an animal study, an absence of effect, a different ginseng (Q2) or a retracted paper, yet be presented as evidence that an interaction exists.
4. **Labels as evidence (DSLD).** Marketing claims ("clinically shown", "safe"), precautions and per-serving amounts could appear as evidence, as safety claims or as dosing advice. Half the products are off market.
5. **Wrong herb.** Blessed thistle products are presented as milk thistle (Q1).
6. **Licence leakage.** SUPP.AI or DSLD text sent to a cloud provider.

## 7. Recommended retrieval strategy

| Dataset | Strategy | Safeguards |
|---|---|---|
| **LiverTox** (first) | Structured *hepatotoxicity* context items (new label, e.g. `H#`), not general text retrieval. Only for resolved agents, and only when the question is about liver injury or herb safety. | Show the chapter's likelihood statement verbatim with "LiverTox likelihood of liver injury — not an interaction class"; show the master-list score only if it agrees, else both with dates. A validator rule must not treat likelihood letters as class mentions, and must reject "safe" derived from them. Cloud use allowed. |
| **SUPP.AI** (second) | Pair-scoped structured context, like DDID `X#` items: for a *resolved* herb and *resolved* drug, a few sentences with PMID, year and study flags. Preferably use the PMID to cite the PubMed record already stored, if present. | Exclude candidates, ambiguous entities and retracted papers; rank human/clinical first; label each "automatically extracted mention, not a confirmed interaction". A validator rule rejects interaction or strength claims supported only by mentions (as `experimental_as_clinical`). Local models only (licence). |
| **NIH DSLD** (last, possibly never in answers) | No label text in model context. At most deterministic product facts ("N products on the market list this herb; forms …") for explicit product questions, or UI-only display. | Never for interaction, safety or dosing questions; exclude off-market products by default; never amounts or doses (dosing guardrail); local only. |

## 8. Prioritised implementation plan

1. **P0: fix mapping quality before any use.**
   - Add a reviewed override list (e.g. `data/curated/name_overrides.yaml`) used by the bulk matcher, and decide whether `/plants/resolve` should use it too.
   - "Blessed thistle" → not milk thistle. Bare "ginseng" and "black snakeroot" → ambiguous or candidate. Review the other GBIF-only names.
   - Re-run the three imports, which is idempotent.
2. **P0: harden consumers.**
   - Add a shared query helper that returns only `resolved` mappings for an explicit source.
   - Add `source_code = 'ddid'` to the AI's DDID lookup, so new datasets can never enter it by accident.
3. **P0: licences.** Verify the SUPP.AI and DSLD terms manually. Until then, local-only use is enforced by `redistributable = false`.
4. **P1: LiverTox hepatotoxicity context.**
   - Add the `H#` items with the safeguards in §7.
   - Decide the score-display policy for Q5.
   - Add hepatotoxicity evaluation questions, e.g. black cohosh, green tea extract and turmeric liver injury, and "Is St John's wort safe for the liver?".
5. **P2: SUPP.AI mention context.**
   - Add the mention items with the validator rule and filters in §7.
   - Add evaluation questions that check mentions are never stated as confirmed interactions.
6. **P3: DSLD product facts.** Add these only if a product question type is added, and keep label text out of AI context.
7. **P3: recall.** Add reviewed name variants (e.g. "Turmeric root extract", "Ginkgo biloba extract") and extend the drug index, which needs RxNav and a separate decision.
