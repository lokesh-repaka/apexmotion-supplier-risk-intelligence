"""Asynchronous repository for immutable AuditLog entries (BR-RULE-007)."""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import AuditLog
from src.database.repositories.base import BaseRepository


class AuditLogRepository(BaseRepository[AuditLog]):
    """Repository managing immutable AuditLog persistence (BR-RULE-007).

    Strictly prohibits UPDATE and DELETE operations at the application repository layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model_cls=AuditLog)

    async def update(self, _entity: AuditLog) -> AuditLog:
        """Enforce BR-RULE-007: AuditLog is strictly append-only."""
        raise PermissionError("AuditLog is append-only and cannot be updated (BR-RULE-007).")

    async def delete(self, _entity_id: Any) -> bool:
        """Enforce BR-RULE-007: AuditLog is strictly append-only."""
        raise PermissionError("AuditLog is append-only and cannot be deleted (BR-RULE-007).")

    async def get_by_entity(
        self, entity_type: str, entity_id: UUID, limit: int = 100
    ) -> Sequence[AuditLog]:
        """Fetch audit log history for a specific business entity."""
        stmt = (
            select(AuditLog)
            .where(
                AuditLog.entity_type == entity_type,
                AuditLog.entity_id == entity_id,
            )
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_trace_id(self, trace_id: str, limit: int = 100) -> Sequence[AuditLog]:
        """Fetch audit entries sharing a distributed correlation trace_id."""
        stmt = (
            select(AuditLog)
            .where(AuditLog.trace_id == trace_id)
            .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_actor(self, actor_id: UUID, limit: int = 100) -> Sequence[AuditLog]:
        """Fetch audit trails initiated by a specific user or system actor."""
        stmt = (
            select(AuditLog)
            .where(AuditLog.actor_id == actor_id)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_recent(self, limit: int = 100) -> Sequence[AuditLog]:
        """Fetch the most recent forensic audit log entries."""
        stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()
