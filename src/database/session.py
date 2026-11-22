"""Async database engine and session factory management for ApexMotion platform.

Provides:
- Async SQLAlchemy engine initialization.
- Async sessionmaker factory.
- FastAPI dependency / context manager `get_db_session()`.
"""

import json
from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import get_settings


def _default_json_serializer(obj: object) -> str:
    """Serialize objects to JSON with fallback to string for UUID and datetime."""
    return json.dumps(obj, default=str)


@lru_cache(maxsize=1)
def get_async_engine() -> AsyncEngine:
    """Create or return the cached singleton AsyncEngine."""
    settings = get_settings()
    database_url = settings.DATABASE_URL

    connect_args: dict[str, bool] = {}
    if "sqlite" in database_url:
        connect_args["check_same_thread"] = False

    return create_async_engine(
        database_url,
        echo=False,
        future=True,
        pool_pre_ping=True if "sqlite" not in database_url else False,
        connect_args=connect_args,
        json_serializer=_default_json_serializer,
    )


@lru_cache(maxsize=1)
def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    """Create or return the cached async session factory."""
    engine = get_async_engine()
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency and async context manager yielding an AsyncSession.

    Ensures transaction rollback on unhandled exceptions and session closure on exit.
    """
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
