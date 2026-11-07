"""Request/response models of the AI endpoints (Phase 5). See docs/api/ai-endpoints.md."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from herbaguard.api.schemas.mechanism_core import MechanismAssessmentOut
from herbaguard.api.schemas.provenance import EvidenceTypeInfo, ProvenanceOut

QUESTION_MAX = 1000  # also enforced by settings.ai_question_max_chars (the smaller wins)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=QUESTION_MAX,
                          examples=["Does St John's wort interact with warfarin?"])  # fmt: skip
    allow_remote_drug_lookup: bool = Field(
        default=True,
        description="Resolve unknown brand names through RxNav (recorded with provenance)",
    )


class EntityOut(BaseModel):
    kind: Literal["herb", "drug", "target", "constituent"]
    mention: str
    name: str
    identifier: str | None = Field(description="Pharmaceutical name, RxCUI or target symbol")
    note: str | None = None


class PairClassification(BaseModel):
    """Copied from the deterministic interaction service; never produced by the language model."""

    herb: str
    drug: str
    interaction_class: str
    class_label: str
    finding: str
    finding_label: str
    explanation: str
    severity_wordings: list[str]
    caveats: list[str]
    mechanism_assessment: MechanismAssessmentOut | None
    method: str
    source: str = (
        "HerbaGuard deterministic interaction classification (POST /api/v1/interactions/check)"
    )


class CitationOut(BaseModel):
    label: str = Field(examples=["S1"], description="Id used in the answer paragraphs")
    kind: Literal[
        "classification",
        "statement",
        "mechanism",
        "excerpt",
        "fact",
        "observation",
        "hepatotoxicity",
        "mention",
        "product_label",
    ]
    role: Literal[
        "deterministic_classification",
        "direct_evidence",
        "graph_context",
        "catalogue",
        "experimental_evidence",
        "hepatotoxicity_evidence",
        "supplementary_mention",
        "product_label_information",
    ]
    evidence_item_id: str | None
    external_id: str | None
    source_code: str | None
    evidence_type: EvidenceTypeInfo | None
    title: str | None
    url: str | None = Field(description="From stored provenance, never from model output")
    location: str | None
    excerpt: str = Field(
        description="Verbatim stored text (or the deterministic graph description)"
    )
    qualifiers: list[str]
    provenance: list[ProvenanceOut]


class ParagraphOut(BaseModel):
    text: str
    citations: list[str]


class ValidationIssueOut(BaseModel):
    rule: str
    severity: Literal["removed", "critical", "warning"]
    message: str
    paragraph: int | None
    # Audit only: the paragraph or limitation the issue refers to. Excluded from API output so text
    # withheld by validation is never shown; evaluation reports store it.
    text: str | None = Field(default=None, exclude=True)


class GenerationInfo(BaseModel):
    mode: Literal["model", "extractive", "none"]
    provider: str
    model: str | None
    prompts: list[str]
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: int
    regenerations: int = Field(default=0, description="Corrected re-requests after a failed check")
    failed_attempts: list[dict[str, str]] = Field(
        description="Providers tried before the one that answered (explicit fallback only)"
    )


class RetrievalInfo(BaseModel):
    mode_requested: str
    mode_used: str
    embedding_model: str | None
    candidates: dict[str, int]
    duration_ms: int
    notes: list[str]


class CacheInfo(BaseModel):
    """Present only when the answer was served from the validated answer cache."""

    served_from_cache: bool = True
    generated_at: datetime
    original_generation_ms: int = Field(
        description="How long the language model took when this answer was generated; no model "
        "ran for the request that returned it"
    )
    validation_status: str = "passed"


class AskResponse(BaseModel):
    status: Literal[
        "answered",
        "insufficient_evidence",
        "rejected_by_validation",
        "declined_dosing",  # no generated text; official posology passages quoted verbatim
        "emergency_referral",  # no retrieval, no generation; referral message only
    ]
    question: str
    intent: str
    answer: str | None = Field(description="Paragraph texts joined; null when rejected")
    paragraphs: list[ParagraphOut]
    classification: list[PairClassification]
    citations: list[CitationOut]
    limitations: list[str]
    insufficient_evidence: bool
    entities: list[EntityOut]
    personal_advice_requested: bool
    validation: list[ValidationIssueOut]
    generation: GenerationInfo
    retrieval: RetrievalInfo | None
    disclaimer: str
    cache: CacheInfo | None = None


class RetrieveRequest(BaseModel):
    query: str = Field(min_length=2, max_length=QUESTION_MAX)
    mode: Literal["keyword", "semantic", "hybrid"] = "hybrid"
    top_k: int = Field(default=10, ge=1, le=50)
    sources: list[str] = Field(default_factory=list, max_length=50)
    evidence_types: list[str] = Field(default_factory=list, max_length=20)
    herb: str | None = Field(
        default=None, max_length=200, description="Restrict to evidence linked to this herb"
    )
    drug: str | None = Field(
        default=None, max_length=200, description="Restrict to evidence linked to this drug"
    )
    target: str | None = Field(
        default=None,
        max_length=32,
        description="Restrict to evidence about this enzyme/transporter",
    )


class RetrievedItemOut(BaseModel):
    segment_id: str
    evidence_item_id: str
    external_id: str
    source_code: str
    source_name: str
    licence: str | None
    licence_status: str
    redistributable: bool
    evidence_type: EvidenceTypeInfo
    title: str
    url: str | None
    document_date: date | None
    publication_year: int | None
    section: str | None
    excerpt: str
    char_start: int
    char_end: int
    herbs: list[str]
    provenance: list[ProvenanceOut]
    fused_score: float = Field(description="RRF score: ranks text relevance, not evidence quality")
    ranks: dict[str, int]
    similarity: float | None
    keyword_score: float | None


class RetrieveResponse(BaseModel):
    query: str
    items: list[RetrievedItemOut]
    retrieval: RetrievalInfo
    note: str = (
        "Ranking reflects text relevance to the query, not the strength or quality of the evidence."
    )


class ProviderOut(BaseModel):
    name: str
    model: str | None
    selected: bool
    fallback: bool
    configured: bool
    reachable: bool | None = Field(
        description="null = not probed (cloud providers are never called)"
    )
    detail: str | None


class ProvidersResponse(BaseModel):
    generation: list[ProviderOut]
    embedding: ProviderOut
    cloud_source_text_allowed: bool


class ComponentStatus(BaseModel):
    name: str
    status: Literal["ok", "degraded", "unavailable", "not_configured"]
    detail: str | None = None


class AIHealthResponse(BaseModel):
    status: Literal["ok", "degraded", "unavailable"]
    components: list[ComponentStatus]
    index: dict[str, object]
