# SUPP.AI (P2) Post-Implementation Audit — 2026-11-07

Branch `feat/dataset-expansion`, uncommitted P2 code. Read-only audit: no database writes, imports, prompt or validator changes, and no model calls. Measurements use the real database. Context assembly ran with a scripted provider and was rolled back; the validator was probed with constructed items.

Supp.AI is `to_verify` and not redistributable. This report quotes only short fragments and gives PMIDs.

## Summary

| # | Issue | Severity |
|---|---|---|
| 1 | The reserved U# slots displace decisive statements and mechanism paths | **High** |
| 2 | The negation flag has no scope: most flagged sentences report an effect for the pair | **High** |
| 3 | Non-human mentions can still be presented as clinical or human evidence | Medium |
| 4 | Many mentions do not support the specific pair (lists, extraction errors) | Medium |
| 5 | "No interaction" conclusions from mentions can pass the validator | Medium |
| 6 | Mapping coverage is low; salt names and product names are missed | Low (no safety impact) |
| 7 | Licensing: the guard works; verbatim text reaches API users; one doc quote | Low |

**Verdict:** a limited local generation evaluation would be *safe*: nothing leaves the machine, the A–E class is unaffected, and nothing is user-facing. It is **not recommended before fixing 1 and 2**. Otherwise the evaluation would mostly re-measure these known defects, and issue 2 can steer answers toward understating real interactions. The RAM limit from the LiverTox evaluation still applies.

## 1. Context-slot competition — High

**How it works.** `assemble()` fills the reserved kinds in pass 1, before any other evidence: X# 2, H# 2, U# 2. Pass 2 then fills the rest by priority, up to 8 items and 2,600 tokens. Reserved U# items are therefore taken *before* decisive statements (priority 5), even though they rank lower. The Supp.AI summary fact is not reserved, but its priority (27) beats excerpts ranked 27 and below. U# items are long (about 150–250 tokens), so they also use up the token budget.

**Measured.** All 97 pairs with eligible mentions were assembled with and without U# items.

| Effect | Pairs |
|---|---|
| Something displaced | 96 / 97 (177 items) |
| Excerpts displaced (EMA, PubMed, FDA labels, NCCIH) | most of the 177 |
| **Decisive statement displaced** | **5**: St John's wort + warfarin, cyclosporine, amitriptyline, paroxetine, fluoxetine |
| Mechanism path displaced | 1 (St John's wort + warfarin: "induces CYP2C9") |
| DDID X# displaced | **0** |
| Context ended by the token budget instead of the item limit | 5 with U#, 2 without |

Example: for St John's wort + cyclosporine, the FDA label statement "reports of a serious drug interaction" is dropped in favour of two U# mentions.

DDID is not affected because it has its own two slots. In 8 pairs that have more than 2 DDID records, the third and fourth records are never shown, with or without Supp.AI.

**Recommended source priority** (no safety rule weakened):
1. Classification (C#), always.
2. Decisive statements and mechanism paths from the interaction service. Take these **before** any reserved external kind.
3. DDID X# (keep 2 reserved) and LiverTox H# (liver questions only, keep 2 reserved).
4. Retrieved excerpts.
5. Supp.AI U#: **no reserved slot**. Use a low priority (e.g. 40+), a cap of 1–2, and include them only when free slots and tokens remain. Put the counts into U1's text, or give the summary fact a priority below every excerpt.

## 2. Negation detection — High

Of the 1,658 stored sentences, 236 are flagged; of the 350 eligible sentences, **25** are flagged. I read all 25 against their pair:

| What the sentence says about *this* pair | n | Examples (PMID: fragment) |
|---|---|---|
| Reports no effect | **2** | 9032623 (garlic + nifedipine: "but not nifedipine"); 20345351 (garlic + docetaxel: reduction "did not achieve statistical significance") |
| Reports an effect; the negation is about another drug or herb | 13 | 15916450 (St John's wort decreased ciclosporin, midazolam, tacrolimus…, "but did not alter" carbamazepine…); 24472406 (increased midazolam clearance, "failed to alter" bosentan); 17050802 (St John's wort increased S-warfarin clearance; "ginkgo and ginger did not affect"); 23033232 (St John's wort may decrease INR; nicotine "is not known to alter") |
| A warning that implies an interaction | 6 | 17578477 ("not recommended" with bupropion); 21142266 (etravirine); 17846933 (simvastatin); 9818800 ("should not be used" with warfarin); 19717088 (irinotecan, "without compromising"); 12649774 (methadone) |
| Uncertainty or method | 2 | 21803754 ("has not been studied"); 12580992 ("should not be extrapolated") |
| Partial or mixed effect | 2 | 3368525 ("partially antagonized … but did not suppress"), shared by 3 senna pairs |

**Consequences**
- The qualifier tells the model the sentence "may report that NO interaction or effect was found; never read it as evidence of an interaction". That is wrong for about 21 of the 25 sentences. It points toward **understating real interactions**, such as St John's wort + cyclosporine or tacrolimus.
- `negated_mention_as_positive` removes correct paragraphs. Probe: "…reports that St John's wort increased S-warfarin clearance", citing PMID 17050802, is removed.
- Real false positives outside the eligible set: "not only … but also" (13 sentences).

**Missed negations** (no-effect wording not caught): none found in the eligible set. Candidates such as "comparable", "little effect" and "minimal effect" only describe a sub-finding in the sentences found (e.g. 21969792 "minimal effect on gastric emptying"). In principle the word list misses "comparable", "similar" and "negligible".

## 3. Study classification — Medium

**Eligible flag combinations** (clinical, human, animal):

| Flags | Sentences |
|---|---|
| human only | 195 |
| animal and human | 69 |
| none | 34 |
| animal only | 32 |
| clinical and human | 19 |
| clinical and animal, no human (conflicting) | 1 |

**Confirmed problems**
- **Conflicting dog study (PMID 22091645, St John's wort + cyclosporine).** It is labelled *conflicting* and "NOT human clinical evidence". But the item text shows `clinical_study=true`, and the validator **accepts** "A clinical study found…" and "In a clinical trial, …" citing it. `_CLINICAL_CLAIM` does not cover "clinical study" or "clinical trial", and `supp_ai_mention_as_confirmed` does not either.
- **In-vitro human-cell studies are flagged as human studies** (≥10 eligible records). Examples: 21138349 (HepG2 monolayers), 11739235 (in-vitro P-gp induction), 16203790 (human hepatocyte cultures), 12215688 (LS180 cells). They are labelled "human study, not flagged as a clinical study", and the validator **accepts** "In patients, St John's wort increases docetaxel metabolism" citing one of them.
- **Mixed citations escape both rules.** A paragraph citing a label statement S# and an animal U# with "…in patients" is accepted: `experimental_as_clinical` needs *all* citations to be non-human, and `mention_issue` needs mention-only evidence.
- **What works:** an animal U# alone with "in humans" or "in patients" is removed (`experimental_as_clinical`), and an animal U# described with hedging is accepted.
- **Irrelevant papers with no flags** (34 eligible) are labelled "not stated", which is correct but uninformative. Examples: 12588248, a news item about a WHO appointment; 30169119, bacterial isolates.

## 4. Mapping coverage — Low

| Measure | Value |
|---|---|
| Eligible sentences (both entities resolved, not retracted, with paper) | 350 of 1,658 |
| Lost to candidate or ambiguous herbs | 241 |
| Lost to unresolved drugs | 447 |

**Herbs** (sentences with a resolved drug / distinct resolved drugs):

| Supp.AI entity | Status | Sentences / drugs |
|---|---|---|
| Ginseng | ambiguous | 88 / 17 |
| Ginkgo Biloba Whole | candidate | 57 / 20 |
| Green Tea Extract | candidate | 52 / 22 |
| Licorice | ambiguous | 19 / 12 |
| Black Cohosh Extract | candidate | 11 / 5 |
| Echinacea | candidate | 11 / 7 |
| Saw Palmetto, Turmeric, Milk Thistle Extract | candidate | 1 each |

- Curated herbs with no resolved Supp.AI supplement: black cohosh, cranberry, ginkgo, ginseng, hawthorn, liquorice, milk thistle, saw palmetto.
- Resolved but contributing nothing: Echinacea Purpurea, Crataegus Azarolus and Garden Heliotrope have no sentences. Curcuma Longa (23) and Valeriana Officinalis (11) have no sentence with a resolved drug.

**Drugs** (sentences with a resolved herb):
- *Not drugs*, so unresolved is correct: nitric oxide 37, serotonin 23, "Hiperforina" (hyperforin, a constituent) 19, norepinephrine 12, hypericin 10, hydrogen peroxide 9.
- *Drugs missing from the 349-drug index:* indomethacin 10, insulin 9, ampicillin 8, morphine 7, acetaminophen 6, cyclophosphamide 5.
- *Salt-form name:* "Doxorubicin Hydrochloride" (16) is unresolved although doxorubicin is in the index.

## 5. Evidence attribution — Medium

Heuristic over the 350 eligible sentences:

| Pattern | Eligible | Among the 178 that can be shown (top 3 per pair) |
|---|---|---|
| Names 3+ indexed drugs | 149 | |
| Names 2+ curated herbs | 52 | |
| List sentence (4+ commas) | 160 | |
| Any of the three above | 190 (54%) | 86 |
| Review-type paper title | 137 | 61 |

- **Lists:** e.g. 10920504 names 11 herbs that "reinforce warfarin action"; 28188296 gives garlic, ginkgo and St John's wort together; 12588248 is a news item listing four drugs.
- **Confirmed extraction errors** (the sentence cannot support the pair):
  - 31752309, garlic + aminolevulinic acid: the tagged herb is "P. sativum" (pea), not garlic.
  - 30169119, garlic + rifampin: bacterial isolates from garlic chives resistant to rifampin.
  - 33638666, garlic + ciprofloxacin: antibacterial synergy, not a drug interaction in people.
  - 25233607, green tea + warfarin: the tagged herb is the word "sinensis" in a list that also contains *Angelica sinensis*.
  - 19126824, green tea + warfarin: about black tea. Same species, but a different product.
- **Shifted spans:** 5 of 350 eligible (19 of 1,658 overall) have argument spans that land mid-word. "Terms tagged by SUPP.AI" then shows fragments such as 'lic no' (12580992) or ' co' (12580993).
- Legitimate abbreviations (AGE, ASE, GE, HP, IHp) are tagged correctly.

## 6. Absence of evidence — Medium

- "SUPP.AI found no interaction between ginger and cyclosporine", citing a U#, is **accepted**.
- "…did not affect warfarin pharmacokinetics, so there is no interaction", citing the mixed sentence 17050802, is **accepted**. The pre-existing `_SAFE` check skips a match when negation appears earlier in the sentence.
- The unattributed "There is no interaction…" is rejected (`safety_claim`).
- In context, the no-eligible-mention fact is worded correctly ("does not show that no interaction exists").

## 7. Licensing — Low

- `source.supp_ai`: `to_verify`, not redistributable. Unchanged.
- Cloud guard: a cloud provider is refused unless `ai_cloud_send_source_text=true`. With it, U# items are excluded (`redistributable=False`). `data/raw/*` is git-ignored.
- **Open:** cited U# sentences are returned verbatim in API citations (`excerpt`) and shown to end users. DDID is handled the same way. This is acceptable for local use, but needs a decision before any public deployment.
- **Before committing:** `docs/data/external-datasets.md` §7 quotes a 9-word Supp.AI sentence fragment. Paraphrase it. This report quotes only short fragments.

## Recommended corrections, by impact

1. **Slots (fixes 1).** Remove `mention` from `RESERVED_SLOTS`. Take decisive statements and mechanism paths before the reserved kinds. Give U# priority 40+ with a cap of 1–2, and lower or merge the summary fact. Add a regression test: St John's wort + cyclosporine must keep the FDA statement.
2. **Negation scope (fixes 2).**
   - Only flag a cue that is in the same clause as the pair's tagged drug span. Split clauses on `;`, "but", "whereas", "however".
   - Treat "should not be used", "not recommended", "cannot be given … without" as a separate **warning** label, not negation.
   - Ignore "not only".
   - Reword the qualifier to "contains negation wording; check which substance it applies to".
   - Apply `negated_mention_as_positive` only to clause-scoped negation.
   - Add the 25 reviewed cases as synthetic test fixtures.
3. **Study claims (fixes 3).**
   - Add "clinical study", "clinical trial", "human study", "in volunteers" and "in patients" to the clinical-claim check for non-clinical U#.
   - Require a clinical claim to have at least one clinical C#, S#, E# or X# item among its citations, which covers mixed citations.
   - Do not show `clinical_study=true` for *conflicting* items.
   - Deterministically downgrade "human" to "in-vitro or animal wording in the title" when the title or sentence names cells, hepatocytes, microsomes, in vitro, rats, mice or dogs.
4. **Absence (fixes 5).** Treat "no interaction" or "does not interact" as critical when the paragraph's evidence is only Supp.AI, attributed or not. Review the `_SAFE` negation guard, which is pre-existing behaviour.
5. **Attribution (fixes 4).**
   - Add a "names N herbs/drugs; may not be specific to this pair" qualifier, and rank specific sentences above list sentences.
   - Keep a reviewed exclusion list for confirmed extraction errors (the 4 PMIDs above).
   - Omit "Terms tagged" when a span is misaligned.
6. **Coverage (fixes 6).** Reviewed name entries only, no fuzzy matching:
   - Green Tea Extract, Ginkgo Biloba Whole, Black Cohosh Extract, Milk Thistle Extract, Saw Palmetto Extract and Turmeric Extract, each with an "extract product" note.
   - Reviewed salt-form drug synonyms, e.g. Doxorubicin Hydrochloride.
7. **Licence (fixes 7).** Paraphrase the doc quote before committing, and decide on API exposure before any deployment.

Audit scripts (scratchpad, not part of the repository): `slots.py`, `negation.py`, `neg_list.py`, `validator_probe.py`, `attribution.py`, `spans.py`.
