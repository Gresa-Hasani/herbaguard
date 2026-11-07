# DDID — Drug–Diet (herb/food) Interaction Database

**Status:** Pipeline and schema implemented (Phase 5 expansion; migration 0006, `herbaguard ingest ddid`). **Import into the development database not yet run** (Docker engine was not available on 2026-11-06). Source: https://bddg.hznu.edu.cn/ddid/download/ — five CSV files downloaded manually into `data/raw/ddid/` (git-ignored, never modified or copied; SHA-256 recorded per file in `source_record`).

## 1. Licence

No licence or terms are stated in the five files. The download page and publication were **not yet checked** in this session. Until verified the source is registered as `licence_status = to_verify`, `redistributable = false`: DDID text is never sent to cloud models (licensing guard), raw files are not committed, and redistribution of derived data needs confirmation first.

## 2. Files (audit 2026-11-06, actual counts)

The download page lists seven categories; the files combine them into five (no separate *Food* or *Drug Indications* file: food items appear only inside the interaction file).

| File | Rows | Columns | Key | Notes |
|---|---|---|---|---|
| Interaction Information | 23,950 | 26 | none (row) | 19,085 herb rows (H…) / 4,865 food rows (F…); 419 exact duplicate rows; 1,196 rows share drug + herb + PMID + result with another row (kept: they differ in other fields) |
| Herb Information | 1,068 | 25 | `FHDI_Herb_ID` (H…) | Latin (83 empty), English, Pinyin, Chinese names; TCM properties; NCBI `Taxonomy_ID` (370 empty), NPASS, HERB, SymMap ids; `Use_Part` (394 empty) |
| NP Information | 43,668 | 7 | (`np_id`, `FHDI_Herb_ID`) | 20,309 NPASS compound ids, 680 organisms; SMILES, name, PubChem CID (670 empty), MW; **no InChIKey**; 1,697 exact duplicate rows |
| Drug Information | 1,516 | 17 | `FHDI_Drug_ID` (D…) | DrugBank (25 empty), PubChem CID/SID, ChEBI, InChI/InChIKey, CAS, TTD, ADReCS; **no RxCUI** |
| Target Information | 1,356 | 6 | (`TTD_ID`, `Target_ID`) | TTD drug id, **TTD target id** (T…), name, highest status, mechanism of action, `FHDI_Drug_ID` |

Interaction file, as stated by DDID:

| Field | Distribution |
|---|---|
| `Effect` | Possible 17,827 · No Effect 2,374 · Positive 1,915 · Negative 1,437 · Harmful 393 · "possible" 4 |
| `Experimental_Species` | Rat 12,335 · NA 6,446 · Homo Sapiens 3,647 (+2 "Homo sapiens") · Rabbit 893 · Dog 334 · Mice 279 · Pig 13 · Zebrafish 1 |
| `Relationship_classification` | HFDI 17,670 · Drugbank 2,784 · FDI-Package Insert 1,666 · Dietary Effect-Package Insert 1,009 · Dietary effects 821 |
| References | PMID 18,478 rows · DOI 17,362 · neither 5,472 |
| `Target_ID` | 29,011 accessions, UniProt format (e.g. P11712); **0 of them occur in the Target file**, which uses TTD ids — two namespaces, never joined |

Interaction ↔ Drug file: 23,950 / 23,950 drug ids resolve. Interaction ↔ Herb file: all 19,085 herb rows resolve; food ids have no entity file. The 16 curated HerbaGuard herbs appear in ≈1,970 herb rows (name match; e.g. Licorice 350, *Hypericum perforatum* 335).

## 3. Representation (migration 0006 — generic for future datasets)

| DDID data | Table | What is kept |
|---|---|---|
| Herb, Drug, NP compound, TTD target, food | `external_entity` (`kind`) | every original column in `attributes`; identifiers by namespace; mapping status, method and note |
| Herb → NP (NP file), Drug → TTD target (Target file) | `external_relation` | relation as stated, its attributes (e.g. NPASS org id; TTD status, MOA), all source row numbers |
| Interaction rows | `experimental_observation` | the complete original row (`original`), typed copies (effect label, species, result, conclusion, PMID, DOI, reference, UniProt accessions), **derived** study context / evidence type in separate columns (`ddid_species_v1`), all source row numbers of exact duplicates |
| References | `evidence_item` | an existing item with the same PMID is reused; otherwise one DDID item per reference (type CLIN only if all its records are human, ANIMAL only if all are animal, else OTHER) |

## 4. Interpretation rules (enforced in code)

* **Study context** from the species only: Homo sapiens → human; Rat/Rabbit/Dog/Mice/Pig/Zebrafish → animal; NA or anything else → **unknown** (never human). New species values are reported.
* **DDID `Effect` labels are DDID's own labels** — kept verbatim, shown as such, **never mapped to A–E**. "Possible" (74 % of rows, mostly rat studies) says nothing about clinical relevance.
* **Not part of the A–E classification.** None of the new tables is read by `domain.interactions`; a test asserts identical classifications before and after an import.
* **Mappings** (nothing silent): herb → HerbaGuard **taxon** by exact scientific name only — never to a herbal substance, because the DDID plant part (`Use_Part`) may differ (e.g. *Semen Ginkgo* vs Ginkgo folium); drug → HerbaGuard drug by exact name, then exact synonym; several candidates → `ambiguous`; none → `unresolved` (kept for review). Interaction UniProt accessions → `target.uniprot_accession` (same namespace). TTD targets are not joined.
* **Duplicates:** only rows identical in every field are collapsed (all row numbers kept); rows differing in any field stay separate observations.
* **Idempotent, retry-safe:** deterministic ids and upserts; source records keyed by file hash; records of an earlier file version are removed after an error-free run.

## 5. Use in the AI layer

For a herb–drug question, DDID records whose herb entry maps to the herb's species and whose drug entry maps to the drug are added as context items `X#` (role `experimental_evidence`), at most four (human first, then records with a PMID), plus a count by study context. Each item states the species, the study context ("animal study: NOT human clinical evidence"), that the DDID label is not a HerbaGuard class, and that the plant part may differ. Validation removes paragraphs that present only animal/unspecified-species records as clinical evidence (`experimental_as_clinical`). DDID records are **not embedded** (structured data); they are not sent to cloud models.

## 6. Not yet integrated, and plan

| Data | Why not yet | Plan |
|---|---|---|
| Herbs without a HerbaGuard taxon (most of 1,068) | Taxonomy is loaded only for curated herbs | Resolve Latin names through the existing WFO/ETHCSTWIN taxonomy pipeline in batches (network; cost to be estimated), then re-run the import |
| Drugs without a HerbaGuard RxCUI | Drug index holds ≈350 RxNorm ingredients | RxNav resolution by name/InChIKey (~1,500 lookups, ≈25 min); review ambiguous results |
| NP compounds (20,309) | No InChIKey; `constituent` requires one | Resolve PubChem CID → InChIKey (PubChem PUG REST, batched) or COCONUT; then link to `constituent` |
| TTD targets | No UniProt cross-reference in DDID | Map TTD → UniProt only with an independently published cross-reference (TTD download); otherwise keep separate |
| Food items | HerbaGuard has no food entities | Out of current scope; records are stored |
