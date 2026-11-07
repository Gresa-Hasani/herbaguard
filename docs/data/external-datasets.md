# External Datasets: SUPP.AI, LiverTox and NIH DSLD

**Status:** Integrated 2026-11-07 on `feat/dataset-expansion`. Code: `backend/src/herbaguard/ingestion/pipelines/{supp_ai,livertox,nih_dsld,external_common}.py`. Tests: `backend/tests/api/test_external_datasets.py`.

The three datasets are stored in the generic tables of migration 0006 (`external_entity`, `external_relation`), the same tables as DDID ([ddid.md](ddid.md)). **No schema change** was needed. Each dataset keeps its own kind of evidence:

| Source | Kind of evidence | What it is | What it is not |
|---|---|---|---|
| `supp_ai` | Supplement–drug interaction **mentions** | Sentences that a machine-learning model selected from papers as describing an interaction | Not confirmed interactions; not an HerbaGuard interaction class |
| `livertox` | **Hepatotoxicity** | LiverTox master list (agents, LiverTox likelihood scores) and chapters (hepatotoxicity text) | Not interaction evidence |
| `nih_dsld` | **Product labels and composition** | Manufacturers' label data for products that list a curated herb | Not evidence of an interaction or of safety |

## 1. Rules shared by all three

- **Raw files.** The local downloads in `data/raw/<source>/` are never modified, copied or committed (`data/raw/*` is git-ignored). Each file read gets a `source_record` with its SHA-256, path and modification time. Nothing is downloaded.
- **Verbatim values.** All original values are kept: in `attributes` (rows, JSON objects, chapter fields) and `identifiers` (UMLS CUI, DSLD ID, UPC, LiverTox chapter id, PMIDs).
- **No duplicates, repeatable runs.**
  - Entities and relations have deterministic ids and are upserted, so re-running an import changes nothing (verified on the real data: same counts, all files "unchanged").
  - Exact duplicate rows collapse into one record that lists every source row.
  - After an error-free run, rows of this source that the current files no longer produce are removed. Other sources are never touched.
- **Name mapping reuses HerbaGuard's exact lookup.** The rule is the same as `repositories.plants.match_names(exact_only=True)`: `normalize_for_lookup` against `taxon_name`. Drugs use the exact name or a dataset-listed synonym against `drug.name` (no RxNav lookup). There is no partial or fuzzy matching.
  - **`resolved`:** exactly one taxon or drug matches the dataset's own name (accepted, pharmaceutical or common name).
  - **`candidate`:** the only match is a synonym, or a name variant listed by the dataset (e.g. a UMLS synonym). These need review before use.
  - **`ambiguous`:** the name matches several taxa (e.g. "Hawthorn" → 4 *Crataegus* species; "Licorice" → 3 *Glycyrrhiza* species). Not mapped; the note lists the taxa.
  - **`unresolved`:** no exact match. Kept, never guessed.
- **Separation from the A–E classification.** Nothing is written to `interaction_assertion`, `evidence_item` or `chunk`, so the deterministic A–E classes, the retrieval index and AI answers are unchanged. A test checks that evidence items, assertions, DDID rows and classifications are identical before and after all three imports. The same was verified on the development database.

## 2. SUPP.AI

**Input:** `meta.json`, `cui_metadata.json`, `interaction_id_dict.json`, `sentence_dict.json` (158 MB) and `paper_metadata.json` (86 MB). Release date 2021-10-20. The two large files are streamed: only the needed pairs and papers are decoded. If the file layout differs from the release format, the import stops instead of reading it partially.

**Scope:** supplements whose name matches a curated herb, with every drug they are paired with.

**Stored:**
- **Entities:** `supplement` and `drug`, keyed by UMLS CUI, with the definition, preferred name and synonyms.
- **Relations:** one `interaction_mentioned` relation per evidence sentence (supplement → drug), holding:
  - the sentence, argument spans, `uid`, `sentence_id` and pair id
  - the paper's PMID, DOI, title, year and venue
  - the study flags (`clinical_study`, `human_study`, `animal_study`) and the retraction flag

| Count (real data) | Value |
|---|---|
| Supplements in the release | 2,044 |
| Imported (matching a curated herb): resolved / candidate / ambiguous | 10 / 9 / 2 |
| Skipped (no curated herb) | 2,023 |
| Herb–drug pairs kept / supplement–supplement pairs skipped / rejected (unknown CUI) | 681 / 350 / 0 |
| Evidence sentences stored | 1,658 (2 from retracted papers, flagged) |
| Drugs: resolved to a HerbaGuard drug / unresolved | 87 / 272 |

The 9 candidates match only through a UMLS synonym, e.g. "Green Tea Extract" and "Echinacea". They are listed as `supp_ai_mapping_needs_review` issues. "Ginseng" (C1119918, defined by UMLS as American ginseng) is ambiguous. "Centaurea Benedicta" (blessed thistle) is no longer matched (§5).

### Use in AI answers (P2, 2026-11-07)

`ai/service._supplementary_mentions` adds SUPP.AI mentions to herb–drug questions as `U#` items (kind `mention`, role `supplementary_mention`). `S#` is already used for source statements, so SUPP.AI uses `U`.

- **Eligibility:**
  - The supplement must map to the herb's species and the SUPP.AI drug to the HerbaGuard drug, both `resolved` (`repositories.external.resolved_entity_ids("supp_ai", …)`). Candidate, ambiguous and unresolved entities are never used.
  - Mentions from retracted papers are excluded. So are mentions whose paper metadata is missing, because their retraction status is unknown.
- **Per pair:** up to 3 mentions; the first also states the count by study type and how many were excluded. Order: clinical, human, animal-and-human, in vitro, animal wording, conflicting flags, not stated, animal; newest first within each. **No reserved context slot** (audit fix 2026-11-07): mentions rank after all other evidence (priority 60+), so they only fill slots and tokens that nothing stronger uses and can never displace a statement, mechanism path, DDID record, LiverTox item, excerpt or fact.
- **Each item holds:**
  - the sentence verbatim and the terms SUPP.AI tagged
  - the paper's title, venue, year, PMID and DOI; the four flags (`clinical_study`, `human_study`, `animal_study`, `retraction`)
  - HerbaGuard's negation flag and the release date
  - citation URL: the PubMed record; provenance: the `sentence_dict.json` source record (hash, retrieval time), interaction id, sentence uid and line numbers
- **Study type** (`ai/mentions.study_type`) comes from the paper-level flags, then deterministic downgrades:
  - *clinical* needs both `clinical_study` and `human_study`; `clinical_study` without `human_study` is *conflicting* (e.g. the dog study PMID 22091645)
  - human, clinical, animal-and-human or unflagged papers whose title or sentence names cells, hepatocytes, microsomes, HepG2 or similar become *in vitro*; human, clinical or unflagged papers naming animals become *animal wording*
  - only *clinical* and *human* may be presented as human evidence; all other types are labelled NOT patient or clinical evidence, and for *in vitro*, *animal wording* and *conflicting* the raw flags are not shown
- **Negation** (`ai/mentions.pair_negation`): SUPP.AI has no negation field (`confidence` is always null). The sentence is split into clauses (`;`, "but", "whereas", "however", …). A negation counts for the pair only if its clause names both the herb and the drug, or continues the herb's clause without a new subject ("…, but did not alter X"). "X alone …", "not only", "has not been studied" and "should not be extrapolated" are not negations of the pair. Warnings ("not recommended", "should not be used", "cannot be given safely") get a separate label: neither a confirmed interaction nor evidence of no interaction. Negation about other substances is labelled as such.
- **Labels on every item:** machine-extracted supplementary interaction mention; NOT a confirmed interaction and NOT a HerbaGuard classification; a mention alone never establishes an interaction; licence not verified, never sent to cloud models.
- **No eligible mention:** if both entities are mapped but nothing is eligible, a fact says so (with the exclusions) and that this does not show that no interaction exists. If the herb or drug is not mapped, nothing is added.
- **Validation** (`validation.mention_issue`):
  - SUPP.AI-only paragraphs (U# items and SUPP.AI facts): concluding "no interaction" in any wording ("found no interaction", "does not interact", "unlikely to interact", "safely combined", …) is critical (`supp_ai_absence_as_no_interaction`), unless it is a negated conclusion ("does not show that no interaction exists")
  - mention-only paragraphs: confirming wording ("confirmed", "established", "interacts with", "clinically significant", …) is critical (`supp_ai_mention_as_confirmed`) unless attributed or hedged; a positive effect from mentions negated for this pair, without the negation, removes the paragraph (`negated_mention_as_positive`)
  - any paragraph citing a non-human mention (animal, in vitro, animal wording, conflicting, not stated), even together with a label statement: a patient or clinical claim ("clinical study", "clinical trial", "in patients", "human data", …) without saying the mention is not human evidence removes the paragraph (`mention_nonhuman_as_clinical`)
- **Separate:** mentions never reach `interaction_assertion`, the A–E classification, DDID `X#` items or LiverTox `H#` items.

## 3. LiverTox

**Input:** 1,389 NXML chapter files (BITS XML), `masterlist02-26.xlsx` and `license.txt`. PDFs (1,419), images (626) and DOCX files (2) duplicate or illustrate the NXML content and are skipped.

**Licence:** "copyright free" (NIDDK), with acknowledgement requested. The terms of use treat documents without a licence statement as public domain, and none of the chapters has one.

**Stored:**
- **`livertox_agent`:** one entity per master-list agent, with every column verbatim. HDS agents (herbal and dietary supplements) are mapped to a taxon; others to a drug.
- **`livertox_chapter`:** one entity per chapter, holding:
  - the id, title, URL and update date
  - every "Likelihood score: …" statement as written
  - the verbatim Hepatotoxicity, Mechanism of Injury and Outcome and Management sections
  - the cited PMIDs
- **`described_in`:** a relation from an agent to its chapter.

**The LiverTox likelihood score (A–E, X, [HD])** grades how likely an agent is to cause clinically apparent liver injury. It is a different scale from HerbaGuard's A–E **interaction classes** and is never mapped to them. When the master list and the chapter disagree (110 agents, e.g. St John's wort: master list D, chapter E), both are kept and the difference is reported as `livertox_score_differs`. They are never reconciled.

| Count (real data) | Value |
|---|---|
| Chapters stored (with a likelihood score / overview chapters) | 1,388 (1,170 / 218) |
| Chapter files rejected | 1 (`TOC.nxml`, the table of contents) |
| Master-list agent rows / stored agents / duplicate rows / non-agent rows skipped | 1,705 / 1,695 / 10 / 22 |
| Agents resolved / ambiguous / unresolved | 329 / 3 / 1,363 |
| Curated herbs resolved | 11: black cohosh, cranberry, ginger, ginkgo ("Gingko"), green tea, milk thistle, saw palmetto, senna, St John's wort, turmeric, valerian. Hawthorn, licorice and ginseng are ambiguous. |
| HDS agents that are not curated herbs | 142 (unresolved) |
| Agents linked to a chapter / without a chapter file | 1,450 / 245 |

Most unresolved agents are drugs that are not in HerbaGuard's drug index, which holds only drugs seen in Phase 2–4 sources.

### Use in AI answers (P1, 2026-11-07)

LiverTox is the only one of the three datasets used by the AI layer. `ai/service._hepatotoxicity_items` adds it to the context as `H#` items (role `hepatotoxicity_evidence`, citation kind `hepatotoxicity`):

- **Only for liver questions.** The question must mention the liver (liver, hepat…, jaundice, cholesta…, cirrho…, DILI, transaminases, LiverTox). Other questions get no LiverTox context.
- **Only resolved mappings.** Agents are found with `repositories.external.resolved_entity_ids("livertox", "taxon", …)`. Candidate, ambiguous and unresolved agents are never used. An ambiguous herb name in the question still returns HTTP 409.
- **Per agent (at most 2 per herb):**
  - one item with the master-list likelihood score, its update date and the LiverTox classification, plus the chapter's "Likelihood score: …" statements as written. If the scores differ, the item says so and shows both; HerbaGuard does not choose.
  - one item with the opening of the chapter's Hepatotoxicity section, verbatim, in whole sentences (up to 900 characters; the location says when it continues).
- **Labels on every item:** LiverTox hepatotoxicity evidence, about liver injury only; the likelihood score is not a HerbaGuard interaction class; "unlikely" and "no record" do not mean safe; the plant part or preparation may differ.
- **Provenance:** the master-list and chapter `source_record`s (URL, retrieval time, file hash, row numbers or chapter file).
- **No mapped agent:** a fact item states that HerbaGuard has no LiverTox record mapped by a confirmed name match and that this does not show the herb is safe for the liver.
- **Validation:** answers that call a LiverTox score a class (`livertox_score_as_class`) or claim liver safety (`hepatotoxicity_overstated`) are rejected, unless the wording is quoted verbatim from the cited text.
- **Separate from classification:** `H#` items never feed the A–E classification, DDID records or interaction assertions.

Question set: `data/evaluation/rag_livertox_v1.yaml` (17 questions, checked on the context; no generation run yet).

## 4. NIH DSLD

**Input:** the 8-part CSV download (version 9.4.0, January 2026; 214,780 labels): `ProductOverview`, `DietarySupplementFacts`, `LabelStatements`, `OtherIngredients`, `CompanyInformation` and `ReadMe`. Company contact data is not needed and is skipped.

**Scope:** labels that list at least one ingredient whose name exactly matches a curated herb name.

**Stored:**
- **`dsld_product`:** one entity per label (DSLD ID), holding the overview row, the full Supplement Facts composition (every row), the other ingredients and every label statement, all verbatim.
- **`dsld_ingredient`:** one entity per matched ingredient name, mapped to a taxon.
- **`lists_ingredient`:** a relation from a product to its matched herb ingredient, holding the Supplement Facts row (amount, unit, category).

| Count (real data) | Value |
|---|---|
| Supplement Facts rows read | 2,020,130 |
| Labels imported / skipped (no curated herb) | 15,506 / 199,274 |
| Ingredient links stored / exact duplicate rows collapsed | 22,261 / 243 |
| Matched ingredient names: resolved / ambiguous / candidate | 41 / 7 / 1 |
| Label statements stored | 106,063 |
| Distinct ingredient names not matching a curated herb | 70,578 (not imported) |

## 5. Reviewed name overrides (2026-11-07 audit, P0.1)

Some GBIF vernacular names in `taxon_name` are wrong for the plant, or are shared by several plants. `backend/src/herbaguard/domain/name_overrides.py` holds reviewed overrides, each with its evidence. They are applied at lookup time by `match_names`, `resolve_herb` (`/plants/resolve`, interaction and mechanism checks, AI question analysis) and the bulk dataset matcher. The stored name rows are kept.

| Name | Override | Evidence (summary) |
|---|---|---|
| blessed thistle | never *Silybum marianum*; unresolved (refers to *Centaurea benedicta*, not in HerbaGuard) | POWO/IPNI: *Cnicus benedictus* L. = *Centaurea benedicta* (L.) L.; UMLS C1015220 |
| holy thistle | ambiguous (*Silybum marianum*, *Centaurea benedicta*) | UMLS C1015220 vs GBIF row on *S. marianum* |
| ginseng | ambiguous (*Panax ginseng*, *P. quinquefolius*, *Eleutherococcus senticosus*) | UMLS C1119918 defined as American ginseng; DSLD lists American and Siberian ginseng separately |
| black snakeroot | ambiguous (*Actaea racemosa*, *Asarum canadense*) | UMLS C0771967 and C0330224 |
| Neapolitan medlar | ambiguous (*Crataegus azarolus*, *C. monogyna*) | UMLS C1651460 vs GBIF row on *C. monogyna* |

**Effect on the imports:**
- 4 mappings changed from resolved to ambiguous: "Ginseng" in all three datasets, and DSLD "Black Snakeroot".
- 2 entities became unresolved and left the scope: DSLD "Blessed Thistle" and SUPP.AI "Centaurea Benedicta".
- 115 DSLD labels whose only curated herb was blessed thistle were removed, with 531 DSLD and 3 SUPP.AI relations.

**Effect on the API:** `/plants/resolve` and the interaction check now treat bare "ginseng" as ambiguous (HTTP 409 with candidates), as the test seed already required. Specific names ("Panax ginseng", "Asian ginseng", "Ginseng radix") still resolve. Evidence, assertions, DDID data and all 2,336 checked A–E pairs are unchanged.

**Licence investigation (P0.3, 2026-11-07):**
- **SUPP.AI.** supp.ai says the dataset is "public and available for download", but the site is "© AI2 All Rights Reserved", and AI2's Terms of Use forbid redistribution without written permission. No dataset licence was found, so the status stays `to_verify` and not redistributable.
- **NIH DSLD.** The download states no licence, and dsld.od.nih.gov and ods.od.nih.gov refused automated requests (HTTP 403), so no terms were confirmed. The status stays `to_verify` and not redistributable.

## 6. Commands

```bash
cd backend
herbaguard ingest supp-ai      # ~6 s
herbaguard ingest livertox     # ~45 s
herbaguard ingest nih-dsld     # ~60 s
```

Each command takes `--directory` (default `<raw data dir>/<source>`). Run them after `ingest taxonomy` and `ingest labels`/RxNav, so that herb names and drugs exist for mapping.

## 7. Limitations

- **Exact names only.**
  - Common label variants are not matched, e.g. "Turmeric root extract" (917 rows), "Ginkgo biloba extract" (627) and "Echinacea angustifolia" (529).
  - Curated herbs whose HerbaGuard names lack the dataset's wording stay unresolved or candidate, e.g. SUPP.AI's "Ginkgo Biloba Whole".
  - Extending recall needs reviewed name lists, not fuzzy matching.
- **Ambiguous names are not mapped.** Hawthorn and licorice labels and agents are stored but not linked to a species.
- **Drugs map only within HerbaGuard's existing drug index.** 272 of 359 SUPP.AI drugs and most LiverTox agents are unresolved, and no RxNav lookups are made.
- **SUPP.AI** sentences are model-selected mentions from a 2021 release, so a mention can describe absence of an effect, an animal study or a retracted paper. The study and retraction flags are stored, not interpreted.
- **NIH DSLD is not used by the API, retrieval or AI.** It is stored and mapped only. LiverTox (§3) and SUPP.AI (§2) are used in AI answers, but no endpoint exposes them directly and they are not part of retrieval segments.
- **SUPP.AI in AI answers:**
  - Only 10 curated herbs are resolved in SUPP.AI and 87 of 359 drugs, so most pairs get no mention. Candidates such as "Green Tea Extract", "Turmeric Extract" and "Ginkgo Biloba Whole" are not used until reviewed, so ginkgo + warfarin gets no mention.
  - Many sentences are from reviews and name a herb in a list of several (e.g. "herbs that showed the greatest potential to interact with warfarin include …"). They are mentions, not findings about this pair.
  - Study flags are paper-level, not sentence-level, and some are wrong (the dog study flagged clinical).
  - Negation scope is clause-based. Sentences without a clause marker, or with the herb named only by a pronoun, can still be misread; a reworded patient claim can pass the clinical-claim check.
  - With the 8-item limit, real herb–drug questions rarely leave free room: in the 97 real pairs with eligible mentions, none reached the context after the slot fix (2026-11-07).
  - The validator's checks are wording patterns; a reworded overstatement can pass, and "may interact" is accepted.
  - The SUPP.AI licence is `to_verify`: items are sent only to local models. With a cloud provider they are removed by the licensing guard.
- **LiverTox in AI answers:**
  - Liver questions are recognised by keywords only, so a question such as "is it toxic?" without a liver word gets no LiverTox context.
  - Mapping is per species. LiverTox describes a product or preparation (e.g. green tea *extract*), which may differ from the HerbaGuard herbal substance.
  - Hawthorn, licorice and ginseng agents are ambiguous, so their LiverTox chapters are never shown; the answer gets the no-record fact instead.
  - The opening passage can end with LiverTox's "Other Names … Drug Class …" lines, because they are part of the stored section text.
  - The validator's checks are wording patterns; a reworded overstatement can pass.
- **Licences:** SUPP.AI and NIH DSLD are `to_verify` and not redistributable. Their content must not be committed or sent to cloud models.
