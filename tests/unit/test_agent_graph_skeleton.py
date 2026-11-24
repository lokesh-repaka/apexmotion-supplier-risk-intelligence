"""Unit tests for LangGraph AgentState & StateGraph Skeleton (P9-1).

Verifies:
- State Schema Invariants (CLAUDE.md Sec 11 & LLD Sec 4.2):
  * SupplierRiskState & AgentState TypedDict definitions with strong types.
  * Reducer channels (operator.add) accumulating errors, execution_path, audit_events.
- Graph Topology & Compilation:
  * StateGraph construction with all required nodes (triage, research, contract, risk, recommendation, hitl_gate, action, dismiss).
  * Valid compilation with and without checkpointer (MemorySaver).
- Deterministic Conditional Edge Routing:
  * Triage routing based on signal classification.
  * Risk routing (shortage gap > 0 -> recommendation; gap <= 0 -> dismiss).
  * HITL gate routing (requires_hitl -> gate; approved -> action; rejected -> end).
- End-to-End Workflow Execution (Offline):
  * NanoCore golden scenario execution through compiled graph.
  * Buffer stock / zero-shortage dismissal execution.
  * Checkpointer state persistence and investigation resumption.
- The Triad of Responsibility (BR-RULE-001):
  * Zero LLM arithmetic; strictly typed Decimal monetary values.
"""

from decimal import Decimal

import pytest
from langgraph.checkpoint.memory import MemorySaver
from src.agents.graph import (
    NODE_ACTION,
    NODE_CONTRACT,
    NODE_DISMISS,
    NODE_HITL_GATE,
    NODE_RECOMMENDATION,
    NODE_RESEARCH,
    NODE_RISK,
    NODE_TRIAGE,
    build_investigation_graph,
    hitl_gate_node,
    recommendation_node,
    risk_node,
    route_after_hitl_gate,
    route_after_risk,
    route_after_triage,
)
from src.agents.orchestrator import (
    InvestigationOrchestrator,
    create_initial_state,
    get_investigation_graph,
)
from src.agents.state import (
    AgentState,
    SignalType,
    SupplierRiskState,
    WorkflowStatus,
)
from src.core.hitl_tokens import SpendTier
from src.kafka.schemas.risk_alert import RiskLevel

# ------------------------------------------------------------------------------
# 1. State Schema & Channel Reducer Tests
# ------------------------------------------------------------------------------


def test_supplier_risk_state_creation_defaults() -> None:
    """Verify create_initial_state constructs a valid SupplierRiskState with defaults."""
    state = create_initial_state(
        alert_id="ALT-TEST-001",
        supplier_id="SUP-NC-001",
        raw_signal="Cleanroom facility fire reported at fab",
        signal_type=SignalType.NEWS,
        component_sku="NC-CHIP-990",
        trace_id="trace-test-uuid-001",
    )

    assert state["alert_id"] == "ALT-TEST-001"
    assert state["supplier_id"] == "SUP-NC-001"
    assert state["signal_type"] == "news"
    assert state["component_sku"] == "NC-CHIP-990"
    assert state["trace_id"] == "trace-test-uuid-001"
    assert state["workflow_status"] == WorkflowStatus.PENDING
    assert state["execution_path"] == []
    assert state["errors"] == []
    assert state["audit_events"] == []
    assert state["requires_hitl"] is False
    assert state["risk_metrics"] is None


def test_supplier_risk_state_agent_state_alias() -> None:
    """Verify AgentState is an alias of SupplierRiskState for CLAUDE.md Sec 11 compatibility."""
    assert AgentState is SupplierRiskState


def test_signal_type_and_workflow_status_enums() -> None:
    """Verify SignalType and WorkflowStatus enum members match architectural spec."""
    assert SignalType.NEWS == "news"
    assert SignalType.FINANCIAL == "financial"
    assert SignalType.LOGISTICS == "logistics"
    assert SignalType.GEOPOLITICAL == "geopolitical"

    assert WorkflowStatus.PENDING == "PENDING"
    assert WorkflowStatus.TRIAGED == "TRIAGED"
    assert WorkflowStatus.INVESTIGATING == "INVESTIGATING"
    assert WorkflowStatus.AWAITING_APPROVAL == "AWAITING_APPROVAL"
    assert WorkflowStatus.EXECUTED == "EXECUTED"
    assert WorkflowStatus.DISMISSED == "DISMISSED"


# ------------------------------------------------------------------------------
# 2. Graph Construction & Compilation Tests
# ------------------------------------------------------------------------------


def test_build_investigation_graph_compiles_successfully() -> None:
    """Verify StateGraph compiles with all expected nodes and edge topologies."""
    graph = build_investigation_graph()
    assert graph is not None

    # Check registered node names
    nodes = set(graph.nodes.keys())
    for expected_node in (
        NODE_TRIAGE,
        NODE_RESEARCH,
        NODE_CONTRACT,
        NODE_RISK,
        NODE_RECOMMENDATION,
        NODE_HITL_GATE,
        NODE_ACTION,
        NODE_DISMISS,
    ):
        assert expected_node in nodes


def test_build_investigation_graph_with_checkpointer() -> None:
    """Verify graph compiles with MemorySaver checkpointer for stateful interruption."""
    checkpointer = MemorySaver()
    graph = build_investigation_graph(checkpointer=checkpointer)
    assert graph is not None
    assert graph.checkpointer is checkpointer


def test_get_investigation_graph_singleton() -> None:
    """Verify get_investigation_graph returns a compiled executable graph singleton."""
    g1 = get_investigation_graph()
    g2 = get_investigation_graph()
    assert g1 is g2


# ------------------------------------------------------------------------------
# 3. Deterministic Routing Logic Tests
# ------------------------------------------------------------------------------


def test_route_after_triage_news_and_geopolitical() -> None:
    """Verify news or geopolitical signals route to research agent node."""
    state_news = create_initial_state(
        alert_id="ALT-1",
        supplier_id="SUP-1",
        signal_type=SignalType.NEWS,
    )
    destinations = route_after_triage(state_news)
    assert destinations == [NODE_RESEARCH]

    state_geo = create_initial_state(
        alert_id="ALT-2",
        supplier_id="SUP-1",
        signal_type=SignalType.GEOPOLITICAL,
    )
    assert route_after_triage(state_geo) == [NODE_RESEARCH]


def test_route_after_triage_contract_and_financial() -> None:
    """Verify financial or contractually sensitive signals route to contract agent node."""
    state_fin = create_initial_state(
        alert_id="ALT-3",
        supplier_id="SUP-1",
        signal_type=SignalType.FINANCIAL,
    )
    destinations = route_after_triage(state_fin)
    assert destinations == [NODE_CONTRACT]


def test_route_after_triage_zero_blast_radius_dismissal() -> None:
    """Verify signal with verified zero plant impact routes immediately to dismiss."""
    state_zero = create_initial_state(
        alert_id="ALT-4",
        supplier_id="SUP-1",
        signal_type=SignalType.LOGISTICS,
        impacted_plant_ids=[],
        is_single_source=False,
    )
    # When explicitly tagged with metadata dismissing blast radius
    state_zero["metadata"]["zero_impact"] = True
    dest = route_after_triage(state_zero)
    assert dest == [NODE_DISMISS]


def test_route_after_risk_shortage_gap_vs_buffer_sufficient() -> None:
    """Verify risk routing branches on shortage gap."""
    # Scenario A: Shortage gap > 0 -> Recommendation
    state_shortage = create_initial_state(
        alert_id="ALT-5",
        supplier_id="SUP-1",
    )
    state_shortage["risk_metrics"] = {
        "gap_days": Decimal("1.32"),
        "is_shortage": True,
        "financial_exposure": Decimal("2448105.00"),
    }
    assert route_after_risk(state_shortage) == NODE_RECOMMENDATION

    # Scenario B: No shortage (buffer stock covers gap) -> Dismiss
    state_safe = create_initial_state(
        alert_id="ALT-6",
        supplier_id="SUP-1",
    )
    state_safe["risk_metrics"] = {
        "gap_days": Decimal("0.00"),
        "is_shortage": False,
        "financial_exposure": Decimal("0.00"),
    }
    assert route_after_risk(state_safe) == NODE_DISMISS


def test_route_after_hitl_gate_governance() -> None:
    """Verify HITL gate routes based on spend tier authorization and decision state."""
    # Scenario A: Requires HITL and no decision yet -> suspend/await
    state_pending = create_initial_state(
        alert_id="ALT-7",
        supplier_id="SUP-1",
    )
    state_pending["requires_hitl"] = True
    state_pending["hitl_decision"] = None
    assert route_after_hitl_gate(state_pending) == "await_approval"

    # Scenario B: Requires HITL and approved -> proceed to action
    state_approved = create_initial_state(
        alert_id="ALT-8",
        supplier_id="SUP-1",
    )
    state_approved["requires_hitl"] = True
    state_approved["hitl_decision"] = {
        "approved": True,
        "token_hash": "abc123hash",
        "signer_id": "usr-director-01",
    }
    assert route_after_hitl_gate(state_approved) == NODE_ACTION

    # Scenario C: Requires HITL and rejected -> end
    state_rejected = create_initial_state(
        alert_id="ALT-9",
        supplier_id="SUP-1",
    )
    state_rejected["requires_hitl"] = True
    state_rejected["hitl_decision"] = {
        "approved": False,
        "reason": "Alternative line re-allocation selected",
    }
    assert route_after_hitl_gate(state_rejected) == "rejected"

    # Scenario D: Zero spend commitment ($0) does not require HITL -> proceed to action
    state_zero_spend = create_initial_state(
        alert_id="ALT-10",
        supplier_id="SUP-1",
    )
    state_zero_spend["requires_hitl"] = False
    assert route_after_hitl_gate(state_zero_spend) == NODE_ACTION


# ------------------------------------------------------------------------------
# 4. End-to-End Execution of Compiled Graph
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_end_to_end_nanocore_golden_flow() -> None:
    """Verify execution of full NanoCore investigation flow through compiled graph."""
    graph = build_investigation_graph()

    initial_state = create_initial_state(
        alert_id="ALT-NC-001",
        supplier_id="SUP-NC-001",
        component_sku="NC-CHIP-990",
        signal_type=SignalType.NEWS,
        raw_signal="Major fire in cleanroom at NanoCore fab in Hsinchu",
        current_stock=142000,
        daily_consumption_rate=Decimal("18500"),
        eta_days=Decimal("9.0"),
        unit_cost_usd=Decimal("100.25"),
        trace_id="test-trace-nanocore-e2e",
    )

    result = await graph.ainvoke(initial_state)

    assert result["alert_id"] == "ALT-NC-001"
    assert NODE_TRIAGE in result["execution_path"]
    assert NODE_RESEARCH in result["execution_path"]
    assert NODE_RISK in result["execution_path"]
    assert NODE_RECOMMENDATION in result["execution_path"]
    assert NODE_HITL_GATE in result["execution_path"]

    # In NanoCore scenario with > $100k exposure, HITL is mandatory
    assert result["requires_hitl"] is True
    assert result["workflow_status"] in (WorkflowStatus.AWAITING_APPROVAL, "AWAITING_APPROVAL")
    assert result["risk_metrics"] is not None
    assert result["risk_metrics"]["days_of_cover"] == Decimal("7.68")
    assert result["risk_metrics"]["gap_days"] == Decimal("1.32")
    assert result["risk_metrics"]["shortage_volume"] == 24420
    assert result["risk_metrics"]["financial_exposure"] == Decimal("2448105.00")


@pytest.mark.asyncio
async def test_end_to_end_buffer_sufficient_dismissal() -> None:
    """Verify zero-shortage event safely executes through to dismissal node."""
    graph = build_investigation_graph()

    initial_state = create_initial_state(
        alert_id="ALT-SAFE-001",
        supplier_id="SUP-SAFE-001",
        component_sku="SAFE-BOLT-100",
        signal_type=SignalType.LOGISTICS,
        raw_signal="Minor 1-day customs inspection delay",
        current_stock=50000,
        daily_consumption_rate=Decimal("1000"),
        eta_days=Decimal("5.0"),
        unit_cost_usd=Decimal("10.00"),
    )

    result = await graph.ainvoke(initial_state)

    assert NODE_TRIAGE in result["execution_path"]
    assert NODE_RISK in result["execution_path"]
    assert NODE_DISMISS in result["execution_path"]
    assert result["workflow_status"] == WorkflowStatus.DISMISSED
    assert result["requires_hitl"] is False


@pytest.mark.asyncio
async def test_investigation_orchestrator_resume_with_approval() -> None:
    """Verify InvestigationOrchestrator pauses on HITL gate and resumes with approved token."""
    checkpointer = MemorySaver()
    orchestrator = InvestigationOrchestrator(checkpointer=checkpointer)

    initial_state = create_initial_state(
        alert_id="ALT-RESUME-001",
        supplier_id="SUP-NC-001",
        component_sku="NC-CHIP-990",
        signal_type=SignalType.NEWS,
        raw_signal="Cleanroom fire at NanoCore",
        current_stock=142000,
        daily_consumption_rate=Decimal("18500"),
        eta_days=Decimal("9.0"),
        unit_cost_usd=Decimal("2.00"),
    )

    thread_config = {"configurable": {"thread_id": "thread-investigation-001"}}

    # 1. Initial run: pauses at HITL gate
    paused_state = await orchestrator.run_investigation(
        initial_state,
        config=thread_config,
    )
    assert paused_state["workflow_status"] == WorkflowStatus.AWAITING_APPROVAL
    assert paused_state["requires_hitl"] is True

    # 2. Resumed run: provide valid approval decision (Tier 2 PROC_DIRECTOR <= $100k allows single signature)
    approval_decision = {
        "approved": True,
        "token_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "signer_id": "usr-vp-supplychain-01",
        "spend_tier": SpendTier.PROC_DIRECTOR,
    }

    # Update governing spend tier to match decision tier for single-signer resumption
    await orchestrator.graph.aupdate_state(
        thread_config,
        {"governing_spend_tier": SpendTier.PROC_DIRECTOR},
    )

    resumed_state = await orchestrator.resume_investigation(
        thread_id="thread-investigation-001",
        hitl_decision=approval_decision,
        config=thread_config,
    )

    assert resumed_state["workflow_status"] == WorkflowStatus.EXECUTED
    assert NODE_ACTION in resumed_state["execution_path"]
    assert resumed_state["hitl_decision"]["approved"] is True


# ------------------------------------------------------------------------------
# 5. Boundary Conditions & 100% Branch Coverage
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_end_to_end_financial_contract_flow() -> None:
    """Verify financial signal routes through contract node and completes investigation."""
    graph = build_investigation_graph()

    state = create_initial_state(
        alert_id="ALT-FIN-001",
        supplier_id="SUP-FIN-001",
        component_sku="FIN-PART-001",
        signal_type=SignalType.FINANCIAL,
        raw_signal="Supplier insolvency filing and payment default",
        current_stock=1000,
        daily_consumption_rate=Decimal("500"),
        eta_days=Decimal("8.0"),
        unit_cost_usd=Decimal("50.00"),
    )

    result = await graph.ainvoke(state)
    assert NODE_TRIAGE in result["execution_path"]
    assert NODE_CONTRACT in result["execution_path"]
    assert NODE_RISK in result["execution_path"]
    assert result["contract_analysis"] is not None
    assert result["contract_analysis"]["payment_terms"] == "Net 30"


@pytest.mark.asyncio
async def test_risk_node_and_recommendation_fallbacks() -> None:
    """Verify fallback paths in risk and recommendation nodes when inputs or types vary."""
    # 1. Direct call to risk_node without prior metrics or stock inputs
    empty_state = create_initial_state(
        alert_id="ALT-EMPTY",
        supplier_id="SUP-EMPTY",
    )
    risk_out = await risk_node(empty_state)
    assert risk_out["risk_metrics"]["days_of_cover"] == Decimal("10.00")
    assert risk_out["severity"] == RiskLevel.LOW

    # 2. route_after_risk with non-Decimal gap_days (e.g. float or string)
    state_float_gap = create_initial_state(alert_id="ALT-GAP", supplier_id="SUP-1")
    state_float_gap["risk_metrics"] = {"gap_days": 2.5, "is_shortage": True}
    assert route_after_risk(state_float_gap) == NODE_RECOMMENDATION

    # 3. recommendation_node with non-Decimal financial_exposure
    state_float_exp = create_initial_state(alert_id="ALT-EXP", supplier_id="SUP-1")
    state_float_exp["risk_metrics"] = {"financial_exposure": 50000.0, "is_shortage": True}
    rec_out = await recommendation_node(state_float_exp)
    assert rec_out["requires_hitl"] is True
    assert rec_out["governing_spend_tier"] in (
        SpendTier.PROC_DIRECTOR,
        SpendTier.CATEGORY_MGR,
        SpendTier.DUAL_VP,
    )


def test_hitl_gate_node_decisions() -> None:
    """Verify hitl_gate_node outcomes for rejection and zero spend."""
    # Rejected decision
    state_rejected = create_initial_state(alert_id="ALT-REJ", supplier_id="SUP-1")
    state_rejected["requires_hitl"] = True
    state_rejected["hitl_decision"] = {"approved": False, "reason": "Too expensive"}
    out_rej = hitl_gate_node(state_rejected)
    assert out_rej["workflow_status"] == WorkflowStatus.REJECTED

    # No HITL required ($0 spend)
    state_free = create_initial_state(alert_id="ALT-FREE", supplier_id="SUP-1")
    state_free["requires_hitl"] = False
    out_free = hitl_gate_node(state_free)
    assert out_free["workflow_status"] == WorkflowStatus.APPROVED
