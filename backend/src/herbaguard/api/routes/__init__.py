"""Versioned API routers."""

from fastapi import APIRouter

from herbaguard.api.routes import assistant, catalog, health, mechanisms, meta

API_VERSION = "v1"

api_router = APIRouter(prefix=f"/api/{API_VERSION}")
api_router.include_router(health.router)
api_router.include_router(meta.router)
api_router.include_router(catalog.router)
api_router.include_router(mechanisms.router)
api_router.include_router(assistant.router)
