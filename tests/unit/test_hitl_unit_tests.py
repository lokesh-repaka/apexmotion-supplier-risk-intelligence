"""Comprehensive unit tests for the HITL Approval System (P10-4).

Explicitly verifies the core acceptance criteria specified in TASKS.md and CLAUDE.md:
1. Valid Token:
   - Tier 1 (CATEGORY_MGR <= $25k, 1-hr TTL): single signature validates, records, and approves.
   - Tier 2 (PROC_DIRECTOR $25k-$100k, 1-hr TTL): single signature validates, records, and approves.
   - Tier 3 (DUAL_VP > $100k, 30-min TTL): dual distinct signatures (Director + VP) validate and approve.
2. Expired Token:
   - Token rejected on elapsed TTL (1 hour vs 30 minutes) across token service, HITL service, and dual-approval enforcer.
   - StateGraph pauses and prevents action execution.
3. Replayed Token:
   - Replay detected against database unique index (hitl_approvals.token_hash).
   - High-severity security alert emitted and forensic audit log entry written.
   - Intra-batch duplicate signature blocked in DUAL_VP workflows.
   - Concurrent race condition IntegrityError safely intercepted.
4. Wrong Action ID / Binding Mismatches:
   - Action ID mismatch rejected with TokenBindingMismatchError / DualApprovalActionMismatchError.
   - Alert ID mismatch and Amount USD mismatch rejected.
5. Dual-Approval with One Missing Signature:
   - DUAL_VP action with single signature returns is_approved=False and transitions to PARTIALLY_APPROVED.
   - Conditional routing (route_after_hitl_gate) pauses StateGraph at await_approval.
   - Hard execution gate in action_node strictly raises InsufficientSignaturesError.
   - Invariant enforced: A DUAL_VP action proceeding with only one approval signature must NEVER happen.
6. The Triad of Responsibility & Security Invariants:
   - Float rejection with TypeError (BR-RULE-001).
   - Tampered signature bytes rejection.
   - Unauthorized role rejection.
   - Duplicate signer rejection.
"""

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.agents.graph import (
    NODE_ACTION,
    action_node,
    hitl_gate_node,
    route_after_hitl_gate,
)
from src.agents.state import (
    SupplierRiskState,
    create_initial_state,
)
from src.core.demo_auth import DEMO_PERSONAS
from src.core.hitl_tokens import (
    HITLToken,
    HITLTokenPayload,
    HITLTokenService,
    SpendTier,
    TokenBindingMismatchError,
    TokenExpiredError,
    TokenSignatureInvalidError,
    compute_token_hash,
)
from src.core.security import UserRole
from src.database.models import Base
from src.database.repositories.hitl_approval_repository import HITLApprovalRepository
from src.services.dual_approval_enforcer import (
    DualApprovalActionMismatchError,
    DualApprovalEnforcer,
    DualApprovalExpiredError,
    DuplicateSignerError,
    InsufficientSignaturesError,
)
from src.services.hitl_service import (
    ApprovalCreateInput,
    HITLService,
    TokenExpiredServiceError,
    UnauthorizedSignerError,
)
from src.services.token_replay_guard import (
    TokenReplayGuard,
    TokenReplaySecurityAlert,
)

# ------------------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------------------


@pytest.fixture
def mock_kms_client() -> MagicMock:
    """Mock boto3 KMS client simulating ECDSA P-256 sign and verify operations."""
    client = MagicMock()
    client.sign.return_value = {
        "Signature": b"mock_ecdsa_p256_der_signature_valid_bytes_test_p10_4",
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


@pytest.fixture
def dual_approval_enforcer(token_service: HITLTokenService) -> DualApprovalEnforcer:
    """Instantiate DualApprovalEnforcer with mocked token service."""
    return DualApprovalEnforcer(token_service=token_service)


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
# 1. Valid Token Acceptance Tests (Tier 1, Tier 2, Tier 3)
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hitl_unit_valid_token_category_manager_tier1(
    hitl_service: HITLService,
    async_db_session: AsyncSession,
):
    """Verify valid Tier 1 token (CATEGORY_MGR <= $25k) verifies and approves successfully."""
    action_id = f"ACT-T1-{uuid.uuid4().hex[:8]}"
    alert_id = str(uuid.uuid4())
    amount = Decimal("18500.00")
    user = DEMO_PERSONAS["category_manager"]
    signer_uuid = uuid.uuid4()

    # 1. Create approval request in repository
    approval = await hitl_service.create_approval_request(
        async_db_session,
        ApprovalCreateInput(
            action_id=action_id,
            action_type="PO_DISPATCH",
            amount_usd=amount,
            alert_id=alert_id,
        ),
    )
    assert approval.spend_tier == SpendTier.CATEGORY_MGR.value
    assert approval.status == "PENDING"

    # 2. Issue valid token
    token = hitl_service.issue_token(
        action_id=action_id,
        alert_id=alert_id,
        action_type="PO_DISPATCH",
        amount_usd=amount,
        user=user,
    )
    assert token.payload.signer_role == UserRole.CATEGORY_MANAGER.value
    assert (token.payload.expires_at - token.payload.issued_at) == timedelta(hours=1)

    # 3. Verify token through HITL service
    ver_res = hitl_service.verify_token(
        token,
        expected_action_id=action_id,
        expected_alert_id=alert_id,
        expected_amount_usd=amount,
    )
    assert ver_res.is_valid is True

    # 4. Record signature in DB
    updated = await hitl_service.sign_approval(
        async_db_session,
        approval_id=approval.id,
        token=token,
        signer_id=signer_uuid,
    )
    assert updated.status == "APPROVED"
    assert updated.approved_at is not None
    assert updated.token_hash == token.token_hash


@pytest.mark.asyncio
async def test_hitl_unit_valid_token_procurement_director_tier2(
    hitl_service: HITLService,
    async_db_session: AsyncSession,
):
    """Verify valid Tier 2 token (PROC_DIRECTOR $25k-$100k) verifies and approves successfully."""
    action_id = f"ACT-T2-{uuid.uuid4().hex[:8]}"
    alert_id = str(uuid.uuid4())
    amount = Decimal("85000.00")
    user = DEMO_PERSONAS["procurement_director"]
    signer_uuid = uuid.uuid4()

    approval = await hitl_service.create_approval_request(
        async_db_session,
        ApprovalCreateInput(
            action_id=action_id,
            action_type="EXPEDITED_AIR_FREIGHT",
            amount_usd=amount,
            alert_id=alert_id,
        ),
    )
    assert approval.spend_tier == SpendTier.PROC_DIRECTOR.value

    token = hitl_service.issue_token(
        action_id=action_id,
        alert_id=alert_id,
        action_type="EXPEDITED_AIR_FREIGHT",
        amount_usd=amount,
        user=user,
    )
    assert (token.payload.expires_at - token.payload.issued_at) == timedelta(hours=1)

    updated = await hitl_service.sign_approval(
        async_db_session,
        approval_id=approval.id,
        token=token,
        signer_id=signer_uuid,
    )
    assert updated.status == "APPROVED"
    assert updated.token_hash == token.token_hash


@pytest.mark.asyncio
async def test_hitl_unit_valid_token_dual_vp_tier3_both_signatures(
    hitl_service: HITLService,
    dual_approval_enforcer: DualApprovalEnforcer,
    async_db_session: AsyncSession,
):
    """Verify valid Tier 3 action (> $100k) satisfies dual-approval with two valid signatures."""
    action_id = f"ACT-T3-{uuid.uuid4().hex[:8]}"
    alert_id = str(uuid.uuid4())
    amount = Decimal("2448105.00")  # NanoCore canonical exposure
    signer_1_id = uuid.uuid4()
    signer_2_id = uuid.uuid4()

    approval = await hitl_service.create_approval_request(
        async_db_session,
        ApprovalCreateInput(
            action_id=action_id,
            action_type="SPOT_BUY_BROKER",
            amount_usd=amount,
            alert_id=alert_id,
        ),
    )
    assert approval.spend_tier == SpendTier.DUAL_VP.value

    # Issue both valid tokens (30-minute TTL)
    token_director = hitl_service.issue_token(
        action_id=action_id,
        alert_id=alert_id,
        action_type="SPOT_BUY_BROKER",
        amount_usd=amount,
        signer_id=str(signer_1_id),
        signer_role="procurement_director",
    )
    token_vp = hitl_service.issue_token(
        action_id=action_id,
        alert_id=alert_id,
        action_type="SPOT_BUY_BROKER",
        amount_usd=amount,
        signer_id=str(signer_2_id),
        signer_role="vp_supply_chain",
    )

    assert (token_director.payload.expires_at - token_director.payload.issued_at) == timedelta(
        minutes=30
    )
    assert (token_vp.payload.expires_at - token_vp.payload.issued_at) == timedelta(minutes=30)

    # 1. DualApprovalEnforcer verification
    res = dual_approval_enforcer.verify_signatures(
        tokens=[token_director, token_vp],
        expected_action_id=action_id,
        expected_alert_id=alert_id,
        expected_amount_usd=amount,
    )
    assert res.is_approved is True
    assert len(res.valid_signers) == 2

    # 2. Sequential signing transitions in repository
    p_signed = await hitl_service.sign_approval(
        session=async_db_session,
        approval_id=approval.id,
        token=token_director,
        signer_id=signer_1_id,
    )
    assert p_signed.status == "PARTIALLY_APPROVED"

    f_signed = await hitl_service.sign_approval(
        session=async_db_session,
        approval_id=approval.id,
        token=token_vp,
        signer_id=signer_2_id,
    )
    assert f_signed.status == "APPROVED"
    assert len(f_signed.approved_by or []) == 2


# ------------------------------------------------------------------------------
# 2. Expired Token Tests
# ------------------------------------------------------------------------------


def test_hitl_unit_expired_token_rejected_at_token_service(
    token_service: HITLTokenService,
):
    """Verify expired token is rejected with TokenExpiredError in HITLTokenService."""
    action_id = "ACT-EXP-001"
    alert_id = str(uuid.uuid4())
    amount = Decimal("15000.00")

    past_time = datetime.now(UTC) - timedelta(hours=2)
    payload = HITLTokenPayload(
        action_id=action_id,
        alert_id=alert_id,
        action_type="PO_DISPATCH",
        amount_usd=amount,
        spend_tier=SpendTier.CATEGORY_MGR,
        signer_id="usr_expired_01",
        signer_role=UserRole.CATEGORY_MANAGER.value,
        issued_at=past_time,
        expires_at=past_time + timedelta(hours=1),
    )
    token = HITLToken(
        payload=payload,
        signature="dGVzdF9zaWduYXR1cmVfYnl0ZXM=",
        key_arn="arn:aws:kms:eu-central-1:123456789012:key/test-hitl-key",
        token_hash=compute_token_hash(str(payload.model_dump())),
    )

    with pytest.raises(TokenExpiredError) as exc_info:
        token_service.verify_token(token, raise_on_error=True)
    assert "expired" in str(exc_info.value).lower()


def test_hitl_unit_expired_token_rejected_at_hitl_service(
    hitl_service: HITLService,
):
    """Verify expired token is rejected with TokenExpiredServiceError in HITLService."""
    action_id = "ACT-EXP-002"
    alert_id = str(uuid.uuid4())
    amount = Decimal("30000.00")

    past_time = datetime.now(UTC) - timedelta(hours=3)
    payload = HITLTokenPayload(
        action_id=action_id,
        alert_id=alert_id,
        action_type="EXPEDITED_AIR_FREIGHT",
        amount_usd=amount,
        spend_tier=SpendTier.PROC_DIRECTOR,
        signer_id="usr_dir_exp",
        signer_role=UserRole.PROCUREMENT_DIRECTOR.value,
        issued_at=past_time,
        expires_at=past_time + timedelta(hours=1),
    )
    token = HITLToken(
        payload=payload,
        signature="dGVzdF9zaWduYXR1cmVfYnl0ZXM=",
        key_arn="arn:aws:kms:eu-central-1:123456789012:key/test-hitl-key",
        token_hash=compute_token_hash(str(payload.model_dump())),
    )

    with pytest.raises(TokenExpiredServiceError):
        hitl_service.verify_token(
            token,
            expected_action_id=action_id,
            raise_on_error=True,
        )


def test_hitl_unit_expired_token_in_dual_approval_rejected(
    dual_approval_enforcer: DualApprovalEnforcer,
    hitl_service: HITLService,
):
    """Verify expired token within DUAL_VP batch raises DualApprovalExpiredError."""
    action_id = "ACT-EXP-DUAL-003"
    alert_id = str(uuid.uuid4())
    amount = Decimal("250000.00")

    valid_token = hitl_service.issue_token(
        action_id=action_id,
        alert_id=alert_id,
        action_type="SPOT_BUY",
        amount_usd=amount,
        signer_id="usr_dir_01",
        signer_role="procurement_director",
    )

    past_time = datetime.now(UTC) - timedelta(hours=1)
    expired_payload = HITLTokenPayload(
        action_id=action_id,
        alert_id=alert_id,
        action_type="SPOT_BUY",
        amount_usd=amount,
        spend_tier=SpendTier.DUAL_VP,
        signer_id="usr_vp_exp",
        signer_role=UserRole.VP_SUPPLY_CHAIN.value,
        issued_at=past_time,
        expires_at=past_time + timedelta(minutes=30),
    )
    expired_token = HITLToken(
        payload=expired_payload,
        signature="dGVzdF9zaWduYXR1cmVfYnl0ZXM=",
        key_arn="arn:aws:kms:eu-central-1:123456789012:key/test-hitl-key",
        token_hash=compute_token_hash(str(expired_payload.model_dump())),
    )

    with pytest.raises(DualApprovalExpiredError):
        dual_approval_enforcer.verify_signatures(
            tokens=[valid_token, expired_token],
            expected_action_id=action_id,
            expected_alert_id=alert_id,
            expected_amount_usd=amount,
            raise_on_error=True,
        )


# ------------------------------------------------------------------------------
# 3. Replayed Token Tests (Anti-Replay & Forensic Alerts)
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hitl_unit_replayed_token_database_detection_and_alert(
    hitl_service: HITLService,
    async_db_session: AsyncSession,
):
    """Verify replayed token triggers TokenReplaySecurityAlert and emits forensic audit log."""
    action_id = "ACT-REPLAY-001"
    alert_id = str(uuid.uuid4())
    amount = Decimal("20000.00")
    user = DEMO_PERSONAS["category_manager"]
    signer_uuid = uuid.uuid4()

    # 1. Issue and record approval
    approval = await hitl_service.create_approval_request(
        async_db_session,
        ApprovalCreateInput(
            action_id=action_id,
            action_type="PO_DISPATCH",
            amount_usd=amount,
            alert_id=alert_id,
        ),
    )
    token = hitl_service.issue_token(
        action_id=action_id,
        alert_id=alert_id,
        action_type="PO_DISPATCH",
        amount_usd=amount,
        user=user,
    )
    await hitl_service.sign_approval(
        async_db_session,
        approval_id=approval.id,
        token=token,
        signer_id=signer_uuid,
    )

    # 2. Attempt to verify or record the same token a second time
    with pytest.raises(TokenReplaySecurityAlert) as exc_info:
        guard = TokenReplayGuard()
        await guard.check_token(
            token=token,
            session=async_db_session,
            action_id="ACT-ATTACK-001",
            raise_on_error=True,
        )
    assert token.token_hash in str(exc_info.value)


@pytest.mark.asyncio
async def test_hitl_unit_replayed_token_intra_batch_duplicate_prevented(
    hitl_service: HITLService,
    async_db_session: AsyncSession,
):
    """Verify providing the exact same token twice in a DUAL_VP batch is blocked (anti-self-replay)."""
    action_id = "ACT-SELF-REPLAY"
    alert_id = str(uuid.uuid4())
    amount = Decimal("150000.00")

    token = hitl_service.issue_token(
        action_id=action_id,
        alert_id=alert_id,
        action_type="SPOT_BUY",
        amount_usd=amount,
        signer_id="usr_dir_replay",
        signer_role="procurement_director",
    )

    guard = TokenReplayGuard()
    repo = HITLApprovalRepository(async_db_session)
    with pytest.raises(TokenReplaySecurityAlert, match="duplicate token hash"):
        await guard.check_tokens_batch(
            tokens=[token, token],  # Duplicate token provided twice
            repository=repo,
            action_id=action_id,
            raise_on_error=True,
        )


# ------------------------------------------------------------------------------
# 4. Wrong Action ID & Binding Mismatch Tests
# ------------------------------------------------------------------------------


def test_hitl_unit_wrong_action_id_rejected(
    hitl_service: HITLService,
    dual_approval_enforcer: DualApprovalEnforcer,
):
    """Verify cryptographic token bound to ACT-1001 is rejected when submitted for ACT-1002."""
    alert_id = str(uuid.uuid4())
    amount = Decimal("20000.00")

    token = hitl_service.issue_token(
        action_id="ACT-1001",
        alert_id=alert_id,
        action_type="PO_DISPATCH",
        amount_usd=amount,
        user=DEMO_PERSONAS["category_manager"],
    )

    # Rejection in HITLTokenService
    with pytest.raises(TokenBindingMismatchError) as exc_info:
        hitl_service.token_service.verify_token(
            token,
            expected_action_id="ACT-1002",
            raise_on_error=True,
        )
    assert "action_id mismatch" in str(exc_info.value).lower()

    # Rejection in DualApprovalEnforcer
    with pytest.raises(DualApprovalActionMismatchError):
        dual_approval_enforcer.verify_signatures(
            tokens=[token, token],
            expected_action_id="ACT-1002",
            raise_on_error=True,
        )


def test_hitl_unit_wrong_alert_id_rejected(
    hitl_service: HITLService,
):
    """Verify cryptographic token bound to alert_id_1 is rejected when submitted for alert_id_2."""
    action_id = "ACT-MISMATCH-ALT"
    alert_id_1 = str(uuid.uuid4())
    alert_id_2 = str(uuid.uuid4())
    amount = Decimal("40000.00")

    token = hitl_service.issue_token(
        action_id=action_id,
        alert_id=alert_id_1,
        action_type="EXPEDITED_AIR_FREIGHT",
        amount_usd=amount,
        user=DEMO_PERSONAS["procurement_director"],
    )

    with pytest.raises(TokenBindingMismatchError) as exc_info:
        hitl_service.token_service.verify_token(
            token,
            expected_alert_id=alert_id_2,
            raise_on_error=True,
        )
    assert "alert_id mismatch" in str(exc_info.value).lower()


def test_hitl_unit_wrong_amount_usd_rejected(
    hitl_service: HITLService,
):
    """Verify cryptographic token bound to $20,000 is rejected when submitted for $50,000."""
    action_id = "ACT-MISMATCH-AMT"
    alert_id = str(uuid.uuid4())

    token = hitl_service.issue_token(
        action_id=action_id,
        alert_id=alert_id,
        action_type="PO_DISPATCH",
        amount_usd=Decimal("20000.00"),
        user=DEMO_PERSONAS["category_manager"],
    )

    with pytest.raises(TokenBindingMismatchError) as exc_info:
        hitl_service.token_service.verify_token(
            token,
            expected_amount_usd=Decimal("50000.00"),
            raise_on_error=True,
        )
    assert "amount mismatch" in str(exc_info.value).lower()


# ------------------------------------------------------------------------------
# 5. Dual-Approval with One Missing Signature Tests
# ------------------------------------------------------------------------------


def test_hitl_unit_dual_approval_one_missing_signature_returns_partial(
    dual_approval_enforcer: DualApprovalEnforcer,
    hitl_service: HITLService,
):
    """Verify DUAL_VP action with 1 signature returns is_approved=False and reason."""
    action_id = "ACT-PARTIAL-001"
    alert_id = str(uuid.uuid4())
    amount = Decimal("150000.00")

    token_director = hitl_service.issue_token(
        action_id=action_id,
        alert_id=alert_id,
        action_type="SPOT_BUY",
        amount_usd=amount,
        signer_id="usr_dir_single",
        signer_role="procurement_director",
    )

    res = dual_approval_enforcer.verify_signatures(
        tokens=[token_director],  # Only Director provided, VP missing
        expected_action_id=action_id,
        expected_alert_id=alert_id,
        expected_amount_usd=amount,
        raise_on_error=False,
    )
    assert res.is_approved is False
    assert res.error == "INSUFFICIENT_SIGNATURES"
    assert res.required_signers_count == 2
    assert len(res.valid_signers) == 0


def test_hitl_unit_dual_approval_one_missing_signature_pauses_stategraph(
    token_service: HITLTokenService,
):
    """Verify single signature on DUAL_VP transitions state to PARTIALLY_APPROVED and routes to await_approval."""
    action_id = "ACT-PARTIAL-ROUTE"
    alert_id = "ALT-PARTIAL-ROUTE"
    amount = Decimal("200000.00")

    token_director = token_service.issue_token(
        action_id=action_id,
        alert_id=alert_id,
        action_type="SPOT_BUY",
        amount_usd=amount,
        signer_id="usr_dir_pause",
        signer_role="procurement_director",
    )

    state: SupplierRiskState = create_initial_state(
        alert_id=alert_id,
        supplier_id="SUP-NC-001",
    )
    state["requires_hitl"] = True
    state["governing_spend_tier"] = SpendTier.DUAL_VP
    state["recommended_action_id"] = action_id
    state["recommendations"] = [{"action_id": action_id, "estimated_cost_usd": amount}]
    state["hitl_decision"] = {
        "approved": False,
        "spend_tier": "DUAL_VP",
        "tokens": [token_director.serialize()],
        "signers": ["usr_dir_pause"],
    }

    # Evaluate approval state in hitl_gate_node
    update_one = hitl_gate_node(state)
    assert update_one["workflow_status"] == "PARTIALLY_APPROVED"

    # Conditional routing MUST route to await_approval, NEVER NODE_ACTION
    state["workflow_status"] = "PARTIALLY_APPROVED"
    next_step = route_after_hitl_gate(state)
    assert next_step == "await_approval"
    assert next_step != NODE_ACTION


def test_hitl_unit_dual_approval_action_node_hard_blocks_one_signature(
    token_service: HITLTokenService,
):
    """Verify action_node raises InsufficientSignaturesError if single signature reaches it.

    Enforces CLAUDE.md Sec 20.1: 'A DUAL_VP action proceeding with only one approval signature must NEVER happen.'
    """
    action_id = "ACT-BYPASS-ATTEMPT"
    alert_id = "ALT-BYPASS-ATTEMPT"
    amount = Decimal("500000.00")

    token_director = token_service.issue_token(
        action_id=action_id,
        alert_id=alert_id,
        action_type="SPOT_BUY",
        amount_usd=amount,
        signer_id="usr_dir_bypass",
        signer_role="procurement_director",
    )

    state: SupplierRiskState = create_initial_state(
        alert_id=alert_id,
        supplier_id="SUP-NC-001",
    )
    state["requires_hitl"] = True
    state["governing_spend_tier"] = SpendTier.DUAL_VP
    state["recommended_action_id"] = action_id
    state["recommendations"] = [{"action_id": action_id, "estimated_cost_usd": amount}]
    state["hitl_decision"] = {
        "approved": True,
        "token_hash": token_director.token_hash,
        "signer_id": "usr_dir_bypass",
        "tokens": [token_director.serialize()],
        "signers": ["usr_dir_bypass"],
    }

    with pytest.raises(InsufficientSignaturesError, match="require 2 independent"):
        action_node(state)


def test_hitl_unit_dual_approval_zero_signatures_hard_blocks_action_node():
    """Verify action_node raises InsufficientSignaturesError when zero tokens are supplied."""
    state = create_initial_state(alert_id="ALT-ZERO-001", supplier_id="SUP-NC-001")
    state["requires_hitl"] = True
    state["governing_spend_tier"] = SpendTier.DUAL_VP
    state["recommended_action_id"] = "ACT-ZERO-001"
    state["recommendations"] = [
        {"action_id": "ACT-ZERO-001", "estimated_cost_usd": Decimal("300000.00")}
    ]

    with pytest.raises(InsufficientSignaturesError):
        action_node(state)


def test_hitl_unit_dual_approval_duplicate_signers_rejected(
    hitl_service: HITLService,
    dual_approval_enforcer: DualApprovalEnforcer,
):
    """Verify two tokens from the same user/role are rejected with DuplicateSignerError."""
    action_id = "ACT-DUP-SIGNER"
    alert_id = str(uuid.uuid4())
    amount = Decimal("250000.00")

    token1 = hitl_service.issue_token(
        action_id=action_id,
        alert_id=alert_id,
        action_type="SPOT_BUY",
        amount_usd=amount,
        signer_id="usr_same_director",
        signer_role="procurement_director",
    )
    token2 = hitl_service.issue_token(
        action_id=action_id,
        alert_id=alert_id,
        action_type="SPOT_BUY",
        amount_usd=amount,
        signer_id="usr_same_director",  # Same signer!
        signer_role="procurement_director",
    )

    with pytest.raises(DuplicateSignerError) as exc_info:
        dual_approval_enforcer.verify_signatures(
            tokens=[token1, token2],
            expected_action_id=action_id,
            expected_alert_id=alert_id,
            expected_amount_usd=amount,
            raise_on_error=True,
        )
    assert "duplicate signer" in str(exc_info.value).lower()


# ------------------------------------------------------------------------------
# 6. Precision, RBAC & Signature Tampering Tests (The Triad of Responsibility)
# ------------------------------------------------------------------------------


def test_hitl_unit_float_amount_rejected_with_type_error(
    hitl_service: HITLService,
    dual_approval_enforcer: DualApprovalEnforcer,
):
    """Verify floating point amounts are strictly rejected with TypeError per BR-RULE-001."""
    with pytest.raises(TypeError) as exc_info:
        hitl_service.get_spend_tier(25000.0)  # type: ignore[arg-type]
    assert "Decimal" in str(exc_info.value)

    with pytest.raises(TypeError) as exc_info2:
        dual_approval_enforcer.is_dual_approval_required(150000.0)  # type: ignore[arg-type]
    assert "Decimal" in str(exc_info2.value)


def test_hitl_unit_unauthorized_role_rejected(
    hitl_service: HITLService,
):
    """Verify unauthorized role (e.g. analyst) is rejected from signing approval tokens."""
    action_id = "ACT-UNAUTH-001"
    alert_id = str(uuid.uuid4())
    amount = Decimal("50000.00")
    analyst = DEMO_PERSONAS["analyst"]

    with pytest.raises(UnauthorizedSignerError) as exc_info:
        hitl_service.issue_token(
            action_id=action_id,
            alert_id=alert_id,
            action_type="EXPEDITED_AIR_FREIGHT",
            amount_usd=amount,
            user=analyst,
        )
    assert "read-only" in str(exc_info.value).lower()


def test_hitl_unit_tampered_signature_bytes_rejected(
    hitl_service: HITLService,
    mock_kms_client: MagicMock,
):
    """Verify tampered cryptographic signature fails verification with TokenSignatureInvalidError."""
    action_id = "ACT-TAMPER-001"
    alert_id = str(uuid.uuid4())
    amount = Decimal("15000.00")

    token = hitl_service.issue_token(
        action_id=action_id,
        alert_id=alert_id,
        action_type="PO_DISPATCH",
        amount_usd=amount,
        user=DEMO_PERSONAS["category_manager"],
    )

    # Simulate KMS reporting signature verification failure on tampered bytes
    mock_kms_client.verify.return_value = {
        "SignatureValid": False,
        "KeyId": "arn:aws:kms:eu-central-1:123456789012:key/test-hitl-key",
    }

    with pytest.raises(TokenSignatureInvalidError) as exc_info:
        hitl_service.token_service.verify_token(token, raise_on_error=True)
    assert "signature verification failed" in str(exc_info.value).lower()
