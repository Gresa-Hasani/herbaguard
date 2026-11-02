# Dataset and Resource Audit

**Project:** HerbaGuard — EthnoHack 2026, Track 04
**Phase:** 0 — Research and Dataset Audit
**Audit date:** 2026-11-02

This document evaluates every resource in the official catalogue (`datasets_all_tracks.docx`) and on the Track 04 slide that is potentially relevant to Digital Health & Phytotherapy, plus a small number of additional resources discovered during the audit. Resources that serve only other tracks (historical text corpora, manuscript images, conservation APIs) are listed briefly in §9 with the reason for exclusion.

API-level test results (requests, response shapes, latencies) are in `api-audit.md`. This document focuses on suitability, licensing and prioritisation.

---

## 0. How to read this audit

### Verification markers

Licensing and access statements carry one of these markers:

| Marker | Meaning |
|---|---|
| **✔ tested** | We made a real request on 2026-11-02 and inspected the response. |
| **✔ page** | We fetched the provider's page and confirmed the statement there. |
| **◐ catalogue** | Taken from the organizer catalogue; not independently re-verified yet. |
| **○ to verify** | Our working understanding; must be confirmed before redistribution or local storage. |

### Priority classes

| Class | Meaning |
|---|---|
| **P0 — Essential** | Required for the core MVP. |
| **P1 — High value** | Clearly improves scientific quality or functionality; include if time allows. |
| **P2 — Optional** | Useful, not necessary for the MVP. |
| **P3 — Deferred / Excluded** | Too complex, inaccessible, unsuitable, redundant, or not reliable enough. |

### Selection principle

HerbaGuard's central question is: *"I take drug X — what is known about combining it with herb Y, how sure is that knowledge, and where does it come from?"* A resource is prioritised by how directly it contributes **traceable, citable evidence** to that question, weighted by access, licence, and integration cost within a 6-day build window.

---

## 1. Summary — recommended source portfolio

| Priority | Resource | Role in HerbaGuard |
|---|---|---|
| P0 | **WFO** (via ETHCSTWIN wrapper + official WFO matching API as fallback) | Primary plant identifier (`wfo_id`), accepted name / synonym resolution |
| P0 | **EMA HMPC herbal inventory + EU herbal monographs** | Authoritative regulatory evidence: indications (WEU vs. traditional use), contraindications (4.3), warnings (4.4), **interactions (4.5)**, undesirable effects (4.8) |
| P0 | **openFDA drug labels (SPL)** | Drug-side regulatory statements naming herbs in interaction sections |
| P0 | **RxNorm / RxClass (RxNav APIs)** | Drug name normalization (RxCUI) and ATC class |
| P0 | **PubMed E-utilities** | Literature retrieval with MeSH (`Herb-Drug Interactions`, publication types) for the evidence explorer and RAG |
| P0 | **NCCIH Herbs at a Glance** | Plain-language, public-domain safety summaries; model for patient-facing text |
| P1 | **WCVP** (ETHCSTWIN) | Synonym cross-check, native distribution, `plant_name_id`, POWO/IPNI link |
| P1 | **IPNI** (ETHCSTWIN) | Nomenclatural verification; IPNI ID crosswalk |
| P1 | **NCBI Taxonomy / TaxTree** (ETHCSTWIN) | `tax_id` bridge to PubChem, LOTUS, COCONUT, UniProt |
| P1 | **GBIF Species API** | Independent backbone check, vernacular names (with caveats) |
| P1 | **Wikidata** | Identifier crosswalk (WFO ↔ IPNI ↔ GBIF ↔ NCBI ↔ POWO); LOTUS plant→compound edges |
| P1 | **openFDA CAERS** | Adverse-event *signal exploration* for supplements; never presented as causal |
| P1 | **FDA Table of CYP/transporter substrates, inhibitors, inducers** | Mechanistic basis for "potential interaction" reasoning (drug substrate ↔ herb inducer/inhibitor) |
| P1 | **Europe PMC** | Open-access full text and license metadata for RAG beyond abstracts |
| P1 | **ClinicalTrials.gov API v2** | Registered trials for a herb (and herb + drug) |
| P1 | **ChEBI** (ETHCSTWIN + official) | Normalization of key constituents (e.g., hyperforin `CHEBI:5834`) |
| P1 | **PubChem PUG-REST** | CID / InChIKey normalization of constituents; cross-reference hub |
| P1 | **EFSA Compendium of Botanicals** | Flags for substances of possible concern (CC BY 4.0) |
| P1 | **MeSH** | Indication / pharmacological-action normalization; links to PubMed |
| P2 | COCONUT (ETHCSTWIN), LOTUS | Plant → compound lists for the knowledge view |
| P2 | ChEMBL, UniProt | Compound → target bioactivity; CYP/P-gp protein identity |
| P2 | WHO monographs | Global-scope monograph text (PDF; licence per volume) |
| P2 | Disease Ontology, ICD-11, ICPC-3 | Monograph → clinical-term mapping (Track 04 direction) |
| P2 | Dr. Duke's databases, IMPPAT, KNApSAcK | Ethnobotanical / phytochemical context |
| P2 | Global Names Verifier | Fuzzy pre-matching of misspelled Latin names |
| P2 | BRENDA (ETHCSTWIN) | In-vitro enzyme inhibition context (low clinical specificity) |
| P3 | DrugBank, LiverTox (bulk), ESCOP, NAPRALERT, MPNS, UMLS, SNOMED CT, MedDRA, EPA CompTox, Kew POWO API, PFAF, TKDL, Native American Ethnobotany DB, Hugging Face / Kaggle sets | Licence, access or relevance constraints — see §8 |

---

## 2. Clinical and regulatory evidence

### 2.1 EMA HMPC — herbal inventory and EU herbal monographs — **P0**

| Field | Assessment |
|---|---|
| Category | Regulatory / clinical evidence, safety |
| Provider | European Medicines Agency, Committee on Herbal Medicinal Products (HMPC) |
| Access | Web pages; **inventory spreadsheet** (`medicines-output-herbal_medicines-report_en.xlsx`, linked from "Download medicine data") ✔ tested; monographs, assessment reports and reference lists as **PDF** per herbal substance ✔ tested |
| Authentication | None ✔ tested |
| Licensing | EMA website content may be reproduced with source acknowledgement ○ to verify against EMA legal notice before storing full PDF text in a public repo. Strategy: store extracted, attributed sections + URL + retrieval date; do not commit the PDFs. |
| Coverage | Inventory: **251 rows** (✔ tested, generated 02/11/2026). Outcome counts: 197 EU herbal monograph, 14 monograph + EU list entry, 4 list entry only, 27 public statements; status: 159 assessment finalised, 59 ongoing call for data. Includes St John's wort, garlic, echinacea, ginseng, valerian, black cohosh, liquorice, turmeric, milk thistle, saw palmetto, peppermint, ginger, senna, hawthorn, green tea, cranberry, devil's claw, pelargonium, rhodiola, and more (✔ tested by keyword). Kava has only a public statement; Ginkgo folium row shows no current outcome (revision in progress — ○ to verify). |
| Data quality | Very high: formal regulatory assessment. Monographs explicitly separate **well-established use (WEU)** from **traditional use (TU)** — exactly the distinction HerbaGuard must preserve. |
| Identifiers | Latin pharmaceutical name (e.g., *Hyperici herba*), botanical name with author (e.g., *Hypericum perforatum* L.), EMA document numbers (e.g., `EMA/HMPC/7695/2021`), herbal page URL |
| Integration | **Medium–high.** Spreadsheet is trivial. Monograph PDFs use a **two-column layout** (WEU / TU side by side) — verified on the St John's wort monograph: section 4.5 lists CYP3A4/2B6/2C9/2C19 and P-gp induction and named contraindicated drug groups, with dose-dependent statements (hyperforin ≤1 mg vs. >1 mg). Column-aware PDF parsing plus human spot-check is required. Spreadsheet export has blank cells that shift columns unless parsed by cell reference (✔ observed). |
| Use case | Backbone of the Herbal Knowledge Explorer (indications with WEU/TU status), the Interaction module (4.3/4.5 = "documented, regulatory"), and Safety (4.4/4.8). |
| Limitations | EU scope; monographs reflect the date of assessment (we must show the monograph date); the botanical-name column contains formatting defects (`Hypericum perforatumL.` — missing space ✔ observed); multiple documents per herb (final, draft, superseded) — only **final, non-superseded** monographs may be used as evidence. |
| Recommendation | **Include (P0).** Curate a focused herb set (see `mvp-scope.md`) rather than parsing all 251 entries. |

### 2.2 WHO monographs on selected medicinal plants — **P2**

| Field | Assessment |
|---|---|
| Provider | World Health Organization (WHO IRIS) |
| Access | PDF via IRIS (`iris.who.int/handle/10665/42052` reachable ✔ page, ~6.5 s response) |
| Authentication | None |
| Licensing | Varies by volume; older volumes are not CC-licensed ○ to verify per volume. Do not redistribute text. |
| Coverage | 4 volumes, global scope, pharmacology, contraindications, adverse reactions |
| Data quality | High, but volumes date from 1999–2009 — **outdated** for interaction evidence |
| Integration | High (long PDFs, inconsistent structure) |
| Use case | Secondary citation where EMA has no monograph |
| Recommendation | **P2.** Link out, do not parse for MVP. |

### 2.3 ESCOP monographs — **P3**

| Field | Assessment |
|---|---|
| Provider | European Scientific Cooperative on Phytotherapy |
| Access | Website reachable ✔ page; monographs are sold as books/online subscription ○ to verify |
| Licensing | Proprietary |
| Recommendation | **P3 (excluded).** Not openly accessible; cite only if a team member has legitimate access, and never ingest. |

### 2.4 NCCIH "Herbs at a Glance" — **P0**

| Field | Assessment |
|---|---|
| Provider | US National Center for Complementary and Integrative Health (NIH) |
| Access | HTML fact sheets per herb ✔ page (St John's wort page fetched; contains explicit interaction warnings) |
| Authentication | None |
| Licensing | US federal government work — generally public domain ○ to verify page-level notices (some images may be third-party) |
| Coverage | ~50 commonly used herbs; "what the science says" and safety sections |
| Data quality | High, plain language, cites underlying research |
| Integration | Low–medium: small number of pages; HTML section parsing |
| Use case | Patient-facing explanations; secondary "documented" interaction source; tone model for the Explainable Patient Interface |
| Recommendation | **Include (P0)** for the curated herb set. |

### 2.5 PubMed / NCBI E-utilities — **P0**

| Field | Assessment |
|---|---|
| Provider | US National Library of Medicine |
| Access | REST (`esearch`, `esummary`, `efetch`) ✔ tested |
| Authentication | None; free API key raises limit from 3 to 10 requests/s ◐ catalogue |
| Licensing | Citation metadata freely usable; **abstracts remain publisher-copyrighted** ○ to verify NLM terms. Store abstracts only in the local database (git-ignored), always with PMID and link. |
| Coverage | Query `"Hypericum"[MeSH] AND "Herb-Drug Interactions"[MeSH]` returned **148** records ✔ tested |
| Data quality | Peer-reviewed literature; MeSH publication types (Randomized Controlled Trial, Case Reports, In Vitro, Review…) enable **evidence-type classification without an LLM** |
| Identifiers | PMID, DOI, MeSH UIDs |
| Integration | Low |
| Use case | Evidence Intelligence Explorer; RAG corpus; evidence-level tagging |
| Limitations | Abstract-level only; MeSH indexing lag for recent papers; publication type ≠ study quality |
| Recommendation | **Include (P0).** |

### 2.6 Europe PMC — **P1**

| Field | Assessment |
|---|---|
| Provider | EMBL-EBI |
| Access | REST ✔ tested (`"St John's wort" AND interaction` → 1,304 hits) |
| Authentication | None |
| Licensing | Per article; open-access subset has explicit CC licences in metadata ◐ catalogue |
| Use case | Full-text OA articles for richer RAG chunks; licence field lets us include only CC-BY/CC0 full text |
| Recommendation | **P1.** |

### 2.7 ClinicalTrials.gov API v2 — **P1**

| Field | Assessment |
|---|---|
| Access | REST ✔ tested (`query.intr=Hypericum` → e.g. NCT06367036, completed, interventional) |
| Authentication | None |
| Licensing | US government registry ○ to verify terms |
| Use case | "Has this been tested in humans?" — trial count, status, phase per herb |
| Limitations | Registration ≠ results; many herbal trials have no posted results |
| Recommendation | **P1.** |

---

## 3. Safety and herb–drug interactions

### 3.1 openFDA drug labels (Structured Product Labeling) — **P0**

| Field | Assessment |
|---|---|
| Provider | US FDA |
| Access | REST `api.fda.gov/drug/label.json` ✔ tested |
| Authentication | None (API key optional for higher limits) ◐ catalogue |
| Licensing | openFDA licence page linked in every response ✔ tested; openFDA data is generally CC0 ○ to verify |
| Coverage | Labels whose `drug_interactions` section mentions: St John's wort **2,878**, ginseng 368, echinacea 281, garlic 274, ginkgo 272, goldenseal 271 ✔ tested. kava/valerian/licorice/turmeric returned no matches. |
| Data quality | Regulatory text, drug-specific. **Caveat:** counts include many repackager duplicates of the same generic; some mentions are generic boilerplate ("herbal products") — requires de-duplication by `openfda.generic_name` / `set_id` and sentence-level extraction. |
| Identifiers | `set_id`, `openfda.rxcui`, `openfda.generic_name`, UNII |
| Integration | Medium (dedupe + sentence extraction) |
| Use case | Drug-side "documented" interaction statements (e.g., a label of drug X stating St John's wort decreases its exposure). Combined with EMA (herb side) gives two independent regulatory perspectives. |
| Recommendation | **Include (P0).** |

### 3.2 openFDA CAERS (food / dietary supplement adverse events) — **P1**

| Field | Assessment |
|---|---|
| Access | REST `api.fda.gov/food/event.json` ✔ tested |
| Licensing | As above; the API's own disclaimer states reports do not establish causation and cannot estimate incidence ✔ tested |
| Coverage | Brand-name match counts: turmeric 579, garlic 458, ginseng 204, ginkgo 186, echinacea 91, kava 65, licorice 57, valerian 56, St John's wort 41, goldenseal 27 ✔ tested |
| Data quality | Spontaneous reports; free-text product names; multi-ingredient products; reporting bias |
| Use case | Safety Dashboard: "reported adverse events (not proof of causation)" with MedDRA-coded reaction counts |
| Recommendation | **P1**, displayed only with explicit non-causality framing. |

### 3.3 FDA Table of CYP enzyme and transporter substrates, inhibitors and inducers — **P1** *(not in catalogue; added)*

| Field | Assessment |
|---|---|
| Provider | US FDA ("For Healthcare Professionals — FDA's Examples of Drugs that Interact with CYP Enzymes and Transporter Systems") |
| Access | HTML page with tables ✔ page (fetched; mentions St John's wort, curcumin, diosmin as supplements in inducer/inhibitor examples) |
| Licensing | US government work ○ to verify |
| Use case | Drug → CYP/transporter substrate relationships, enabling the **"potential interaction (mechanism-based)"** class: herb documented as CYP3A4 inducer (EMA 4.5) × drug documented as CYP3A4-sensitive substrate (FDA table) |
| Limitations | "Examples" list — not exhaustive; absence ≠ not a substrate |
| Recommendation | **P1.** Replaces the role DrugBank would otherwise play, without licence restrictions. |

### 3.4 DrugBank — **P3**

| Field | Assessment |
|---|---|
| Access | Website reachable (release 5.1.22 shown) ✔ page; bulk download requires account and approval |
| Licensing | Free for academic non-commercial use with registration; redistribution restricted ◐ catalogue |
| Recommendation | **P3 (deferred).** Licence conflicts with a public GitHub repo containing processed data and approval timing is uncertain within 6 days. FDA table + labels + EMA cover the MVP need. Revisit post-hackathon. |

### 3.5 LiverTox — **P2 (link-out only)**

| Field | Assessment |
|---|---|
| Provider | NIDDK / NLM (NCBI Bookshelf) |
| Access | Direct page fetch returned a **reCAPTCHA browser check** ✔ tested — scripted scraping is blocked and must not be bypassed. E-utilities `db=books` search works (36 hits for a St John's wort query) ✔ tested. |
| Licensing | NIH content, generally public domain ○ to verify |
| Use case | Hepatotoxicity flags (e.g., kava, green tea extract, turmeric) as cited links |
| Recommendation | **P2.** Curate a short manual list of LiverTox URLs for the MVP herb set; no automated harvesting. |

### 3.6 EFSA Compendium of Botanicals — **P1**

| Field | Assessment |
|---|---|
| Provider | European Food Safety Authority |
| Access | Zenodo records 996024 (2016) and **1212388 (2018)** with `BOTANIC.xls`, `PlantList.xls`, `ENDPOINTSTUDY.xls` ✔ tested |
| Licensing | **CC BY 4.0** ✔ tested (Zenodo metadata) |
| Use case | Flag botanicals containing substances of possible concern; supports Safety Dashboard |
| Limitations | Last version 2018; legacy `.xls` format |
| Recommendation | **P1.** |

### 3.7 EPA CompTox — **P3**

Reachable ✔ page. Compound-level toxicology is far from the clinical HDI question and requires compound mapping first. **Deferred.**

### 3.8 BRENDA (ETHCSTWIN wrapper) — **P2**

Wrapper works ✔ tested (EC 1.14.14.1 → "unspecific monooxygenase"; inhibitor records return comments and `compound_id` only). EC 1.14.14.1 aggregates **all** CYP450 monooxygenases across organisms, so inhibitor records are not human-isoform-specific. Licence of underlying BRENDA data ○ to verify (catalogue says "check the current licence terms"). Useful only as **in-vitro** context, never as interaction evidence. **P2.**

### 3.9 Dr. Duke's Phytochemical and Ethnobotanical Databases — **P2**

Web reachable ✔ page; bulk download via USDA Ag Data Commons ◐ catalogue. Entries vary in sourcing depth (catalogue warns to cite the underlying reference). **P2** for constituent/activity context.

### 3.10 PubChem toxicity annotations — covered under §5 (PubChem).

---

## 4. Medicinal plant and ethnobotanical knowledge

| Resource | Access (verified) | Licence | Relevance to Track 04 | Priority |
|---|---|---|---|---|
| **IMPPAT 2.0** | Site reachable ✔ page | Open access, no login ◐ catalogue; reuse terms ○ to verify | Indian medicinal plants, phytochemicals, therapeutic uses; outside EU-monograph scope of the MVP | **P2** |
| **KNApSAcK Family** | Site reachable ✔ page | No explicit open licence found ○ to verify | Species–metabolite, Kampo/Jamu; redundant with LOTUS for our needs | **P2** |
| **LOTUS** | Portal reachable ✔ page; Wikidata SPARQL ✔ tested (239 compounds with "found in taxon" = *H. perforatum*) | **CC0** ◐ catalogue | Cleanest open plant → compound edge | **P2** (P1 if knowledge graph is built) |
| **Ewé** | Paper (PMC7015817) ◐ catalogue | Varies | Data model reference for use reports | **P3** (reference only) |
| **NAPRALERT** | **HTTP 502** on 2026-11-02 ✔ tested | Subscription ◐ catalogue | Not accessible | **P3** |
| **Regional ethnobotanical datasets** (Zenodo, Dryad, GBIF checklists) | Not individually tested | Varies; Nagoya / Local Contexts considerations ◐ catalogue | Community knowledge requires governance metadata; not essential for a safety tool | **P3** for MVP |
| **Native American Ethnobotany DB** | Not tested | Attributed to specific peoples ◐ catalogue | Restricted-knowledge concerns; out of scope | **P3** |
| **PFAF** | Not tested | Copyrighted; ask before scraping ◐ catalogue | Not a scholarly source | **P3** |
| **TKDL** | Restricted to patent offices ◐ catalogue | N/A | Case study only | **P3** |

**Rationale.** HerbaGuard is a *safety and evidence* tool for health systems. Ethnobotanical use records add cultural context, but each one would need governance metadata (community attribution, consent status). For the MVP, "traditional use" is drawn from the **EMA traditional-use (TU)** category, which is a regulatory statement with clear provenance, instead of from community datasets.

---

## 5. Chemistry and natural products

| Resource | Access (verified) | Licence | Role | Priority |
|---|---|---|---|---|
| **ChEBI** (ETHCSTWIN wrapper) | ✔ tested — `hyperforin` → `CHEBI:5834`, 3 stars, formula C35H52O4, KEGG C07608 | Wrapper is explicitly "not an official ChEBI API" ✔ tested; ChEBI data CC BY 4.0 ○ to verify | Constituent normalization | **P1** |
| **ChEBI** (official EBI API) | ✔ tested — same `CHEBI:5834` | as above | Fallback / cross-check | **P1** |
| **PubChem PUG-REST** | ✔ tested — hyperforin → CID 441298, InChIKey `KGSZHKRKHXOAMG-HQKKAZOISA-N` | Mostly public domain; some depositor-specific terms ○ to verify | Canonical compound key (InChIKey) | **P1** |
| **ChEMBL** | ✔ tested — hyperforin → `CHEMBL1237210` | CC BY-SA 3.0 ◐ catalogue (share-alike affects redistributed derived data) | Constituent → target bioactivity (e.g., PXR activation, CYP inhibition assays) | **P2** |
| **COCONUT** (ETHCSTWIN wrapper) | ✔ tested — organism *H. perforatum* (tax_id 65561, wcvp_id 516286) lists dozens of `CNP…` compound IDs; name suggestions work | COCONUT data CC0 ○ to verify | Plant → compound list | **P2** |
| **UniProt** | ✔ tested — CYP3A4 human → `P08684` (Swiss-Prot reviewed) | CC BY 4.0 ◐ catalogue | Canonical protein IDs for CYP/P-gp nodes | **P2** |
| **BRENDA** | see §3.8 | ○ to verify | In-vitro enzyme context | **P2** |
| **IMPPAT** | see §4 | | | **P2** |

**Rationale.** Chemistry explains *why* an interaction happens (e.g., hyperforin activates PXR → CYP3A4 induction), which is valuable for explanation, but the MVP's interaction classification must rest on clinical and regulatory evidence. Chemistry is therefore P1 only for the handful of **marker constituents named in monographs** (hyperforin, hypericin, glycyrrhizin, allicin, etc.), and P2 for broad compound catalogues.

---

## 6. Plant taxonomy and identification

| Resource | Access (verified) | Licence | Result for *Hypericum perforatum* | Priority |
|---|---|---|---|---|
| **WFO** (ETHCSTWIN wrapper) | ✔ tested — `/name/first_hit/` 0.4 s | WFO backbone CC0 ◐ catalogue; wrapper is "not an official WFO API" ✔ tested | `wfo_id` 728093 (`wfo-0000728093`), accepted, Hypericaceae, IPNI 433719-1 | **P0** |
| **WFO** (official matching REST) | ✔ tested — `list.worldfloraonline.org/matching_rest.php` | CC0 ◐ catalogue | `wfo-0000728093`, classification version 2026-06 | **P0** (fallback) |
| **WCVP** (ETHCSTWIN wrapper) | ✔ tested | WCVP licence in download ○ to verify (catalogue: "check the licence file") | `plant_name_id` 516286, Accepted, "Europe to China, NW. Africa", IPNI 433719-1 | **P1** |
| **IPNI** (ETHCSTWIN wrapper) | ✔ tested | ○ to verify | Returned **two** IPNI records for the same name and author: `433719-1` (status "tax. nov.", p. 785 — the ID used by WFO, WCVP and Wikidata) and a duplicate `101692-3` (status "unknown"). Both list the family as Clusiaceae, the placement at publication, whereas current backbones use Hypericaceae. A free-text IPNI search therefore cannot pick the right record on its own; IPNI IDs must be taken from the accepted-name backbone (WFO/WCVP). | **P1** |
| **NCBI Taxonomy / TaxTree** (ETHCSTWIN) | ✔ tested | NCBI public ◐ catalogue | `tax_id` 65561 | **P1** |
| **GBIF Species API** | ✔ tested (match + vernacular names) | GBIF backbone CC BY 4.0 ○ to verify | usageKey 3189486, EXACT, confidence 99 | **P1** |
| **Wikidata** | ✔ tested (SPARQL) | CC0 ◐ catalogue | WFO `wfo-0000728093`, IPNI `433719-1`, GBIF `3189486`, NCBI `65561`, POWO `urn:lsid:ipni.org:names:433719-1` — **all consistent** | **P1** |
| **Global Names Verifier** | ✔ tested | Free ◐ catalogue | Misspelling `Hypericum perforatun` → WFO record, PartialExact | **P2** |
| **Kew POWO** | API request returned **HTTP 403 / Cloudflare challenge** ✔ tested | | Not usable for scripted access; WCVP wrapper covers the need | **P3** |
| **Kew MPNS** | Bulk/API restricted and licensed ◐ catalogue | Restricted | Ideal for pharmaceutical names (e.g., *Hyperici herba* → taxon) but not redistributable | **P3** (manual validation only) |
| **Catalogue of Life / ChecklistBank** | Not tested | Open API ◐ catalogue | Redundant with WFO + GBIF for MVP | **P2** |

**Identity triangulation result (✔ tested).** For St John's wort, six independent sources agree on a single taxon:

```
WFO wfo-0000728093  ↔  IPNI 433719-1  ↔  WCVP 516286  ↔  GBIF 3189486  ↔  NCBI 65561  ↔  COCONUT organism 477
```

This confirms the catalogue's recommendation: `wfo_id` as the primary key with IPNI / GBIF / NCBI / WCVP stored as cross-references, and Wikidata as a crosswalk check.

**Pharmaceutical names.** EMA uses Latin pharmaceutical names (*Hyperici herba*, *Liquiritiae radix*) that are **not** taxon names: they encode the taxon plus the plant part. HerbaGuard must model a *herbal substance* (taxon + plant part + preparation) separately from the *taxon*. Plant parts map to the Plant Ontology (P2).

---

## 7. Clinical terminologies and ontologies

| Resource | Access (verified) | Licence | Role | Priority |
|---|---|---|---|---|
| **RxNorm / RxNav** | ✔ tested — `warfarin` → RxCUI 11289 | Free from NLM; some content needs UMLS licence ◐ catalogue | Drug normalization (ingredient level) | **P0** |
| **ATC (via RxClass)** | ✔ tested — warfarin → `B01AA` Vitamin K antagonists | ATC is owned by the WHO Collaborating Centre; bulk redistribution of the ATC index is restricted ○ to verify. Query via RxClass; store codes only. | Drug class grouping (EMA 4.5 names classes, e.g., "coumarin-type anticoagulants") | **P0** |
| **MeSH** | ✔ tested — `Hypericum` → D020902 | Free from NLM ◐ catalogue | Indication / pharmacologic action normalization; PubMed link | **P1** |
| **ICD-11** | API returned **HTTP 401** without token ✔ tested | Free registration for API key ◐ catalogue | "Monographs to clinical terms" (Track 04 direction) | **P2** (needs registration — user action) |
| **ICPC-3** | Site reachable ✔ page | Terms ○ to verify | Primary-care coding of indications | **P2** |
| **Disease Ontology (DOID)** | API returned **HTTP 500** ✔ tested; OBO file download works (HTTP 206 on ranged request) ✔ tested | CC0 ◐ catalogue | Open, redistributable indication IDs | **P2** (use file, not API) |
| **UMLS** | Account + licence ◐ catalogue | Restricted redistribution | | **P3** |
| **SNOMED CT** | Licensed ◐ catalogue | Restricted | | **P3** |
| **MedDRA** | Subscription ◐ catalogue | Restricted | CAERS already provides MedDRA-coded reaction **terms**; we display them but do not ship the terminology | **P3** |
| **ChEBI Ontology** | see §5 | | Chemical classes | **P2** |
| **Plant Ontology** | OBO Foundry ◐ catalogue | Open | Plant-part normalization (herba, radix, folium…) | **P2** |

---

## 8. Excluded or deferred resources — reasons

| Resource | Reason |
|---|---|
| DrugBank | Licence restricts redistribution; registration approval uncertain within the deadline |
| ESCOP | Proprietary monographs |
| NAPRALERT | Subscription; endpoint returned HTTP 502 |
| Kew POWO API | Cloudflare challenge (HTTP 403) — no scripted access; must not be bypassed |
| LiverTox (bulk) | reCAPTCHA on scripted access — must not be bypassed; link-out only |
| Kew MPNS | Licensed bulk/API access |
| UMLS, SNOMED CT, MedDRA | Licence restrictions incompatible with a public repository |
| EPA CompTox | Compound-level toxicology; too indirect for the HDI question |
| PFAF, TKDL, Native American Ethnobotany DB | Copyright, restricted access, or community-rights concerns |
| Hugging Face datasets | Search for "herb-drug", "herb drug interaction", "phytotherapy" returned **no datasets**; "herbal" returned small, unlicensed or image datasets and one explicitly **synthetic** safety dataset (`…-synth-herbal-traditional-medicine-safety…`) — synthetic data must not be presented as evidence ✔ tested |
| Kaggle datasets | Not tested (requires account); low expected provenance quality |

---

## 9. Catalogue resources outside Track 04 scope

Reviewed and not evaluated in depth because they serve Tracks 01–03:

- **Historical texts** (§1 of catalogue): Dioscorides, Alexander of Tralles, Hippocratic Corpus, Pliny, Avicenna, Culpeper, recipe books, Buchan, Medical Heritage Library, Wellcome, OpenITI, ctext.org, Logeion, CLTK, BHL, Europeana, Gallica, OPenn, Perseus/Scaife, Curious Cures. *Possible future extension:* show "historical claim vs. modern regulatory view" for a herb — appealing to the Track 01 judges, but out of MVP scope.
- **Images and specimens** (§7): GBIF occurrences with media, iDigBio, LifeCLEF, Pl@ntNet, BHL Flickr, Wikimedia Commons. Plant photo identification is **not** a safe input for an interaction checker (misidentification risk).
- **Conservation** (§8): IUCN Red List (token, non-commercial), CITES Species+ (token), TDWG WGSRPD. *Possible P2:* a "sustainability note" on threatened medicinal plants (e.g., goldenseal), which would support the "Best Community Impact" angle.
- **Text and metadata standards** (§9.3): TEI, IIIF, ALTO/PAGE — not relevant. **PROV-O**, **SKOS**, **Dublin Core / DataCite** — adopted as *modelling guidance* for provenance and mapping confidence (see `technology-evaluation.md`).

---

## 10. Data-quality risks identified during the audit

| # | Risk | Evidence | Mitigation |
|---|---|---|---|
| 1 | Name ≠ taxon | IPNI search returned two records (433719-1, 101692-3) for one name, with a historical family (Clusiaceae) | Resolve via WFO accepted name; keep all source IDs |
| 1b | Lookups fail on non-taxon strings | WFO `first_hit` returned `null` for `Hyperici herba` and for the malformed `Hypericum perforatumL.` ✔ tested | Pre-normalise strings; maintain a curated pharmaceutical-name → taxon table for the MVP herb set |
| 2 | Pharmaceutical name ≠ botanical name | EMA "Hyperici herba" | Separate `HerbalSubstance` (taxon + part) entity |
| 3 | Malformed source strings | EMA `Hypericum perforatumL.` | Normalization with logged transformations |
| 4 | Document versions | EMA lists final, draft and superseded monographs for one herb | Only final, non-superseded docs; record document ID and date |
| 5 | Duplicate drug labels | 2,878 SJW label hits include repackagers | Dedupe by generic name / RxCUI / set_id |
| 6 | Free-text product names in CAERS | Multi-ingredient brand names | Display as "reports mentioning X"; no causal or incidence claims |
| 7 | Hosted wrapper stability | ETHCSTWIN wrappers are hackathon infrastructure, not official services | Snapshot responses; official-API fallbacks (WFO REST, ChEBI EBI) |
| 8 | Non-specific enzyme data | BRENDA EC 1.14.14.1 covers all CYPs, all organisms | In-vitro context only |
| 9 | Spreadsheet export quirks | EMA xlsx skips blank cells | Parse by cell reference; schema validation |
| 10 | Outdated monographs | WHO volumes 1999–2009 | Display publication/assessment date prominently |
