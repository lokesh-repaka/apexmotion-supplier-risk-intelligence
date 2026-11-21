"""Unit tests for FastAPI application skeleton, middleware, and exception handlers."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel


def test_app_instantiation_and_metadata():
    """Verify that the FastAPI app instance is configured with expected metadata."""
    from src.api.main import app

    assert isinstance(app, FastAPI)
    assert app.title == "ApexMotion Supplier Risk Intelligence Platform"
    assert app.version == "0.1.0"


def test_request_id_middleware_generates_and_attaches_headers():
    """Verify X-Request-ID and X-Trace-ID headers are generated and attached to responses."""
    from src.api.main import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/health-check-non-existent")

    assert "x-request-id" in response.headers
    assert "x-trace-id" in response.headers
    assert response.headers["x-request-id"] == response.headers["x-trace-id"]
    assert len(response.headers["x-request-id"]) > 0


def test_request_id_middleware_preserves_client_request_id():
    """Verify client-supplied X-Request-ID is preserved and propagated to response headers."""
    from src.api.main import app

    client = TestClient(app, raise_server_exceptions=False)
    client_req_id = "req-apex-client-uuid-9999"
    response = client.get("/health-check-non-existent", headers={"X-Request-ID": client_req_id})

    assert response.headers["x-request-id"] == client_req_id
    assert response.headers["x-trace-id"] == client_req_id


def test_cors_headers_on_preflight():
    """Verify CORS headers are returned for allowed origins."""
    from src.api.main import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.options(
        "/api/v1/alerts",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,x-request-id",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_404_error_response_standard_schema():
    """Verify 404 errors adhere to CLAUDE.md Section 10 error response format."""
    from src.api.main import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/v1/missing-resource-endpoint")

    assert response.status_code == 404
    data = response.json()

    assert "error" in data
    error = data["error"]
    assert error["code"] == "NOT_FOUND"
    assert "message" in error
    assert "trace_id" in error
    assert error["trace_id"] == response.headers["x-trace-id"]


def test_validation_error_standard_schema():
    """Verify request validation errors return 400 with VALIDATION_ERROR code."""
    from src.api.main import app

    class DummyPayload(BaseModel):
        supplier_id: str
        stock_units: int

    @app.post("/test-validation-route")
    def dummy_route(payload: DummyPayload):
        return {"status": "ok", "supplier_id": payload.supplier_id}

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/test-validation-route", json={"supplier_id": "SUP-1", "stock_units": "invalid_integer"}
    )

    assert response.status_code == 400
    data = response.json()

    assert "error" in data
    error = data["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert "message" in error
    assert "trace_id" in error


def test_unhandled_exception_does_not_leak_stack_trace():
    """Verify 500 errors return standard INTERNAL_ERROR schema and do not leak stack traces."""
    from src.api.main import app

    @app.get("/test-internal-crash")
    def crash_route():
        raise RuntimeError("Sensitive internal database credential failure!")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/test-internal-crash")

    assert response.status_code == 500
    data = response.json()

    assert "error" in data
    error = data["error"]
    assert error["code"] == "INTERNAL_ERROR"
    assert "Sensitive internal database credential failure!" not in error["message"]
    assert "trace_id" in error


def test_custom_app_exception_standard_schema():
    """Verify custom AppException returns the exact status_code and error code specified."""
    from src.api.exceptions import AppException
    from src.api.main import app

    @app.get("/test-custom-app-exception")
    def custom_error_route():
        raise AppException(
            code="HITL_TOKEN_EXPIRED",
            message="The approval token has expired. Please request a new one.",
            status_code=403,
        )

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/test-custom-app-exception")

    assert response.status_code == 403
    data = response.json()

    assert "error" in data
    error = data["error"]
    assert error["code"] == "HITL_TOKEN_EXPIRED"
    assert error["message"] == "The approval token has expired. Please request a new one."
    assert "trace_id" in error
