"""Unit tests for HITL approval token_hash unique index & anti-replay protection (P3-4).

Verifies:
- Database-level unique constraint on hitl_approvals.token_hash rejects duplicate tokens with IntegrityError.
- Schema introspection confirms idx_hitl_approvals_token_hash is registered with unique=True.
- HITLApprovalRepository.is_token_used detects previously used cryptographic tokens.
- HITLApprovalRepository.create_approval enforces anti-replay, raising TokenReplayError.
- Multi-action and cross-alert token reuse attempts are strictly prevented by the database constraint.
- Alignment across SQLAlchemy ORM models, Alembic baseline, and schema.sql DDL.
"""

import json
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from src.database.models import Base, HITLApproval, RiskAlert
from src.database.repositories.hitl_approval_repository import (
    HITLApprovalRepository,
    TokenReplayError,
)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """In-memory SQLite async session with foreign keys and unique constraints enforced."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        json_serializer=lambda obj: json.dumps(obj, default=str),
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_database_level_unique_constraint_enforcement(db_session: AsyncSession) -> None:
    """Verify database engine strictly raises IntegrityError when inserting duplicate token_hash."""
    shared_token_hash = "kms_ecdsa_sha256_nano_core_expedite_signature_hash_001"

    approval_1 = HITLApproval(
        id=uuid.uuid4(),
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("2448105.00"),
        spend_tier="DUAL_VP",
        token_hash=shared_token_hash,
        status="PENDING",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    db_session.add(approval_1)
    await db_session.commit()

    # Attempt to insert second approval with identical token_hash
    approval_2 = HITLApproval(
        id=uuid.uuid4(),
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("2448105.00"),
        spend_tier="DUAL_VP",
        token_hash=shared_token_hash,
        status="PENDING",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    db_session.add(approval_2)

    with pytest.raises(IntegrityError):
        await db_session.commit()

    await db_session.rollback()


@pytest.mark.asyncio
async def test_token_hash_index_catalog_introspection() -> None:
    """Verify SQLAlchemy engine metadata registers the unique index on hitl_approvals.token_hash."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        def _inspect_indexes(connection):
            inspector = inspect(connection)
            return inspector.get_indexes("hitl_approvals")

        indexes = await conn.run_sync(_inspect_indexes)

    token_hash_indexes = [idx for idx in indexes if "token_hash" in idx.get("column_names", [])]
    assert len(token_hash_indexes) >= 1, "No index found on hitl_approvals.token_hash"
    assert any(idx.get("unique") for idx in token_hash_indexes), (
        "Index on hitl_approvals.token_hash is not unique"
    )

    await engine.dispose()


@pytest.mark.asyncio
async def test_hitl_approval_repository_is_token_used(db_session: AsyncSession) -> None:
    """Verify repository detects whether a cryptographic token hash has been recorded."""
    repo = HITLApprovalRepository(db_session)
    token_hash = "token_hash_query_test_abc123"

    # Initially unused
    assert await repo.is_token_used(token_hash) is False

    # After record creation
    approval = HITLApproval(
        id=uuid.uuid4(),
        action_type="SPOT_BUY",
        amount_usd=Decimal("15000.00"),
        spend_tier="CATEGORY_MGR",
        token_hash=token_hash,
        status="PENDING",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    await repo.create(approval)

    # Now used
    assert await repo.is_token_used(token_hash) is True


@pytest.mark.asyncio
async def test_hitl_approval_repository_create_approval_anti_replay(
    db_session: AsyncSession,
) -> None:
    """Verify create_approval() pre-validates and raises TokenReplayError on duplicate tokens."""
    repo = HITLApprovalRepository(db_session)
    token_hash = "token_hash_anti_replay_test_7788"

    approval_1 = HITLApproval(
        id=uuid.uuid4(),
        action_type="SECONDARY_SOURCE",
        amount_usd=Decimal("75000.00"),
        spend_tier="PROC_DIRECTOR",
        token_hash=token_hash,
        status="PENDING",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    created = await repo.create_approval(approval_1)
    assert created.id == approval_1.id

    # Second creation attempt with same token_hash must raise TokenReplayError
    approval_replay = HITLApproval(
        id=uuid.uuid4(),
        action_type="SECONDARY_SOURCE",
        amount_usd=Decimal("75000.00"),
        spend_tier="PROC_DIRECTOR",
        token_hash=token_hash,
        status="PENDING",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    with pytest.raises(TokenReplayError, match="Replay detected for token hash"):
        await repo.create_approval(approval_replay)


@pytest.mark.asyncio
async def test_multi_action_and_cross_alert_token_isolation(
    db_session: AsyncSession,
) -> None:
    """Verify token_hash uniqueness is global across different alerts and action types."""
    repo = HITLApprovalRepository(db_session)

    alert_1_id = uuid.uuid4()
    alert_2_id = uuid.uuid4()
    reused_token = "reused_kms_token_hash_global_isolation_check"

    alert_1 = RiskAlert(id=alert_1_id, component_sku="MCU-X91", risk_level="CRITICAL")
    alert_2 = RiskAlert(id=alert_2_id, component_sku="BATTERY-CEL-01", risk_level="HIGH")
    db_session.add(alert_1)
    db_session.add(alert_2)
    await db_session.commit()

    # Valid approval for Alert 1
    app_1 = HITLApproval(
        id=uuid.uuid4(),
        alert_id=alert_1_id,
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("25000.00"),
        spend_tier="CATEGORY_MGR",
        token_hash=reused_token,
        status="APPROVED",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    await repo.create(app_1)

    # Replay attack: Attacker attempts to reuse app_1's token on Alert 2 with a different action
    app_2 = HITLApproval(
        id=uuid.uuid4(),
        alert_id=alert_2_id,
        action_type="SPOT_BUY",
        amount_usd=Decimal("12000.00"),
        spend_tier="CATEGORY_MGR",
        token_hash=reused_token,
        status="PENDING",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(app_2)
    with pytest.raises(IntegrityError):
        await db_session.commit()

    await db_session.rollback()


def test_schema_sql_and_migration_index_alignment() -> None:
    """Verify that schema.sql and Alembic migration explicitly declare the unique index name."""
    from pathlib import Path

    schema_sql_path = Path("schema.sql")
    assert schema_sql_path.exists()
    content_sql = schema_sql_path.read_text()
    assert "idx_hitl_approvals_token_hash" in content_sql
    assert "UNIQUE INDEX" in content_sql

    migration_path = Path("src/database/migrations/versions/0001_initial_schema.py")
    assert migration_path.exists()
    content_migration = migration_path.read_text()
    assert "idx_hitl_approvals_token_hash" in content_migration
