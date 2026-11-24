"""Cryptographic Token Replay Guard Service (P10-3).

Enforces:
- Cryptographic anti-replay protection checking `hitl_approvals.token_hash` unique constraint and index.
- Immediate emission of high-severity security violation alert:
  "SECURITY ALERT: Cryptographic token replay attempt detected!".
- Forensic immutable audit logging to `audit_logs` table via `write_audit_log`
  with action="SECURITY_TOKEN_REPLAY_ATTEMPT" (BR-RULE-007).
- Multi-token intra-batch uniqueness verification (blocking anti-self-replay in DUAL_VP).
- Database-level IntegrityError / TokenReplayError interception for concurrent race condition safety.
- Optional alert emitter dispatch (Kafka security event / webhook callback).
- Thread-safe singleton accessor with double-checked locking.
"""

import threading
import uuid
from collections.abc import Callable, Coroutine, Mapping
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.audit import coerce_uuid, write_audit_log
from src.core.hitl_tokens import HITLToken, compute_token_hash
from src.core.logging import get_logger, get_trace_id
from src.database.models import HITLApproval
from src.database.repositories.hitl_approval_repository import (
    HITLApprovalRepository,
    TokenReplayError,
)
from src.database.session import get_async_session_factory

logger = get_logger("apexmotion.services.token_replay_guard")


# ------------------------------------------------------------------------------
# Exceptions Hierarchy
# ------------------------------------------------------------------------------


class TokenReplayGuardError(Exception):
    """Base exception for all token replay guard errors."""


class TokenReplaySecurityAlert(TokenReplayGuardError):
    """Raised when a cryptographic token replay attack is detected and alerted."""


# ------------------------------------------------------------------------------
# Models & Results
# ------------------------------------------------------------------------------


class TokenReplayCheckResult(BaseModel):
    """Structured result returned by token replay inspection."""

    token_hash: str = Field(..., description="SHA-256 hash of the evaluated token")
    is_replay: bool = Field(..., description="True if the token hash has already been used")
    is_valid: bool = Field(..., description="True if the token is clean and unused")
    existing_approval_id: str | None = Field(
        default=None, description="UUID string of existing approval record if replay detected"
    )
    existing_action_type: str | None = Field(
        default=None, description="Action type of existing approval record"
    )
    message: str | None = Field(default=None, description="Human-readable status summary")
    alert_emitted: bool = Field(
        default=False, description="True if security alert was logged and emitted"
    )
    audit_logged: bool = Field(default=False, description="True if forensic audit log was recorded")


# ------------------------------------------------------------------------------
# Token Replay Guard Service
# ------------------------------------------------------------------------------


class TokenReplayGuard:
    """Service governing cryptographic anti-replay validation and security incident alerting.

    Guarantees:
    - Every approval token hash is validated against hitl_approvals.token_hash unique constraint.
    - Any attempt to reuse a token hash emits a high-severity security log and forensic audit entry.
    - Race condition integrity errors from concurrent requests are intercepted, rolled back, and alerted.
    - Intra-batch identical token hashes in multi-token approvals (e.g., DUAL_VP) are immediately blocked.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        alert_emitter: (Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None) = None,
    ) -> None:
        """Initialize with injectable session factory and alert emitter callback."""
        self.session_factory = session_factory
        self.alert_emitter = alert_emitter

    def _get_session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Lazily initialize database session factory if not injected."""
        if self.session_factory is None:
            self.session_factory = get_async_session_factory()
        return self.session_factory

    def extract_token_hash(self, token: str | HITLToken | Mapping[str, Any]) -> str:
        """Extract or compute deterministic SHA-256 token hash from supported formats."""
        if isinstance(token, HITLToken):
            return token.token_hash
        if isinstance(token, Mapping):
            if "token_hash" in token and token["token_hash"]:
                return str(token["token_hash"])
            if "token" in token and token["token"]:
                return self.extract_token_hash(
                    cast(str | HITLToken | Mapping[str, Any], token["token"])
                )
            return compute_token_hash(str(token))

        token_str = str(token).strip()
        # If it is already a 64-character hexadecimal SHA-256 string
        if len(token_str) == 64 and all(c in "0123456789abcdefABCDEF" for c in token_str):
            return token_str.lower()

        # Try deserializing if base64 serialized HITLToken
        try:
            parsed = HITLToken.deserialize(token_str)
            return parsed.token_hash
        except Exception:
            # Fallback to computing SHA-256 hash of token string
            return compute_token_hash(token_str)

    async def handle_replay_attempt(
        self,
        token_hash: str,
        actor_id: UUID | str | None = None,
        action_id: str | None = None,
        alert_id: UUID | str | None = None,
        reason: str = "Duplicate token hash detected in hitl_approvals",
        existing_approval: HITLApproval | None = None,
        context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Centralized handler for cryptographic replay incidents: logs, audits, and alerts."""
        trace_id = get_trace_id()
        actor_str = str(actor_id) if actor_id else "UNKNOWN_ACTOR"
        action_str = str(action_id) if action_id else "UNKNOWN_ACTION"
        alert_str = str(alert_id) if alert_id else "UNKNOWN_ALERT"
        now = datetime.now(UTC)

        # 1. Immediate High-Severity Security Alert Logging
        logger.error(
            "SECURITY ALERT: Cryptographic token replay attempt detected! "
            "[token_hash=%s, actor_id=%s, target_action_id=%s, target_alert_id=%s, trace_id=%s, reason=%s]",
            token_hash,
            actor_str,
            action_str,
            alert_str,
            trace_id,
            reason,
        )

        alert_payload: dict[str, Any] = {
            "security_incident": "HITL_TOKEN_REPLAYED",
            "token_hash": token_hash,
            "actor_id": actor_str,
            "action_id": action_str,
            "alert_id": alert_str,
            "timestamp": now.isoformat(),
            "trace_id": trace_id,
            "reason": reason,
        }
        if existing_approval is not None:
            alert_payload["existing_approval_id"] = str(existing_approval.id)
            alert_payload["existing_action_type"] = existing_approval.action_type
            alert_payload["existing_status"] = existing_approval.status
        if context:
            alert_payload["context"] = dict(context)

        # 2. Immutable Forensic Audit Log in dedicated transaction (BR-RULE-007)
        try:
            audit_entity_id = (
                existing_approval.id
                if existing_approval is not None
                else (coerce_uuid(alert_id) if alert_id else uuid.uuid4())
            )
            audit_factory = self.session_factory if self.session_factory is not None else None
            await write_audit_log(
                entity_type="HITL_APPROVAL",
                entity_id=audit_entity_id,
                action="SECURITY_TOKEN_REPLAY_ATTEMPT",
                actor_id=actor_str,
                before_state={"status": "APPROVED", "token_hash": token_hash}
                if existing_approval
                else None,
                after_state=alert_payload,
                trace_id=trace_id,
                session_factory=audit_factory,
            )
        except Exception as exc:
            logger.critical(
                "CRITICAL: Failed to write security replay forensic audit log: %s",
                exc,
                exc_info=True,
            )

        # 3. Optional Alert Emitter Callback (Kafka publisher / webhook)
        if self.alert_emitter is not None:
            try:
                await self.alert_emitter(alert_payload)
            except Exception as exc:
                logger.error("Failed to dispatch security alert to emitter: %s", exc)

        return alert_payload

    async def check_token(
        self,
        token: str | HITLToken | Mapping[str, Any],
        repository: HITLApprovalRepository | None = None,
        session: AsyncSession | None = None,
        actor_id: UUID | str | None = None,
        action_id: str | None = None,
        alert_id: UUID | str | None = None,
        raise_on_error: bool = False,
    ) -> TokenReplayCheckResult:
        """Verify token hash uniqueness against repository or active session.

        If a replay is detected, immediately emits a security alert and audit entry.
        """
        token_hash = self.extract_token_hash(token)
        existing_approval: HITLApproval | None = None

        if repository is not None:
            existing_approval = await repository.get_by_token_hash(token_hash)
        elif session is not None:
            repo = HITLApprovalRepository(session)
            existing_approval = await repo.get_by_token_hash(token_hash)
        else:
            factory = self._get_session_factory()
            async with factory() as active_session:
                repo = HITLApprovalRepository(active_session)
                existing_approval = await repo.get_by_token_hash(token_hash)

        if existing_approval is not None:
            await self.handle_replay_attempt(
                token_hash=token_hash,
                actor_id=actor_id,
                action_id=action_id,
                alert_id=alert_id,
                reason=f"Token hash already registered on approval {existing_approval.id}",
                existing_approval=existing_approval,
            )

            if raise_on_error:
                raise TokenReplaySecurityAlert(
                    f"Cryptographic token replay detected: token hash '{token_hash}' has already been registered."
                )

            return TokenReplayCheckResult(
                token_hash=token_hash,
                is_replay=True,
                is_valid=False,
                existing_approval_id=str(existing_approval.id),
                existing_action_type=existing_approval.action_type,
                message=f"Token hash {token_hash} already used on approval {existing_approval.id}.",
                alert_emitted=True,
                audit_logged=True,
            )

        return TokenReplayCheckResult(
            token_hash=token_hash,
            is_replay=False,
            is_valid=True,
            message="Token hash is unused and valid.",
            alert_emitted=False,
            audit_logged=False,
        )

    async def check_tokens_batch(
        self,
        tokens: list[str | HITLToken | Mapping[str, Any]],
        repository: HITLApprovalRepository | None = None,
        session: AsyncSession | None = None,
        actor_id: UUID | str | None = None,
        action_id: str | None = None,
        alert_id: UUID | str | None = None,
        raise_on_error: bool = False,
    ) -> list[TokenReplayCheckResult]:
        """Verify a batch of tokens, enforcing both intra-batch and database-level uniqueness."""
        results: list[TokenReplayCheckResult] = []
        seen_in_batch: set[str] = set()

        for idx, t in enumerate(tokens):
            token_hash = self.extract_token_hash(t)

            # Intra-batch duplicate check (e.g., same signature supplied twice in DUAL_VP)
            if token_hash in seen_in_batch:
                await self.handle_replay_attempt(
                    token_hash=token_hash,
                    actor_id=actor_id,
                    action_id=action_id,
                    alert_id=alert_id,
                    reason=f"Duplicate token hash in batch (position {idx})",
                )
                if raise_on_error:
                    raise TokenReplaySecurityAlert(
                        f"Cryptographic token replay detected: duplicate token hash '{token_hash}' in batch."
                    )
                results.append(
                    TokenReplayCheckResult(
                        token_hash=token_hash,
                        is_replay=True,
                        is_valid=False,
                        message=f"Duplicate token hash in batch (position {idx}).",
                        alert_emitted=True,
                        audit_logged=True,
                    )
                )
                continue

            seen_in_batch.add(token_hash)

            # Database-level uniqueness check
            res = await self.check_token(
                token=t,
                repository=repository,
                session=session,
                actor_id=actor_id,
                action_id=action_id,
                alert_id=alert_id,
                raise_on_error=raise_on_error,
            )
            results.append(res)

        return results

    async def wrap_create_approval(
        self,
        approval: HITLApproval,
        repository: HITLApprovalRepository,
        actor_id: UUID | str | None = None,
    ) -> HITLApproval:
        """Create an approval record, safely intercepting database IntegrityError and alerting on replay."""
        token_hash = approval.token_hash

        # 1. Pre-insertion check
        check = await self.check_token(
            token=token_hash,
            repository=repository,
            actor_id=actor_id,
            action_id=getattr(approval, "action_id", None),
            alert_id=approval.alert_id,
            raise_on_error=False,
        )
        if check.is_replay:
            raise TokenReplaySecurityAlert(
                f"Cryptographic token replay detected for hash '{token_hash}'."
            )

        # 2. Insertion with race condition handling
        try:
            return await repository.create_approval(approval)
        except (TokenReplayError, IntegrityError) as exc:
            await self.handle_replay_attempt(
                token_hash=token_hash,
                actor_id=actor_id,
                action_id=getattr(approval, "action_id", None),
                alert_id=approval.alert_id,
                reason=f"Database unique constraint violation: {exc}",
            )
            raise TokenReplaySecurityAlert(
                f"Cryptographic token replay detected for hash '{token_hash}'."
            ) from exc


# ------------------------------------------------------------------------------
# Thread-Safe Singleton Accessor
# ------------------------------------------------------------------------------

_global_replay_guard: TokenReplayGuard | None = None
_guard_lock = threading.Lock()


def get_token_replay_guard(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    alert_emitter: (Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None) = None,
) -> TokenReplayGuard:
    """Thread-safe singleton accessor for TokenReplayGuard."""
    global _global_replay_guard
    if _global_replay_guard is None or session_factory is not None or alert_emitter is not None:
        with _guard_lock:
            if (
                _global_replay_guard is None
                or session_factory is not None
                or alert_emitter is not None
            ):
                guard = TokenReplayGuard(
                    session_factory=session_factory,
                    alert_emitter=alert_emitter,
                )
                if session_factory is None and alert_emitter is None:
                    _global_replay_guard = guard
                return guard
    return _global_replay_guard
