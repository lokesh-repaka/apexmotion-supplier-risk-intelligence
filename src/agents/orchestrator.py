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
from src.core.langfuse import (
    ApexLangfuseCallbackHandler,
    get_langfuse_callback_handler,
)
from src.core.logging import get_logger
from src.core.telemetry import trace_span

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
        init_attrs = {
            "alert_id": str(state.get("alert_id", "")),
            "supplier_id": str(state.get("supplier_id", "")),
            "signal_type": str(state.get("signal_type", "")),
        }
        with trace_span("investigation_workflow_execute", attributes=init_attrs) as span:
            logger.info("Executing investigation workflow for alert: %s", state.get("alert_id"))

            # Attach Langfuse CallbackHandler for LLM telemetry & token accounting (P15-2)
            active_config: dict[str, Any] = dict(config) if config else {}
            raw_callbacks = active_config.get("callbacks")
            existing_callbacks: list[Any] = (
                list(raw_callbacks) if isinstance(raw_callbacks, list) else []
            )
            langfuse_handler: ApexLangfuseCallbackHandler | None = None
            for cb in existing_callbacks:
                if isinstance(cb, ApexLangfuseCallbackHandler):
                    langfuse_handler = cb
                    break
            if langfuse_handler is None:
                langfuse_handler = get_langfuse_callback_handler(
                    alert_id=state.get("alert_id"),
                    investigation_id=state.get("case_id"),
                    metadata={
                        "supplier_id": state.get("supplier_id"),
                        "component_sku": state.get("component_sku"),
                    },
                )
                existing_callbacks.append(langfuse_handler)
                active_config["callbacks"] = existing_callbacks

            result = await self.graph.ainvoke(state, config=cast(RunnableConfig, active_config))
            res_dict = cast(SupplierRiskState, result)
            if langfuse_handler is not None:
                langfuse_handler.flush()
                metrics = langfuse_handler.get_metrics()
                meta = dict(res_dict.get("metadata") or {})
                meta["llm_metrics"] = metrics
                meta["langfuse_trace_id"] = metrics["trace_id"]
                res_dict["metadata"] = meta

            if res_dict.get("workflow_status"):
                span.set_attribute("workflow_status", str(res_dict["workflow_status"]))
            return res_dict

    async def resume_investigation(
        self,
        thread_id: str,
        hitl_decision: dict[str, Any],
        config: RunnableConfig | None = None,
    ) -> SupplierRiskState:
        """Resume a suspended investigation following human-in-the-loop sign-off."""
        init_attrs = {
            "thread_id": thread_id,
            "is_approved": str(hitl_decision.get("approved")),
        }
        with trace_span("investigation_workflow_resume", attributes=init_attrs) as span:
            logger.info("Resuming investigation thread %s with HITL approval decision", thread_id)
            active_config: dict[str, Any] = (
                dict(config) if config else {"configurable": {"thread_id": thread_id}}
            )
            raw_callbacks = active_config.get("callbacks")
            existing_callbacks: list[Any] = (
                list(raw_callbacks) if isinstance(raw_callbacks, list) else []
            )
            langfuse_handler: ApexLangfuseCallbackHandler | None = None
            for cb in existing_callbacks:
                if isinstance(cb, ApexLangfuseCallbackHandler):
                    langfuse_handler = cb
                    break
            if langfuse_handler is None:
                langfuse_handler = get_langfuse_callback_handler(
                    investigation_id=thread_id,
                    metadata={"action": "resume_investigation"},
                )
                existing_callbacks.append(langfuse_handler)
                active_config["callbacks"] = existing_callbacks

            # Update checkpointed state with approved HITL decision
            await self.graph.aupdate_state(
                cast(RunnableConfig, active_config),
                {"hitl_decision": hitl_decision},
            )

            # Re-invoke to process approval through hitl_gate and action nodes
            result = await self.graph.ainvoke(
                {"hitl_decision": hitl_decision},
                config=cast(RunnableConfig, active_config),
            )
            res_dict = cast(SupplierRiskState, result)
            if langfuse_handler is not None:
                langfuse_handler.flush()
                metrics = langfuse_handler.get_metrics()
                meta = dict(res_dict.get("metadata") or {})
                meta["llm_metrics"] = metrics
                meta["langfuse_trace_id"] = metrics["trace_id"]
                res_dict["metadata"] = meta

            if res_dict.get("workflow_status"):
                span.set_attribute("workflow_status", str(res_dict["workflow_status"]))
            return res_dict


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
