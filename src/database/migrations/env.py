"""Alembic migration environment configuration.

Configures offline and online migration runners, dynamically loading
connection parameters from src.core.config.get_settings().
"""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from src.core.config import get_settings
from src.database.models import Base

# Alembic Config object, which provides access to values within alembic.ini
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None and os.path.exists(config.config_file_name):
    fileConfig(config.config_file_name)

# Model MetaData for 'autogenerate' support
target_metadata = Base.metadata


def get_url() -> str:
    """Resolve database URL dynamically from application settings."""
    try:
        settings = get_settings()
        url = settings.DATABASE_URL
        # In offline or sync contexts, if asyncpg is present in URL, keep it or use standard postgresql
        return url
    except Exception:
        fallback_url = config.get_main_option(
            "sqlalchemy.url",
            "postgresql://apexmotion_app:local_dev_password@localhost:5432/apexmotion",
        )
        return fallback_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures context with just a URL and not an Engine, though an Engine is
    acceptable here as well. By skipping Engine creation we don't even need a DBAPI
    to be available.
    """
    url = get_url()
    # Replace asyncpg dialect for offline SQL generation to standard postgresql
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Helper executing migration run in sync worker thread."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode using async engine."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
