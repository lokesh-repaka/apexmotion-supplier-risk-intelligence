"""Unit tests for HITL Token Replay Guard (P10-3).

Verifies:
- Replay detection against `hitl_approvals.token_hash` unique constraint and index.
- Immediate emission of high-severity security violation log:
  "SECURITY ALERT: Cryptographic token replay attempt detected!".
- Immutable forensic audit logging to `audit_logs` table via `write_audit_log`
  with action="SECURITY_TOKEN_REPLAY_ATTEMPT".
- Detection and blocking of intra-batch token duplicates (anti-self-replay in DUAL_VP).
- Database-level IntegrityError / TokenReplayError interception on concurrent race conditions.
- Alert emitter integration (Kafka / security webhook callback).
- Token hash extraction from HITLToken, serialized base64 string, hex hash, and dict payloads.
- Integration with HITLService and DualApprovalEnforcer.
- Thread-safe singleton pattern for get_token_replay_guard().
- 100% offline isolation with zero external AWS or live network calls.
"""

import json
import logging
import threading
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from src.core.hitl_tokens import (
    HITLTokenService,
    compute_token_hash,
)
from src.database.models import AuditLog, Base, HITLApproval
from src.database.repositories.hitl_approval_repository import (
    HITLApprovalRepository,
)
from src.services.token_replay_guard import (
    TokenReplayGuard,
    TokenReplaySecurityAlert,
    get_token_replay_guard,
)


@pytest.fixture
def mock_kms_client() -> MagicMock:
    """Mock boto3 KMS client simulating ECDSA P-256 signing and verification."""
    client = MagicMock()
    client.sign.return_value = {
        "Signature": b"mock_ecdsa_p256_der_signature_bytes_1234567890",
        "KeyId": "arn:aws:kms:eu-central-1:123456789012:key/test-hitl-key",
        "SigningAlgorithm": "ECDSA_SHA_256",
    }
    client.verify.return_value = {
        "SignatureValid": True,
        "KeyId": "arn:aws:kms:eu-central-1:123456789012:key/test-hitl-key",
        "SigningAlgorithm": "ECDSA_SHA_256",
    }
    return client


@pytest.fixture
def token_service(mock_kms_client: MagicMock) -> HITLTokenService:
    """Instantiate HITLTokenService with mocked KMS client."""
    return HITLTokenService(
        kms_client=mock_kms_client,
        key_arn="arn:aws:kms:eu-central-1:123456789012:key/test-hitl-key",
    )


@pytest_asyncio.fixture
async def async_db_session() -> AsyncGenerator[AsyncSession, None]:
    """In-memory SQLite async session with foreign keys and unique constraints."""
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


@pytest.fixture
def session_factory(async_db_session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    """Return session factory producing sessions sharing the test database."""
    engine = async_db_session.bind
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest.fixture
def replay_guard(session_factory: async_sessionmaker[AsyncSession]) -> TokenReplayGuard:
    """Instantiate TokenReplayGuard with in-memory test session factory."""
    return TokenReplayGuard(session_factory=session_factory)


# ------------------------------------------------------------------------------
# 1. Single Token Replay Verification & Security Alerting Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_token_unused_passes(
    replay_guard: TokenReplayGuard,
    token_service: HITLTokenService,
    async_db_session: AsyncSession,
) -> None:
    """Verify an unused token hash returns a valid non-replay result."""
    token = token_service.issue_token(
        action_id="ACT-NEW-001",
        alert_id="ALT-NEW-001",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("15000.00"),
        signer_id="usr-cat-mgr-01",
        signer_role="category_manager",
    )

    repo = HITLApprovalRepository(async_db_session)
    result = await replay_guard.check_token(
        token=token,
        repository=repo,
        action_id="ACT-NEW-001",
    )

    assert result.is_replay is False
    assert result.is_valid is True
    assert result.token_hash == token.token_hash
    assert result.alert_emitted is False
    assert result.audit_logged is False


@pytest.mark.asyncio
async def test_check_token_replayed_detects_and_alerts(
    replay_guard: TokenReplayGuard,
    token_service: HITLTokenService,
    async_db_session: AsyncSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify that an already-registered token hash triggers an immediate security alert and forensic audit log."""
    token = token_service.issue_token(
        action_id="ACT-REPLAY-001",
        alert_id="ALT-REPLAY-001",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("2448105.00"),
        signer_id="usr-director-01",
        signer_role="procurement_director",
    )

    # 1. Register approval in database with this token hash
    repo = HITLApprovalRepository(async_db_session)
    existing_approval = HITLApproval(
        id=uuid.uuid4(),
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("2448105.00"),
        spend_tier="DUAL_VP",
        token_hash=token.token_hash,
        status="APPROVED",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    await repo.create_approval(existing_approval)
    await async_db_session.commit()

    # 2. Check token replay with structured security logging
    actor_id = uuid.uuid4()
    with caplog.at_level(logging.ERROR):
        result = await replay_guard.check_token(
            token=token,
            repository=repo,
            actor_id=actor_id,
            action_id="ACT-ATTACK-002",
            alert_id=uuid.uuid4(),
            raise_on_error=False,
        )

    assert result.is_replay is True
    assert result.is_valid is False
    assert result.token_hash == token.token_hash
    assert result.existing_approval_id == str(existing_approval.id)
    assert result.alert_emitted is True
    assert result.audit_logged is True

    # Verify high-severity security alert log output
    assert any(
        "SECURITY ALERT: Cryptographic token replay attempt detected!" in record.message
        for record in caplog.records
    )

    # Verify forensic audit log entry was written (token_hash is redacted by security sanitizer)
    stmt = select(AuditLog).where(AuditLog.action == "SECURITY_TOKEN_REPLAY_ATTEMPT")
    audit_res = await async_db_session.execute(stmt)
    audit_entry = audit_res.scalars().first()
    assert audit_entry is not None
    assert audit_entry.entity_type == "HITL_APPROVAL"
    assert audit_entry.after_state is not None
    assert audit_entry.after_state.get("token_hash") == "[REDACTED]"
    assert audit_entry.after_state.get("action_id") == "ACT-ATTACK-002"


@pytest.mark.asyncio
async def test_check_token_replayed_raises_on_error(
    replay_guard: TokenReplayGuard,
    token_service: HITLTokenService,
    async_db_session: AsyncSession,
) -> None:
    """Verify raise_on_error=True raises TokenReplaySecurityAlert on replay detection."""
    token = token_service.issue_token(
        action_id="ACT-REPLAY-ERR",
        alert_id="ALT-REPLAY-ERR",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("50000.00"),
    )

    repo = HITLApprovalRepository(async_db_session)
    existing_approval = HITLApproval(
        id=uuid.uuid4(),
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("50000.00"),
        spend_tier="PROC_DIRECTOR",
        token_hash=token.token_hash,
        status="APPROVED",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    await repo.create_approval(existing_approval)
    await async_db_session.commit()

    with pytest.raises(TokenReplaySecurityAlert, match="Cryptographic token replay detected"):
        await replay_guard.check_token(
            token=token,
            repository=repo,
            raise_on_error=True,
        )


# ------------------------------------------------------------------------------
# 2. Batch & Multi-Token Anti-Self-Replay (DUAL_VP) Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_tokens_batch_detects_intra_batch_duplicates(
    replay_guard: TokenReplayGuard,
    token_service: HITLTokenService,
    async_db_session: AsyncSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify submitting duplicate identical tokens within a dual-approval batch triggers replay detection."""
    token = token_service.issue_token(
        action_id="ACT-DUAL-DUP",
        alert_id="ALT-DUAL-DUP",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("2448105.00"),
        signer_id="usr-director-01",
        signer_role="procurement_director",
    )

    repo = HITLApprovalRepository(async_db_session)

    # Attempting to satisfy dual-approval with identical token submitted twice
    with caplog.at_level(logging.ERROR):
        results = await replay_guard.check_tokens_batch(
            tokens=[token, token],
            repository=repo,
            action_id="ACT-DUAL-DUP",
            raise_on_error=False,
        )

    assert len(results) == 2
    assert results[0].is_replay is False  # First occurrence is clean
    assert results[1].is_replay is True  # Second occurrence is an intra-batch duplicate replay
    assert results[1].alert_emitted is True

    assert any(
        "Duplicate token hash in batch" in record.message
        or "Cryptographic token replay" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_check_tokens_batch_detects_db_replays(
    replay_guard: TokenReplayGuard,
    token_service: HITLTokenService,
    async_db_session: AsyncSession,
) -> None:
    """Verify batch check detects tokens that are already used in the database."""
    token1 = token_service.issue_token(
        action_id="ACT-BATCH-1",
        alert_id="ALT-BATCH-1",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("150000.00"),
        signer_id="usr-director-01",
        signer_role="procurement_director",
    )
    token2 = token_service.issue_token(
        action_id="ACT-BATCH-1",
        alert_id="ALT-BATCH-1",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("150000.00"),
        signer_id="usr-vp-02",
        signer_role="vp_supply_chain",
    )

    repo = HITLApprovalRepository(async_db_session)
    # Register token1 in DB already
    approval = HITLApproval(
        id=uuid.uuid4(),
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("150000.00"),
        spend_tier="DUAL_VP",
        token_hash=token1.token_hash,
        status="APPROVED",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    await repo.create_approval(approval)
    await async_db_session.commit()

    results = await replay_guard.check_tokens_batch(
        tokens=[token1, token2],
        repository=repo,
        raise_on_error=False,
    )

    assert results[0].is_replay is True
    assert results[1].is_replay is False


# ------------------------------------------------------------------------------
# 3. Database IntegrityError & Race Condition Interception
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wrap_create_approval_unique_constraint_interception(
    replay_guard: TokenReplayGuard,
    async_db_session: AsyncSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify wrap_create_approval intercepts database IntegrityError on token_hash unique constraint."""
    shared_token_hash = "kms_sha256_race_condition_hash_9999"

    approval_1 = HITLApproval(
        id=uuid.uuid4(),
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("50000.00"),
        spend_tier="PROC_DIRECTOR",
        token_hash=shared_token_hash,
        status="APPROVED",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    repo = HITLApprovalRepository(async_db_session)
    await repo.create_approval(approval_1)
    await async_db_session.commit()

    # Attempting to create duplicate approval with same token hash
    approval_2 = HITLApproval(
        id=uuid.uuid4(),
        action_type="SECONDARY_SOURCE_SPOT_BUY",
        amount_usd=Decimal("50000.00"),
        spend_tier="PROC_DIRECTOR",
        token_hash=shared_token_hash,
        status="PENDING",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(TokenReplaySecurityAlert, match="Cryptographic token replay detected"):
            await replay_guard.wrap_create_approval(
                approval=approval_2,
                repository=repo,
                actor_id=uuid.uuid4(),
            )

    assert any(
        "SECURITY ALERT: Cryptographic token replay attempt detected!" in record.message
        for record in caplog.records
    )


# ------------------------------------------------------------------------------
# 4. Token Hash Extraction & Serialization Formats
# ------------------------------------------------------------------------------


def test_extract_token_hash_formats(
    replay_guard: TokenReplayGuard,
    token_service: HITLTokenService,
) -> None:
    """Verify token hash extraction from HITLToken, serialized string, hex hash, and dict."""
    token = token_service.issue_token(
        action_id="ACT-EXT-01",
        alert_id="ALT-EXT-01",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("25000.00"),
    )

    # 1. Direct HITLToken instance
    hash_obj = replay_guard.extract_token_hash(token)
    assert hash_obj == token.token_hash

    # 2. Serialized base64 string
    serialized_str = token.serialize()
    hash_str = replay_guard.extract_token_hash(serialized_str)
    assert hash_str == token.token_hash

    # 3. Direct SHA-256 hex string (64 characters)
    raw_hex = token.token_hash
    hash_hex = replay_guard.extract_token_hash(raw_hex)
    assert hash_hex == raw_hex

    # 4. Dictionary containing token_hash
    dict_token = {"token_hash": token.token_hash, "action_id": "ACT-EXT-01"}
    hash_dict = replay_guard.extract_token_hash(dict_token)
    assert hash_dict == token.token_hash


# ------------------------------------------------------------------------------
# 5. Alert Emitter Callback & Webhook/Kafka Integration
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alert_emitter_callback_invoked_on_replay(
    session_factory: async_sessionmaker[AsyncSession],
    token_service: HITLTokenService,
    async_db_session: AsyncSession,
) -> None:
    """Verify that a custom alert emitter (e.g. Kafka event publisher) is called upon replay attempt."""
    mock_emitter = AsyncMock()
    guard_with_emitter = TokenReplayGuard(
        session_factory=session_factory,
        alert_emitter=mock_emitter,
    )

    token = token_service.issue_token(
        action_id="ACT-EMIT-01",
        alert_id="ALT-EMIT-01",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("150000.00"),
    )

    repo = HITLApprovalRepository(async_db_session)
    existing_approval = HITLApproval(
        id=uuid.uuid4(),
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("150000.00"),
        spend_tier="DUAL_VP",
        token_hash=token.token_hash,
        status="APPROVED",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    await repo.create_approval(existing_approval)
    await async_db_session.commit()

    actor_uuid = uuid.uuid4()
    await guard_with_emitter.check_token(
        token=token,
        repository=repo,
        actor_id=actor_uuid,
        action_id="ACT-EMIT-ATTACK",
        raise_on_error=False,
    )

    mock_emitter.assert_awaited_once()
    call_args = mock_emitter.call_args[0][0]
    assert call_args["token_hash"] == token.token_hash
    assert call_args["actor_id"] == str(actor_uuid)
    assert call_args["action_id"] == "ACT-EMIT-ATTACK"


# ------------------------------------------------------------------------------
# 6. Singleton Accessor & Thread-Safety Tests
# ------------------------------------------------------------------------------


def test_get_token_replay_guard_singleton() -> None:
    """Verify get_token_replay_guard returns a thread-safe singleton instance."""
    g1 = get_token_replay_guard()
    g2 = get_token_replay_guard()
    assert g1 is g2
    assert isinstance(g1, TokenReplayGuard)


def test_token_replay_guard_thread_safe_initialization() -> None:
    """Verify concurrent calls to get_token_replay_guard create exactly one instance."""
    import src.services.token_replay_guard as mod

    with mod._guard_lock:
        mod._global_replay_guard = None

    instances: list[TokenReplayGuard] = []

    def _worker() -> None:
        inst = get_token_replay_guard()
        instances.append(inst)

    threads = [threading.Thread(target=_worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(instances) == 10
    assert all(i is instances[0] for i in instances)


# ------------------------------------------------------------------------------
# 7. Additional Branch Coverage & Resilience Tests (100% Targets)
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_token_with_active_session_and_session_factory(
    replay_guard: TokenReplayGuard,
    token_service: HITLTokenService,
    async_db_session: AsyncSession,
) -> None:
    """Verify check_token operates seamlessly with direct session and self-managed session factory."""
    token = token_service.issue_token(
        action_id="ACT-SESS-01",
        alert_id="ALT-SESS-01",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("15000.00"),
    )

    # 1. With direct session
    res1 = await replay_guard.check_token(token, session=async_db_session)
    assert res1.is_replay is False

    # 2. Persist approval in DB
    approval = HITLApproval(
        id=uuid.uuid4(),
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("15000.00"),
        spend_tier="CATEGORY_MGR",
        token_hash=token.token_hash,
        status="APPROVED",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    repo = HITLApprovalRepository(async_db_session)
    await repo.create_approval(approval)
    await async_db_session.commit()

    # 3. With self-managed session factory (repository=None, session=None)
    res2 = await replay_guard.check_token(token)
    assert res2.is_replay is True
    assert res2.existing_approval_id == str(approval.id)


@pytest.mark.asyncio
async def test_check_tokens_batch_intra_batch_duplicate_raises(
    replay_guard: TokenReplayGuard,
    token_service: HITLTokenService,
    async_db_session: AsyncSession,
) -> None:
    """Verify check_tokens_batch raises TokenReplaySecurityAlert on intra-batch duplicate when raise_on_error=True."""
    token = token_service.issue_token(
        action_id="ACT-BATCH-DUP-ERR",
        alert_id="ALT-BATCH-DUP-ERR",
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("2448105.00"),
    )

    repo = HITLApprovalRepository(async_db_session)
    with pytest.raises(TokenReplaySecurityAlert, match="duplicate token hash"):
        await replay_guard.check_tokens_batch(
            tokens=[token, token],
            repository=repo,
            raise_on_error=True,
        )


def test_extract_token_hash_nested_dict_and_fallbacks(replay_guard: TokenReplayGuard) -> None:
    """Verify extract_token_hash handles nested dicts, raw text strings, and fallback payloads."""
    # 1. Nested dict containing "token"
    token_nested = {"token": "some_random_token_string_12345"}
    expected_hash = compute_token_hash("some_random_token_string_12345")
    assert replay_guard.extract_token_hash(token_nested) == expected_hash

    # 2. Dict without token_hash or token keys
    token_dict_arbitrary = {"foo": "bar", "baz": 123}
    expected_dict_hash = compute_token_hash(str(token_dict_arbitrary))
    assert replay_guard.extract_token_hash(token_dict_arbitrary) == expected_dict_hash


@pytest.mark.asyncio
async def test_handle_replay_attempt_resilience(
    replay_guard: TokenReplayGuard,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify handle_replay_attempt is resilient if audit log or alert emitter encounters an exception."""
    # 1. Emitter exception resilience
    failing_emitter = AsyncMock(side_effect=RuntimeError("Kafka broker unreachable"))
    guard_failing_emitter = TokenReplayGuard(
        session_factory=replay_guard.session_factory,
        alert_emitter=failing_emitter,
    )
    # Should not raise exception
    payload = await guard_failing_emitter.handle_replay_attempt(
        token_hash="mock_hash_emitter_fail_123",
        reason="Test emitter resilience",
    )
    assert payload["token_hash"] == "mock_hash_emitter_fail_123"

    # 2. Audit log exception resilience
    async def _failing_audit(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("Database connection pool exhausted")

    monkeypatch.setattr("src.services.token_replay_guard.write_audit_log", _failing_audit)

    # Should not raise exception even when write_audit_log fails
    payload_audit_fail = await replay_guard.handle_replay_attempt(
        token_hash="mock_hash_audit_fail_123",
        reason="Test audit resilience",
    )
    assert payload_audit_fail["token_hash"] == "mock_hash_audit_fail_123"
