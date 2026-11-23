"""LangGraph Detective Agent Orchestrator (P9-1).

Provides high-level lifecycle methods to execute, interrupt, and resume
supply chain risk investigations across the LangGraph StateGraph workflow.
"""

import threading
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

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
)
from src.agents.state import (
    AgentState,
    SignalType,
    SupplierRiskState,
    WorkflowStatus,
    create_initial_state,
)
from src.core.logging import get_logger

logger = get_logger("apexmotion.agents.orchestrator")


class InvestigationOrchestrator:
    """Manages invocation, state checkpointing, and HITL resumption of the investigation graph."""

    def __init__(self, checkpointer: BaseCheckpointSaver[Any] | None = None) -> None:
        self.checkpointer = checkpointer
        self.graph = build_investigation_graph(checkpointer=checkpointer)

    async def run_investigation(
        self,
        state: SupplierRiskState,
        config: RunnableConfig | None = None,
    ) -> SupplierRiskState:
        """Execute the investigation graph until completion or suspension at HITL gate."""
        logger.info("Executing investigation workflow for alert: %s", state.get("alert_id"))
        result = await self.graph.ainvoke(state, config=config)
        return cast(SupplierRiskState, result)

    async def resume_investigation(
        self,
        thread_id: str,
        hitl_decision: dict[str, Any],
        config: RunnableConfig | None = None,
    ) -> SupplierRiskState:
        """Resume a suspended investigation following human-in-the-loop sign-off."""
        logger.info("Resuming investigation thread %s with HITL approval decision", thread_id)
        active_config = config or cast(RunnableConfig, {"configurable": {"thread_id": thread_id}})

        # Update checkpointed state with approved HITL decision
        await self.graph.aupdate_state(
            active_config,
            {"hitl_decision": hitl_decision},
        )

        # Re-invoke to process approval through hitl_gate and action nodes
        result = await self.graph.ainvoke(
            {"hitl_decision": hitl_decision},
            config=active_config,
        )
        return cast(SupplierRiskState, result)


# ------------------------------------------------------------------------------
# Singleton & Dependency Injection
# ------------------------------------------------------------------------------

_graph_singleton_lock = threading.Lock()
_graph_singleton: CompiledStateGraph[Any, Any, Any, Any] | None = None


def get_investigation_graph() -> CompiledStateGraph[Any, Any, Any, Any]:
    """Obtain or initialize thread-safe compiled investigation StateGraph singleton."""
    global _graph_singleton
    if _graph_singleton is None:
        with _graph_singleton_lock:
            if _graph_singleton is None:
                _graph_singleton = build_investigation_graph()
    return _graph_singleton


__all__ = [
    "AgentState",
    "InvestigationOrchestrator",
    "NODE_ACTION",
    "NODE_CONTRACT",
    "NODE_DISMISS",
    "NODE_HITL_GATE",
    "NODE_RECOMMENDATION",
    "NODE_RESEARCH",
    "NODE_RISK",
    "NODE_TRIAGE",
    "SignalType",
    "SupplierRiskState",
    "WorkflowStatus",
    "build_investigation_graph",
    "create_initial_state",
    "get_investigation_graph",
]
