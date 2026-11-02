"""Deterministic herb–drug interaction classification (classes A–E, refined by a finding).

Pure functions: no database, no network, no LLM. The criteria implement
``docs/research/scientific-and-ethical-considerations.md`` §2 on top of the typed statements
produced in Phase 2, and are documented for users in ``docs/api/interaction-classification.md``.

Inputs are the *active* stored statements that match the queried pair, either because they name
the drug itself or because they name an ATC class the drug belongs to.

Decision order (the first rule that applies wins):

1. **E / insufficient_information** — the herb or the drug could not be identified.
2. **A** — at least one *authoritative* statement (evidence type REG or GOV: EMA monograph, FDA
   label, NCCIH fact sheet) of type ``interaction`` or ``precaution`` that names the drug or a
   whole class it belongs to:
   * ``documented_interaction`` if any such statement is of type ``interaction``;
   * ``documented_precaution`` if all are of type ``precaution`` (caution/monitoring advised,
     no effect asserted).
3. **B / potential_interaction** — authoritative interaction/precaution statements exist only for
   *part* of a class the drug belongs to (Phase 2 marker "Applies to part of the class only"),
   or a *qualifying* mechanism path is supplied (Phase 4: herb induces/inhibits an enzyme or
   transporter of which the drug is a substrate; rules in ``herbaguard.domain.mechanisms``).
   A mechanism-only result carries ``MECHANISM_CAVEAT``.
4. **C** — only weaker statements:
   * ``uncertain_evidence`` if a source itself calls the evidence conflicting or unclear;
   * ``label_subject_not_confirmed`` if FDA label sentences with interaction or precaution
     wording exist, but none confirms the label's drug as its subject (``subject_verified`` false:
     the sentence neither names the drug nor sits in the label's drug-interaction,
     contraindication or boxed-warning section);
   * ``mentioned_without_interaction_wording`` if the herb is only mentioned (statement type
     ``unclassified``).
   Both are context only, never a confirmed interaction.
5. **E / insufficient_information** — no source covering the herb was searched.
6. **D** — nothing above applies:
   * ``no_interaction_reported`` if a source explicitly states that no interaction was found —
     either for this pair, or for the herb as a whole (EMA monograph §4.5 "None reported/known");
   * ``no_evidence_found`` otherwise.
   Neither D finding means the combination is safe.

Severity is never computed: the wording of decisive statements is relayed verbatim.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from herbaguard.domain.enums import EvidenceType, InteractionClass, StatementType
from herbaguard.domain.mechanisms import MECHANISM_CAVEAT

AUTHORITATIVE = frozenset({EvidenceType.REGULATORY, EvidenceType.GOVERNMENT_SUMMARY})
PARTIAL_CLASS_MARKER = "Applies to part of the class only"


class Finding(StrEnum):
    DOCUMENTED_INTERACTION = "documented_interaction"
    DOCUMENTED_PRECAUTION = "documented_precaution"
    POTENTIAL_INTERACTION = "potential_interaction"
    UNCERTAIN_EVIDENCE = "uncertain_evidence"
    LABEL_SUBJECT_NOT_CONFIRMED = "label_subject_not_confirmed"
    MENTIONED_WITHOUT_INTERACTION_WORDING = "mentioned_without_interaction_wording"
    NO_INTERACTION_REPORTED = "no_interaction_reported"
    NO_EVIDENCE_FOUND = "no_evidence_found"
    INSUFFICIENT_INFORMATION = "insufficient_information"


FINDING_CLASS: dict[Finding, InteractionClass] = {
    Finding.DOCUMENTED_INTERACTION: InteractionClass.DOCUMENTED,
    Finding.DOCUMENTED_PRECAUTION: InteractionClass.DOCUMENTED,
    Finding.POTENTIAL_INTERACTION: InteractionClass.POTENTIAL,
    Finding.UNCERTAIN_EVIDENCE: InteractionClass.SUSPECTED,
    Finding.LABEL_SUBJECT_NOT_CONFIRMED: InteractionClass.SUSPECTED,
    Finding.MENTIONED_WITHOUT_INTERACTION_WORDING: InteractionClass.SUSPECTED,
    Finding.NO_INTERACTION_REPORTED: InteractionClass.NO_EVIDENCE_FOUND,
    Finding.NO_EVIDENCE_FOUND: InteractionClass.NO_EVIDENCE_FOUND,
    Finding.INSUFFICIENT_INFORMATION: InteractionClass.INSUFFICIENT_INFORMATION,
}

CLASS_LABELS: dict[InteractionClass, str] = {
    InteractionClass.DOCUMENTED: "Documented",
    InteractionClass.POTENTIAL: "Potential",
    InteractionClass.SUSPECTED: "Suspected / unclear",
    InteractionClass.NO_EVIDENCE_FOUND: "No interaction evidence found",
    InteractionClass.INSUFFICIENT_INFORMATION: "Insufficient information",
}

FINDING_LABELS: dict[Finding, str] = {
    Finding.DOCUMENTED_INTERACTION: "Documented interaction",
    Finding.DOCUMENTED_PRECAUTION: "Documented precaution (caution or monitoring advised)",
    Finding.POTENTIAL_INTERACTION: "Potential interaction",
    Finding.UNCERTAIN_EVIDENCE: "Uncertain evidence",
    Finding.LABEL_SUBJECT_NOT_CONFIRMED: "Drug-label statement; this drug not confirmed as its subject",
    Finding.MENTIONED_WITHOUT_INTERACTION_WORDING: "Mentioned without explicit interaction wording",
    Finding.NO_INTERACTION_REPORTED: "No interaction reported by a source",
    Finding.NO_EVIDENCE_FOUND: "No interaction evidence found in the sources searched",
    Finding.INSUFFICIENT_INFORMATION: "Insufficient information to assess",
}

EXPLANATIONS: dict[Finding, str] = {
    Finding.DOCUMENTED_INTERACTION: (
        "A regulatory or government source explicitly states an interaction or contraindication for "
        "this herb with this drug, or with a drug class it belongs to as a whole."
    ),
    Finding.DOCUMENTED_PRECAUTION: (
        "A regulatory or government source names this combination and advises caution or monitoring, "
        "without stating that an interaction occurs."
    ),
    Finding.POTENTIAL_INTERACTION: (
        "A source describes an interaction only for part of a drug class this drug belongs to, or a "
        "plausible mechanism links the herb to how this drug is processed. The specific combination "
        "is not named explicitly."
    ),
    Finding.UNCERTAIN_EVIDENCE: (
        "A source mentions this combination but describes the evidence as conflicting or unclear."
    ),
    Finding.LABEL_SUBJECT_NOT_CONFIRMED: (
        "A drug label mentions the herb in an interaction-like statement, but the sentence neither names "
        "this drug nor appears in the label's drug-interaction, contraindication or boxed-warning section, "
        "so it is not confirmed that the statement is about this drug. Shown as context; it may still be "
        "relevant — read the source sentence."
    ),
    Finding.MENTIONED_WITHOUT_INTERACTION_WORDING: (
        "The herb is mentioned in an interaction-related section about this drug, but the sentence does "
        "not state an interaction. This is context only, not a confirmed interaction."
    ),
    Finding.NO_INTERACTION_REPORTED: (
        "A source explicitly reports that no interaction was found or reported for this combination. "
        "This reflects the source at its date; it does not prove the combination is safe."
    ),
    Finding.NO_EVIDENCE_FOUND: (
        "None of the sources searched contains an interaction statement for this combination. This does "
        "not mean the combination is safe: the sources may be incomplete, and many combinations have "
        "never been studied."
    ),
    Finding.INSUFFICIENT_INFORMATION: (
        "HerbaGuard cannot assess this combination because the herb or the drug could not be identified, "
        "or no source covering the herb is available."
    ),
}

ALWAYS_CAVEAT = (
    "This is information from scientific and regulatory sources, not medical advice. Talk to your doctor "
    "or pharmacist before combining herbal products with medicines."
)
NOT_SAFETY_CAVEAT = (
    "An absence of reported interactions is not evidence that a combination is safe."
)


@dataclass(frozen=True, slots=True)
class Statement:
    """One stored, active interaction statement matched to the queried pair."""

    id: str
    source_code: str
    evidence_type: EvidenceType
    statement_type: StatementType
    matched_via: str  # "drug" | "class"
    drug_class_code: str | None
    conditions: str | None
    severity_wording: str | None
    use_category: str
    # False when a drug-label sentence neither names the label's drug nor sits in an
    # interaction-specific label section, so the drug cannot be confirmed as its subject.
    subject_verified: bool = True

    @property
    def partial_class(self) -> bool:
        return self.matched_via == "class" and PARTIAL_CLASS_MARKER in (self.conditions or "")

    @property
    def authoritative(self) -> bool:
        return self.evidence_type in AUTHORITATIVE


@dataclass(frozen=True, slots=True)
class MechanismPath:
    """A *qualifying* mechanism path (``herbaguard.domain.mechanisms``): the herb induces or
    inhibits an enzyme/transporter of which this drug is a substrate. Only qualifying paths are
    passed to ``classify``; the others are shown as context by the service."""

    target_symbol: str
    herb_effect: str
    drug_role: str
    source: str
    description: str | None = None  # full plain-language sentence (Phase 4)

    def reason(self) -> str:
        if self.description:
            return self.description
        return (
            f"Herb {self.herb_effect} {self.target_symbol}; this drug is a "
            f"{self.drug_role.replace('_', ' ')} of {self.target_symbol} ({self.source})."
        )


@dataclass(frozen=True, slots=True)
class Classification:
    interaction_class: InteractionClass
    finding: Finding
    class_label: str
    finding_label: str
    explanation: str
    reasons: list[str]
    decisive_statement_ids: list[str]
    context_statement_ids: list[str]
    severity_wordings: list[str]
    caveats: list[str] = field(default_factory=list)


def _unique(values: Sequence[str | None]) -> list[str]:
    out: list[str] = []
    for value in values:
        if value and value not in out:
            out.append(value)
    return out


def _result(
    finding: Finding,
    reasons: list[str],
    decisive: Sequence[Statement],
    all_statements: Sequence[Statement],
    extra_caveats: Sequence[str] = (),
) -> Classification:
    cls = FINDING_CLASS[finding]
    decisive_ids = {s.id for s in decisive}
    caveats = [ALWAYS_CAVEAT]
    if cls in (InteractionClass.NO_EVIDENCE_FOUND, InteractionClass.INSUFFICIENT_INFORMATION):
        caveats.append(NOT_SAFETY_CAVEAT)
    return Classification(
        interaction_class=cls,
        finding=finding,
        class_label=CLASS_LABELS[cls],
        finding_label=FINDING_LABELS[finding],
        explanation=EXPLANATIONS[finding],
        reasons=reasons,
        decisive_statement_ids=[s.id for s in decisive],
        context_statement_ids=[s.id for s in all_statements if s.id not in decisive_ids],
        severity_wordings=_unique([s.severity_wording for s in decisive]),
        caveats=[*caveats, *extra_caveats],
    )


def _classify(
    *,
    herb_resolved: bool,
    drug_resolved: bool,
    herb_has_sources: bool,
    statements: Sequence[Statement],
    mechanisms: Sequence[MechanismPath] = (),
    herb_level_none_reported: Sequence[str] = (),
) -> Classification:
    """Apply the decision order documented in the module docstring.

    ``herb_level_none_reported``: descriptions of source sections that state "None reported" /
    "None known" for the herb as a whole, quoting the source (e.g. 'EMA/HMPC/48745/2017 §4.5
    (well-established use, 2018-03-27): "None reported"').
    """
    if not herb_resolved or not drug_resolved:
        missing = [n for n, ok in (("herb", herb_resolved), ("drug", drug_resolved)) if not ok]
        return _result(
            Finding.INSUFFICIENT_INFORMATION,
            [f"The {' and the '.join(missing)} could not be identified."],
            (),
            statements,
        )

    actionable = (StatementType.INTERACTION, StatementType.PRECAUTION)
    usable = [
        s
        for s in statements
        if s.authoritative and s.statement_type in actionable and s.subject_verified
    ]
    whole = [s for s in usable if not s.partial_class]
    partial = [s for s in usable if s.partial_class]
    uncertain = [s for s in statements if s.statement_type is StatementType.UNCERTAIN]
    unconfirmed = [
        s for s in statements if s.statement_type in actionable and not s.subject_verified
    ]
    mentioned = [s for s in statements if s.statement_type is StatementType.UNCLASSIFIED]
    negative = [s for s in statements if s.statement_type is StatementType.NO_INTERACTION_REPORTED]

    if whole:
        interactions = [s for s in whole if s.statement_type is StatementType.INTERACTION]
        finding = Finding.DOCUMENTED_INTERACTION if interactions else Finding.DOCUMENTED_PRECAUTION
        decisive = interactions or whole
        reasons = []
        direct = [s for s in decisive if s.matched_via == "drug"]
        via_class = [s for s in decisive if s.matched_via == "class"]
        if direct:
            sources = ", ".join(sorted({s.source_code for s in direct}))
            reasons.append(
                f"Named explicitly with this drug in {len(direct)} statement(s) ({sources})."
            )
        if via_class:
            codes = ", ".join(sorted({s.drug_class_code or "" for s in via_class}))
            reasons.append(f"Stated for a drug class this drug belongs to (ATC {codes}).")
        extra = []
        if any(s.conditions for s in decisive):
            extra.append(
                "Some statements apply only under stated conditions (indication, dose or use category)."
            )
        if uncertain or negative or mentioned:
            extra.append(
                "Other statements report uncertain, absent or unspecific evidence; see context statements."
            )
        return _result(finding, reasons, decisive, statements, extra)

    if partial or mechanisms:
        reasons = []
        if partial:
            reasons.append(
                "A source states this for part of a drug class this drug belongs to; whether it applies "
                "to this drug is not stated."
            )
        reasons += [m.reason() for m in mechanisms]
        extra = [MECHANISM_CAVEAT] if mechanisms and not partial else []
        return _result(Finding.POTENTIAL_INTERACTION, reasons, partial, statements, extra)

    if uncertain:
        return _result(
            Finding.UNCERTAIN_EVIDENCE,
            ["A source describes the evidence for this combination as conflicting or unclear."],
            uncertain,
            statements,
        )
    if unconfirmed:
        return _result(
            Finding.LABEL_SUBJECT_NOT_CONFIRMED,
            [
                "Drug-label sentences mention the herb, but this drug is not confirmed as their subject; "
                "shown as context only."
            ],
            unconfirmed,
            statements,
        )
    if mentioned:
        return _result(
            Finding.MENTIONED_WITHOUT_INTERACTION_WORDING,
            [
                "The herb is mentioned in an interaction-related section for this drug without explicit "
                "interaction wording; shown as context only."
            ],
            mentioned,
            statements,
        )

    if not herb_has_sources:
        return _result(
            Finding.INSUFFICIENT_INFORMATION,
            ["No HerbaGuard source covers this herb, so no search could be performed."],
            (),
            statements,
        )

    if negative or herb_level_none_reported:
        reasons = []
        if negative:
            reasons.append("A source explicitly reports no interaction for this combination.")
        reasons += [
            f"{where} — stated for this herbal substance as a whole, not for this drug specifically."
            for where in herb_level_none_reported
        ]
        return _result(Finding.NO_INTERACTION_REPORTED, reasons, negative, statements)
    return _result(
        Finding.NO_EVIDENCE_FOUND,
        ["No interaction statement for this combination was found in the sources searched."],
        (),
        statements,
    )


def classify(
    *,
    herb_resolved: bool,
    drug_resolved: bool,
    herb_has_sources: bool,
    statements: Sequence[Statement],
    mechanisms: Sequence[MechanismPath] = (),
    herb_level_none_reported: Sequence[str] = (),
) -> Classification:
    """Classify (see module docstring) and make source disagreements visible: when a monograph
    states "None reported" for the herb but other sources produce class A, B or C, the
    monograph statement is added as a caveat instead of being silently overridden."""
    result = _classify(
        herb_resolved=herb_resolved,
        drug_resolved=drug_resolved,
        herb_has_sources=herb_has_sources,
        statements=statements,
        mechanisms=mechanisms,
        herb_level_none_reported=herb_level_none_reported,
    )
    if herb_level_none_reported and result.interaction_class in (
        InteractionClass.DOCUMENTED,
        InteractionClass.POTENTIAL,
        InteractionClass.SUSPECTED,
    ):
        notes = [
            f"Sources differ: {where} — for the herbal substance as a whole, at the document date."
            for where in herb_level_none_reported
        ]
        return Classification(
            interaction_class=result.interaction_class,
            finding=result.finding,
            class_label=result.class_label,
            finding_label=result.finding_label,
            explanation=result.explanation,
            reasons=result.reasons,
            decisive_statement_ids=result.decisive_statement_ids,
            context_statement_ids=result.context_statement_ids,
            severity_wordings=result.severity_wordings,
            caveats=[*result.caveats, *notes],
        )
    return result
