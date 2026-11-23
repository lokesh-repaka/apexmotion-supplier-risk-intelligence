"""Asynchronous repository for RiskAlert domain entities."""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import RiskAlert
from src.database.repositories.base import BaseRepository


class RiskAlertRepository(BaseRepository[RiskAlert]):
    """Repository managing RiskAlert persistence and domain queries."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model_cls=RiskAlert)

    async def get_by_supplier_id(self, supplier_id: UUID, limit: int = 100) -> Sequence[RiskAlert]:
        """Fetch all alerts associated with a specific supplier."""
        stmt = (
            select(RiskAlert)
            .where(RiskAlert.supplier_id == supplier_id)
            .order_by(RiskAlert.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_component_sku(
        self, component_sku: str, limit: int = 100
    ) -> Sequence[RiskAlert]:
        """Fetch alerts associated with a specific component SKU."""
        stmt = (
            select(RiskAlert)
            .where(RiskAlert.component_sku == component_sku)
            .order_by(RiskAlert.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_status(self, status: str, limit: int = 100) -> Sequence[RiskAlert]:
        """Fetch alerts matching a specific workflow status."""
        stmt = (
            select(RiskAlert)
            .where(RiskAlert.status == status.upper())
            .order_by(RiskAlert.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_active_alerts(self, limit: int = 100) -> Sequence[RiskAlert]:
        """Fetch active alerts requiring monitoring or operational intervention (OPEN, INVESTIGATING)."""
        stmt = (
            select(RiskAlert)
            .where(RiskAlert.status.in_(["OPEN", "INVESTIGATING"]))
            .order_by(RiskAlert.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_risk_level(self, risk_level: str, limit: int = 100) -> Sequence[RiskAlert]:
        """Fetch alerts matching a specific risk severity level."""
        stmt = (
            select(RiskAlert)
            .where(RiskAlert.risk_level == risk_level.upper())
            .order_by(RiskAlert.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update_status(self, alert_id: UUID, new_status: str) -> RiskAlert | None:
        """Transition alert to a new workflow status."""
        alert = await self.get_by_id(alert_id)
        if alert is None:
            return None
        alert.status = new_status.upper()
        return await self.update(alert)

    async def find_recent_active_alert(
        self,
        component_sku: str,
        supplier_id: UUID | None,
        window_seconds: int = 3600,
        reference_time: datetime | None = None,
    ) -> RiskAlert | None:
        """Fetch the most recent active alert for (component_sku, supplier_id) within rolling window."""
        ref = reference_time or datetime.now(UTC)
        stmt = (
            select(RiskAlert)
            .where(
                RiskAlert.component_sku == component_sku,
                RiskAlert.status.in_(["OPEN", "INVESTIGATING"]),
            )
            .order_by(RiskAlert.created_at.desc())
        )
        if supplier_id is not None:
            stmt = stmt.where(RiskAlert.supplier_id == supplier_id)
        else:
            stmt = stmt.where(RiskAlert.supplier_id.is_(None))

        result = await self.session.execute(stmt)
        candidates = result.scalars().all()
        for candidate in candidates:
            cand_created = candidate.created_at
            if cand_created is None:
                continue
            if cand_created.tzinfo is None:
                cand_created = cand_created.replace(tzinfo=UTC)
            ref_tz = ref if ref.tzinfo is not None else ref.replace(tzinfo=UTC)
            diff_seconds = (ref_tz - cand_created).total_seconds()
            if -60.0 <= diff_seconds <= window_seconds:
                return candidate
        return None
