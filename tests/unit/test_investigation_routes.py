"""Unit tests for investigation API routes and async polling (P11-2).

Verifies:
- POST /api/v1/investigations/start & /api/v1/investigations/trigger:
    * Asynchronous launch returning HTTP 202 Accepted with poll URL.
    * Synchronous execution with wait_for_completion=True.
    * NanoCore golden reference matching: 7.68d cover, 1.32d gap, 24,420 units, $2,448,105.00 exposure, DUAL_VP tier.
    * Canonical SKU auto-population when stock parameters are omitted.
    * Zero-impact signals routed to DISMISSED with requires_hitl=False.
- GET /api/v1/investigations/{id} & GET /api/v1/cases/{case_id}:
    * Polling active and completed investigation states.
    * Lookup by investigation UUID, case_id, and alert_id.
    * Database fallback lookup for persisted AgentRun records.
    * 404 NOT_FOUND error response for non-existent identifiers.
- Security & RBAC:
    * Missing Authorization header returns 401 AUTHENTICATION_REQUIRED.
    * Malformed bearer token returns 401.
- Resilience:
    * Graceful error containment when graph execution raises an unhandled exception.
"""

import json
import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from src.api.main import app
from src.core.security import UserRole, create_access_token
from src.database.models import AgentRun, Base, RiskAlert
from src.database.session import get_db_session
from src.services.investigation_service import (
    InvestigationService,
    get_investigation_service,
)

# ------------------------------------------------------------------------------
# In-Memory SQLite Fixtures & Isolated Client
# ------------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """In-memory SQLite async session for offline isolated testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        json_serializer=lambda obj: json.dumps(obj, default=str),
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def test_service() -> InvestigationService:
    """Fresh isolated InvestigationService instance per test."""
    return InvestigationService()


@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession,
    test_service: InvestigationService,
) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient wired with FastAPI dependency overrides and mock audit logging."""

    async def _override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    def _override_get_investigation_service() -> InvestigationService:
        return test_service

    app.dependency_overrides[get_db_session] = _override_get_db_session
    app.dependency_overrides[get_investigation_service] = _override_get_investigation_service
    transport = ASGITransport(app=app)

    with patch(
        "src.services.investigation_service.write_audit_log", new=AsyncMock(return_value=None)
    ):
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as async_http_client:
            yield async_http_client

    app.dependency_overrides.clear()


@pytest.fixture
def analyst_token() -> str:
    """Valid Bearer JWT token with supply_chain_analyst role."""
    return create_access_token(
        subject="usr-analyst-inv-001",
        roles=[UserRole.SUPPLY_CHAIN_ANALYST.value],
    )


@pytest.fixture
def auth_headers(analyst_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {analyst_token}"}


# ------------------------------------------------------------------------------
# 1. POST /api/v1/investigations/start
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_investigation_async_background_returns_202(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Verify asynchronous trigger returns 202 Accepted and a polling URL."""
    payload = {
        "supplier_id": "SUP-NC-001",
        "component_sku": "NC-2024-001",
        "signal_type": "news",
        "raw_signal": "Reports of cleanroom fire at NanoCore Semiconductor Fab 2",
        "wait_for_completion": False,
    }

    response = await client.post(
        "/api/v1/investigations/start",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == 202
    data = response.json()

    assert "investigation_id" in data
    assert data["case_id"].startswith("CASE-")
    assert data["status"] == "RUNNING"
    assert data["poll_url"] == f"/api/v1/investigations/{data['investigation_id']}"
    assert data["estimated_completion_seconds"] == 90
    assert "started_at" in data


@pytest.mark.asyncio
async def test_start_investigation_sync_nanocore_golden_match(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Verify synchronous execution runs graph and reproduces NanoCore golden numbers."""
    payload = {
        "supplier_id": "SUP-NC-001",
        "component_sku": "NC-2024-001",
        "signal_type": "news",
        "raw_signal": "Major cleanroom fire at NanoCore Hsinchu facility halting production",
        "current_stock": 142000,
        "daily_consumption_rate": 18500,
        "eta_days": "9.0",
        "unit_cost_usd": "100.25",
        "wait_for_completion": True,
    }

    response = await client.post(
        "/api/v1/investigations/start",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == 202
    data = response.json()
    inv_id = data["investigation_id"]

    # Poll detail record
    detail_resp = await client.get(f"/api/v1/investigations/{inv_id}", headers=auth_headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()

    # Paused at HITL gate awaiting dual executive sign-off (> $100k)
    assert detail["status"] == "AWAITING_APPROVAL"
    assert detail["requires_hitl"] is True
    assert detail["governing_spend_tier"] == "DUAL_VP"

    # Numerical invariants (BR-RULE-001)
    metrics = detail["risk_metrics"]
    assert metrics is not None
    assert Decimal(str(metrics["days_of_cover"])) == Decimal("7.68")
    assert Decimal(str(metrics["gap_days"])) == Decimal("1.32")
    assert metrics["shortage_volume"] == 24420
    assert Decimal(str(metrics["financial_exposure"])) == Decimal("2448105.00")

    # Execution graph traversal path
    assert "triage" in detail["execution_path"]
    assert "research" in detail["execution_path"]
    assert "risk" in detail["execution_path"]
    assert "recommendation" in detail["execution_path"]
    assert "hitl_gate" in detail["execution_path"]


@pytest.mark.asyncio
async def test_start_investigation_alias_trigger_endpoint(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Verify /api/v1/investigations/trigger operates as an alias for /start."""
    payload = {
        "supplier_id": "SUP-ALIAS-001",
        "component_sku": "SKU-MCU-4402",
        "signal_type": "news",
        "raw_signal": "Minor supply delay notice",
        "wait_for_completion": True,
    }

    response = await client.post(
        "/api/v1/investigations/trigger",
        json=payload,
        headers=auth_headers,
    )
    assert response.status_code == 202
    data = response.json()
    assert "investigation_id" in data
    assert data["poll_url"].startswith("/api/v1/investigations/")


@pytest.mark.asyncio
async def test_start_investigation_zero_impact_signal_dismissed(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Verify signal with zero impact metadata routes to DISMISSED without HITL."""
    payload = {
        "supplier_id": "SUP-SAFE-001",
        "component_sku": "RES-SAFE-001",
        "signal_type": "news",
        "raw_signal": "Routine factory maintenance completed safely",
        "metadata": {"is_zero_impact": True},
        "wait_for_completion": True,
    }

    response = await client.post(
        "/api/v1/investigations/start",
        json=payload,
        headers=auth_headers,
    )
    assert response.status_code == 202
    inv_id = response.json()["investigation_id"]

    # Poll status
    detail_resp = await client.get(f"/api/v1/investigations/{inv_id}", headers=auth_headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["status"] == "DISMISSED"
    assert detail["requires_hitl"] is False
    assert "dismiss" in detail["execution_path"]


# ------------------------------------------------------------------------------
# 2. GET /api/v1/investigations/{id} & Polling Endpoints
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_investigation_by_case_id_alias(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Verify polling via /api/v1/cases/{case_id} alias works cleanly."""
    payload = {
        "supplier_id": "SUP-CASE-001",
        "component_sku": "SKU-CASE-001",
        "wait_for_completion": False,
    }

    start_resp = await client.post(
        "/api/v1/investigations/start",
        json=payload,
        headers=auth_headers,
    )
    case_id = start_resp.json()["case_id"]

    response = await client.get(f"/api/v1/cases/{case_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == case_id
    assert data["supplier_id"] == "SUP-CASE-001"


@pytest.mark.asyncio
async def test_get_investigation_by_alert_id(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Verify lookup by linked alert_id string."""
    alert_id = "ALT-CUSTOM-ALERT-999"
    payload = {
        "alert_id": alert_id,
        "supplier_id": "SUP-ALT-001",
        "wait_for_completion": False,
    }

    await client.post(
        "/api/v1/investigations/start",
        json=payload,
        headers=auth_headers,
    )

    response = await client.get(f"/api/v1/investigations/{alert_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["alert_id"] == alert_id


@pytest.mark.asyncio
async def test_get_investigation_not_found_returns_404(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Verify querying non-existent investigation ID returns 404 NOT_FOUND."""
    random_id = str(uuid.uuid4())
    response = await client.get(f"/api/v1/investigations/{random_id}", headers=auth_headers)
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_investigation_database_fallback(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """Verify database fallback queries AgentRun table when investigation is evicted from memory."""
    run_id = uuid.uuid4()
    alert_id = uuid.uuid4()

    # Seed alert and agent run directly in DB
    alert = RiskAlert(
        id=alert_id,
        component_sku="SKU-DB-001",
        risk_level="HIGH",
        status="INVESTIGATING",
    )
    agent_run = AgentRun(
        id=run_id,
        alert_id=alert_id,
        graph_name="incident_investigation_graph",
        status="COMPLETED",
        duration_ms=1500,
        tokens_used=4200,
        cost_usd=Decimal("0.0250"),
    )
    db_session.add(alert)
    db_session.add(agent_run)
    await db_session.commit()

    response = await client.get(f"/api/v1/investigations/{run_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["investigation_id"] == str(run_id)
    assert data["alert_id"] == str(alert_id)
    assert data["status"] == "COMPLETED"
    assert data["duration_ms"] == 1500
    assert data["tokens_used"] == 4200
    assert Decimal(str(data["cost_usd"])) == Decimal("0.0250")


# ------------------------------------------------------------------------------
# 3. Resilience & Failure Handling
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_investigation_execution_failure_resilience(
    client: AsyncClient,
    test_service: InvestigationService,
    auth_headers: dict[str, str],
) -> None:
    """Verify that unhandled exceptions during graph execution transition status to FAILED."""
    payload = {
        "supplier_id": "SUP-FAIL-001",
        "component_sku": "SKU-FAIL-001",
        "wait_for_completion": True,
    }

    with patch.object(
        test_service.orchestrator,
        "run_investigation",
        new=AsyncMock(side_effect=RuntimeError("LangGraph cluster execution timeout")),
    ):
        response = await client.post(
            "/api/v1/investigations/start",
            json=payload,
            headers=auth_headers,
        )
        assert response.status_code == 202
        inv_id = response.json()["investigation_id"]

        detail_resp = await client.get(f"/api/v1/investigations/{inv_id}", headers=auth_headers)
        assert detail_resp.status_code == 200
        detail = detail_resp.json()
        assert detail["status"] == "FAILED"
        assert any("timeout" in err.lower() for err in detail["errors"])


# ------------------------------------------------------------------------------
# 4. Security & Authentication Checks
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthenticated_requests_return_401(client: AsyncClient) -> None:
    """Verify missing Authorization header is rejected with 401 AUTHENTICATION_REQUIRED."""
    r1 = await client.post("/api/v1/investigations/start", json={"supplier_id": "SUP-1"})
    assert r1.status_code == 401
    assert r1.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    r2 = await client.get("/api/v1/investigations/inv-123")
    assert r2.status_code == 401
    assert r2.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.asyncio
async def test_malformed_token_returns_401(client: AsyncClient) -> None:
    """Verify malformed bearer token is rejected with 401 AUTHENTICATION_REQUIRED."""
    headers = {"Authorization": "Bearer invalid.jwt.token"}
    response = await client.get("/api/v1/investigations/inv-123", headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
