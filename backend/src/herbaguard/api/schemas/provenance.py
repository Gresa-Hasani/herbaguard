"""Provenance and evidence-type objects shared by every scientific response."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from herbaguard.domain.enums import EvidenceType

EVIDENCE_TYPE_LABELS: dict[str, str] = {
    EvidenceType.REGULATORY: "Regulatory document",
    EvidenceType.GOVERNMENT_SUMMARY: "Government summary",
    EvidenceType.SYSTEMATIC_REVIEW: "Systematic review or meta-analysis",
    EvidenceType.RANDOMISED_CONTROLLED_TRIAL: "Randomised controlled trial",
    EvidenceType.CLINICAL_STUDY: "Other clinical study",
    EvidenceType.CASE_REPORT: "Case report",
    EvidenceType.NARRATIVE_REVIEW: "Narrative review",
    EvidenceType.ANIMAL: "Animal study",
    EvidenceType.IN_VITRO: "In-vitro study",
    EvidenceType.TRADITIONAL_USE: "Traditional use (recognised by a regulator)",
    EvidenceType.SPONTANEOUS_REPORT: "Spontaneous adverse-event report",
    EvidenceType.COMPUTATIONAL: "Computational prediction",
    EvidenceType.OTHER: "Other publication type",
}

TYPE_NOT_QUALITY = (
    "Evidence type describes the kind of document or study design (for PubMed: the publication "
    "type assigned by NLM indexers). It is not a quality rating; HerbaGuard has not appraised study quality."
)


class EvidenceTypeInfo(BaseModel):
    code: EvidenceType
    label: str
    basis: Literal["source_document", "nlm_publication_type"] = Field(
        description="How the type was assigned: by the kind of source document, or from PubMed publication types/MeSH."
    )
    quality_assessed: Literal[False] = Field(
        default=False, description="Always false: study quality has not been appraised."
    )
    note: str = TYPE_NOT_QUALITY

    @classmethod
    def of(cls, code: str, source_code: str) -> EvidenceTypeInfo:
        evidence = EvidenceType(code)
        return cls(
            code=evidence,
            label=EVIDENCE_TYPE_LABELS[evidence],
            basis="nlm_publication_type" if source_code == "pubmed" else "source_document",
        )


class ProvenanceOut(BaseModel):
    """Where a statement or record came from, as retrieved by HerbaGuard."""

    source_code: str = Field(examples=["ema_hmpc"])
    source_name: str
    licence: str | None
    licence_status: str = Field(
        description="verified | catalogue | to_verify (see docs/data/sources.md)"
    )
    retrieved_url: str = Field(description="URL of the exact request HerbaGuard made")
    retrieved_at: datetime
    source_version: str | None = Field(
        description="E.g. EMA document number or NCCIH 'last updated' date"
    )
    extraction_method: str
    location: str | None = Field(
        description="Where in the record, e.g. 'section 4.5, well_established_use, pages 9-10'"
    )
    excerpt: str | None = Field(description="Verbatim source text (where the licence permits)")


class EvidenceRef(BaseModel):
    """A citable evidence item (monograph section, label section, fact-sheet section, article)."""

    id: str
    source_code: str
    external_id: str = Field(
        description="Identifier in the source: EMA document#section#use, set_id#section, PMID, …"
    )
    title: str
    url: str | None
    evidence_type: EvidenceTypeInfo
    document_date: date | None
    publication_year: int | None
