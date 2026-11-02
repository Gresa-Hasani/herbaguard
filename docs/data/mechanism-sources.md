# Mechanism Layer — Source Investigation (Phase 4)

**Date:** 2026-11-02. Verification markers as in Phase 0: **✔ tested** (real request on that date), **✔ page** (stated on the provider page), **◐ catalogue / prior audit**, **○ to verify**.

The mechanism layer needs two kinds of statements:

1. **Herb side** — *herb (or constituent) induces / inhibits enzyme or transporter E*.
2. **Drug side** — *drug D is a substrate (or inhibitor / inducer) of E*.

## 1. Sources evaluated

| Source | URL | Format and fields | Licence / reuse | Retrieval | Decision |
|---|---|---|---|---|---|
| **FDA — For Healthcare Professionals: Examples of Drugs that Interact with CYP Enzymes and Transporter Systems** | [fda.gov page](https://www.fda.gov/drugs/drug-interactions-labeling/healthcare-professionals-fdas-examples-drugs-interact-cyp-enzymes-and-transporter-systems) | One HTML page. Table 1: 245 rows × 11 columns (drug or other substance; CYP strong/moderate/weak inhibitor; strong/moderate/weak inducer; sensitive substrate; moderately sensitive substrate; transporter inhibitor; transporter substrate). Cells list isoforms ("2D6; 3A weak inhibitor"). Footnotes as `<sup>`. Tables 2–3 define the categories (e.g. strong inhibitor = AUC ≥5-fold). "Content current as of 05/29/2026". ✔ tested (page read in a browser 2026-11-02) | U.S. government work; FDA website content is generally public domain — page-level notice **○ to verify** | `GET` the page; parser `ingestion/parsers/fda_cyp_table.py`. FDA also offers a client-side Excel export (DataTables button) — not used, the HTML is the authoritative rendering | **P0 for Phase 4 — used** (drug side, and herb side for the five non-drug rows) |
| FDA — Drug Development and Drug Interactions: Table of Substrates, Inhibitors and Inducers | [fda.gov page](https://www.fda.gov/drugs/drug-interactions-labeling/drug-development-and-drug-interactions-table-substrates-inhibitors-and-inducers) | HTML; *index* drugs for clinical DDI studies only (≈ 15 substrates, e.g. midazolam, triazolam) and in-vitro probe tables. "Content current as of 06/05/2023". ✔ tested | As above | — | **Not used.** Designed for drug developers; the clinical list is a subset of the healthcare-professional table, and the in-vitro probe tables are not clinical evidence |
| EU herbal monographs (EMA HMPC), section 4.5 | Already ingested in Phase 2 (`ema_hmpc`) | Stored section text per use category, with PDF provenance | "Reproduction is authorised provided the source is acknowledged" ✔ page (Phase 2) | No new request: Phase 4 reads the stored section text | **Used** (herb side). Example: *"Hyperici herba preparations induce the activity of CYP3A4, CYP2B6, CYP2C9, CYP2C19 and P-glycoprotein."* |
| openFDA drug labels | Ingested in Phase 2 (`openfda_label`) | Label sections mention CYP roles in prose ("strong CYP3A inducers, including St John's wort") | ◐ (Phase 2) | — | **Deferred.** Free-text role extraction from 270+ labels needs its own validation; the FDA table already gives curated drug roles |
| DrugBank | go.drugbank.com | Enzyme/transporter "substrate/inhibitor/inducer" per drug | Academic licence, registration required; redistribution restricted ◐ (Phase 0) | Download after registration | **Excluded** — licence incompatible with a public repository (Phase 0 decision) |
| PharmGKB | pharmgkb.org | Clinical annotations (mainly pharmacogenomics), drug labels | CC BY-SA 4.0 for most downloads ○ to verify | Downloads (account) | **Not used.** Pharmacogenomic focus; share-alike terms would apply to derived data; no herb coverage |
| PubMed | Ingested in Phase 2 | Abstracts | Abstracts © publishers | — | **Not used for edges** (no validated extraction; PubMed stays "related literature") |
| ChEMBL | ebi.ac.uk/chembl | In-vitro bioactivity (IC50 etc.) | CC BY-SA 3.0 ◐ (Phase 0) | API | **Not used** — in-vitro data never supports class B (scientific principle 2) |
| ETHCSTWIN BRENDA wrapper | brenda.ethcstwin.di.uoa.gr:65000 | EC-level enzyme data; inhibitor rows not organism/isoform specific | ○ to verify | API | **Not used** — EC 1.14.14.1 lumps all CYPs across organisms (Phase 0 finding) |
| UniProt | rest.uniprot.org | Protein identity | CC BY 4.0 ◐ | `GET /uniprotkb/<acc>.txt` | **Used for identifiers only.** All 17 accessions in `data/curated/targets.yaml` checked ✔ tested (reviewed, *Homo sapiens*, gene name matches) |
| PubChem | pubchem.ncbi.nlm.nih.gov | Compound identity | Public domain (NCBI) ◐ | PUG REST | **Used for identifiers only.** Curcumin CID 969516, InChIKey VFLDPWHFBUODDF-FCXRPNKRSA-N ✔ tested |

## 2. FDA table — observations from the real page

| Observation | Handling |
|---|---|
| The column, not the cell wording, defines role and potency; cell wording sometimes deviates ("3A moderate substrate" in the moderately-sensitive column) | Column wins; contradictions are recorded as `fda_cell_wording` issues |
| Footnote markers are `<sup>` inside name and role cells (e.g. `OATP1B1<sup>13</sup>`) | Removed before reading targets; footnote text stored as `conditions` |
| Separators vary: `;`, `,`, `and` ("2C8 and 3A", "BCRP and P-gp transporters") | Fixed target table; anything unread is reported (`fda_cell_unparsed_text`, e.g. the stray "b" in the cenobamate row) |
| "OATP1B transporters" without a number | Mapped to OATP1B1 and OATP1B3 (FDA's legend groups them as OATP1B1/OATP1B3) |
| Duplicate rows (aprepitant twice, different columns) | Both kept |
| Five non-drug rows (St. John's wort, curcumin, diosmin, tobacco, grapefruit juice) and two non-ingredient rows (piperine, oral contraceptives) | Mapped explicitly in `data/curated/mechanism_sources.yaml`; only St. John's wort (herb) and curcumin (constituent of turmeric) are stored |
| Combination regimens ("lopinavir and ritonavir") and single enantiomers ("S-mephenytoin") | Skipped with a reason; not sent to RxNorm |
| The table is "a guide and not … a comprehensive list" (FDA) | Stated in every target detail and in the class-B caveat: a drug that is not listed may still be affected |
| fda.gov may refuse non-browser clients | The HTTP status is recorded; a page saved from a browser can be ingested with `--fda-html-file` (the record states `saved_from_browser`) |

## 3. What Phase 4 does not cover

- Enzyme/transporter roles of drugs that the FDA table does not list.
- Effects of herbs other than St John's wort that EMA monographs do not state in a recognised sentence form (sentences that name an enzyme but are not used are listed as `ema_mechanism_sentence_not_used` issues, so recall can be reviewed).
- Pharmacodynamic interactions (e.g. serotonergic, anticoagulant effects) — these stay with the statement-based classes A/C.
