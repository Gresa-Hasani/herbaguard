# Data Sources — Phase 2 Integration Notes and Licences

Verification markers as in Phase 0: **✔ tested** (real request on 2026-11-02), **✔ page** (stated on the provider page / in the document), **◐ catalogue** (organizer catalogue), **○ to verify**.

| Source code | Source | Used for | Licence / reuse | Integration status | Known limitations |
|---|---|---|---|---|---|
| `wfo_ethcstwin` | WFO via ETHCSTWIN wrapper | Accepted names, `wfo_id`, family, IPNI | WFO backbone CC0 ◐ | ✔ tested, in production use | Wrapper, no SLA; missing TLS intermediate (handled); duplicate name strings with different authorities (handled) |
| `wfo` | Official WFO matching API | Fallback | CC0 ◐ | ✔ tested (live test) | Missing TLS intermediate (handled) |
| `wcvp_ethcstwin` | WCVP via ETHCSTWIN | `plant_name_id`, POWO ID, native range, synonyms, NCBI tax_id | ○ to verify (Kew WCVP download licence) | ✔ tested | `limit` ≤ 100; IPNI ID may differ from WFO (seen for *Silybum marianum*) |
| `taxtree_ethcstwin` | NCBI Taxonomy via ETHCSTWIN | `ncbi_tax_id` | NCBI public ◐ | ✔ tested | — |
| `gbif` | GBIF Species API | Backbone key, English vernacular names | CC BY 4.0 ○ | ✔ tested | Vernacular names are not proof of identity (catalogue warning) — stored as `common` names with source `gbif` only; GBIF key differs from Wikidata for *Crataegus laevigata* |
| `wikidata` | Wikidata Query Service | Independent crosswalk check, QID | CC0 ◐ | ✔ tested | Requires contact info in User-Agent |
| `ema_hmpc` | EMA herbal inventory + EU herbal monographs | Indications (WEU/TU), contraindications, warnings, interactions, undesirable effects | **✔ page: every monograph PDF states "Reproduction is authorised provided the source is acknowledged."** (status in the source registry kept as `to_verify` until the EMA legal notice is reviewed for database storage) | ✔ tested; 16/16 monographs parsed and cross-validated | Monograph dates range 2013–2026; inventory spreadsheet is regenerated daily (snapshot stored); duplicate inventory rows de-duplicated |
| `nccih` | NCCIH Herbs at a Glance | Plain-language sections; safety statements | U.S. government work ○ (page-level notices to verify) | ✔ tested; 15 fact sheets (no senna page) | Lay terms ("blood thinner", "HIV drugs") mapped conservatively |
| `fda_cyp_table` | FDA: Examples of Drugs that Interact with CYP Enzymes and Transporter Systems (Phase 4) | Drug roles (substrate / inhibitor / inducer, potency) for 7 CYPs and 9 transporters; St John's wort and curcumin effects | U.S. government work ○ (page notice to verify) | ✔ tested (2026-11-02, browser) | Examples, not exhaustive; details in [mechanism-sources.md](mechanism-sources.md) |
| `openfda_label` | openFDA drug labels | Drug-specific label sentences naming a herb | openFDA terms; CC0 ○ | ✔ tested | Capped at 500 most recent labels per herb (no API key); multi-ingredient products skipped; some labels lack harmonised fields |
| `rxnav` | RxNorm / RxClass | Ingredient normalisation, ATC classes | NLM terms; ATC © WHO CC (codes only stored) ◐ | ✔ tested | Some lay/foreign drug names do not resolve (recorded) |
| `pubmed` | PubMed E-utilities | Literature metadata, abstracts (local only), evidence type | Metadata free; abstracts © publishers — **never committed** | ✔ tested | Evidence type from publication types reflects design, not quality; MeSH indexing lag |
| `herbaguard_curated` | `data/curated/*.yaml` | Herb list, lexicon | MIT (project) ✔ | — | Human-curated; every lexicon entry records where its wording was seen |
| `supp_ai` | SUPP.AI (Allen Institute for AI), local download | Supplement–drug interaction *mentions* (sentences selected by a model) for curated herbs | ○ to verify (not stated in the download) — not redistributable | ✔ tested ([external-datasets.md](external-datasets.md)) | Automatically extracted; not confirmed interactions; release dated 2021-10-20 |
| `livertox` | LiverTox (NIDDK/NLM, NCBI Bookshelf NBK547852), local download | Hepatotoxicity: agent master list with LiverTox likelihood scores, chapter text | Copyright free (NIDDK), acknowledgement requested ✔ | ✔ tested ([external-datasets.md](external-datasets.md)) | LiverTox likelihood A–E/X is not HerbaGuard's interaction class |
| `nih_dsld` | NIH Dietary Supplement Label Database, local download | Product labels and ingredient composition of products that list a curated herb | ○ to verify (U.S. government database of manufacturers' label text) — not redistributable | ✔ tested ([external-datasets.md](external-datasets.md)) | Manufacturer statements; exact ingredient names only |

## Corrections to Phase 0 findings

| Phase 0 statement | Phase 2 finding |
|---|---|
| Ginkgo folium: "EMA inventory row shows no current outcome (revision in progress)" | Wrong. The inventory row has outcome "European Union herbal monograph"; the Phase 0 regex parser shifted columns. A final monograph (EMA/HMPC/321097/2012) exists and was ingested. |
| ETHCSTWIN wrappers: "valid certificate" | The certificate is valid, but the servers omit the intermediate certificate; strict TLS clients fail without the shipped intermediate. |
| WFO: name → one record | WFO can hold several records per name string (e.g. *Glycyrrhiza uralensis*); `first_hit` may return a non-accepted one. |
| EMA licence "to verify" | Each monograph PDF carries "Reproduction is authorised provided the source is acknowledged." |

## Deferred to later phases

FDA CYP/transporter table and mechanism edges (`target_modulation`, `drug_target_role`) → **done in Phase 4** ([mechanism-sources.md](mechanism-sources.md)); CAERS, EFSA, ChEBI/PubChem constituents, ClinicalTrials.gov → P1 items for later phases if time allows.
