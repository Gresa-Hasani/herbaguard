"""Controlled vocabularies.

Definitions follow ``docs/research/scientific-and-ethical-considerations.md``. Values are
stored as plain strings in the database (with CHECK constraints), so adding a value needs a
migration that updates the constraint.
"""

from __future__ import annotations

from enum import StrEnum


class LicenceStatus(StrEnum):
    """How confident we are about a source's licence (mirrors the Phase 0 audit markers)."""

    VERIFIED = "verified"  # confirmed on the provider page or in API metadata
    CATALOGUE = "catalogue"  # taken from the organizer catalogue, not re-verified
    TO_VERIFY = "to_verify"  # working assumption; do not redistribute until verified


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"  # finished, but some records failed validation
    FAILED = "failed"


class IssueSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class NameType(StrEnum):
    ACCEPTED = "accepted"
    SYNONYM = "synonym"
    COMMON = "common"
    PHARMACEUTICAL = "pharmaceutical"  # e.g. EMA Latin name "Hyperici herba"


class UseCategory(StrEnum):
    """EMA HMPC use categories. Never merge them: they carry different evidentiary weight."""

    WELL_ESTABLISHED = "well_established_use"
    TRADITIONAL = "traditional_use"
    NOT_APPLICABLE = "not_applicable"


class ModulationEffect(StrEnum):
    """Effect of a herbal substance or constituent on an enzyme or transporter."""

    INDUCES = "induces"
    INHIBITS = "inhibits"
    ACTIVATES = "activates"  # e.g. nuclear receptor activation (hyperforin → PXR)
    OTHER = "other"


class DrugTargetRole(StrEnum):
    """A drug's role for an enzyme or transporter.

    The two "sensitive" values follow the FDA definitions (AUC increase with strong inhibitors of
    the pathway: sensitive ≥5-fold; moderately sensitive ≥2- to <5-fold). ``substrate`` is used
    for transporter substrates, which FDA does not grade by sensitivity.
    """

    SUBSTRATE = "substrate"
    SENSITIVE_SUBSTRATE = "sensitive_substrate"
    MODERATELY_SENSITIVE_SUBSTRATE = "moderately_sensitive_substrate"  # Phase 4
    INHIBITOR = "inhibitor"
    INDUCER = "inducer"


SUBSTRATE_ROLES = frozenset(
    {
        DrugTargetRole.SUBSTRATE,
        DrugTargetRole.SENSITIVE_SUBSTRATE,
        DrugTargetRole.MODERATELY_SENSITIVE_SUBSTRATE,
    }
)


class Potency(StrEnum):
    """Clinical potency category of an inhibitor or inducer as stated by the source (FDA
    definitions: strong / moderate / weak by AUC change of sensitive index substrates). Never
    computed by HerbaGuard."""

    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"


class TargetType(StrEnum):
    ENZYME = "enzyme"
    TRANSPORTER = "transporter"
    RECEPTOR = "receptor"
    OTHER = "other"


class EvidenceType(StrEnum):
    """Evidence-type vocabulary (scientific-and-ethical-considerations.md §3)."""

    REGULATORY = "REG"
    GOVERNMENT_SUMMARY = "GOV"
    SYSTEMATIC_REVIEW = "SR"
    RANDOMISED_CONTROLLED_TRIAL = "RCT"
    CLINICAL_STUDY = "CLIN"
    CASE_REPORT = "CASE"
    ANIMAL = "ANIMAL"
    IN_VITRO = "INVITRO"
    TRADITIONAL_USE = "TRAD"
    SPONTANEOUS_REPORT = "SPONT"
    COMPUTATIONAL = "COMP"
    # Added in Phase 2 for literature that fits none of the categories above.
    NARRATIVE_REVIEW = "REV"  # non-systematic review
    OTHER = "OTHER"  # letters, editorials, unclassifiable records


class InteractionClass(StrEnum):
    """Herb–drug interaction classes (scientific-and-ethical-considerations.md §2).

    Computed by deterministic rules from stored evidence; never assigned by an LLM.
    """

    DOCUMENTED = "A"
    POTENTIAL = "B"
    SUSPECTED = "C"
    NO_EVIDENCE_FOUND = "D"
    INSUFFICIENT_INFORMATION = "E"


class AssertionStatus(StrEnum):
    """Lifecycle of an extracted assertion. Superseded assertions are kept for lineage."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"  # failed human QA


class StatementType(StrEnum):
    """What an extracted sentence says about a herb–drug pair (Phase 2).

    Set by deterministic cue rules (``herbaguard.ingestion.normalize.statements``). It describes
    the *sentence*, not the final interaction class, which Phase 3 computes.
    """

    INTERACTION = "interaction"  # states or predicts an interaction / contraindication
    PRECAUTION = "precaution"  # advises caution, monitoring or consultation
    NO_INTERACTION_REPORTED = "no_interaction_reported"  # states none was found/reported
    UNCERTAIN = "uncertain"  # source itself says evidence is conflicting or unclear
    UNCLASSIFIED = "unclassified"  # drug named in an interaction context without clear cues


class EvidenceRelation(StrEnum):
    """Why an evidence item is linked to a herbal substance."""

    MONOGRAPH = "monograph"  # the substance's own regulatory monograph
    FACT_SHEET = "fact_sheet"  # government fact sheet about the substance
    LABEL_MENTION = "label_mention"  # a drug label naming the herb
    LITERATURE_INTERACTION = "literature_interaction"  # PubMed herb-drug interaction query
    LITERATURE_CLINICAL = "literature_clinical"  # PubMed SR / meta-analysis / RCT query
