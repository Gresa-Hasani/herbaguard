"""Map every error to the standard envelope ``{"error": {code, message, details, request_id}}``."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from herbaguard.api.middleware import REQUEST_ID_HEADER
from herbaguard.api.schemas import ErrorBody, ErrorResponse
from herbaguard.core.errors import ErrorCode, HerbaGuardError
from herbaguard.core.logging import get_logger

logger = get_logger("herbaguard.errors")

_HTTP_STATUS_CODES: dict[int, ErrorCode] = {
    400: ErrorCode.BAD_REQUEST,
    404: ErrorCode.NOT_FOUND,
    409: ErrorCode.CONFLICT,
    422: ErrorCode.VALIDATION_ERROR,
    503: ErrorCode.SERVICE_UNAVAILABLE,
}


def _request_id(request: Request) -> str | None:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) else None


def error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
) -> JSONResponse:
    request_id = _request_id(request)
    body = ErrorResponse(
        error=ErrorBody(
            code=code,
            message=message,
            details=jsonable_encoder(details),
            request_id=request_id,
        )
    )
    # Unhandled exceptions are answered by Starlette's outermost error middleware, which runs
    # outside RequestContextMiddleware — so the header is also set here.
    headers = {REQUEST_ID_HEADER: request_id} if request_id else None
    return JSONResponse(status_code=status_code, content=body.model_dump(), headers=headers)


async def _handle_domain_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, HerbaGuardError)  # noqa: S101 - narrowing for type checkers
    return error_response(
        request,
        status_code=exc.status_code,
        code=exc.code.value,
        message=exc.message,
        details=exc.details,
    )


async def _handle_http_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101
    code = _HTTP_STATUS_CODES.get(exc.status_code, ErrorCode.BAD_REQUEST)
    if exc.status_code >= 500:
        code = ErrorCode.INTERNAL_ERROR
    return error_response(
        request,
        status_code=exc.status_code,
        code=code.value,
        message=str(exc.detail),
    )


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    details = [
        {"location": list(err.get("loc", ())), "message": err.get("msg"), "type": err.get("type")}
        for err in exc.errors()
    ]
    return error_response(
        request,
        status_code=422,
        code=ErrorCode.VALIDATION_ERROR.value,
        message="The request is invalid.",
        details=details,
    )


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error", path=request.url.path, error_type=type(exc).__name__)
    return error_response(
        request,
        status_code=500,
        code=ErrorCode.INTERNAL_ERROR.value,
        message="An unexpected error occurred.",
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HerbaGuardError, _handle_domain_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)
