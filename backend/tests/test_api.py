"""API foundation: health, meta, error envelope and request IDs."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Query
from fastapi.testclient import TestClient

from herbaguard.core.config import DISCLAIMER
from herbaguard.core.errors import AmbiguousEntityError


def test_liveness(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": [{"name": "database", "status": "ok", "detail": None}],
    }


def test_readiness_reports_database_failure(make_client: Callable[..., TestClient]) -> None:
    response = make_client(database_ok=False).get("/api/v1/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"][0] == {
        "name": "database",
        "status": "error",
        "detail": "Database unreachable",
    }


def test_meta_contains_disclaimer(client: TestClient) -> None:
    body = client.get("/api/v1/meta").json()
    assert body["name"] == "HerbaGuard"
    assert body["api_version"] == "v1"
    assert body["environment"] == "test"
    assert body["disclaimer"] == DISCLAIMER
    assert "not medical advice" in body["disclaimer"]


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist", headers={"X-Request-ID": "abc-123"})
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Not Found",
            "details": None,
            "request_id": "abc-123",
        }
    }


def test_request_id_is_generated_when_missing(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    request_id = response.headers["X-Request-ID"]
    assert len(request_id) == 32
    assert request_id.isalnum()


def test_unsafe_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"X-Request-ID": "bad id\nwith newline"})
    assert response.headers["X-Request-ID"] != "bad id\nwith newline"
    assert len(response.headers["X-Request-ID"]) == 32


def _client_with_test_routes(make_client: Callable[..., TestClient]) -> TestClient:
    client = make_client()
    router = APIRouter()

    @router.get("/api/v1/_test/validate")
    def validate(limit: int = Query(ge=1, le=10)) -> dict[str, int]:
        return {"limit": limit}

    @router.get("/api/v1/_test/ambiguous")
    def ambiguous() -> None:
        raise AmbiguousEntityError(
            "Several taxa match 'ginseng'.",
            details={"candidates": ["wfo-0000263606", "wfo-0000948117"]},
        )

    @router.get("/api/v1/_test/crash")
    def crash() -> None:
        raise RuntimeError("boom")

    client.app.include_router(router)  # type: ignore[attr-defined]
    return client


def test_validation_error_envelope(make_client: Callable[..., TestClient]) -> None:
    response = _client_with_test_routes(make_client).get("/api/v1/_test/validate?limit=0")
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["location"] == ["query", "limit"]


def test_domain_error_envelope(make_client: Callable[..., TestClient]) -> None:
    response = _client_with_test_routes(make_client).get("/api/v1/_test/ambiguous")
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "ambiguous_entity"
    assert error["details"] == {"candidates": ["wfo-0000263606", "wfo-0000948117"]}


def test_unhandled_error_does_not_leak_details(make_client: Callable[..., TestClient]) -> None:
    response = _client_with_test_routes(make_client).get("/api/v1/_test/crash")
    assert response.status_code == 500
    error = response.json()["error"]
    assert error == {
        "code": "internal_error",
        "message": "An unexpected error occurred.",
        "details": None,
        "request_id": response.headers["X-Request-ID"],
    }


def test_openapi_document_is_served(client: TestClient) -> None:
    spec = client.get("/api/openapi.json").json()
    assert spec["info"]["title"] == "HerbaGuard API"
    assert "/api/v1/health/ready" in spec["paths"]
