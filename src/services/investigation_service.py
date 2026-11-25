"""Investigation Lifecycle & Multi-Agent Orchestration Service (P11-2).

Coordinates:
- Asynchronous invocation of the LangGraph multi-agent investigation workflow.
- In-memory state tracking and LangGraph Checkpointer state retrieval.
- Telemetry recording and status synchronization with Aurora PostgreSQL `agent_runs`.
- Append-only forensic audit trail dispatch (BR-RULE-007).
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver

from src.agents.orchestrator import InvestigationOrchestrator
from src.agents.state import (
    SupplierRiskState,
    WorkflowStatus,
    create_initial_state,
)
from src.api.schemas.investigation import InvestigationStartRequest
from src.core.audit import write_audit_log
from src.core.logging import get_logger, get_trace_id
from src.core.metrics import record_investigation_completion
from src.core.security import AuthenticatedUser
from src.database.models import AgentRun
from src.database.repositories.agent_run_repository import AgentRunRepository
from src.database.session import get_async_session_factory
from src.services.risk import (
    NANOCORE_CANONICAL_SKU,
    REFERENCE_INVENTORY_REGISTRY,
)

logger = get_logger("apexmotion.services.investigation")


@dataclass
class InvestigationRecord:
    """Internal representation of an investigation run and its progress."""

    investigation_id: str
    case_id: str
    alert_id: str | None
    supplier_id: str
    component_sku: str | None
    status: str
    current_node: str | None = None
    execution_path: list[str] = field(default_factory=list)
    risk_metrics: dict[str, Any] | None = None
    severity: str | None = None
    narrative: str | None = None
    research_analysis: dict[str, Any] | None = None
    contract_analysis: dict[str, Any] | None = None
    recommendations: list[dict[str, Any]] | None = None
    recommended_action_id: str | None = None
    requires_hitl: bool = False
    governing_spend_tier: str | None = None
    errors: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    duration_ms: int | None = None
    tokens_used: int | None = None
    cost_usd: Decimal | None = None
    langfuse_trace_id: str | None = None
    state: SupplierRiskState | None = None
    task: asyncio.Task[Any] | None = None

    @property
    def id(self) -> uuid.UUID:
        """Expose investigation_id as UUID for repository compatibility."""
        return uuid.UUID(self.investigation_id)


class InvestigationService:
    """Coordinates lifecycle, execution, and polling of multi-agent investigations."""

    def __init__(
        self,
        checkpointer: MemorySaver | None = None,
        session_factory: Any = None,
    ) -> None:
        self.checkpointer = checkpointer or MemorySaver()
        self.session_factory = session_factory
        self.orchestrator = InvestigationOrchestrator(checkpointer=self.checkpointer)
        self._active_investigations: dict[str, InvestigationRecord] = {}
        self._case_id_index: dict[str, str] = {}
        self._alert_id_index: dict[str, str] = {}

    def _resolve_inventory(
        self,
        component_sku: str | None,
        stock: int | None,
        daily_rate: Decimal | None,
        cost: Decimal | None,
        eta: Decimal | None,
    ) -> tuple[int | None, Decimal | None, Decimal | None, Decimal | None]:
        """Resolve inventory parameters against canonical registry when omitted."""
        if not component_sku:
            return stock, daily_rate, cost, eta

        ref = REFERENCE_INVENTORY_REGISTRY.get(component_sku)
        resolved_stock = stock
        resolved_rate = daily_rate
        resolved_cost = cost
        resolved_eta = eta

        if ref is not None:
            if resolved_stock is None:
                resolved_stock = int(ref["current_stock"])
            if resolved_rate is None:
                resolved_rate = Decimal(str(ref["daily_consumption_rate"]))
            if resolved_cost is None:
                resolved_cost = Decimal(str(ref["unit_cost_usd"]))
            if resolved_eta is None and "inbound_eta_days" in ref:
                resolved_eta = Decimal(str(ref["inbound_eta_days"]))
        elif component_sku in (NANOCORE_CANONICAL_SKU, "NC-2024-001"):
            if resolved_stock is None:
                resolved_stock = 142000
            if resolved_rate is None:
                resolved_rate = Decimal("18500")
            if resolved_cost is None:
                resolved_cost = Decimal("100.25")
            if resolved_eta is None:
                resolved_eta = Decimal("9.0")

        return resolved_stock, resolved_rate, resolved_cost, resolved_eta

    async def start_investigation(
        self,
        payload: InvestigationStartRequest,
        current_user: AuthenticatedUser,
        session: Any = None,
    ) -> InvestigationRecord:
        """Initialize, register, and launch a new investigation workflow."""
        investigation_id = str(uuid.uuid4())
        date_str = datetime.now(UTC).strftime("%Y%m%d")
        case_id = f"CASE-{date_str}-{investigation_id[:8].upper()}"

        stock, rate, cost, eta = self._resolve_inventory(
            component_sku=payload.component_sku,
            stock=payload.current_stock,
            daily_rate=payload.daily_consumption_rate,
            cost=payload.unit_cost_usd,
            eta=payload.eta_days,
        )

        initial_state = create_initial_state(
            alert_id=payload.alert_id or f"ALT-{investigation_id[:8].upper()}",
            supplier_id=payload.supplier_id,
            signal_type=payload.signal_type,
            raw_signal=payload.raw_signal,
            case_id=case_id,
            supplier_name=payload.target_supplier_hint,
            component_sku=payload.component_sku,
            trace_id=get_trace_id(),
            current_stock=stock,
            daily_consumption_rate=rate,
            eta_days=eta,
            unit_cost_usd=cost,
            metadata=payload.metadata,
        )

        record = InvestigationRecord(
            investigation_id=investigation_id,
            case_id=case_id,
            alert_id=payload.alert_id,
            supplier_id=payload.supplier_id,
            component_sku=payload.component_sku,
            status="RUNNING",
            state=initial_state,
            started_at=datetime.now(UTC),
        )

        self._active_investigations[investigation_id] = record
        self._case_id_index[case_id] = investigation_id
        if payload.alert_id:
            self._alert_id_index[payload.alert_id] = investigation_id

        # Persist AgentRun record in database if session is available
        if session is not None:
            try:
                alert_uuid = None
                if payload.alert_id:
                    try:
                        alert_uuid = uuid.UUID(payload.alert_id.strip())
                    except ValueError:
                        pass
                agent_run = AgentRun(
                    id=uuid.UUID(investigation_id),
                    alert_id=alert_uuid,
                    graph_name="incident_investigation_graph",
                    status="RUNNING",
                )
                repo = AgentRunRepository(session)
                await repo.create(agent_run)
            except Exception as exc:
                logger.warning("Could not persist initial AgentRun to database: %s", exc)

        # Dispatch background workflow task or execute synchronously
        task = asyncio.create_task(
            self._execute_workflow(investigation_id, initial_state, current_user.user_id)
        )
        record.task = task

        if payload.wait_for_completion:
            await task

        # Dispatched audit log
        try:
            await write_audit_log(
                entity_type="INVESTIGATION",
                entity_id=investigation_id,
                action="INVESTIGATION_STARTED",
                actor_id=current_user.user_id,
                session_factory=self.session_factory,
                after_state={
                    "case_id": case_id,
                    "supplier_id": payload.supplier_id,
                    "component_sku": payload.component_sku,
                    "status": "RUNNING",
                },
            )
        except Exception as exc:
            logger.warning("Audit write failed during investigation start: %s", exc)

        return record

    async def _execute_workflow(
        self,
        investigation_id: str,
        initial_state: SupplierRiskState,
        actor_id: str,
    ) -> None:
        """Asynchronous execution task advancing LangGraph state machine to completion or pause."""
        record = self._active_investigations.get(investigation_id)
        if not record:
            return

        start_time = time.perf_counter()
        thread_config = cast(RunnableConfig, {"configurable": {"thread_id": investigation_id}})

        try:
            final_state = await self.orchestrator.run_investigation(
                initial_state,
                config=thread_config,
            )
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            # Determine finalized status
            raw_status = final_state.get("workflow_status")
            if raw_status == WorkflowStatus.AWAITING_APPROVAL:
                status_str = "AWAITING_APPROVAL"
            elif raw_status == WorkflowStatus.DISMISSED:
                status_str = "DISMISSED"
            else:
                status_str = "COMPLETED"

            spend_tier_val = final_state.get("governing_spend_tier")
            spend_tier_str = (
                (spend_tier_val.value if hasattr(spend_tier_val, "value") else str(spend_tier_val))
                if spend_tier_val
                else None
            )

            # Extract LLM telemetry and Langfuse trace
            meta = final_state.get("metadata") or {}
            llm_metrics = meta.get("llm_metrics") or {}
            langfuse_trace_id = meta.get("langfuse_trace_id") or llm_metrics.get("trace_id")
            tokens_used = llm_metrics.get("tokens_used")
            cost_usd = llm_metrics.get("cost_usd")

            record.status = status_str
            record.state = final_state
            record.current_node = final_state.get("current_node")
            record.execution_path = list(final_state.get("execution_path") or [])
            record.risk_metrics = final_state.get("risk_metrics")
            record.severity = (
                str(final_state.get("severity")) if final_state.get("severity") else None
            )
            record.narrative = final_state.get("narrative")
            record.research_analysis = final_state.get("research_analysis")
            record.contract_analysis = final_state.get("contract_analysis")
            record.recommendations = final_state.get("recommendations")
            record.recommended_action_id = final_state.get("recommended_action_id")
            record.requires_hitl = bool(final_state.get("requires_hitl", False))
            record.governing_spend_tier = spend_tier_str
            record.errors = list(final_state.get("errors") or [])
            record.completed_at = datetime.now(UTC)
            record.duration_ms = duration_ms
            record.tokens_used = tokens_used
            record.cost_usd = cost_usd
            record.langfuse_trace_id = langfuse_trace_id

            # Synchronize AgentRun completion in database
            await self._sync_agent_run_completion(
                investigation_id=investigation_id,
                status="COMPLETED",
                duration_ms=duration_ms,
                tokens_used=tokens_used,
                cost_usd=cost_usd,
                langfuse_trace_id=langfuse_trace_id,
            )

            # Record Prometheus investigation metrics (P15-3)
            record_investigation_completion(
                status=status_str,
                duration_seconds=duration_ms / 1000.0,
            )

            # Forensic audit log
            try:
                await write_audit_log(
                    entity_type="INVESTIGATION",
                    entity_id=investigation_id,
                    action="INVESTIGATION_COMPLETED",
                    actor_id=actor_id,
                    session_factory=self.session_factory,
                    after_state={
                        "status": status_str,
                        "duration_ms": duration_ms,
                        "requires_hitl": record.requires_hitl,
                        "governing_spend_tier": record.governing_spend_tier,
                    },
                )
            except Exception as audit_exc:
                logger.warning("Audit write failed during investigation completion: %s", audit_exc)

        except Exception as exc:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.error(
                "Investigation '%s' failed during graph execution: %s",
                investigation_id,
                exc,
                exc_info=True,
                extra={"trace_id": get_trace_id()},
            )
            record.status = "FAILED"
            record.completed_at = datetime.now(UTC)
            record.duration_ms = duration_ms
            record.errors.append(str(exc))

            await self._sync_agent_run_completion(
                investigation_id=investigation_id,
                status="FAILED",
                duration_ms=duration_ms,
            )

            record_investigation_completion(
                status="FAILED",
                duration_seconds=duration_ms / 1000.0,
            )

            try:
                await write_audit_log(
                    entity_type="INVESTIGATION",
                    entity_id=investigation_id,
                    action="INVESTIGATION_FAILED",
                    actor_id=actor_id,
                    session_factory=self.session_factory,
                    after_state={"error": str(exc), "duration_ms": duration_ms},
                )
            except Exception as audit_exc:
                logger.warning("Audit write failed during investigation failure: %s", audit_exc)

    async def _sync_agent_run_completion(
        self,
        investigation_id: str,
        status: str,
        duration_ms: int,
        tokens_used: int | None = None,
        cost_usd: Decimal | None = None,
        langfuse_trace_id: str | None = None,
    ) -> None:
        """Update AgentRun record in database using an isolated session."""
        try:
            run_uuid = uuid.UUID(investigation_id)
            session_factory = self.session_factory or get_async_session_factory()
            async with session_factory() as db_sess:
                repo = AgentRunRepository(db_sess)
                await repo.complete_run(
                    run_id=run_uuid,
                    status=status,
                    duration_ms=duration_ms,
                    tokens_used=tokens_used,
                    cost_usd=cost_usd,
                    langfuse_trace_id=langfuse_trace_id,
                )
                await db_sess.commit()
        except Exception as exc:
            logger.debug("Could not synchronize AgentRun completion to database: %s", exc)

    async def get_investigation(
        self,
        identifier: str,
        session: Any = None,
    ) -> InvestigationRecord | None:
        """Retrieve investigation status and results by investigation_id, case_id, or alert_id."""
        clean_id = identifier.strip()

        # 1. Lookup in active memory cache by investigation UUID
        if clean_id in self._active_investigations:
            return self._active_investigations[clean_id]

        # 2. Lookup by case_id alias
        if clean_id in self._case_id_index:
            inv_id = self._case_id_index[clean_id]
            return self._active_investigations.get(inv_id)

        # 3. Lookup by alert_id alias
        if clean_id in self._alert_id_index:
            inv_id = self._alert_id_index[clean_id]
            return self._active_investigations.get(inv_id)

        # 4. Checkpoint state lookup via orchestrator checkpointer
        checkpoint_tuple = await self.checkpointer.aget_tuple(
            {"configurable": {"thread_id": clean_id}}
        )
        if checkpoint_tuple is not None and checkpoint_tuple.checkpoint:
            channel_values = checkpoint_tuple.checkpoint.get("channel_values", {})
            if channel_values:
                status_raw = channel_values.get("workflow_status", "COMPLETED")
                status_str = (
                    "AWAITING_APPROVAL"
                    if status_raw == WorkflowStatus.AWAITING_APPROVAL
                    else "COMPLETED"
                )
                rec = InvestigationRecord(
                    investigation_id=clean_id,
                    case_id=channel_values.get("case_id", f"CASE-{clean_id[:8].upper()}"),
                    alert_id=channel_values.get("alert_id"),
                    supplier_id=channel_values.get("supplier_id", "UNKNOWN"),
                    component_sku=channel_values.get("component_sku"),
                    status=status_str,
                    current_node=channel_values.get("current_node"),
                    execution_path=list(channel_values.get("execution_path") or []),
                    risk_metrics=channel_values.get("risk_metrics"),
                    severity=str(channel_values.get("severity"))
                    if channel_values.get("severity")
                    else None,
                    narrative=channel_values.get("narrative"),
                    research_analysis=channel_values.get("research_analysis"),
                    contract_analysis=channel_values.get("contract_analysis"),
                    recommendations=channel_values.get("recommendations"),
                    recommended_action_id=channel_values.get("recommended_action_id"),
                    requires_hitl=bool(channel_values.get("requires_hitl", False)),
                    errors=list(channel_values.get("errors") or []),
                    state=cast(SupplierRiskState, channel_values),
                )
                self._active_investigations[clean_id] = rec
                return rec

        # 5. Fallback database lookup via AgentRunRepository
        if session is not None:
            try:
                run_uuid = uuid.UUID(clean_id)
                repo = AgentRunRepository(session)
                run = await repo.get_by_id(run_uuid)
                if run is not None:
                    return InvestigationRecord(
                        investigation_id=str(run.id),
                        case_id=f"CASE-{str(run.id)[:8].upper()}",
                        alert_id=str(run.alert_id) if run.alert_id else None,
                        supplier_id="UNKNOWN",
                        component_sku=None,
                        status=run.status,
                        started_at=run.created_at,
                        completed_at=run.created_at,
                        duration_ms=run.duration_ms,
                        tokens_used=run.tokens_used,
                        cost_usd=run.cost_usd,
                        langfuse_trace_id=run.langfuse_trace_id,
                    )
            except (ValueError, Exception) as exc:
                logger.debug("Database fallback query failed for '%s': %s", clean_id, exc)

        return None


# Global singleton instance
_investigation_service_instance: InvestigationService | None = None


def get_investigation_service() -> InvestigationService:
    """Retrieve or initialize the InvestigationService singleton."""
    global _investigation_service_instance
    if _investigation_service_instance is None:
        _investigation_service_instance = InvestigationService()
    return _investigation_service_instance
