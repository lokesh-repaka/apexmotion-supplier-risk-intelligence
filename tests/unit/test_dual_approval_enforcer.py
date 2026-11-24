"""Unit tests for Dual-Approval Enforcer (P10-2).

Verifies:
- Dual-Approval requirement detection based on monetary thresholds (> $100,000) and spend tier (DUAL_VP).
- Enforcement of The Triad of Responsibility (BR-RULE-001): Pure Python Decimal arithmetic, rejecting floats.
- Multi-token signature validation: exactly 2 distinct executive signatures required (Procurement Director + VP Supply Chain).
- Detection and prevention of single-signature execution bypasses on DUAL_VP actions (CLAUDE.md Sec 20.1).
- Detection and prevention of identical signers, expired tokens (30-min TTL), action mismatches, and replay attempts.
- LangGraph hitl_gate_node state transitions: PENDING -> PARTIALLY_APPROVED (1 signature) -> APPROVED (2 signatures).
- LangGraph route_after_hitl_gate conditional edge routing:
  * 0 or 1 signature -> routes to "await_approval" (never NODE_ACTION).
  * 2 valid signatures -> routes to NODE_ACTION.
- LangGraph action_node hard pre-execution gate: raising InsufficientSignaturesError if single signature reaches action node.
- End-to-end compiled StateGraph execution with NanoCore $2,448,105 disruption pausing until dual signatures are presented.
- Thread-safe singleton accessor and double-checked locking.
- Offline-first execution: zero live network or AWS KMS calls.
"""

import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest
import src.services.dual_approval_enforcer as enforcer_mod
from langgraph.checkpoint.memory import MemorySaver
from src.agents.graph import (
    NODE_ACTION,
    action_node,
    hitl_gate_node,
    route_after_hitl_gate,
)
from src.agents.orchestrator import InvestigationOrchestrator
from src.agents.state import (
    SupplierRiskState,
    WorkflowStatus,
    create_initial_state,
)
from src.core.hitl_tokens import (
    HITLToken,
    HITLTokenPayload,
    HITLTokenService,
    SpendTier,
)
from src.services.dual_approval_enforcer import (
    DualApprovalActionMismatchError,
    DualApprovalEnforcer,
    DualApprovalError,
    DualApprovalExpiredError,
    DualApprovalVerificationResult,
    DuplicateSignerError,
    InsufficientSignaturesError,
    UnauthorizedSignerRoleError,
    get_dual_approval_enforcer,
)


@pytest.fixture
def mock_kms_client() -> MagicMock:
    """Mock KMS client returning valid ECDSA P-256 signatures."""
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
def enforcer(token_service: HITLTokenService) -> DualApprovalEnforcer:
    """Instantiate DualApprovalEnforcer with mocked token service."""
    return DualApprovalEnforcer(token_service=token_service)


@pytest.fixture(autouse=True)
def auto_mock_kms(mock_kms_client: MagicMock, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Ensure all boto3 KMS clients in tests use the mock client and reset singleton."""
    monkeypatch.setattr("boto3.client", lambda *_args, **_kwargs: mock_kms_client)
    with enforcer_mod._enforcer_lock:
        enforcer_mod._global_enforcer = None
    yield
    with enforcer_mod._enforcer_lock:
        enforcer_mod._global_enforcer = None


# ------------------------------------------------------------------------------
# 1. Dual-Approval Threshold & Requirement Tests
# ------------------------------------------------------------------------------


def test_is_dual_approval_required_thresholds(enforcer: DualApprovalEnforcer) -> None:
    """Verify dual approval is required strictly when spend > $100,000 or tier is DUAL_VP."""
    # Under $100,000 -> False
    assert enforcer.is_dual_approval_required(amount_usd=Decimal("25000.00")) is False
    assert enforcer.is_dual_approval_required(amount_usd=Decimal("100000.00")) is False
    assert enforcer.is_dual_approval_required(spend_tier=SpendTier.CATEGORY_MGR) is False
    assert enforcer.is_dual_approval_required(spend_tier=SpendTier.PROC_DIRECTOR) is False

    # Over $100,000 -> True
    assert enforcer.is_dual_approval_required(amount_usd=Decimal("100000.01")) is True
    assert enforcer.is_dual_approval_required(amount_usd=Decimal("150000.00")) is True
    assert enforcer.is_dual_approval_required(amount_usd=Decimal("2448105.00")) is True  # NanoCore
    assert enforcer.is_dual_approval_required(spend_tier=SpendTier.DUAL_VP) is True
    assert enforcer.is_dual_approval_required(spend_tier="DUAL_VP") is True


def test_is_dual_approval_required_float_rejection(enforcer: DualApprovalEnforcer) -> None:
    """Verify float inputs raise TypeError per BR-RULE-001 monetary precision."""
    with pytest.raises(TypeError, match="Float values are strictly forbidden"):
        enforcer.is_dual_approval_required(amount_usd=100000.50)  # type: ignore[arg-type]


# ------------------------------------------------------------------------------
# 2. Signature Verification & Validation Logic Tests
# ------------------------------------------------------------------------------


def test_verify_dual_approval_success(
    enforcer: DualApprovalEnforcer,
    token_service: HITLTokenService,
) -> None:
    """Verify two valid tokens from distinct executives successfully validate."""
    action_id = "ACT-EXPEDITE-2026-001"
    alert_id = "ALT-NC-001"
    amount = Decimal("2448105.00")

    token_director = token_service.issue_token(
        action_id=action_id,
        alert_id=alert_id,
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=amount,
        signer_id="usr-elena-rostova",
        signer_role="procurement_director",
    )

    token_vp = token_service.issue_token(
        action_id=action_id,
        alert_id=alert_id,
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=amount,
        signer_id="usr-marcus-vance",
        signer_role="vp_supply_chain",
    )

    res = enforcer.verify_signatures(
        tokens=[token_director, token_vp],
        expected_action_id=action_id,
        expected_alert_id=alert_id,
        expected_amount_usd=amount,
    )

    assert isinstance(res, DualApprovalVerificationResult)
    assert res.is_approved is True
    assert res.spend_tier == SpendTier.DUAL_VP
    assert res.required_signers_count == 2
    assert len(res.valid_signers) == 2
    assert "usr-elena-rostova" in res.valid_signers
    assert "usr-marcus-vance" in res.valid_signers
    assert len(res.token_hashes) == 2
    assert res.error is None


def test_verify_dual_approval_insufficient_signatures(
    enforcer: DualApprovalEnforcer,
    token_service: HITLTokenService,
) -> None:
    """Verify fewer than 2 tokens raises InsufficientSignaturesError."""
    action_id = "ACT-EXPEDITE-2026-001"
    alert_id = "ALT-NC-001"
    amount = Decimal("2448105.00")

    token_director = token_service.issue_token(
        action_id=action_id,
        alert_id=alert_id,
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=amount,
        signer_id="usr-elena-rostova",
        signer_role="procurement_director",
    )

    # 1. Non-raising verification
    res_one = enforcer.verify_signatures(
        tokens=[token_director],
        expected_action_id=action_id,
        expected_alert_id=alert_id,
        expected_amount_usd=amount,
        raise_on_error=False,
    )
    assert res_one.is_approved is False
    assert res_one.error == "INSUFFICIENT_SIGNATURES"

    res_zero = enforcer.verify_signatures(
        tokens=[],
        expected_action_id=action_id,
        expected_alert_id=alert_id,
        expected_amount_usd=amount,
        raise_on_error=False,
    )
    assert res_zero.is_approved is False
    assert res_zero.error == "INSUFFICIENT_SIGNATURES"

    # 2. Raising verification
    with pytest.raises(InsufficientSignaturesError, match="require 2 independent"):
        enforcer.verify_signatures(
            tokens=[token_director],
            expected_action_id=action_id,
            expected_alert_id=alert_id,
            expected_amount_usd=amount,
            raise_on_error=True,
        )


def test_verify_dual_approval_identical_signers_rejection(
    enforcer: DualApprovalEnforcer,
    token_service: HITLTokenService,
) -> None:
    """Verify identical signers are rejected with DuplicateSignerError."""
    action_id = "ACT-EXPEDITE-2026-001"
    alert_id = "ALT-NC-001"
    amount = Decimal("2448105.00")

    token1 = token_service.issue_token(
        action_id=action_id,
        alert_id=alert_id,
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=amount,
        signer_id="usr-elena-rostova",
        signer_role="procurement_director",
    )
    token2 = token_service.issue_token(
        action_id=action_id,
        alert_id=alert_id,
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=amount,
        signer_id="usr-elena-rostova",  # Duplicate signer
        signer_role="procurement_director",
    )

    res = enforcer.verify_signatures(
        tokens=[token1, token2],
        expected_action_id=action_id,
        expected_alert_id=alert_id,
        expected_amount_usd=amount,
        raise_on_error=False,
    )
    assert res.is_approved is False
    assert res.error == "IDENTICAL_SIGNERS"

    with pytest.raises(DuplicateSignerError, match="distinct"):
        enforcer.verify_signatures(
            tokens=[token1, token2],
            expected_action_id=action_id,
            expected_alert_id=alert_id,
            expected_amount_usd=amount,
            raise_on_error=True,
        )


def test_verify_dual_approval_action_mismatch(
    enforcer: DualApprovalEnforcer,
    token_service: HITLTokenService,
) -> None:
    """Verify mismatched action IDs between tokens are rejected with DualApprovalActionMismatchError."""
    token1 = token_service.issue_token(
        action_id="ACT-ACTION-001",
        alert_id="ALT-NC-001",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("150000.00"),
        signer_id="usr-director-01",
        signer_role="procurement_director",
    )
    token2 = token_service.issue_token(
        action_id="ACT-ACTION-002",  # Different action ID
        alert_id="ALT-NC-001",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("150000.00"),
        signer_id="usr-vp-02",
        signer_role="vp_supply_chain",
    )

    res = enforcer.verify_signatures(
        tokens=[token1, token2],
        expected_action_id="ACT-ACTION-001",
        raise_on_error=False,
    )
    assert res.is_approved is False
    assert res.error in ("DUAL_ACTION_MISMATCH", "ACTION_MISMATCH")

    with pytest.raises(DualApprovalActionMismatchError):
        enforcer.verify_signatures(
            tokens=[token1, token2],
            expected_action_id="ACT-ACTION-001",
            raise_on_error=True,
        )


def test_verify_dual_approval_expired_token(
    enforcer: DualApprovalEnforcer,
) -> None:
    """Verify tokens exceeding the 30-minute DUAL_VP TTL are rejected with DualApprovalExpiredError."""
    now = datetime.now(UTC)
    payload_expired = HITLTokenPayload(
        action_id="ACT-EXP-001",
        alert_id="ALT-EXP-001",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("150000.00"),
        spend_tier=SpendTier.DUAL_VP,
        signer_id="usr-director",
        signer_role="procurement_director",
        issued_at=now - timedelta(minutes=45),
        expires_at=now - timedelta(minutes=15),  # Expired
    )
    token_expired = HITLToken(
        payload=payload_expired,
        signature="mock_sig_1",
        token_hash="hash_expired_1",
        key_arn="arn:aws:kms:eu-central-1:123456789012:key/test-hitl-key",
    )

    payload_valid = HITLTokenPayload(
        action_id="ACT-EXP-001",
        alert_id="ALT-EXP-001",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("150000.00"),
        spend_tier=SpendTier.DUAL_VP,
        signer_id="usr-vp",
        signer_role="vp_supply_chain",
        issued_at=now - timedelta(minutes=10),
        expires_at=now + timedelta(minutes=20),
    )
    token_valid = HITLToken(
        payload=payload_valid,
        signature="mock_sig_2",
        token_hash="hash_valid_2",
        key_arn="arn:aws:kms:eu-central-1:123456789012:key/test-hitl-key",
    )

    res = enforcer.verify_signatures(
        tokens=[token_expired, token_valid],
        expected_action_id="ACT-EXP-001",
        raise_on_error=False,
    )
    assert res.is_approved is False
    assert res.error == "TOKEN_EXPIRED"

    with pytest.raises(DualApprovalExpiredError, match="expired"):
        enforcer.verify_signatures(
            tokens=[token_expired, token_valid],
            expected_action_id="ACT-EXP-001",
            raise_on_error=True,
        )


def test_verify_dual_approval_unauthorized_role(
    enforcer: DualApprovalEnforcer,
    token_service: HITLTokenService,
) -> None:
    """Verify signers lacking executive authority are rejected with UnauthorizedSignerRoleError."""
    token_analyst = token_service.issue_token(
        action_id="ACT-ROLE-001",
        alert_id="ALT-ROLE-001",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("150000.00"),
        signer_id="usr-analyst",
        signer_role="analyst",  # Analyst has no spend authority
    )
    token_vp = token_service.issue_token(
        action_id="ACT-ROLE-001",
        alert_id="ALT-ROLE-001",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("150000.00"),
        signer_id="usr-vp",
        signer_role="vp_supply_chain",
    )

    with pytest.raises(UnauthorizedSignerRoleError, match="ineligible"):
        enforcer.verify_signatures(
            tokens=[token_analyst, token_vp],
            expected_action_id="ACT-ROLE-001",
            enforce_roles=True,
            raise_on_error=True,
        )


# ------------------------------------------------------------------------------
# 3. LangGraph Node & Edge Routing Integration Tests
# ------------------------------------------------------------------------------


def test_hitl_gate_node_evaluates_partial_and_full_approval(
    token_service: HITLTokenService,
) -> None:
    """Verify hitl_gate_node marks PARTIALLY_APPROVED on 1 signature and APPROVED on 2."""
    action_id = "ACT-GATE-001"
    alert_id = "ALT-GATE-001"
    amount = Decimal("200000.00")

    token1 = token_service.issue_token(
        action_id=action_id,
        alert_id=alert_id,
        action_type="SECONDARY_SOURCE_SPOT_BUY",
        amount_usd=amount,
        signer_id="usr-director-01",
        signer_role="procurement_director",
    )
    token2 = token_service.issue_token(
        action_id=action_id,
        alert_id=alert_id,
        action_type="SECONDARY_SOURCE_SPOT_BUY",
        amount_usd=amount,
        signer_id="usr-vp-02",
        signer_role="vp_supply_chain",
    )

    state: SupplierRiskState = create_initial_state(
        alert_id=alert_id,
        supplier_id="SUP-NC-882",
    )
    state["requires_hitl"] = True
    state["governing_spend_tier"] = SpendTier.DUAL_VP
    state["recommended_action_id"] = action_id
    state["recommendations"] = [{"action_id": action_id, "estimated_cost_usd": amount}]

    # Case A: Zero signatures -> AWAITING_APPROVAL
    update_zero = hitl_gate_node(state)
    assert update_zero["workflow_status"] == WorkflowStatus.AWAITING_APPROVAL

    # Case B: One signature -> PARTIALLY_APPROVED
    state["hitl_decision"] = {
        "approved": False,
        "spend_tier": "DUAL_VP",
        "tokens": [token1.serialize()],
        "signers": ["usr-director-01"],
    }
    update_one = hitl_gate_node(state)
    assert update_one["workflow_status"] == "PARTIALLY_APPROVED"

    # Case C: Two distinct signatures -> APPROVED
    state["hitl_decision"] = {
        "approved": True,
        "spend_tier": "DUAL_VP",
        "tokens": [token1.serialize(), token2.serialize()],
        "signers": ["usr-director-01", "usr-vp-02"],
        "token_hash": token2.token_hash,
    }
    update_two = hitl_gate_node(state)
    assert update_two["workflow_status"] == WorkflowStatus.APPROVED


def test_route_after_hitl_gate_enforces_dual_signatures_before_action(
    token_service: HITLTokenService,
) -> None:
    """Verify route_after_hitl_gate strictly prevents single-signature progression to NODE_ACTION."""
    action_id = "ACT-ROUTE-001"
    alert_id = "ALT-ROUTE-001"
    amount = Decimal("150000.00")

    state: SupplierRiskState = create_initial_state(
        alert_id=alert_id,
        supplier_id="SUP-NC-882",
    )
    state["requires_hitl"] = True
    state["governing_spend_tier"] = SpendTier.DUAL_VP
    state["recommended_action_id"] = action_id
    state["recommendations"] = [{"action_id": action_id, "estimated_cost_usd": amount}]

    # 1. No decision -> await_approval
    assert route_after_hitl_gate(state) == "await_approval"

    # 2. Single signature with approved=True attempted (Adversarial Bypass Attempt) -> MUST STILL BE await_approval
    state["hitl_decision"] = {
        "approved": True,
        "tokens": ["single_token_string"],
        "signers": ["usr-director-01"],
    }
    assert route_after_hitl_gate(state) == "await_approval"

    # 3. Two valid tokens in state -> NODE_ACTION
    token1 = token_service.issue_token(
        action_id=action_id,
        alert_id=alert_id,
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=amount,
        signer_id="usr-director-01",
        signer_role="procurement_director",
    )
    token2 = token_service.issue_token(
        action_id=action_id,
        alert_id=alert_id,
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=amount,
        signer_id="usr-vp-02",
        signer_role="vp_supply_chain",
    )
    state["hitl_decision"] = {
        "approved": True,
        "tokens": [token1.serialize(), token2.serialize()],
        "signers": ["usr-director-01", "usr-vp-02"],
        "token_hash": token2.token_hash,
        "is_dual_approved": True,
    }
    assert route_after_hitl_gate(state) == NODE_ACTION


def test_action_node_hard_gate_blocks_single_signature_execution(
    token_service: HITLTokenService,
) -> None:
    """Verify action_node raises InsufficientSignaturesError if invoked with single signature on DUAL_VP."""
    action_id = "ACT-BLOCK-001"
    alert_id = "ALT-BLOCK-001"
    amount = Decimal("2448105.00")

    token1 = token_service.issue_token(
        action_id=action_id,
        alert_id=alert_id,
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=amount,
        signer_id="usr-director-01",
        signer_role="procurement_director",
    )

    state: SupplierRiskState = create_initial_state(
        alert_id=alert_id,
        supplier_id="SUP-NC-882",
    )
    state["requires_hitl"] = True
    state["governing_spend_tier"] = SpendTier.DUAL_VP
    state["recommended_action_id"] = action_id
    state["recommendations"] = [{"action_id": action_id, "estimated_cost_usd": amount}]
    state["hitl_decision"] = {
        "approved": True,
        "token_hash": token1.token_hash,
        "signer_id": "usr-director-01",
        "tokens": [token1.serialize()],
        "signers": ["usr-director-01"],
    }

    # Direct invocation of action_node MUST raise InsufficientSignaturesError
    with pytest.raises(InsufficientSignaturesError, match="require 2 independent"):
        action_node(state)


def test_action_node_executes_when_dual_approval_satisfied(
    token_service: HITLTokenService,
) -> None:
    """Verify action_node executes successfully when two valid signatures are verified."""
    action_id = "ACT-EXEC-001"
    alert_id = "ALT-EXEC-001"
    amount = Decimal("2448105.00")

    token1 = token_service.issue_token(
        action_id=action_id,
        alert_id=alert_id,
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=amount,
        signer_id="usr-director-01",
        signer_role="procurement_director",
    )
    token2 = token_service.issue_token(
        action_id=action_id,
        alert_id=alert_id,
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=amount,
        signer_id="usr-vp-02",
        signer_role="vp_supply_chain",
    )

    state: SupplierRiskState = create_initial_state(
        alert_id=alert_id,
        supplier_id="SUP-NC-882",
    )
    state["requires_hitl"] = True
    state["governing_spend_tier"] = SpendTier.DUAL_VP
    state["recommended_action_id"] = action_id
    state["recommendations"] = [{"action_id": action_id, "estimated_cost_usd": amount}]
    state["hitl_decision"] = {
        "approved": True,
        "token_hash": token2.token_hash,
        "tokens": [token1.serialize(), token2.serialize()],
        "signers": ["usr-director-01", "usr-vp-02"],
        "is_dual_approved": True,
    }

    result = action_node(state)
    assert result["workflow_status"] == WorkflowStatus.EXECUTED
    assert result["current_node"] == NODE_ACTION
    assert len(result["audit_events"]) == 1
    audit = result["audit_events"][0]
    assert audit["action"] == "EXECUTE_PROCUREMENT_MITIGATION"
    assert audit["action_id"] == action_id
    assert audit["is_dual_approved"] is True
    assert "usr-director-01" in audit["signers"]
    assert "usr-vp-02" in audit["signers"]


# ------------------------------------------------------------------------------
# 4. End-to-End StateGraph Execution with Dual Sign-Off
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compiled_stategraph_pauses_for_dual_approval_and_resumes(
    token_service: HITLTokenService,
) -> None:
    """Verify compiled StateGraph on high-value disruption ($2.45M) pauses at HITL gate and executes only on 2 tokens."""
    action_id = "ACT-NC-EXPEDITE"
    alert_id = "ALT-NC-GOLDEN"
    amount = Decimal("2448105.00")

    checkpointer = MemorySaver()
    orchestrator = InvestigationOrchestrator(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "case-dual-nanocore-001"}}

    initial_state = create_initial_state(
        alert_id=alert_id,
        supplier_id="SUP-NC-882",
        raw_signal="Cleanroom fire in Fab 2 at NanoCore Microelectronics.",
        current_stock=142000,
        daily_consumption_rate=Decimal("18500.00"),
        eta_days=Decimal("9.00"),
        unit_cost_usd=Decimal("100.25"),
    )

    # 1. Run until hitl_gate: must pause at AWAITING_APPROVAL because spend is $2,448,105 (DUAL_VP)
    res1 = await orchestrator.run_investigation(initial_state, config=config)
    assert res1["requires_hitl"] is True
    assert res1["governing_spend_tier"] == SpendTier.DUAL_VP
    assert res1["workflow_status"] == WorkflowStatus.AWAITING_APPROVAL
    assert NODE_ACTION not in res1["execution_path"]

    rec_action_id = res1.get("recommended_action_id") or action_id
    token_dir = token_service.issue_token(
        action_id=rec_action_id,
        alert_id=alert_id,
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=amount,
        signer_id="usr-director-01",
        signer_role="procurement_director",
    )
    token_vp = token_service.issue_token(
        action_id=rec_action_id,
        alert_id=alert_id,
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=amount,
        signer_id="usr-vp-02",
        signer_role="vp_supply_chain",
    )

    # 2. Submit single signature: state transitions to PARTIALLY_APPROVED and remains paused
    partial_update = {
        "approved": False,
        "tokens": [token_dir.serialize()],
        "signers": ["usr-director-01"],
        "spend_tier": "DUAL_VP",
    }
    res2 = await orchestrator.resume_investigation(
        thread_id="case-dual-nanocore-001",
        hitl_decision=partial_update,
        config=config,
    )
    assert res2["workflow_status"] == "PARTIALLY_APPROVED"
    assert NODE_ACTION not in res2["execution_path"]

    # 3. Submit second executive signature: state validates dual approval and executes action_node
    full_update = {
        "approved": True,
        "tokens": [token_dir.serialize(), token_vp.serialize()],
        "signers": ["usr-director-01", "usr-vp-02"],
        "token_hash": token_vp.token_hash,
        "spend_tier": "DUAL_VP",
        "is_dual_approved": True,
    }
    res3 = await orchestrator.resume_investigation(
        thread_id="case-dual-nanocore-001",
        hitl_decision=full_update,
        config=config,
    )
    assert res3["workflow_status"] == WorkflowStatus.EXECUTED
    assert NODE_ACTION in res3["execution_path"]


# ------------------------------------------------------------------------------
# 5. Singleton & Thread-Safety Tests
# ------------------------------------------------------------------------------


def test_get_dual_approval_enforcer_singleton() -> None:
    """Verify get_dual_approval_enforcer returns a thread-safe singleton instance."""
    e1 = get_dual_approval_enforcer()
    e2 = get_dual_approval_enforcer()
    assert e1 is e2
    assert isinstance(e1, DualApprovalEnforcer)


def test_get_dual_approval_enforcer_thread_safe_init() -> None:
    """Verify concurrent instantiation creates exactly one singleton instance."""
    import src.services.dual_approval_enforcer as mod

    with mod._enforcer_lock:
        mod._enforcer_instance = None

    instances: list[DualApprovalEnforcer] = []

    def _worker() -> None:
        inst = get_dual_approval_enforcer()
        instances.append(inst)

    threads = [threading.Thread(target=_worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(i is instances[0] for i in instances)


# ------------------------------------------------------------------------------
# 6. Additional Branch Coverage Tests (100% Targets)
# ------------------------------------------------------------------------------


def test_verify_dual_approval_tampered_signature(
    enforcer: DualApprovalEnforcer,
    token_service: HITLTokenService,
    mock_kms_client: MagicMock,
) -> None:
    """Verify tampered or invalid cryptographic signatures are rejected with TokenSignatureInvalidError."""
    token1 = token_service.issue_token(
        action_id="ACT-TAMP-001",
        alert_id="ALT-TAMP-001",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("150000.00"),
        signer_id="usr-director-01",
        signer_role="procurement_director",
    )
    token2 = token_service.issue_token(
        action_id="ACT-TAMP-001",
        alert_id="ALT-TAMP-001",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("150000.00"),
        signer_id="usr-vp-02",
        signer_role="vp_supply_chain",
    )

    # Simulate KMS returning invalid signature for second token
    mock_kms_client.verify.return_value = {"SignatureValid": False}

    res = enforcer.verify_signatures(
        tokens=[token1, token2],
        expected_action_id="ACT-TAMP-001",
        raise_on_error=False,
    )
    assert res.is_approved is False
    assert res.error == "INVALID_SIGNATURE"


def test_verify_dual_approval_malformed_token_string(enforcer: DualApprovalEnforcer) -> None:
    """Verify malformed serialized token strings are rejected gracefully or raise DualApprovalError."""
    res = enforcer.verify_signatures(
        tokens=["not-a-valid-base64-json-token", "another-invalid-token"],
        raise_on_error=False,
    )
    assert res.is_approved is False
    assert res.error == "MALFORMED_TOKEN"

    with pytest.raises(DualApprovalError, match="Malformed token"):
        enforcer.verify_signatures(
            tokens=["not-a-valid-base64-json-token", "another-invalid-token"],
            raise_on_error=True,
        )


def test_enforce_state_approval_single_signer_and_fallbacks(enforcer: DualApprovalEnforcer) -> None:
    """Verify enforce_state_approval for single-signer spend tiers, non-HITL states, and rejected states."""
    # 1. State does not require HITL ($0 spend)
    state_free = create_initial_state(alert_id="ALT-FREE", supplier_id="SUP-1")
    state_free["requires_hitl"] = False
    res_free = enforcer.enforce_state_approval(state_free)
    assert res_free.is_approved is True

    # 2. State requires HITL but no decision present
    state_no_dec = create_initial_state(alert_id="ALT-NODEC", supplier_id="SUP-1")
    state_no_dec["requires_hitl"] = True
    res_no_dec = enforcer.enforce_state_approval(state_no_dec, raise_on_error=False)
    assert res_no_dec.is_approved is False
    assert res_no_dec.error == "AWAITING_APPROVAL"

    with pytest.raises(InsufficientSignaturesError):
        enforcer.enforce_state_approval(state_no_dec, raise_on_error=True)

    # 3. State rejected by human
    state_rej = create_initial_state(alert_id="ALT-REJ", supplier_id="SUP-1")
    state_rej["requires_hitl"] = True
    state_rej["hitl_decision"] = {"approved": False, "reason": "Cost excessive"}
    res_rej = enforcer.enforce_state_approval(state_rej)
    assert res_rej.is_approved is False
    assert res_rej.error == "REJECTED"

    # 4. Single-signer tier approved (Category Mgr <= $25k)
    state_cat = create_initial_state(alert_id="ALT-CAT", supplier_id="SUP-1")
    state_cat["requires_hitl"] = True
    state_cat["governing_spend_tier"] = SpendTier.CATEGORY_MGR
    state_cat["hitl_decision"] = {
        "approved": True,
        "token_hash": "cat_mgr_hash_123",
        "signer_id": "usr-cat-mgr",
    }
    res_cat = enforcer.enforce_state_approval(state_cat)
    assert res_cat.is_approved is True
    assert res_cat.spend_tier == SpendTier.CATEGORY_MGR

    # 5. Amount normalization with int and str
    assert enforcer.is_dual_approval_required(amount_usd=150000) is True
    assert enforcer.is_dual_approval_required(amount_usd="50000.00") is False
    assert enforcer.is_dual_approval_required(amount_usd=None, spend_tier=SpendTier.DUAL_VP) is True
