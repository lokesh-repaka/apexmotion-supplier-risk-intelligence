"""Unit tests for Recommendation Agent Node (P9-6).

Enforces:
- The Triad of Responsibility (BR-RULE-001):
  * Probabilistic AI proposes mitigation scenarios, but is STRICTLY FORBIDDEN from auto-approving
    or executing financial commitments.
  * Any mitigation scenario with financial spend (estimated_cost_usd > $0.00) MANDATES
    human-in-the-loop authorization (requires_hitl=True).
  * Spend governance tiers strictly map:
    - Spend <= $25,000 -> Category Manager (1x token, 1-hr TTL).
    - Spend $25,001 - $100,000 -> Procurement Director (1x token, 1-hr TTL).
    - Spend > $100,000 -> Dual Sign-Off (Procurement Director + VP Supply Chain, 30-min TTL).
  * Exact Decimal arithmetic for all costs, avoided losses, and net financial benefits:
    net_financial_benefit_usd == avoided_loss_usd - estimated_cost_usd.
- Structured LLM Output Schema:
  * Uses LiteLLMGateway (TaskType.SYNTHESIS) with RecommendationReport response model.
  * Rejects free-text and malformed outputs.
- Resilient Fallback:
  * Deterministic rule-based mitigation options generated on LLM provider failure or timeout.
- StateGraph Integration:
  * Full async node entrypoint recommendation_node conforming to SupplierRiskState channels.
  * Thread-safe singleton accessor get_recommendation_agent().
"""

import threading
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.agents.graph import (
    NODE_ACTION,
    NODE_DISMISS,
    NODE_HITL_GATE,
    NODE_RECOMMENDATION,
    NODE_RESEARCH,
    NODE_RISK,
    NODE_TRIAGE,
    build_investigation_graph,
)
from src.agents.nodes.recommendation_agent import (
    RecommendationAgent,
    get_recommendation_agent,
    recommendation_node,
)
from src.agents.state import (
    SupplierRiskState,
    WorkflowStatus,
    create_initial_state,
)
from src.core.hitl_tokens import SpendTier
from src.kafka.schemas.risk_alert import RiskLevel
from src.llm.gateway import LLMResponse
from src.llm.models import (
    MitigationScenario,
    MitigationStrategyType,
    RecommendationReport,
)


@pytest.fixture
def nanocore_risk_state() -> SupplierRiskState:
    """Standardized NanoCore reference state with computed risk metrics."""
    state = create_initial_state(
        alert_id="ALT-2026-NC-001",
        supplier_id="SUP-NC-001",
        supplier_name="NanoCore Semiconductor Corp",
        component_sku="SKU-MCU-4402",
        signal_type="news",
        raw_signal="Cleanroom fire at Hsinchu Fab 2 halts MCU-X91 production.",
        current_stock=142000,
        daily_consumption_rate=Decimal("18500"),
        eta_days=Decimal("9.0"),
        unit_cost_usd=Decimal("100.25"),
        impacted_plant_ids=["PLT-MUC-01", "PLT-LEP-02"],
        is_single_source=True,
    )
    state["risk_metrics"] = {
        "days_of_cover": Decimal("7.68"),
        "gap_days": Decimal("1.32"),
        "shortage_volume": 24420,
        "financial_exposure": Decimal("2448105.00"),
        "factory_halt_exposure": Decimal("2692800.00"),
        "total_exposure": Decimal("5140905.00"),
        "is_shortage": True,
        "calculation_hash": "hash-nc-001",
    }
    state["severity"] = RiskLevel.CRITICAL
    state["research_analysis"] = {
        "findings": ["Cleanroom fire confirmed at Fab 2.", "Estimated 2-3 week outage."]
    }
    state["contract_analysis"] = {
        "clauses": [
            {
                "clause_type": "FORCE_MAJEURE",
                "content": "Fire constitutes force majeure relieving supplier of late delivery penalties.",
            }
        ]
    }
    state["narrative"] = (
        "Critical MCU-X91 shortage threatens immediate line halt across Munich and Leipzig."
    )
    return state


# ------------------------------------------------------------------------------
# 1. Golden Reference & Scenario Generation Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recommendation_agent_nanocore_golden_scenarios(
    nanocore_risk_state: SupplierRiskState,
) -> None:
    """Verify recommendation agent generates ranked mitigation scenarios for NanoCore reference case."""
    agent = RecommendationAgent()
    report = await agent.arecommend(nanocore_risk_state)

    assert isinstance(report, RecommendationReport)
    assert report.alert_id == "ALT-2026-NC-001"
    assert report.supplier_id == "SUP-NC-001"
    assert report.component_sku == "SKU-MCU-4402"
    assert len(report.scenarios) >= 2

    # Scenarios must contain the recommended scenario
    scenario_ids = [s.scenario_id for s in report.scenarios]
    assert report.recommended_scenario_id in scenario_ids

    # Top scenario validation
    top_scenario = next(
        s for s in report.scenarios if s.scenario_id == report.recommended_scenario_id
    )
    assert top_scenario.estimated_cost_usd > Decimal("0.00")
    assert top_scenario.avoided_loss_usd > Decimal("0.00")
    assert (
        top_scenario.net_financial_benefit_usd
        == top_scenario.avoided_loss_usd - top_scenario.estimated_cost_usd
    )

    # Must require HITL authorization and reflect governing spend tier
    assert report.requires_hitl is True
    assert report.governing_spend_tier in (SpendTier.DUAL_VP, SpendTier.PROC_DIRECTOR)
    assert len(report.justification) >= 10


# ------------------------------------------------------------------------------
# 2. The Triad of Responsibility & Anti-Auto-Approval Invariants (BR-RULE-001)
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_triad_never_auto_approves_consequential_spend(
    nanocore_risk_state: SupplierRiskState,
) -> None:
    """Verify that any scenario with positive spend strictly mandates human approval and cannot auto-execute."""
    agent = RecommendationAgent()

    # Even if mock gateway returned a payload with requires_hitl=False, the agent/model must enforce requires_hitl=True
    report = await agent.arecommend(nanocore_risk_state)

    assert report.requires_hitl is True
    assert any(s.estimated_cost_usd > Decimal("0.00") for s in report.scenarios)

    # Node execution output must be in PLANNING status, never EXECUTED or APPROVED
    node_output = await recommendation_node(nanocore_risk_state)
    assert node_output["workflow_status"] == WorkflowStatus.PLANNING
    assert node_output["requires_hitl"] is True
    assert node_output["current_node"] == NODE_RECOMMENDATION


@pytest.mark.asyncio
async def test_recommendation_agent_zero_cost_buffer_depletion() -> None:
    """Verify zero-cost mitigation options (e.g. buffer depletion) correctly calculate tiers."""
    state = create_initial_state(
        alert_id="ALT-ZERO-001",
        supplier_id="SUP-GEN-001",
        supplier_name="Generic Supplier",
        component_sku="SKU-BOLT-100",
        current_stock=50000,
        daily_consumption_rate=Decimal("1000"),
        eta_days=Decimal("2.0"),
        unit_cost_usd=Decimal("1.50"),
    )
    state["risk_metrics"] = {
        "days_of_cover": Decimal("50.00"),
        "gap_days": Decimal("0.00"),
        "shortage_volume": 0,
        "financial_exposure": Decimal("0.00"),
        "factory_halt_exposure": Decimal("0.00"),
        "total_exposure": Decimal("0.00"),
        "is_shortage": False,
    }

    mock_report = RecommendationReport(
        alert_id="ALT-ZERO-001",
        component_sku="SKU-BOLT-100",
        supplier_id="SUP-GEN-001",
        scenarios=[
            MitigationScenario(
                scenario_id="SCEN-ZERO-1",
                title="Internal Safety Buffer Depletion",
                strategy_type=MitigationStrategyType.BUFFER_DEPLETION,
                description="Draw down safety buffer from warehouse B with zero external financial spend.",
                estimated_cost_usd=Decimal("0.00"),
                avoided_loss_usd=Decimal("5000.00"),
                net_financial_benefit_usd=Decimal("5000.00"),
                implementation_lead_time_days=Decimal("0.5"),
                lead_time_reduction_days=Decimal("0.5"),
                feasibility_score=0.99,
                required_spend_tier=SpendTier.CATEGORY_MGR,
                target_supplier_id="SUP-GEN-001",
                target_sku="SKU-BOLT-100",
                target_plant_id="PLT-MUC-01",
                action_type="DEPLETE_INTERNAL_BUFFER",
                risk_notes=["Buffer level reduced to 3 days."],
            )
        ],
        recommended_scenario_id="SCEN-ZERO-1",
        justification="Zero cost buffer reallocation provides adequate coverage without commercial commitments.",
        requires_hitl=False,
        governing_spend_tier=SpendTier.CATEGORY_MGR,
    )

    mock_gateway = MagicMock()
    mock_gateway.acomplete = AsyncMock(
        return_value=LLMResponse(
            content=mock_report.model_dump_json(),
            model="mock-claude-3-5-sonnet",
            prompt_tokens=100,
            completion_tokens=100,
            total_tokens=200,
            cost_usd=Decimal("0.001"),
        )
    )

    agent = RecommendationAgent(gateway=mock_gateway)
    report = await agent.arecommend(state)

    assert report.requires_hitl is False
    assert report.scenarios[0].estimated_cost_usd == Decimal("0.00")
    assert report.scenarios[0].net_financial_benefit_usd == Decimal("5000.00")


# ------------------------------------------------------------------------------
# 3. Spend Tier Threshold & Mapping Tests
# ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cost_str", "expected_tier"),
    [
        ("15000.00", SpendTier.CATEGORY_MGR),  # <= $25k
        ("25000.00", SpendTier.CATEGORY_MGR),  # == $25k boundary
        ("25001.00", SpendTier.PROC_DIRECTOR),  # > $25k and <= $100k
        ("75000.00", SpendTier.PROC_DIRECTOR),  # midpoint
        ("100000.00", SpendTier.PROC_DIRECTOR),  # == $100k boundary
        ("100001.00", SpendTier.DUAL_VP),  # > $100k
        ("285000.00", SpendTier.DUAL_VP),  # high value dual sign-off
    ],
)
def test_recommendation_agent_spend_tier_resolution(
    cost_str: str, expected_tier: SpendTier
) -> None:
    """Verify mitigation scenario costs map deterministically to correct HITL spend tiers."""
    cost = Decimal(cost_str)
    tier = RecommendationAgent.resolve_spend_tier(cost)
    assert tier == expected_tier


# ------------------------------------------------------------------------------
# 4. Deterministic Fallback on LLM Failure Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recommendation_agent_deterministic_fallback_on_llm_failure(
    nanocore_risk_state: SupplierRiskState,
) -> None:
    """Verify deterministic fallback formulation activates on LLM provider exceptions or timeouts."""
    mock_gateway = MagicMock()
    mock_gateway.acomplete.side_effect = TimeoutError("Bedrock service timeout after 30s")

    agent = RecommendationAgent(gateway=mock_gateway)
    report = await agent.arecommend(nanocore_risk_state)

    assert isinstance(report, RecommendationReport)
    assert report.alert_id == "ALT-2026-NC-001"
    assert report.supplier_id == "SUP-NC-001"
    assert len(report.scenarios) >= 2

    # Scenarios must have valid Decimal values
    for sc in report.scenarios:
        assert sc.net_financial_benefit_usd == sc.avoided_loss_usd - sc.estimated_cost_usd
        assert sc.feasibility_score >= 0.0
        assert sc.required_spend_tier in (
            SpendTier.CATEGORY_MGR,
            SpendTier.PROC_DIRECTOR,
            SpendTier.DUAL_VP,
        )

    assert report.requires_hitl is True
    assert report.governing_spend_tier == SpendTier.DUAL_VP
    assert "deterministic fallback" in report.justification.lower()


@pytest.mark.asyncio
async def test_recommendation_agent_fallback_with_empty_metrics() -> None:
    """Verify fallback formulation functions safely when risk_metrics are missing or empty."""
    empty_state = create_initial_state(
        alert_id="ALT-EMPTY-001",
        supplier_id="SUP-UNKNOWN",
    )

    mock_gateway = MagicMock()
    mock_gateway.acomplete.side_effect = RuntimeError("Service Unavailable")

    agent = RecommendationAgent(gateway=mock_gateway)
    report = await agent.arecommend(empty_state)

    assert isinstance(report, RecommendationReport)
    assert report.supplier_id == "SUP-UNKNOWN"
    assert len(report.scenarios) >= 1
    assert report.requires_hitl is True


# ------------------------------------------------------------------------------
# 5. Synchronous & Asynchronous Interface Parity
# ------------------------------------------------------------------------------


def test_recommendation_agent_sync_recommend(nanocore_risk_state: SupplierRiskState) -> None:
    """Verify synchronous recommend() produces identical schema output via complete()."""
    agent = RecommendationAgent()
    report = agent.recommend(nanocore_risk_state)

    assert isinstance(report, RecommendationReport)
    assert report.alert_id == "ALT-2026-NC-001"
    assert len(report.scenarios) >= 1
    assert report.requires_hitl is True


def test_recommendation_agent_sync_fallback_on_error(
    nanocore_risk_state: SupplierRiskState,
) -> None:
    """Verify sync recommend() gracefully falls back when gateway.complete() raises."""
    mock_gateway = MagicMock()
    mock_gateway.complete.side_effect = ConnectionError("Mock gateway connection refused")

    agent = RecommendationAgent(gateway=mock_gateway)
    report = agent.recommend(nanocore_risk_state)

    assert isinstance(report, RecommendationReport)
    assert len(report.scenarios) >= 2
    assert report.requires_hitl is True


# ------------------------------------------------------------------------------
# 6. Singleton & Thread-Safety Tests
# ------------------------------------------------------------------------------


def test_get_recommendation_agent_singleton() -> None:
    """Verify get_recommendation_agent returns a thread-safe singleton instance."""
    agent1 = get_recommendation_agent()
    agent2 = get_recommendation_agent()
    assert agent1 is agent2
    assert isinstance(agent1, RecommendationAgent)


def test_get_recommendation_agent_thread_safe_initialization() -> None:
    """Verify concurrent instantiation creates exactly one singleton instance."""
    import src.agents.nodes.recommendation_agent as mod

    with mod._recommendation_agent_lock:
        mod._recommendation_agent_instance = None

    instances: list[RecommendationAgent] = []

    def _worker() -> None:
        inst = get_recommendation_agent()
        instances.append(inst)

    threads = [threading.Thread(target=_worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(instances) == 10
    assert all(inst is instances[0] for inst in instances)


def test_get_recommendation_agent_race_lock_coverage() -> None:
    """Simulate race conditions inside the double-checked lock to achieve 100% branch coverage."""
    import src.agents.nodes.recommendation_agent as mod

    created_inst = RecommendationAgent()

    class RaceLock:
        def __enter__(self) -> "RaceLock":
            mod._recommendation_agent_instance = created_inst
            return self

        def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            pass

    with mod._recommendation_agent_lock:
        mod._recommendation_agent_instance = None

    with patch.object(mod, "_recommendation_agent_lock", RaceLock()):
        inst = get_recommendation_agent()
        assert inst is created_inst


# ------------------------------------------------------------------------------
# 7. LangGraph recommendation_node State Transformation Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recommendation_node_state_transformation(
    nanocore_risk_state: SupplierRiskState,
) -> None:
    """Verify recommendation_node updates state channels with recommendations, spend tier, and audit events."""
    output = await recommendation_node(nanocore_risk_state)

    assert output["current_node"] == NODE_RECOMMENDATION
    assert output["execution_path"] == [NODE_RECOMMENDATION]
    assert output["workflow_status"] == WorkflowStatus.PLANNING
    assert isinstance(output["recommendations"], list)
    assert len(output["recommendations"]) >= 2
    assert output["recommended_action_id"] is not None
    assert output["requires_hitl"] is True
    assert output["governing_spend_tier"] in (SpendTier.DUAL_VP, SpendTier.PROC_DIRECTOR)

    # Audit events
    audit_events = output["audit_events"]
    assert len(audit_events) == 1
    event = audit_events[0]
    assert event["action"] == "RECOMMENDATION_FORMULATION_COMPLETED"
    assert event["alert_id"] == "ALT-2026-NC-001"
    assert event["supplier_id"] == "SUP-NC-001"
    assert event["recommended_action_id"] == output["recommended_action_id"]
    assert event["requires_hitl"] is True
    assert event["scenarios_count"] == len(output["recommendations"])


@pytest.mark.asyncio
async def test_recommendation_node_handles_non_decimal_exposure() -> None:
    """Verify recommendation_node gracefully coerces float or string exposures in state."""
    state = create_initial_state(alert_id="ALT-FLOAT-001", supplier_id="SUP-FLOAT-001")
    state["risk_metrics"] = {
        "financial_exposure": 50000.0,
        "is_shortage": True,
        "gap_days": 2.0,
    }

    output = await recommendation_node(state)
    assert output["requires_hitl"] is True
    assert output["governing_spend_tier"] in (
        SpendTier.PROC_DIRECTOR,
        SpendTier.CATEGORY_MGR,
        SpendTier.DUAL_VP,
    )


@pytest.mark.asyncio
async def test_recommendation_agent_coerces_halt_and_total_exposure_in_prompt() -> None:
    """Verify prompt builder coerces non-Decimal factory halt and total exposures."""
    state = create_initial_state(alert_id="ALT-COERCE-001", supplier_id="SUP-COERCE-001")
    state["risk_metrics"] = {
        "financial_exposure": 50000.0,
        "factory_halt_exposure": 85000.0,
        "total_exposure": "135000.00",
        "is_shortage": True,
        "gap_days": 1.5,
    }

    agent = RecommendationAgent()
    report = await agent.arecommend(state)
    assert isinstance(report, RecommendationReport)
    assert report.requires_hitl is True


def test_recommendation_agent_fallback_moderate_exposure_branches() -> None:
    """Verify fallback branches when exposure triggers spot and freight minimum thresholds."""
    state = create_initial_state(alert_id="ALT-MOD-001", supplier_id="SUP-MOD-001")
    state["risk_metrics"] = {
        "financial_exposure": Decimal("20000.00"),
        "factory_halt_exposure": Decimal("0.00"),
        "is_shortage": True,
        "gap_days": Decimal("1.0"),
    }

    agent = RecommendationAgent()
    report = agent._generate_fallback_recommendations(state)
    assert report.scenarios[0].estimated_cost_usd == Decimal("15000.00")
    assert report.scenarios[1].estimated_cost_usd == Decimal("12000.00")
    assert report.requires_hitl is True


@pytest.mark.asyncio
async def test_recommendation_agent_fallback_when_llm_violates_hitl_rule(
    nanocore_risk_state: SupplierRiskState,
) -> None:
    """Verify that if LLM returns requires_hitl=false for positive spend, parser rejects it and fallback kicks in."""
    invalid_json = """{
      "alert_id": "ALT-2026-NC-001",
      "component_sku": "SKU-MCU-4402",
      "supplier_id": "SUP-NC-001",
      "scenarios": [
        {
          "scenario_id": "SCEN-INVALID-01",
          "title": "Bypassing spend gate",
          "strategy_type": "SPOT_PURCHASE",
          "description": "Unauthorized spend attempt bypassing human authorization gate.",
          "estimated_cost_usd": "50000.00",
          "avoided_loss_usd": "200000.00",
          "net_financial_benefit_usd": "150000.00",
          "implementation_lead_time_days": "1.0",
          "lead_time_reduction_days": "1.0",
          "feasibility_score": 0.9,
          "required_spend_tier": "PROC_DIRECTOR",
          "target_sku": "SKU-MCU-4402",
          "target_plant_id": "PLT-MUC-01",
          "action_type": "DISPATCH_SECONDARY_PO"
        }
      ],
      "recommended_scenario_id": "SCEN-INVALID-01",
      "justification": "Bypassing human authorization illegally.",
      "requires_hitl": false,
      "governing_spend_tier": "PROC_DIRECTOR"
    }"""

    mock_gateway = MagicMock()
    mock_gateway.acomplete = AsyncMock(
        return_value=LLMResponse(
            content=invalid_json,
            model="mock-claude-3-5-sonnet",
            prompt_tokens=100,
            completion_tokens=100,
            total_tokens=200,
            cost_usd=Decimal("0.001"),
        )
    )

    agent = RecommendationAgent(gateway=mock_gateway)
    report = await agent.arecommend(nanocore_risk_state)

    # Must engage deterministic fallback with requires_hitl=True
    assert report.requires_hitl is True
    assert "deterministic fallback" in report.justification.lower()


# ------------------------------------------------------------------------------
# 8. End-to-End StateGraph Integration Test
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compiled_stategraph_executes_real_recommendation_node() -> None:
    """Verify compiled StateGraph traverses triage -> research -> risk -> recommendation -> hitl_gate.

    Because requires_hitl=True and no decision exists, it must suspend at AWAITING_APPROVAL and end at END.
    """
    graph = build_investigation_graph()

    initial_state = create_initial_state(
        alert_id="ALT-2026-NC-E2E",
        supplier_id="SUP-NC-001",
        supplier_name="NanoCore Semiconductor Corp",
        component_sku="SKU-MCU-4402",
        signal_type="news",
        raw_signal="Fab 2 cleanroom fire halts microcontroller packaging.",
        current_stock=142000,
        daily_consumption_rate=Decimal("18500"),
        eta_days=Decimal("9.0"),
        unit_cost_usd=Decimal("100.25"),
        impacted_plant_ids=["PLT-MUC-01"],
        is_single_source=True,
    )

    final_state = await graph.ainvoke(initial_state)

    path = final_state["execution_path"]
    assert NODE_TRIAGE in path
    assert NODE_RESEARCH in path
    assert NODE_RISK in path
    assert NODE_RECOMMENDATION in path
    assert NODE_HITL_GATE in path
    assert NODE_ACTION not in path  # Must not auto-execute
    assert NODE_DISMISS not in path

    # HITL gate must pause workflow awaiting human decision
    assert final_state["workflow_status"] == WorkflowStatus.AWAITING_APPROVAL
    assert final_state["requires_hitl"] is True
    assert final_state["governing_spend_tier"] in (SpendTier.DUAL_VP, SpendTier.PROC_DIRECTOR)
    assert final_state["recommendations"] is not None
    assert len(final_state["recommendations"]) >= 1
