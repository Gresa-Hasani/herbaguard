"""Shared API response schemas (error envelope, pagination, health, meta)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str = Field(description="Stable machine-readable error code.")
    message: str = Field(description="Human-readable explanation.")
    details: Any | None = Field(default=None, description="Optional structured context.")
    request_id: str | None = Field(default=None, description="Echo of the X-Request-ID header.")


class ErrorResponse(BaseModel):
    error: ErrorBody


class Page[T](BaseModel):
    """Standard pagination envelope for list endpoints."""

    items: list[T]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadinessCheck(BaseModel):
    name: str
    status: Literal["ok", "error"]
    detail: str | None = None


class ReadinessResponse(BaseModel):
    status: Literal["ok", "degraded"]
    checks: list[ReadinessCheck]


class MetaResponse(BaseModel):
    name: str
    version: str
    environment: str
    api_version: str
    disclaimer: str
