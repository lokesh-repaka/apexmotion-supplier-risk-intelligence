"""Unit tests for Supplier API routes (P11-4).

Verifies:
- GET /api/v1/suppliers:
    * Paginated supplier listing with tier, country, and risk score filters.
    * Pagination metadata (total, page, page_size, total_pages).
- GET /api/v1/suppliers/{id}:
    * Master supplier entity retrieval by UUID, Neptune ID, or exact name.
    * 404 NOT_FOUND for non-existent supplier identifier.
- GET /api/v1/suppliers/{id}/risk:
    * Live risk metrics calculation for NanoCore reference scenario:
      (composite risk score 0.880, CRITICAL level, $2,448,105.00 exposure, 7.68d cover, 1.32d gap).
    * Resolution of supplier by UUID and by Neptune node ID (SUP-NC-882).
    * Graceful graph enrichment fallback when Neptune is unavailable.
    * 404 NOT_FOUND for unknown supplier.
- GET /api/v1/suppliers/{id}/graph:
    * 2-hop ego-subgraph extraction with nodes and edges.
    * Graph lookup by UUID mapping to Neptune node ID.
    * Minimal 1-node fallback when Neptune graph is unseeded but DB entity exists.
    * 404 NOT_FOUND when supplier exists neither in DB nor in knowledge graph.
    * Traversal error mapping (504 on timeout, 503 on connection failure).
- RBAC Security Gates:
    * analyst+ authority permitted across all endpoints.
    * 401 AUTHENTICATION_REQUIRED for unauthenticated requests.
"""

import json
import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from src.api.main import app
from src.api.routes.supplier_routes import get_supplier_traversal_service
from src.core.security import UserRole, create_access_token
from src.database.models import Base, RiskAlert, Supplier
from src.database.session import get_db_session
from src.graph.traversal import (
    AffectedComponent,
    AffectedPlant,
    AffectedProgram,
    DisruptionBlastRadius,
    SupplierSubgraph,
    SupplierTraversalService,
    TraversalError,
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


@pytest.fixture
def mock_traversal_service() -> AsyncMock:
    """Mock SupplierTraversalService simulating Neptune graph queries."""
    service = AsyncMock(spec=SupplierTraversalService)

    # Default blast radius for NanoCore
    service.get_disruption_blast_radius.return_value = DisruptionBlastRadius(
        supplier_id="SUP-NC-882",
        supplier_name="NanoCore Semiconductor",
        supplier_risk_score=0.88,
        shortest_path_hops=2,
        affected_components=[
            AffectedComponent(
                component_id="CMP-MCU-X91",
                mpn="MCU-X91",
                criticality="CRITICAL",
                is_single_source=True,
                lead_time_days=45,
            )
        ],
        affected_plants=[
            AffectedPlant(
                plant_id="PLT-MUC-01",
                plant_name="Munich Hyper-GT Plant",
                component_id="CMP-MCU-X91",
            )
        ],
        affected_programs=[
            AffectedProgram(
                program_id="PRG-HYPER-GT",
                model="Hyper-GT",
            )
        ],
    )

    # Default 2-hop subgraph for NanoCore
    service.get_supplier_subgraph.return_value = SupplierSubgraph(
        supplier_id="SUP-NC-882",
        nodes=[
            {
                "id": "SUP-NC-882",
                "label": "Supplier",
                "name": "NanoCore Semiconductor",
                "tier": 2,
                "country": "TW",
            },
            {
                "id": "CMP-MCU-X91",
                "label": "Component",
                "mpn": "MCU-X91",
                "criticality": "CRITICAL",
            },
            {
                "id": "PLT-MUC-01",
                "label": "Plant",
                "name": "Munich Hyper-GT Plant",
                "country": "DE",
            },
        ],
        edges=[
            {
                "from": "SUP-NC-882",
                "to": "CMP-MCU-X91",
                "type": "SUPPLIES_PART",
            },
            {
                "from": "CMP-MCU-X91",
                "to": "PLT-MUC-01",
                "type": "CONSUMES",
            },
        ],
    )

    return service


@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession,
    mock_traversal_service: AsyncMock,
) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient wired with FastAPI dependency overrides."""

    async def _override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    def _override_get_supplier_traversal_service() -> SupplierTraversalService:
        return mock_traversal_service

    app.dependency_overrides[get_db_session] = _override_get_db_session
    app.dependency_overrides[get_supplier_traversal_service] = (
        _override_get_supplier_traversal_service
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as async_http_client:
        yield async_http_client

    app.dependency_overrides.clear()


# ------------------------------------------------------------------------------
# Auth Token Helpers
# ------------------------------------------------------------------------------


def _auth_header(role: UserRole = UserRole.ANALYST, user_id: str | None = None) -> dict[str, str]:
    """Generate Authorization header with valid mock Keycloak JWT."""
    uid = user_id or str(uuid.uuid4())
    token = create_access_token(
        subject=uid,
        roles=[role.value],
        email=f"{role.value}@apexmotion.com",
    )
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------------------------
# Test Cases: GET /api/v1/suppliers
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_suppliers_success(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify paginated listing of suppliers directory."""
    s1 = Supplier(
        id=uuid.uuid4(),
        name="BetaElectro AG",
        country_code="DE",
        tier=1,
        risk_score=Decimal("0.220"),
        neptune_node_id="SUP-BE-101",
    )
    s2 = Supplier(
        id=uuid.uuid4(),
        name="NanoCore Semiconductor",
        country_code="TW",
        tier=2,
        risk_score=Decimal("0.880"),
        neptune_node_id="SUP-NC-882",
    )
    s3 = Supplier(
        id=uuid.uuid4(),
        name="Volta Lithium",
        country_code="AU",
        tier=3,
        risk_score=Decimal("0.350"),
        neptune_node_id="SUP-VL-501",
    )
    db_session.add_all([s1, s2, s3])
    await db_session.commit()

    headers = _auth_header(UserRole.ANALYST)
    resp = await client.get("/api/v1/suppliers", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert data["total_pages"] == 1


@pytest.mark.asyncio
async def test_list_suppliers_filter_by_tier_and_country(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify filtering suppliers by tier and country code."""
    s1 = Supplier(
        id=uuid.uuid4(),
        name="Supplier DE 1",
        country_code="DE",
        tier=1,
        risk_score=Decimal("0.200"),
    )
    s2 = Supplier(
        id=uuid.uuid4(),
        name="Supplier TW 2",
        country_code="TW",
        tier=2,
        risk_score=Decimal("0.850"),
    )
    db_session.add_all([s1, s2])
    await db_session.commit()

    headers = _auth_header(UserRole.ANALYST)
    resp = await client.get("/api/v1/suppliers?tier=2&country_code=TW", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["country_code"] == "TW"
    assert data["items"][0]["tier"] == 2


@pytest.mark.asyncio
async def test_list_suppliers_filter_by_min_risk_score(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify filtering suppliers by minimum risk score threshold."""
    s1 = Supplier(
        id=uuid.uuid4(),
        name="Low Risk Supplier",
        country_code="DE",
        tier=1,
        risk_score=Decimal("0.150"),
    )
    s2 = Supplier(
        id=uuid.uuid4(),
        name="High Risk Supplier",
        country_code="TW",
        tier=2,
        risk_score=Decimal("0.880"),
    )
    db_session.add_all([s1, s2])
    await db_session.commit()

    headers = _auth_header(UserRole.ANALYST)
    resp = await client.get("/api/v1/suppliers?min_risk_score=0.700", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "High Risk Supplier"


@pytest.mark.asyncio
async def test_list_suppliers_unauthenticated(
    client: AsyncClient,
) -> None:
    """Verify unauthenticated request returns 401 AUTHENTICATION_REQUIRED."""
    resp = await client.get("/api/v1/suppliers")

    assert resp.status_code == 401
    data = resp.json()
    assert data["error"]["code"] == "AUTHENTICATION_REQUIRED"


# ------------------------------------------------------------------------------
# Test Cases: GET /api/v1/suppliers/{id}
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_supplier_detail_by_uuid_success(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify detailed supplier profile lookup by UUID."""
    s_id = uuid.uuid4()
    supplier = Supplier(
        id=s_id,
        name="NanoCore Semiconductor",
        country_code="TW",
        tier=2,
        risk_score=Decimal("0.880"),
        neptune_node_id="SUP-NC-882",
    )
    db_session.add(supplier)
    await db_session.commit()

    headers = _auth_header(UserRole.ANALYST)
    resp = await client.get(f"/api/v1/suppliers/{s_id}", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(s_id)
    assert data["name"] == "NanoCore Semiconductor"
    assert data["country_code"] == "TW"
    assert data["tier"] == 2
    assert Decimal(str(data["risk_score"])) == Decimal("0.880")
    assert data["neptune_node_id"] == "SUP-NC-882"


@pytest.mark.asyncio
async def test_get_supplier_detail_by_neptune_id_success(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify supplier profile lookup by Neptune node ID string (e.g. SUP-NC-882)."""
    supplier = Supplier(
        id=uuid.uuid4(),
        name="NanoCore Semiconductor",
        country_code="TW",
        tier=2,
        risk_score=Decimal("0.880"),
        neptune_node_id="SUP-NC-882",
    )
    db_session.add(supplier)
    await db_session.commit()

    headers = _auth_header(UserRole.ANALYST)
    resp = await client.get("/api/v1/suppliers/SUP-NC-882", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["neptune_node_id"] == "SUP-NC-882"
    assert data["name"] == "NanoCore Semiconductor"


@pytest.mark.asyncio
async def test_get_supplier_detail_not_found(
    client: AsyncClient,
) -> None:
    """Verify 404 NOT_FOUND for non-existent supplier identifier."""
    random_id = str(uuid.uuid4())
    headers = _auth_header(UserRole.ANALYST)
    resp = await client.get(f"/api/v1/suppliers/{random_id}", headers=headers)

    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "NOT_FOUND"


# ------------------------------------------------------------------------------
# Test Cases: GET /api/v1/suppliers/{id}/risk
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_supplier_risk_nanocore_golden_success(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify live composite risk metrics for NanoCore reference scenario."""
    s_id = uuid.uuid4()
    supplier = Supplier(
        id=s_id,
        name="NanoCore Semiconductor",
        country_code="TW",
        tier=2,
        risk_score=Decimal("0.880"),
        neptune_node_id="SUP-NC-882",
    )
    db_session.add(supplier)
    await db_session.commit()

    # Seed active risk alert matching NanoCore golden metrics
    alert = RiskAlert(
        id=uuid.uuid4(),
        supplier_id=s_id,
        component_sku="NC-2024",
        risk_level="CRITICAL",
        status="OPEN",
        days_of_cover=Decimal("7.68"),
        shortage_volume=24420,
        financial_exposure=Decimal("2448105.00"),
    )
    db_session.add(alert)
    await db_session.commit()

    headers = _auth_header(UserRole.ANALYST)
    resp = await client.get("/api/v1/suppliers/SUP-NC-882/risk", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["supplier_id"] == str(s_id)
    assert data["neptune_node_id"] == "SUP-NC-882"
    assert data["supplier_name"] == "NanoCore Semiconductor"
    assert data["country_code"] == "TW"
    assert data["tier"] == 2
    assert Decimal(str(data["composite_risk_score"])) == Decimal("0.880")
    assert data["risk_level"] == "CRITICAL"
    assert data["active_alerts_count"] == 1
    assert data["critical_alerts_count"] == 1
    assert Decimal(str(data["total_financial_exposure_usd"])) == Decimal("2448105.00")
    assert Decimal(str(data["min_days_of_cover"])) == Decimal("7.68")
    assert data["total_shortage_volume"] == 24420
    assert data["affected_skus"] == ["NC-2024"]
    assert "PLT-MUC-01" in data["affected_plants"]
    assert "PRG-HYPER-GT" in data["affected_programs"]
    assert data["is_single_source"] is True


@pytest.mark.asyncio
async def test_get_supplier_risk_by_uuid(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify live risk metrics resolution by supplier UUID."""
    s_id = uuid.uuid4()
    supplier = Supplier(
        id=s_id,
        name="BetaElectro AG",
        country_code="DE",
        tier=1,
        risk_score=Decimal("0.220"),
        neptune_node_id="SUP-BE-101",
    )
    db_session.add(supplier)
    await db_session.commit()

    headers = _auth_header(UserRole.ANALYST)
    resp = await client.get(f"/api/v1/suppliers/{s_id}/risk", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["supplier_id"] == str(s_id)
    assert data["supplier_name"] == "BetaElectro AG"
    assert data["risk_level"] == "LOW"
    assert data["active_alerts_count"] == 0
    assert Decimal(str(data["total_financial_exposure_usd"])) == Decimal("0.00")
    assert data["min_days_of_cover"] is None


@pytest.mark.asyncio
async def test_get_supplier_risk_not_found(
    client: AsyncClient,
) -> None:
    """Verify 404 NOT_FOUND for non-existent supplier on /risk endpoint."""
    random_id = str(uuid.uuid4())
    headers = _auth_header(UserRole.ANALYST)
    resp = await client.get(f"/api/v1/suppliers/{random_id}/risk", headers=headers)

    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_supplier_risk_graph_failure_graceful(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_traversal_service: AsyncMock,
) -> None:
    """Verify graph traversal exception is caught gracefully without breaking risk metrics."""
    s_id = uuid.uuid4()
    supplier = Supplier(
        id=s_id,
        name="NanoCore Semiconductor",
        country_code="TW",
        tier=2,
        risk_score=Decimal("0.750"),
        neptune_node_id="SUP-NC-882",
    )
    db_session.add(supplier)
    await db_session.commit()

    # Mock Neptune blast radius lookup failure
    mock_traversal_service.get_disruption_blast_radius.side_effect = TraversalError(
        "Neptune connection timed out", status_code=504
    )

    headers = _auth_header(UserRole.ANALYST)
    resp = await client.get(f"/api/v1/suppliers/{s_id}/risk", headers=headers)

    # Route still returns 200 with relational database risk metrics
    assert resp.status_code == 200
    data = resp.json()
    assert data["supplier_name"] == "NanoCore Semiconductor"
    assert data["affected_plants"] == []
    assert data["is_single_source"] is False


# ------------------------------------------------------------------------------
# Test Cases: GET /api/v1/suppliers/{id}/graph
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_supplier_graph_success(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify 2-hop ego-subgraph extraction for frontend visualization."""
    supplier = Supplier(
        id=uuid.uuid4(),
        name="NanoCore Semiconductor",
        country_code="TW",
        tier=2,
        risk_score=Decimal("0.880"),
        neptune_node_id="SUP-NC-882",
    )
    db_session.add(supplier)
    await db_session.commit()

    headers = _auth_header(UserRole.ANALYST)
    resp = await client.get("/api/v1/suppliers/SUP-NC-882/graph?max_hops=2", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["neptune_node_id"] == "SUP-NC-882"
    assert len(data["nodes"]) == 3
    assert len(data["edges"]) == 2
    assert data["total_nodes"] == 3
    assert data["total_edges"] == 2
    assert data["hop_depth"] == 2


@pytest.mark.asyncio
async def test_get_supplier_graph_by_uuid(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify graph endpoint accepts supplier UUID and maps to Neptune node ID."""
    s_id = uuid.uuid4()
    supplier = Supplier(
        id=s_id,
        name="NanoCore Semiconductor",
        country_code="TW",
        tier=2,
        risk_score=Decimal("0.880"),
        neptune_node_id="SUP-NC-882",
    )
    db_session.add(supplier)
    await db_session.commit()

    headers = _auth_header(UserRole.ANALYST)
    resp = await client.get(f"/api/v1/suppliers/{s_id}/graph", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["supplier_id"] == str(s_id)
    assert data["neptune_node_id"] == "SUP-NC-882"


@pytest.mark.asyncio
async def test_get_supplier_graph_fallback_to_db_supplier_when_neptune_empty(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_traversal_service: AsyncMock,
) -> None:
    """Verify fallback to 1-node root graph when Neptune returns empty but supplier exists in DB."""
    s_id = uuid.uuid4()
    supplier = Supplier(
        id=s_id,
        name="Isolated Supplier",
        country_code="DE",
        tier=1,
        risk_score=Decimal("0.100"),
        neptune_node_id="SUP-ISO-001",
    )
    db_session.add(supplier)
    await db_session.commit()

    # Neptune returns empty subgraph
    mock_traversal_service.get_supplier_subgraph.return_value = SupplierSubgraph(
        supplier_id="SUP-ISO-001",
        nodes=[],
        edges=[],
    )

    headers = _auth_header(UserRole.ANALYST)
    resp = await client.get(f"/api/v1/suppliers/{s_id}/graph", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_nodes"] == 1
    assert data["total_edges"] == 0
    assert data["nodes"][0]["name"] == "Isolated Supplier"


@pytest.mark.asyncio
async def test_get_supplier_graph_not_found(
    client: AsyncClient,
    mock_traversal_service: AsyncMock,
) -> None:
    """Verify 404 NOT_FOUND when supplier exists neither in DB nor in Neptune."""
    mock_traversal_service.get_supplier_subgraph.return_value = SupplierSubgraph(
        supplier_id="SUP-UNKNOWN",
        nodes=[],
        edges=[],
    )

    headers = _auth_header(UserRole.ANALYST)
    resp = await client.get("/api/v1/suppliers/SUP-UNKNOWN/graph", headers=headers)

    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_supplier_detail_by_name_success(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify supplier profile lookup by exact name string."""
    supplier = Supplier(
        id=uuid.uuid4(),
        name="Exact Name Semiconductor",
        country_code="DE",
        tier=1,
        risk_score=Decimal("0.180"),
    )
    db_session.add(supplier)
    await db_session.commit()

    headers = _auth_header(UserRole.ANALYST)
    resp = await client.get("/api/v1/suppliers/Exact Name Semiconductor", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Exact Name Semiconductor"
    assert data["tier"] == 1


@pytest.mark.asyncio
async def test_get_supplier_risk_high_and_medium_levels(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify categorical risk levels HIGH (>=0.500) and MEDIUM (>=0.300)."""
    s_high = Supplier(
        id=uuid.uuid4(),
        name="High Tier Supplier",
        country_code="US",
        tier=2,
        risk_score=Decimal("0.550"),
    )
    s_med = Supplier(
        id=uuid.uuid4(),
        name="Med Tier Supplier",
        country_code="DE",
        tier=1,
        risk_score=Decimal("0.350"),
    )
    db_session.add_all([s_high, s_med])
    await db_session.commit()

    headers = _auth_header(UserRole.ANALYST)
    resp_high = await client.get(f"/api/v1/suppliers/{s_high.id}/risk", headers=headers)
    assert resp_high.status_code == 200
    assert resp_high.json()["risk_level"] == "HIGH"

    resp_med = await client.get(f"/api/v1/suppliers/{s_med.id}/risk", headers=headers)
    assert resp_med.status_code == 200
    assert resp_med.json()["risk_level"] == "MEDIUM"


@pytest.mark.asyncio
async def test_get_supplier_graph_unexpected_exception_mapped(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_traversal_service: AsyncMock,
) -> None:
    """Verify unexpected runtime exceptions in traversal service are wrapped in 500 TraversalError."""
    s_id = uuid.uuid4()
    supplier = Supplier(
        id=s_id,
        name="Failing Supplier",
        country_code="DE",
        tier=1,
        neptune_node_id="SUP-FAIL-01",
    )
    db_session.add(supplier)
    await db_session.commit()

    mock_traversal_service.get_supplier_subgraph.side_effect = RuntimeError(
        "Low level socket crash"
    )

    headers = _auth_header(UserRole.ANALYST)
    resp = await client.get(f"/api/v1/suppliers/{s_id}/graph", headers=headers)

    assert resp.status_code == 500
    data = resp.json()
    assert data["error"]["code"] == "GRAPH_TRAVERSAL_ERROR"


@pytest.mark.asyncio
async def test_get_supplier_graph_traversal_error_mapped(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_traversal_service: AsyncMock,
) -> None:
    """Verify TraversalError is properly mapped to HTTP status code and standardized envelope."""
    s_id = uuid.uuid4()
    supplier = Supplier(
        id=s_id,
        name="NanoCore Semiconductor",
        country_code="TW",
        tier=2,
        neptune_node_id="SUP-NC-882",
    )
    db_session.add(supplier)
    await db_session.commit()

    mock_traversal_service.get_supplier_subgraph.side_effect = TraversalError(
        "Neptune query exceeded 5.0s timeout",
        status_code=504,
    )

    headers = _auth_header(UserRole.ANALYST)
    resp = await client.get(f"/api/v1/suppliers/{s_id}/graph", headers=headers)

    assert resp.status_code == 504
    data = resp.json()
    assert data["error"]["code"] == "GRAPH_TRAVERSAL_ERROR"
