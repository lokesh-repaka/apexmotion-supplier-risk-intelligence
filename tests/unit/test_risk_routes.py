"""Unit tests for risk evaluation pipeline and alert management routes (P11-1).

Verifies:
- POST /api/v1/risk/evaluate:
    * Deterministic risk calculation (BR-RULE-001): zero LLM arithmetic.
    * NanoCore golden scenario: 7.68d cover, 1.32d gap, 24,420 units, $2,448,105.00 exposure, FULL_TRACK, CRITICAL, DUAL_VP tier.
    * Fast-track classification: when stock buffer is sufficient (gap <= 0, LOW severity).
    * Explicit mode overriding: 'fast_track' and 'full_track'.
    * Deduplication: collapsing active alerts within 1-hour window.
    * Canonical SKU auto-population when stock parameters are omitted.
- GET /api/v1/alerts & /api/v1/risk/alerts:
    * Paginated response envelope with total, page, page_size, total_pages.
    * Filtering by component_sku, risk_level, and status.
    * Ordering: descending by created_at.
- GET /api/v1/alerts/{alert_id} & /api/v1/risk/alerts/{alert_id}:
    * Detail record lookup for valid UUID.
    * 404 NOT_FOUND for non-existent alert.
    * 400 VALIDATION_ERROR for malformed UUID string.
- POST /api/v1/alerts/{alert_id}/acknowledge & /api/v1/risk/alerts/{alert_id}/acknowledge:
    * Category Manager authority succeeds: transitions status from OPEN to ACKNOWLEDGED.
    * Read-only Analyst authority strictly rejected with 403 INSUFFICIENT_ROLE.
    * Conflict 409 rejected when alert is already in terminal state (RESOLVED, CLOSED, DISMISSED).
    * 404 NOT_FOUND for non-existent alert ID.
- RBAC Security Gates:
    * Missing Authorization header returns 401 AUTHENTICATION_REQUIRED.
    * Invalid/tampered Bearer token returns 401.
"""

import json
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
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
from src.database.models import AuditLog, Base, RiskAlert
from src.database.session import get_db_session

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
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient wired with FastAPI dependency overrides and mock audit logging."""

    async def _override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = _override_get_db_session
    transport = ASGITransport(app=app)

    with patch("src.api.routes.risk_routes.write_audit_log", new=AsyncMock(return_value=None)):
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as async_http_client:
            yield async_http_client

    app.dependency_overrides.clear()


@pytest.fixture
def analyst_token() -> str:
    """Valid Bearer JWT token with supply_chain_analyst role."""
    return create_access_token(
        subject="usr-analyst-001",
        roles=[UserRole.SUPPLY_CHAIN_ANALYST.value],
    )


@pytest.fixture
def category_manager_token() -> str:
    """Valid Bearer JWT token with category_manager role."""
    return create_access_token(
        subject="usr-catman-001",
        roles=[UserRole.CATEGORY_MANAGER.value],
    )


@pytest.fixture
def auth_headers_analyst(analyst_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {analyst_token}"}


@pytest.fixture
def auth_headers_catman(category_manager_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {category_manager_token}"}


# ------------------------------------------------------------------------------
# 1. Pipeline Evaluation: POST /api/v1/risk/evaluate
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_risk_pipeline_nanocore_golden_match(
    client: AsyncClient,
    auth_headers_analyst: dict[str, str],
) -> None:
    """Verify evaluation matches NanoCore golden scenario deterministically."""
    supplier_uuid = str(uuid.uuid4())
    payload = {
        "component_sku": "NC-2024-001",
        "supplier_id": supplier_uuid,
        "current_stock": 142000,
        "daily_consumption_rate": 18500,
        "eta_days": "9.0",
        "unit_cost_usd": "100.25",
        "pipeline_mode": "auto",
    }

    response = await client.post(
        "/api/v1/risk/evaluate",
        json=payload,
        headers=auth_headers_analyst,
    )

    assert response.status_code == 200
    data = response.json()

    # Numerical invariants (BR-RULE-001)
    assert data["component_sku"] == "NC-2024-001"
    assert data["supplier_id"] == supplier_uuid
    assert Decimal(str(data["days_of_cover"])) == Decimal("7.68")
    assert Decimal(str(data["gap_days"])) == Decimal("1.32")
    assert data["shortage_volume"] == 24420
    assert Decimal(str(data["financial_exposure_usd"])) == Decimal("2448105.00")

    # Governance & Routing invariants
    assert data["pipeline_track"] == "FULL_TRACK"
    assert data["risk_level"] == "CRITICAL"
    assert data["requires_hitl"] is True
    assert data["governing_spend_tier"] == "DUAL_VP"
    assert data["status"] == "EVALUATED"
    assert data["alert_id"] is not None


@pytest.mark.asyncio
async def test_evaluate_risk_pipeline_fast_track_when_buffer_sufficient(
    client: AsyncClient,
    auth_headers_analyst: dict[str, str],
) -> None:
    """Verify evaluation classifies as FAST_TRACK when inventory buffer exceeds ETA."""
    payload = {
        "component_sku": "RES-FAST-001",
        "current_stock": 50000,
        "daily_consumption_rate": 1000,  # 50 days of cover
        "eta_days": "5.0",  # ETA is 5 days -> gap = 0
        "unit_cost_usd": "10.00",
        "pipeline_mode": "auto",
    }

    response = await client.post(
        "/api/v1/risk/evaluate",
        json=payload,
        headers=auth_headers_analyst,
    )

    assert response.status_code == 200
    data = response.json()

    assert data["pipeline_track"] == "FAST_TRACK"
    assert Decimal(str(data["gap_days"])) == Decimal("0.00")
    assert data["shortage_volume"] == 0
    assert Decimal(str(data["financial_exposure_usd"])) == Decimal("0.00")
    assert data["risk_level"] == "LOW"
    assert data["requires_hitl"] is False
    assert data["governing_spend_tier"] is None
    assert "Sufficient inventory buffer" in data["fast_track_reason"]


@pytest.mark.asyncio
async def test_evaluate_risk_pipeline_explicit_modes(
    client: AsyncClient,
    auth_headers_analyst: dict[str, str],
) -> None:
    """Verify explicit pipeline_mode overrides auto routing."""
    # Force fast track on critical disruption
    payload_fast = {
        "component_sku": "NC-2024-001",
        "current_stock": 1000,
        "daily_consumption_rate": 1000,
        "eta_days": "10.0",
        "pipeline_mode": "fast_track",
    }
    resp_fast = await client.post(
        "/api/v1/risk/evaluate",
        json=payload_fast,
        headers=auth_headers_analyst,
    )
    assert resp_fast.status_code == 200
    assert resp_fast.json()["pipeline_track"] == "FAST_TRACK"

    # Force full track on zero disruption
    payload_full = {
        "component_sku": "NC-2024-001",
        "current_stock": 50000,
        "daily_consumption_rate": 100,
        "eta_days": "2.0",
        "pipeline_mode": "full_track",
    }
    resp_full = await client.post(
        "/api/v1/risk/evaluate",
        json=payload_full,
        headers=auth_headers_analyst,
    )
    assert resp_full.status_code == 200
    assert resp_full.json()["pipeline_track"] == "FULL_TRACK"


@pytest.mark.asyncio
async def test_evaluate_risk_pipeline_deduplication_collapses_recent_alert(
    client: AsyncClient,
    auth_headers_analyst: dict[str, str],
) -> None:
    """Verify evaluate collapses into existing active alert when repeated within rolling window."""
    supplier_uuid = str(uuid.uuid4())
    payload = {
        "component_sku": "NC-2024-001",
        "supplier_id": supplier_uuid,
        "current_stock": 142000,
        "daily_consumption_rate": 18500,
        "eta_days": "9.0",
    }

    # First evaluation -> EVALUATED
    resp1 = await client.post("/api/v1/risk/evaluate", json=payload, headers=auth_headers_analyst)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["status"] == "EVALUATED"
    alert_id1 = data1["alert_id"]

    # Second evaluation within 1-hr window -> COLLAPSED
    resp2 = await client.post("/api/v1/risk/evaluate", json=payload, headers=auth_headers_analyst)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["status"] == "COLLAPSED"
    assert data2["alert_id"] == alert_id1


@pytest.mark.asyncio
async def test_evaluate_risk_canonical_sku_lookup(
    client: AsyncClient,
    auth_headers_analyst: dict[str, str],
) -> None:
    """Verify omitting stock and daily consumption populates canonical registry values."""
    payload = {
        "component_sku": "NC-2024-001",
        # current_stock and daily_consumption_rate omitted
    }
    resp = await client.post("/api/v1/risk/evaluate", json=payload, headers=auth_headers_analyst)
    assert resp.status_code == 200
    data = resp.json()
    assert Decimal(str(data["days_of_cover"])) == Decimal("7.68")


# ------------------------------------------------------------------------------
# 2. Alert Feed Routes: GET /api/v1/alerts & GET /api/v1/risk/alerts
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_alerts_empty_state(
    client: AsyncClient,
    auth_headers_analyst: dict[str, str],
) -> None:
    """Verify empty alert feed returns properly structured pagination envelope."""
    response = await client.get("/api/v1/alerts", headers=auth_headers_analyst)
    assert response.status_code == 200
    data = response.json()

    assert data["items"] == []
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert data["total_pages"] == 0


@pytest.mark.asyncio
async def test_list_alerts_pagination_and_ordering(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers_analyst: dict[str, str],
) -> None:
    """Verify multi-page pagination and descending timestamp ordering."""
    # Seed 5 alerts with increasing timestamps
    base_time = datetime.now(UTC)
    for i in range(5):
        alert = RiskAlert(
            component_sku=f"SKU-PAGE-{i}",
            risk_level="HIGH",
            days_of_cover=Decimal("5.0"),
            financial_exposure=Decimal("150000.00"),
            status="OPEN",
            created_at=base_time + timedelta(minutes=i),
        )
        db_session.add(alert)
    await db_session.commit()

    # Page 1, size 2 -> alerts 4 and 3 (newest first)
    r1 = await client.get(
        "/api/v1/alerts?page=1&page_size=2",
        headers=auth_headers_analyst,
    )
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["total"] == 5
    assert d1["page"] == 1
    assert d1["page_size"] == 2
    assert d1["total_pages"] == 3
    assert len(d1["items"]) == 2
    assert d1["items"][0]["component_sku"] == "SKU-PAGE-4"
    assert d1["items"][1]["component_sku"] == "SKU-PAGE-3"

    # Page 2, size 2 -> alerts 2 and 1
    r2 = await client.get(
        "/api/v1/alerts?page=2&page_size=2",
        headers=auth_headers_analyst,
    )
    assert r2.status_code == 200
    d2 = r2.json()
    assert len(d2["items"]) == 2
    assert d2["items"][0]["component_sku"] == "SKU-PAGE-2"
    assert d2["items"][1]["component_sku"] == "SKU-PAGE-1"


@pytest.mark.asyncio
async def test_list_alerts_filtering_by_attributes(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers_analyst: dict[str, str],
) -> None:
    """Verify filtering by SKU, severity risk level, and alert status."""
    supp_id = uuid.uuid4()
    alerts = [
        RiskAlert(
            supplier_id=supp_id,
            component_sku="NC-2024-001",
            risk_level="CRITICAL",
            financial_exposure=Decimal("2448105.00"),
            status="OPEN",
        ),
        RiskAlert(
            supplier_id=supp_id,
            component_sku="NC-2024-001",
            risk_level="HIGH",
            financial_exposure=Decimal("350000.00"),
            status="ACKNOWLEDGED",
        ),
        RiskAlert(
            component_sku="RES-OTHER-002",
            risk_level="LOW",
            financial_exposure=Decimal("0.00"),
            status="RESOLVED",
        ),
    ]
    for a in alerts:
        db_session.add(a)
    await db_session.commit()

    # Filter by component_sku
    r_sku = await client.get(
        "/api/v1/alerts?component_sku=NC-2024-001",
        headers=auth_headers_analyst,
    )
    assert r_sku.status_code == 200
    assert r_sku.json()["total"] == 2

    # Filter by risk_level
    r_crit = await client.get(
        "/api/v1/alerts?risk_level=CRITICAL",
        headers=auth_headers_analyst,
    )
    assert r_crit.status_code == 200
    assert r_crit.json()["total"] == 1
    assert r_crit.json()["items"][0]["risk_level"] == "CRITICAL"

    # Filter by status
    r_ack = await client.get(
        "/api/v1/alerts?status=ACKNOWLEDGED",
        headers=auth_headers_analyst,
    )
    assert r_ack.status_code == 200
    assert r_ack.json()["total"] == 1
    assert r_ack.json()["items"][0]["status"] == "ACKNOWLEDGED"

    # Filter by supplier_id
    r_supp = await client.get(
        f"/api/v1/alerts?supplier_id={supp_id}",
        headers=auth_headers_analyst,
    )
    assert r_supp.status_code == 200
    assert r_supp.json()["total"] == 2


@pytest.mark.asyncio
async def test_list_alerts_alias_endpoint(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers_analyst: dict[str, str],
) -> None:
    """Verify /api/v1/risk/alerts works as an alias for /api/v1/alerts."""
    alert = RiskAlert(
        component_sku="ALIAS-SKU-001",
        risk_level="MEDIUM",
        status="OPEN",
    )
    db_session.add(alert)
    await db_session.commit()

    response = await client.get("/api/v1/risk/alerts", headers=auth_headers_analyst)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["component_sku"] == "ALIAS-SKU-001"


# ------------------------------------------------------------------------------
# 3. Alert Detail Routes: GET /api/v1/alerts/{alert_id}
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_alert_by_id_success(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers_analyst: dict[str, str],
) -> None:
    """Verify fetching single alert detail by valid UUID returns 200."""
    alert = RiskAlert(
        component_sku="DETAIL-SKU-001",
        risk_level="CRITICAL",
        days_of_cover=Decimal("7.68"),
        financial_exposure=Decimal("2448105.00"),
        shortage_volume=24420,
        status="OPEN",
    )
    db_session.add(alert)
    await db_session.commit()
    await db_session.refresh(alert)

    response = await client.get(
        f"/api/v1/alerts/{alert.id}",
        headers=auth_headers_analyst,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(alert.id)
    assert data["component_sku"] == "DETAIL-SKU-001"
    assert data["risk_level"] == "CRITICAL"
    assert Decimal(str(data["financial_exposure"])) == Decimal("2448105.00")
    assert data["shortage_volume"] == 24420
    assert data["status"] == "OPEN"


@pytest.mark.asyncio
async def test_get_alert_by_id_not_found(
    client: AsyncClient,
    auth_headers_analyst: dict[str, str],
) -> None:
    """Verify querying non-existent alert returns 404 NOT_FOUND."""
    random_id = str(uuid.uuid4())
    response = await client.get(
        f"/api/v1/alerts/{random_id}",
        headers=auth_headers_analyst,
    )
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_alert_by_id_invalid_uuid(
    client: AsyncClient,
    auth_headers_analyst: dict[str, str],
) -> None:
    """Verify querying with malformed UUID string returns 400 VALIDATION_ERROR."""
    response = await client.get(
        "/api/v1/alerts/not-a-valid-uuid",
        headers=auth_headers_analyst,
    )
    assert response.status_code == 400
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


# ------------------------------------------------------------------------------
# 4. Alert Acknowledge Routes: POST /api/v1/alerts/{alert_id}/acknowledge
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acknowledge_alert_success_category_manager(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers_catman: dict[str, str],
) -> None:
    """Verify Category Manager authority successfully transitions status to ACKNOWLEDGED."""
    alert = RiskAlert(
        component_sku="ACK-SKU-001",
        risk_level="HIGH",
        status="OPEN",
    )
    db_session.add(alert)
    await db_session.commit()
    await db_session.refresh(alert)

    payload = {"notes": "Acknowledged disruption, alternate supplier sourcing initiated."}
    response = await client.post(
        f"/api/v1/alerts/{alert.id}/acknowledge",
        json=payload,
        headers=auth_headers_catman,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(alert.id)
    assert data["status"] == "ACKNOWLEDGED"
    assert data["acknowledged_by"] == "usr-catman-001"
    assert data["notes"] == payload["notes"]

    # Verify persisted DB status
    await db_session.refresh(alert)
    assert alert.status == "ACKNOWLEDGED"


@pytest.mark.asyncio
async def test_acknowledge_alert_forbidden_for_analyst(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers_analyst: dict[str, str],
) -> None:
    """Verify supply_chain_analyst lacks authority to acknowledge alert (403 INSUFFICIENT_ROLE)."""
    alert = RiskAlert(
        component_sku="ACK-SKU-002",
        risk_level="CRITICAL",
        status="OPEN",
    )
    db_session.add(alert)
    await db_session.commit()
    await db_session.refresh(alert)

    response = await client.post(
        f"/api/v1/alerts/{alert.id}/acknowledge",
        json={"notes": "Analyst trying to acknowledge"},
        headers=auth_headers_analyst,
    )
    assert response.status_code == 403
    data = response.json()
    assert data["error"]["code"] == "INSUFFICIENT_ROLE"

    # Verify DB status is unchanged
    await db_session.refresh(alert)
    assert alert.status == "OPEN"


@pytest.mark.asyncio
async def test_acknowledge_alert_terminal_status_conflict_409(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers_catman: dict[str, str],
) -> None:
    """Verify acknowledging an already RESOLVED or CLOSED alert returns 409 CONFLICT."""
    alert = RiskAlert(
        component_sku="ACK-SKU-003",
        risk_level="LOW",
        status="RESOLVED",
    )
    db_session.add(alert)
    await db_session.commit()
    await db_session.refresh(alert)

    response = await client.post(
        f"/api/v1/alerts/{alert.id}/acknowledge",
        headers=auth_headers_catman,
    )
    assert response.status_code == 409
    data = response.json()
    assert data["error"]["code"] == "CONFLICT"
    assert "terminal status" in data["error"]["message"].lower()


@pytest.mark.asyncio
async def test_acknowledge_alert_not_found_404(
    client: AsyncClient,
    auth_headers_catman: dict[str, str],
) -> None:
    """Verify acknowledging non-existent alert returns 404 NOT_FOUND."""
    random_id = str(uuid.uuid4())
    response = await client.post(
        f"/api/v1/alerts/{random_id}/acknowledge",
        headers=auth_headers_catman,
    )
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_acknowledge_alert_alias_endpoint(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers_catman: dict[str, str],
) -> None:
    """Verify /api/v1/risk/alerts/{id}/acknowledge alias route functions properly."""
    alert = RiskAlert(
        component_sku="ACK-ALIAS-001",
        risk_level="HIGH",
        status="OPEN",
    )
    db_session.add(alert)
    await db_session.commit()
    await db_session.refresh(alert)

    response = await client.post(
        f"/api/v1/risk/alerts/{alert.id}/acknowledge",
        headers=auth_headers_catman,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ACKNOWLEDGED"


# ------------------------------------------------------------------------------
# 5. Security & Authentication Checks
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthenticated_request_returns_401(client: AsyncClient) -> None:
    """Verify missing Authorization header is rejected with 401 AUTHENTICATION_REQUIRED."""
    r1 = await client.post("/api/v1/risk/evaluate", json={"component_sku": "TEST"})
    assert r1.status_code == 401
    assert r1.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    r2 = await client.get("/api/v1/alerts")
    assert r2.status_code == 401
    assert r2.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.asyncio
async def test_malformed_token_returns_401(client: AsyncClient) -> None:
    """Verify malformed bearer token is rejected with 401 AUTHENTICATION_REQUIRED."""
    headers = {"Authorization": "Bearer malformed.invalid.jwt"}
    response = await client.get("/api/v1/alerts", headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


# ------------------------------------------------------------------------------
# 6. Branch Coverage & Direct Handler Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_risk_direct_registry_hit(db_session: AsyncSession) -> None:
    """Directly test evaluation using SKU in REFERENCE_INVENTORY_REGISTRY."""
    from src.api.routes.risk_routes import evaluate_risk_pipeline
    from src.api.schemas.risk import RiskEvaluationRequest
    from src.core.security import AuthenticatedUser

    user = AuthenticatedUser(user_id="usr-direct-001", roles=["analyst"])
    req = RiskEvaluationRequest(
        component_sku="SKU-MCU-4402",  # Present in REFERENCE_INVENTORY_REGISTRY
        # current_stock, daily_consumption_rate, and unit_cost_usd omitted
    )

    with patch("src.api.routes.risk_routes.write_audit_log", new=AsyncMock(return_value=None)):
        res = await evaluate_risk_pipeline(req, user, db_session)
        assert res.component_sku == "SKU-MCU-4402"
        assert Decimal(str(res.days_of_cover)) == Decimal("7.68")


@pytest.mark.asyncio
async def test_evaluate_risk_audit_failure_resilience(db_session: AsyncSession) -> None:
    """Verify evaluation still succeeds even if forensic audit writer fails."""
    from src.api.routes.risk_routes import evaluate_risk_pipeline
    from src.api.schemas.risk import RiskEvaluationRequest
    from src.core.security import AuthenticatedUser

    user = AuthenticatedUser(user_id="usr-direct-002", roles=["analyst"])
    req = RiskEvaluationRequest(
        component_sku="RES-FAIL-001",
        current_stock=1000,
        daily_consumption_rate=500,
    )

    with patch(
        "src.api.routes.risk_routes.write_audit_log",
        new=AsyncMock(side_effect=RuntimeError("Audit writer unavailable")),
    ):
        res = await evaluate_risk_pipeline(req, user, db_session)
        assert res.status == "EVALUATED"


@pytest.mark.asyncio
async def test_acknowledge_alert_audit_failure_resilience(db_session: AsyncSession) -> None:
    """Verify alert acknowledgement succeeds even if forensic audit writer fails."""
    from src.api.routes.risk_routes import acknowledge_risk_alert
    from src.core.security import AuthenticatedUser

    alert = RiskAlert(component_sku="ACK-FAIL-001", status="OPEN", risk_level="HIGH")
    db_session.add(alert)
    await db_session.commit()
    await db_session.refresh(alert)

    user = AuthenticatedUser(user_id="usr-catman-002", roles=["category_manager"])

    with patch(
        "src.api.routes.risk_routes.write_audit_log",
        new=AsyncMock(side_effect=RuntimeError("Audit writer unavailable")),
    ):
        res = await acknowledge_risk_alert(str(alert.id), user, db_session, payload=None)
        assert res.status == "ACKNOWLEDGED"
        assert res.notes is None


@pytest.mark.asyncio
async def test_list_alerts_invalid_supplier_uuid(
    client: AsyncClient,
    auth_headers_analyst: dict[str, str],
) -> None:
    """Verify filtering by invalid supplier_id raises 400 VALIDATION_ERROR."""
    response = await client.get(
        "/api/v1/alerts?supplier_id=invalid-uuid", headers=auth_headers_analyst
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# ------------------------------------------------------------------------------
# 5. Alert Audit Trail Tests: GET /api/v1/alerts/{alert_id}/audit
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_alert_audit_trail_success(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers_analyst: dict[str, str],
) -> None:
    """Verify retrieving chronological audit trail for an existing alert succeeds."""
    alert = RiskAlert(
        component_sku="AUDIT-SKU-001",
        risk_level="HIGH",
        status="OPEN",
    )
    db_session.add(alert)
    await db_session.commit()
    await db_session.refresh(alert)

    # Insert mock audit log for this alert
    audit_entry = AuditLog(
        entity_type="RISK_ALERT",
        entity_id=alert.id,
        action="ALERT_ACKNOWLEDGED",
        actor_id=uuid.uuid4(),
        before_state={"status": "OPEN"},
        after_state={"status": "ACKNOWLEDGED"},
        trace_id="tr-test-audit-001",
    )
    db_session.add(audit_entry)
    await db_session.commit()

    response = await client.get(
        f"/api/v1/alerts/{alert.id}/audit",
        headers=auth_headers_analyst,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["entity_type"] == "RISK_ALERT"
    assert data["entity_id"] == str(alert.id)
    assert len(data["items"]) == 1
    assert data["items"][0]["action"] == "ALERT_ACKNOWLEDGED"
    assert data["items"][0]["trace_id"] == "tr-test-audit-001"


@pytest.mark.asyncio
async def test_get_alert_audit_trail_not_found_404(
    client: AsyncClient,
    auth_headers_analyst: dict[str, str],
) -> None:
    """Verify querying audit trail for non-existent alert returns 404 NOT_FOUND."""
    fake_id = str(uuid.uuid4())
    response = await client.get(
        f"/api/v1/alerts/{fake_id}/audit",
        headers=auth_headers_analyst,
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_alert_audit_trail_invalid_uuid_400(
    client: AsyncClient,
    auth_headers_analyst: dict[str, str],
) -> None:
    """Verify querying audit trail with malformed UUID returns 400 VALIDATION_ERROR."""
    response = await client.get(
        "/api/v1/alerts/not-a-valid-uuid/audit",
        headers=auth_headers_analyst,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

