"""Unit tests for Risk Agent Node & Narrative Synthesis (P9-5).

Verifies:
- The Triad of Responsibility (BR-RULE-001):
  * 100% of arithmetic calculations (Days of Cover, Coverage Gap, Shortage Volume, Financial Exposure, Factory Halt)
    run strictly in pure deterministic Python via RiskCalculator and RiskScorer.
  * LLMs are STRICTLY FORBIDDEN from performing any arithmetic.
  * Strict Decimal precision (NUMERIC(14,2)) for all monetary and inventory numbers.
  * Canonical NanoCore Golden Scenario asserts days_of_cover=7.68, gap_days=1.32, shortage_volume=24420,
    financial_exposure=2448105.00, factory_halt_exposure=2692800.00, total_exposure=5140905.00, severity=CRITICAL.
- Pydantic v2 Structured Output Validation (P8-3):
  * LLM synthesis strictly produces typed RiskNarrative models.
  * Verifies executive_summary, root_cause_analysis, operational_impact, runway_and_exposure_commentary.
- Deterministic Fallback Synthesis:
  * Gracefully degrades to deterministic RiskNarrative on LLM timeout or service degradation.
- Edge Case & Inventory Boundary Handling:
  * Zero stock -> immediate shortage.
  * Zero consumption rate -> capped at 999.00 days.
  * Buffer stock sufficient (ETA <= cover) -> gap=0, exposure=0, routes to dismiss.
- LangGraph State Machine Integration:
  * risk_node integrates into compiled StateGraph DAG.
  * State transformation conforms to SupplierRiskState with operator.add reducers.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from src.agents.graph import (
    NODE_DISMISS,
    NODE_HITL_GATE,
    NODE_RECOMMENDATION,
    NODE_RESEARCH,
    NODE_RISK,
    NODE_TRIAGE,
    build_investigation_graph,
)
from src.agents.nodes.risk_agent import (
    RiskAgent,
    get_risk_agent,
    risk_node,
)
from src.agents.state import (
    SignalType,
    WorkflowStatus,
    create_initial_state,
)
from src.kafka.schemas.risk_alert import RiskLevel
from src.llm.gateway import LLMTimeoutError
from src.llm.models import RiskNarrative

# ------------------------------------------------------------------------------
# 1. Deterministic Arithmetic & Golden Scenario Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_risk_agent_nanocore_golden_metrics_and_narrative() -> None:
    """Verify RiskAgent computes canonical NanoCore golden numbers and generates valid narrative."""
    agent = RiskAgent()
    state = create_initial_state(
        alert_id="ALT-NC-001",
        supplier_id="SUP-NC-001",
        supplier_name="NanoCore Semiconductor",
        component_sku="NC-CHIP-990",
        signal_type=SignalType.NEWS,
        raw_signal="Cleanroom facility fire reported at NanoCore fab",
        current_stock=142000,
        daily_consumption_rate=Decimal("18500"),
        eta_days=Decimal("9.0"),
        unit_cost_usd=Decimal("100.25"),
        impacted_plant_ids=["PLT-MUC-01"],
        is_single_source=True,
    )

    metrics, severity, narrative, evidence = await agent.aassess(state)

    # 1. The Triad of Responsibility: Exact Deterministic Math Assertions
    assert metrics["days_of_cover"] == Decimal("7.68")
    assert metrics["gap_days"] == Decimal("1.32")
    assert metrics["shortage_volume"] == 24420
    assert metrics["financial_exposure"] == Decimal("2448105.00")
    assert metrics["factory_halt_exposure"] == Decimal("2692800.00")
    assert metrics["total_exposure"] == Decimal("5140905.00")
    assert metrics["is_shortage"] is True
    assert len(metrics["calculation_hash"]) == 64

    # 2. Deterministic Severity Classification
    assert severity == RiskLevel.CRITICAL

    # 3. Structured RiskNarrative Output
    assert isinstance(narrative, RiskNarrative)
    assert len(narrative.executive_summary) >= 20
    assert len(narrative.root_cause_analysis) >= 20
    assert len(narrative.operational_impact) >= 20
    assert len(narrative.runway_and_exposure_commentary) >= 20
    assert len(evidence) >= 1


@pytest.mark.asyncio
async def test_the_triad_of_separation_llm_zero_arithmetic() -> None:
    """Verify LLM is given pre-computed numbers as context and strictly forbidden from math."""
    agent = RiskAgent()
    state = create_initial_state(
        alert_id="ALT-TRIAD-001",
        supplier_id="SUP-NC-001",
        current_stock=142000,
        daily_consumption_rate=Decimal("18500"),
        eta_days=Decimal("9.0"),
        unit_cost_usd=Decimal("100.25"),
    )

    # Spy on LLM gateway call to verify prompt contents
    with patch.object(agent.gateway, "acomplete", wraps=agent.gateway.acomplete) as mock_complete:
        await agent.aassess(state)
        mock_complete.assert_called_once()
        call_prompt = mock_complete.call_args.kwargs.get("prompt") or mock_complete.call_args[0][0]
        # Must enforce Triad prohibitions in system instructions
        assert "STRICTLY FORBIDDEN from performing any arithmetic" in str(call_prompt)
        assert "7.68" in str(call_prompt)
        assert "24,420" in str(call_prompt) or "24420" in str(call_prompt)
        assert "2,448,105.00" in str(call_prompt) or "2448105.00" in str(call_prompt)


@pytest.mark.asyncio
async def test_risk_agent_buffer_stock_sufficient_low_severity() -> None:
    """Verify zero-shortage event (days_of_cover >= ETA) yields gap=0 and LOW severity."""
    agent = RiskAgent()
    state = create_initial_state(
        alert_id="ALT-SAFE-001",
        supplier_id="SUP-SAFE-001",
        component_sku="SAFE-BOLT-100",
        current_stock=50000,
        daily_consumption_rate=Decimal("1000"),
        eta_days=Decimal("5.0"),
        unit_cost_usd=Decimal("10.00"),
    )

    metrics, severity, narrative, _ = await agent.aassess(state)

    assert metrics["days_of_cover"] == Decimal("50.00")
    assert metrics["gap_days"] == Decimal("0.00")
    assert metrics["shortage_volume"] == 0
    assert metrics["financial_exposure"] == Decimal("0.00")
    assert metrics["is_shortage"] is False
    assert severity == RiskLevel.LOW
    assert isinstance(narrative, RiskNarrative)


@pytest.mark.asyncio
async def test_risk_agent_severity_classification_thresholds() -> None:
    """Verify deterministic severity assignment across boundary conditions."""
    agent = RiskAgent()

    # 1. HIGH severity ($250k < exposure <= $1M)
    state_high = create_initial_state(
        alert_id="ALT-HIGH",
        supplier_id="SUP-1",
        current_stock=1000,
        daily_consumption_rate=Decimal("1000"),
        eta_days=Decimal("5.0"),  # gap = 4 days -> 4,000 units
        unit_cost_usd=Decimal("100.00"),  # exposure = $400,000.00
    )
    _, sev_high, _, _ = await agent.aassess(state_high)
    assert sev_high == RiskLevel.HIGH

    # 2. MEDIUM severity (gap > 0, exposure <= $250k)
    state_medium = create_initial_state(
        alert_id="ALT-MED",
        supplier_id="SUP-2",
        current_stock=1000,
        daily_consumption_rate=Decimal("1000"),
        eta_days=Decimal("2.0"),  # gap = 1 day -> 1,000 units
        unit_cost_usd=Decimal("50.00"),  # exposure = $50,000.00
    )
    _, sev_med, _, _ = await agent.aassess(state_medium)
    assert sev_med == RiskLevel.MEDIUM


@pytest.mark.asyncio
async def test_risk_agent_zero_consumption_rate_cap() -> None:
    """Verify zero daily consumption caps Days of Cover at 999.00 days without division by zero."""
    agent = RiskAgent()
    state = create_initial_state(
        alert_id="ALT-ZERO-BURN",
        supplier_id="SUP-Z",
        current_stock=10000,
        daily_consumption_rate=Decimal("0"),
        eta_days=Decimal("10.0"),
        unit_cost_usd=Decimal("5.00"),
    )

    metrics, severity, _, _ = await agent.aassess(state)
    assert metrics["days_of_cover"] == Decimal("999.00")
    assert metrics["gap_days"] == Decimal("0.00")
    assert metrics["shortage_volume"] == 0
    assert metrics["financial_exposure"] == Decimal("0.00")
    assert severity == RiskLevel.LOW


@pytest.mark.asyncio
async def test_risk_agent_zero_stock_immediate_shortage() -> None:
    """Verify zero on-hand stock yields 0.00 days of cover and immediate coverage gap."""
    agent = RiskAgent()
    state = create_initial_state(
        alert_id="ALT-EMPTY-STOCK",
        supplier_id="SUP-E",
        current_stock=0,
        daily_consumption_rate=Decimal("500"),
        eta_days=Decimal("6.0"),
        unit_cost_usd=Decimal("20.00"),
    )

    metrics, _, _, _ = await agent.aassess(state)
    assert metrics["days_of_cover"] == Decimal("0.00")
    assert metrics["gap_days"] == Decimal("6.00")
    assert metrics["shortage_volume"] == 3000
    assert metrics["financial_exposure"] == Decimal("60000.00")


@pytest.mark.asyncio
async def test_risk_agent_deterministic_fallback_on_llm_failure() -> None:
    """Verify RiskAgent gracefully degrades to deterministic RiskNarrative on LLM failure."""
    agent = RiskAgent()
    state = create_initial_state(
        alert_id="ALT-FALLBACK",
        supplier_id="SUP-FAIL-01",
        supplier_name="Degraded Supplier Corp",
        component_sku="FAIL-SKU-99",
        current_stock=1000,
        daily_consumption_rate=Decimal("500"),
        eta_days=Decimal("6.0"),
        unit_cost_usd=Decimal("10.00"),
    )

    with patch.object(
        agent.gateway,
        "acomplete",
        new=AsyncMock(side_effect=LLMTimeoutError("Bedrock endpoint timed out")),
    ):
        metrics, severity, narrative, evidence = await agent.aassess(state)

        assert isinstance(narrative, RiskNarrative)
        assert "Degraded Supplier Corp" in narrative.executive_summary
        assert len(narrative.executive_summary) >= 20
        assert len(narrative.root_cause_analysis) >= 20
        assert len(narrative.operational_impact) >= 20
        assert len(narrative.runway_and_exposure_commentary) >= 20
        assert len(evidence) >= 1


def test_risk_agent_singleton() -> None:
    """Verify get_risk_agent returns the thread-safe singleton instance."""
    agent_1 = get_risk_agent()
    agent_2 = get_risk_agent()
    assert agent_1 is agent_2

    # Verify double-checked locking race condition branch
    import src.agents.nodes.risk_agent as ra

    ra._risk_agent_instance = None
    original_lock = ra._risk_agent_lock

    class RaceLock:
        def __enter__(self) -> "RaceLock":
            ra._risk_agent_instance = agent_1
            return self

        def __exit__(self, *args: object) -> None:
            pass

    ra._risk_agent_lock = RaceLock()  # type: ignore[assignment]
    try:
        inst = ra.get_risk_agent()
        assert inst is agent_1
    finally:
        ra._risk_agent_lock = original_lock


# ------------------------------------------------------------------------------
# 2. LangGraph Node Integration Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_risk_node_state_transformation() -> None:
    """Verify risk_node transforms SupplierRiskState with expected reducer outputs."""
    state = create_initial_state(
        alert_id="ALT-NODE-001",
        supplier_id="SUP-NC-001",
        supplier_name="NanoCore Semiconductor",
        component_sku="NC-CHIP-990",
        signal_type=SignalType.NEWS,
        current_stock=142000,
        daily_consumption_rate=Decimal("18500"),
        eta_days=Decimal("9.0"),
        unit_cost_usd=Decimal("100.25"),
    )

    result = await risk_node(state)

    assert result["current_node"] == NODE_RISK
    assert result["execution_path"] == [NODE_RISK]
    assert result["workflow_status"] == WorkflowStatus.CALCULATING_RISK

    # Metrics
    assert "risk_metrics" in result
    metrics = result["risk_metrics"]
    assert metrics["days_of_cover"] == Decimal("7.68")
    assert metrics["gap_days"] == Decimal("1.32")
    assert metrics["shortage_volume"] == 24420
    assert metrics["financial_exposure"] == Decimal("2448105.00")

    # Severity & Narrative
    assert result["severity"] == RiskLevel.CRITICAL
    assert "narrative" in result
    assert isinstance(result["narrative"], str)
    assert len(result["narrative"]) >= 20

    # Audit events
    assert "audit_events" in result
    assert len(result["audit_events"]) == 1
    event = result["audit_events"][0]
    assert event["action"] == "RISK_CALCULATION_AND_SYNTHESIS_COMPLETED"
    assert event["supplier_id"] == "SUP-NC-001"
    assert event["severity"] == RiskLevel.CRITICAL.value


@pytest.mark.asyncio
async def test_risk_node_empty_state_fallback() -> None:
    """Verify risk_node gracefully handles empty state without inventory inputs."""
    empty_state = create_initial_state(
        alert_id="ALT-EMPTY",
        supplier_id="SUP-EMPTY",
    )

    result = await risk_node(empty_state)
    assert result["risk_metrics"]["days_of_cover"] == Decimal("10.00")
    assert result["risk_metrics"]["gap_days"] == Decimal("0.00")
    assert result["risk_metrics"]["financial_exposure"] == Decimal("0.00")
    assert result["severity"] == RiskLevel.LOW
    assert len(result["narrative"]) >= 20


def test_risk_agent_sync_assess() -> None:
    """Verify RiskAgent.assess provides synchronous execution path."""
    agent = RiskAgent()
    state = create_initial_state(
        alert_id="ALT-SYNC-001",
        supplier_id="SUP-SYNC-001",
        current_stock=20000,
        daily_consumption_rate=Decimal("1000"),
        eta_days=Decimal("10.0"),
        unit_cost_usd=Decimal("50.00"),
    )
    metrics, severity, narrative, evidence = agent.assess(state)
    assert metrics["days_of_cover"] == Decimal("20.00")
    assert severity == RiskLevel.LOW
    assert isinstance(narrative, RiskNarrative)
    assert len(evidence) >= 1


def test_risk_agent_sync_assess_fallback_on_exception() -> None:
    """Verify RiskAgent.assess falls back gracefully on sync gateway failure."""
    agent = RiskAgent()
    state = create_initial_state(
        alert_id="ALT-SYNC-FAIL",
        supplier_id="SUP-FAIL-02",
        supplier_name="Sync Failing Corp",
        component_sku="SKU-SYNC-FAIL",
    )
    with patch.object(agent.gateway, "complete", side_effect=RuntimeError("Sync LLM unavailable")):
        metrics, severity, narrative, evidence = agent.assess(state)
        assert isinstance(narrative, RiskNarrative)
        assert "Sync Failing Corp" in narrative.executive_summary
        assert len(evidence) >= 1


@pytest.mark.asyncio
async def test_risk_agent_pre_computed_metrics_and_coercion() -> None:
    """Verify normalization and Decimal coercion when state provides existing raw metrics."""
    agent = RiskAgent()
    state = create_initial_state(
        alert_id="ALT-PRE-001",
        supplier_id="SUP-PRE-001",
        eta_days=8.5,  # float eta_days
    )
    # Existing metrics with float/str values
    state["risk_metrics"] = {
        "days_of_cover": 5.5,
        "financial_exposure": "150000.00",
        "gap_days": 2.5,
        "is_shortage": True,
    }

    metrics, severity = agent.calculate_deterministic_metrics(state)
    assert isinstance(metrics["days_of_cover"], Decimal)
    assert metrics["days_of_cover"] == Decimal("5.5")
    assert isinstance(metrics["financial_exposure"], Decimal)
    assert metrics["financial_exposure"] == Decimal("150000.00")
    assert isinstance(metrics["gap_days"], Decimal)
    assert severity == RiskLevel.MEDIUM

    # Also exercise when eta_days is already Decimal
    state["eta_days"] = Decimal("8.5")
    metrics_2, _ = agent.calculate_deterministic_metrics(state)
    assert metrics_2["gap_days"] == Decimal("2.5")


@pytest.mark.asyncio
async def test_risk_agent_with_research_and_contract_context() -> None:
    """Verify prompt synthesis incorporates research and contract evidence when present."""
    agent = RiskAgent()
    state = create_initial_state(
        alert_id="ALT-CTX-001",
        supplier_id="SUP-CTX-001",
        current_stock=10000,
        daily_consumption_rate=Decimal("1000"),
        eta_days=Decimal("15.0"),
        unit_cost_usd=Decimal("20.00"),
        metadata={"factory_halt_cost_per_hour_eur": "95000.00"},
    )
    state["research_analysis"] = {
        "incident_category": "port_congestion",
        "summary": "Container freight delayed at terminal",
        "key_findings": ["Customs inspection backlog", "14-day queue"],
    }
    state["contract_analysis"] = {
        "contract_id": "CTR-CTX-01",
        "payment_terms": "Net 45",
        "notice_period_days": 30,
        "delay_penalty_percentage_per_day": "0.05",
        "force_majeure_clause": "Force majeure clause 10 active",
    }

    metrics, severity, narrative, _ = await agent.aassess(state)
    assert metrics["gap_days"] == Decimal("5.00")
    assert severity in (RiskLevel.HIGH, RiskLevel.MEDIUM)
    assert isinstance(narrative, RiskNarrative)


@pytest.mark.asyncio
async def test_risk_agent_nanocore_partial_defaults() -> None:
    """Verify NanoCore default fallback populates missing individual parameters."""
    agent = RiskAgent()
    state = create_initial_state(
        alert_id="ALT-NC-FULL-DEFAULT",
        supplier_id="SUP-NC-001",
        supplier_name="NanoCore Semiconductor",
    )
    metrics, severity, _, _ = await agent.aassess(state)
    assert metrics["days_of_cover"] == Decimal("7.68")
    assert metrics["gap_days"] == Decimal("1.32")
    assert metrics["shortage_volume"] == 24420
    assert metrics["financial_exposure"] == Decimal("2448105.00")
    assert severity == RiskLevel.CRITICAL

    # Exercise NanoCore when halt_eur is explicitly provided in metadata
    state_halt = create_initial_state(
        alert_id="ALT-NC-HALT",
        supplier_id="SUP-NC-001",
        supplier_name="NanoCore Semiconductor",
        metadata={"factory_halt_cost_per_hour_eur": Decimal("85000.00")},
    )
    m_halt, _, _, _ = await agent.aassess(state_halt)
    assert m_halt["factory_halt_exposure"] == Decimal("2692800.00")


@pytest.mark.asyncio
async def test_compiled_stategraph_executes_real_risk_node_to_recommendation() -> None:
    """Verify compiled StateGraph routes NanoCore through real risk_node to recommendation node."""
    graph = build_investigation_graph()

    state = create_initial_state(
        alert_id="ALT-GRAPH-RISK-001",
        supplier_id="SUP-NC-001",
        supplier_name="NanoCore Semiconductor",
        component_sku="NC-CHIP-990",
        signal_type=SignalType.NEWS,
        raw_signal="Cleanroom fire at NanoCore Semiconductor fab",
        current_stock=142000,
        daily_consumption_rate=Decimal("18500"),
        eta_days=Decimal("9.0"),
        unit_cost_usd=Decimal("100.25"),
    )

    final_state = await graph.ainvoke(state)

    # Path must traverse: triage -> research -> risk -> recommendation -> hitl_gate
    assert NODE_TRIAGE in final_state["execution_path"]
    assert NODE_RESEARCH in final_state["execution_path"]
    assert NODE_RISK in final_state["execution_path"]
    assert NODE_RECOMMENDATION in final_state["execution_path"]
    assert NODE_HITL_GATE in final_state["execution_path"]

    # Assert deterministic numbers
    metrics = final_state["risk_metrics"]
    assert metrics["days_of_cover"] == Decimal("7.68")
    assert metrics["gap_days"] == Decimal("1.32")
    assert metrics["shortage_volume"] == 24420
    assert metrics["financial_exposure"] == Decimal("2448105.00")
    assert final_state["severity"] == RiskLevel.CRITICAL
    assert final_state["narrative"] is not None
    assert final_state["requires_hitl"] is True


@pytest.mark.asyncio
async def test_compiled_stategraph_executes_real_risk_node_to_dismissal() -> None:
    """Verify compiled StateGraph routes buffer-sufficient event through real risk_node to dismiss node."""
    graph = build_investigation_graph()

    state = create_initial_state(
        alert_id="ALT-GRAPH-DISMISS-001",
        supplier_id="SUP-SAFE-001",
        component_sku="SAFE-BOLT-100",
        signal_type=SignalType.LOGISTICS,
        raw_signal="Minor 1-day customs inspection hold",
        current_stock=50000,
        daily_consumption_rate=Decimal("1000"),
        eta_days=Decimal("5.0"),
        unit_cost_usd=Decimal("10.00"),
    )

    final_state = await graph.ainvoke(state)

    # Path must traverse: triage -> research -> risk -> dismiss
    assert NODE_TRIAGE in final_state["execution_path"]
    assert NODE_RESEARCH in final_state["execution_path"]
    assert NODE_RISK in final_state["execution_path"]
    assert NODE_DISMISS in final_state["execution_path"]
    assert final_state["workflow_status"] == WorkflowStatus.DISMISSED
    assert final_state["requires_hitl"] is False
