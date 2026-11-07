"""Plants, drugs, drug classes, evidence, interactions, sources and coverage."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from herbaguard.api.schemas.common import ErrorResponse, Page
from herbaguard.api.schemas.resources import (
    CoverageRow,
    DrugClassOut,
    DrugDetail,
    DrugOut,
    DrugResolution,
    DrugResolveRequest,
    EvidenceDetail,
    EvidenceSummary,
    HerbInteractionGroup,
    HerbResolution,
    InteractionCheckRequest,
    InteractionCheckResponse,
    PlantCoverage,
    ProductLabelOut,
    SourceOut,
    TaxonDetail,
    TaxonSummary,
)
from herbaguard.core.config import Settings, get_settings
from herbaguard.core.db import get_session
from herbaguard.domain.enums import EvidenceRelation, EvidenceType, StatementType
from herbaguard.services import drugs as drug_service
from herbaguard.services import evidence as evidence_service
from herbaguard.services import interactions as interaction_service
from herbaguard.services import plants as plant_service
from herbaguard.services import product_labels as product_label_service

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
Limit = Annotated[int, Query(ge=1, le=100, description="Page size (1–100)")]
Offset = Annotated[int, Query(ge=0, le=100_000)]
SearchText = Annotated[str | None, Query(min_length=1, max_length=200, description="Search text")]
WfoId = Annotated[str, Path(pattern=r"^wfo-\d{10}$", examples=["wfo-0000728093"])]
SourceCode = Literal["ema_hmpc", "nccih", "openfda_label", "pubmed"]
ERRORS: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


# --------------------------------------------------------------------------- plants


@router.get(
    "/plants",
    response_model=Page[TaxonSummary],
    tags=["plants"],
    summary="Search plants (all name types)",
)
def search_plants(
    session: SessionDep, q: SearchText = None, limit: Limit = 20, offset: Offset = 0
) -> Page[TaxonSummary]:
    items, total = plant_service.search(session, q, limit=limit, offset=offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/plants/resolve",
    response_model=HerbResolution,
    tags=["plants"],
    summary="Resolve a name to one curated herb (or list candidates)",
)
def resolve_plant(
    session: SessionDep, name: Annotated[str, Query(min_length=1, max_length=200)]
) -> HerbResolution:
    return plant_service.resolve_herb(session, name)


@router.get("/plants/{wfo_id}", response_model=TaxonDetail, tags=["plants"], responses=ERRORS)
def plant_detail(session: SessionDep, wfo_id: WfoId) -> TaxonDetail:
    return plant_service.detail(session, wfo_id)


@router.get(
    "/plants/{wfo_id}/product-labels",
    response_model=Page[ProductLabelOut],
    tags=["plants", "product_labels"],
    summary="Stored NIH DSLD product labels for a plant (manufacturer information only)",
    description="Labels whose matched ingredient maps to this plant by an exact, resolved name. "
    "Product information, never clinical evidence or an interaction class. The NIH DSLD licence is "
    "unverified and the content is not redistributable.",
    responses=ERRORS,
)
def plant_product_labels(
    session: SessionDep, wfo_id: WfoId, limit: Limit = 20, offset: Offset = 0
) -> Page[ProductLabelOut]:
    items, total = product_label_service.list_for_plant(session, wfo_id, limit=limit, offset=offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/plants/{wfo_id}/interactions",
    response_model=list[HerbInteractionGroup],
    tags=["plants", "interactions"],
    summary="All stored interaction statements for a plant, grouped by drug or class",
    responses=ERRORS,
)
def plant_interactions(
    session: SessionDep,
    wfo_id: WfoId,
    statement_type: Annotated[list[StatementType] | None, Query()] = None,
    source: SourceCode | None = None,
) -> list[HerbInteractionGroup]:
    return interaction_service.herb_overview(
        session,
        wfo_id,
        statement_types=[t.value for t in statement_type] if statement_type else None,
        source_code=source,
    )


# --------------------------------------------------------------------------- drugs


@router.get(
    "/drugs",
    response_model=Page[DrugOut],
    tags=["drugs"],
    summary="Search drugs in the HerbaGuard index",
)
def search_drugs(
    session: SessionDep, q: SearchText = None, limit: Limit = 20, offset: Offset = 0
) -> Page[DrugOut]:
    items, total = drug_service.search(session, q, limit=limit, offset=offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post(
    "/drugs/resolve",
    response_model=DrugResolution,
    tags=["drugs"],
    summary="Normalise a drug name (incl. brand names) to an RxNorm ingredient",
)
def resolve_drug(
    session: SessionDep, settings: SettingsDep, body: DrugResolveRequest
) -> DrugResolution:
    return drug_service.resolve(session, settings, body.name, allow_remote=body.allow_remote)


@router.get("/drugs/{rxcui}", response_model=DrugDetail, tags=["drugs"], responses=ERRORS)
def drug_detail(
    session: SessionDep, rxcui: Annotated[str, Path(pattern=r"^\d{1,10}$")]
) -> DrugDetail:
    return drug_service.detail(session, rxcui)


class DrugClassDetail(BaseModel):
    drug_class: DrugClassOut
    drugs: list[DrugOut]


@router.get(
    "/drug-classes/{code}", response_model=DrugClassDetail, tags=["drugs"], responses=ERRORS
)
def drug_class_detail(
    session: SessionDep,
    code: Annotated[str, Path(pattern=r"^[A-Z](\d{2}([A-Z]([A-Z](\d{2})?)?)?)?$")],
) -> DrugClassDetail:
    cls, drugs = drug_service.drug_class(session, code)
    return DrugClassDetail(drug_class=cls, drugs=drugs)


# --------------------------------------------------------------------------- evidence


@router.get("/evidence", response_model=Page[EvidenceSummary], tags=["evidence"], responses=ERRORS)
def list_evidence(
    session: SessionDep,
    wfo_id: Annotated[str | None, Query(pattern=r"^wfo-\d{10}$")] = None,
    herb: Annotated[
        str | None,
        Query(max_length=200, description="EMA pharmaceutical name, e.g. 'Hyperici herba'"),
    ] = None,
    source: SourceCode | None = None,
    evidence_type: Annotated[
        list[EvidenceType] | None,
        Query(description="Study design / document type — not a quality rating"),
    ] = None,
    relation: EvidenceRelation | None = None,
    year_from: Annotated[int | None, Query(ge=1500, le=2100)] = None,
    year_to: Annotated[int | None, Query(ge=1500, le=2100)] = None,
    q: SearchText = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page[EvidenceSummary]:
    items, total = evidence_service.list_evidence(
        session,
        wfo_id=wfo_id,
        herb=herb,
        source_code=source,
        evidence_types=[t.value for t in evidence_type] if evidence_type else None,
        relation=relation.value if relation else None,
        year_from=year_from,
        year_to=year_to,
        query=q,
        limit=limit,
        offset=offset,
    )
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/evidence/{evidence_id}", response_model=EvidenceDetail, tags=["evidence"], responses=ERRORS
)
def evidence_detail(session: SessionDep, evidence_id: uuid.UUID) -> EvidenceDetail:
    return evidence_service.detail(session, evidence_id)


# --------------------------------------------------------------------------- interactions


@router.post(
    "/interactions/check",
    response_model=InteractionCheckResponse,
    tags=["interactions"],
    summary="Classify one herb against one or more drugs (deterministic rules, classes A–E)",
    responses={
        409: {
            "model": ErrorResponse,
            "description": "The herb name is ambiguous; candidates in details",
        },
        422: {"model": ErrorResponse},
    },
)
def check_interactions(
    session: SessionDep, settings: SettingsDep, body: InteractionCheckRequest
) -> InteractionCheckResponse:
    return interaction_service.check(
        session,
        settings,
        herb_query=body.herb,
        drug_queries=body.drugs,
        allow_remote=body.allow_remote_drug_lookup,
    )


# --------------------------------------------------------------------------- sources & coverage


@router.get(
    "/sources",
    response_model=list[SourceOut],
    tags=["sources"],
    summary="Data sources, licences and last runs",
)
def list_sources(session: SessionDep) -> list[SourceOut]:
    return evidence_service.sources(session)


@router.get(
    "/coverage/plants",
    response_model=PlantCoverage,
    tags=["sources"],
    summary="Per-taxon coverage by kind of material",
    description=(
        "For every taxon in the index: taxonomic record, regulatory material, indexed "
        "literature, supplementary-source mappings and manufacturer product labels, reported "
        "separately. A product label or a taxonomic record is not clinical evidence."
    ),
)
def plant_coverage(session: SessionDep) -> PlantCoverage:
    return plant_service.plant_coverage(session)


@router.get(
    "/coverage",
    response_model=list[CoverageRow],
    tags=["sources"],
    summary="Per-herb data coverage",
)
def coverage(session: SessionDep) -> list[CoverageRow]:
    return evidence_service.coverage(session)
