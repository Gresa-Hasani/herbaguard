# HerbaGuard — Phase 4 Completion Audit and Targeted Completion

**Date:** 2026-11-03. **Audited state:** `origin/main` = `3314e34` (merge of PR #1, `phase-4-mechanisms`: commits `911e71d`, `a429d25`), compared with the Phase 3 baseline `930af5b`.

The full audit request (sections 1–10: original Phase 4 scope, repository inspection, requirement-by-requirement audit, scientific verification, A–E integration check, real validation, outcome decision, rules for completion work, Git restrictions, report format) was given in chat on 2026-11-03. This file records the audit baseline and the completion tasks derived from it.

## Audit baseline (original Phase 4 scope)

1. Integrate authoritative CYP450 enzyme and transporter datasets (CYP3A4, 2C9, 2C19, 2D6, 1A2, 2E1 as examples; P-gp/ABCB1, BCRP/ABCG2, OATP1B1, OATP1B3).
2. Traceable relationships herb → compound → enzyme/transporter ← drug, each with provenance, source reference, evidence, evidence type, extraction metadata and uncertainty where available.
3. Mechanism-based graph queries: enzymes of a herb; compounds of an enzyme; drugs sharing an enzyme; herbs and drugs sharing a documented pathway; herb–drug pairs with mechanism evidence; relationships based only on in-vitro evidence; graph paths with insufficient or conflicting evidence. PostgreSQL unless a graph database is justified by an ADR.
4. Mechanism analysis distinguishing: mechanistically supported potential interaction; experimental/in-vitro mechanism evidence; insufficient mechanism evidence; conflicting mechanism evidence; no documented mechanism found. Shared enzyme membership, two substrates of one enzyme, or in-vitro inhibition alone never establish an interaction; substrate/inhibitor/inducer never confused; missing relationships never mean safety.
5. A–E integration: `domain/interactions.py` stays authoritative; explicit, deterministic class-B eligibility; provenance; explained graph relationships; clinical vs experimental distinction; no unsupported upgrades; Phase 3 regressions preserved; no LLM.
6. Repositories, services, schemas, endpoints, data-quality reports, tests, documentation and ADRs.

Note: `prompts/phase-4-knowledge-graph-and-mechanisms.md` records that the implementing session received only sections 1–3 of the Phase 4 prompt. Requirements 3 (most graph queries), 4 (the five mechanism outcomes) and parts of 6 were therefore not in the prompt it worked from.

## Completion tasks (from the audit)

Critical:

1. **Explicit mechanism outcome** for every herb–drug pair (interaction check and `POST /mechanisms/paths`): mechanism-supported / experimental only / conflicting / insufficient / no documented mechanism found / not assessed (herb or drug not identified). Deterministic, in `domain/mechanisms.py`, with explanations that never imply safety. The paths endpoint must no longer show the mechanism-finding caveat when there is no path.
2. **Conflicting mechanism evidence**: opposite authoritative effects (induction and inhibition) of one herb on the same enzyme/transporter are detected; such paths never qualify for class B and are labelled.
3. **Prodrug name mismatch**: FDA lists "dabigatran etexilate"; users enter "dabigatran" (different RxNorm ingredient), so St John's wort + dabigatran returned "no evidence found". Add an explicit, curated FDA name alias with provenance.

Important:

4. **Uncertainty of herb-side wording**: record hedged wording ("may inhibit") with the edge (migration 0004), show it in every path, effect and reason.
5. **Data-quality logging**: EU monograph sentences that name an enzyme/transporter but have no recognised effect verb (e.g. "might affect the activity of CYP3A4", "because of induction of CYP3A4") are logged as `ema_mechanism_sentence_not_used`, as the documentation already claims.
6. **Graph queries**: filterable herb-effect listing (by target, evidence type, effect, subject kind, herb) — answers "compounds for an enzyme" and "relationships based only on in-vitro evidence"; herb–drug pairs with mechanism paths for one herb, with their outcome.

Optional:

7. Herb graph: link EMA's CYP3A4/CYP3A5 nodes to FDA's grouped CYP3A node, so the graph shows the match the rules use.

Rules: implement only these; keep Phase 1–4 behaviour otherwise; tests for every fix; update documentation; rerun validation. No commit, no push. Do not start Phase 5.
