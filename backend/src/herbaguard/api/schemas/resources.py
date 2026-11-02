"""Schemas for plants, herbs, drugs, evidence, interactions and sources."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from herbaguard.api.schemas.mechanism_core import MechanismPathOut
from herbaguard.api.schemas.provenance import EvidenceRef, EvidenceTypeInfo, ProvenanceOut
from herbaguard.domain.enums import InteractionClass, StatementType
from herbaguard.domain.interactions import Finding

# --------------------------------------------------------------------------- plants / herbs


class NameOut(BaseModel):
    name: str
    name_type: Literal["accepted", "synonym", "common", "pharmaceutical"]
    language: str | None
    source_code: str


class HerbRef(BaseModel):
    """A curated herb = all substances sharing an EMA pharmaceutical name."""

    pharmaceutical_name: str = Field(examples=["Hyperici herba"])
    common_name: str | None
    plant_part: str


class TaxonSummary(BaseModel):
    wfo_id: str = Field(examples=["wfo-0000728093"])
    scientific_name: str
    authorship: str | None
    family: str | None
    herbs: list[HerbRef]
    matched_name: NameOut | None = Field(
        default=None, description="The name that matched the search query"
    )


class Identifiers(BaseModel):
    wfo_id: str
    ipni_id: str | None
    wcvp_plant_name_id: int | None
    gbif_key: int | None
    ncbi_tax_id: int | None
    powo_id: str | None
    wikidata_id: str | None


class IndicationOut(BaseModel):
    text: str
    use_category: str = Field(description="well_established_use | traditional_use — never merged")
    evidence: EvidenceRef
    provenance: list[ProvenanceOut]


class MonographSummary(BaseModel):
    document: str
    title: str
    url: str | None
    document_date: date | None
    use_categories: list[str]
    section_completeness: dict[str, str]
    interactions_section_states_none_reported: list[str] = Field(
        description="Use categories whose §4.5 text is 'None reported/known' (a regulator statement at the "
        "document date, not proof of safety)"
    )


class TaxonDetail(TaxonSummary):
    identifiers: Identifiers
    native_range: str | None
    names: list[NameOut]
    indications: list[IndicationOut]
    monographs: list[MonographSummary]
    provenance: list[ProvenanceOut]
    counts: dict[str, int] = Field(
        description="Evidence items by relation, active interaction statements"
    )


class Candidate(BaseModel):
    pharmaceutical_name: str
    common_name: str | None
    taxa: list[str] = Field(description="WFO IDs")
    matched_name: NameOut


class HerbResolution(BaseModel):
    query: str
    status: Literal["resolved", "ambiguous", "not_found"]
    herb: HerbRef | None = None
    taxa: list[TaxonSummary] = Field(default_factory=list)
    matched_name: NameOut | None = None
    candidates: list[Candidate] = Field(default_factory=list)
    note: str | None = None


# --------------------------------------------------------------------------- drugs


class DrugClassOut(BaseModel):
    code: str = Field(examples=["B01AA"])
    name: str
    level: int
    system: str = "ATC"


class DrugOut(BaseModel):
    rxcui: str = Field(examples=["11289"])
    name: str
    atc_classes: list[DrugClassOut]


class DrugDetail(DrugOut):
    provenance: list[ProvenanceOut]


class DrugResolveRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200, examples=["Coumadin"])
    allow_remote: bool = Field(
        default=True, description="Query RxNav if the drug is not yet in the database"
    )


class DrugResolution(BaseModel):
    query: str
    status: Literal["resolved", "not_found", "lookup_failed"]
    resolved_via: Literal["database", "rxnav"] | None = None
    drug: DrugOut | None = None
    note: str | None = None


# --------------------------------------------------------------------------- evidence


class EvidenceSummary(EvidenceRef):
    herbs: list[str] = Field(description="Pharmaceutical names of linked herbs")
    relations: list[str]
    metadata: dict[str, object]


class ChunkOut(BaseModel):
    section: str | None
    text: str


class EvidenceDetail(EvidenceSummary):
    content: list[ChunkOut] = Field(
        description="Stored source text (local database only, never redistributed)"
    )
    provenance: list[ProvenanceOut]


# --------------------------------------------------------------------------- interactions


class StatementOut(BaseModel):
    id: str
    role: Literal["decisive", "context"]
    statement_type: StatementType
    statement_type_note: str
    source_code: str
    source_section: str | None
    use_category: str
    matched_via: Literal["drug", "class"]
    drug: DrugOut | None = None
    drug_class: DrugClassOut | None = None
    object_label_verbatim: str
    subject_label_verbatim: str | None
    severity_wording: str | None = Field(
        description="Relayed verbatim from the source; never computed"
    )
    conditions: str | None
    mechanism: str | None
    excerpt: str | None
    subject_check: Literal[
        "not_applicable", "named_in_sentence", "interaction_section", "not_verified"
    ] = Field(
        description="Drug labels only: how the label's drug was confirmed as the subject of the sentence. "
        "'not_verified' statements are context only."
    )
    subject_check_note: str | None = None
    evidence: EvidenceRef
    provenance: list[ProvenanceOut]
    herbs: list[str]


class SourceSearched(BaseModel):
    source_code: str
    description: str
    retrieved_at: datetime | None
    used_for_classification: bool


class ClassificationOut(BaseModel):
    interaction_class: InteractionClass
    class_label: str
    finding: Finding
    finding_label: str
    explanation: str
    reasons: list[str]
    severity_wordings: list[str] = Field(
        description="Verbatim wording of decisive statements; HerbaGuard does not grade severity"
    )
    caveats: list[str]
    method: str = "deterministic rules v1 (docs/api/interaction-classification.md); no machine learning or LLM"


class DrugCheckResult(BaseModel):
    drug: DrugResolution
    classification: ClassificationOut
    decisive_statements: list[StatementOut]
    context_statements: list[StatementOut]
    sources_searched: list[SourceSearched]
    related_literature: dict[str, object]
    mechanism_paths: list[MechanismPathOut] = Field(
        default_factory=list,
        description="Herb → enzyme/transporter ← drug paths (Phase 4). Only paths with "
        "qualifies_for_class_b can produce class B, and only when no documented statement applies.",
    )


class InteractionCheckRequest(BaseModel):
    herb: str = Field(min_length=1, max_length=200, examples=["St John's wort"])
    drugs: list[str] = Field(min_length=1, max_length=20, examples=[["warfarin", "sertraline"]])
    allow_remote_drug_lookup: bool = Field(
        default=True,
        description="Resolve drugs not yet in the database through RxNav (with provenance)",
    )

    @field_validator("drugs")
    @classmethod
    def _non_empty(cls, value: list[str]) -> list[str]:
        cleaned = [v.strip() for v in value]
        if any(not v or len(v) > 200 for v in cleaned):
            msg = "Each drug name must be 1–200 characters."
            raise ValueError(msg)
        return cleaned


class InteractionCheckResponse(BaseModel):
    herb: HerbResolution
    results: list[DrugCheckResult]
    disclaimer: str


class HerbInteractionGroup(BaseModel):
    target: str = Field(description="Drug name or ATC class the statements are about")
    target_kind: Literal["drug", "class"]
    rxcui: str | None
    atc_code: str | None
    statement_types: dict[str, int]
    statements: list[StatementOut]


# --------------------------------------------------------------------------- sources


class SourceOut(BaseModel):
    code: str
    name: str
    provider: str
    homepage_url: str | None
    is_official: bool
    licence: str | None
    licence_status: str
    redistributable: bool
    last_run_status: str | None
    last_run_finished_at: datetime | None
    records: int


class CoverageRow(BaseModel):
    herb: HerbRef
    taxa: int
    monograph: str | None
    monograph_date: date | None
    fact_sheet: bool
    label_coverage: str | None
    evidence_items: dict[str, int]
    active_statements: dict[str, int]
    pubmed_by_type: dict[str, int]
    type_note: str = EvidenceTypeInfo.model_fields["note"].default
