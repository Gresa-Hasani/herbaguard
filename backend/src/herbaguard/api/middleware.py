"""Request-ID middleware: accepts or generates ``X-Request-ID`` and binds it to the log context."""

from __future__ import annotations

import re
import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from herbaguard.core.logging import get_logger

REQUEST_ID_HEADER = "X-Request-ID"
# Accept client-supplied IDs only if they are short and harmless, to avoid log injection.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

logger = get_logger("herbaguard.http")


def resolve_request_id(candidate: str | None) -> str:
    if candidate and _SAFE_REQUEST_ID.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 1)

        response.headers[REQUEST_ID_HEADER] = request_id
        # Only method, path and status are logged — never query strings or bodies, which may
        # contain medication names typed by users.
        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response
