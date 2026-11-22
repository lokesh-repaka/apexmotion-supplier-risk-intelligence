"""Asynchronous repository for Supplier domain entities."""

from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Supplier
from src.database.repositories.base import BaseRepository


class SupplierRepository(BaseRepository[Supplier]):
    """Repository managing Supplier persistence and domain queries."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model_cls=Supplier)

    async def get_by_neptune_node_id(self, neptune_node_id: str) -> Supplier | None:
        """Find a supplier mapped to an Amazon Neptune knowledge graph node."""
        stmt = select(Supplier).where(Supplier.neptune_node_id == neptune_node_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_name(self, name: str) -> Supplier | None:
        """Lookup a supplier by exact name."""
        stmt = select(Supplier).where(Supplier.name == name)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_tier(self, tier: int, offset: int = 0, limit: int = 100) -> Sequence[Supplier]:
        """Fetch suppliers belonging to a supply chain tier (1..3)."""
        stmt = select(Supplier).where(Supplier.tier == tier).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_country(
        self, country_code: str, offset: int = 0, limit: int = 100
    ) -> Sequence[Supplier]:
        """Fetch suppliers operating in a specified ISO-3166 2-letter country."""
        stmt = (
            select(Supplier)
            .where(Supplier.country_code == country_code.upper())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_high_risk_suppliers(
        self, threshold: Decimal = Decimal("0.700"), limit: int = 100
    ) -> Sequence[Supplier]:
        """Fetch suppliers exceeding the critical risk threshold, ordered descending."""
        stmt = (
            select(Supplier)
            .where(Supplier.risk_score >= threshold)
            .order_by(Supplier.risk_score.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update_risk_score(self, supplier_id: UUID, new_score: Decimal) -> Supplier | None:
        """Update risk score for a supplier."""
        supplier = await self.get_by_id(supplier_id)
        if supplier is None:
            return None
        supplier.risk_score = new_score
        return await self.update(supplier)
