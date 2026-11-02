# Scientific and Ethical Considerations

**Project:** HerbaGuard — EthnoHack 2026, Track 04
**Phase:** 0 — Research and Dataset Audit
**Status:** Proposed framework. It becomes binding for Phases 1–8 once the user approves it.

This document sets the rules HerbaGuard follows when it stores, classifies and presents scientific information. Each rule is tied to a concrete data source or failure mode observed during the audit.

---

## 1. Core principles

| # | Principle | Concrete consequence in HerbaGuard |
|---|---|---|
| 1 | Traditional use ≠ clinical efficacy | EMA **traditional use (TU)** indications are labelled "accepted on the basis of long-standing use" and never shown as "proven effective". EMA **well-established use (WEU)** is shown separately. |
| 2 | In-vitro / animal ≠ clinical | Evidence items carry an `evidence_type`; BRENDA, ChEMBL and in-vitro PubMed studies can never raise an interaction above "Suspected". |
| 3 | No reported interaction ≠ safe | The UI never shows "safe", "no interaction" or a green tick. The lowest state is **"No interaction evidence found in the sources searched"**, listing those sources and their coverage dates. |
| 4 | Spontaneous reports ≠ causality | CAERS data appears only in the Safety Dashboard under "Reported adverse events — not proof of causation", with openFDA's own disclaimer. Never used to classify an interaction. |
| 5 | Correlation ≠ causation | No computed risk scores from report counts; no incidence estimates (openFDA explicitly forbids that use). |
| 6 | Uncertainty is visible | Every finding shows evidence class, source type, source date, and a short "what we don't know" note. |
| 7 | Every claim is traceable | Every displayed statement links to a `Provenance` record: source, document/record ID, URL, retrieval timestamp, extraction method, and verbatim excerpt where licence permits. |
| 8 | Preserve original identifiers | Source IDs (wfo_id, IPNI, RxCUI, PMID, EMA document number, openFDA `set_id`) are stored unchanged alongside internal IDs. |
| 9 | Distinguish evidence types | Controlled vocabulary in §3. |
| 10 | Never fabricate | No generated references, mechanisms, or classifications. The AI assistant may only cite retrieved items; citations are validated against the store after generation (§6). |
| 11 | No personalised medical advice | No dosing, no "you should", no diagnosis. Questions that require personal advice get a referral message. |
| 12 | Not a replacement for professionals | Persistent disclaimer; "talk to your pharmacist or doctor" prompts at every interaction result. |

---

## 2. Herb–drug interaction classification

The master prompt asks for five states. We define them **operationally**, so that every class assignment is reproducible from stored evidence and needs no judgement call at runtime.

| Class | Display label | Assignment rule (all must be traceable) | Example (from audited data) |
|---|---|---|---|
| **A — Documented** | "Documented interaction" | At least one **regulatory or authoritative clinical source** explicitly names this herb with this drug, or with a drug class that the drug belongs to (class membership via ATC / RxClass). Eligible sources: EMA monograph §4.3 or §4.5 (final, non-superseded); FDA drug label `drug_interactions`, `contraindications` or `warnings` section; NCCIH fact sheet. | EMA *Hyperici herba* §4.5 (WEU): concomitant use with coumarin-type anticoagulants, cyclosporine, tacrolimus, protease inhibitors, irinotecan, imatinib… is contraindicated. Warfarin ∈ ATC B01AA (Vitamin K antagonists, coumarin type) → **A** for St John's wort + warfarin. |
| **B — Potential (mechanism-based)** | "Potential interaction (based on mechanism)" | No class-A statement for the pair, **but**: (i) a regulatory source documents the herb as an inducer/inhibitor of enzyme or transporter E, **and** (ii) an authoritative source (FDA CYP/transporter table or FDA label) documents the drug as a substrate of E. Both premises are shown. | Herb documented as CYP3A4 inducer (EMA §4.5) × drug listed as sensitive CYP3A4 substrate (FDA table), but the drug itself is not named in either monograph or label. |
| **C — Suspected** | "Suspected interaction (limited evidence)" | Only weaker evidence exists for the pair: human case reports, small uncontrolled PK studies, animal or in-vitro studies, retrieved from PubMed with matching MeSH publication types; **or** a regulatory source mentions the herb generically ("herbal products") without naming it. | PubMed case report linking herb X and drug Y; in-vitro inhibition data. |
| **D — No evidence found** | "No interaction evidence found in the sources we searched" | Herb and drug both resolved to identifiers; all class-A/B/C sources were searched; nothing was found. Shown with: the list of sources searched, their versions/dates, and the sentence "This does not mean the combination is safe." | — |
| **E — Insufficient information** | "We cannot assess this combination" | Either entity could not be resolved to an identifier, **or** the herb is outside HerbaGuard's curated coverage (no monograph or fact sheet ingested), **or** an ingestion error prevents complete search. | Herb typed as an ambiguous common name with several candidate taxa. |

### 2.1 Severity

HerbaGuard does **not** compute severity. It only **relays the wording used by the source**, quoted and attributed:

- EMA: "contraindicated", "special care should be taken", "not recommended"
- FDA label: "avoid", "contraindicated", "monitor", "not recommended"

If sources disagree, all are shown side by side with dates (see §5).

### 2.2 Context qualifiers that must be preserved

Observed in the St John's wort monograph and required for correctness:

- **Use category:** WEU vs. TU sections may contain **different** interaction statements.
- **Dose dependence:** EMA states a threshold based on daily hyperforin intake (≤1 mg vs. >1 mg) and duration (≤2 weeks). The interaction record must store this condition text; the UI must not collapse it into a yes/no.
- **Plant part / preparation:** interactions are stated for *Hyperici herba* preparations, not for the taxon in general.
- **Direction and mechanism:** e.g., "induces CYP3A4, CYP2B6, CYP2C9, CYP2C19 and P-glycoprotein".

---

## 3. Evidence-type vocabulary

Every `EvidenceItem` gets exactly one type. For PubMed, the type is derived deterministically from MeSH **Publication Type** and MeSH terms, not by an LLM.

| Code | Evidence type | Typical source | Can support class |
|---|---|---|---|
| `REG` | Regulatory assessment | EMA monograph, FDA label | A, B (premise) |
| `GOV` | Government consumer/professional summary | NCCIH, FDA CYP table | A (NCCIH), B (FDA table) |
| `SR` | Systematic review / meta-analysis | PubMed PT "Systematic Review", "Meta-Analysis" | C (displayed, not auto-upgraded) |
| `RCT` | Randomised controlled trial | PubMed PT "Randomized Controlled Trial" | C |
| `CLIN` | Other human clinical study (PK, cohort, case series) | PubMed PT "Clinical Trial", "Observational Study" | C |
| `CASE` | Case report | PubMed PT "Case Reports" | C |
| `ANIMAL` | Animal study | MeSH "Animals" without "Humans" | C |
| `INVITRO` | In-vitro / biochemical | MeSH "In Vitro Techniques"; BRENDA; ChEMBL | C |
| `TRAD` | Traditional use (regulatory recognition) | EMA TU section | Never for interactions; only for indications |
| `SPONT` | Spontaneous adverse-event report | openFDA CAERS | None (signal display only) |
| `COMP` | Computational prediction | none in MVP | None |

**Why systematic reviews do not automatically produce class A:** reviews of herb–drug interactions often pool case reports and in-vitro data. Upgrading them would require human appraisal, which the MVP cannot do at scale. They are shown prominently but the class stays evidence-driven. This rule may be relaxed later through documented, human-curated assertions.

---

## 4. Taxonomic and identifier integrity

Findings from the audit (see `dataset-audit.md` §6 and §10):

1. **Common names are ambiguous.** "Ginseng" can mean *Panax ginseng*, *P. quinquefolius*, or *Eleutherococcus senticosus* ("Siberian ginseng"). HerbaGuard always resolves to a `wfo_id` and asks the user to choose when several candidates exist (class E until resolved).
2. **Pharmaceutical names are not taxon names.** *Hyperici herba* = *Hypericum perforatum* + aerial parts. These are modelled as `HerbalSubstance(taxon, plant_part)`.
3. **Duplicate nomenclatural records exist.** IPNI returned two records for *H. perforatum* L.; we take IPNI IDs from the WFO/WCVP accepted record.
4. **Synonyms.** User input in a synonym (e.g., an older binomial) is resolved to the accepted name, and the UI shows "You searched for X, accepted name Y (source: WFO, version 2026-06)".
5. **Fuzzy matches need confirmation.** WFO `find_similar` returned *H. perfoliatum* as second hit for a typo of *perforatum*; automatic acceptance only above a documented similarity threshold and only if a single candidate clears it.
6. **Drug identity.** Drugs are normalised to RxNorm ingredient (TTY `IN`) RxCUIs; brand names map to ingredients. ATC classes come from RxClass, so the class-based matching in §2 is auditable.
7. **Chemical identity.** Constituents use InChIKey as join key, with ChEBI and PubChem CID as cross-references.

---

## 5. Conflicting and outdated evidence

| Situation | Rule |
|---|---|
| Two sources disagree (e.g., EMA contraindicated vs. a label saying "monitor") | Show both, attributed and dated; class is the **highest** class supported by any eligible source; no silent override. |
| Superseded EMA document | Never used as evidence; may be stored for lineage with `status=superseded`. |
| Old source (e.g., WHO vol. 1, 1999) | Shown with year; flagged "may be outdated" if > 10 years old. |
| Source updated after ingestion | Each record stores `retrieved_at` and source version; the dashboard shows data freshness per source. |
| Source precedence (for display order, not for deletion) | 1 EMA final monograph → 2 FDA label → 3 NCCIH → 4 FDA CYP table → 5 PubMed systematic reviews → 6 other PubMed → 7 CAERS (signal only). |

---

## 6. AI-specific safeguards (for Phase 5)

1. **Retrieval-only grounding.** The assistant answers only from retrieved, stored items (monograph sections, label excerpts, NCCIH text, PubMed abstracts). No retrieval → explicit "insufficient evidence" answer.
2. **Classification is not done by the LLM.** The interaction class is computed by deterministic rules (§2) and passed to the LLM as a fact. The LLM explains; it does not decide.
3. **Citation validation.** Each citation marker in generated text must resolve to a retrieved chunk ID. Answers with unresolvable or missing citations are rejected or regenerated; failing that, an extractive fallback (quoted source passages) is shown.
4. **Separation of voices.** The UI visually separates *source text* (quoted, attributed) from *generated explanation* (labelled "AI-generated summary").
5. **Refusal patterns.** Dosing requests, diagnosis requests, "is it safe for me" questions → referral response plus available evidence, no personal recommendation.
6. **Evaluation.** A fixed test set (Phase 5) covering: documented pairs, pairs with no evidence, unknown herbs, ambiguous names, dosing questions, prompt-injection attempts in retrieved text. Metrics: citation precision, unsupported-claim rate (manual review), correct refusal rate.

---

## 7. Ethical and legal considerations

### 7.1 Traditional and Indigenous knowledge

- The MVP draws "traditional use" only from **EMA TU monographs** — public regulatory documents about products on the EU market — not from community-collected ethnobotanical datasets.
- Community-attributed datasets (e.g., Native American Ethnobotany DB, regional field studies) are **excluded** from the MVP. Any future inclusion requires: community attribution, licence, consent status, and Local Contexts TK/BC Labels or Notices where applicable, consistent with the Nagoya Protocol guidance in the organizer catalogue.
- The README will include a statement on these principles.

### 7.2 Licensing and redistribution

The repository is **public** (Devpost requirement). Therefore:

| Material | Committed to Git? |
|---|---|
| Our code, docs, schemas, tests | Yes (MIT licence already in repo) |
| Curated mapping tables we author (e.g., pharmaceutical name → wfo_id for the MVP herbs) | Yes, with sources cited |
| CC0 / CC BY data extracts (WFO, Wikidata, EFSA, GBIF) | Yes if small, with attribution file |
| EMA extracted sections | Only after confirming EMA reuse terms; otherwise fetched by the pipeline at build time |
| PubMed abstracts, Europe PMC non-OA text | **No** — fetched at runtime into a git-ignored local store |
| Raw API snapshots | Small test fixtures only; bulk snapshots git-ignored |
| DrugBank, UMLS, SNOMED CT, MedDRA content | **Never** |

A `DATA_SOURCES.md` / attribution file with licence, URL, retrieval date and attribution text per source is a Phase 2 deliverable.

### 7.3 Privacy

- No user accounts, no storage of personal medication lists on the server in the MVP. Medication inputs are processed per request and not logged with identifiers.
- Logs must not contain free-text health questions in production mode.
- If an external LLM API is used, the UI must state that questions are sent to a third-party model provider.

### 7.4 Responsible communication

- Persistent banner: "HerbaGuard provides information from scientific and regulatory sources. It is not medical advice and does not replace your doctor or pharmacist."
- No "recommender" feature that suggests herbs for conditions (see `ethnohack-requirements.md` §3).
- Organizer requirement honoured: no modern dosing instructions derived from historical or traditional sources; no encouragement to prepare or ingest remedies.

---

## 8. Known scientific limitations of the MVP (to state openly in the submission)

1. Coverage is limited to a curated set of herbs; class E will be common outside it.
2. Mechanism-based class B depends on the FDA "examples" table, which is not exhaustive.
3. Product variability (extract type, hyperforin content, adulteration) cannot be captured from user input.
4. PubMed-derived evidence types rely on MeSH indexing, which lags for recent articles and does not measure study quality.
5. EU (EMA) and US (FDA, NCCIH) regulatory perspectives dominate; other regions are under-represented.
6. Pharmacodynamic interactions (e.g., additive bleeding risk, serotonergic effects) are captured only when a source states them; HerbaGuard does not infer them.
