"""Unit tests for liveness and readiness health routes.

Verifies:
- GET /health: Public liveness probe, zero I/O, returns 200 and version metadata.
- GET /health/ready: Deep readiness probe checking Aurora, Neptune, Kafka, Redis.
- HTTP 503 status when any critical dependency fails.
- Isolation and timeout resilience.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_liveness_health_check_returns_200():
    """Verify GET /health returns 200, status 'healthy', and version metadata with zero I/O."""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == "0.1.0"
    assert "timestamp" in data
    assert "x-request-id" in response.headers
    assert "x-trace-id" in response.headers


def test_readiness_check_all_healthy_returns_200():
    """Verify GET /health/ready returns 200 and 'ready' when all services are healthy."""
    mock_checks = {
        "database": {"status": "healthy", "latency_ms": 1.5},
        "neptune": {"status": "healthy", "latency_ms": 3.2},
        "kafka": {"status": "healthy", "latency_ms": 0.9},
        "redis": {"status": "healthy", "latency_ms": 0.4},
    }

    with patch(
        "src.api.routes.health.check_all_dependencies",
        new=AsyncMock(return_value=mock_checks),
    ):
        response = client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert "timestamp" in data
        assert "dependencies" in data
        deps = data["dependencies"]
        assert deps["database"]["status"] == "healthy"
        assert deps["neptune"]["status"] == "healthy"
        assert deps["kafka"]["status"] == "healthy"
        assert deps["redis"]["status"] == "healthy"


def test_readiness_check_database_failure_returns_503():
    """Verify GET /health/ready returns 503 when the database dependency fails."""
    mock_checks = {
        "database": {
            "status": "unhealthy",
            "error": "Connection to Aurora PostgreSQL refused",
            "latency_ms": 50.1,
        },
        "neptune": {"status": "healthy", "latency_ms": 2.1},
        "kafka": {"status": "healthy", "latency_ms": 1.0},
        "redis": {"status": "healthy", "latency_ms": 0.5},
    }

    with patch(
        "src.api.routes.health.check_all_dependencies",
        new=AsyncMock(return_value=mock_checks),
    ):
        response = client.get("/health/ready")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["dependencies"]["database"]["status"] == "unhealthy"
        assert "Connection to Aurora" in data["dependencies"]["database"]["error"]
        assert data["dependencies"]["neptune"]["status"] == "healthy"


def test_readiness_check_multiple_failures_returns_503():
    """Verify GET /health/ready returns 503 and reports all failures when multiple services fail."""
    mock_checks = {
        "database": {"status": "healthy", "latency_ms": 1.2},
        "neptune": {
            "status": "unhealthy",
            "error": "Neptune Bolt connection timeout",
            "latency_ms": 2000.0,
        },
        "kafka": {"status": "unhealthy", "error": "Kafka broker unreachable", "latency_ms": 1500.0},
        "redis": {"status": "healthy", "latency_ms": 0.6},
    }

    with patch(
        "src.api.routes.health.check_all_dependencies",
        new=AsyncMock(return_value=mock_checks),
    ):
        response = client.get("/health/ready")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["dependencies"]["neptune"]["status"] == "unhealthy"
        assert data["dependencies"]["kafka"]["status"] == "unhealthy"
        assert data["dependencies"]["database"]["status"] == "healthy"
        assert data["dependencies"]["redis"]["status"] == "healthy"


def test_liveness_healthy_even_when_dependencies_fail():
    """Verify GET /health (liveness) stays 200 healthy even if deep infrastructure is down."""
    mock_checks = {
        "database": {"status": "unhealthy", "error": "Crash"},
        "neptune": {"status": "unhealthy", "error": "Crash"},
        "kafka": {"status": "unhealthy", "error": "Crash"},
        "redis": {"status": "unhealthy", "error": "Crash"},
    }

    with patch(
        "src.api.routes.health.check_all_dependencies",
        new=AsyncMock(return_value=mock_checks),
    ):
        # Liveness must NOT call dependencies and must return 200
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_individual_dependency_checker_timeout_resilience():
    """Verify check_dependency helper handles exceptions and returns unhealthy dictionary."""
    from src.api.routes.health import check_dependency

    async def faulty_probe():
        raise ConnectionResetError("Socket abruptly closed by peer")

    result = await check_dependency("test_service", faulty_probe)
    assert result["status"] == "unhealthy"
    assert "Socket abruptly closed" in result["error"]
    assert "latency_ms" in result


def test_default_readiness_probe_with_offline_settings():
    """Verify GET /health/ready returns 200 without mocks using default offline mock settings."""
    response = client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert "database" in data["dependencies"]
    assert "neptune" in data["dependencies"]
    assert "kafka" in data["dependencies"]
    assert "redis" in data["dependencies"]
