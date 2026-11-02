"""API request/response schemas, one module per resource."""

from herbaguard.api.schemas.common import (
    ErrorBody,
    ErrorResponse,
    HealthResponse,
    MetaResponse,
    Page,
    ReadinessCheck,
    ReadinessResponse,
)

__all__ = [
    "ErrorBody",
    "ErrorResponse",
    "HealthResponse",
    "MetaResponse",
    "Page",
    "ReadinessCheck",
    "ReadinessResponse",
]
