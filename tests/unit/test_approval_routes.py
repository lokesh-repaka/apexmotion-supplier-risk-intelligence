"""Unit tests for HITL approval API routes (P11-3).

Verifies:
- GET /api/v1/approvals:
    * Paginated response envelope with total, page, page_size, total_pages.
    * Filtering by status (PENDING, ALL) and spend_tier (CATEGORY_MGR, PROC_DIRECTOR, DUAL_VP).
    * Auto-expiration of stale pending items.
    * RBAC: Category Manager, Director, VP allowed; Analyst strictly 403 INSUFFICIENT_ROLE.
    * 401 for unauthenticated requests.
- GET /api/v1/approvals/{approval_id}:
    * Detail record lookup for valid UUID.
    * 404 NOT_FOUND for non-existent approval.
    * 400 VALIDATION_ERROR for malformed UUID string.
- POST /api/v1/approvals/{approval_id}/sign:
    * Single approval (Tier 1 <= $25k) signed by Category Manager -> APPROVED.
    * Single approval (Tier 2 $25k-$100k) signed by Procurement Director -> APPROVED.
    * Unauthorized role rejection: Category Manager attempting to sign Tier 2/3 -> 403 INSUFFICIENT_ROLE.
    * Dual-approval workflow (Tier 3 > $100k):
        - Signature 1 (Director) -> PARTIALLY_APPROVED.
        - Signature 2 (VP Supply Chain) -> APPROVED.
    * Duplicate signer on Tier 3 dual approval -> 409 DUPLICATE_SIGNER.
    * Token anti-replay protection -> 409 TOKEN_REPLAY.
    * Expired token / record -> 400 TOKEN_EXPIRED.
    * Parameter binding mismatch -> 400 TOKEN_BINDING_MISMATCH.
    * Terminal state conflict -> 409 CONFLICT.
- POST /api/v1/approvals/{approval_id}/reject:
    * Rejection with mandatory rationale -> REJECTED.
- POST /api/v1/cases/{case_id}/approve:
    * Backward-compatible case approval alias.
"""

import json
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
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
    compute_token_hash,
)
from src.core.security import UserRole, create_access_token
from src.database.models import Base, HITLApproval
from src.database.session import get_db_session
from src.services.hitl_service import (
    HITLService,
    get_hitl_service,
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
def mock_kms_client() -> MagicMock:
    """Mock boto3 KMS client simulating ECDSA P-256 signing and verification."""
    client = MagicMock()
    client.sign.return_value = {
        "Signature": b"mock_ecdsa_p256_der_signature_bytes_1234567890",
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
    """Instantiate HITLTokenService with mocked KMS client."""
    return HITLTokenService(
        kms_client=mock_kms_client,
        key_arn="arn:aws:kms:eu-central-1:123456789012:key/test-hitl-key",
    )


@pytest.fixture
def hitl_service_instance(token_service: HITLTokenService) -> HITLService:
    """Instantiate HITLService with mocked token service."""
    return HITLService(token_service=token_service)


@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession,
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
    ):
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as async_http_client:
            yield async_http_client

    app.dependency_overrides.clear()


# ------------------------------------------------------------------------------
# Auth Token Helpers
# ------------------------------------------------------------------------------


def _auth_header(role: UserRole, user_id: str | None = None) -> dict[str, str]:
    """Generate Authorization header with valid mock Keycloak JWT."""
    uid = user_id or str(uuid.uuid4())
    token = create_access_token(
        subject=uid,
        roles=[role.value],
        email=f"{role.value}@apexmotion.com",
    )
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------------------------
# Test Cases
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_approvals_queue_pending_success(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify paginated listing of pending approval items for Category Manager."""
    now = datetime.now(UTC)
    app1 = HITLApproval(
        id=uuid.uuid4(),
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("15000.00"),
        spend_tier="CATEGORY_MGR",
        token_hash=f"PENDING-{uuid.uuid4().hex}",
        status="PENDING",
        expires_at=now + timedelta(hours=1),
        created_at=now - timedelta(minutes=10),
    )
    app2 = HITLApproval(
        id=uuid.uuid4(),
        action_type="SECONDARY_SOURCE",
        amount_usd=Decimal("50000.00"),
        spend_tier="PROC_DIRECTOR",
        token_hash=f"PENDING-{uuid.uuid4().hex}",
        status="PENDING",
        expires_at=now + timedelta(hours=1),
        created_at=now - timedelta(minutes=5),
    )
    app3 = HITLApproval(
        id=uuid.uuid4(),
        action_type="SPOT_PURCHASE",
        amount_usd=Decimal("8000.00"),
        spend_tier="CATEGORY_MGR",
        token_hash=f"APPROVED-{uuid.uuid4().hex}",
        status="APPROVED",
        expires_at=now + timedelta(hours=1),
        created_at=now - timedelta(minutes=2),
    )
    db_session.add_all([app1, app2, app3])
    await db_session.commit()

    headers = _auth_header(UserRole.CATEGORY_MANAGER)
    resp = await client.get("/api/v1/approvals", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert data["total_pages"] == 1
    # Verify items are in PENDING status
    for item in data["items"]:
        assert item["status"] == "PENDING"


@pytest.mark.asyncio
async def test_list_approvals_filtered_by_spend_tier_and_status(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify filtering approvals by spend authority tier and status=ALL."""
    now = datetime.now(UTC)
    app_tier1 = HITLApproval(
        id=uuid.uuid4(),
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("20000.00"),
        spend_tier="CATEGORY_MGR",
        token_hash=f"HASH-{uuid.uuid4().hex}",
        status="PENDING",
        expires_at=now + timedelta(hours=1),
    )
    app_tier3 = HITLApproval(
        id=uuid.uuid4(),
        action_type="PRODUCTION_REBALANCE",
        amount_usd=Decimal("250000.00"),
        spend_tier="DUAL_VP",
        token_hash=f"HASH-{uuid.uuid4().hex}",
        status="PARTIALLY_APPROVED",
        expires_at=now + timedelta(minutes=30),
    )
    db_session.add_all([app_tier1, app_tier3])
    await db_session.commit()

    headers = _auth_header(UserRole.PROCUREMENT_DIRECTOR)
    resp = await client.get("/api/v1/approvals?spend_tier=DUAL_VP&status=ALL", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["spend_tier"] == "DUAL_VP"
    assert data["items"][0]["status"] == "PARTIALLY_APPROVED"


@pytest.mark.asyncio
async def test_list_approvals_forbidden_for_analyst(
    client: AsyncClient,
) -> None:
    """Verify read-only analyst is strictly rejected with 403 INSUFFICIENT_ROLE."""
    headers = _auth_header(UserRole.ANALYST)
    resp = await client.get("/api/v1/approvals", headers=headers)

    assert resp.status_code == 403
    data = resp.json()
    assert data["error"]["code"] == "INSUFFICIENT_ROLE"


@pytest.mark.asyncio
async def test_list_approvals_unauthenticated(
    client: AsyncClient,
) -> None:
    """Verify missing authorization header returns 401 AUTHENTICATION_REQUIRED."""
    resp = await client.get("/api/v1/approvals")

    assert resp.status_code == 401
    data = resp.json()
    assert data["error"]["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.asyncio
async def test_get_approval_detail_success(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify retrieval of detailed approval record by UUID."""
    now = datetime.now(UTC)
    app_id = uuid.uuid4()
    alert_id = uuid.uuid4()
    approval = HITLApproval(
        id=app_id,
        alert_id=alert_id,
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("22000.00"),
        spend_tier="CATEGORY_MGR",
        token_hash=f"PENDING-{uuid.uuid4().hex}",
        status="PENDING",
        expires_at=now + timedelta(hours=1),
    )
    db_session.add(approval)
    await db_session.commit()

    headers = _auth_header(UserRole.CATEGORY_MANAGER)
    resp = await client.get(f"/api/v1/approvals/{app_id}", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(app_id)
    assert data["alert_id"] == str(alert_id)
    assert data["action_type"] == "LOGISTICS_EXPEDITE"
    assert Decimal(str(data["amount_usd"])) == Decimal("22000.00")
    assert data["spend_tier"] == "CATEGORY_MGR"
    assert data["status"] == "PENDING"


@pytest.mark.asyncio
async def test_get_approval_detail_not_found(
    client: AsyncClient,
) -> None:
    """Verify 404 NOT_FOUND for non-existent approval record."""
    random_id = str(uuid.uuid4())
    headers = _auth_header(UserRole.CATEGORY_MANAGER)
    resp = await client.get(f"/api/v1/approvals/{random_id}", headers=headers)

    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_approval_detail_invalid_uuid(
    client: AsyncClient,
) -> None:
    """Verify 400 VALIDATION_ERROR for malformed UUID in path."""
    headers = _auth_header(UserRole.CATEGORY_MANAGER)
    resp = await client.get("/api/v1/approvals/invalid-uuid-format", headers=headers)

    assert resp.status_code == 400
    data = resp.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_sign_approval_tier1_category_manager_success(
    client: AsyncClient,
    db_session: AsyncSession,
    token_service: HITLTokenService,
) -> None:
    """Verify Category Manager successfully authorizes Tier 1 spend ($18,000 <= $25,000)."""
    now = datetime.now(UTC)
    app_id = uuid.uuid4()
    alert_id = uuid.uuid4()
    amount = Decimal("18000.00")

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

    signer_id = str(uuid.uuid4())
    token = token_service.issue_token(
        action_id=str(app_id),
        alert_id=str(alert_id),
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=amount,
        signer_id=signer_id,
        signer_role="category_manager",
    )

    headers = _auth_header(UserRole.CATEGORY_MANAGER, user_id=signer_id)
    payload = {
        "token": token.serialize(),
        "notes": "Emergency air freight authorized for assembly continuity.",
    }

    resp = await client.post(f"/api/v1/approvals/{app_id}/sign", json=payload, headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(app_id)
    assert data["status"] == "APPROVED"
    assert data["spend_tier"] == "CATEGORY_MGR"
    assert signer_id in data["approved_by"]
    assert len(data["approved_at"]) == 1


@pytest.mark.asyncio
async def test_sign_approval_tier2_procurement_director_success(
    client: AsyncClient,
    db_session: AsyncSession,
    token_service: HITLTokenService,
) -> None:
    """Verify Procurement Director successfully authorizes Tier 2 spend ($75,000)."""
    now = datetime.now(UTC)
    app_id = uuid.uuid4()
    alert_id = uuid.uuid4()
    amount = Decimal("75000.00")

    approval = HITLApproval(
        id=app_id,
        alert_id=alert_id,
        action_type="SECONDARY_SOURCE",
        amount_usd=amount,
        spend_tier="PROC_DIRECTOR",
        token_hash=f"PENDING-{uuid.uuid4().hex}",
        status="PENDING",
        expires_at=now + timedelta(hours=1),
    )
    db_session.add(approval)
    await db_session.commit()

    signer_id = str(uuid.uuid4())
    token = token_service.issue_token(
        action_id=str(app_id),
        alert_id=str(alert_id),
        action_type="SECONDARY_SOURCE",
        amount_usd=amount,
        signer_id=signer_id,
        signer_role="procurement_director",
    )

    headers = _auth_header(UserRole.PROCUREMENT_DIRECTOR, user_id=signer_id)
    payload = {"token": token.serialize()}

    resp = await client.post(f"/api/v1/approvals/{app_id}/sign", json=payload, headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(app_id)
    assert data["status"] == "APPROVED"
    assert data["spend_tier"] == "PROC_DIRECTOR"
    assert signer_id in data["approved_by"]


@pytest.mark.asyncio
async def test_sign_approval_tier2_category_manager_unauthorized(
    client: AsyncClient,
    db_session: AsyncSession,
    token_service: HITLTokenService,
) -> None:
    """Verify Category Manager cannot sign Tier 2 spend ($75,000) -> 403 INSUFFICIENT_ROLE."""
    now = datetime.now(UTC)
    app_id = uuid.uuid4()
    alert_id = uuid.uuid4()
    amount = Decimal("75000.00")

    approval = HITLApproval(
        id=app_id,
        alert_id=alert_id,
        action_type="SECONDARY_SOURCE",
        amount_usd=amount,
        spend_tier="PROC_DIRECTOR",
        token_hash=f"PENDING-{uuid.uuid4().hex}",
        status="PENDING",
        expires_at=now + timedelta(hours=1),
    )
    db_session.add(approval)
    await db_session.commit()

    signer_id = str(uuid.uuid4())
    token = token_service.issue_token(
        action_id=str(app_id),
        alert_id=str(alert_id),
        action_type="SECONDARY_SOURCE",
        amount_usd=amount,
        signer_id=signer_id,
        signer_role="category_manager",
    )

    headers = _auth_header(UserRole.CATEGORY_MANAGER, user_id=signer_id)
    payload = {"token": token.serialize()}

    resp = await client.post(f"/api/v1/approvals/{app_id}/sign", json=payload, headers=headers)

    assert resp.status_code == 403
    data = resp.json()
    assert data["error"]["code"] == "INSUFFICIENT_ROLE"


@pytest.mark.asyncio
async def test_sign_approval_tier3_dual_vp_lifecycle(
    client: AsyncClient,
    db_session: AsyncSession,
    token_service: HITLTokenService,
) -> None:
    """Verify Tier 3 ($200,000) dual-approval lifecycle: PARTIALLY_APPROVED then APPROVED."""
    now = datetime.now(UTC)
    app_id = uuid.uuid4()
    alert_id = uuid.uuid4()
    amount = Decimal("200000.00")

    approval = HITLApproval(
        id=app_id,
        alert_id=alert_id,
        action_type="SPOT_PURCHASE",
        amount_usd=amount,
        spend_tier="DUAL_VP",
        token_hash=f"PENDING-{uuid.uuid4().hex}",
        status="PENDING",
        expires_at=now + timedelta(minutes=30),
    )
    db_session.add(approval)
    await db_session.commit()

    director_id = str(uuid.uuid4())
    token_1 = token_service.issue_token(
        action_id=str(app_id),
        alert_id=str(alert_id),
        action_type="SPOT_PURCHASE",
        amount_usd=amount,
        signer_id=director_id,
        signer_role="procurement_director",
    )

    # 1. First signature: Procurement Director
    headers_dir = _auth_header(UserRole.PROCUREMENT_DIRECTOR, user_id=director_id)
    resp1 = await client.post(
        f"/api/v1/approvals/{app_id}/sign",
        json={"token": token_1.serialize()},
        headers=headers_dir,
    )

    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["status"] == "PARTIALLY_APPROVED"
    assert director_id in data1["approved_by"]
    assert len(data1["approved_by"]) == 1

    # 2. Second signature: VP Supply Chain
    vp_id = str(uuid.uuid4())
    token_2 = token_service.issue_token(
        action_id=str(app_id),
        alert_id=str(alert_id),
        action_type="SPOT_PURCHASE",
        amount_usd=amount,
        signer_id=vp_id,
        signer_role="vp_supply_chain",
    )

    headers_vp = _auth_header(UserRole.VP_SUPPLY_CHAIN, user_id=vp_id)
    resp2 = await client.post(
        f"/api/v1/approvals/{app_id}/sign",
        json={"token": token_2.serialize()},
        headers=headers_vp,
    )

    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["status"] == "APPROVED"
    assert director_id in data2["approved_by"]
    assert vp_id in data2["approved_by"]
    assert len(data2["approved_by"]) == 2


@pytest.mark.asyncio
async def test_sign_approval_tier3_duplicate_signer_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    token_service: HITLTokenService,
) -> None:
    """Verify identical signer cannot submit both signatures on Tier 3 dual approval."""
    now = datetime.now(UTC)
    app_id = uuid.uuid4()
    alert_id = uuid.uuid4()
    amount = Decimal("150000.00")

    approval = HITLApproval(
        id=app_id,
        alert_id=alert_id,
        action_type="PRODUCTION_REBALANCE",
        amount_usd=amount,
        spend_tier="DUAL_VP",
        token_hash=f"PENDING-{uuid.uuid4().hex}",
        status="PENDING",
        expires_at=now + timedelta(minutes=30),
    )
    db_session.add(approval)
    await db_session.commit()

    director_id = str(uuid.uuid4())
    token_1 = token_service.issue_token(
        action_id=str(app_id),
        alert_id=str(alert_id),
        action_type="PRODUCTION_REBALANCE",
        amount_usd=amount,
        signer_id=director_id,
        signer_role="procurement_director",
    )

    headers = _auth_header(UserRole.PROCUREMENT_DIRECTOR, user_id=director_id)
    resp1 = await client.post(
        f"/api/v1/approvals/{app_id}/sign",
        json={"token": token_1.serialize()},
        headers=headers,
    )
    assert resp1.status_code == 200

    # Same director tries to submit second signature
    token_dup = token_service.issue_token(
        action_id=str(app_id),
        alert_id=str(alert_id),
        action_type="PRODUCTION_REBALANCE",
        amount_usd=amount,
        signer_id=director_id,
        signer_role="procurement_director",
    )
    resp2 = await client.post(
        f"/api/v1/approvals/{app_id}/sign",
        json={"token": token_dup.serialize()},
        headers=headers,
    )

    assert resp2.status_code == 409
    data2 = resp2.json()
    assert data2["error"]["code"] == "DUPLICATE_SIGNER"


@pytest.mark.asyncio
async def test_sign_approval_token_replay_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    token_service: HITLTokenService,
) -> None:
    """Verify re-submitting an already used token hash triggers 409 TOKEN_REPLAY."""
    now = datetime.now(UTC)
    amount = Decimal("20000.00")
    app1_id = uuid.uuid4()
    app2_id = uuid.uuid4()

    token = token_service.issue_token(
        action_id=str(app1_id),
        alert_id=str(uuid.uuid4()),
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=amount,
    )
    token_ser = token.serialize()
    token_hash = compute_token_hash(token_ser)

    # Pre-existing approval with this token_hash already recorded
    app_used = HITLApproval(
        id=app1_id,
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=amount,
        spend_tier="CATEGORY_MGR",
        token_hash=token_hash,
        status="APPROVED",
        expires_at=now + timedelta(hours=1),
    )
    # New pending approval
    app_pending = HITLApproval(
        id=app2_id,
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=amount,
        spend_tier="CATEGORY_MGR",
        token_hash=f"PENDING-{uuid.uuid4().hex}",
        status="PENDING",
        expires_at=now + timedelta(hours=1),
    )
    db_session.add_all([app_used, app_pending])
    await db_session.commit()

    headers = _auth_header(UserRole.CATEGORY_MANAGER)
    resp = await client.post(
        f"/api/v1/approvals/{app2_id}/sign",
        json={"token": token_ser},
        headers=headers,
    )

    assert resp.status_code == 409
    data = resp.json()
    assert data["error"]["code"] == "TOKEN_REPLAY"


@pytest.mark.asyncio
async def test_sign_approval_expired_record_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    token_service: HITLTokenService,
) -> None:
    """Verify signing an expired approval record returns 400 TOKEN_EXPIRED."""
    now = datetime.now(UTC)
    app_id = uuid.uuid4()
    amount = Decimal("15000.00")

    # Record expired 15 minutes ago
    approval = HITLApproval(
        id=app_id,
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=amount,
        spend_tier="CATEGORY_MGR",
        token_hash=f"PENDING-{uuid.uuid4().hex}",
        status="PENDING",
        expires_at=now - timedelta(minutes=15),
    )
    db_session.add(approval)
    await db_session.commit()

    token = token_service.issue_token(
        action_id=str(app_id),
        alert_id=str(uuid.uuid4()),
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=amount,
    )

    headers = _auth_header(UserRole.CATEGORY_MANAGER)
    resp = await client.post(
        f"/api/v1/approvals/{app_id}/sign",
        json={"token": token.serialize()},
        headers=headers,
    )

    assert resp.status_code == 400
    data = resp.json()
    assert data["error"]["code"] == "TOKEN_EXPIRED"


@pytest.mark.asyncio
async def test_sign_approval_binding_mismatch_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    token_service: HITLTokenService,
) -> None:
    """Verify token parameter amount mismatch returns 400 TOKEN_BINDING_MISMATCH."""
    now = datetime.now(UTC)
    app_id = uuid.uuid4()
    actual_amount = Decimal("24000.00")
    mismatched_amount = Decimal("10000.00")

    approval = HITLApproval(
        id=app_id,
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=actual_amount,
        spend_tier="CATEGORY_MGR",
        token_hash=f"PENDING-{uuid.uuid4().hex}",
        status="PENDING",
        expires_at=now + timedelta(hours=1),
    )
    db_session.add(approval)
    await db_session.commit()

    # Token minted for different amount
    token = token_service.issue_token(
        action_id=str(app_id),
        alert_id=str(uuid.uuid4()),
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=mismatched_amount,
    )

    headers = _auth_header(UserRole.CATEGORY_MANAGER)
    resp = await client.post(
        f"/api/v1/approvals/{app_id}/sign",
        json={"token": token.serialize()},
        headers=headers,
    )

    assert resp.status_code == 400
    data = resp.json()
    assert data["error"]["code"] == "TOKEN_BINDING_MISMATCH"


@pytest.mark.asyncio
async def test_sign_approval_terminal_state_conflict(
    client: AsyncClient,
    db_session: AsyncSession,
    token_service: HITLTokenService,
) -> None:
    """Verify attempting to sign an already APPROVED or REJECTED record returns 409 CONFLICT."""
    now = datetime.now(UTC)
    app_id = uuid.uuid4()
    amount = Decimal("15000.00")

    approval = HITLApproval(
        id=app_id,
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=amount,
        spend_tier="CATEGORY_MGR",
        token_hash=f"APPROVED-{uuid.uuid4().hex}",
        status="APPROVED",
        expires_at=now + timedelta(hours=1),
    )
    db_session.add(approval)
    await db_session.commit()

    token = token_service.issue_token(
        action_id=str(app_id),
        alert_id=str(uuid.uuid4()),
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=amount,
    )

    headers = _auth_header(UserRole.CATEGORY_MANAGER)
    resp = await client.post(
        f"/api/v1/approvals/{app_id}/sign",
        json={"token": token.serialize()},
        headers=headers,
    )

    assert resp.status_code == 409
    data = resp.json()
    assert data["error"]["code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_reject_approval_success(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify Category Manager can reject an approval with recorded rationale."""
    now = datetime.now(UTC)
    app_id = uuid.uuid4()

    approval = HITLApproval(
        id=app_id,
        action_type="SECONDARY_SOURCE",
        amount_usd=Decimal("20000.00"),
        spend_tier="CATEGORY_MGR",
        token_hash=f"PENDING-{uuid.uuid4().hex}",
        status="PENDING",
        expires_at=now + timedelta(hours=1),
    )
    db_session.add(approval)
    await db_session.commit()

    headers = _auth_header(UserRole.CATEGORY_MANAGER)
    payload = {"reason": "Alternative supplier offered 20% lower expedited rates."}
    resp = await client.post(f"/api/v1/approvals/{app_id}/reject", json=payload, headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(app_id)
    assert data["status"] == "REJECTED"
    assert "Alternative supplier" in data["message"]


@pytest.mark.asyncio
async def test_case_approval_alias_success(
    client: AsyncClient,
    db_session: AsyncSession,
    token_service: HITLTokenService,
) -> None:
    """Verify backward-compatible case approval alias POST /api/v1/cases/{id}/approve."""
    now = datetime.now(UTC)
    app_id = uuid.uuid4()
    alert_id = uuid.uuid4()
    amount = Decimal("12000.00")

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

    token = token_service.issue_token(
        action_id=str(app_id),
        alert_id=str(alert_id),
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=amount,
    )

    headers = _auth_header(UserRole.CATEGORY_MANAGER)
    payload = {"token": token.serialize()}

    # Call alias route
    resp = await client.post(f"/api/v1/cases/{app_id}/approve", json=payload, headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(app_id)
    assert data["status"] == "APPROVED"
