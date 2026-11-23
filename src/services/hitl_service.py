"""Human-in-the-Loop (HITL) Spend Approval & Cryptographic Token Service (P10-1).

Enforces:
- The Triad of Responsibility (BR-RULE-001):
  * Probabilistic AI proposes mitigation options, but human authority strictly governs capital spend.
  * Strict Decimal monetary precision; float values are strictly prohibited to avoid precision drift.
  * Deterministic spend authority tier routing:
    - Tier 1 (CATEGORY_MGR): Spend <= $25,000 (1x token, 1-hr TTL, Category Manager sign-off).
    - Tier 2 (PROC_DIRECTOR): Spend $25,001 - $100,000 (1x token, 1-hr TTL, Procurement Director sign-off).
    - Tier 3 (DUAL_VP): Spend > $100,000 (Dual sign-off, 30-min TTL, Director + VP Supply Chain).
- Cryptographic KMS ECDSA P-256 Tokens:
  * Issues, serializes, and cryptographically signs approval tokens using AWS KMS (ECC_NIST_P256).
  * Strict parameter binding: tokens are bound to action_id, alert_id, amount_usd, and spend_tier.
  * Time-to-Live enforcement (1 hour for single approvals; 30 minutes for dual sign-offs).
  * Cryptographic anti-replay validation: token hashes are uniquely tracked and cannot be replayed.
  * Dual-approval verification: high-value commitments require 2 independent tokens with distinct signers.
- Layering Purity (CLAUDE.md Sec 5.2):
  * Application service coordinating core cryptographic primitives (src.core.hitl_tokens)
    and database repositories (src.database.repositories.hitl_approval_repository).
"""

import threading
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.audit import coerce_uuid, write_audit_log
from src.core.hitl_tokens import (
    HITLToken,
    HITLTokenError,
    HITLTokenService,
    SpendTier,
    TokenBindingMismatchError,
    TokenExpiredError,
    TokenReplayDetectedError,
    TokenSignatureInvalidError,
    TokenVerificationResult,
)
from src.core.logging import get_logger
from src.core.spend_tier_router import (
    SpendTierRoute,
    _normalize_amount,
    can_user_approve_spend,
    is_eligible_signer,
    route_spend,
)
from src.database.models import HITLApproval
from src.database.repositories.hitl_approval_repository import (
    HITLApprovalRepository,
    TokenReplayError,
)

logger = get_logger("apexmotion.services.hitl")


# ------------------------------------------------------------------------------
# Exceptions
# ------------------------------------------------------------------------------


class HITLServiceError(Exception):
    """Base exception for all HITL service operations."""


class ApprovalNotFoundError(HITLServiceError):
    """Raised when an approval record cannot be found by ID."""


class UnauthorizedSignerError(HITLServiceError):
    """Raised when a user lacks sufficient authority to sign an approval for the given spend tier."""


class InvalidApprovalOperationError(HITLServiceError):
    """Raised when an approval workflow transition is illegal or invalid."""


class TokenReplayServiceError(HITLServiceError):
    """Raised when a cryptographic token replay attack is detected."""


class TokenExpiredServiceError(HITLServiceError):
    """Raised when an approval token has exceeded its TTL limit."""


class TokenVerificationServiceError(HITLServiceError):
    """Raised when cryptographic or semantic token verification fails."""


# ------------------------------------------------------------------------------
# Input Models
# ------------------------------------------------------------------------------


@dataclass
class ApprovalCreateInput:
    """Input payload for initiating a Human-in-the-Loop spend approval request."""

    action_id: str
    action_type: str
    amount_usd: Decimal | int | str
    alert_id: uuid.UUID | str | None = None


# ------------------------------------------------------------------------------
# HITL Service Implementation
# ------------------------------------------------------------------------------


class HITLService:
    """Enterprise Human-in-the-Loop approval orchestrator and token management service."""

    def __init__(
        self,
        token_service: HITLTokenService | None = None,
    ) -> None:
        self.token_service = token_service or HITLTokenService()

    # --------------------------------------------------------------------------
    # Spend Tier Routing & Governance
    # --------------------------------------------------------------------------

    def route_spend(self, amount_usd: Decimal | int | str) -> SpendTierRoute:
        """Deterministically resolve the governing spend tier route and TTL policy."""
        norm_amt = _normalize_amount(amount_usd)
        return route_spend(norm_amt)

    def get_spend_tier(self, amount_usd: Decimal | int | str) -> SpendTier:
        """Return the SpendTier enum corresponding to the authorized spend commitment."""
        return self.route_spend(amount_usd).tier

    def get_token_ttl(self, spend_tier: SpendTier) -> timedelta:
        """Return the TTL limit for a spend tier (1 hour for Tier 1 & 2; 30 minutes for Tier 3)."""
        if spend_tier == SpendTier.DUAL_VP:
            return timedelta(minutes=30)
        return timedelta(hours=1)

    def can_user_approve(
        self,
        user: Any,
        amount_usd: Decimal | int | str,
    ) -> tuple[bool, str]:
        """Check if a specific user possesses sufficient authority to unilaterally approve a spend."""
        return can_user_approve_spend(user, amount_usd)

    def is_eligible_signer(
        self,
        user: Any,
        amount_usd: Decimal | int | str,
    ) -> bool:
        """Check if a user is eligible to act as a signer (primary or secondary) for an amount."""
        return is_eligible_signer(user, amount_usd)

    # --------------------------------------------------------------------------
    # Cryptographic Token Issuance
    # --------------------------------------------------------------------------

    def issue_token(
        self,
        action_id: str,
        alert_id: str,
        action_type: str,
        amount_usd: Decimal | int | str,
        signer_id: str | None = None,
        signer_role: str | None = None,
        user: Any | None = None,
    ) -> HITLToken:
        """Issue, sign with KMS ECDSA P-256, and return a cryptographically bound approval token."""
        norm_amount = _normalize_amount(amount_usd)
        route = self.route_spend(norm_amount)

        resolved_signer_id = signer_id
        resolved_signer_role = signer_role

        if user is not None:
            can_approve, reason = self.can_user_approve(user, norm_amount)
            if not can_approve:
                logger.warning(
                    "Signer authority rejection for user '%s' on spend $%s: %s",
                    getattr(user, "username", getattr(user, "user_id", str(user))),
                    norm_amount,
                    reason,
                )
                raise UnauthorizedSignerError(reason)

            resolved_signer_id = getattr(user, "user_id", getattr(user, "sub", str(user)))
            resolved_signer_role = getattr(user, "role", getattr(user, "primary_role", None))
            if resolved_signer_role is not None and hasattr(resolved_signer_role, "value"):
                resolved_signer_role = resolved_signer_role.value

        token = self.token_service.issue_token(
            action_id=action_id,
            alert_id=alert_id,
            action_type=action_type,
            amount_usd=norm_amount,
            signer_id=resolved_signer_id,
            signer_role=resolved_signer_role,
        )

        logger.info(
            "HITLService: Issued token for action '%s' tier=%s ttl=%s hash=%s...",
            action_id,
            route.tier.value,
            route.token_ttl,
            token.token_hash[:16],
        )
        return token

    # --------------------------------------------------------------------------
    # Token Verification & Anti-Replay
    # --------------------------------------------------------------------------

    def verify_token(
        self,
        token: str | HITLToken,
        expected_action_id: str | None = None,
        expected_alert_id: str | None = None,
        expected_amount_usd: Decimal | None = None,
        raise_on_error: bool = False,
    ) -> TokenVerificationResult:
        """Verify token cryptographic signature, temporal validity (TTL), and parameter bindings."""
        try:
            res = self.token_service.verify_token(
                token=token,
                expected_action_id=expected_action_id,
                expected_alert_id=expected_alert_id,
                expected_amount_usd=expected_amount_usd,
                raise_on_error=True,
            )
            return res
        except TokenExpiredError as exc:
            if raise_on_error:
                raise TokenExpiredServiceError(str(exc)) from exc
            return TokenVerificationResult(is_valid=False, error="TOKEN_EXPIRED")
        except (TokenBindingMismatchError, TokenSignatureInvalidError, HITLTokenError) as exc:
            if raise_on_error:
                raise TokenVerificationServiceError(str(exc)) from exc
            err_code = "VERIFICATION_FAILED"
            if isinstance(exc, TokenBindingMismatchError):
                msg = str(exc).lower()
                if "action_id" in msg:
                    err_code = "ACTION_MISMATCH"
                elif "alert_id" in msg:
                    err_code = "ALERT_MISMATCH"
                elif "amount" in msg:
                    err_code = "AMOUNT_MISMATCH"
            elif isinstance(exc, TokenSignatureInvalidError):
                err_code = "INVALID_SIGNATURE"
            return TokenVerificationResult(is_valid=False, error=err_code)

    async def verify_anti_replay(
        self,
        token: str | HITLToken,
        repository: HITLApprovalRepository,
        raise_on_error: bool = False,
    ) -> bool:
        """Verify that the token hash has not already been used in previous actions."""
        try:
            return await self.token_service.verify_anti_replay(
                token=token,
                repository=repository,
                raise_on_error=raise_on_error,
            )
        except TokenReplayDetectedError as exc:
            if raise_on_error:
                raise TokenReplayServiceError(str(exc)) from exc
            return False

    def verify_dual_approval(
        self,
        tokens: list[str | HITLToken],
        expected_action_id: str | None = None,
        expected_alert_id: str | None = None,
        expected_amount_usd: Decimal | None = None,
    ) -> TokenVerificationResult:
        """Verify dual sign-off requirements for high-value commitments (> $100,000)."""
        return self.token_service.verify_dual_approval(
            tokens=tokens,
            expected_action_id=expected_action_id,
            expected_alert_id=expected_alert_id,
            expected_amount_usd=expected_amount_usd,
        )

    # --------------------------------------------------------------------------
    # Database Approval Lifecycle
    # --------------------------------------------------------------------------

    async def create_approval_request(
        self,
        session: AsyncSession,
        input_data: ApprovalCreateInput,
    ) -> HITLApproval:
        """Create a new pending HITL approval request in the database."""
        norm_amount = _normalize_amount(input_data.amount_usd)
        route = self.route_spend(norm_amount)
        now = datetime.now(UTC)
        expires_at = now + route.token_ttl

        coerced_alert_id = coerce_uuid(input_data.alert_id) if input_data.alert_id else None
        placeholder_hash = f"PENDING-{uuid.uuid4().hex}"

        approval = HITLApproval(
            alert_id=coerced_alert_id,
            action_type=input_data.action_type,
            amount_usd=norm_amount,
            spend_tier=route.tier.value,
            token_hash=placeholder_hash,
            expires_at=expires_at,
            status="PENDING",
            approved_by=[],
            approved_at=[],
        )

        repo = HITLApprovalRepository(session)
        created = await repo.create(approval)
        await session.commit()

        try:
            await write_audit_log(
                entity_type="HITL_APPROVAL",
                entity_id=created.id,
                action="HITL_APPROVAL_REQUEST_CREATED",
                actor_id=coerced_alert_id or created.id,
                after_state={
                    "action_id": input_data.action_id,
                    "action_type": input_data.action_type,
                    "amount_usd": str(norm_amount),
                    "spend_tier": route.tier.value,
                    "expires_at": expires_at.isoformat(),
                },
            )
        except Exception as exc:
            logger.warning("Audit write failed for approval request %s: %s", created.id, exc)

        logger.info(
            "Created HITL approval request %s (action=%s, tier=%s, amount=$%s, expires=%s)",
            created.id,
            input_data.action_id,
            route.tier.value,
            norm_amount,
            expires_at.isoformat(),
        )
        return created

    async def sign_approval(
        self,
        session: AsyncSession,
        approval_id: uuid.UUID | str,
        token: str | HITLToken,
        signer_id: uuid.UUID | str,
    ) -> HITLApproval:
        """Apply an authorized cryptographic token signature to a pending approval request."""
        repo = HITLApprovalRepository(session)
        app_uuid = coerce_uuid(approval_id)
        signer_uuid = coerce_uuid(signer_id)

        approval = await repo.get_by_id(app_uuid)
        if approval is None:
            raise ApprovalNotFoundError(f"HITL approval {approval_id} not found.")

        if approval.status not in ("PENDING", "PARTIALLY_APPROVED"):
            raise InvalidApprovalOperationError(
                f"Cannot sign approval in '{approval.status}' state."
            )

        # Deserialize token if string
        hitl_token = HITLToken.deserialize(token) if isinstance(token, str) else token

        # 1. Verify token parameters against approval record
        self.verify_token(
            token=hitl_token,
            expected_amount_usd=approval.amount_usd,
            raise_on_error=True,
        )

        # 2. Verify anti-replay: token hash must not already exist in approved records
        is_unused = await self.verify_anti_replay(hitl_token, repo, raise_on_error=False)
        if not is_unused:
            raise TokenReplayServiceError(
                f"Token hash {hitl_token.token_hash} has already been registered."
            )

        # 3. Handle state transitions based on spend tier
        current_signers = list(approval.approved_by or [])
        current_times = list(approval.approved_at or [])
        now = datetime.now(UTC)

        spend_tier = SpendTier(approval.spend_tier)

        if spend_tier == SpendTier.DUAL_VP:
            # Dual Sign-off
            if not current_signers:
                # First signature
                current_signers.append(signer_uuid)
                current_times.append(now)
                approval.approved_by = current_signers
                approval.approved_at = current_times
                approval.status = "PARTIALLY_APPROVED"
            else:
                # Second signature
                if signer_uuid in current_signers:
                    raise UnauthorizedSignerError(
                        "Duplicate signer: Tier 3 dual approval requires two distinct executive signers."
                    )
                current_signers.append(signer_uuid)
                current_times.append(now)
                approval.approved_by = current_signers
                approval.approved_at = current_times
                approval.token_hash = hitl_token.token_hash
                approval.status = "APPROVED"
        else:
            # Single signature (Tier 1 or Tier 2)
            current_signers.append(signer_uuid)
            current_times.append(now)
            approval.approved_by = current_signers
            approval.approved_at = current_times
            approval.token_hash = hitl_token.token_hash
            approval.status = "APPROVED"

        try:
            await session.commit()
        except TokenReplayError as exc:
            await session.rollback()
            raise TokenReplayServiceError(str(exc)) from exc

        try:
            await write_audit_log(
                entity_type="HITL_APPROVAL",
                entity_id=approval.id,
                action="HITL_APPROVAL_SIGNED",
                actor_id=signer_uuid,
                after_state={
                    "status": approval.status,
                    "signer_id": str(signer_uuid),
                    "token_hash": hitl_token.token_hash,
                },
            )
        except Exception as exc:
            logger.warning("Audit write failed for signed approval %s: %s", approval.id, exc)

        logger.info(
            "HITL approval %s signed by %s (new status: %s)",
            approval.id,
            signer_uuid,
            approval.status,
        )
        return approval

    async def reject_approval(
        self,
        session: AsyncSession,
        approval_id: uuid.UUID | str,
        reason: str,
        actor_id: uuid.UUID | str,
    ) -> HITLApproval:
        """Reject a pending HITL approval request."""
        repo = HITLApprovalRepository(session)
        app_uuid = coerce_uuid(approval_id)
        actor_uuid = coerce_uuid(actor_id)

        approval = await repo.get_by_id(app_uuid)
        if approval is None:
            raise ApprovalNotFoundError(f"HITL approval {approval_id} not found.")

        approval.status = "REJECTED"
        await session.commit()

        try:
            await write_audit_log(
                entity_type="HITL_APPROVAL",
                entity_id=approval.id,
                action="HITL_APPROVAL_REJECTED",
                actor_id=actor_uuid,
                after_state={"status": "REJECTED", "reason": reason},
            )
        except Exception as exc:
            logger.warning("Audit write failed for rejected approval %s: %s", approval.id, exc)

        logger.info("HITL approval %s rejected by %s: %s", approval.id, actor_uuid, reason)
        return approval

    async def get_approval(
        self,
        session: AsyncSession,
        approval_id: uuid.UUID | str,
    ) -> HITLApproval | None:
        """Fetch an approval by ID, checking and updating TTL expiration if pending."""
        repo = HITLApprovalRepository(session)
        app_uuid = coerce_uuid(approval_id)
        approval = await repo.get_by_id(app_uuid)

        if approval is not None and approval.status == "PENDING":
            exp = approval.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=UTC)
            if datetime.now(UTC) > exp:
                approval.status = "EXPIRED"
                await session.commit()

        return approval

    async def list_pending_approvals(
        self,
        session: AsyncSession,
        spend_tier: str | None = None,
        limit: int = 100,
    ) -> Sequence[HITLApproval]:
        """List pending approvals requiring human review, optionally filtered by spend tier."""
        repo = HITLApprovalRepository(session)
        if spend_tier:
            approvals = await repo.get_by_spend_tier(spend_tier, limit=limit)
            return [a for a in approvals if a.status in ("PENDING", "PARTIALLY_APPROVED")]
        return await repo.get_pending_approvals(limit=limit)


# ------------------------------------------------------------------------------
# Thread-safe Singleton Accessor
# ------------------------------------------------------------------------------

_hitl_service_instance: HITLService | None = None
_hitl_service_lock = threading.Lock()


def get_hitl_service() -> HITLService:
    """Return the thread-safe singleton instance of HITLService."""
    global _hitl_service_instance
    if _hitl_service_instance is None:
        with _hitl_service_lock:
            if _hitl_service_instance is None:
                _hitl_service_instance = HITLService()
    return _hitl_service_instance
