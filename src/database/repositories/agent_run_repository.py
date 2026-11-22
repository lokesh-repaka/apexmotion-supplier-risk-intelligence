"""Asynchronous repository for AgentRun multi-agent execution telemetry."""

from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import AgentRun
from src.database.repositories.base import BaseRepository


class AgentRunRepository(BaseRepository[AgentRun]):
    """Repository managing AgentRun multi-agent telemetry and Langfuse trace links."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model_cls=AgentRun)

    async def get_by_alert_id(self, alert_id: UUID) -> Sequence[AgentRun]:
        """Fetch all agent graph runs associated with an alert."""
        stmt = (
            select(AgentRun)
            .where(AgentRun.alert_id == alert_id)
            .order_by(AgentRun.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_langfuse_trace_id(self, langfuse_trace_id: str) -> AgentRun | None:
        """Lookup an agent run by external Langfuse trace ID."""
        stmt = select(AgentRun).where(AgentRun.langfuse_trace_id == langfuse_trace_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_graph_name(self, graph_name: str, limit: int = 100) -> Sequence[AgentRun]:
        """Fetch runs by LangGraph workflow identifier."""
        stmt = (
            select(AgentRun)
            .where(AgentRun.graph_name == graph_name)
            .order_by(AgentRun.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_runs_by_status(self, status: str, limit: int = 100) -> Sequence[AgentRun]:
        """Fetch runs matching an execution status (e.g., RUNNING, COMPLETED, FAILED)."""
        stmt = (
            select(AgentRun)
            .where(AgentRun.status == status.upper())
            .order_by(AgentRun.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def complete_run(
        self,
        run_id: UUID,
        status: str,
        duration_ms: int,
        tokens_used: int | None = None,
        cost_usd: Decimal | None = None,
    ) -> AgentRun | None:
        """Finalize agent execution recording latency, status, tokens, and cost."""
        run = await self.get_by_id(run_id)
        if run is None:
            return None

        run.status = status.upper()
        run.duration_ms = duration_ms
        if tokens_used is not None:
            run.tokens_used = tokens_used
        if cost_usd is not None:
            run.cost_usd = cost_usd

        return await self.update(run)
