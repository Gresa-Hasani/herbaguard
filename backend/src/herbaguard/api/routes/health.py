"""Liveness and readiness probes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.exc import SQLAlchemyError

from herbaguard.api.schemas import HealthResponse, ReadinessCheck, ReadinessResponse
from herbaguard.core.db import check_database
from herbaguard.core.logging import get_logger

router = APIRouter(prefix="/health", tags=["health"])
logger = get_logger("herbaguard.health")


def get_database_check() -> Callable[[], bool]:
    """Dependency so tests can replace the database probe."""
    return check_database


@router.get("", response_model=HealthResponse, summary="Liveness probe")
def liveness() -> HealthResponse:
    return HealthResponse()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe (checks the database)",
    responses={503: {"model": ReadinessResponse}},
)
def readiness(
    response: Response,
    database_check: Annotated[Callable[[], bool], Depends(get_database_check)],
) -> ReadinessResponse:
    try:
        database_check()
        checks = [ReadinessCheck(name="database", status="ok")]
    except (SQLAlchemyError, OSError) as exc:
        logger.warning("readiness_database_failed", error_type=type(exc).__name__)
        checks = [ReadinessCheck(name="database", status="error", detail="Database unreachable")]

    if all(check.status == "ok" for check in checks):
        return ReadinessResponse(status="ok", checks=checks)
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="degraded", checks=checks)
