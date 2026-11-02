# Herb–Drug Interaction Classification (classes A–E)

**Status:** Implemented in Phase 3 — `backend/src/herbaguard/domain/interactions.py` (pure, deterministic), applied by `services/interactions.py`, exposed by `POST /api/v1/interactions/check`. Tested by `tests/domain/test_interaction_rules.py` and `tests/api/test_interactions_api.py`.

**No language model, machine-learning model or scoring function decides a classification.** The class is the result of the fixed rules below, applied to stored, provenance-tracked statements. The same inputs always give the same output.

## 1. Inputs

| Input | Where it comes from |
|---|---|
| Herb | Free text resolved to one curated herb (all species sharing an EMA pharmaceutical name, e.g. *Crataegi folium cum flore* = 4 *Crataegus* species). Ambiguous names → HTTP 409 with candidates. |
| Drug | Name, brand name or RxCUI resolved to one RxNorm ingredient (database first; optionally RxNav live, recorded with provenance). |
| Statements | Active (`status = active`) interaction statements from Phase 2 for the herb's substances that name **the drug**, or **an ATC class containing the drug** (all ancestor codes of the drug's ATC classes, e.g. warfarin B01AA → B, B01, B01A, B01AA). Superseded statements are never used. Statements repeated for several species of one herb are merged. |
| Herb-level "None reported" | EMA monograph §4.5 sections whose whole text is "None reported/known" (stored at section level in Phase 2). |
| Mechanisms | Phase 4: herb → enzyme/transporter effects (EMA monograph 4.5 sentences, FDA table) joined with drug roles (FDA CYP/transporter table) on the same target. Only *qualifying* paths are used — rules in [mechanism-paths.md](mechanism-paths.md). |

Each statement carries its **statement type** (Phase 2, deterministic sentence cues): `interaction`, `precaution`, `uncertain`, `unclassified`, `no_interaction_reported`; and its **evidence type**. Only `REG` (EMA monographs, FDA labels) and `GOV` (NCCIH) are *authoritative*.

### Label subject check

FDA labels are about the label's drug, but a label sentence can be about something else (real example, isotretinoin label: *"…a possible interaction has been suggested with hormonal contraceptives…"*). A label statement is **subject-verified** if the sentence names the label's drug (ingredient, first word of the generic or brand name) **or** it is in the label's `drug_interactions`, `contraindications` or `boxed_warning` section. Otherwise (`warnings`, `warnings_and_cautions`, `precautions` without naming the drug) it is **context only**. Every statement in the API shows `subject_check` and a note.

## 2. Decision order (first rule that applies wins)

| # | Class | Finding | Criterion |
|---|---|---|---|
| 1 | **E** | `insufficient_information` | The herb or the drug could not be identified. |
| 2 | **A** | `documented_interaction` | ≥ 1 authoritative, subject-verified statement of type `interaction` naming the drug or a **whole** ATC class containing it. |
| 2 | **A** | `documented_precaution` | As above, but all such statements are of type `precaution` (caution/monitoring advised, no effect asserted). |
| 3 | **B** | `potential_interaction` | Authoritative interaction/precaution statements exist only for **part** of a class the drug belongs to (Phase 2 marker "Applies to part of the class only", e.g. *"other cytostatic agents metabolised by CYP3A4"*, *"Certain statins"*), or a mechanism path exists (Phase 4). |
| 4 | **C** | `uncertain_evidence` | A source itself calls the evidence conflicting or unclear (NCCIH cranberry: *"There is conflicting evidence about whether cranberry interacts with … warfarin"*). |
| 4 | **C** | `label_subject_not_confirmed` | Only label statements with interaction/precaution wording whose subject is not verified (see above). |
| 4 | **C** | `mentioned_without_interaction_wording` | Only `unclassified` statements (the herb is named without interaction wording). |
| 5 | **E** | `insufficient_information` | No source covering the herb was searched. |
| 6 | **D** | `no_interaction_reported` | A source explicitly reports no interaction for the pair, **or** the herb's EMA monograph §4.5 states "None reported/known" (quoted with document number, use category and date; it applies to the herbal substance as a whole). |
| 6 | **D** | `no_evidence_found` | Nothing above applies. |

What each finding means for users is returned in `classification.explanation`; reasons specific to the case in `classification.reasons`.

## 3. Safety rules built into the output

- **No "safe" field, ever.** Classes D and E always carry the caveat *"An absence of reported interactions is not evidence that a combination is safe."* D explanations state that sources may be incomplete.
- **Severity is never computed.** `severity_wordings` relays the verbatim wording of decisive statements (e.g. "is contraindicated", "should be avoided"); for EMA §4.3 statements the heading "Contraindications" is relayed.
- **Context is never promoted.** `unclassified` and subject-unverified label statements can never produce class A; they appear as context or as the decisive statements of a class-C finding, labelled as such.
- **Disagreement is shown, not resolved.** If an herb's monograph says "None reported" but other sources give A, B or C, a caveat *"Sources differ: … None reported …"* is added.
- **Conditions travel with the statement**: EMA indications and dose thresholds (e.g. *"Indications 1), 3) and 4); Daily dose of hyperforin > 1 mg"*) and use category (well-established vs traditional use) are on each statement.
- **Literature is not used for classification.** PubMed records are linked to herbs, not drug pairs; they are reported as `related_literature` with `used_for_classification: false`. Evidence type is study design, not quality (`quality_assessed: false`).
- Every result carries the medical-advice caveat.

## 4. Behaviour on the real Phase 2 data (2026-11-02)

All 156 herb–drug pairs that have at least one drug-level statement, classified through the service:

| Class | Finding | Pairs |
|---|---|---|
| A | documented_interaction | 146 |
| A | documented_precaution | 1 |
| C | label_subject_not_confirmed | 7 |
| C | mentioned_without_interaction_wording | 2 |

Paired with a drug without statements (metformin): 9 herbs → `no_interaction_reported` (EMA §4.5 "None reported/known"), 7 herbs → `no_evidence_found`.

Representative verified scenarios (live API against the development database):

| Herb + drug | Result | Basis |
|---|---|---|
| St John's wort + warfarin (also brand "Coumadin" via live RxNav) | A documented_interaction | EMA §4.3/§4.5 for ATC B01AA ("coumarin-type anticoagulants … is contraindicated"), NCCIH, FDA labels |
| St John's wort + atorvastatin | B potential_interaction | NCCIH "Certain statins, including simvastatin" (partial class C10AA) |
| St John's wort + isotretinoin | C label_subject_not_confirmed | Isotretinoin label sentence about hormonal contraceptives |
| Cranberry + warfarin | A documented_interaction | EMA §4.3/§4.5 ("should be avoided"); NCCIH uncertain statement as context |
| Hawthorn + warfarin | D no_interaction_reported | EMA/HMPC/159075/2014 §4.5 (traditional use, 2016-04-05): "None reported." |
| *Cimicifuga racemosa* (synonym) + tamoxifen | D no_interaction_reported | Resolved to *Actaea racemosa*; EMA §4.5 "None reported" |
| Unknown herb / unknown drug | E insufficient_information | — |

## 5. Known limitations of the rules

1. **Conservative label rule.** 7 pairs move from A to C because their label sentences sit in general warning sections without naming the drug. One is the isotretinoin error the rule was written for; the others (St John's wort with lithium, meperidine, methamphetamine, lisdexamfetamine; echinacea with nimodipine) are probably genuine statements about the label drug that are now under-classified. The sentence remains visible as the decisive statement of the C finding.
2. **Mechanism-based class B** (Phase 4) depends on FDA's example lists and on recognised monograph sentence forms; see [mechanism-paths.md](mechanism-paths.md) §5. The Phase 3 real-data counts in §4 predate Phase 4.
3. **Class granularity** depends on RxClass ATC level (mostly level 4); a statement about a level-5 code would not match a level-4 membership.
4. **Statement types come from Phase 2 sentence rules** (lexicon-bound recall); see `docs/data/pipeline.md` §3.3.
5. **Ambiguity is only detectable within the curated herb set**: "ginseng" resolves to *Panax ginseng* because *Eleutherococcus senticosus* is not curated; the response warns that a common name was matched.
