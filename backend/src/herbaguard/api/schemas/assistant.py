"""AI evidence assistant (Phase 5) request/response schemas."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from herbaguard.api.schemas.provenance import EvidenceTypeInfo
from herbaguard.api.schemas.resources import Candidate, ClassificationOut, DrugResolution, HerbRef

AnswerMode = Literal[
    "generated",  # LLM answer that passed citation validation
    "extractive",  # verbatim quotes from the retrieved passages
    "insufficient_evidence",  # nothing relevant retrieved
    "needs_clarification",  # ambiguous herb name
    "declined_dosing",  # individual dosing question
    "emergency_referral",  # emergency wording; no retrieval
]


class AssistantRequest(BaseModel):
    question: str = Field(
        min_length=3,
        max_length=1000,
        examples=["Can I take St John's wort with my contraceptive pill?"],
    )
    herb: str | None = Field(
        default=None,
        max_length=200,
        description="Optional herb name; otherwise herbs are recognised in the question.",
    )
    drugs: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Optional drug names; otherwise drugs in HerbaGuard's index are recognised "
        "in the question. Never looked up remotely.",
    )
    mode: Literal["auto", "extractive"] = Field(
        default="auto",
        description="'auto' uses the local LLM when available; 'extractive' never calls an LLM.",
    )

    @field_validator("question")
    @classmethod
    def _strip(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("drugs")
    @classmethod
    def _clean_drugs(cls, value: list[str]) -> list[str]:
        cleaned = [" ".join(v.split()) for v in value]
        if any(not v or len(v) > 200 for v in cleaned):
            msg = "Each drug name must be 1–200 characters."
            raise ValueError(msg)
        return cleaned


class Citation(BaseModel):
    marker: str = Field(examples=["S1"], description="As written in the answer: [S1]")
    evidence_id: str
    chunk_id: str
    href: str = Field(description="API link to the full evidence item with provenance")
    source_code: str
    source_name: str
    title: str
    section: str | None
    url: str | None
    evidence_type: EvidenceTypeInfo
    document_date: date | None
    publication_year: int | None
    excerpt: str = Field(description="The passage text the model saw (truncated)")
    cited: bool = Field(description="True when the answer cites this passage")
    retrieval: list[Literal["interaction_result", "full_text", "vector"]]


class InteractionFinding(BaseModel):
    """The deterministic A–E result for one recognised herb–drug pair (not computed by the LLM)."""

    drug: DrugResolution
    classification: ClassificationOut | None
    mechanism_finding: str | None = None
    href: str = "/api/v1/interactions/check"


class EntitiesOut(BaseModel):
    herb_status: Literal["resolved", "ambiguous", "not_found", "not_mentioned"]
    herb: HerbRef | None = None
    herb_matched_text: str | None = None
    herb_candidates: list[Candidate] = Field(default_factory=list)
    drugs: list[DrugResolution] = Field(default_factory=list)


class GenerationInfo(BaseModel):
    provider: Literal["ollama", "none"]
    model: str | None = None
    prompt_version: str
    attempts: int = Field(ge=0)
    duration_ms: int | None = None
    citation_check: Literal["passed", "failed", "not_applicable"]
    citation_issues: list[str] = Field(default_factory=list)
    fallback_reason: str | None = None


class AssistantResponse(BaseModel):
    question: str
    mode: AnswerMode
    answer: str = Field(description="Plain text; citations as [S1] refer to `citations`.")
    referral: str
    entities: EntitiesOut
    interaction_findings: list[InteractionFinding]
    citations: list[Citation]
    generation: GenerationInfo
    notes: list[str] = Field(default_factory=list)
    disclaimer: str


class AssistantStatus(BaseModel):
    provider: Literal["ollama", "none"]
    ollama_url: str | None
    ollama_reachable: bool
    chat_model: str | None
    chat_model_available: bool
    embedding_model: str | None
    embedding_model_available: bool
    chunks_total: int
    chunks_embedded: int
    retrieval: Literal["hybrid", "full_text_only"]
    answer_modes: list[str]
    notes: list[str]
