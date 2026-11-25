"""Integration Tests for RBAC 403 Scenarios and Governance Boundaries (P14-5).

Verifies strict role-based access control and high-consequence spend gating:
1. Scenario 1 (Analyst Blocked from Approvals):
   - `analyst` attempting `GET /api/v1/approvals` -> 403 Forbidden (INSUFFICIENT_ROLE).
   - `analyst` attempting `GET /api/v1/approvals/{id}` -> 403 Forbidden (INSUFFICIENT_ROLE).
   - `analyst` attempting `POST /api/v1/approvals/{id}/sign` -> 403 Forbidden (INSUFFICIENT_ROLE).
   - `analyst` attempting `POST /api/v1/cases/{id}/approve` -> 403 Forbidden (INSUFFICIENT_ROLE).
   - `analyst` attempting `POST /api/v1/approvals/{id}/reject` -> 403 Forbidden (INSUFFICIENT_ROLE).
2. Scenario 2 (Category Manager Blocked from Tier 3 Spend):
   - `category_manager` attempting to sign > $100,000 spend actions (e.g. NanoCore $2,448,105.00
     or $150,000.00 commitment) -> 403 Forbidden (INSUFFICIENT_ROLE).
   - Alias route `POST /api/v1/cases/{id}/approve` strictly enforces the same gate.
   - DB record status preserved in PENDING state; zero unauthorized state mutations.
3. Scenario 3 (Category Manager Blocked from Tier 2 Spend):
   - `category_manager` attempting to sign Tier 2 spend ($25,001 - $100,000, e.g. $50,000.00) -> 403 Forbidden.
   - Procurement Director signing the same approval succeeds -> 200 OK (APPROVED).
4. Scenario 4 (Exact Spend Boundary Thresholds):
   - Exact $25,000.00 (Tier 1 ceiling): Category Manager succeeds -> 200 OK (APPROVED).
   - Exact $25,000.01 (Tier 2 floor): Category Manager rejected with 403; Procurement Director succeeds.
   - Exact $100,000.00 (Tier 2 ceiling): Category Manager rejected with 403; Procurement Director succeeds.
   - Exact $100,000.01 (Tier 3 floor): Category Manager rejected with 403; Procurement Director moves to
     PARTIALLY_APPROVED; dual VP sign-off completes to APPROVED.
5. Scenario 5 (Tier 3 Unilateral Approval Strictly Prohibited):
   - Pure function `can_user_approve_spend` rejects single approval for Tier 3 regardless of role.
   - In API: Procurement Director sign 1 -> PARTIALLY_APPROVED.
   - Duplicate sign attempt by same Director -> 409 DUPLICATE_SIGNER.
   - Dual sign-off by VP Supply Chain -> APPROVED.
6. Scenario 6 (Analyst Blocked from Alert Mutation):
   - `analyst` calling `POST /api/v1/alerts/{id}/acknowledge` -> 403 Forbidden.
   - `category_manager` calling acknowledge route -> 200 OK (ACKNOWLEDGED).
   - `analyst` reading audit trail `GET /api/v1/alerts/{id}/audit` -> 200 OK.
7. Scenario 7 (Unauthenticated & Tampered Requests Return 401):
   - Missing header, malformed token, expired JWT, and forged signature return 401 AUTHENTICATION_REQUIRED.
8. Scenario 8 (Role Spoofing & Privilege Elevation Defense):
   - Unrecognized roles and manipulated scope claims cannot bypass authorization checks.
"""

import json
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from src.api.main import app
from src.core.hitl_tokens import (
    HITLTokenService,
    SpendTier,
)
from src.core.security import (
    AuthenticatedUser,
    UserRole,
    create_access_token,
)
from src.core.spend_tier_router import (
    can_user_approve_spend,
    route_spend,
)
from src.database.models import (
    Base,
    HITLApproval,
    RiskAlert,
)
from src.database.session import get_db_session
from src.services.hitl_service import (
    HITLService,
    get_hitl_service,
)

# ------------------------------------------------------------------------------
# In-Memory Database Fixtures & Offline Isolation
# ------------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_engine() -> AsyncGenerator[Any, None]:
    """Provide an isolated in-memory SQLite async engine."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        json_serializer=lambda obj: json.dumps(obj, default=str),
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(db_engine: Any) -> async_sessionmaker[AsyncSession]:
    """Provide an async session factory bound to the in-memory engine."""
    return async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest_asyncio.fixture
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Provide a single scoped async session for assertions."""
    async with session_factory() as session:
        yield session


# ------------------------------------------------------------------------------
# Mock KMS Client & Services Fixtures
# ------------------------------------------------------------------------------


@pytest.fixture
def mock_kms_client() -> MagicMock:
    """Mock KMS client providing deterministic ECDSA P-256 signatures."""
    client = MagicMock()
    client.sign.return_value = {
        "Signature": b"mock_ecdsa_p256_der_signature_bytes_rbac_tests_1234567890",
        "KeyId": "arn:aws:kms:eu-central-1:123456789012:key/test-hitl-key",
        "SigningAlgorithm": "ECDSA_SHA_256",
    }
    client.verify.return_value = {
        "SignatureValid": True,
        "KeyId": "arn:aws:kms:eu-central-1:123456789012:key/test-hitl-key",
        "SigningAlgorithm": "ECDSA_SHA_256",
    }
    return client


@pytest.fixture
def token_service(mock_kms_client: MagicMock) -> HITLTokenService:
    """Instantiate HITLTokenService with mock KMS client."""
    return HITLTokenService(
        kms_client=mock_kms_client,
        key_arn="arn:aws:kms:eu-central-1:123456789012:key/test-hitl-key",
    )


@pytest.fixture
def hitl_service_instance(token_service: HITLTokenService) -> HITLService:
    """Instantiate HITLService bound to mock token service."""
    return HITLService(token_service=token_service)


@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    hitl_service_instance: HITLService,
) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient wired with FastAPI dependency overrides and mock audit logging."""

    async def _override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    def _override_get_hitl_service() -> HITLService:
        return hitl_service_instance

    app.dependency_overrides[get_db_session] = _override_get_db_session
    app.dependency_overrides[get_hitl_service] = _override_get_hitl_service
    transport = ASGITransport(app=app)

    with (
        patch("src.api.routes.approval_routes.write_audit_log", new=AsyncMock(return_value=None)),
        patch("src.services.hitl_service.write_audit_log", new=AsyncMock(return_value=None)),
        patch("src.api.routes.risk_routes.write_audit_log", new=AsyncMock(return_value=None)),
        patch("src.database.session.get_async_session_factory", return_value=session_factory),
    ):
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as async_http_client:
            yield async_http_client

    app.dependency_overrides.clear()


# ------------------------------------------------------------------------------
# Auth Token Helpers
# ------------------------------------------------------------------------------


def _auth_header(
    role: UserRole | str,
    user_id: str | None = None,
    expires_delta: timedelta | None = None,
    additional_claims: dict[str, Any] | None = None,
    key: str | None = None,
) -> dict[str, str]:
    """Generate Authorization header with valid mock Keycloak/Okta JWT."""
    uid = user_id or str(uuid.uuid4())
    role_val = role.value if isinstance(role, UserRole) else str(role)
    token = create_access_token(
        subject=uid,
        roles=[role_val],
        email=f"{role_val}@apexmotion.com",
        expires_delta=expires_delta,
        additional_claims=additional_claims,
        key=key,
    )
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------------------------
# Test 1: Analyst Calling Approval Endpoints Rejected with 403
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyst_blocked_from_all_approval_endpoints(
    client: AsyncClient,
    db_session: AsyncSession,
    token_service: HITLTokenService,
) -> None:
    """Verify that an analyst (read-only) calling approval routes is rejected with 403."""
    now = datetime.now(UTC)
    app_id = uuid.uuid4()
    alert_id = uuid.uuid4()
    amount = Decimal("15000.00")

    approval = HITLApproval(
        id=app_id,
        alert_id=alert_id,
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=amount,
        spend_tier="CATEGORY_MGR",
        token_hash=f"PENDING-{uuid.uuid4().hex}",
        status="PENDING",
        expires_at=now + timedelta(hours=1),
    )
    db_session.add(approval)
    await db_session.commit()

    analyst_uid = str(uuid.uuid4())
    analyst_headers = _auth_header(UserRole.ANALYST, user_id=analyst_uid)

    # 1. GET /api/v1/approvals (queue listing) -> 403
    resp_list = await client.get("/api/v1/approvals", headers=analyst_headers)
    assert resp_list.status_code == 403
    data_list = resp_list.json()
    assert data_list["error"]["code"] == "INSUFFICIENT_ROLE"
    assert "category_manager" in data_list["error"]["message"]

    # 2. GET /api/v1/approvals/{approval_id} (detail lookup) -> 403
    resp_detail = await client.get(f"/api/v1/approvals/{app_id}", headers=analyst_headers)
    assert resp_detail.status_code == 403
    data_detail = resp_detail.json()
    assert data_detail["error"]["code"] == "INSUFFICIENT_ROLE"

    # 3. POST /api/v1/approvals/{approval_id}/sign (sign route) -> 403
    token = token_service.issue_token(
        action_id=str(app_id),
        alert_id=str(alert_id),
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=amount,
        signer_id=analyst_uid,
        signer_role="analyst",
    )
    sign_payload = {
        "token": token.serialize(),
        "notes": "Attempted authorization by analyst.",
    }
    resp_sign = await client.post(
        f"/api/v1/approvals/{app_id}/sign",
        json=sign_payload,
        headers=analyst_headers,
    )
    assert resp_sign.status_code == 403
    data_sign = resp_sign.json()
    assert data_sign["error"]["code"] == "INSUFFICIENT_ROLE"

    # 4. POST /api/v1/cases/{approval_id}/approve (case approve alias) -> 403
    resp_case = await client.post(
        f"/api/v1/cases/{app_id}/approve",
        json=sign_payload,
        headers=analyst_headers,
    )
    assert resp_case.status_code == 403
    data_case = resp_case.json()
    assert data_case["error"]["code"] == "INSUFFICIENT_ROLE"

    # 5. POST /api/v1/approvals/{approval_id}/reject (rejection route) -> 403
    reject_payload = {
        "reason": "Unauthorized rejection attempt by analyst.",
    }
    resp_reject = await client.post(
        f"/api/v1/approvals/{app_id}/reject",
        json=reject_payload,
        headers=analyst_headers,
    )
    assert resp_reject.status_code == 403
    data_reject = resp_reject.json()
    assert data_reject["error"]["code"] == "INSUFFICIENT_ROLE"

    # Verify database state remains unmutated (PENDING, approved_by is None)
    await db_session.refresh(approval)
    assert approval.status == "PENDING"
    assert approval.approved_by is None


# ------------------------------------------------------------------------------
# Test 2: Category Manager Blocked from Tier 3 Spend (> $100k)
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_category_manager_blocked_from_tier_3_high_consequence_spend(
    client: AsyncClient,
    db_session: AsyncSession,
    token_service: HITLTokenService,
) -> None:
    """Verify Category Manager cannot sign >$100,000 Tier 3 actions (e.g. NanoCore $2,448,105.00)."""
    now = datetime.now(UTC)
    nanocore_exposure = Decimal("2448105.00")
    app_id = uuid.uuid4()
    alert_id = uuid.uuid4()

    approval = HITLApproval(
        id=app_id,
        alert_id=alert_id,
        action_type="SECONDARY_SOURCE_QUALIFICATION",
        amount_usd=nanocore_exposure,
        spend_tier="DUAL_VP",
        token_hash=f"PENDING-{uuid.uuid4().hex}",
        status="PENDING",
        expires_at=now + timedelta(minutes=30),
    )
    db_session.add(approval)
    await db_session.commit()

    cm_uid = str(uuid.uuid4())
    cm_headers = _auth_header(UserRole.CATEGORY_MANAGER, user_id=cm_uid)

    token = token_service.issue_token(
        action_id=str(app_id),
        alert_id=str(alert_id),
        action_type="SECONDARY_SOURCE_QUALIFICATION",
        amount_usd=nanocore_exposure,
        signer_id=cm_uid,
        signer_role="category_manager",
    )
    payload = {
        "token": token.serialize(),
        "notes": "Category manager attempting unilateral high-spend commitment.",
    }

    # Calling POST /api/v1/approvals/{id}/sign -> 403 Forbidden
    resp = await client.post(f"/api/v1/approvals/{app_id}/sign", json=payload, headers=cm_headers)
    assert resp.status_code == 403
    data = resp.json()
    assert data["error"]["code"] == "INSUFFICIENT_ROLE"
    assert "DUAL_VP" in data["error"]["message"]
    assert "2,448,105.00" in data["error"]["message"]

    # Calling POST /api/v1/cases/{id}/approve (alias) -> 403 Forbidden
    resp_alias = await client.post(
        f"/api/v1/cases/{app_id}/approve", json=payload, headers=cm_headers
    )
    assert resp_alias.status_code == 403
    assert resp_alias.json()["error"]["code"] == "INSUFFICIENT_ROLE"

    # Also test an explicit $150,000.00 commitment (Tier 3 floor excess)
    app2_id = uuid.uuid4()
    app2 = HITLApproval(
        id=app2_id,
        alert_id=alert_id,
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("150000.00"),
        spend_tier="DUAL_VP",
        token_hash=f"PENDING-{uuid.uuid4().hex}",
        status="PENDING",
        expires_at=now + timedelta(minutes=30),
    )
    db_session.add(app2)
    await db_session.commit()

    token2 = token_service.issue_token(
        action_id=str(app2_id),
        alert_id=str(alert_id),
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("150000.00"),
        signer_id=cm_uid,
        signer_role="category_manager",
    )
    resp2 = await client.post(
        f"/api/v1/approvals/{app2_id}/sign",
        json={"token": token2.serialize(), "notes": "Tier 3 test"},
        headers=cm_headers,
    )
    assert resp2.status_code == 403
    assert resp2.json()["error"]["code"] == "INSUFFICIENT_ROLE"

    # Verify DB records remain PENDING and unmutated
    await db_session.refresh(approval)
    assert approval.status == "PENDING"
    assert approval.approved_by is None


# ------------------------------------------------------------------------------
# Test 3: Category Manager Blocked from Tier 2 Spend ($25,001 - $100,000)
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_category_manager_blocked_from_tier_2_spend(
    client: AsyncClient,
    db_session: AsyncSession,
    token_service: HITLTokenService,
) -> None:
    """Verify Category Manager is blocked from Tier 2 spend, while Procurement Director succeeds."""
    now = datetime.now(UTC)
    tier2_amount = Decimal("50000.00")
    app_id = uuid.uuid4()
    alert_id = uuid.uuid4()

    approval = HITLApproval(
        id=app_id,
        alert_id=alert_id,
        action_type="SECONDARY_SOURCE",
        amount_usd=tier2_amount,
        spend_tier="PROC_DIRECTOR",
        token_hash=f"PENDING-{uuid.uuid4().hex}",
        status="PENDING",
        expires_at=now + timedelta(hours=1),
    )
    db_session.add(approval)
    await db_session.commit()

    cm_uid = str(uuid.uuid4())
    cm_headers = _auth_header(UserRole.CATEGORY_MANAGER, user_id=cm_uid)

    token_cm = token_service.issue_token(
        action_id=str(app_id),
        alert_id=str(alert_id),
        action_type="SECONDARY_SOURCE",
        amount_usd=tier2_amount,
        signer_id=cm_uid,
        signer_role="category_manager",
    )
    payload_cm = {
        "token": token_cm.serialize(),
        "notes": "Category manager attempting Tier 2 sign-off.",
    }

    # 1. Category Manager rejected with 403
    resp_cm = await client.post(
        f"/api/v1/approvals/{app_id}/sign", json=payload_cm, headers=cm_headers
    )
    assert resp_cm.status_code == 403
    data_cm = resp_cm.json()
    assert data_cm["error"]["code"] == "INSUFFICIENT_ROLE"
    assert "PROC_DIRECTOR" in data_cm["error"]["message"]

    # 2. Procurement Director signing the same approval succeeds (200 OK -> APPROVED)
    director_uid = str(uuid.uuid4())
    director_headers = _auth_header(UserRole.PROCUREMENT_DIRECTOR, user_id=director_uid)

    token_director = token_service.issue_token(
        action_id=str(app_id),
        alert_id=str(alert_id),
        action_type="SECONDARY_SOURCE",
        amount_usd=tier2_amount,
        signer_id=director_uid,
        signer_role="procurement_director",
    )
    payload_director = {
        "token": token_director.serialize(),
        "notes": "Procurement Director authorized tooling setup.",
    }

    resp_dir = await client.post(
        f"/api/v1/approvals/{app_id}/sign",
        json=payload_director,
        headers=director_headers,
    )
    assert resp_dir.status_code == 200
    data_dir = resp_dir.json()
    assert data_dir["status"] == "APPROVED"
    assert director_uid in data_dir["approved_by"]

    # Verify DB reflects state transition
    await db_session.refresh(approval)
    assert approval.status == "APPROVED"


# ------------------------------------------------------------------------------
# Test 4: Exact Spend Boundary Threshold Enforcement
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spend_tier_exact_boundary_conditions(
    client: AsyncClient,
    db_session: AsyncSession,
    token_service: HITLTokenService,
) -> None:
    """Verify exact boundary threshold enforcement: $25k.00 vs $25k.01 and $100k.00 vs $100k.01."""
    now = datetime.now(UTC)
    cm_uid = str(uuid.uuid4())
    cm_headers = _auth_header(UserRole.CATEGORY_MANAGER, user_id=cm_uid)
    director_uid = str(uuid.uuid4())
    director_headers = _auth_header(UserRole.PROCUREMENT_DIRECTOR, user_id=director_uid)
    vp_uid = str(uuid.uuid4())
    vp_headers = _auth_header(UserRole.VP_SUPPLY_CHAIN, user_id=vp_uid)

    # --------------------------------------------------------------------------
    # Boundary 1A: Exact $25,000.00 (Tier 1 Maximum Ceiling)
    # --------------------------------------------------------------------------
    route_b1a = route_spend(Decimal("25000.00"))
    assert route_b1a.tier == SpendTier.CATEGORY_MGR
    assert route_b1a.required_signatures == 1

    alert_b1a = uuid.uuid4()
    app_b1a = HITLApproval(
        id=uuid.uuid4(),
        alert_id=alert_b1a,
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("25000.00"),
        spend_tier="CATEGORY_MGR",
        token_hash=f"PENDING-{uuid.uuid4().hex}",
        status="PENDING",
        expires_at=now + timedelta(hours=1),
    )
    db_session.add(app_b1a)
    await db_session.commit()

    tok_b1a = token_service.issue_token(
        action_id=str(app_b1a.id),
        alert_id=str(alert_b1a),
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("25000.00"),
        signer_id=cm_uid,
        signer_role="category_manager",
    )
    resp_b1a = await client.post(
        f"/api/v1/approvals/{app_b1a.id}/sign",
        json={"token": tok_b1a.serialize(), "notes": "Boundary $25k.00 Category Manager allowed."},
        headers=cm_headers,
    )
    assert resp_b1a.status_code == 200
    assert resp_b1a.json()["status"] == "APPROVED"

    # --------------------------------------------------------------------------
    # Boundary 1B: Exact $25,000.01 (Tier 2 Minimum Floor)
    # --------------------------------------------------------------------------
    route_b1b = route_spend(Decimal("25000.01"))
    assert route_b1b.tier == SpendTier.PROC_DIRECTOR
    assert route_b1b.required_signatures == 1

    alert_b1b = uuid.uuid4()
    app_b1b = HITLApproval(
        id=uuid.uuid4(),
        alert_id=alert_b1b,
        action_type="SECONDARY_SOURCE",
        amount_usd=Decimal("25000.01"),
        spend_tier="PROC_DIRECTOR",
        token_hash=f"PENDING-{uuid.uuid4().hex}",
        status="PENDING",
        expires_at=now + timedelta(hours=1),
    )
    db_session.add(app_b1b)
    await db_session.commit()

    tok_b1b_cm = token_service.issue_token(
        action_id=str(app_b1b.id),
        alert_id=str(alert_b1b),
        action_type="SECONDARY_SOURCE",
        amount_usd=Decimal("25000.01"),
        signer_id=cm_uid,
        signer_role="category_manager",
    )
    # Category Manager rejected with 403 on $25,000.01
    resp_b1b_cm = await client.post(
        f"/api/v1/approvals/{app_b1b.id}/sign",
        json={"token": tok_b1b_cm.serialize(), "notes": "CM sign boundary 25000.01"},
        headers=cm_headers,
    )
    assert resp_b1b_cm.status_code == 403
    assert resp_b1b_cm.json()["error"]["code"] == "INSUFFICIENT_ROLE"

    # Procurement Director succeeds on $25,000.01
    tok_b1b_dir = token_service.issue_token(
        action_id=str(app_b1b.id),
        alert_id=str(alert_b1b),
        action_type="SECONDARY_SOURCE",
        amount_usd=Decimal("25000.01"),
        signer_id=director_uid,
        signer_role="procurement_director",
    )
    resp_b1b_dir = await client.post(
        f"/api/v1/approvals/{app_b1b.id}/sign",
        json={"token": tok_b1b_dir.serialize(), "notes": "Director sign boundary 25000.01"},
        headers=director_headers,
    )
    assert resp_b1b_dir.status_code == 200
    assert resp_b1b_dir.json()["status"] == "APPROVED"

    # --------------------------------------------------------------------------
    # Boundary 2A: Exact $100,000.00 (Tier 2 Maximum Ceiling)
    # --------------------------------------------------------------------------
    route_b2a = route_spend(Decimal("100000.00"))
    assert route_b2a.tier == SpendTier.PROC_DIRECTOR
    assert route_b2a.required_signatures == 1

    alert_b2a = uuid.uuid4()
    app_b2a = HITLApproval(
        id=uuid.uuid4(),
        alert_id=alert_b2a,
        action_type="SECONDARY_SOURCE",
        amount_usd=Decimal("100000.00"),
        spend_tier="PROC_DIRECTOR",
        token_hash=f"PENDING-{uuid.uuid4().hex}",
        status="PENDING",
        expires_at=now + timedelta(hours=1),
    )
    db_session.add(app_b2a)
    await db_session.commit()

    # Category Manager rejected with 403 on $100,000.00
    tok_b2a_cm = token_service.issue_token(
        action_id=str(app_b2a.id),
        alert_id=str(alert_b2a),
        action_type="SECONDARY_SOURCE",
        amount_usd=Decimal("100000.00"),
        signer_id=cm_uid,
        signer_role="category_manager",
    )
    resp_b2a_cm = await client.post(
        f"/api/v1/approvals/{app_b2a.id}/sign",
        json={"token": tok_b2a_cm.serialize(), "notes": "CM sign boundary 100k"},
        headers=cm_headers,
    )
    assert resp_b2a_cm.status_code == 403

    # Procurement Director succeeds on $100,000.00 (Tier 2 max)
    tok_b2a_dir = token_service.issue_token(
        action_id=str(app_b2a.id),
        alert_id=str(alert_b2a),
        action_type="SECONDARY_SOURCE",
        amount_usd=Decimal("100000.00"),
        signer_id=director_uid,
        signer_role="procurement_director",
    )
    resp_b2a_dir = await client.post(
        f"/api/v1/approvals/{app_b2a.id}/sign",
        json={"token": tok_b2a_dir.serialize(), "notes": "Director sign boundary 100k"},
        headers=director_headers,
    )
    assert resp_b2a_dir.status_code == 200
    assert resp_b2a_dir.json()["status"] == "APPROVED"

    # --------------------------------------------------------------------------
    # Boundary 2B: Exact $100,000.01 (Tier 3 Minimum Floor -> Dual Sign-off)
    # --------------------------------------------------------------------------
    route_b2b = route_spend(Decimal("100000.01"))
    assert route_b2b.tier == SpendTier.DUAL_VP
    assert route_b2b.required_signatures == 2
    assert route_b2b.requires_dual_approval is True

    alert_b2b = uuid.uuid4()
    app_b2b = HITLApproval(
        id=uuid.uuid4(),
        alert_id=alert_b2b,
        action_type="DUAL_RESERVATION",
        amount_usd=Decimal("100000.01"),
        spend_tier="DUAL_VP",
        token_hash=f"PENDING-{uuid.uuid4().hex}",
        status="PENDING",
        expires_at=now + timedelta(minutes=30),
    )
    db_session.add(app_b2b)
    await db_session.commit()

    # Category Manager rejected with 403 on $100,000.01
    tok_b2b_cm = token_service.issue_token(
        action_id=str(app_b2b.id),
        alert_id=str(alert_b2b),
        action_type="DUAL_RESERVATION",
        amount_usd=Decimal("100000.01"),
        signer_id=cm_uid,
        signer_role="category_manager",
    )
    resp_b2b_cm = await client.post(
        f"/api/v1/approvals/{app_b2b.id}/sign",
        json={"token": tok_b2b_cm.serialize(), "notes": "CM sign boundary 100000.01"},
        headers=cm_headers,
    )
    assert resp_b2b_cm.status_code == 403

    # Procurement Director signs signature 1 -> PARTIALLY_APPROVED
    tok_b2b_dir = token_service.issue_token(
        action_id=str(app_b2b.id),
        alert_id=str(alert_b2b),
        action_type="DUAL_RESERVATION",
        amount_usd=Decimal("100000.01"),
        signer_id=director_uid,
        signer_role="procurement_director",
    )
    resp_b2b_dir = await client.post(
        f"/api/v1/approvals/{app_b2b.id}/sign",
        json={"token": tok_b2b_dir.serialize(), "notes": "Director sign 1 of 2"},
        headers=director_headers,
    )
    assert resp_b2b_dir.status_code == 200
    assert resp_b2b_dir.json()["status"] == "PARTIALLY_APPROVED"

    # VP Supply Chain signs signature 2 -> APPROVED
    tok_b2b_vp = token_service.issue_token(
        action_id=str(app_b2b.id),
        alert_id=str(alert_b2b),
        action_type="DUAL_RESERVATION",
        amount_usd=Decimal("100000.01"),
        signer_id=vp_uid,
        signer_role="vp_supply_chain",
    )
    resp_b2b_vp = await client.post(
        f"/api/v1/approvals/{app_b2b.id}/sign",
        json={"token": tok_b2b_vp.serialize(), "notes": "VP sign 2 of 2"},
        headers=vp_headers,
    )
    assert resp_b2b_vp.status_code == 200
    assert resp_b2b_vp.json()["status"] == "APPROVED"


# ------------------------------------------------------------------------------
# Test 5: Tier 3 Unilateral Single Approval Strictly Prohibited
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tier_3_unilateral_single_approval_strictly_prohibited(
    client: AsyncClient,
    db_session: AsyncSession,
    token_service: HITLTokenService,
) -> None:
    """Verify that no single user can unilaterally approve Tier 3 spend and duplicate signers are blocked."""
    nanocore_amount = Decimal("2448105.00")

    # 1. Pure spend router verification across all roles
    roles_to_test = [
        UserRole.ANALYST,
        UserRole.CATEGORY_MANAGER,
        UserRole.PROCUREMENT_DIRECTOR,
        UserRole.VP_SUPPLY_CHAIN,
        UserRole.SYSTEM_ADMIN,
    ]
    for role in roles_to_test:
        user = AuthenticatedUser(user_id=f"user-{role.value}", roles=[role.value])
        can_approve, reason = can_user_approve_spend(user, nanocore_amount)
        assert can_approve is False, f"Role '{role.value}' should not unilaterally approve Tier 3"
        assert "dual sign-off from Procurement Director and VP Supply Chain" in reason

    # 2. API integration verification
    now = datetime.now(UTC)
    app_id = uuid.uuid4()
    alert_id = uuid.uuid4()
    approval = HITLApproval(
        id=app_id,
        alert_id=alert_id,
        action_type="SECONDARY_SOURCE_QUALIFICATION",
        amount_usd=nanocore_amount,
        spend_tier="DUAL_VP",
        token_hash=f"PENDING-{uuid.uuid4().hex}",
        status="PENDING",
        expires_at=now + timedelta(minutes=30),
    )
    db_session.add(approval)
    await db_session.commit()

    director_uid = str(uuid.uuid4())
    director_headers = _auth_header(UserRole.PROCUREMENT_DIRECTOR, user_id=director_uid)

    tok1 = token_service.issue_token(
        action_id=str(app_id),
        alert_id=str(alert_id),
        action_type="SECONDARY_SOURCE_QUALIFICATION",
        amount_usd=nanocore_amount,
        signer_id=director_uid,
        signer_role="procurement_director",
    )

    # First signature succeeds -> PARTIALLY_APPROVED
    resp1 = await client.post(
        f"/api/v1/approvals/{app_id}/sign",
        json={"token": tok1.serialize(), "notes": "Director initial signature."},
        headers=director_headers,
    )
    assert resp1.status_code == 200
    assert resp1.json()["status"] == "PARTIALLY_APPROVED"

    # Attempt second signature with SAME Director -> 409 DUPLICATE_SIGNER conflict
    tok1_replay_attempt = token_service.issue_token(
        action_id=str(app_id),
        alert_id=str(alert_id),
        action_type="SECONDARY_SOURCE_QUALIFICATION",
        amount_usd=nanocore_amount,
        signer_id=director_uid,
        signer_role="procurement_director",
    )
    resp_dup = await client.post(
        f"/api/v1/approvals/{app_id}/sign",
        json={
            "token": tok1_replay_attempt.serialize(),
            "notes": "Director attempting unilateral second signature.",
        },
        headers=director_headers,
    )
    assert resp_dup.status_code == 409
    assert resp_dup.json()["error"]["code"] == "DUPLICATE_SIGNER"

    # Distinct VP Supply Chain provides valid second signature -> APPROVED
    vp_uid = str(uuid.uuid4())
    vp_headers = _auth_header(UserRole.VP_SUPPLY_CHAIN, user_id=vp_uid)

    tok2 = token_service.issue_token(
        action_id=str(app_id),
        alert_id=str(alert_id),
        action_type="SECONDARY_SOURCE_QUALIFICATION",
        amount_usd=nanocore_amount,
        signer_id=vp_uid,
        signer_role="vp_supply_chain",
    )
    resp2 = await client.post(
        f"/api/v1/approvals/{app_id}/sign",
        json={"token": tok2.serialize(), "notes": "VP secondary sign-off."},
        headers=vp_headers,
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["status"] == "APPROVED"
    assert len(data2["approved_by"]) == 2
    assert director_uid in data2["approved_by"]
    assert vp_uid in data2["approved_by"]


# ------------------------------------------------------------------------------
# Test 6: Analyst Blocked from Alert Acknowledgment / Allowed Audit Read
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyst_blocked_from_alert_acknowledgment_but_allowed_audit_read(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify analyst cannot mutate/acknowledge alerts (403), but can read audit logs (200)."""
    alert_id = uuid.uuid4()
    alert = RiskAlert(
        id=alert_id,
        component_sku="NC-2024-001",
        risk_level="CRITICAL",
        days_of_cover=Decimal("7.68"),
        financial_exposure=Decimal("2448105.00"),
        shortage_volume=24420,
        status="OPEN",
    )
    db_session.add(alert)
    await db_session.commit()

    analyst_headers = _auth_header(UserRole.ANALYST)
    cm_headers = _auth_header(UserRole.CATEGORY_MANAGER)

    # 1. Analyst calling POST /api/v1/alerts/{id}/acknowledge -> 403 Forbidden
    resp_ack1 = await client.post(
        f"/api/v1/alerts/{alert_id}/acknowledge",
        json={"notes": "Analyst attempted acknowledgment."},
        headers=analyst_headers,
    )
    assert resp_ack1.status_code == 403
    assert resp_ack1.json()["error"]["code"] == "INSUFFICIENT_ROLE"

    # 2. Analyst calling secondary route POST /api/v1/risk/alerts/{id}/acknowledge -> 403
    resp_ack2 = await client.post(
        f"/api/v1/risk/alerts/{alert_id}/acknowledge",
        json={"notes": "Analyst attempted secondary route acknowledgment."},
        headers=analyst_headers,
    )
    assert resp_ack2.status_code == 403
    assert resp_ack2.json()["error"]["code"] == "INSUFFICIENT_ROLE"

    # 3. Category Manager calling acknowledge route -> 200 OK (ACKNOWLEDGED)
    resp_cm = await client.post(
        f"/api/v1/alerts/{alert_id}/acknowledge",
        json={"notes": "Category manager acknowledged alert for triage."},
        headers=cm_headers,
    )
    assert resp_cm.status_code == 200
    assert resp_cm.json()["status"] == "ACKNOWLEDGED"

    # 4. Analyst reading audit trail GET /api/v1/alerts/{id}/audit -> 200 OK
    resp_audit = await client.get(
        f"/api/v1/alerts/{alert_id}/audit",
        headers=analyst_headers,
    )
    assert resp_audit.status_code == 200
    data_audit = resp_audit.json()
    assert data_audit["entity_id"] == str(alert_id)
    assert data_audit["entity_type"] == "RISK_ALERT"


# ------------------------------------------------------------------------------
# Test 7: Unauthenticated & Tampered Requests Return 401
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthenticated_and_tampered_jwt_requests_return_401(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify missing, expired, forged, or malformed credentials return 401 AUTHENTICATION_REQUIRED."""
    app_id = uuid.uuid4()
    approval = HITLApproval(
        id=app_id,
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("15000.00"),
        spend_tier="CATEGORY_MGR",
        token_hash=f"PENDING-{uuid.uuid4().hex}",
        status="PENDING",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(approval)
    await db_session.commit()

    # 1. Missing Authorization header -> 401
    resp_missing = await client.get("/api/v1/approvals")
    assert resp_missing.status_code == 401
    assert resp_missing.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    # 2. Malformed / non-JWT token -> 401
    resp_malformed = await client.get(
        "/api/v1/approvals",
        headers={"Authorization": "Bearer not-a-valid-jwt-token"},
    )
    assert resp_malformed.status_code == 401
    assert resp_malformed.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    # 3. Invalid scheme (Basic instead of Bearer) -> 401
    resp_scheme = await client.get(
        "/api/v1/approvals",
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert resp_scheme.status_code == 401

    # 4. Expired JWT token -> 401
    expired_headers = _auth_header(
        UserRole.CATEGORY_MANAGER,
        expires_delta=timedelta(seconds=-120),
    )
    resp_expired = await client.get("/api/v1/approvals", headers=expired_headers)
    assert resp_expired.status_code == 401
    assert "expired" in resp_expired.json()["error"]["message"].lower()

    # 5. Forged signature (signed with untrusted private secret key) -> 401
    forged_headers = _auth_header(
        UserRole.CATEGORY_MANAGER,
        key="untrusted-forged-secret-key-1234567890",
    )
    resp_forged = await client.get("/api/v1/approvals", headers=forged_headers)
    assert resp_forged.status_code == 401
    assert resp_forged.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    # 6. Token missing subject identifier (`sub`) -> 401
    no_sub_token = create_access_token(
        subject="",
        roles=[UserRole.CATEGORY_MANAGER],
    )
    resp_no_sub = await client.get(
        "/api/v1/approvals",
        headers={"Authorization": f"Bearer {no_sub_token}"},
    )
    assert resp_no_sub.status_code == 401
    assert resp_no_sub.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


# ------------------------------------------------------------------------------
# Test 8: Role Elevation and Spoofing Defense
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_role_elevation_and_spoofing_defense(
    client: AsyncClient,
) -> None:
    """Verify arbitrary roles, fabricated scopes, and casing variations are safely governed."""
    # 1. Unrecognized / arbitrary roles (e.g. contractor, guest) -> 403
    for arbitrary_role in ["contractor", "guest_viewer", "external_supplier", "auditor"]:
        token = create_access_token(
            subject=str(uuid.uuid4()),
            roles=[arbitrary_role],
        )
        resp = await client.get(
            "/api/v1/approvals",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403, (
            f"Arbitrary role '{arbitrary_role}' must be rejected with 403"
        )
        assert resp.json()["error"]["code"] == "INSUFFICIENT_ROLE"

    # 2. Scope injection without valid role claims -> 403
    scope_token = create_access_token(
        subject=str(uuid.uuid4()),
        roles=[],
        additional_claims={"scp": "approvals:admin risk:write all:access"},
    )
    resp_scope = await client.get(
        "/api/v1/approvals",
        headers={"Authorization": f"Bearer {scope_token}"},
    )
    assert resp_scope.status_code == 403
    assert resp_scope.json()["error"]["code"] == "INSUFFICIENT_ROLE"

    # 3. Case and whitespace variations in recognized roles normalize safely
    # (e.g., '  CATEGORY_MANAGER  ' correctly grants Category Manager access)
    normalized_token = create_access_token(
        subject=str(uuid.uuid4()),
        roles=["  CATEGORY_MANAGER  "],
    )
    resp_norm = await client.get(
        "/api/v1/approvals",
        headers={"Authorization": f"Bearer {normalized_token}"},
    )
    assert resp_norm.status_code == 200, "Normalized role string should be accepted"


# ------------------------------------------------------------------------------
# Test 9: Role Hierarchy Level Inheritance
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_role_hierarchy_inheritance(
    client: AsyncClient,
) -> None:
    """Verify higher roles inherit permissions of lower roles, while lower roles remain restricted."""
    # Procurement Director (level 30), VP Supply Chain (level 40), and Admin (level 50)
    # can all access Category Manager (level 20) routes such as GET /api/v1/approvals
    higher_roles = [
        UserRole.PROCUREMENT_DIRECTOR,
        UserRole.VP_SUPPLY_CHAIN,
        UserRole.SYSTEM_ADMIN,
    ]
    for r in higher_roles:
        headers = _auth_header(r)
        resp = await client.get("/api/v1/approvals", headers=headers)
        assert resp.status_code == 200, f"Role '{r.value}' should inherit access to list approvals"

    # Read-only analyst (level 10) cannot access
    analyst_headers = _auth_header(UserRole.ANALYST)
    resp_analyst = await client.get("/api/v1/approvals", headers=analyst_headers)
    assert resp_analyst.status_code == 403
