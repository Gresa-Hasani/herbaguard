"""FastAPI application factory. Run with ``uvicorn herbaguard.main:app``."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from herbaguard import __version__
from herbaguard.api.error_handlers import register_error_handlers
from herbaguard.api.middleware import REQUEST_ID_HEADER, RequestContextMiddleware
from herbaguard.api.routes import api_router
from herbaguard.core.config import DISCLAIMER, Settings, get_settings
from herbaguard.core.logging import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title="HerbaGuard API",
        version=__version__,
        description=(
            "Evidence-based herb–drug interaction and phytotherapy evidence API "
            f"(EthnoHack 2026, Track 04).\n\n**Disclaimer:** {DISCLAIMER}"
        ),
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
    )
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
