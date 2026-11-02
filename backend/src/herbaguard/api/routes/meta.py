"""Service metadata, including the medical disclaimer every client must display."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from herbaguard import __version__
from herbaguard.api.schemas import MetaResponse
from herbaguard.core.config import DISCLAIMER, Settings, get_settings

router = APIRouter(tags=["meta"])


@router.get("/meta", response_model=MetaResponse, summary="Service metadata and disclaimer")
def meta(settings: Annotated[Settings, Depends(get_settings)]) -> MetaResponse:
    return MetaResponse(
        name="HerbaGuard",
        version=__version__,
        environment=settings.environment.value,
        api_version="v1",
        disclaimer=DISCLAIMER,
    )
