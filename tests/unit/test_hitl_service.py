"""Unit tests for HITL Service (P10-1).

Enforces:
- The Triad of Responsibility (BR-RULE-001):
  * Strict Decimal monetary precision for all spend commitments; float values strictly prohibited.
  * Deterministic spend tier routing:
    - Tier 1 (CATEGORY_MGR): Spend <= $25,000 (1x token, 1-hr TTL).
    - Tier 2 (PROC_DIRECTOR): Spend $25,001 - $100,000 (1x token, 1-hr TTL).
    - Tier 3 (DUAL_VP): Spend > $100,000 (Dual sign-off, 30-min TTL).
- Cryptographic Token Lifecycle:
  * Issues AWS KMS ECDSA P-256 tokens bound to action ID, alert ID, amount USD, and spend tier.
  * Enforces temporal expiration (1-hour vs 30-minute TTL).
  * Cryptographic anti-replay protection via token SHA-256 hash checking against repository.
  * Dual-approval verification for high-value (> $100k) consequential actions.
- Offline Isolation:
  * 100% offline unit execution using mocked KMS client and in-memory SQLite database.
"""

import json
import threading
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.core.demo_auth import DEMO_PERSONAS
from src.core.hitl_tokens import (
    HITLToken,
    HITLTokenPayload,
    HITLTokenService,
    SpendTier,
)
from src.core.security import UserRole
from src.database.models import Base, HITLApproval, RiskAlert
from src.database.repositories.hitl_approval_repository import HITLApprovalRepository
from src.services.hitl_service import (
    ApprovalCreateInput,
    ApprovalNotFoundError,
    HITLService,
    InvalidApprovalOperationError,
    TokenExpiredServiceError,
    TokenReplayServiceError,
    TokenVerificationServiceError,
    UnauthorizedSignerError,
    get_hitl_service,
)


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
def hitl_service(token_service: HITLTokenService) -> HITLService:
    """Instantiate HITLService with mocked token service."""
    return HITLService(token_service=token_service)


@pytest_asyncio.fixture
async def async_db_session():
    """Create an isolated in-memory SQLite database session for repository testing."""
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

    await engine.dispose()


# ------------------------------------------------------------------------------
# 1. Spend Tier Routing & TTL Governance Tests
# ------------------------------------------------------------------------------


def test_hitl_service_spend_tier_routing_and_ttl_enforcement(
    hitl_service: HITLService,
) -> None:
    """Verify monetary thresholds map deterministically to spend tiers and TTL limits."""
    # Tier 1: Spend <= $25,000 -> Category Manager, 1-hr TTL
    route1 = hitl_service.route_spend(Decimal("15000.00"))
    assert route1.tier == SpendTier.CATEGORY_MGR
    assert route1.token_ttl == timedelta(hours=1)
    assert route1.required_signatures == 1
    assert UserRole.CATEGORY_MANAGER in route1.required_roles

    # Boundary Tier 1: Exactly $25,000.00
    route1_bound = hitl_service.route_spend(Decimal("25000.00"))
    assert route1_bound.tier == SpendTier.CATEGORY_MGR
    assert route1_bound.token_ttl == timedelta(hours=1)

    # Tier 2: Spend $25,001 - $100,000 -> Procurement Director, 1-hr TTL
    route2 = hitl_service.route_spend(Decimal("25000.01"))
    assert route2.tier == SpendTier.PROC_DIRECTOR
    assert route2.token_ttl == timedelta(hours=1)
    assert route2.required_signatures == 1
    assert UserRole.PROCUREMENT_DIRECTOR in route2.required_roles

    # Boundary Tier 2: Exactly $100,000.00
    route2_bound = hitl_service.route_spend(Decimal("100000.00"))
    assert route2_bound.tier == SpendTier.PROC_DIRECTOR
    assert route2_bound.token_ttl == timedelta(hours=1)

    # Tier 3: Spend > $100,000 -> Dual sign-off, 30-min TTL
    route3 = hitl_service.route_spend(Decimal("100000.01"))
    assert route3.tier == SpendTier.DUAL_VP
    assert route3.token_ttl == timedelta(minutes=30)
    assert route3.required_signatures == 2
    assert route3.requires_dual_approval is True
    assert UserRole.PROCUREMENT_DIRECTOR in route3.required_roles
    assert UserRole.VP_SUPPLY_CHAIN in route3.required_roles

    # NanoCore Golden commitment ($285,000)
    route_nc = hitl_service.route_spend(Decimal("285000.00"))
    assert route_nc.tier == SpendTier.DUAL_VP
    assert route_nc.token_ttl == timedelta(minutes=30)
    assert route_nc.required_signatures == 2


def test_hitl_service_float_rejection(hitl_service: HITLService) -> None:
    """Verify float monetary values are strictly rejected under BR-RULE-001."""
    with pytest.raises(TypeError, match="Float values are strictly prohibited"):
        hitl_service.route_spend(50000.0)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="Spend amount cannot be negative"):
        hitl_service.route_spend(Decimal("-100.00"))


# ------------------------------------------------------------------------------
# 2. Token Issuance & Signer Authority Validation Tests
# ------------------------------------------------------------------------------


def test_hitl_service_issue_token_success(hitl_service: HITLService) -> None:
    """Verify token issuance creates a cryptographically signed token with accurate parameters."""
    token = hitl_service.issue_token(
        action_id="ACT-SPOT-001",
        alert_id="ALT-2026-NC-001",
        action_type="SECONDARY_SOURCE_SPOT_BUY",
        amount_usd=Decimal("180000.00"),
        signer_id="usr-marcus-vance",
        signer_role="vp_supply_chain",
    )

    assert isinstance(token, HITLToken)
    assert token.payload.action_id == "ACT-SPOT-001"
    assert token.payload.alert_id == "ALT-2026-NC-001"
    assert token.payload.amount_usd == Decimal("180000.00")
    assert token.payload.spend_tier == SpendTier.DUAL_VP
    assert token.payload.signer_id == "usr-marcus-vance"
    assert token.payload.signer_role == "vp_supply_chain"
    assert len(token.token_hash) == 64
    assert token.signature != ""

    # Tier 3 must enforce 30-minute TTL
    expected_ttl = timedelta(minutes=30)
    actual_ttl = token.payload.expires_at - token.payload.issued_at
    assert abs(actual_ttl.total_seconds() - expected_ttl.total_seconds()) < 2.0


def test_hitl_service_issue_token_tier1_1_hour_ttl(hitl_service: HITLService) -> None:
    """Verify Tier 1 token receives a 1-hour validity window."""
    token = hitl_service.issue_token(
        action_id="ACT-FREIGHT-001",
        alert_id="ALT-2026-001",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("15000.00"),
        signer_id="usr-sarah-chen",
        signer_role="category_manager",
    )

    assert token.payload.spend_tier == SpendTier.CATEGORY_MGR
    actual_ttl = token.payload.expires_at - token.payload.issued_at
    assert abs(actual_ttl.total_seconds() - 3600.0) < 2.0


def test_hitl_service_issue_token_with_user_authority_validation(
    hitl_service: HITLService,
) -> None:
    """Verify signer authority validation permits authorized personas and rejects unauthorized roles."""
    # 1. Category Manager approving $20,000 (Tier 1) -> Success
    cat_mgr = DEMO_PERSONAS["category_manager"]
    token = hitl_service.issue_token(
        action_id="ACT-001",
        alert_id="ALT-001",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("20000.00"),
        user=cat_mgr,  # Category Manager ($25k limit)
    )
    assert token.payload.signer_id == cat_mgr.user_id
    assert token.payload.spend_tier == SpendTier.CATEGORY_MGR

    # 2. Category Manager attempting to approve $50,000 (Tier 2 limit $100k) -> Unauthorized
    with pytest.raises(UnauthorizedSignerError, match="Insufficient permissions"):
        hitl_service.issue_token(
            action_id="ACT-002",
            alert_id="ALT-001",
            action_type="SECONDARY_SOURCE_SPOT_BUY",
            amount_usd=Decimal("50000.00"),
            user=cat_mgr,
        )

    # 3. Supply Chain Analyst attempting to approve $5,000 -> Unauthorized (Read-only, $0 limit)
    analyst = DEMO_PERSONAS["analyst"]
    with pytest.raises(UnauthorizedSignerError, match="Analyst role has read-only"):
        hitl_service.issue_token(
            action_id="ACT-003",
            alert_id="ALT-001",
            action_type="LOGISTICS_EXPEDITE",
            amount_usd=Decimal("5000.00"),
            user=analyst,
        )

    # 4. Unilateral single approval for Tier 3 (> $100,000) is rejected
    director = DEMO_PERSONAS["procurement_director"]
    with pytest.raises(UnauthorizedSignerError, match="dual sign-off"):
        hitl_service.issue_token(
            action_id="ACT-004",
            alert_id="ALT-001",
            action_type="SECONDARY_SOURCE_SPOT_BUY",
            amount_usd=Decimal("150000.00"),
            user=director,  # Director cannot unilaterally approve > $100k
        )


def test_hitl_service_issue_token_with_explicit_signer_bypasses_user_check(
    hitl_service: HITLService,
) -> None:
    """Verify passing explicit signer_id without user object allows programmatic issuance."""
    token = hitl_service.issue_token(
        action_id="ACT-DIRECT-001",
        alert_id="ALT-001",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("50000.00"),
        signer_id="usr-proc-director-01",
        signer_role="procurement_director",
    )
    assert token.payload.signer_id == "usr-proc-director-01"
    assert token.payload.signer_role == "procurement_director"


# ------------------------------------------------------------------------------
# 3. Token Verification & Anti-Replay Tests
# ------------------------------------------------------------------------------


def test_hitl_service_verify_token_valid(hitl_service: HITLService) -> None:
    """Verify valid token returns TokenVerificationResult with is_valid=True."""
    token = hitl_service.issue_token(
        action_id="ACT-VERIFY-001",
        alert_id="ALT-VERIFY-001",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("20000.00"),
    )

    res = hitl_service.verify_token(
        token=token,
        expected_action_id="ACT-VERIFY-001",
        expected_alert_id="ALT-VERIFY-001",
        expected_amount_usd=Decimal("20000.00"),
    )
    assert res.is_valid is True
    assert res.error is None
    assert res.token_hash == token.token_hash


def test_hitl_service_verify_token_expired(hitl_service: HITLService) -> None:
    """Verify expired token returns error or raises TokenExpiredServiceError."""
    now = datetime.now(UTC)
    expired_payload = HITLTokenPayload(
        action_id="ACT-EXP-001",
        alert_id="ALT-EXP-001",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("10000.00"),
        spend_tier=SpendTier.CATEGORY_MGR,
        issued_at=now - timedelta(hours=2),
        expires_at=now - timedelta(hours=1),
    )
    expired_token = HITLToken(
        payload=expired_payload,
        signature="mock_sig",
        key_arn="mock_arn",
        token_hash="mock_hash",
    )

    res = hitl_service.verify_token(expired_token, raise_on_error=False)
    assert res.is_valid is False
    assert res.error == "TOKEN_EXPIRED"

    with pytest.raises(TokenExpiredServiceError, match="expired"):
        hitl_service.verify_token(expired_token, raise_on_error=True)


def test_hitl_service_verify_token_parameter_mismatches(hitl_service: HITLService) -> None:
    """Verify parameter binding mismatches (action, alert, amount) are detected."""
    token = hitl_service.issue_token(
        action_id="ACT-M-001",
        alert_id="ALT-M-001",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("15000.00"),
    )

    # Action ID mismatch
    res_act = hitl_service.verify_token(token, expected_action_id="ACT-WRONG")
    assert res_act.is_valid is False
    assert res_act.error == "ACTION_MISMATCH"

    # Alert ID mismatch
    res_alt = hitl_service.verify_token(token, expected_alert_id="ALT-WRONG")
    assert res_alt.is_valid is False
    assert res_alt.error == "ALERT_MISMATCH"

    # Amount mismatch
    res_amt = hitl_service.verify_token(token, expected_amount_usd=Decimal("99999.00"))
    assert res_amt.is_valid is False
    assert res_amt.error == "AMOUNT_MISMATCH"

    with pytest.raises(TokenVerificationServiceError, match="Action_id mismatch"):
        hitl_service.verify_token(token, expected_action_id="ACT-WRONG", raise_on_error=True)


@pytest.mark.asyncio
async def test_hitl_service_verify_anti_replay_with_repository(
    hitl_service: HITLService,
    async_db_session: AsyncSession,
) -> None:
    """Verify anti-replay validation detects and rejects reused cryptographic tokens."""
    repo = HITLApprovalRepository(async_db_session)

    token = hitl_service.issue_token(
        action_id="ACT-REPLAY-001",
        alert_id="ALT-REPLAY-001",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("10000.00"),
    )

    # 1. Unused token must pass anti-replay check
    is_unused = await hitl_service.verify_anti_replay(token, repo)
    assert is_unused is True

    # 2. Persist approval with token hash in database
    approval = HITLApproval(
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("10000.00"),
        spend_tier="CATEGORY_MGR",
        token_hash=token.token_hash,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        status="APPROVED",
    )
    await repo.create_approval(approval)
    await async_db_session.commit()

    # 3. Check now reports replay
    is_used = await hitl_service.verify_anti_replay(token, repo)
    assert is_used is False

    with pytest.raises(TokenReplayServiceError, match="replay detected"):
        await hitl_service.verify_anti_replay(token, repo, raise_on_error=True)


# ------------------------------------------------------------------------------
# 4. Dual Sign-Off Governance Tests
# ------------------------------------------------------------------------------


def test_hitl_service_verify_dual_approval_success(hitl_service: HITLService) -> None:
    """Verify dual sign-off requires two independently signed tokens with distinct executive signers."""
    token_director = hitl_service.issue_token(
        action_id="ACT-DUAL-001",
        alert_id="ALT-DUAL-001",
        action_type="SECONDARY_SOURCE_SPOT_BUY",
        amount_usd=Decimal("285000.00"),
        signer_id="usr-elena-rostova",
        signer_role="procurement_director",
    )
    token_vp = hitl_service.issue_token(
        action_id="ACT-DUAL-001",
        alert_id="ALT-DUAL-001",
        action_type="SECONDARY_SOURCE_SPOT_BUY",
        amount_usd=Decimal("285000.00"),
        signer_id="usr-marcus-vance",
        signer_role="vp_supply_chain",
    )

    res = hitl_service.verify_dual_approval(
        tokens=[token_director, token_vp],
        expected_action_id="ACT-DUAL-001",
        expected_alert_id="ALT-DUAL-001",
        expected_amount_usd=Decimal("285000.00"),
    )
    assert res.is_valid is True
    assert res.error is None


def test_hitl_service_verify_dual_approval_failures(hitl_service: HITLService) -> None:
    """Verify dual sign-off rejects single token, duplicate signer, or mismatched action IDs."""
    token1 = hitl_service.issue_token(
        action_id="ACT-FAIL-001",
        alert_id="ALT-FAIL-001",
        action_type="SECONDARY_SOURCE_SPOT_BUY",
        amount_usd=Decimal("200000.00"),
        signer_id="usr-director-01",
        signer_role="procurement_director",
    )

    # 1. Single token provided
    res_single = hitl_service.verify_dual_approval(tokens=[token1])
    assert res_single.is_valid is False
    assert res_single.error == "INSUFFICIENT_SIGNATURES"

    # 2. Same signer twice
    token_duplicate = hitl_service.issue_token(
        action_id="ACT-FAIL-001",
        alert_id="ALT-FAIL-001",
        action_type="SECONDARY_SOURCE_SPOT_BUY",
        amount_usd=Decimal("200000.00"),
        signer_id="usr-director-01",  # Same signer
        signer_role="procurement_director",
    )
    res_dup = hitl_service.verify_dual_approval(tokens=[token1, token_duplicate])
    assert res_dup.is_valid is False
    assert res_dup.error == "IDENTICAL_SIGNERS"

    # 3. Action ID mismatch between tokens
    token_diff_action = hitl_service.issue_token(
        action_id="ACT-DIFFERENT-002",
        alert_id="ALT-FAIL-001",
        action_type="SECONDARY_SOURCE_SPOT_BUY",
        amount_usd=Decimal("200000.00"),
        signer_id="usr-vp-02",
        signer_role="vp_supply_chain",
    )
    res_mismatch = hitl_service.verify_dual_approval(tokens=[token1, token_diff_action])
    assert res_mismatch.is_valid is False
    assert res_mismatch.error == "DUAL_ACTION_MISMATCH"


# ------------------------------------------------------------------------------
# 5. Database Approval Lifecycle & Repository Integration Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hitl_service_create_and_sign_approval_request(
    hitl_service: HITLService,
    async_db_session: AsyncSession,
) -> None:
    """Verify approval creation, spend tier routing, and single-signature execution."""
    alert_uuid = uuid.uuid4()
    alert = RiskAlert(
        id=alert_uuid,
        component_sku="SKU-CHIP-99",
        risk_level="HIGH",
        status="INVESTIGATING",
    )
    async_db_session.add(alert)
    await async_db_session.commit()

    # 1. Create approval request for $50,000 (Tier 2 PROC_DIRECTOR)
    input_data = ApprovalCreateInput(
        alert_id=alert_uuid,
        action_id="ACT-REQ-001",
        action_type="SECONDARY_SOURCE_SPOT_BUY",
        amount_usd=Decimal("50000.00"),
    )
    approval = await hitl_service.create_approval_request(async_db_session, input_data)

    assert approval.id is not None
    assert approval.spend_tier == "PROC_DIRECTOR"
    assert approval.status == "PENDING"
    assert approval.amount_usd == Decimal("50000.00")
    exp = (
        approval.expires_at.replace(tzinfo=UTC)
        if approval.expires_at.tzinfo is None
        else approval.expires_at
    )
    assert exp > datetime.now(UTC)

    # 2. Issue valid token
    token = hitl_service.issue_token(
        action_id="ACT-REQ-001",
        alert_id=str(alert_uuid),
        action_type="SECONDARY_SOURCE_SPOT_BUY",
        amount_usd=Decimal("50000.00"),
        signer_id="usr-elena-rostova",
        signer_role="procurement_director",
    )

    # 3. Sign approval
    signed_approval = await hitl_service.sign_approval(
        session=async_db_session,
        approval_id=approval.id,
        token=token,
        signer_id=uuid.uuid4(),
    )
    assert signed_approval.status == "APPROVED"
    assert signed_approval.token_hash == token.token_hash
    assert len(signed_approval.approved_by or []) == 1

    # 4. Attempting to sign the same approval again fails with InvalidApprovalOperationError
    with pytest.raises(InvalidApprovalOperationError):
        await hitl_service.sign_approval(
            session=async_db_session,
            approval_id=approval.id,
            token=token,
            signer_id=uuid.uuid4(),
        )

    # 5. Attempting to replay the used token on a new pending approval raises TokenReplayServiceError
    input_data_2 = ApprovalCreateInput(
        alert_id=alert_uuid,
        action_id="ACT-REQ-002",
        action_type="SECONDARY_SOURCE_SPOT_BUY",
        amount_usd=Decimal("50000.00"),
    )
    approval_2 = await hitl_service.create_approval_request(async_db_session, input_data_2)
    with pytest.raises(TokenReplayServiceError):
        await hitl_service.sign_approval(
            session=async_db_session,
            approval_id=approval_2.id,
            token=token,
            signer_id=uuid.uuid4(),
        )


@pytest.mark.asyncio
async def test_hitl_service_reject_approval_request(
    hitl_service: HITLService,
    async_db_session: AsyncSession,
) -> None:
    """Verify rejecting an approval updates status to REJECTED."""
    input_data = ApprovalCreateInput(
        action_id="ACT-REJ-001",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("15000.00"),
    )
    approval = await hitl_service.create_approval_request(async_db_session, input_data)

    rejected = await hitl_service.reject_approval(
        session=async_db_session,
        approval_id=approval.id,
        reason="Budget frozen by executive committee",
        actor_id="usr-elena-rostova",
    )
    assert rejected.status == "REJECTED"


@pytest.mark.asyncio
async def test_hitl_service_get_and_list_approvals(
    hitl_service: HITLService,
    async_db_session: AsyncSession,
) -> None:
    """Verify fetching and querying pending approvals."""
    app1 = await hitl_service.create_approval_request(
        async_db_session,
        ApprovalCreateInput(
            action_id="ACT-LIST-1",
            action_type="LOGISTICS_EXPEDITE",
            amount_usd=Decimal("10000.00"),
        ),
    )
    app2 = await hitl_service.create_approval_request(
        async_db_session,
        ApprovalCreateInput(
            action_id="ACT-LIST-2",
            action_type="SECONDARY_SOURCE_SPOT_BUY",
            amount_usd=Decimal("60000.00"),
        ),
    )

    fetched = await hitl_service.get_approval(async_db_session, app1.id)
    assert fetched is not None
    assert fetched.id == app1.id

    # Non-existent ID returns None
    missing = await hitl_service.get_approval(async_db_session, uuid.uuid4())
    assert missing is None

    # List pending
    pending = await hitl_service.list_pending_approvals(async_db_session)
    assert len(pending) >= 2

    # Filter by spend tier
    tier2_pending = await hitl_service.list_pending_approvals(
        async_db_session, spend_tier="PROC_DIRECTOR"
    )
    assert any(a.id == app2.id for a in tier2_pending)


@pytest.mark.asyncio
async def test_hitl_service_tier3_dual_approval_workflow(
    hitl_service: HITLService,
    async_db_session: AsyncSession,
) -> None:
    """Verify Tier 3 dual approval database workflow from PENDING to PARTIALLY_APPROVED to APPROVED."""
    alert_uuid = uuid.uuid4()
    alert = RiskAlert(
        id=alert_uuid,
        component_sku="SKU-EXP-001",
        risk_level="CRITICAL",
        status="INVESTIGATING",
    )
    async_db_session.add(alert)
    await async_db_session.commit()

    # 1. Create Tier 3 approval request ($150,000)
    input_data = ApprovalCreateInput(
        alert_id=alert_uuid,
        action_id="ACT-DUAL-001",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("150000.00"),
    )
    approval = await hitl_service.create_approval_request(async_db_session, input_data)
    assert approval.spend_tier == "DUAL_VP"
    assert approval.status == "PENDING"

    # 2. Issue tokens for two distinct signers
    signer_1_id = uuid.uuid4()
    signer_2_id = uuid.uuid4()

    token_1 = hitl_service.issue_token(
        action_id="ACT-DUAL-001",
        alert_id=str(alert_uuid),
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("150000.00"),
        signer_id=str(signer_1_id),
        signer_role="procurement_director",
    )

    token_2 = hitl_service.issue_token(
        action_id="ACT-DUAL-001",
        alert_id=str(alert_uuid),
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("150000.00"),
        signer_id=str(signer_2_id),
        signer_role="vp_supply_chain",
    )

    # 3. First signature: transitions to PARTIALLY_APPROVED
    partially_signed = await hitl_service.sign_approval(
        session=async_db_session,
        approval_id=approval.id,
        token=token_1,
        signer_id=signer_1_id,
    )
    assert partially_signed.status == "PARTIALLY_APPROVED"
    assert len(partially_signed.approved_by or []) == 1

    # 4. Duplicate signature attempt by signer 1 raises UnauthorizedSignerError
    with pytest.raises(UnauthorizedSignerError, match="Duplicate signer"):
        await hitl_service.sign_approval(
            session=async_db_session,
            approval_id=approval.id,
            token=token_1,
            signer_id=signer_1_id,
        )

    # 5. Second signature by distinct executive signer 2 transitions to APPROVED
    fully_signed = await hitl_service.sign_approval(
        session=async_db_session,
        approval_id=approval.id,
        token=token_2,
        signer_id=signer_2_id,
    )
    assert fully_signed.status == "APPROVED"
    assert len(fully_signed.approved_by or []) == 2
    assert fully_signed.token_hash == token_2.token_hash


@pytest.mark.asyncio
async def test_hitl_service_approval_not_found_and_errors(
    hitl_service: HITLService,
    async_db_session: AsyncSession,
) -> None:
    """Verify ApprovalNotFoundError is raised when operating on non-existent records."""
    random_id = uuid.uuid4()

    # Sign non-existent
    token = hitl_service.issue_token(
        action_id="ACT-ERR-001",
        alert_id="ALT-ERR-001",
        action_type="SPOT_BUY",
        amount_usd=Decimal("10000.00"),
        signer_id="usr-test",
        signer_role="category_manager",
    )
    with pytest.raises(ApprovalNotFoundError):
        await hitl_service.sign_approval(
            session=async_db_session,
            approval_id=random_id,
            token=token,
            signer_id=uuid.uuid4(),
        )

    # Reject non-existent
    with pytest.raises(ApprovalNotFoundError):
        await hitl_service.reject_approval(
            session=async_db_session,
            approval_id=random_id,
            reason="Test rejection",
            actor_id=uuid.uuid4(),
        )

    # Get non-existent
    res = await hitl_service.get_approval(async_db_session, random_id)
    assert res is None


@pytest.mark.asyncio
async def test_hitl_service_expired_on_get(
    hitl_service: HITLService,
    async_db_session: AsyncSession,
) -> None:
    """Verify get_approval automatically updates status to EXPIRED if TTL passed."""
    repo = HITLApprovalRepository(async_db_session)
    expired_approval = HITLApproval(
        id=uuid.uuid4(),
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("5000.00"),
        spend_tier="CATEGORY_MGR",
        token_hash="exp_test_token_hash",
        status="PENDING",
        expires_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    await repo.create(expired_approval)

    fetched = await hitl_service.get_approval(async_db_session, expired_approval.id)
    assert fetched is not None
    assert fetched.status == "EXPIRED"


@pytest.mark.asyncio
async def test_hitl_service_verify_token_and_anti_replay_raise_on_error(
    hitl_service: HITLService,
    mock_kms_client: MagicMock,
    async_db_session: AsyncSession,
) -> None:
    """Verify raise_on_error flags raise appropriate service errors and invalid signature handling."""
    token = hitl_service.issue_token(
        action_id="ACT-VER-001",
        alert_id="ALT-VER-001",
        action_type="SPOT_BUY",
        amount_usd=Decimal("10000.00"),
        signer_id="usr-cat-01",
        signer_role="category_manager",
    )

    # verify_token with amount mismatch and raise_on_error=True
    with pytest.raises(TokenVerificationServiceError):
        hitl_service.verify_token(
            token=token,
            expected_amount_usd=Decimal("99999.00"),
            raise_on_error=True,
        )

    # Invalid signature branch
    mock_kms_client.verify.return_value = {"SignatureValid": False}
    res_invalid_sig = hitl_service.verify_token(token, raise_on_error=False)
    assert res_invalid_sig.is_valid is False
    assert res_invalid_sig.error == "INVALID_SIGNATURE"
    mock_kms_client.verify.return_value = {"SignatureValid": True}

    # verify_anti_replay raise_on_error=True
    repo = HITLApprovalRepository(async_db_session)
    existing_approval = HITLApproval(
        id=uuid.uuid4(),
        action_type="SPOT_BUY",
        amount_usd=Decimal("10000.00"),
        spend_tier="CATEGORY_MGR",
        token_hash=token.token_hash,
        status="APPROVED",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    await repo.create(existing_approval)

    with pytest.raises(TokenReplayServiceError):
        await hitl_service.verify_anti_replay(token, repo, raise_on_error=True)


def test_hitl_service_helpers_and_authority_edge_cases(
    hitl_service: HITLService,
) -> None:
    """Verify spend tier TTL routing, get_spend_tier, and eligible signer authority helpers."""
    assert hitl_service.get_spend_tier(Decimal("10000.00")) == SpendTier.CATEGORY_MGR
    assert hitl_service.get_spend_tier(Decimal("50000.00")) == SpendTier.PROC_DIRECTOR
    assert hitl_service.get_spend_tier(Decimal("150000.00")) == SpendTier.DUAL_VP

    assert hitl_service.get_token_ttl(SpendTier.DUAL_VP) == timedelta(minutes=30)
    assert hitl_service.get_token_ttl(SpendTier.PROC_DIRECTOR) == timedelta(hours=1)
    assert hitl_service.get_token_ttl(SpendTier.CATEGORY_MGR) == timedelta(hours=1)

    cat_mgr = DEMO_PERSONAS["category_manager"]
    proc_dir = DEMO_PERSONAS["procurement_director"]
    analyst = DEMO_PERSONAS["analyst"]

    assert hitl_service.is_eligible_signer(cat_mgr, Decimal("10000.00")) is True
    assert hitl_service.is_eligible_signer(proc_dir, Decimal("150000.00")) is True
    assert hitl_service.is_eligible_signer(analyst, Decimal("10000.00")) is False

    # Issue token with user having role object
    token = hitl_service.issue_token(
        action_id="ACT-ROLE-001",
        alert_id="ALT-ROLE-001",
        action_type="SPOT_BUY",
        amount_usd=Decimal("10000.00"),
        user=cat_mgr,
    )
    assert token.payload.spend_tier == "CATEGORY_MGR"


# ------------------------------------------------------------------------------
# 6. Singleton & Thread-Safety Tests
# ------------------------------------------------------------------------------


def test_get_hitl_service_singleton() -> None:
    """Verify get_hitl_service returns a thread-safe singleton instance."""
    s1 = get_hitl_service()
    s2 = get_hitl_service()
    assert s1 is s2
    assert isinstance(s1, HITLService)


def test_get_hitl_service_thread_safe_initialization() -> None:
    """Verify concurrent instantiation creates exactly one singleton instance."""
    import src.services.hitl_service as mod

    with mod._hitl_service_lock:
        mod._hitl_service_instance = None

    instances: list[HITLService] = []

    def _worker() -> None:
        inst = get_hitl_service()
        instances.append(inst)

    threads = [threading.Thread(target=_worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(instances) == 10
    assert all(inst is instances[0] for inst in instances)


def test_get_hitl_service_race_lock_coverage() -> None:
    """Simulate race conditions inside the double-checked lock to achieve 100% branch coverage."""
    import src.services.hitl_service as mod

    created_inst = HITLService()

    class RaceLock:
        def __enter__(self) -> "RaceLock":
            mod._hitl_service_instance = created_inst
            return self

        def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            pass

    with mod._hitl_service_lock:
        mod._hitl_service_instance = None

    with patch.object(mod, "_hitl_service_lock", RaceLock()):
        inst = get_hitl_service()
        assert inst is created_inst
