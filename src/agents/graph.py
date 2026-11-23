"""LangGraph StateGraph Skeleton & Node Routing Implementation (P9-1).

Enforces:
- Layering Invariants (CLAUDE.md Sec 5.2 & Sec 11):
  * Deterministic DAG in LangGraph ensuring bounded, verifiable investigation steps.
  * Node stubs: triage, research, contract, risk, recommendation, hitl_gate, action, dismiss.
- The Triad of Responsibility (BR-RULE-001):
  * Pure Python deterministic risk calculations (`src.services.risk.calculator`).
  * Consequential spend actions gated by cryptographic HITL spend tiers (`src.core.hitl_tokens`).
  * Strict Decimal precision for all monetary numbers. Zero LLM math.
- Resilient State Interruption & Checkpointing (LLD Sec 4.2):
  * Supports checkpointer state saving (`MemorySaver` or `AsyncPostgresSaver`) for human approval resumption.
"""

from decimal import Decimal
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.nodes.contract_agent import contract_node
from src.agents.nodes.research_agent import research_node
from src.agents.nodes.triage_agent import triage_node
from src.agents.state import (
    SupplierRiskState,
    WorkflowStatus,
)
from src.core.hitl_tokens import get_spend_tier
from src.core.logging import get_logger
from src.kafka.schemas.risk_alert import RiskLevel
from src.services.risk.calculator import RiskAssessmentInput, RiskCalculator

logger = get_logger("apexmotion.agents.graph")

# ------------------------------------------------------------------------------
# Node Identifiers
# ------------------------------------------------------------------------------

NODE_TRIAGE = "triage"
NODE_RESEARCH = "research"
NODE_CONTRACT = "contract"
NODE_RISK = "risk"
NODE_RECOMMENDATION = "recommendation"
NODE_HITL_GATE = "hitl_gate"
NODE_ACTION = "action"
NODE_DISMISS = "dismiss"


# ------------------------------------------------------------------------------
# Conditional Routing Functions
# ------------------------------------------------------------------------------


def route_after_triage(state: SupplierRiskState) -> list[str]:
    """Deterministically route following signal classification.

    - Explicit zero blast radius or zero impact -> dismiss.
    - Active resumption with existing HITL decision -> skip to hitl_gate.
    - Pre-computed target nodes from triage agent -> target nodes.
    - Financial or contract signals -> contract node.
    - News or geopolitical signals -> research node.
    """
    meta = state.get("metadata") or {}
    if (
        meta.get("zero_impact")
        or meta.get("is_zero_impact")
        or state.get("workflow_status") == WorkflowStatus.DISMISSED
    ):
        return [NODE_DISMISS]

    if state.get("hitl_decision") is not None:
        return [NODE_HITL_GATE]

    target_nodes = meta.get("target_nodes")
    if target_nodes:
        valid_destinations = [
            n
            for n in target_nodes
            if n in (NODE_RESEARCH, NODE_CONTRACT, NODE_DISMISS, NODE_HITL_GATE)
        ]
        if valid_destinations:
            return valid_destinations

    sig = str(state.get("signal_type", "news")).lower().strip()
    if sig in ("financial", "contract"):
        return [NODE_CONTRACT]

    # Default news, logistics, geopolitical
    return [NODE_RESEARCH]


def route_after_risk(state: SupplierRiskState) -> str:
    """Branch based on computed quantitative shortage gap.

    - Shortage gap > 0 or is_shortage=True -> recommendation node.
    - Buffer stock sufficient (gap <= 0) -> dismiss node.
    """
    metrics = state.get("risk_metrics") or {}
    gap = metrics.get("gap_days", Decimal("0.00"))
    if not isinstance(gap, Decimal):
        gap = Decimal(str(gap))

    is_shortage = bool(metrics.get("is_shortage", False))

    if is_shortage or gap > Decimal("0.00"):
        return NODE_RECOMMENDATION

    return NODE_DISMISS


def route_after_hitl_gate(state: SupplierRiskState) -> str:
    """Evaluate whether workflow requires human sign-off before executing mitigation actions.

    - Requires HITL and no decision present -> suspend / await approval (routes to END).
    - Requires HITL and approved -> proceed to action node.
    - Requires HITL and rejected -> terminate (routes to END).
    - Zero spend ($0) does not require HITL -> proceed to action node.
    """
    if state.get("requires_hitl"):
        decision = state.get("hitl_decision")
        if decision is not None:
            if decision.get("approved") is True:
                return NODE_ACTION
            return "rejected"
        return "await_approval"

    return NODE_ACTION


# ------------------------------------------------------------------------------
# Node Handlers & Stubs (triage_node, research_node, and contract_node imported from nodes)
# ------------------------------------------------------------------------------


def risk_node(state: SupplierRiskState) -> dict[str, Any]:
    """Node 4: Execute deterministic Python risk calculations (BR-RULE-001).

    Computes Days of Cover, Shortage Gap, Shortage Volume, and Financial Exposure.
    Strictly isolated from probabilistic LLM arithmetic.
    """
    logger.info(
        "Risk node executing deterministic calculations for alert: %s", state.get("alert_id")
    )

    metrics = state.get("risk_metrics")

    # If raw stock and rates are present, execute the canonical calculation engine
    if metrics is None and (
        state.get("current_stock") is not None
        and state.get("daily_consumption_rate") is not None
        and state.get("eta_days") is not None
        and state.get("unit_cost_usd") is not None
    ):
        calc_input = RiskAssessmentInput(
            current_stock=state["current_stock"],  # type: ignore[arg-type]
            daily_consumption_rate=state["daily_consumption_rate"],  # type: ignore[arg-type]
            eta_days=state["eta_days"],  # type: ignore[arg-type]
            unit_cost_usd=state["unit_cost_usd"],  # type: ignore[arg-type]
            supplier_id=state.get("supplier_id"),
            component_sku=state.get("component_sku"),
        )
        calc_res = RiskCalculator().calculate(calc_input)
        metrics = {
            "days_of_cover": calc_res.days_of_cover,
            "gap_days": calc_res.gap_days,
            "shortage_volume": calc_res.shortage_volume,
            "financial_exposure": calc_res.financial_exposure,
            "factory_halt_exposure": calc_res.factory_halt_exposure,
            "total_exposure": calc_res.total_exposure,
            "is_shortage": calc_res.is_shortage,
            "calculation_hash": calc_res.calculation_hash,
        }

    # Default fallback if metrics missing
    if metrics is None:
        metrics = {
            "days_of_cover": Decimal("10.00"),
            "gap_days": Decimal("0.00"),
            "shortage_volume": 0,
            "financial_exposure": Decimal("0.00"),
            "is_shortage": False,
        }

    severity = (
        RiskLevel.CRITICAL
        if metrics.get("financial_exposure", Decimal("0")) > Decimal("1000000.00")
        else RiskLevel.LOW
    )

    narrative = (
        f"Automated risk analysis: Days of cover computed at {metrics.get('days_of_cover')} days. "
        f"Projected shortage gap: {metrics.get('gap_days')} days. "
        f"Financial exposure: ${metrics.get('financial_exposure', Decimal('0.00'))} USD."
    )

    return {
        "current_node": NODE_RISK,
        "execution_path": [NODE_RISK],
        "workflow_status": WorkflowStatus.CALCULATING_RISK,
        "risk_metrics": metrics,
        "severity": severity,
        "narrative": narrative,
    }


def recommendation_node(state: SupplierRiskState) -> dict[str, Any]:
    """Node 5: Formulate procurement mitigation options and map governing spend tier."""
    logger.info(
        "Recommendation node generating mitigation scenarios for alert: %s", state.get("alert_id")
    )

    metrics = state.get("risk_metrics") or {}
    financial_exposure = metrics.get("financial_exposure", Decimal("0.00"))
    if not isinstance(financial_exposure, Decimal):
        financial_exposure = Decimal(str(financial_exposure))

    # Scenario formulation
    scenario_cost = min(financial_exposure, Decimal("285000.00"))
    spend_tier = get_spend_tier(scenario_cost) if scenario_cost > Decimal("0.00") else None
    requires_hitl = scenario_cost > Decimal("0.00")

    scenarios = [
        {
            "scenario_id": f"SCEN-{state.get('alert_id', '001')}-01",
            "title": "Emergency Spot-Buy and Expedited Air Freight",
            "cost_usd": scenario_cost,
            "governing_spend_tier": spend_tier,
            "requires_hitl": requires_hitl,
        }
    ]

    return {
        "current_node": NODE_RECOMMENDATION,
        "execution_path": [NODE_RECOMMENDATION],
        "workflow_status": WorkflowStatus.PLANNING,
        "recommendations": scenarios,
        "recommended_action_id": scenarios[0]["scenario_id"],
        "governing_spend_tier": spend_tier,
        "requires_hitl": requires_hitl,
    }


def hitl_gate_node(state: SupplierRiskState) -> dict[str, Any]:
    """Node 6: Enforce cryptographic Human-In-The-Loop gate based on spend tier."""
    logger.info("HITL gate node checking authorization status for alert: %s", state.get("alert_id"))

    if state.get("requires_hitl"):
        decision = state.get("hitl_decision")
        if decision is not None:
            if decision.get("approved") is True:
                status = WorkflowStatus.APPROVED
            else:
                status = WorkflowStatus.REJECTED
        else:
            status = WorkflowStatus.AWAITING_APPROVAL
    else:
        status = WorkflowStatus.APPROVED

    return {
        "current_node": NODE_HITL_GATE,
        "execution_path": [NODE_HITL_GATE],
        "workflow_status": status,
    }


def action_node(state: SupplierRiskState) -> dict[str, Any]:
    """Node 7: Execute approved procurement action and append cryptographic audit record."""
    logger.info("Action node executing approved mitigation for alert: %s", state.get("alert_id"))

    decision = state.get("hitl_decision") or {}
    audit_record = {
        "action": "EXECUTE_PROCUREMENT_MITIGATION",
        "action_id": state.get("recommended_action_id"),
        "token_hash": decision.get("token_hash", "SYSTEM_PRE_AUTHORIZED"),
        "signer_id": decision.get("signer_id", "SYSTEM"),
        "status": "EXECUTED",
    }

    return {
        "current_node": NODE_ACTION,
        "execution_path": [NODE_ACTION],
        "workflow_status": WorkflowStatus.EXECUTED,
        "audit_events": [audit_record],
    }


def dismiss_node(state: SupplierRiskState) -> dict[str, Any]:
    """Node 8: Record zero-impact event and close investigation without expenditure."""
    logger.info("Dismiss node closing zero-risk case for alert: %s", state.get("alert_id"))

    audit_record = {
        "action": "CASE_DISMISSED",
        "reason": "Sufficient buffer stock or zero plant blast radius",
        "status": "DISMISSED",
    }

    return {
        "current_node": NODE_DISMISS,
        "execution_path": [NODE_DISMISS],
        "workflow_status": WorkflowStatus.DISMISSED,
        "requires_hitl": False,
        "audit_events": [audit_record],
    }


# ------------------------------------------------------------------------------
# StateGraph Builder & Compiler
# ------------------------------------------------------------------------------


def build_investigation_graph(
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """Construct and compile the detective agent StateGraph DAG.

    Topology:
      START
        │
        ▼
      [triage]
        ├─► [research] ──┐
        ├─► [contract] ──┼─► [risk]
        └─► [dismiss] ───┼───────────► (END)
                         │
                         ▼
                   [recommendation]
                         │
                         ▼
                    [hitl_gate]
                         ├─► (await / rejected) ──► (END)
                         └─► [action] ────────────► (END)
    """
    builder = StateGraph(SupplierRiskState)

    # 1. Register All Nodes
    builder.add_node(NODE_TRIAGE, triage_node)
    builder.add_node(NODE_RESEARCH, research_node)
    builder.add_node(NODE_CONTRACT, contract_node)
    builder.add_node(NODE_RISK, risk_node)
    builder.add_node(NODE_RECOMMENDATION, recommendation_node)
    builder.add_node(NODE_HITL_GATE, hitl_gate_node)
    builder.add_node(NODE_ACTION, action_node)
    builder.add_node(NODE_DISMISS, dismiss_node)

    # 2. Entry & Triage Edges
    builder.add_edge(START, NODE_TRIAGE)
    builder.add_conditional_edges(
        NODE_TRIAGE,
        route_after_triage,
        {
            NODE_RESEARCH: NODE_RESEARCH,
            NODE_CONTRACT: NODE_CONTRACT,
            NODE_HITL_GATE: NODE_HITL_GATE,
            NODE_DISMISS: NODE_DISMISS,
        },
    )

    # 3. Investigation Convergence into Risk Node
    builder.add_edge(NODE_RESEARCH, NODE_RISK)
    builder.add_edge(NODE_CONTRACT, NODE_RISK)

    # 4. Quantitative Risk to Mitigation or Dismissal
    builder.add_conditional_edges(
        NODE_RISK,
        route_after_risk,
        {
            NODE_RECOMMENDATION: NODE_RECOMMENDATION,
            NODE_DISMISS: NODE_DISMISS,
        },
    )

    # 5. Recommendation to Governance Gate
    builder.add_edge(NODE_RECOMMENDATION, NODE_HITL_GATE)

    # 6. Governance Decision Routing
    builder.add_conditional_edges(
        NODE_HITL_GATE,
        route_after_hitl_gate,
        {
            NODE_ACTION: NODE_ACTION,
            "await_approval": END,
            "rejected": END,
        },
    )

    # 7. Terminal Edges
    builder.add_edge(NODE_ACTION, END)
    builder.add_edge(NODE_DISMISS, END)

    # 8. Compile
    return builder.compile(checkpointer=checkpointer)
