"""Generic asynchronous repository base class for SQLAlchemy 2 models."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Base


class BaseRepository[ModelType: Base]:
    """Generic async repository providing standard CRUD operations."""

    def __init__(self, session: AsyncSession, model_cls: type[ModelType]) -> None:
        self.session = session
        self.model_cls = model_cls

    async def create(self, entity: ModelType) -> ModelType:
        """Persist a new model instance and commit."""
        self.session.add(entity)
        await self.session.commit()
        await self.session.refresh(entity)
        return entity

    async def get_by_id(self, entity_id: Any) -> ModelType | None:
        """Fetch a single model instance by primary key."""
        return await self.session.get(self.model_cls, entity_id)

    async def list(self, offset: int = 0, limit: int = 100) -> Sequence[ModelType]:
        """Fetch paginated records ordered by primary key."""
        stmt = select(self.model_cls).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count(self) -> int:
        """Count total rows in the underlying table."""
        stmt = select(func.count()).select_from(self.model_cls)
        result = await self.session.execute(stmt)
        count_val = result.scalar()
        return count_val if count_val is not None else 0

    async def update(self, entity: ModelType) -> ModelType:
        """Commit pending changes on an existing instance and refresh."""
        self.session.add(entity)
        await self.session.commit()
        await self.session.refresh(entity)
        return entity

    async def delete(self, entity_id: Any) -> bool:
        """Delete an instance by primary key."""
        entity = await self.get_by_id(entity_id)
        if entity is None:
            return False
        await self.session.delete(entity)
        await self.session.commit()
        return True
