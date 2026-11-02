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
    SUBSTRATE = "substrate"
    SENSITIVE_SUBSTRATE = "sensitive_substrate"
    INHIBITOR = "inhibitor"
    INDUCER = "inducer"


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
