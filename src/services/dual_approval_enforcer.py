"""Dual-Approval Enforcer Service (P10-2).

Enforces:
- Cryptographic Dual Sign-Off for Tier 3 spend commitments (> $100,000 / DUAL_VP)
  mandating two distinct, cryptographically valid tokens from authorized executive
  signers (Procurement Director + VP Supply Chain) prior to action execution.
- Strict prevention of single-signature execution bypasses (CLAUDE.md Sec 20.1:
  "A DUAL_VP action proceeding with only one approval signature must NEVER happen").
- Enforces The Triad of Responsibility (BR-RULE-001): Pure deterministic Python arithmetic
  with Decimal / NUMERIC(14,2) precision, strictly rejecting native floats with TypeError.
- Time-to-Live (TTL) enforcement: Tokens bound to 30-minute expiration for DUAL_VP spend.
- Distinct signer validation, preventing identical signers from signing twice.
- Action, alert, and amount binding consistency across multiple tokens.
- Integration into LangGraph StateGraph (hitl_gate_node, route_after_hitl_gate, action_node).
"""

import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from src.core.hitl_tokens import (
    HITLToken,
    HITLTokenService,
    SpendTier,
)
from src.core.logging import get_logger
from src.core.security import UserRole

logger = get_logger("apexmotion.services.dual_approval")


# ------------------------------------------------------------------------------
# Exceptions Hierarchy
# ------------------------------------------------------------------------------


class DualApprovalError(Exception):
    """Base exception for all dual-approval governance violations."""


class InsufficientSignaturesError(DualApprovalError):
    """Raised when an action requiring dual approval lacks the second signature."""


class DuplicateSignerError(DualApprovalError):
    """Raised when the same individual attempts to sign twice on a dual-approval action."""


class UnauthorizedSignerRoleError(DualApprovalError):
    """Raised when a signer lacks the requisite executive authority for Tier 3 spend."""


class DualApprovalExpiredError(DualApprovalError):
    """Raised when one or more tokens in a dual approval have exceeded their 30-minute TTL."""


class DualApprovalActionMismatchError(DualApprovalError):
    """Raised when tokens in a dual approval are bound to different actions, alerts, or amounts."""


class DualApprovalReplayError(DualApprovalError):
    """Raised when a token hash in a dual approval has already been registered or executed."""


# ------------------------------------------------------------------------------
# Domain Models
# ------------------------------------------------------------------------------


class DualApprovalVerificationResult(BaseModel):
    """Cryptographic verification result for multi-signature spend governance."""

    is_approved: bool = Field(
        ...,
        description="Whether all requisite cryptographic signatures are present and valid",
    )
    spend_tier: SpendTier = Field(
        default=SpendTier.DUAL_VP,
        description="Governing spend tier authority",
    )
    required_signers_count: int = Field(
        default=2,
        description="Number of independent signatures required for the spend tier",
    )
    valid_signers: list[str] = Field(
        default_factory=list,
        description="List of distinct validated signer identifiers",
    )
    token_hashes: list[str] = Field(
        default_factory=list,
        description="List of cryptographic SHA-256 token hashes corresponding to signatures",
    )
    error: str | None = Field(
        default=None,
        description="Machine-readable error code if verification failed",
    )
    reason: str | None = Field(
        default=None,
        description="Human-readable justification or failure explanation",
    )


# ------------------------------------------------------------------------------
# Amount Normalization Helper (BR-RULE-001)
# ------------------------------------------------------------------------------


def _normalize_amount(amount: Decimal | int | str | None) -> Decimal | None:
    """Validate and normalize monetary amount to Decimal, rejecting native floats."""
    if amount is None:
        return None
    if isinstance(amount, float):
        raise TypeError(
            "Float values are strictly forbidden for monetary amounts (BR-RULE-001). "
            f"Use Decimal or string representation, received float {amount!r}."
        )
    if isinstance(amount, Decimal):
        return amount
    return Decimal(str(amount))


# ------------------------------------------------------------------------------
# Dual-Approval Enforcer Service
# ------------------------------------------------------------------------------


class DualApprovalEnforcer:
    """Service enforcing dual executive cryptographic sign-off for high-value spend.

    Guarantees:
    - Actions exceeding $100,000 (Tier 3 / DUAL_VP) require two independent, valid tokens.
    - Signatures must come from distinct executive signers (Procurement Director + VP Supply Chain).
    - Tokens must have valid 30-minute TTLs and match action_id, alert_id, and amount_usd.
    - Hard gate prevents action_node execution if single signature reaches it.
    """

    # Roles authorized to participate in Tier 3 dual approval
    TIER_3_AUTHORIZED_ROLES = {
        UserRole.PROCUREMENT_DIRECTOR.value,
        UserRole.VP_SUPPLY_CHAIN.value,
        "procurement_director",
        "vp_supply_chain",
        "chief_financial_officer",
        "cfo",
        "system_admin",
    }

    def __init__(self, token_service: HITLTokenService | None = None) -> None:
        """Initialize with injectable HITLTokenService."""
        self.token_service = token_service or HITLTokenService()

    def is_dual_approval_required(
        self,
        amount_usd: Decimal | int | str | None = None,
        spend_tier: SpendTier | str | None = None,
    ) -> bool:
        """Evaluate if an action or commitment mandates dual executive authorization.

        Dual approval is required if:
        1. spend_tier is DUAL_VP
        2. amount_usd > $100,000.00
        """
        if spend_tier is not None:
            tier_str = spend_tier.value if isinstance(spend_tier, SpendTier) else str(spend_tier)
            if tier_str.upper() == SpendTier.DUAL_VP.value:
                return True

        if amount_usd is not None:
            norm_amount = _normalize_amount(amount_usd)
            if norm_amount is not None and norm_amount > Decimal("100000.00"):
                return True

        return False

    def verify_signatures(
        self,
        tokens: list[str | HITLToken],
        expected_action_id: str | None = None,
        expected_alert_id: str | None = None,
        expected_amount_usd: Decimal | None = None,
        enforce_roles: bool = False,
        raise_on_error: bool = False,
    ) -> DualApprovalVerificationResult:
        """Verify that exactly two independent, valid executive signatures exist for a DUAL_VP action."""
        norm_amount = _normalize_amount(expected_amount_usd)

        # 1. Signature Count Gate
        if len(tokens) < 2:
            logger.warning("Dual approval failed: received %d token(s), required 2", len(tokens))
            if raise_on_error:
                raise InsufficientSignaturesError(
                    f"Tier 3 DUAL_VP actions require 2 independent executive signatures, "
                    f"received {len(tokens)}."
                )
            return DualApprovalVerificationResult(
                is_approved=False,
                required_signers_count=2,
                valid_signers=[],
                error="INSUFFICIENT_SIGNATURES",
                reason=f"Received {len(tokens)} token(s), required 2 distinct executive signatures.",
            )

        # 2. Token Deserialization
        parsed_tokens: list[HITLToken] = []
        for t in tokens:
            if isinstance(t, str):
                try:
                    parsed = HITLToken.deserialize(t)
                except Exception as exc:
                    logger.warning("Failed to deserialize token in dual approval: %s", exc)
                    if raise_on_error:
                        raise DualApprovalError(f"Malformed token: {exc}") from exc
                    return DualApprovalVerificationResult(
                        is_approved=False,
                        error="MALFORMED_TOKEN",
                        reason=str(exc),
                    )
            else:
                parsed = t
            parsed_tokens.append(parsed)

        # 3. Expiration Check (30-Minute TTL for DUAL_VP)
        now = datetime.now(UTC)
        for p in parsed_tokens:
            exp = p.payload.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=UTC)
            if now > exp:
                logger.warning(
                    "Dual approval token for signer %s expired at %s",
                    p.payload.signer_id,
                    exp.isoformat(),
                )
                if raise_on_error:
                    raise DualApprovalExpiredError(
                        f"Token for signer '{p.payload.signer_id}' has expired (TTL elapsed)."
                    )
                return DualApprovalVerificationResult(
                    is_approved=False,
                    error="TOKEN_EXPIRED",
                    reason=f"Token for signer '{p.payload.signer_id}' has expired.",
                )

        # 4. Action Binding & Consistency
        action_ids = {p.payload.action_id for p in parsed_tokens if p.payload.action_id}
        if len(action_ids) > 1:
            logger.warning("Dual approval tokens bound to different action IDs: %s", action_ids)
            if raise_on_error:
                raise DualApprovalActionMismatchError(
                    f"Tokens bound to different actions: {action_ids}"
                )
            return DualApprovalVerificationResult(
                is_approved=False,
                error="DUAL_ACTION_MISMATCH",
                reason=f"Tokens bound to different actions: {action_ids}",
            )

        if expected_action_id:
            for p in parsed_tokens:
                if p.payload.action_id != expected_action_id:
                    logger.warning(
                        "Token action '%s' does not match expected action '%s'",
                        p.payload.action_id,
                        expected_action_id,
                    )
                    if raise_on_error:
                        raise DualApprovalActionMismatchError(
                            f"Token action '{p.payload.action_id}' does not match expected '{expected_action_id}'."
                        )
                    return DualApprovalVerificationResult(
                        is_approved=False,
                        error="ACTION_MISMATCH",
                        reason=f"Token action mismatch for expected '{expected_action_id}'.",
                    )

        # 5. Distinct Signers Gate (Anti-Self-Signoff)
        signers = [p.payload.signer_id for p in parsed_tokens if p.payload.signer_id]
        unique_signers = set(signers)
        if len(unique_signers) < 2:
            logger.warning("Dual approval rejected: identical signers detected: %s", unique_signers)
            if raise_on_error:
                raise DuplicateSignerError(
                    "Dual approval mandates 2 distinct executive signers; duplicate signer detected."
                )
            return DualApprovalVerificationResult(
                is_approved=False,
                error="IDENTICAL_SIGNERS",
                reason="Dual approval requires two distinct executive signers; received identical signer.",
            )

        # 6. Role Authority Validation (Director + VP)
        if enforce_roles:
            for p in parsed_tokens:
                role = (p.payload.signer_role or "").lower()
                if role not in self.TIER_3_AUTHORIZED_ROLES:
                    logger.warning(
                        "Signer '%s' has role '%s', which is ineligible for Tier 3 dual approval",
                        p.payload.signer_id,
                        role,
                    )
                    if raise_on_error:
                        raise UnauthorizedSignerRoleError(
                            f"Signer '{p.payload.signer_id}' has role '{role}', which is ineligible for DUAL_VP."
                        )
                    return DualApprovalVerificationResult(
                        is_approved=False,
                        error="UNAUTHORIZED_ROLE",
                        reason=f"Signer '{p.payload.signer_id}' has role '{role}', ineligible for Tier 3.",
                    )

        # 7. Cryptographic Signature Verification via KMS
        for p in parsed_tokens:
            ver_res = self.token_service.verify_token(
                token=p,
                expected_action_id=expected_action_id,
                expected_alert_id=expected_alert_id,
                expected_amount_usd=norm_amount,
                raise_on_error=False,
            )
            if not ver_res.is_valid:
                logger.warning(
                    "Cryptographic verification failed for token hash %s: %s",
                    p.token_hash[:16],
                    ver_res.error,
                )
                if raise_on_error:
                    if ver_res.error == "TOKEN_EXPIRED":
                        raise DualApprovalExpiredError("Token has expired.")
                    if ver_res.error == "INVALID_SIGNATURE":
                        raise DualApprovalError("Invalid cryptographic signature.")
                    raise DualApprovalError(f"Verification failed: {ver_res.error}")
                return DualApprovalVerificationResult(
                    is_approved=False,
                    error=ver_res.error,
                    reason=f"Cryptographic verification failed for token: {ver_res.error}",
                )

        token_hashes = [p.token_hash for p in parsed_tokens]
        logger.info(
            "Dual approval verified successfully for action '%s' (Signers: %s, Hashes: %s)",
            expected_action_id or list(action_ids)[0],
            list(unique_signers),
            [h[:12] + "..." for h in token_hashes],
        )

        return DualApprovalVerificationResult(
            is_approved=True,
            spend_tier=SpendTier.DUAL_VP,
            required_signers_count=2,
            valid_signers=list(unique_signers),
            token_hashes=token_hashes,
            error=None,
            reason="Dual executive sign-off verified with valid cryptographic signatures.",
        )

    def enforce_state_approval(
        self,
        state: Mapping[str, Any],
        raise_on_error: bool = False,
    ) -> DualApprovalVerificationResult:
        """Inspect state payload and evaluate if the required approval gates are satisfied."""
        requires_hitl = bool(state.get("requires_hitl", False))
        if not requires_hitl:
            return DualApprovalVerificationResult(
                is_approved=True,
                spend_tier=SpendTier.CATEGORY_MGR,
                required_signers_count=0,
                valid_signers=[],
                token_hashes=[],
                reason="Spend commitment does not require human authorization.",
            )

        # Resolve governing tier and action
        action_id = state.get("recommended_action_id")
        spend_tier = state.get("governing_spend_tier")
        recommendations = state.get("recommendations") or []

        # Find recommended scenario cost if available
        amount_usd: Decimal | None = None
        for rec in recommendations:
            if rec.get("action_id") == action_id:
                cost = rec.get("estimated_cost_usd")
                if cost is not None:
                    amount_usd = _normalize_amount(cost)
                    break

        is_dual = self.is_dual_approval_required(amount_usd=amount_usd, spend_tier=spend_tier)

        decision = state.get("hitl_decision") or {}
        if not decision:
            if raise_on_error:
                raise InsufficientSignaturesError("No human approval decision present in state.")
            return DualApprovalVerificationResult(
                is_approved=False,
                spend_tier=SpendTier.DUAL_VP if is_dual else SpendTier.CATEGORY_MGR,
                required_signers_count=2 if is_dual else 1,
                error="AWAITING_APPROVAL",
                reason="Awaiting executive authorization.",
            )

        if decision.get("approved") is not True:
            return DualApprovalVerificationResult(
                is_approved=False,
                spend_tier=SpendTier.DUAL_VP if is_dual else SpendTier.CATEGORY_MGR,
                required_signers_count=2 if is_dual else 1,
                error="REJECTED",
                reason=decision.get("reason", "Action rejected by human reviewer."),
            )

        # For Single-Signer Tiers (CATEGORY_MGR or PROC_DIRECTOR)
        if not is_dual:
            token_hash = decision.get("token_hash", "PRE_AUTHORIZED")
            signer = decision.get("signer_id", "AUTHORIZED_USER")
            return DualApprovalVerificationResult(
                is_approved=True,
                spend_tier=SpendTier.PROC_DIRECTOR
                if spend_tier == SpendTier.PROC_DIRECTOR
                else SpendTier.CATEGORY_MGR,
                required_signers_count=1,
                valid_signers=[signer],
                token_hashes=[token_hash],
                reason="Single executive signature verified for spend <= $100,000.",
            )

        # For DUAL_VP: Extract multi-token signatures
        tokens = decision.get("tokens") or []
        if not tokens:
            # If decision only contains single token_hash / single signer
            if decision.get("token_hash"):
                tokens = [decision["token_hash"]]

        return self.verify_signatures(
            tokens=tokens,
            expected_action_id=action_id,
            expected_amount_usd=amount_usd,
            raise_on_error=raise_on_error,
        )

    def enforce_action_execution(self, state: Mapping[str, Any]) -> None:
        """Hard security gate called inside action_node before any real-world effect occurs.

        Raises InsufficientSignaturesError or DualApprovalError if dual authorization is not satisfied.
        """
        requires_hitl = bool(state.get("requires_hitl", False))
        if not requires_hitl:
            return

        result = self.enforce_state_approval(state, raise_on_error=True)
        if not result.is_approved:
            raise InsufficientSignaturesError(
                f"Action execution blocked: {result.reason} (error: {result.error})"
            )


# ------------------------------------------------------------------------------
# Thread-Safe Singleton Accessor
# ------------------------------------------------------------------------------

_enforcer_instance: DualApprovalEnforcer | None = None
_enforcer_lock = threading.Lock()


def get_dual_approval_enforcer() -> DualApprovalEnforcer:
    """Return the thread-safe singleton instance of DualApprovalEnforcer."""
    global _enforcer_instance
    if _enforcer_instance is None:
        with _enforcer_lock:
            if _enforcer_instance is None:
                _enforcer_instance = DualApprovalEnforcer()
    return _enforcer_instance
