# EthnoHack 2026 — Requirements Analysis (Track 04)

**Project:** HerbaGuard
**Phase:** 0 — Research and Dataset Audit
**Date of analysis:** 2026-11-02
**Sources analysed (read in full):**

| File | Location at analysis time | Extent read |
|---|---|---|
| `EthnoHack 2026 Opening Ceremony.pptx.pdf` | `C:\Users\Admin\Downloads\` | All 26 slides (text extracted with `pdftotext -layout`) |
| `datasets_all_tracks.docx` | `C:\Users\Admin\Downloads\` | Full document: 9 sections, sponsor perks, responsible-use guidance, 142 numbered references and all embedded hyperlinks |
| Devpost page `ethnohack2026.devpost.com` | Fetched 2026-11-02 | Overview, requirements, "What to Submit", judging criteria, prizes, judges |

Devpost is the official submission platform, so its text is treated as organizer material **[ORG-DP]**. Where the slides and Devpost differ, Devpost is the more detailed and more recent source.

The source files are **not** stored in this repository (they are organizer material). This document quotes only short phrases and otherwise paraphrases.

> **Convention used below.** Every item is tagged:
> - **[ORG]** — stated explicitly by the organizers in the slides or catalogue.
> - **[INF]** — our inference from organizer material (reasonable, but not stated verbatim).
> - **[REC]** — our own architectural / product recommendation. Not an organizer requirement.

---

## 1. Event facts

| Item | Value | Tag |
|---|---|---|
| Event | EthnoHack 2026 — "Data Hackathon on Ethnopharmacology & Health" | [ORG] |
| Dates | 2–8 November 2026, 100% online, CET | [ORG] |
| Kick-off | Monday 2 Nov: 10:00 welcome, 10:30 track presentations, 11:00 team formation, 13:00 hacking begins | [ORG] |
| Build window | Monday–Saturday, own hours, any time zone; mentoring and Q&A on Discord all week | [ORG] |
| **Submission deadline** | **Sunday 8 November 2026, 10:00 CET** | [ORG] |
| Judging | One week of jury deliberation | [ORG] |
| Winners announced | Sunday 15 November 2026 | [ORG] |
| Organizer | ETHCSTWIN — Horizon Europe twinning project (June 2024 – May 2027), 5 partners in 4 countries | [ORG] |
| Consortium | IESP, National & Kapodistrian University of Athens (GR); Fraunhofer SCAI, Dept. of Bioinformatics (DE); Pangea Botanica / PangeAI (DE); University of Gastronomic Sciences, Pollenzo (IT); University of Prishtina, Dept. of Biology (XK) | [ORG] |
| Platform | Devpost: `ethnohack2026.devpost.com`; contact `ethnopharmacology@pharm.uoa.gr` | [ORG] |
| Devpost deadline display | "Nov 8, 2026 @ 11:00am EET" — identical to 10:00 CET | [ORG-DP] |
| **Registration cut-off** | "Official participant registration closes on Octomber [sic] 31 at 11:00 PM. Registrations after this time will not be eligible for judging or prizes." | [ORG-DP] |

**Implication [INF]:** at the time of this analysis (Monday 2 Nov) roughly **six calendar days** remain until the deadline. The nine-phase plan in the master prompt must be scoped to this window (see `mvp-scope.md`).

> **⚠ Action for the user:** confirm that you (and your team) were registered on Devpost before 31 Oct, 23:00. If not, contact the organizers immediately — this is outside the scope of engineering work but determines eligibility.

## 2. Overall hackathon objective

- Mission statement on the slides: turn traditional knowledge into evidence for drug discovery. [ORG]
- Motivation: plant knowledge is scattered (manuscripts, folklore, field notes, many languages, old plant names), at risk (fading traditions, harvesting pressure), and data methods (NLP, cheminformatics, maps) can link old remedies to compounds, targets and care. [ORG]
- Interdisciplinarity is emphasised: coders and plant scientists on the same team. [ORG]

## 3. Track 04 — Digital Health & Phytotherapy

| Item | Content | Tag |
|---|---|---|
| Track lead | Nektarios Aligiannis | [ORG] |
| One-line description | Apps and decision tools linking phytotherapy evidence to care | [ORG] |
| Guiding question | How to make phytotherapy knowledge usable, safe and evidence-based so it can be incorporated in health systems | [ORG] |
| Directions to spark ideas | (1) Herbal product recommender; (2) **Herb–drug interactions**; (3) **Evidence explained for patients**; (4) **Safety signal detection**; (5) **Monographs to clinical terms**; (6) Health providers education | [ORG] |
| Open data suggested on the Track 04 slide | EMA herbal monographs, WHO monographs, ICD-11, ICPC-3, ESCOP, DrugBank, OpenFDA, RxNorm, Kaggle/Hugging Face datasets | [ORG] |
| Freedom | Directions are "inspiration only"; own ideas welcome; tracks may be combined | [ORG] |

**Mapping of HerbaGuard to the Track 04 directions [REC]:**

| Organizer direction | HerbaGuard module | Coverage plan |
|---|---|---|
| Herb–drug interactions | Herb–Drug Interaction Intelligence | Core (P0) |
| Evidence explained for patients | Explainable Patient Interface + AI Evidence Assistant | Core (P0) |
| Safety signal detection | Safety Intelligence Dashboard (CAERS signal exploration, explicitly non-causal) | Core, limited (P1) |
| Monographs to clinical terms | Monograph → ICD-11 / MeSH / ATC mapping of indications and contraindications | P1 (MeSH/ATC first; ICD-11 needs API registration) |
| Health providers education | Professional view of the same evidence with citations | Partial, via evidence views |
| Herbal product recommender | **Deliberately not built.** A recommender implies treatment advice, which conflicts with our safety principles. | Excluded, documented rationale |

## 4. Deliverables (submission requirements)

All four items are due by **Sunday 8 Nov 2026, 10:00 CET**. [ORG]

| # | Deliverable | Organizer description | Tag |
|---|---|---|---|
| 1 | Devpost page | Title, description, team and track | [ORG] |
| 2 | GitHub repository | Code, notebooks and a clear README | [ORG] |
| 3 | Pitch video | 10 minutes: problem, approach, results, impact, demo | [ORG] |
| 4 | Slide deck | At most 10 slides | [ORG] |

### Detailed checklist from Devpost [ORG-DP]

1. **Devpost project page** must include: project title; selected challenge track; short description; problem statement; solution/approach; technologies used; **data sources**; results or prototype demonstration; team members; impact and future development.
2. **Source code** — link to a **public** GitHub repository containing: source code; data-processing scripts; model code/notebooks where applicable; **installation instructions**; README; **dataset references and licences**; instructions for reproducing the results where reasonably possible.
3. **Pitch video** — **maximum 10 minutes**: problem, motivation, approach, technology, data, results, demonstration, potential impact, future development.
4. **Slide deck** — **maximum 10 slides**: problem, methodology, results, demonstration, potential impact.

Recommended structure for judges: **Problem → Data → Method → Prototype → Results → Impact**. Teams should clearly identify assumptions, limitations, uncertainty and important data-quality issues. [ORG-DP]

What to build: a working prototype, pipeline, model, application, analysis or tool; explicitly allowed forms include web application, AI/NLP system, knowledge graph, dashboard, **decision-support prototype**, interactive database. Projects "do not need to be production-ready". [ORG-DP]

**Responsible Research** section [ORG-DP]: respect dataset licences and attribution, IP rights, privacy and personal-data protection, Indigenous and traditional knowledge considerations, scientific integrity, appropriate interpretation of computational predictions, responsible use of AI. "Projects must not present unvalidated computational findings as established medical facts."

Notes:
- The public-repository requirement means **no restricted data (DrugBank, UMLS, SNOMED, MedDRA, copyrighted abstracts/PDFs) may be committed**. [INF]
- The video is a **maximum** of 10 minutes (Devpost wording). [ORG-DP]
- Team size is 2–5 people, registered on Devpost with the track selected. [ORG] A solo entrant would need to confirm eligibility with organizers. [INF]
- The latest submission rules must be re-checked on Devpost before Phase 8 (see `api-audit.md` §3 for the Devpost page probe). [REC]

## 5. Judging criteria

Explicitly listed on the deliverables slide [ORG]:

1. Scientific relevance
2. Innovation
3. Technical quality
4. Data science
5. Feasibility
6. Impact
7. Presentation

No weights were published in the material reviewed. [ORG — absence noted]

Devpost defines each criterion [ORG-DP]:

| Criterion | Devpost definition | How HerbaGuard addresses it [REC] |
|---|---|---|
| Scientific Relevance | Does the project address a genuine ethnopharmacology or health challenge? | Herb–drug interactions are a recognised patient-safety problem; EMA monographs contraindicate specific drug classes |
| Innovation | Is the approach novel? Does it use data in a creative way? | Combines herb-side (EMA) and drug-side (FDA label) regulatory evidence with a mechanism layer and literature, in one graded view |
| Technical Implementation | Quality of code, model or tool — reproducibility and documentation | Tested ingestion pipeline, snapshots, Docker, CI |
| Data Science Quality | Appropriate methods, validation, handling of uncertainty | Evidence-level taxonomy, explicit "no evidence found ≠ safe", RAG evaluation set |
| Feasibility | Is the solution realistic and scalable beyond the hackathon? | Source connectors generalise from the curated herb set to all 251 EMA entries |
| Impact | Potential benefit to conservation, sustainability, drug discovery or public health | Patient and pharmacist safety |
| Presentation | Clarity of the pitch, slides and demo | Phase 8 |

### Prizes

- Track prizes: one first prize per track, **€2,000 in cash** per winning team; total "€8,000+ in prizes". [ORG-DP]
- Special category awards open to all tracks [ORG]: Best AI Solution; Best Student Team; **Best Scientific Rigor** ("most thorough design and data validation"); Most Innovative Application; Best Community Impact; Best Collaboration.

**Implication [REC]:** HerbaGuard's emphasis on provenance, evidence grading and validation is a natural fit for *Best Scientific Rigor* and *Best AI Solution*, in addition to the Track 04 prize.

## 6. Organizer guidance, constraints and recommendations

From the dataset catalogue and slides:

| Topic | Guidance | Tag |
|---|---|---|
| Catalogue status | "Just a proposal" — teams are not limited to listed resources | [ORG] |
| Historical claims | User-facing prototypes should show a clear warning that historical/traditional claims are not established efficacy or safe medical advice; do not derive modern dosing from historical quantities; do not encourage preparing or ingesting remedies | [ORG] |
| Evidence vs. assays | An assay result does not establish efficacy of a plant preparation; a historical use does not establish safety | [ORG] |
| Spontaneous reports | openFDA CAERS reports are not proof of causation; map products to taxa with care | [ORG] |
| Plant identifier | WFO is recommended as the primary plant identifier (`wfo_id`); record IPNI IDs alongside | [ORG] |
| Cross-backbone checking | Store WFO IDs, GBIF taxon keys and Catalogue of Life IDs where possible | [ORG] |
| Vernacular names | GBIF / Wikidata vernacular names are not proof that a term refers to a taxon | [ORG] |
| Licensing | Record rights at item level; public viewing ≠ permission for bulk redistribution or model training; prefer PD/CC0/CC BY; keep `rights_uri`, attribution, source URL, retrieval date per item | [ORG] |
| UMLS / SNOMED / MedDRA | Do not bundle UMLS-derived files in a public repo without checking each source restriction; UMLS access does not lift SNOMED/MedDRA restrictions | [ORG] |
| RxNorm / ATC | Use only for modern medicinal products or normalized drug ingredients, not for unstandardised historical preparations | [ORG] |
| DrugBank | Free for academic non-commercial use with registration; check licence before redistribution | [ORG] |
| Community rights | Nagoya Protocol; avoid newly collected or community-restricted knowledge without permissions; Local Contexts TK/BC Labels and Notices | [ORG] |
| Provenance standards | PROV-O for provenance; SKOS mapping properties for uncertain mappings; Dublin Core / DataCite for metadata | [ORG] |
| Live dependencies | (For historical corpora) freeze item identifiers and downloaded files before the event; avoid live dependence on fragile endpoints | [ORG] — we generalise this to all sources [REC] |
| Mentors | Mentors guide, they do not write code; reply within ~12 hours | [ORG] |
| Hosted APIs | Seven ETHCSTWIN-hosted wrappers (WFO, IPNI, WCVP, COCONUT, BRENDA, ChEBI, TaxTree) are explicitly "not the official service"; each can export RDF/Turtle and import into Neo4j | [ORG] |

## 7. In-kind sponsor tools

| Sponsor | Offer | Relevance to HerbaGuard | Tag |
|---|---|---|---|
| Anakin | One free month of the $20 plan; turns websites into structured APIs | Possible for EMA/NCCIH page extraction, but scraping must respect each site's terms; not required for the MVP | [ORG] / [REC] |
| Aitho | Presenter Pro free until 31 Dec; pitch rehearsal | Phase 8 pitch practice | [ORG] / [REC] |

## 8. What the organizers did **not** specify

The following are **not** organizer requirements; any choice here is ours [REC]:

- Technology stack, programming language, hosting, or deployment.
- Whether a live demo URL is required (only a video demo is stated).
- Whether AI/LLMs must be used.
- A required data model, ontology, or graph database.
- Licensing of the submitted code.
- Judging weights.

The FastAPI / PostgreSQL / React / Neo4j stack in the master prompt is therefore a team choice, evaluated in `technology-evaluation.md`.

## 9. Judges listed on Devpost [ORG-DP]

Judges include Nektarios Aligiannis (Scientific Director of IESP; Professor of Pharmacognosy and Natural Products Chemistry, NKUA — also the Track 04 lead), Petros Bouras-Vallianatos (History of Science, NKUA), Dimitrios Gunopulos, Antigoni Cheilari (pharmacist, postdoctoral researcher in pharmacognosy, NKUA), and Mehmet Can Ay (Fraunhofer SCAI, Biomedical Data Intelligence); the list may continue beyond what was captured.

**Implication [INF]:** the jury is strongly pharmacognosy-oriented. Pharmacognosists will notice imprecise use of herbal-substance terminology (plant part, preparation, WEU vs. TU), so HerbaGuard must model these correctly.

## 10. Open questions to raise with organizers (Discord `#event-questions` / `#track-4`)

1. Is a solo or 2-person team eligible, and was registration completed before the 31 Oct cut-off?
2. Is a deployed demo expected, or is the video sufficient?
3. Are the ETHCSTWIN wrappers guaranteed to stay online during the judging week (until 15 Nov)?
4. What are the licence terms for the data served by the ETHCSTWIN wrappers (particularly BRENDA and COCONUT subsets)?
5. Are there any Track 04 datasets prepared by the organizers (e.g., a structured extract of EMA monographs)?
