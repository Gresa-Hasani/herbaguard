# Ingestion Results — Phase 2

**Run date:** 2026-11-02, against the live sources, into the development database (clean schema, migrations 0001–0002). All numbers below come from `herbaguard report`, `herbaguard validate` and SQL on that database. The raw snapshots (1,530 source records) are in `data/raw/` (git-ignored).

## 1. Validation (`herbaguard validate`, exit code 0)

| Check | Result |
|---|---|
| Curated herbs resolved | PASS — 16 herbs, 21 taxa, every curated taxon → exactly one accepted WFO record |
| Provenance coverage | PASS — 100 % of taxon (21), herbal_substance (21), evidence_item (1,219), interaction_assertion (545), indication (44), drug (184), drug_class (136) rows |
| Orphan provenance | PASS — 0 |
| Superseded documents used as evidence | PASS — 0 |
| Assertion excerpts verbatim in stored source text | PASS — 545/545 |
| EMA required sections | PASS — 16 monographs × 8 sections complete for every covered use category |
| EMA extraction vs PDFium | PASS — 256 columns verified or consistently empty, 0 mismatches ([details](ema-extraction-validation.md)) |
| Cross-backbone identifiers | WARN — 2 genuine disagreements (below) |

## 2. Volumes

| Table | Rows |
|---|---|
| taxon / herbal_substance | 21 / 21 (16 herbs; liquorice 3 species, hawthorn 4) |
| taxon_name | 862 (666 WCVP synonyms, 148 GBIF English vernacular names, accepted, curated common and pharmaceutical names) |
| drug / drug_class / memberships | 184 / 136 / 252 |
| evidence_item | 1,219 (EMA 214, NCCIH 75, openFDA 270, PubMed 660) |
| chunk | 2,872 (local only; never committed) |
| herbal_substance_evidence | 1,630 |
| indication | 44 (WEU and TU kept separate) |
| interaction_assertion | 545 (527 active, 18 superseded) |
| source_record / provenance / data_quality_issue | 1,530 / 3,120 / 366 (all runs) |

### Active interaction statements by source and type

| Source | interaction | precaution | uncertain | unclassified | Total |
|---|---|---|---|---|---|
| EMA monographs (§4.3–4.5) | 168 | 2 | 0 | 2 | 172 |
| NCCIH fact sheets | 41 | 6 | 1 | 0 | 48 |
| openFDA labels | 269 | 2 | 0 | 36 | 307 |

Counts are per herbal substance (a liquorice statement appears once for each of its three species).

### Per herb (active statements; first substance of multi-species herbs)

| Herb | EMA | NCCIH | FDA labels | Distinct drugs | Distinct ATC classes | Notes |
|---|---|---|---|---|---|---|
| St John's wort | 84 | 24 | 290 | 129 | 12 | EMA dose-dependent TU conditions preserved |
| Ginkgo | 26 | 5 | 6 | 10 | 6 | Includes the EMA "no interaction indicated, but monitoring advised" warfarin precaution |
| Garlic | 12 | 10 | 1 | 4 | 9 | |
| Liquorice | 11 | 1 | 1 | 3 | 5 | ×3 species |
| Senna | 9 | 0 | 0 | 0 | 5 | Class-level statements only (cardiac glycosides, diuretics, …) |
| Cranberry | 5 | 2 | 0 | 2 | 0 | NCCIH warfarin sentence typed `uncertain` ("conflicting evidence") |
| Green tea | 1 | 3 | 0 | 3 | 1 | |
| Echinacea | 0 | 0 | 4 | 2 | 0 | EMA §4.5: "None reported" |
| Saw palmetto | 2 | 0 | 0 | 1 | 0 | |
| Ginseng | 0 | 0 | 2 | 1 | 0 | EMA §4.5: "None reported"; label sentences naming Siberian/American ginseng excluded |
| Milk thistle | 0 | 0 | 1 | 1 | 0 | EMA §4.5: "None reported" |
| Valerian | 0 | 1 | 0 | 0 | 1 | EMA §4.5: "None reported" |
| Black cohosh | 0 | 0 | 0 | 0 | 0 | EMA §4.5: "None reported" |
| Hawthorn | 0 | 0 | 0 | 0 | 0 | EMA §4.5: "None reported" |
| Ginger | 0 | 0 | 0 | 0 | 0 | EMA §4.5: "None known" |
| Turmeric | 0 | 0 | 0 | 0 | 0 | EMA §4.5: "None reported" |

**Zero statements does not mean "safe".** For eight herbs the regulator's monograph states "None reported/known" at its date (stored as such); other sources simply contain no sentence matching the curated lexicon.

### Literature (PubMed)

660 articles (600 with abstracts) linked to all 16 herbs. Evidence types: SR 196, RCT 202, CLIN 22, CASE 18, REV 74, ANIMAL 50, INVITRO 28, OTHER 70. Retrieval: up to 60 herb–drug-interaction and 25 SR/MA/RCT records per herb (relevance order) out of 545 and 2,731 total hits respectively.

### openFDA label coverage

| Herb | Labels fetched | Distinct generics seen | Generics counted by openFDA | Single-ingredient labels with attributable sentences |
|---|---|---|---|---|
| St John's wort | 3,000 (30 pages) | 244 | 245 | 170 |
| Ginseng | 422 | 5 | 4 | 2 |
| Liquorice | 403 | 7 | 6 | 1 |
| Echinacea | 301 | 5 | 4 | 3 |
| Ginkgo | 292 | 5 | 4 | 4 |
| Garlic | 290 | 4 | 3 | 2 |
| Ginger | 49 | 1 | n/a¹ | 0 |
| Green tea | 22 | 1 | n/a¹ | 0 |
| Cranberry | 20 | 1 | n/a¹ | 0 |
| Black cohosh | 16 | 1 | n/a¹ | 0 |
| Milk thistle | 15 | 2 | 1 | 1 |
| Senna, turmeric | 1 each | 1 | — | 0 |
| Hawthorn, saw palmetto, valerian | 0 | 0 | — | 0 |

¹ The matching labels lack harmonised `openfda` fields (typically OTC/supplement-style labels), so openFDA cannot count them. "Generics seen" can exceed the count by one because labels without a generic name are grouped as "(no generic name)".

73 labels were skipped as multi-ingredient (latest runs), including oral-contraceptive packs whose product list includes iron placebo tablets.

## 3. Data-quality findings (genuine, not code defects)

| Finding | Detail |
|---|---|
| WFO duplicate name strings | 8 lookups needed disambiguation; e.g. *Glycyrrhiza uralensis* Fisch. (unplaced) vs *G. uralensis* Fisch. ex DC. (accepted) |
| IPNI disagreement | *Silybum marianum*: WFO IPNI 91418-3 vs WCVP 249211-1 (WFO value kept, warning recorded) |
| GBIF disagreement | *Crataegus laevigata*: GBIF key 8252683 vs Wikidata 3015796 |
| Infraspecific EMA name | EMA "*Cassia angustifolia* Vahl" → *Senna alexandrina* var. *alexandrina* (within the curated species) |
| Unmapped lexicon phrases | "sympathomimetic drugs", "heart medications", "liquorice root" (a herb), "medications which may aggravate electrolyte imbalance" |
| Unknown RxCUIs | 2 label product RxCUIs not known to RxNav |
| No fact sheet | NCCIH has no senna page |

## 4. Manual spot check of label statements (random sample of 12, seed 0.42)

| Outcome | Count | Example |
|---|---|---|
| Correct drug, herb and wording | 10 | maraviroc — "Concomitant use of maraviroc and St. John's wort … is not recommended." |
| **Misattributed — fixed** | 1 | Oral-contraceptive pack attributed to *ferrous fumarate* (first product RxCUI was the iron placebo). Fix: all product RxCUIs must resolve to one ingredient; regression test added; the 5 affected statements are now `superseded`. |
| Correctly typed `unclassified`, but the label drug is not the object of the sentence | 1 | isotretinoin label: "Pregnancies have been reported by users of combined hormonal contraceptives who also used some form of St. John's Wort." **Phase 3 must treat `unclassified` label statements as context, not as interactions.** |

## 5. Timings (latest runs)

taxonomy 25 s · EMA 62 s · NCCIH 24 s · openFDA labels 181 s (16 herbs, 5 pages) + 334 s (St John's wort, 30 pages) · PubMed 34 s.
