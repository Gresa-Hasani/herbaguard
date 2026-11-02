# Captured API responses (test fixtures)

These files are **real responses** from the live services, captured on **2026-11-02** with the
HerbaGuard User-Agent, so connector and pipeline tests run against genuine response structures.
They are not invented data. Changes made before saving:

| File(s) | Source | Change made for the fixture |
|---|---|---|
| `wfo_*` (first_hit and names), `wcvp_*`, `taxtree_*` | ETHCSTWIN wrappers (`*.ethcstwin.di.uoa.gr:65000`) | none |
| `gbif_match_*` | GBIF Species API | none |
| `gbif_vernacular_3189486.json` | GBIF Species API | `results` cut to the first 12 entries |
| `wikidata_*` | Wikidata Query Service (CC0) | none |
| `rxnav_*` (incl. Coumadin brand lookup, captured during Phase 3) | NLM RxNav / RxClass | none |
| `openfda_label_sertraline.json` | openFDA drug label API | one label; only `set_id`, `id`, `version`, `effective_time`, `drug_interactions` and four `openfda` fields kept |
| `pubmed_efetch_2.xml` | NCBI E-utilities efetch | **abstract text replaced** with a placeholder (publisher copyright); all metadata unchanged |
| `nccih_st-johns-wort_main.html` | NCCIH (U.S. government work) | only the page's `<main>` element kept |

Synthetic fixtures (hand-written layouts and spreadsheets) live in the tests themselves and are
labelled as synthetic there.

To refresh: re-run the capture script described in `docs/data/pipeline.md` and review the diff;
upstream format changes should make tests fail before they break ingestion.
