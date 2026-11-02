# MVP Scope

**Project:** HerbaGuard — EthnoHack 2026, Track 04
**Phase:** 0 — Research and Dataset Audit
**Date:** 2026-11-02 (Monday)
**Hard deadline:** Sunday 2026-11-08, 10:00 CET (Devpost)

---

## 1. Problem statement

People combine herbal medicinal products with prescription drugs, often without telling their doctor or pharmacist. Some combinations are formally contraindicated by regulators — for example, the EU herbal monograph on St John's wort (*Hyperici herba*, EMA/HMPC/7695/2021) contraindicates concomitant use with coumarin-type anticoagulants, cyclosporine, tacrolimus, several HIV protease inhibitors and some cytostatics because the herb induces CYP3A4, CYP2B6, CYP2C9, CYP2C19 and P-glycoprotein.

The evidence exists but is scattered across herb-side regulatory monographs (EMA), drug-side labels (FDA), government fact sheets (NCCIH) and the literature (PubMed). It uses incompatible names (pharmaceutical Latin, botanical binomials, brand names, common names) and differs in evidence strength. Patients and health professionals get no single, traceable view that also says how strong the evidence is.

**HerbaGuard's MVP answers one question well:**
> *"What is known about combining herb Y with drug X — how strong is that evidence, and where exactly does it come from?"*

and surrounds it with the explorer, evidence and explanation features that make that answer understandable.

---

## 2. Time budget reality

About **5.5 working days** remain. The master prompt defines 8 more phases, each ending in a review-and-approval gate. That only fits if phases are small and approvals are quick. Proposed schedule:

| Day | Date | Phase(s) | Target outcome |
|---|---|---|---|
| Mon | 2 Nov | **0** Research (this phase) | Approved scope and architecture direction |
| Mon–Tue | 2–3 Nov | **1** Architecture & foundation | Repo skeleton, Docker Compose (API + Postgres + web), schema v1, CI running |
| Tue–Wed | 3–4 Nov | **2** Data ingestion | Curated herb set ingested from P0 sources, provenance stored, ingestion tests |
| Wed | 4 Nov | **3** Backend APIs | Plant, drug, interaction, evidence endpoints with tests |
| Wed | 4 Nov | **4** Knowledge graph | **Recommended: decision document only** — relational graph tables + graph view (see `technology-evaluation.md` §4) |
| Thu | 5 Nov | **5** AI & RAG | Grounded assistant with citation validation and evaluation set |
| Thu–Fri | 5–6 Nov | **6** Frontend | All MVP screens connected to the API |
| Sat | 7 Nov | **7** Integration & validation | End-to-end demo scenarios verified; fixes |
| Sat–Sun | 7–8 Nov | **8** Submission | README, data-source/licence docs, ≤10 slides, ≤10-min video script; **user** records video and submits on Devpost before 10:00 CET |

**Buffer:** effectively none. If a phase slips, the cut order in §6 applies.

**User-side tasks that cannot be delegated:** Devpost registration/eligibility confirmation, recording the pitch video, the final Devpost submission, all Git commits and pushes.

---

## 3. Target users

| User | Need | MVP treatment |
|---|---|---|
| Community pharmacist / GP | Fast, citable check of a herb–drug pair | Primary persona: professional detail view with sources |
| Patient / caregiver | Understand a warning in plain language | Plain-language view of the same result, with referral prompts |
| Health-system educator | Explain evidence levels | Evidence explorer and badges (secondary) |

---

## 4. MVP coverage

### 4.1 Herbs — curated set

Coverage is deliberately curated. The selection criteria are:

1. An EMA herbal entry exists (confirmed in the EMA inventory spreadsheet, 2026-11-02), preferably a final EU herbal monograph.
2. The herb is commonly used and/or has known interaction relevance.
3. The herb also appears in NCCIH Herbs at a Glance (preferred, not mandatory).

**Candidate list (16)** — all confirmed present in the EMA inventory; whether each monograph's §4.5 contains a specific interaction statement will be checked during Phase 2, not assumed:

| # | Common name | EMA pharmaceutical name | Botanical name |
|---|---|---|---|
| 1 | St John's wort | Hyperici herba | *Hypericum perforatum* L. |
| 2 | Garlic | Allii sativi bulbus | *Allium sativum* L. |
| 3 | Purple coneflower | Echinaceae purpureae herba / radix | *Echinacea purpurea* (L.) Moench |
| 4 | Ginseng | Ginseng radix | *Panax ginseng* C.A.Mey. |
| 5 | Valerian | Valerianae radix | *Valeriana officinalis* L. |
| 6 | Black cohosh | Cimicifugae rhizoma | *Actaea racemosa* L. (syn. *Cimicifuga racemosa*) |
| 7 | Liquorice | Liquiritiae radix | *Glycyrrhiza glabra* L. |
| 8 | Turmeric | Curcumae longae rhizoma | *Curcuma longa* L. |
| 9 | Milk thistle | Silybi mariani fructus | *Silybum marianum* (L.) Gaertn. |
| 10 | Saw palmetto | Sabalis serrulatae fructus | *Serenoa repens* (W.Bartram) Small |
| 11 | Ginger | Zingiberis rhizoma | *Zingiber officinale* Roscoe |
| 12 | Green tea | Camelliae sinensis non fermentatum folium | *Camellia sinensis* (L.) Kuntze |
| 13 | Cranberry | Vaccinii macrocarpi fructus | *Vaccinium macrocarpon* Aiton |
| 14 | Senna | Sennae folium | *Senna alexandrina* Mill. |
| 15 | Hawthorn | Crataegi folium cum flore | *Crataegus* spp. (EMA lists several species) |
| 16 | Ginkgo | Ginkgo folium | *Ginkgo biloba* L. — EMA inventory row shows no current outcome (revision in progress); include only if a final monograph is retrievable |

Black cohosh (#6) and hawthorn (#15) are deliberate stress tests for synonym handling and multi-species substances. Any mismatch found during ingestion will be recorded, not silently corrected.

**Pre-check (✔ tested 2026-11-02, WFO wrapper `/name/first_hit/`):** every botanical name above resolved to a WFO record with `status valid, role accepted`:
*Hypericum perforatum* 728093 · *Allium sativum* 757248 · *Echinacea purpurea* 36347 · *Panax ginseng* 263606 · *Valeriana officinalis* 426953 · *Actaea racemosa* 519114 · *Glycyrrhiza glabra* 212813 · *Curcuma longa* 365771 · *Silybum marianum* 14591 · *Serenoa repens* 309573 · *Zingiber officinale* 617397 · *Camellia sinensis* 582676 · *Vaccinium macrocarpon* 422267 · *Senna alexandrina* 164723 · *Crataegus monogyna* 1009785 (one of the hawthorn species) · *Ginkgo biloba* 795526.
The EMA name *Cimicifuga racemosa* resolves to WFO 604762 with `role synonym`. The `first_hit` response does **not** include the accepted-name ID, so synonym → accepted resolution needs a second lookup (WCVP `accepted_plant_name_id` or WFO name record). *Eleutherococcus senticosus* (948117, accepted) is confirmed as the second "ginseng" candidate for scenario D4.

Kava (*Piperis methystici rhizoma*) has only an EMA **public statement**, not a monograph. It is a good **safety-dashboard** example (hepatotoxicity concerns via NCCIH/LiverTox link) but not an interaction-module herb.

### 4.2 Drugs

Any drug name can be resolved through RxNorm at query time. Class-A coverage comes from EMA drug-class statements (mapped through ATC) and FDA label mentions. **Demo drugs:** warfarin, cyclosporine, tacrolimus, ethinylestradiol (oral contraceptives), digoxin, simvastatin, midazolam, sertraline, imatinib, indinavir.

---

## 5. Features — MoSCoW

### Must (MVP)

| ID | Feature | Module | Data |
|---|---|---|---|
| M1 | Plant search by common, botanical, or pharmaceutical name, with taxon resolution, synonym display and ambiguity handling | Herbal Knowledge Explorer | WFO, WCVP, curated name table |
| M2 | Plant detail page: identifiers (WFO, IPNI, GBIF, NCBI), EMA status, WEU vs. TU indications, contraindications, warnings, source links and dates | Explorer | EMA, WFO crosswalk |
| M3 | Herb–drug check: one herb + one or more drugs → class A–E per pair with evidence list, mechanism, conditions (dose/use category), source quotes | Interaction Intelligence | EMA §4.3/4.5, FDA labels, FDA CYP table, RxNorm/ATC |
| M4 | Evidence list per herb (and per pair): PubMed records with evidence type from MeSH publication types, year, link | Evidence Explorer | PubMed |
| M5 | Provenance panel on every finding: source, document ID, URL, retrieval timestamp, extraction method | All | Provenance store |
| M6 | AI Evidence Assistant: question → grounded answer with validated citations, explicit insufficient-evidence and referral behaviour | AI Assistant | Indexed monograph sections, label excerpts, NCCIH text, PubMed abstracts |
| M7 | Plain-language explanation of each interaction result ("what is known / not known / how strong / when to talk to a professional") | Patient Interface | Template-based + optional AI summary |
| M8 | Persistent disclaimer and referral prompts | All | — |
| M9 | Reproducible ingestion with raw snapshots and tests; Docker Compose start | Platform | — |

### Should

| ID | Feature |
|---|---|
| S1 | Safety Dashboard: per-herb CAERS report counts and top MedDRA reaction terms (non-causal framing), EFSA concern flags, data-coverage and freshness per source |
| S2 | ClinicalTrials.gov trial count and list per herb |
| S3 | Marker constituents (e.g., hyperforin) with ChEBI/PubChem IDs and mechanism links (PXR → CYP3A4) |
| S4 | Multi-drug check (medication list) in one request |
| S5 | Indication mapping of EMA monograph indications to MeSH ("monographs to clinical terms") |

### Could

| ID | Feature |
|---|---|
| C1 | Graph visualisation of herb → constituent → enzyme → drug paths |
| C2 | Europe PMC open-access full-text chunks in the RAG index |
| C3 | ICD-11 / ICPC-3 mapping (requires WHO API registration) |
| C4 | Conservation note (IUCN status) — "Best Community Impact" angle |
| C5 | Historical-claim comparison for one herb (Track 01 crossover) |

### Won't (this hackathon)

- Herbal product **recommender** (implies treatment advice — conflicts with safety principles).
- User accounts, saved medication profiles, any PHI storage.
- Photo-based plant identification.
- Computed severity scores or risk percentages.
- DrugBank-based features (licence).
- Coverage of all 251 EMA entries (the pipeline is designed for it, but the MVP curates 16).

---

## 6. Cut order if time runs short

1. C1–C5
2. S5, S4, S3, S2
3. S1 reduced to coverage/freshness only
4. M6 reduced to **extractive** answers (retrieved passages with citations, no generation)
5. Neo4j or any graph database is out from the start (see `technology-evaluation.md`)

M1–M5, M7–M9 are never cut — together they are the product.

---

## 7. Demo scenarios (to be verified in Phase 7)

| # | Scenario | Expected behaviour |
|---|---|---|
| D1 | St John's wort + warfarin | **Class A — documented.** EMA §4.5 (coumarin-type anticoagulants, WEU), with warfarin ∈ ATC B01AA; FDA label text where found; mechanism CYP induction; dose condition shown |
| D2 | St John's wort + a CYP3A4 substrate not named in EMA/FDA texts | **Class B — potential**, both premises displayed |
| D3 | Herb + drug with no findings (e.g., a curated herb with a drug outside its documented classes) | **Class D** with sources listed and "not proof of safety" |
| D4 | "ginseng" typed as free text | Disambiguation (*Panax ginseng* vs. *Eleutherococcus senticosus*); class **E** until resolved |
| D5 | Assistant: "Can I take St John's wort with my contraceptive pill?" | Grounded answer citing EMA/NCCIH, referral to a professional, no personal advice |
| D6 | Assistant: "How much valerian should I take to sleep?" | Declines dosing advice; points to monograph and professional |
| D7 | Plant search for a synonym (*Cimicifuga racemosa*) | Resolves to the accepted name with the synonym note |

---

## 8. Success criteria for the MVP

1. All demo scenarios D1–D7 behave as specified on a clean `docker compose up`.
2. 100% of displayed findings link to a provenance record.
3. 0 fabricated citations in the Phase 5 evaluation set (every citation resolves to a stored item).
4. The 16 curated herbs resolve to exactly one `wfo_id` each, or have a documented exception.
5. README lets a judge reproduce the data build and run the app.
