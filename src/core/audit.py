"""Append-only forensic audit writer for ApexMotion platform (BR-RULE-007).

Enforces:
- Strict append-only immutability on `audit_logs` (zero UPDATE or DELETE operations)
- Autonomous transaction execution: audit entries are written using a dedicated,
  decoupled AsyncSession, ensuring they persist even if the caller's transaction
  subsequently rolls back due to error or business rejection
- Automatic distributed trace context capture via `src.core.logging.get_trace_id()`
- Deterministic UUID coercion for human-readable and system identity strings
- Automatic sanitization and masking of sensitive credentials in state payloads
"""

from collections.abc import Sequence
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, cast
from uuid import NAMESPACE_DNS, UUID, uuid5

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.logging import get_logger, get_trace_id
from src.database.models import AuditLog
from src.database.repositories.audit_log_repository import AuditLogRepository
from src.database.session import get_async_session_factory

logger = get_logger("apexmotion.audit")

# Sensitive keys to redact from audit state payloads
SENSITIVE_KEY_SUBSTRINGS = (
    "token",
    "secret",
    "password",
    "api_key",
    "private_key",
    "credential",
    "jwt",
    "auth_token",
)


# ------------------------------------------------------------------------------
# Exceptions
# ------------------------------------------------------------------------------


class AuditError(Exception):
    """Base exception for audit logging errors."""


class AuditWriteError(AuditError):
    """Raised when an audit record cannot be written to the database."""


# ------------------------------------------------------------------------------
# Helpers: UUID Coercion & State Payload Sanitization
# ------------------------------------------------------------------------------


def coerce_uuid(val: UUID | str) -> UUID:
    """Coerce a string or UUID into a valid UUID.

    If given a valid UUID or UUID string, parses it directly.
    If given a human-readable identifier (e.g. 'usr-alex-chen', 'sys-engine'),
    generates a deterministic UUID5 using the DNS namespace.
    """
    if isinstance(val, UUID):
        return val

    val_str = str(val).strip()
    try:
        return UUID(val_str)
    except ValueError:
        return uuid5(NAMESPACE_DNS, val_str)


def sanitize_audit_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Recursively redact sensitive credentials and keys from audit state payloads."""
    if payload is None:
        return None

    def _sanitize(item: Any) -> Any:
        if isinstance(item, dict):
            clean_dict: dict[str, Any] = {}
            for k, v in item.items():
                k_lower = str(k).lower()
                if any(sub in k_lower for sub in SENSITIVE_KEY_SUBSTRINGS):
                    clean_dict[k] = "[REDACTED]"
                else:
                    clean_dict[k] = _sanitize(v)
            return clean_dict
        if isinstance(item, list):
            return [_sanitize(elem) for elem in item]
        return item

    return cast(dict[str, Any], _sanitize(deepcopy(payload)))


# ------------------------------------------------------------------------------
# Core Audit Writer Logic (Autonomous Transaction)
# ------------------------------------------------------------------------------


async def write_audit_log(
    entity_type: str,
    entity_id: UUID | str,
    action: str,
    actor_id: UUID | str,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
    trace_id: str | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> AuditLog:
    """Write an immutable forensic audit log record in an independent transaction.

    CRITICAL ARCHITECTURAL INVARIANT:
    This function ALWAYS executes inside its own dedicated AsyncSession, never inside
    an ambient caller transaction. If an outer business operation fails and rolls
    back, this audit log remains committed and permanent in `audit_logs`.
    """
    factory = session_factory if session_factory is not None else get_async_session_factory()
    resolved_entity_id = coerce_uuid(entity_id)
    resolved_actor_id = coerce_uuid(actor_id)
    resolved_trace_id = trace_id or get_trace_id()

    clean_before = sanitize_audit_payload(before_state)
    clean_after = sanitize_audit_payload(after_state)

    audit_entry = AuditLog(
        entity_type=entity_type,
        entity_id=resolved_entity_id,
        action=action,
        actor_id=resolved_actor_id,
        before_state=clean_before,
        after_state=clean_after,
        trace_id=resolved_trace_id,
        created_at=datetime.now(UTC),
    )

    try:
        async with factory() as session:
            repo = AuditLogRepository(session)
            await repo.create(audit_entry)

        logger.info(
            "Forensic audit log written: action=%s entity=%s:%s actor=%s trace_id=%s",
            action,
            entity_type,
            resolved_entity_id,
            resolved_actor_id,
            resolved_trace_id,
        )
        return audit_entry
    except Exception as exc:
        logger.critical(
            "CRITICAL: Failed to write audit log entry [action=%s entity=%s:%s]: %s",
            action,
            entity_type,
            resolved_entity_id,
            exc,
            exc_info=True,
        )
        raise AuditWriteError(f"Failed to write audit log entry: {exc}") from exc


# ------------------------------------------------------------------------------
# Query Trail Helpers
# ------------------------------------------------------------------------------


async def get_entity_audit_trail(
    entity_type: str,
    entity_id: UUID | str,
    limit: int = 100,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> Sequence[AuditLog]:
    """Retrieve chronological audit trail for a specific entity."""
    factory = session_factory if session_factory is not None else get_async_session_factory()
    resolved_id = coerce_uuid(entity_id)
    async with factory() as session:
        repo = AuditLogRepository(session)
        return await repo.get_by_entity(entity_type=entity_type, entity_id=resolved_id, limit=limit)


async def get_trace_audit_trail(
    trace_id: str,
    limit: int = 100,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> Sequence[AuditLog]:
    """Retrieve all audit logs recorded during a specific distributed trace context."""
    factory = session_factory if session_factory is not None else get_async_session_factory()
    async with factory() as session:
        repo = AuditLogRepository(session)
        return await repo.get_by_trace_id(trace_id=trace_id, limit=limit)


async def get_actor_audit_trail(
    actor_id: UUID | str,
    limit: int = 100,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> Sequence[AuditLog]:
    """Retrieve all audit logs recorded for actions initiated by a specific actor."""
    factory = session_factory if session_factory is not None else get_async_session_factory()
    resolved_id = coerce_uuid(actor_id)
    async with factory() as session:
        repo = AuditLogRepository(session)
        return await repo.get_by_actor(actor_id=resolved_id, limit=limit)


# ------------------------------------------------------------------------------
# Class-Based Audit Writer
# ------------------------------------------------------------------------------


class AuditWriter:
    """High-level forensic audit writer service instance."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self.session_factory = session_factory

    async def record_event(
        self,
        entity_type: str,
        entity_id: UUID | str,
        action: str,
        actor_id: UUID | str,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> AuditLog:
        """Record an immutable audit event in an independent transaction."""
        return await write_audit_log(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_id=actor_id,
            before_state=before_state,
            after_state=after_state,
            trace_id=trace_id,
            session_factory=self.session_factory,
        )

    async def get_history(
        self,
        entity_type: str,
        entity_id: UUID | str,
        limit: int = 100,
    ) -> Sequence[AuditLog]:
        """Fetch audit log trail for an entity."""
        return await get_entity_audit_trail(
            entity_type=entity_type,
            entity_id=entity_id,
            limit=limit,
            session_factory=self.session_factory,
        )

    async def get_by_trace(
        self,
        trace_id: str,
        limit: int = 100,
    ) -> Sequence[AuditLog]:
        """Fetch audit log trail for a trace context."""
        return await get_trace_audit_trail(
            trace_id=trace_id,
            limit=limit,
            session_factory=self.session_factory,
        )

    async def get_by_actor(
        self,
        actor_id: UUID | str,
        limit: int = 100,
    ) -> Sequence[AuditLog]:
        """Fetch audit log trail for an actor."""
        return await get_actor_audit_trail(
            actor_id=actor_id,
            limit=limit,
            session_factory=self.session_factory,
        )
