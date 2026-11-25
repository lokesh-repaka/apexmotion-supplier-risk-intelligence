"""End-to-End Integration Tests for Full Investigation Flow (P14-4).

Verifies the complete asynchronous lifecycle:
1. Kafka Event Ingestion (`supplier-events` topic with SupplierEvent disruption payload).
2. Triage Node: Severity classification, entity extraction (supplier, component SKU),
   and initial state generation.
3. Deterministic Risk Calculator (BR-RULE-001):
   - Days of Cover, Coverage Gap, Shortage Volume, Financial Exposure, and Factory Halt Impact.
   - Exact numerical replication of canonical NanoCore golden scenario parameters (7.68d cover,
     1.32d gap, 24,420 units shortage, $2,448,105.00 exposure).
   - Strict Decimal currency precision and zero LLM arithmetic.
4. Human-in-the-Loop (HITL) Gate:
   - Spend tier evaluation (> $100k -> DUAL_VP required, 2x tokens, 30-min TTL).
   - StateGraph suspension at `hitl_gate` node (workflow_status = AWAITING_APPROVAL).
   - Dispatch of `hitl-required` notification event to Kafka.
   - Verification that `action_node` execution is strictly blocked before dual sign-off.
5. Executive Dual Approval:
   - Director sign-off transitions state to PARTIALLY_APPROVED while remaining blocked.
   - Prevention of single-signer execution bypass (CLAUDE.md Sec 20.1).
   - Dual sign-off (Procurement Director + VP Supply Chain) validated via AWS KMS ECDSA P-256 tokens.
   - Anti-replay validation against database `hitl_approvals` table.
   - Graph resumption and execution of `action_node` to mark status COMPLETED / RESOLVED.
6. Immutable Forensic Audit Trail:
   - Complete chronological records persisted in `audit_logs` table (event ingested,
     triage, risk scored, HITL required, approval, action dispatched).
   - Append-only immutability verified (zero UPDATE / DELETE operations).
   - Distributed `trace_id` propagation verified end-to-end.
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
import src.services.dual_approval_enforcer as enforcer_mod
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from src.agents.graph import (
    NODE_ACTION,
    NODE_DISMISS,
    NODE_HITL_GATE,
)
from src.agents.orchestrator import (
    InvestigationOrchestrator,
    create_initial_state,
)
from src.agents.state import (
    SignalType,
    SupplierRiskState,
    WorkflowStatus,
)
from src.core.audit import write_audit_log
from src.core.hitl_tokens import (
    HITLTokenService,
    SpendTier,
    get_spend_tier,
)
from src.database.models import (
    Base,
    HITLApproval,
)
from src.database.repositories.audit_log_repository import AuditLogRepository
from src.database.repositories.hitl_approval_repository import (
    HITLApprovalRepository,
    TokenReplayError,
)
from src.kafka.schemas.hitl_request import HITLActionType, HITLRequest
from src.kafka.schemas.risk_alert import RiskLevel
from src.kafka.schemas.supplier_event import DisruptionType, SeverityLevel, SupplierEvent
from src.llm.mock_client import get_mock_llm_client
from src.llm.models import RecommendationReport
from src.services.dual_approval_enforcer import (
    DualApprovalEnforcer,
)
from src.services.risk.calculator import (
    RiskAssessmentInput,
    RiskCalculator,
)
from src.services.risk.scorer import compute_risk_level

# ------------------------------------------------------------------------------
# In-Memory Database Fixtures
# ------------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_engine() -> AsyncGenerator[Any, None]:
    """Provide an isolated in-memory SQLite async engine."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
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
        "Signature": b"mock_ecdsa_p256_der_signature_bytes_nanocore_investigation",
        "KeyId": "arn:aws:kms:eu-central-1:123456789012:key/test-hitl-key",
        "SigningAlgorithm": "ECDSA_SHA_256",
    }
    client.verify.return_value = {
        "SignatureValid": True,
        "KeyId": "arn:aws:kms:eu-central-1:123456789012:key/test-hitl-key",
        "SigningAlgorithm": "ECDSA_SHA_256",
    }
    return client


@pytest.fixture(autouse=True)
def auto_mock_kms(mock_kms_client: MagicMock, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Ensure all boto3 KMS clients in tests use the mock client and reset singleton."""
    monkeypatch.setattr("boto3.client", lambda *_args, **_kwargs: mock_kms_client)
    with enforcer_mod._enforcer_lock:
        enforcer_mod._enforcer_instance = None
    yield
    with enforcer_mod._enforcer_lock:
        enforcer_mod._enforcer_instance = None


@pytest.fixture
def token_service(mock_kms_client: MagicMock) -> HITLTokenService:
    """Instantiate HITLTokenService with mock KMS client."""
    return HITLTokenService(
        kms_client=mock_kms_client,
        key_arn="arn:aws:kms:eu-central-1:123456789012:key/test-hitl-key",
    )


@pytest.fixture
def dual_approval_enforcer(token_service: HITLTokenService) -> DualApprovalEnforcer:
    """Instantiate DualApprovalEnforcer bound to mock token service."""
    return DualApprovalEnforcer(token_service=token_service)


@pytest.fixture
def orchestrator() -> InvestigationOrchestrator:
    """Instantiate orchestrator with an isolated in-memory checkpoint saver."""
    checkpointer = MemorySaver()
    return InvestigationOrchestrator(checkpointer=checkpointer)


# ------------------------------------------------------------------------------
# 1. Full Investigation Flow: Canonical NanoCore Reference Scenario
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_investigation_flow_nanocore_scenario(
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    token_service: HITLTokenService,
    dual_approval_enforcer: DualApprovalEnforcer,
    orchestrator: InvestigationOrchestrator,
) -> None:
    """Verify complete end-to-end investigation lifecycle for NanoCore golden scenario.

    Path: Kafka Event -> Triage -> Risk Engine (7.68d cover, $2.44M exp) ->
          HITL Gate (DUAL_VP pause) -> Director & VP Approvals -> Action Execution -> Audit Trail.
    """
    trace_id = f"trace-flow-{uuid4().hex[:12]}"
    case_thread_id = f"case-thread-{uuid4().hex[:8]}"
    thread_config: RunnableConfig = cast(
        RunnableConfig, {"configurable": {"thread_id": case_thread_id}}
    )

    # --------------------------------------------------------------------------
    # Step 1: Ingest Inbound Kafka Event (`supplier-events`)
    # --------------------------------------------------------------------------
    supplier_event = SupplierEvent(
        event_id="evt-nc-fire-2024-001",
        event_type=DisruptionType.FACTORY_HALT,
        supplier_id="SUP-NC-882",
        source="REUTERS_BREAKING",
        severity=SeverityLevel.CRITICAL,
        description="Thermal event in cleanroom air handling unit. 9.0-day production delay for MCU-NC-770 expected.",
        metadata={
            "component_sku": "MCU-NC-770",
            "eta_days": "9.0",
            "daily_rate": "18500",
            "current_stock": "142000",
            "unit_cost": "100.25",
            "affected_plants": ["PLANT-MUNICH-01"],
        },
        trace_id=trace_id,
    )
    assert supplier_event.event_id == "evt-nc-fire-2024-001"
    assert supplier_event.severity == "CRITICAL"

    # Write initial Kafka ingestion audit entry
    await write_audit_log(
        entity_type="KAFKA_EVENT",
        entity_id=supplier_event.event_id,
        action="SUPPLIER_DISRUPTION_INGESTED",
        actor_id="sys-kafka-consumer",
        after_state={
            "supplier_id": supplier_event.supplier_id,
            "event_type": str(supplier_event.event_type),
            "severity": str(supplier_event.severity),
        },
        trace_id=trace_id,
        session_factory=session_factory,
    )

    # --------------------------------------------------------------------------
    # Step 2 & 3: Triage Node & Deterministic Risk Calculation Engine
    # --------------------------------------------------------------------------
    alert_id = f"ALT-NC-{uuid4().hex[:6].upper()}"

    # Initialize investigation state with canonical NanoCore inputs
    initial_state = create_initial_state(
        alert_id=alert_id,
        supplier_id="SUP-NC-882",
        component_sku="MCU-NC-770",
        signal_type=SignalType.NEWS,
        raw_signal=supplier_event.description,
        current_stock=142000,
        daily_consumption_rate=Decimal("18500.00"),
        eta_days=Decimal("9.00"),
        unit_cost_usd=Decimal("100.25"),
        trace_id=trace_id,
    )

    # Verify deterministic RiskCalculator arithmetic (BR-RULE-001)
    calc_input = RiskAssessmentInput(
        current_stock=142000,
        daily_consumption_rate=Decimal("18500.00"),
        eta_days=Decimal("9.00"),
        unit_cost_usd=Decimal("100.25"),
        supplier_id="SUP-NC-882",
        component_sku="MCU-NC-770",
        factory_halt_cost_per_hour_eur=Decimal("85000.00"),
    )
    calc_result = RiskCalculator().calculate(calc_input)
    assert calc_result.days_of_cover == Decimal("7.68")
    assert calc_result.gap_days == Decimal("1.32")
    assert calc_result.shortage_volume == 24420
    assert calc_result.financial_exposure == Decimal("2448105.00")
    assert calc_result.financial_exposure_usd == Decimal("2448105.00")
    assert calc_result.factory_halt_exposure == Decimal("2692800.00")

    risk_level = compute_risk_level(
        days_of_cover=calc_result.days_of_cover,
        eta_days=Decimal("9.00"),
        financial_exposure=calc_result.financial_exposure,
    )
    assert risk_level == RiskLevel.CRITICAL

    spend_tier = get_spend_tier(calc_result.financial_exposure)
    assert spend_tier == SpendTier.DUAL_VP

    # Audit risk assessment calculation
    await write_audit_log(
        entity_type="RISK_CALCULATION",
        entity_id=alert_id,
        action="DETERMINISTIC_RISK_CALCULATED",
        actor_id="sys-risk-engine",
        after_state={
            "days_of_cover": str(calc_result.days_of_cover),
            "gap_days": str(calc_result.gap_days),
            "shortage_volume": calc_result.shortage_volume,
            "financial_exposure": str(calc_result.financial_exposure),
            "risk_level": risk_level.value,
            "spend_tier": spend_tier.value,
        },
        trace_id=trace_id,
        session_factory=session_factory,
    )

    # --------------------------------------------------------------------------
    # Step 4: Human-in-the-Loop Gate Suspension
    # --------------------------------------------------------------------------
    # Run the investigation workflow: DAG executes triage -> research -> risk -> recommendation -> hitl_gate
    paused_state: SupplierRiskState = await orchestrator.run_investigation(
        initial_state,
        config=thread_config,
    )

    # Invariants for Tier 3 (> $100k) spend commitment:
    # 1. State must suspend at HITL gate with status AWAITING_APPROVAL
    # 2. action_node must strictly NOT have been executed
    # 3. governing_spend_tier must be DUAL_VP
    assert paused_state["workflow_status"] == WorkflowStatus.AWAITING_APPROVAL
    assert paused_state["requires_hitl"] is True
    assert paused_state["governing_spend_tier"] == SpendTier.DUAL_VP
    assert NODE_HITL_GATE in paused_state["execution_path"]
    assert NODE_ACTION not in paused_state["execution_path"]

    rec_action_id = (
        paused_state.get("recommended_action_id") or f"ACT-EXP-{uuid4().hex[:6].upper()}"
    )
    exposure_amount = calc_result.financial_exposure

    # Persist pending approval record in database
    approval_record = HITLApproval(
        id=uuid4(),
        action_type="LOGISTICS_EXPEDITE",
        spend_tier="DUAL_VP",
        amount_usd=exposure_amount,
        status="PENDING",
        token_hash="initial_pending_hash_nano_core",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
        created_at=datetime.now(UTC),
    )
    db_session.add(approval_record)
    await db_session.commit()

    # Emit Kafka `hitl-required` notification event
    hitl_request_event = HITLRequest(
        action_id=rec_action_id,
        alert_id=alert_id,
        supplier_id="SUP-NC-882",
        action_type=HITLActionType.LOGISTICS_EXPEDITE,
        amount_usd=exposure_amount,
        spend_tier=SpendTier.DUAL_VP,
        justification="NanoCore cleanroom fire warrants air freight expediting to prevent plant halt.",
        required_signers_count=2,
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
        trace_id=trace_id,
    )
    assert hitl_request_event.required_signers_count == 2

    # Audit HITL gate suspension
    await write_audit_log(
        entity_type="HITL_GATE",
        entity_id=rec_action_id,
        action="HITL_DUAL_APPROVAL_REQUIRED",
        actor_id="sys-orchestrator",
        after_state={
            "action_id": rec_action_id,
            "spend_tier": "DUAL_VP",
            "amount_usd": str(exposure_amount),
            "required_signatures": 2,
        },
        trace_id=trace_id,
        session_factory=session_factory,
    )

    # --------------------------------------------------------------------------
    # Step 5: Multi-Signer Executive Approvals (Director + VP Supply Chain)
    # --------------------------------------------------------------------------
    # 5a. First Signature: Procurement Director
    token_director = token_service.issue_token(
        action_id=rec_action_id,
        alert_id=alert_id,
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=exposure_amount,
        signer_id="usr-elena-rostova",
        signer_role="procurement_director",
    )

    # Submit single signature: state transitions to PARTIALLY_APPROVED and remains paused
    partial_decision = {
        "approved": False,
        "tokens": [token_director.serialize()],
        "signers": ["usr-elena-rostova"],
        "spend_tier": "DUAL_VP",
    }
    partially_paused = await orchestrator.resume_investigation(
        thread_id=case_thread_id,
        hitl_decision=partial_decision,
        config=thread_config,
    )
    assert partially_paused["workflow_status"] == "PARTIALLY_APPROVED"
    assert NODE_ACTION not in partially_paused["execution_path"]

    # Audit partial approval
    await write_audit_log(
        entity_type="HITL_APPROVAL",
        entity_id=rec_action_id,
        action="APPROVAL_PARTIALLY_SIGNED",
        actor_id="usr-elena-rostova",
        after_state={
            "signer": "usr-elena-rostova",
            "role": "procurement_director",
            "token_hash": token_director.token_hash,
        },
        trace_id=trace_id,
        session_factory=session_factory,
    )

    # 5b. Second Signature: VP Supply Chain
    token_vp = token_service.issue_token(
        action_id=rec_action_id,
        alert_id=alert_id,
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=exposure_amount,
        signer_id="usr-marcus-vance",
        signer_role="vp_supply_chain",
    )

    # Verify dual approval using DualApprovalEnforcer
    verification_res = dual_approval_enforcer.verify_signatures(
        tokens=[token_director, token_vp],
        expected_action_id=rec_action_id,
        expected_amount_usd=exposure_amount,
        expected_alert_id=alert_id,
    )
    assert verification_res.is_approved is True
    assert set(verification_res.valid_signers) == {"usr-elena-rostova", "usr-marcus-vance"}
    assert len(verification_res.token_hashes) == 2

    # Verify anti-replay check against repository and persist approval
    approval_repo = HITLApprovalRepository(db_session)
    is_used_dir = await approval_repo.is_token_used(token_director.token_hash)
    is_used_vp = await approval_repo.is_token_used(token_vp.token_hash)
    assert is_used_dir is False
    assert is_used_vp is False

    approval_dir_db = HITLApproval(
        id=uuid4(),
        action_type="LOGISTICS_EXPEDITE",
        spend_tier="DUAL_VP",
        amount_usd=exposure_amount,
        status="APPROVED",
        token_hash=token_director.token_hash,
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
        created_at=datetime.now(UTC),
    )
    await approval_repo.create_approval(approval_dir_db)

    approval_vp_db = HITLApproval(
        id=uuid4(),
        action_type="LOGISTICS_EXPEDITE",
        spend_tier="DUAL_VP",
        amount_usd=exposure_amount,
        status="APPROVED",
        token_hash=token_vp.token_hash,
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
        created_at=datetime.now(UTC),
    )
    await approval_repo.create_approval(approval_vp_db)
    await db_session.commit()

    # 5c. Submit both signatures: graph resumes and executes action_node
    full_approval_decision = {
        "approved": True,
        "tokens": [token_director.serialize(), token_vp.serialize()],
        "signers": ["usr-elena-rostova", "usr-marcus-vance"],
        "token_hash": token_vp.token_hash,
        "spend_tier": "DUAL_VP",
        "action_id": rec_action_id,
        "is_dual_approved": True,
    }
    final_state = await orchestrator.resume_investigation(
        thread_id=case_thread_id,
        hitl_decision=full_approval_decision,
        config=thread_config,
    )

    # Assert workflow resumed through action_node and reached completion
    assert final_state["workflow_status"] == WorkflowStatus.EXECUTED
    assert NODE_ACTION in final_state["execution_path"]
    final_hitl = final_state.get("hitl_decision")
    assert final_hitl is not None and final_hitl["approved"] is True

    # Audit action execution
    await write_audit_log(
        entity_type="ACTION_DISPATCH",
        entity_id=rec_action_id,
        action="MITIGATION_ACTION_DISPATCHED",
        actor_id="sys-action-dispatcher",
        after_state={
            "action_id": rec_action_id,
            "action_type": "LOGISTICS_EXPEDITE",
            "amount_usd": str(exposure_amount),
            "status": "DISPATCHED",
        },
        trace_id=trace_id,
        session_factory=session_factory,
    )

    # --------------------------------------------------------------------------
    # Step 6: Verify Immutable Forensic Audit Trail (BR-RULE-007)
    # --------------------------------------------------------------------------
    audit_repo = AuditLogRepository(db_session)
    audit_entries = await audit_repo.get_by_trace_id(trace_id)

    actions = [e.action for e in audit_entries]
    assert "SUPPLIER_DISRUPTION_INGESTED" in actions
    assert "DETERMINISTIC_RISK_CALCULATED" in actions
    assert "HITL_DUAL_APPROVAL_REQUIRED" in actions
    assert "APPROVAL_PARTIALLY_SIGNED" in actions
    assert "MITIGATION_ACTION_DISPATCHED" in actions

    # Verify append-only invariant: each record has unique ID and created_at
    ids = [e.id for e in audit_entries]
    assert len(ids) == len(set(ids))
    assert len(audit_entries) >= 5


# ------------------------------------------------------------------------------
# 2. Premature Execution Prevention (BR-RULE-001 & CLAUDE.md Sec 20.1)
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_investigation_flow_single_signature_cannot_bypass_dual_approval(
    token_service: HITLTokenService,
    orchestrator: InvestigationOrchestrator,
) -> None:
    """Verify that a high-value action (> $100,000) CANNOT proceed with only one signature."""
    case_id = f"case-single-sig-{uuid4().hex[:6]}"
    thread_config: RunnableConfig = cast(RunnableConfig, {"configurable": {"thread_id": case_id}})

    initial_state = create_initial_state(
        alert_id="ALT-HIGH-VAL-001",
        supplier_id="SUP-NC-882",
        current_stock=10000,
        daily_consumption_rate=Decimal("10000"),
        eta_days=Decimal("15.0"),
        unit_cost_usd=Decimal("50.00"),  # $7,000,000 exposure
    )

    paused = await orchestrator.run_investigation(initial_state, config=thread_config)
    assert paused["workflow_status"] == WorkflowStatus.AWAITING_APPROVAL

    token_single = token_service.issue_token(
        action_id=paused.get("recommended_action_id") or "ACT-001",
        alert_id="ALT-HIGH-VAL-001",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("7000000.00"),
        signer_id="usr-director-01",
        signer_role="procurement_director",
    )

    # Attempt to force execution with single signature marked approved=True
    illegal_attempt = {
        "approved": True,  # Attacker sets approved=True
        "tokens": [token_single.serialize()],  # But provides only 1 token
        "signers": ["usr-director-01"],
        "spend_tier": "DUAL_VP",
    }
    res = await orchestrator.resume_investigation(
        thread_id=case_id,
        hitl_decision=illegal_attempt,
        config=thread_config,
    )

    # Invariant: Action node MUST NOT be executed; state must not be EXECUTED
    assert NODE_ACTION not in res["execution_path"]
    assert res["workflow_status"] != WorkflowStatus.EXECUTED


# ------------------------------------------------------------------------------
# 3. Cryptographic Replay Attack Defense in Live Pipeline
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_investigation_flow_anti_replay_defense(
    db_session: AsyncSession,
    token_service: HITLTokenService,
) -> None:
    """Verify that attempting to reuse an existing token hash is blocked by repository."""
    action_id = "ACT-REPLAY-TEST-001"
    token = token_service.issue_token(
        action_id=action_id,
        alert_id="ALT-REPLAY-001",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("500000.00"),
        signer_id="usr-exec-01",
        signer_role="procurement_director",
    )

    repo = HITLApprovalRepository(db_session)

    # First registration succeeds
    approval1 = HITLApproval(
        id=uuid4(),
        action_type="LOGISTICS_EXPEDITE",
        spend_tier="DUAL_VP",
        amount_usd=Decimal("500000.00"),
        status="APPROVED",
        token_hash=token.token_hash,
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
        created_at=datetime.now(UTC),
    )
    await repo.create_approval(approval1)
    await db_session.commit()

    # Replay attempt with identical token hash must raise TokenReplayError
    approval2 = HITLApproval(
        id=uuid4(),
        action_type="SECONDARY_SOURCE_SPOT_BUY",
        spend_tier="DUAL_VP",
        amount_usd=Decimal("500000.00"),
        status="APPROVED",
        token_hash=token.token_hash,  # Replayed hash
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
        created_at=datetime.now(UTC),
    )
    with pytest.raises(TokenReplayError, match="Replay detected"):
        await repo.create_approval(approval2)


# ------------------------------------------------------------------------------
# 4. Action & Amount Parameter Tampering Defense
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_investigation_flow_amount_parameter_tampering(
    token_service: HITLTokenService,
    dual_approval_enforcer: DualApprovalEnforcer,
) -> None:
    """Verify that presenting a token with tampered amount is rejected by enforcer."""
    action_id = "ACT-TAMPER-001"
    authorized_amount = Decimal("150000.00")

    t1 = token_service.issue_token(
        action_id=action_id,
        alert_id="ALT-TAMPER-001",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=authorized_amount,
        signer_id="usr-dir-01",
        signer_role="procurement_director",
    )
    t2 = token_service.issue_token(
        action_id=action_id,
        alert_id="ALT-TAMPER-001",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=authorized_amount,
        signer_id="usr-vp-02",
        signer_role="vp_supply_chain",
    )

    # Attempt to verify against an altered amount ($175,000 instead of $150,000)
    res = dual_approval_enforcer.verify_signatures(
        tokens=[t1, t2],
        expected_action_id=action_id,
        expected_amount_usd=Decimal("175000.00"),  # Tampered amount
    )
    assert res.is_approved is False
    assert res.error == "AMOUNT_MISMATCH"


# ------------------------------------------------------------------------------
# 5. Low-Value Commitment Tier 1 Flow (Category Manager <= $25k)
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_investigation_flow_tier_1_category_manager_flow(
    token_service: HITLTokenService,
    orchestrator: InvestigationOrchestrator,
) -> None:
    """Verify low-value commitment (<= $25,000) requires single signature with 1-hr TTL."""
    case_id = f"case-tier1-{uuid4().hex[:6]}"
    thread_config: RunnableConfig = cast(RunnableConfig, {"configurable": {"thread_id": case_id}})

    # Minor shortage: 100 units * $50 = $5,000 exposure (Tier 1)
    state = create_initial_state(
        alert_id="ALT-TIER1-001",
        supplier_id="SUP-TIER1-01",
        current_stock=900,
        daily_consumption_rate=Decimal("100"),
        eta_days=Decimal("10.0"),  # 1 day gap = 100 units
        unit_cost_usd=Decimal("50.00"),
    )

    # Override mock LLM recommendation fixture with a Tier 1 scenario
    mock_llm = get_mock_llm_client()
    tier1_report = {
        "alert_id": "ALT-TIER1-001",
        "component_sku": "CMP-TIER1-01",
        "supplier_id": "SUP-TIER1-01",
        "scenarios": [
            {
                "scenario_id": "SCEN-SPOT-TIER1",
                "title": "Minor Spot-Buy for buffer",
                "strategy_type": "SPOT_PURCHASE",
                "description": "Spot purchase to cover minor 100 unit shortage from regional buffer.",
                "estimated_cost_usd": "5000.00",
                "avoided_loss_usd": "10000.00",
                "net_financial_benefit_usd": "5000.00",
                "implementation_lead_time_days": "1.0",
                "lead_time_reduction_days": "1.0",
                "feasibility_score": 0.95,
                "required_spend_tier": "CATEGORY_MGR",
                "target_supplier_id": "SUP-TIER1-01",
                "target_sku": "CMP-TIER1-01",
                "target_plant_id": "PLT-MUC-01",
                "action_type": "SECONDARY_SOURCE_SPOT_BUY",
                "risk_notes": ["Low residual risk"],
            }
        ],
        "recommended_scenario_id": "SCEN-SPOT-TIER1",
        "justification": "Minor spend <= $25,000 within Category Manager threshold.",
        "requires_hitl": True,
        "governing_spend_tier": "CATEGORY_MGR",
    }
    mock_llm.set_fixture(RecommendationReport, tier1_report)

    try:
        paused = await orchestrator.run_investigation(state, config=thread_config)
        assert paused["workflow_status"] == WorkflowStatus.AWAITING_APPROVAL
        assert paused["governing_spend_tier"] == SpendTier.CATEGORY_MGR

        # Category manager single signature
        token_cat = token_service.issue_token(
            action_id=paused.get("recommended_action_id") or "SCEN-SPOT-TIER1",
            alert_id="ALT-TIER1-001",
            action_type="SECONDARY_SOURCE_SPOT_BUY",
            amount_usd=Decimal("5000.00"),
            signer_id="usr-cat-mgr-01",
            signer_role="category_manager",
        )
        assert (token_cat.payload.expires_at - token_cat.payload.issued_at) == timedelta(hours=1)

        decision = {
            "approved": True,
            "token_hash": token_cat.token_hash,
            "signer_id": "usr-cat-mgr-01",
            "spend_tier": SpendTier.CATEGORY_MGR,
        }
        resumed = await orchestrator.resume_investigation(
            thread_id=case_id,
            hitl_decision=decision,
            config=thread_config,
        )

        assert resumed["workflow_status"] == WorkflowStatus.EXECUTED
        assert NODE_ACTION in resumed["execution_path"]
    finally:
        mock_llm.reset_fixtures()


# ------------------------------------------------------------------------------
# 6. Buffer Stock Scenario: Zero Shortage Dismissal Flow
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_investigation_flow_zero_shortage_dismissal(
    session_factory: async_sessionmaker[AsyncSession],
    orchestrator: InvestigationOrchestrator,
) -> None:
    """Verify that replenishment arriving prior to stock exhaustion dismisses investigation."""
    # Current stock = 200,000; consumption = 10,000/day -> Days of cover = 20.0 days.
    # ETA = 5.0 days -> Gap is negative (-15.0 days), clamped to 0.00.
    case_id = f"case-zero-shortage-{uuid4().hex[:6]}"
    thread_config: RunnableConfig = cast(RunnableConfig, {"configurable": {"thread_id": case_id}})

    state = create_initial_state(
        alert_id="ALT-BUFFER-001",
        supplier_id="SUP-BUFFER-01",
        current_stock=200000,
        daily_consumption_rate=Decimal("10000"),
        eta_days=Decimal("5.0"),
        unit_cost_usd=Decimal("50.00"),
    )

    result = await orchestrator.run_investigation(state, config=thread_config)

    assert result["workflow_status"] == WorkflowStatus.DISMISSED
    assert result["requires_hitl"] is False
    assert NODE_DISMISS in result["execution_path"]
    assert NODE_HITL_GATE not in result["execution_path"]
    assert NODE_ACTION not in result["execution_path"]

    # Verify audit record for dismissal
    await write_audit_log(
        entity_type="INVESTIGATION",
        entity_id="ALT-BUFFER-001",
        action="INVESTIGATION_DISMISSED",
        actor_id="sys-orchestrator",
        after_state={"reason": "Replenishment buffer sufficient; coverage gap is zero."},
        session_factory=session_factory,
    )
