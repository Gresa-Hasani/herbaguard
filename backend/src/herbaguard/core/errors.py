"""Domain-level exceptions and the error codes exposed in the API error envelope."""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    BAD_REQUEST = "bad_request"
    VALIDATION_ERROR = "validation_error"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    AMBIGUOUS_ENTITY = "ambiguous_entity"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    SERVICE_UNAVAILABLE = "service_unavailable"
    INTERNAL_ERROR = "internal_error"


class HerbaGuardError(Exception):
    """Base class for errors that map to a well-defined API response."""

    status_code: int = 500
    code: ErrorCode = ErrorCode.INTERNAL_ERROR

    def __init__(self, message: str, *, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(HerbaGuardError):
    status_code = 404
    code = ErrorCode.NOT_FOUND


class AmbiguousEntityError(HerbaGuardError):
    """Raised when an input name maps to several candidates (e.g. "ginseng")."""

    status_code = 409
    code = ErrorCode.AMBIGUOUS_ENTITY


class UpstreamUnavailableError(HerbaGuardError):
    """An external data source could not be reached or returned an unusable response."""

    status_code = 502
    code = ErrorCode.UPSTREAM_UNAVAILABLE


class ServiceUnavailableError(HerbaGuardError):
    status_code = 503
    code = ErrorCode.SERVICE_UNAVAILABLE
