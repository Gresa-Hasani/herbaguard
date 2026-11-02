# Mechanism Paths and Class B (Phase 4)

**Status:** Implemented in `backend/src/herbaguard/domain/mechanisms.py` (pure, deterministic), applied by `services/mechanisms.py` and `services/interactions.py`. Tested by `tests/domain/test_mechanism_rules.py`, `tests/api/test_mechanisms_api.py`.

## 1. The knowledge graph

PostgreSQL edge tables (ADR-002), every row with provenance:

```
herbal_substance ──contains──> constituent            (herbal_substance_constituent)
herbal_substance ──induces/inhibits──> target          (target_modulation, herb level)
constituent      ──induces/inhibits──> target          (target_modulation, constituent level)
drug             ──substrate/inhibitor/inducer of──> target   (drug_target_role)
```

`target` = 18 enzymes and transporters (`data/curated/targets.yaml`; UniProt accessions verified).
Herb-side edges come from EU monograph section 4.5 sentences and from the FDA table's non-drug rows; drug-side edges from the FDA table. Each edge records the source's own potency category (never computed), conditions (use category, dose condition, FDA footnotes) and the citable `evidence_item`.

## 2. Rules: when a path supports class B

A **path** = one herb effect + one drug role on the same enzyme/transporter. All paths are returned to users; a path is **qualifying** only if all rules hold:

| # | Rule | Why |
|---|---|---|
| 1 | The effect is stated for the **herbal substance**, not a constituent | A constituent's effect (curcumin → BCRP) does not show that the herbal preparation has it |
| 2 | Herb-side evidence type is **REG or GOV**; sentences reporting in-vitro or animal findings are stored as INVITRO / ANIMAL and never qualify | Scientific principle 2 |
| 3 | The effect is **induction or inhibition** | Only these change a drug's exposure through the enzyme/transporter |
| 4 | The source does **not grade the effect as weak** | FDA weak = AUC change ≥1.25- to <2-fold (inhibitors) / ≥20 to <50 % (inducers) |
| 5 | The drug is a **substrate** (sensitive, moderately sensitive, or transporter substrate) according to the FDA table | A drug that is itself an inhibitor/inducer is not the "victim" of the herb's effect |
| 6 | **Same target**; CYP3A4/CYP3A5 match FDA's grouped CYP3A, nothing else is cross-matched | EMA names CYP3A4, FDA lists CYP3A |

## 3. Effect on classification

The decision order of `docs/api/interaction-classification.md` is unchanged. A qualifying path:

- gives **B / potential_interaction** only when no documented statement (class A) applies;
- ranks above class C findings (e.g. St John's wort + digoxin: NCCIH "conflicting evidence" would be C; the P-gp path gives B);
- adds the caveat: *"Mechanism-based finding: no source names this herb together with this drug … whether this changes the drug's effect, and by how much, is not known from these sources."*;
- is shown alongside "None reported" monograph statements as *"Sources differ: …"* (never silently overridden).

Non-qualifying paths are listed with `reasons_not_qualifying` and are never used for classification.

## 4. Endpoints

| Method & path | Purpose |
|---|---|
| `GET /api/v1/targets` | Enzymes/transporters with UniProt link and edge counts |
| `GET /api/v1/targets/{symbol}?role=&limit=` | Herb effects and drug roles for one target, each with provenance |
| `GET /api/v1/plants/{wfo_id}/mechanisms?include_drugs=` | Graph JSON (nodes: herb, constituent, target, drug; edges: contains, induces/inhibits, substrate_of) plus the herb's effect statements |
| `POST /api/v1/mechanisms/paths` | `{herb, drug, allow_remote_drug_lookup}` → every path with its rule assessment (POST because the body carries a medication name) |
| `POST /api/v1/interactions/check` | Each drug result now also has `mechanism_paths`; `sources_searched` lists the FDA table once ingested |

## 5. Known limitations

1. FDA lists examples; an unlisted drug may still be a substrate (stated in responses).
2. Herb-side recall is limited to the sentence forms in `normalize/mechanisms.py` (unused enzyme sentences are logged for review).
3. Size of effect is unknown for mechanism-only findings; dose and preparation conditions (e.g. hyperforin content) travel with the herb effect.
4. Transporter inhibitors are not graded by FDA (no potency).
