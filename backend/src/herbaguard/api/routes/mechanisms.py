"""Mechanism layer (Phase 4): enzymes/transporters, herb mechanism graphs, herb–drug paths."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from herbaguard.api.schemas.common import ErrorResponse
from herbaguard.api.schemas.mechanism_core import TargetOut
from herbaguard.api.schemas.mechanisms import (
    HerbMechanismGraph,
    MechanismPathsRequest,
    MechanismPathsResponse,
    TargetDetail,
)
from herbaguard.core.config import Settings, get_settings
from herbaguard.core.db import get_session
from herbaguard.services import mechanisms as mechanism_service

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
WfoId = Annotated[str, Path(pattern=r"^wfo-\d{10}$", examples=["wfo-0000728093"])]
Symbol = Annotated[str, Path(pattern=r"^[A-Za-z0-9-]{2,32}$", examples=["CYP3A"])]
RoleFilter = Literal[
    "substrate", "sensitive_substrate", "moderately_sensitive_substrate", "inhibitor", "inducer"
]
ERRORS: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


@router.get(
    "/targets",
    response_model=list[TargetOut],
    tags=["mechanisms"],
    summary="Enzymes and transporters in the mechanism layer, with edge counts",
)
def list_targets(session: SessionDep) -> list[TargetOut]:
    return mechanism_service.list_targets(session)


@router.get(
    "/targets/{symbol}",
    response_model=TargetDetail,
    tags=["mechanisms"],
    summary="One enzyme/transporter: herb effects and drug roles, each with provenance",
    responses=ERRORS,
)
def target_detail(
    session: SessionDep,
    symbol: Symbol,
    role: RoleFilter | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> TargetDetail:
    return mechanism_service.target_detail(session, symbol, role=role, limit=limit)


@router.get(
    "/plants/{wfo_id}/mechanisms",
    response_model=HerbMechanismGraph,
    tags=["plants", "mechanisms"],
    summary="Knowledge-graph view: herb → constituent → enzyme/transporter ← drug",
    responses=ERRORS,
)
def plant_mechanisms(
    session: SessionDep,
    wfo_id: WfoId,
    include_drugs: Annotated[
        bool, Query(description="Add drugs that are substrates of the affected targets")
    ] = True,
) -> HerbMechanismGraph:
    return mechanism_service.herb_graph(session, wfo_id, include_drugs=include_drugs)


@router.post(
    "/mechanisms/paths",
    response_model=MechanismPathsResponse,
    tags=["mechanisms", "interactions"],
    summary="All mechanism paths between one herb and one drug, with the class-B rule assessment",
    responses={
        409: {"model": ErrorResponse, "description": "The herb name is ambiguous"},
        422: {"model": ErrorResponse},
    },
)
def mechanism_paths(
    session: SessionDep, settings: SettingsDep, body: MechanismPathsRequest
) -> MechanismPathsResponse:
    return mechanism_service.paths(
        session,
        settings,
        herb_query=body.herb,
        drug_query=body.drug,
        allow_remote=body.allow_remote_drug_lookup,
    )
