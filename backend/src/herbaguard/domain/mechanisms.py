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

A qualifying path never yields class A, never overrides a documented statement, and its size of
effect is unknown — this is stated in every result.
"""

from __future__ import annotations

from dataclasses import dataclass

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

    @property
    def target_symbols(self) -> str:
        if self.herb.target_symbol == self.drug.target_symbol:
            return self.herb.target_symbol
        return f"{self.herb.target_symbol} / {self.drug.target_symbol}"


def _assess(herb: HerbEffect, drug: DrugRole) -> AssessedPath:
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
    return AssessedPath(herb, drug, not reasons, tuple(reasons))


def assess_paths(herb_effects: list[HerbEffect], drug_roles: list[DrugRole]) -> list[AssessedPath]:
    """Every herb effect × drug role on the same enzyme/transporter (rule 6), assessed against
    rules 1–5. Qualifying paths first, then by target symbol; deterministic order."""
    paths = [
        _assess(herb, drug)
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
    text = (
        f"{herb.subject_label} {herb.effect}{strength} {herb.target_symbol} "
        f"[{herb.source_code}]; this drug is a {role} of {drug.target_symbol} [{drug.source_code}]."
    )
    if herb.conditions:
        text += f" Conditions stated for the herb: {herb.conditions}"
    return text
