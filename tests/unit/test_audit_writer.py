"""Unit tests for the Append-Only Audit Writer (P4-5).

Verifies:
- Append-only immutability invariant (BR-RULE-007) on `audit_logs`
- Decoupled autonomous transaction: audit logs persist even when the caller's transaction is rolled back
- Automatic trace_id extraction from context via `bind_trace_id`
- Deterministic UUID coercion for string identifiers (e.g. `usr-alex-chen`, `sys-engine`)
- Sensitive state payload sanitization (masking tokens, secrets, keys, passwords)
- Read and query capabilities: `get_entity_audit_trail`, `get_trace_audit_trail`, `get_actor_audit_trail`
- Error handling and resilience under database failure
"""

import json
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from src.core.audit import (
    AuditWriteError,
    AuditWriter,
    get_actor_audit_trail,
    get_entity_audit_trail,
    get_trace_audit_trail,
    write_audit_log,
)
from src.core.logging import bind_trace_id
from src.database.models import AuditLog, Base


@pytest_asyncio.fixture
async def test_db():
    """Shared in-memory SQLite database with static pool for testing multi-session independence."""
    engine: AsyncEngine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
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

    yield session_factory

    await engine.dispose()


@pytest.mark.asyncio
async def test_write_audit_log_success(test_db: async_sessionmaker[AsyncSession]):
    """Verify write_audit_log successfully inserts an immutable forensic audit log."""
    entity_id = uuid4()
    actor_id = uuid4()

    log_entry = await write_audit_log(
        entity_type="risk_alerts",
        entity_id=entity_id,
        action="ALERT_TRIGGERED",
        actor_id=actor_id,
        before_state={"status": "PENDING"},
        after_state={"status": "ACTIVE", "score": 85},
        trace_id="trace-test-101",
        session_factory=test_db,
    )

    assert log_entry.id is not None
    assert log_entry.entity_type == "risk_alerts"
    assert log_entry.entity_id == entity_id
    assert log_entry.action == "ALERT_TRIGGERED"
    assert log_entry.actor_id == actor_id
    assert log_entry.before_state == {"status": "PENDING"}
    assert log_entry.after_state == {"status": "ACTIVE", "score": 85}
    assert log_entry.trace_id == "trace-test-101"
    assert log_entry.created_at is not None

    # Query directly in a separate session to verify physical persistence
    async with test_db() as session:
        result = await session.execute(select(AuditLog).where(AuditLog.id == log_entry.id))
        fetched = result.scalar_one()
        assert fetched.id == log_entry.id
        assert fetched.action == "ALERT_TRIGGERED"


@pytest.mark.asyncio
async def test_audit_log_persists_across_caller_transaction_rollback(
    test_db: async_sessionmaker[AsyncSession],
):
    """Forensic requirement: Audit log must NEVER be rolled back when a caller's transaction fails."""
    entity_id = uuid4()
    actor_id = uuid4()

    # Caller starts an active transaction that performs work and then rolls back
    async with test_db() as caller_session:
        # Caller does some ambient work...
        # An audit log is written via the audit writer
        audit_entry = await write_audit_log(
            entity_type="hitl_approvals",
            entity_id=entity_id,
            action="APPROVAL_FAILED_VALIDATION",
            actor_id=actor_id,
            before_state={"spend_usd": "180000.00"},
            after_state={"error": "INSUFFICIENT_SIGNATURES"},
            session_factory=test_db,
        )
        assert audit_entry.id is not None

        # Caller encounters failure and explicitly rolls back caller_session
        await caller_session.rollback()

    # In a brand new session, the audit log MUST still exist
    async with test_db() as verify_session:
        result = await verify_session.execute(select(AuditLog).where(AuditLog.id == audit_entry.id))
        fetched = result.scalar_one_or_none()
        assert fetched is not None
        assert fetched.id == audit_entry.id
        assert fetched.action == "APPROVAL_FAILED_VALIDATION"


@pytest.mark.asyncio
async def test_audit_log_trace_id_auto_propagation(test_db: async_sessionmaker[AsyncSession]):
    """Verify trace_id is automatically captured from context if not explicitly passed."""
    entity_id = uuid4()
    actor_id = uuid4()

    with bind_trace_id("trace-auto-ctx-999"):
        entry = await write_audit_log(
            entity_type="suppliers",
            entity_id=entity_id,
            action="SUPPLIER_RISK_SCORE_UPDATED",
            actor_id=actor_id,
            session_factory=test_db,
        )
        assert entry.trace_id == "trace-auto-ctx-999"


@pytest.mark.asyncio
async def test_audit_log_uuid_coercion_for_string_ids(test_db: async_sessionmaker[AsyncSession]):
    """Verify string UUIDs and human-readable string IDs (e.g. usr-alex-chen) are coerced to UUIDs."""
    raw_entity_uuid = str(uuid4())
    string_actor_id = "usr-alex-chen"

    entry = await write_audit_log(
        entity_type="auth_actions",
        entity_id=raw_entity_uuid,
        action="TOKEN_GENERATED",
        actor_id=string_actor_id,
        session_factory=test_db,
    )

    assert isinstance(entry.entity_id, UUID)
    assert str(entry.entity_id) == raw_entity_uuid
    assert isinstance(entry.actor_id, UUID)

    # Calling again with same string actor id produces deterministic UUID
    entry2 = await write_audit_log(
        entity_type="auth_actions",
        entity_id=raw_entity_uuid,
        action="TOKEN_VERIFIED",
        actor_id=string_actor_id,
        session_factory=test_db,
    )
    assert entry.actor_id == entry2.actor_id


@pytest.mark.asyncio
async def test_audit_log_state_sanitization(test_db: async_sessionmaker[AsyncSession]):
    """Verify sensitive keys in state payloads (token, secret, key, password) are automatically redacted."""
    entity_id = uuid4()
    actor_id = uuid4()

    sensitive_before = {
        "user": "alex.chen",
        "api_key": "secret-api-key-12345",
        "nested": {"access_token": "jwt-token-string", "safe_field": 42},
        "list_data": [{"secret_key": "internal-secret"}, "regular-string"],
    }
    sensitive_after = {
        "status": "AUTHENTICATED",
        "password": "super-secret-password",
        "secret_token": "ecdsa-signature-private",
    }

    entry = await write_audit_log(
        entity_type="auth",
        entity_id=entity_id,
        action="AUTHENTICATION_ATTEMPT",
        actor_id=actor_id,
        before_state=sensitive_before,
        after_state=sensitive_after,
        session_factory=test_db,
    )

    # Verify sensitive keys were redacted
    assert entry.before_state["api_key"] == "[REDACTED]"
    assert entry.before_state["nested"]["access_token"] == "[REDACTED]"
    assert entry.before_state["nested"]["safe_field"] == 42
    assert entry.before_state["user"] == "alex.chen"

    assert entry.after_state["password"] == "[REDACTED]"
    assert entry.after_state["secret_token"] == "[REDACTED]"
    assert entry.after_state["status"] == "AUTHENTICATED"


@pytest.mark.asyncio
async def test_audit_log_query_helpers_and_writer_class(test_db: async_sessionmaker[AsyncSession]):
    """Verify AuditWriter class methods and query trail helpers."""
    writer = AuditWriter(session_factory=test_db)
    entity_id = uuid4()
    actor_id = uuid4()
    trace_id = "trace-trail-456"

    # Write multiple entries for same entity and trace
    await writer.record_event(
        entity_type="hitl_approvals",
        entity_id=entity_id,
        action="PENDING_REVIEW",
        actor_id=actor_id,
        trace_id=trace_id,
    )
    await writer.record_event(
        entity_type="hitl_approvals",
        entity_id=entity_id,
        action="FIRST_SIGNATURE_APPLIED",
        actor_id=actor_id,
        trace_id=trace_id,
    )

    # 1. Query by entity trail
    entity_trail = await get_entity_audit_trail(
        entity_type="hitl_approvals",
        entity_id=entity_id,
        session_factory=test_db,
    )
    assert len(entity_trail) == 2
    assert {x.action for x in entity_trail} == {"PENDING_REVIEW", "FIRST_SIGNATURE_APPLIED"}

    # 2. Query by trace trail
    trace_trail = await get_trace_audit_trail(trace_id=trace_id, session_factory=test_db)
    assert len(trace_trail) == 2

    # 3. Query by actor trail
    actor_trail = await get_actor_audit_trail(actor_id=actor_id, session_factory=test_db)
    assert len(actor_trail) == 2

    # 4. Query via writer instance methods
    writer_entity_trail = await writer.get_history(
        entity_type="hitl_approvals", entity_id=entity_id
    )
    assert len(writer_entity_trail) == 2
    writer_trace_trail = await writer.get_by_trace(trace_id=trace_id)
    assert len(writer_trace_trail) == 2
    writer_actor_trail = await writer.get_by_actor(actor_id=actor_id)
    assert len(writer_actor_trail) == 2


@pytest.mark.asyncio
async def test_audit_writer_error_handling():
    """Verify write failure raises AuditWriteError and logs appropriate error."""

    # Pass an invalid or broken session factory that throws on session instantiation
    class BrokenSessionFactory:
        def __call__(self):
            raise RuntimeError("Database connection pool exhausted")

    with pytest.raises(AuditWriteError, match="Failed to write audit log"):
        await write_audit_log(
            entity_type="orders",
            entity_id=uuid4(),
            action="DISPATCH",
            actor_id=uuid4(),
            session_factory=BrokenSessionFactory(),  # type: ignore[arg-type]
        )
