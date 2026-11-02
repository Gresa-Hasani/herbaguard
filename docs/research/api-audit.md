# API Audit

**Project:** HerbaGuard — EthnoHack 2026, Track 04
**Phase:** 0 — Research and Dataset Audit
**Test date:** 2026-11-02, approx. 10:15–10:45 UTC, from a residential connection (Windows 11, `curl` 8.x, Python 3.13)
**Reference test entity:** *Hypericum perforatum* L. (St John's wort) — chosen because it has the most thoroughly documented herb–drug interactions, so every source *should* return data for it.

All results below come from real HTTP requests. Response excerpts are shortened. No request in this audit modified server state.

---

## 1. ETHCSTWIN-hosted APIs

### 1.1 Common characteristics (all seven services)

| Property | Finding | How verified |
|---|---|---|
| Reachability | All seven reachable over **HTTPS on port 65000** | `GET /openapi.json` → HTTP 200 for all |
| TLS | Valid certificate (`ssl_verify_result=0`) | curl without `-k` |
| Server | `nginx/1.29.2` in front of FastAPI apps | Response headers |
| Spec | OpenAPI **3.1.0**, version `0.1.0`, Swagger UI at `/docs` | Spec files downloaded |
| Status | **Organizer-hosted wrappers**, not official institutional APIs. The WFO and ChEBI specs say so explicitly ("This is not an official … API"); the catalogue says the same for all seven. | Spec `info.description`, catalogue |
| Read endpoints | **No authentication** | Successful anonymous GETs |
| Admin endpoints | `POST /import_data/`, `GET /export_ttls/` (`/download_ttls/` on WCVP), `GET /import_neo4j/` (`/import_into_neo4j/` on WCVP) require **HTTP Basic** auth | `security` field per operation in spec; anonymous `GET /export_ttls/` on WFO → **HTTP 401** |
| Rate limits | **None documented**, no `X-RateLimit-*` headers | Headers inspected; 15 sequential requests to TaxTree → 15 × HTTP 200 |
| Latency | 0.4–1.5 s per request | `curl -w %{time_total}` |
| Pagination | `limit` / `offset` query params; responses `{count, offset, limit, results}` on search endpoints | Responses |
| Error format | FastAPI default (`422` with `detail` for validation errors) — inferred from spec | Spec `HTTPValidationError` schema |

**Integration implication.** The RDF/Turtle export and Neo4j import features advertised in the catalogue are **admin-only** — teams cannot trigger them without credentials. HerbaGuard must consume the read endpoints and build its own store.

**Operational risk.** These wrappers are hackathon infrastructure with no SLA. Judges will review the project for a week after the deadline. HerbaGuard must therefore (a) cache/snapshot every response it relies on with retrieval timestamp, and (b) keep official-API fallbacks for P0 needs (WFO official matching REST, EBI ChEBI API).

### 1.2 WFO — `https://wfo.ethcstwin.di.uoa.gr:65000`

| Item | Detail |
|---|---|
| Title | "RESTful API for BioKB-WFO." (not official) |
| Key operations | `GET /name/first_hit/?names=…&only_if_valid=` (best match), `GET /names/find_similar?search_for_name=…` (fuzzy, returns similarity score and algorithm), `GET /names/?…` (field search, 40+ filters), rank browsers `/species/`, `/genus/`, `/family/`, … |
| Test 1 | `GET /name/first_hit/?names=Hypericum perforatum` → **200**, 0.40 s: `wfo_id 728093`, `full_name_plain "Hypericum perforatum L."`, family Hypericaceae, `status valid`, `role accepted`, year 1753, `ipni "433719-1"`, URL `https://www.worldfloraonline.org/taxon/wfo-0000728093` |
| Test 2 | `GET /names/find_similar?search_for_name=Hypericum perforatun` (typo) → **200**, 0.87 s: top hit *H. perforatum*, `calculate_with "metaphone_jaro"`, `similarity 0.98`; second hit *H. perfoliatum* — illustrates why fuzzy hits need a confirmation threshold |
| Test 3 | `GET /names/?full_name_plain=Hypericum perforatum` → `count 0` (field includes author); `full_name_no_authors=Hypericum perforatum` → 1 result ✔ |
| Test 4 | `first_hit` with `Hyperici herba` (EMA pharmaceutical name) → `null`; with `Hypericum perforatumL.` (EMA malformed string) → `null` |
| Note | Numeric `wfo_id` (728093) must be converted to the canonical `wfo-0000728093` form |
| Verdict | **Usable — P0.** Fast and informative. |

### 1.3 IPNI — `https://ipni.ethcstwin.di.uoa.gr:65000`

| Item | Detail |
|---|---|
| Title | "IPNI Data API" |
| Key operations | `/names/search/`, `/name/by_id/`, `/names/find_similar`, `/name_relations/search/`, `/references/search/`, `/type_materials/search/`, `/families/` |
| Test | `GET /names/search/?scientific_name=Hypericum perforatum&limit=2` → **200**, 0.53 s, `count 2`: `433719-1` (status "tax. nov.", page 785, Clusiaceae) and `101692-3` (status "unknown", Clusiaceae). Embedded `reference` object includes BHL page IDs in remarks. |
| Test | `GET /name/by_id/?name_id=433719-1` → **200**, full record |
| Verdict | **Usable — P1.** Nomenclatural detail; not a taxonomic opinion (spec description says so). |

### 1.4 WCVP — `https://wcvp.ethcstwin.di.uoa.gr:65000`

| Item | Detail |
|---|---|
| Title | "RESTful API for WCVP." |
| Key operations | `/plants/` (35 filters incl. `taxon_name`, `ipni_id`, `powo_id`, `tax_id`, `accepted_plant_name_id`), `/plants/with_locations/`, `/locations/…` (WGSRPD levels 1–3), `/locations/code_l3/by_tax_id/`, `/plant_locations_statistics/` |
| Test | `GET /plants/?taxon_name=Hypericum perforatum&limit=2` → **200**, 0.48 s: `plant_name_id 516286`, `taxon_status Accepted`, `geographic_area "Europe to China, NW. Africa"`, lifeform perennial, climate temperate, `accepted_plant_name_id 516286` |
| Verdict | **Usable — P1** (synonym → accepted resolution via `accepted_plant_name_id`; native range). |

### 1.5 NCBI TaxTree — `https://taxtree.ethcstwin.di.uoa.gr:65000`

| Item | Detail |
|---|---|
| Key operations | `/names/search/`, `/names/similar/`, `/names/suggestions/`, `/node/search/` (+ siblings, descendants), `/ranked_lineage/search/`, `POST /ranked_lineage/statistics/` |
| Test | `GET /names/search/?name_txt=Hypericum perforatum&limit=3` → **200**, 0.49 s: `tax_id 65561`, name class "scientific name", rank species |
| Burst test | 15 consecutive requests → all HTTP 200, no throttling |
| Verdict | **Usable — P1** (bridge to PubChem/LOTUS/COCONUT/UniProt). |

### 1.6 COCONUT — `https://coconut.ethcstwin.di.uoa.gr:65000`

| Item | Detail |
|---|---|
| Key operations | `POST /compounds/` (search), `/compound/?identifier=`, `/compound/molfile/{id}`, `/compound/image/{id}/`, `/organisms/` (filters `tax_id`, `wcvp_id`, `powo_id`), suggestion endpoints, chemical-class and NPClassifier lookups, `/compounds/export` (60+ property filters) |
| Test 1 | `GET /organisms/?name=Hypericum perforatum&limit=2` → **200**, 0.62 s: organism `id 477`, `tax_id 65561`, `wcvp_id 516286`, `powo_id "433719-1"`, `compound_identifiers` list of dozens of `CNP…` IDs |
| Test 2 | `GET /compound/name/suggestions?name=hyperforin` → **200**, 1.42 s: `["hyperforin","Hyperforin"]` |
| Verdict | **Usable — P2.** Organism records already carry cross-IDs (tax_id, wcvp_id, powo_id) — helpful for triangulation. |

### 1.7 ChEBI (BioKB-ChEBI) — `https://chebi.ethcstwin.di.uoa.gr:65000`

| Item | Detail |
|---|---|
| Key operations | `/compounds/`, `/chemical_data/`, `/database_accession/`, `/name/`, `/relation/`, `/relation_type/`, `/reference/`, `/structure/` (SMILES, InChI, InChIKey) |
| Test | `GET /compounds/?name=hyperforin&limit=2` → **200**, 0.81 s: `CHEBI:5834`, 3 stars, status CHECKED, definition mentions *Hypericum perforatum*, formula C35H52O4, mass 536.797, KEGG accession C07608 |
| Verdict | **Usable — P1.** Cross-checked identical with the official EBI ChEBI API (§2). |

### 1.8 BRENDA — `https://brenda.ethcstwin.di.uoa.gr:65000`

| Item | Detail |
|---|---|
| Key operations | `/enzyme_classes/`, `/enzymes/by_organism/`, `/organisms/`, `/compounds/` (by name, InChIKey, ChEBI ID), `/references/`, and ~25 per-EC parameter endpoints (`/inhibitors/enzyme/{ec}`, `/km_values/…`, `/ic50_values/…`, `/ki_values/…`, …) |
| Test 1 | `GET /enzyme_classes/1.14.14.1` → **200**: "unspecific monooxygenase" |
| Test 2 | `GET /inhibitors/enzyme/1.14.14.1?limit=3` → **200**: records `{id, comment, ec_number, compound_id}` — e.g. "at high concentrations", "CYP102A7 exhibits 50% of its initial activity in the presence of 26% dimethyl sulfoxide" |
| Limitation | Inhibitor rows need a second call per `compound_id` to get the name; no organism/isoform field on the row; EC 1.14.14.1 lumps all CYPs (bacterial CYP102A7 appears in the first results) |
| Verdict | **Reachable but low clinical value — P2.** In-vitro context only. |

---

## 2. Public scientific APIs

| API | Request (abbreviated) | HTTP | Time | Result summary | Auth |
|---|---|---|---|---|---|
| openFDA drug label | `drug/label.json?search=drug_interactions:"St. John's Wort"` | 200 | 1.4 s | `meta.last_updated 2026-10-30`; disclaimer + licence URL; total hits 2,878 | None |
| openFDA CAERS | `food/event.json?search=products.name_brand:"st. john's wort"` | 200 | 1.3 s | 41 reports; `count=reactions.exact` aggregation works | None |
| PubMed esearch | `"Hypericum"[MeSH] AND "Herb-Drug Interactions"[MeSH]` | 200 | 1.1 s | 148 PMIDs | None (key optional) |
| Europe PMC | `"St John's wort" AND interaction`, `resultType=lite` | 200 | 2.3 s | 1,304 hits; cursor pagination | None |
| ClinicalTrials.gov v2 | `studies?query.intr=Hypericum&fields=…` | 200 | 0.9 s | NCT06367036, COMPLETED, INTERVENTIONAL; `nextPageToken` | None |
| RxNorm | `REST/rxcui.json?name=warfarin` | 200 | 1.6 s | RxCUI 11289 | None |
| RxClass (ATC) | `rxclass/class/byDrugName.json?drugName=warfarin&relaSource=ATC` | 200 | 0.5 s | `B01AA` Vitamin K antagonists | None |
| ChEMBL | `molecule/search.json?q=hyperforin` | 200 | 2.4 s | `CHEMBL1237210` | None |
| PubChem PUG-REST | `compound/name/hyperforin/property/InChIKey,MolecularFormula/JSON` | 200 | 0.7 s | CID 441298, `KGSZHKRKHXOAMG-HQKKAZOISA-N` | None |
| GBIF match | `species/match?name=Hypericum perforatum` | 200 | 0.4 s | usageKey 3189486, EXACT, confidence 99 | None |
| GBIF vernacular | `species/3189486/vernacularNames` | 200 | — | List returned | None |
| Global Names Verifier | `verifications/Hypericum perforatun?data_sources=196` | 200 | 0.8 s | WFO match, `PartialExact` | None |
| ChEBI (official EBI) | `chebi/backend/api/public/es_search/?term=hyperforin` | 200 | 0.5 s | `CHEBI:5834` (index `chebi-prod-compounds-30102026`) | None |
| UniProt | `uniprotkb/search?query=gene:CYP3A4 AND organism_id:9606 AND reviewed:true` | 200 | 1.5 s | `P08684` Cytochrome P450 3A4 | None |
| MeSH lookup | `mesh/lookup/descriptor?label=Hypericum&match=exact` | 200 | 1.1 s | D020902 | None |
| Wikidata SPARQL | crosswalk for `wd:Q158289` | 200 | 0.6 s | WFO, IPNI, GBIF, NCBI, POWO IDs — consistent with all other sources; LOTUS: 239 compounds "found in taxon" | None (User-Agent required by policy) |
| NCBI Books (LiverTox) | `esearch.fcgi?db=books&term=livertox[book] AND st john's wort` | 200 | — | 36 hits | None |
| **Disease Ontology API** | `api.disease-ontology.org/v1/terms/DOID:1596` | **500** | 0.8 s | `"Unexpected server error."` | — |
| Disease Ontology file | `purl.obolibrary.org/obo/doid.obo` (ranged) | 206 | — | File download works | None |
| **WHO ICD-11 API** | `id.who.int/icd/entity` | **401** | 0.4 s | "Authentication failed … bearer token" — requires registration + OAuth2 client credentials | Token |
| Zenodo (EFSA) | `api/records?q="compendium of botanicals"` | 200 | — | Records 996024, 1212388, licence `cc-by-4.0`; files `BOTANIC.xls`, `PlantList.xls`, `ENDPOINTSTUDY.xls` | None |
| Hugging Face datasets | `api/datasets?search=…` | 200 | — | No herb–drug datasets (see `dataset-audit.md` §8) | None |

---

## 3. Web-only sources (page fetch)

| Source | URL | HTTP | Finding |
|---|---|---|---|
| EMA herbal overview | `ema.europa.eu/en/human-regulatory-overview/herbal-medicinal-products` | 200 | Reachable |
| EMA download page | `ema.europa.eu/en/medicines/download-medicine-data` | 200 | Links to `medicines-output-herbal_medicines-report_en.xlsx` |
| EMA herbal inventory xlsx | `…/documents/report/medicines-output-herbal_medicines-report_en.xlsx` | 200 | 101,829 bytes; 251 data rows; generated 02/11/2026 06:05 (**daily regenerated** — snapshot needed for reproducibility). The URL variant with a hyphen (`…herbal-medicines…`) returns **404**. |
| EMA *Hyperici herba* page | `ema.europa.eu/en/medicines/herbal/hyperici-herba-0` | 200 | Links to final monograph Rev. 1, drafts, superseded docs, opinions, comments |
| EMA monograph PDF | `…/final-european-union-herbal-monograph-hypericum-perforatum-l-herba-revision-1_en.pdf` | 200 | 328,884 bytes; `EMA/HMPC/7695/2021`, dated 23 November 2022; `pdftotext -layout` → 727 lines; section **4.5** extracted successfully, two-column (WEU / TU) layout |
| WHO IRIS monographs | `iris.who.int/handle/10665/42052` | 200 | Slow (6.5 s) |
| NCCIH St John's wort | `nccih.nih.gov/health/st-johns-wort` | 200 | Contains explicit interaction warnings |
| FDA CYP/transporter table | `fda.gov/drugs/drug-interactions-labeling/healthcare-professionals-fdas-examples-drugs-interact-cyp-enzymes-and-transporter-systems` | 200 | Tables include St John's wort as a supplement example |
| EFSA compendium page | `efsa.europa.eu/en/data-report/compendium-botanicals` | 200 | No direct file links on page; data on Zenodo |
| **LiverTox** | `ncbi.nlm.nih.gov/books/NBK548022/` | 200 | Body is a **reCAPTCHA browser check** — scripted access blocked; will not be bypassed |
| **Kew POWO API** | `powo.science.kew.org/api/2/search` | **403** | **Cloudflare challenge** — scripted access blocked; will not be bypassed |
| **NAPRALERT** | `napralert.org` | **502** | Unavailable |
| DrugBank | `go.drugbank.com/releases/latest` | 200 | Release 5.1.22 listed; download needs account |
| IMPPAT, KNApSAcK, LOTUS, Dr. Duke's, CompTox, ESCOP, ICPC-3 | various | 200 | Reachable (not further evaluated by API) |
| Devpost | `ethnohack2026.devpost.com` | 200 | Deadline "Nov 8, 2026 @ 11:00am EET" (= 10:00 CET); judging criteria and submission checklist extracted into `ethnohack-requirements.md` |

---

## 4. Integration complexity ranking (for Phase 2 planning)

| Rank | Source | Complexity | Main difficulty |
|---|---|---|---|
| 1 | WFO wrapper / official WFO | Low | ID format conversion; fuzzy-match thresholds |
| 2 | RxNorm / RxClass | Low | Ingredient vs. product term types (TTY) |
| 3 | PubMed | Low | Rate limit; abstract copyright handling |
| 4 | WCVP, TaxTree, IPNI wrappers | Low | Wrapper availability |
| 5 | openFDA labels | Medium | De-duplication; sentence extraction from long sections |
| 6 | openFDA CAERS | Medium | Free-text product names |
| 7 | EFSA (xls) | Medium | Legacy `.xls` format, 2018 data |
| 8 | NCCIH pages | Medium | HTML section parsing, limited count |
| 9 | FDA CYP table | Medium | HTML tables with footnotes; manual verification |
| 10 | **EMA monograph PDFs** | **High** | Two-column layout, per-herb document discovery, version selection; needs human QA |

## 5. Reliability and fallback plan

| Need | Primary | Fallback | Snapshot strategy |
|---|---|---|---|
| Plant ID | WFO wrapper | Official WFO matching REST (tested), GBIF match | Store raw JSON + timestamp per lookup |
| Synonyms / range | WCVP wrapper | GBIF synonyms | Store raw JSON |
| NCBI tax_id | TaxTree wrapper | NCBI E-utilities `db=taxonomy` | Store raw JSON |
| Compound ID | ChEBI wrapper | EBI ChEBI API, PubChem | Store raw JSON |
| Regulatory text | EMA PDFs (downloaded) | — | Keep PDFs locally (git-ignored); commit extracted sections with attribution if EMA terms allow |
| Literature | PubMed | Europe PMC | Store metadata + abstracts locally (git-ignored) |

## 6. Credentials needed (user action, optional)

| Service | Needed for | Required for MVP? |
|---|---|---|
| NCBI API key | Higher E-utilities rate (10 req/s) | No (recommended) |
| openFDA API key | Higher daily limit | No |
| WHO ICD-API client ID/secret | ICD-11 mapping | No (P2) |
| LLM provider API key | AI Evidence Assistant generation | See `technology-evaluation.md` |

No credentials were used or stored during this audit.
