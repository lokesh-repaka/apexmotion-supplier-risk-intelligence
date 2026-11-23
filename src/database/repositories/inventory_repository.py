"""Asynchronous repository for InventorySnapshot domain entities."""

from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import InventorySnapshot
from src.database.repositories.base import BaseRepository


class InventoryRepository(BaseRepository[InventorySnapshot]):
    """Repository managing InventorySnapshot persistence and stock level queries in Aurora PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model_cls=InventorySnapshot)

    async def get_by_sku(
        self, component_sku: str, plant_id: str | None = None
    ) -> InventorySnapshot | None:
        """Fetch inventory snapshot for a specific SKU and optional manufacturing plant."""
        stmt = select(InventorySnapshot).where(InventorySnapshot.component_sku == component_sku)
        if plant_id is not None:
            stmt = stmt.where(InventorySnapshot.plant_id == plant_id)
        stmt = stmt.order_by(InventorySnapshot.updated_at.desc())

        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_sku_all_plants(self, component_sku: str) -> Sequence[InventorySnapshot]:
        """Fetch all inventory records across manufacturing plants for a given SKU."""
        stmt = (
            select(InventorySnapshot)
            .where(InventorySnapshot.component_sku == component_sku)
            .order_by(InventorySnapshot.plant_id.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_supplier_id(
        self, supplier_id: UUID, limit: int = 100
    ) -> Sequence[InventorySnapshot]:
        """Fetch inventory components associated with a specific supplier UUID."""
        stmt = (
            select(InventorySnapshot)
            .where(InventorySnapshot.supplier_id == supplier_id)
            .order_by(InventorySnapshot.component_sku.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def upsert_inventory(self, snapshot: InventorySnapshot) -> InventorySnapshot:
        """Insert or update inventory record by component SKU and plant code."""
        existing = await self.get_by_sku(snapshot.component_sku, snapshot.plant_id)
        if existing is not None:
            existing.current_stock = snapshot.current_stock
            existing.daily_consumption_rate = snapshot.daily_consumption_rate
            existing.safety_stock_units = snapshot.safety_stock_units
            existing.unit_cost_usd = snapshot.unit_cost_usd
            existing.inbound_eta_days = snapshot.inbound_eta_days
            existing.inbound_shipment_units = snapshot.inbound_shipment_units
            existing.inbound_shipment_po = snapshot.inbound_shipment_po
            existing.supplier_id = snapshot.supplier_id
            return await self.update(existing)
        return await self.create(snapshot)

    async def update_stock_quantity(
        self,
        component_sku: str,
        delta_units: Decimal,
        plant_id: str | None = None,
    ) -> InventorySnapshot | None:
        """Apply positive or negative quantity adjustment to on-hand inventory balance."""
        existing = await self.get_by_sku(component_sku, plant_id)
        if existing is None:
            return None

        new_stock = existing.current_stock + delta_units
        if new_stock < Decimal("0.00"):
            raise ValueError(
                f"Negative inventory balance disallowed: {existing.current_stock} + ({delta_units}) = {new_stock}"
            )

        existing.current_stock = new_stock
        return await self.update(existing)
