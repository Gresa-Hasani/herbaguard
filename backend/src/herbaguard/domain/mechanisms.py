"""Mechanism paths: herb → enzyme/transporter ← drug, and when they may support class B.

Pure functions: no database, no network, no LLM. Documented for users in
``docs/api/mechanism-paths.md``; tested in ``tests/domain/test_mechanism_rules.py``.

A *path* joins one stored herb effect (``target_modulation``: the herb, or one of its
constituents, induces or inhibits an enzyme/transporter) with one stored drug role
(``drug_target_role``: the drug is a substrate, inhibitor or inducer of the same
enzyme/transporter). Every path is shown to users. Only a path that meets **all** rules below is
*qualifying* and may produce class B ("potential interaction, based on mechanism"):

1. **Herb-level effect.** The effect is stated for the herbal substance itself. Effects stated for
   a constituent (e.g. curcumin, listed by FDA as a BCRP inhibitor) are context only: a
   constituent's effect does not show that the herbal preparation has it at the amounts it
   contains.
2. **Authoritative herb-side source.** Evidence type REG or GOV (EMA monograph, FDA table). In-vitro
   or animal findings never qualify (scientific principle 2).
3. **Induction or inhibition.** Other effects (activation, "other") are context only.
4. **Not weak.** Effects the source itself grades as *weak* are context only (FDA: weak inhibitor
   = AUC increase ≥1.25- to <2-fold; weak inducer = AUC decrease ≥20 to <50 %).
5. **The drug is the victim.** The drug's role is a substrate role (sensitive, moderately
   sensitive, or transporter substrate) from an authoritative drug-side source (FDA table). A drug
   that is itself an inhibitor or inducer of the same enzyme does not form a herb → drug exposure
   path.
6. **Same enzyme or transporter.** CYP3A4 and CYP3A5 match FDA's grouped "CYP3A"; no other
   cross-matching is done.

7. **No conflicting statement.** If authoritative sources state both induction and inhibition of
   the same enzyme/transporter for this herb, the net effect is unknown: paths on that target are
   marked *conflicting* and do not qualify.

A qualifying path never yields class A, never overrides a documented statement, and its size of
effect is unknown — this is stated in every result. A source's hedging word ("may inhibit") is
kept with the effect and shown; it does not change the rules (class B already means *potential*).

Every herb–drug pair also gets one **mechanism finding** (``assess_mechanism``), so users can tell
apart: a mechanism-supported potential interaction; experimental (in-vitro/animal) evidence only;
conflicting evidence; insufficient evidence (paths exist, none meets the rules); no documented
mechanism found; and "not assessed" (herb or drug not identified). Only the first can affect the
A–E class. None of them is evidence of safety.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from herbaguard.domain.enums import (
    SUBSTRATE_ROLES,
    DrugTargetRole,
    EvidenceType,
    ModulationEffect,
    Potency,
)

RULES_VERSION = "mechanism rules v1 (docs/api/mechanism-paths.md)"

AUTHORITATIVE_HERB_EVIDENCE = frozenset({EvidenceType.REGULATORY, EvidenceType.GOVERNMENT_SUMMARY})
AUTHORITATIVE_DRUG_ROLE_SOURCES = frozenset({"fda_cyp_table"})
EXPERIMENTAL_EVIDENCE = frozenset({EvidenceType.IN_VITRO, EvidenceType.ANIMAL})

# FDA groups CYP3A4 and CYP3A5 as "CYP3A"; EMA monographs name CYP3A4.
MATCH_GROUP: dict[str, str] = {"CYP3A4": "CYP3A", "CYP3A5": "CYP3A"}

MECHANISM_CAVEAT = (
    "Mechanism-based finding: no source names this herb together with this drug. The herb affects "
    "an enzyme or transporter this drug depends on; whether this changes the drug's effect, and by "
    "how much, is not known from these sources."
)


def match_key(symbol: str) -> str:
    return MATCH_GROUP.get(symbol, symbol)


@dataclass(frozen=True, slots=True)
class HerbEffect:
    """One stored ``target_modulation`` row as seen from a herb."""

    id: str
    target_symbol: str
    effect: str  # ModulationEffect value
    potency: str | None  # Potency value as stated by the source
    evidence_type: str  # EvidenceType value
    source_code: str
    subject_kind: str  # "herbal_substance" | "constituent"
    subject_label: str  # e.g. "Hyperici herba", "curcumin"
    conditions: str | None = None
    hedge: str | None = None  # the source's modal word before the verb ("may"), if any


@dataclass(frozen=True, slots=True)
class DrugRole:
    """One stored ``drug_target_role`` row."""

    id: str
    target_symbol: str
    role: str  # DrugTargetRole value
    potency: str | None
    source_code: str
    conditions: str | None = None


@dataclass(frozen=True, slots=True)
class AssessedPath:
    herb: HerbEffect
    drug: DrugRole
    qualifies: bool
    reasons_not_qualifying: tuple[str, ...]
    conflicting: bool = False  # opposite authoritative effects on this target (rule 7)
    experimental: bool = False  # herb side is in-vitro or animal evidence

    @property
    def target_symbols(self) -> str:
        if self.herb.target_symbol == self.drug.target_symbol:
            return self.herb.target_symbol
        return f"{self.herb.target_symbol} / {self.drug.target_symbol}"


def _assess(herb: HerbEffect, drug: DrugRole, conflicted: frozenset[str]) -> AssessedPath:
    reasons: list[str] = []
    if herb.subject_kind != "herbal_substance":
        reasons.append(
            f"The effect is stated for the constituent {herb.subject_label}, not for the herbal "
            "preparation."
        )
    if herb.evidence_type not in AUTHORITATIVE_HERB_EVIDENCE:
        reasons.append(
            f"The herb-side evidence is of type {herb.evidence_type} (not a regulatory or government "
            "source)."
        )
    if herb.effect not in (ModulationEffect.INDUCES, ModulationEffect.INHIBITS):
        reasons.append(f"The herb's effect ('{herb.effect}') is not induction or inhibition.")
    if herb.potency == Potency.WEAK:
        reasons.append("The source grades the herb's effect as weak.")
    if drug.role not in SUBSTRATE_ROLES:
        reasons.append(
            f"The drug is a{'n' if drug.role[0] in 'aeiou' else ''} {drug.role.replace('_', ' ')} of "
            f"{drug.target_symbol}, not a substrate, so the herb would not change its exposure "
            "through this route."
        )
    if drug.source_code not in AUTHORITATIVE_DRUG_ROLE_SOURCES:
        reasons.append(f"The drug-side source ({drug.source_code}) is not an authoritative table.")
    conflicting = match_key(herb.target_symbol) in conflicted
    if conflicting:
        reasons.append(
            f"Sources state both induction and inhibition of {herb.target_symbol} for this herb; the "
            "net effect is not known."
        )
    return AssessedPath(
        herb,
        drug,
        not reasons,
        tuple(reasons),
        conflicting=conflicting,
        experimental=herb.evidence_type in EXPERIMENTAL_EVIDENCE,
    )


def conflicting_targets(herb_effects: list[HerbEffect]) -> frozenset[str]:
    """Targets (match keys) for which authoritative, herb-level statements give both induction and
    inhibition. Constituent and in-vitro/animal statements do not create a conflict: they never
    qualify anyway and are shown as context."""
    seen: dict[str, set[str]] = {}
    for effect in herb_effects:
        if (
            effect.subject_kind == "herbal_substance"
            and effect.evidence_type in AUTHORITATIVE_HERB_EVIDENCE
            and effect.effect in (ModulationEffect.INDUCES, ModulationEffect.INHIBITS)
        ):
            seen.setdefault(match_key(effect.target_symbol), set()).add(effect.effect)
    return frozenset(key for key, effects in seen.items() if len(effects) > 1)


def assess_paths(herb_effects: list[HerbEffect], drug_roles: list[DrugRole]) -> list[AssessedPath]:
    """Every herb effect × drug role on the same enzyme/transporter (rule 6), assessed against
    rules 1–5 and 7. Qualifying paths first, then by target symbol; deterministic order."""
    conflicted = conflicting_targets(herb_effects)
    paths = [
        _assess(herb, drug, conflicted)
        for herb in herb_effects
        for drug in drug_roles
        if match_key(herb.target_symbol) == match_key(drug.target_symbol)
    ]
    return sorted(
        paths,
        key=lambda p: (not p.qualifies, match_key(p.herb.target_symbol), p.herb.id, p.drug.id),
    )


def describe(path: AssessedPath) -> str:
    """One plain-language sentence for a path (used as a classification reason)."""
    herb = path.herb
    drug = path.drug
    strength = f" ({herb.potency})" if herb.potency else ""
    role = DrugTargetRole(drug.role).value.replace("_", " ")
    verb = f"{herb.hedge} {herb.effect.removesuffix('s')}" if herb.hedge else herb.effect
    text = (
        f"{herb.subject_label} {verb}{strength} {herb.target_symbol} "
        f"[{herb.source_code}]; this drug is a {role} of {drug.target_symbol} [{drug.source_code}]."
    )
    if herb.hedge:
        text += f" The source's wording is hedged ('{herb.hedge}')."
    if herb.conditions:
        text += f" Conditions stated for the herb: {herb.conditions}"
    return text


# --------------------------------------------------------------------------- mechanism finding


class MechanismFinding(StrEnum):
    MECHANISM_SUPPORTED = "mechanism_supported"
    CONFLICTING = "conflicting_mechanism_evidence"
    EXPERIMENTAL_ONLY = "experimental_mechanism_evidence_only"
    INSUFFICIENT = "insufficient_mechanism_evidence"
    NONE_FOUND = "no_documented_mechanism_found"
    NOT_ASSESSED = "not_assessed"


MECHANISM_FINDING_LABELS: dict[MechanismFinding, str] = {
    MechanismFinding.MECHANISM_SUPPORTED: "Mechanism-supported potential interaction",
    MechanismFinding.CONFLICTING: "Conflicting mechanism evidence",
    MechanismFinding.EXPERIMENTAL_ONLY: "Experimental (in-vitro or animal) mechanism evidence only",
    MechanismFinding.INSUFFICIENT: "Insufficient mechanism evidence",
    MechanismFinding.NONE_FOUND: "No documented mechanism found",
    MechanismFinding.NOT_ASSESSED: "Not assessed",
}

NOT_SAFETY = "This is not evidence that the combination is safe."


@dataclass(frozen=True, slots=True)
class MechanismAssessment:
    finding: MechanismFinding
    label: str
    explanation: str
    paths_total: int
    qualifying_paths: int


def assess_mechanism(
    *,
    herb_resolved: bool,
    drug_resolved: bool,
    herb_effects_stored: int,
    drug_roles_stored: int,
    paths: list[AssessedPath],
) -> MechanismAssessment:
    """One finding per herb–drug pair; the first matching rule wins (module docstring)."""

    def result(finding: MechanismFinding, explanation: str) -> MechanismAssessment:
        return MechanismAssessment(
            finding,
            MECHANISM_FINDING_LABELS[finding],
            explanation,
            len(paths),
            sum(1 for p in paths if p.qualifies),
        )

    if not (herb_resolved and drug_resolved):
        return result(
            MechanismFinding.NOT_ASSESSED,
            "The herb or the drug could not be identified, so no mechanism was looked up.",
        )
    if any(p.qualifies for p in paths):
        return result(
            MechanismFinding.MECHANISM_SUPPORTED,
            "A regulatory or government source states that this herb induces or inhibits an enzyme "
            "or transporter of which FDA lists this drug as a substrate. This supports a potential "
            "interaction; whether and how much it changes the drug's effect is not known from "
            "these sources.",
        )
    if any(p.conflicting for p in paths):
        return result(
            MechanismFinding.CONFLICTING,
            "Sources state opposite effects (induction and inhibition) of this herb on an enzyme or "
            f"transporter this drug depends on; the net effect is not known. {NOT_SAFETY}",
        )
    if paths and all(p.experimental for p in paths):
        return result(
            MechanismFinding.EXPERIMENTAL_ONLY,
            "The only link between this herb and this drug comes from laboratory (in-vitro) or "
            "animal findings, which do not show an effect in people. It is shown for transparency "
            f"and does not change the classification. {NOT_SAFETY}",
        )
    if paths:
        return result(
            MechanismFinding.INSUFFICIENT,
            "The herb and the drug share an enzyme or transporter, but no link meets the rules for a "
            "potential interaction (see the reasons on each path). Sharing an enzyme or transporter "
            f"does not by itself establish an interaction. {NOT_SAFETY}",
        )
    if herb_effects_stored == 0:
        why = "No enzyme or transporter effect of this herb is stated in the sources searched."
    elif drug_roles_stored == 0:
        why = (
            "FDA's table does not list this drug; it lists examples only, so the drug may still "
            "depend on an enzyme or transporter this herb affects."
        )
    else:
        why = (
            "The enzymes/transporters this herb affects are not ones FDA lists this drug as a "
            "substrate of. FDA lists examples only."
        )
    return result(MechanismFinding.NONE_FOUND, f"{why} {NOT_SAFETY}")
