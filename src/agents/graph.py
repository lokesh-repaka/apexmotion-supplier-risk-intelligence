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
from src.agents.nodes.recommendation_agent import recommendation_node
from src.agents.nodes.research_agent import research_node
from src.agents.nodes.risk_agent import risk_node
from src.agents.nodes.triage_agent import triage_node
from src.agents.state import (
    SupplierRiskState,
    WorkflowStatus,
)
from src.core.logging import get_logger
from src.core.telemetry import trace_agent_node
from src.services.dual_approval_enforcer import get_dual_approval_enforcer

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
    - Requires HITL and approved (including both signatures for DUAL_VP) -> proceed to action node.
    - Requires HITL and rejected -> terminate (routes to END).
    - Zero spend ($0) does not require HITL -> proceed to action node.
    """
    if state.get("requires_hitl"):
        decision = state.get("hitl_decision")
        if decision is not None:
            enforcer = get_dual_approval_enforcer()
            is_dual = enforcer.is_dual_approval_required(
                spend_tier=state.get("governing_spend_tier")
            )
            if is_dual:
                tokens = decision.get("tokens") or []
                if len(tokens) < 2 and not decision.get("is_dual_approved"):
                    return "await_approval"
                ver_res = enforcer.enforce_state_approval(state)
                if ver_res.is_approved:
                    return NODE_ACTION
                if decision.get("approved") is False:
                    return "rejected"
                return "await_approval"

            if decision.get("approved") is True:
                return NODE_ACTION
            return "rejected"
        return "await_approval"

    return NODE_ACTION


# ------------------------------------------------------------------------------
# Node Handlers & Stubs (triage, research, contract, risk, and recommendation imported from nodes)
# ------------------------------------------------------------------------------


@trace_agent_node(NODE_HITL_GATE)
def hitl_gate_node(state: SupplierRiskState) -> dict[str, Any]:
    """Node 6: Enforce cryptographic Human-In-The-Loop gate based on spend tier."""
    logger.info("HITL gate node checking authorization status for alert: %s", state.get("alert_id"))

    if state.get("requires_hitl"):
        enforcer = get_dual_approval_enforcer()
        is_dual = enforcer.is_dual_approval_required(spend_tier=state.get("governing_spend_tier"))

        decision = state.get("hitl_decision")
        if decision is not None:
            if is_dual:
                tokens = decision.get("tokens") or []
                if not tokens and decision.get("token_hash"):
                    tokens = [decision["token_hash"]]

                if len(tokens) == 1 and not decision.get("approved"):
                    status = "PARTIALLY_APPROVED"
                else:
                    ver_res = enforcer.enforce_state_approval(state)
                    if ver_res.is_approved:
                        status = WorkflowStatus.APPROVED
                    elif decision.get("approved") is False:
                        status = WorkflowStatus.REJECTED
                    elif len(tokens) == 1:
                        status = "PARTIALLY_APPROVED"
                    else:
                        status = WorkflowStatus.AWAITING_APPROVAL
            else:
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


@trace_agent_node(NODE_ACTION)
def action_node(state: SupplierRiskState) -> dict[str, Any]:
    """Node 7: Execute approved procurement action and append cryptographic audit record."""
    logger.info("Action node executing approved mitigation for alert: %s", state.get("alert_id"))

    # Hard security gate: Enforce dual executive signatures for DUAL_VP actions
    enforcer = get_dual_approval_enforcer()
    enforcer.enforce_action_execution(state)

    decision = state.get("hitl_decision") or {}
    tokens = decision.get("tokens") or []
    signers = decision.get("signers") or (
        [decision.get("signer_id")] if decision.get("signer_id") else ["SYSTEM"]
    )

    audit_record: dict[str, Any] = {
        "action": "EXECUTE_PROCUREMENT_MITIGATION",
        "action_id": state.get("recommended_action_id"),
        "token_hash": decision.get("token_hash", "SYSTEM_PRE_AUTHORIZED"),
        "signer_id": decision.get("signer_id", "SYSTEM"),
        "status": "EXECUTED",
    }
    if len(tokens) >= 2 or decision.get("is_dual_approved"):
        audit_record["is_dual_approved"] = True
        audit_record["signers"] = signers
        audit_record["token_hashes"] = tokens

    return {
        "current_node": NODE_ACTION,
        "execution_path": [NODE_ACTION],
        "workflow_status": WorkflowStatus.EXECUTED,
        "audit_events": [audit_record],
    }


@trace_agent_node(NODE_DISMISS)
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
    builder.add_node(NODE_TRIAGE, trace_agent_node(NODE_TRIAGE)(triage_node))
    builder.add_node(NODE_RESEARCH, trace_agent_node(NODE_RESEARCH)(research_node))
    builder.add_node(NODE_CONTRACT, trace_agent_node(NODE_CONTRACT)(contract_node))
    builder.add_node(NODE_RISK, trace_agent_node(NODE_RISK)(risk_node))
    builder.add_node(
        NODE_RECOMMENDATION, trace_agent_node(NODE_RECOMMENDATION)(recommendation_node)
    )
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
