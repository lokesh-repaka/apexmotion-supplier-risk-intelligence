"""Spend-Tier Router & HITL Authorization Governance.

Maps authorized financial commitments to governance tiers adhering to:
- BR-RULE-001: Pure Python deterministic math and Decimal monetary precision
- CLAUDE.md Section 3:
    * Tier 1 (CATEGORY_MGR): Spend <= $25,000 (1x token, 1-hr TTL)
    * Tier 2 (PROC_DIRECTOR): Spend $25,001 - $100,000 (1x token, 1-hr TTL)
    * Tier 3 (DUAL_VP): Spend > $100,000 (Dual sign-off, 30-min TTL)
- Role verification, eligibility checks, and dual-signoff enforcement
"""

from datetime import timedelta
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from src.api.exceptions import AuthorizationException
from src.core.config import get_settings
from src.core.demo_auth import DemoPersona
from src.core.hitl_tokens import SpendTier, get_token_ttl
from src.core.logging import get_logger
from src.core.security import (
    AuthenticatedUser,
    UserRole,
    get_role_level,
    normalize_role,
)

logger = get_logger("apexmotion.spend_tier_router")


# ------------------------------------------------------------------------------
# Spend Tier Route Model
# ------------------------------------------------------------------------------


class SpendTierRoute(BaseModel):
    """Domain model representing the governing HITL policy for a spend amount."""

    model_config = ConfigDict(frozen=True)

    tier: SpendTier = Field(description="Governing HITL spend authority tier")
    amount_usd: Decimal = Field(description="Exact authorized spend amount in USD (Decimal)")
    min_amount_usd: Decimal = Field(description="Lower bound threshold of this spend tier")
    max_amount_usd: Decimal | None = Field(
        default=None,
        description="Upper bound threshold of this spend tier (None for Tier 3)",
    )
    required_signatures: int = Field(
        description="Number of distinct cryptographic signatures required"
    )
    required_roles: list[UserRole] = Field(
        description="User roles required to authorize this spend"
    )
    primary_role: UserRole = Field(description="Primary authorized role required for approval")
    secondary_role: UserRole | None = Field(
        default=None,
        description="Secondary role required for dual approval (Tier 3)",
    )
    token_ttl: timedelta = Field(description="Cryptographic token validity window")
    requires_dual_approval: bool = Field(
        description="Whether dual sign-off from two distinct executives is required"
    )
    description: str = Field(description="Human-readable policy specification")


# ------------------------------------------------------------------------------
# Monetary Amount Normalization
# ------------------------------------------------------------------------------


def _normalize_amount(amount: Decimal | int | str) -> Decimal:
    """Normalize input to Decimal and enforce BR-RULE-001 monetary precision.

    Raises:
        TypeError: If native float is supplied (to avoid IEEE 754 precision drift).
        ValueError: If amount is negative or invalid numeric string.
    """
    if isinstance(amount, float):
        raise TypeError(
            "Float values are strictly prohibited for monetary amounts under BR-RULE-001. "
            "Use Decimal or numeric string instead."
        )

    if isinstance(amount, Decimal):
        val = amount
    else:
        try:
            val = Decimal(str(amount))
        except Exception as exc:
            raise ValueError(f"Invalid monetary format '{amount}': {exc}") from exc

    if val < Decimal("0.00"):
        raise ValueError(f"Spend amount cannot be negative: {val}")

    return val


def _extract_user_info(
    user: AuthenticatedUser | DemoPersona | UserRole | str,
) -> tuple[str, list[str]]:
    """Extract user identifier and normalized roles from various user representations."""
    if isinstance(user, AuthenticatedUser):
        return user.user_id, [normalize_role(r) for r in user.roles]
    if isinstance(user, DemoPersona):
        return user.user_id, [normalize_role(r) for r in user.roles]
    if isinstance(user, UserRole):
        norm = normalize_role(user)
        return norm, [norm]
    norm_str = normalize_role(str(user))
    return norm_str, [norm_str]


# ------------------------------------------------------------------------------
# Routing Logic
# ------------------------------------------------------------------------------


def route_spend(amount_usd: Decimal | int | str) -> SpendTierRoute:
    """Map an authorized spend commitment to its governing HITL tier and policy.

    Thresholds configured via Settings:
    - Tier 1: Spend <= $25,000 (Category Manager, 1x signature, 1-hr TTL)
    - Tier 2: Spend $25,001 - $100,000 (Procurement Director, 1x signature, 1-hr TTL)
    - Tier 3: Spend > $100,000 (Dual sign-off, 2x signatures, 30-min TTL)
    """
    amt = _normalize_amount(amount_usd)
    settings = get_settings()

    tier_1_max = settings.HITL_TIER_1_THRESHOLD_USD
    tier_2_max = settings.HITL_TIER_2_THRESHOLD_USD

    if amt <= tier_1_max:
        tier = SpendTier.CATEGORY_MGR
        return SpendTierRoute(
            tier=tier,
            amount_usd=amt,
            min_amount_usd=Decimal("0.00"),
            max_amount_usd=tier_1_max,
            required_signatures=1,
            required_roles=[UserRole.CATEGORY_MANAGER],
            primary_role=UserRole.CATEGORY_MANAGER,
            secondary_role=None,
            token_ttl=get_token_ttl(tier),
            requires_dual_approval=False,
            description=f"Tier 1: Category Manager approval for spend <= ${tier_1_max:,.2f} (1x token, 1-hr TTL)",
        )

    if amt <= tier_2_max:
        tier = SpendTier.PROC_DIRECTOR
        return SpendTierRoute(
            tier=tier,
            amount_usd=amt,
            min_amount_usd=Decimal("25000.01"),
            max_amount_usd=tier_2_max,
            required_signatures=1,
            required_roles=[UserRole.PROCUREMENT_DIRECTOR],
            primary_role=UserRole.PROCUREMENT_DIRECTOR,
            secondary_role=None,
            token_ttl=get_token_ttl(tier),
            requires_dual_approval=False,
            description=(
                f"Tier 2: Procurement Director approval for spend ${tier_1_max + Decimal('0.01'):,.2f} - "
                f"${tier_2_max:,.2f} (1x token, 1-hr TTL)"
            ),
        )

    tier = SpendTier.DUAL_VP
    return SpendTierRoute(
        tier=tier,
        amount_usd=amt,
        min_amount_usd=Decimal("100000.01"),
        max_amount_usd=None,
        required_signatures=2,
        required_roles=[UserRole.PROCUREMENT_DIRECTOR, UserRole.VP_SUPPLY_CHAIN],
        primary_role=UserRole.PROCUREMENT_DIRECTOR,
        secondary_role=UserRole.VP_SUPPLY_CHAIN,
        token_ttl=get_token_ttl(tier),
        requires_dual_approval=True,
        description=f"Tier 3: Dual sign-off (Director + VP Supply Chain) for spend > ${tier_2_max:,.2f} (2x tokens, 30-min TTL)",
    )


def get_spend_tier(amount_usd: Decimal | int | str) -> SpendTier:
    """Return the SpendTier enum corresponding to the authorized spend amount."""
    return route_spend(amount_usd).tier


def get_required_roles(amount_usd: Decimal | int | str) -> list[UserRole]:
    """Return the list of UserRoles required to authorize this spend."""
    return route_spend(amount_usd).required_roles


def get_required_signatures_count(amount_usd: Decimal | int | str) -> int:
    """Return the number of distinct signatures required for this spend."""
    return route_spend(amount_usd).required_signatures


# ------------------------------------------------------------------------------
# Signer Authority & Dual-Signoff Validation
# ------------------------------------------------------------------------------


def can_user_approve_spend(
    user: AuthenticatedUser | DemoPersona | UserRole | str,
    amount_usd: Decimal | int | str,
) -> tuple[bool, str]:
    """Check if a single user possesses sufficient authority to unilaterally approve an amount.

    Returns:
        tuple[bool, str]: (is_authorized, status_or_rejection_reason)
    """
    amt = _normalize_amount(amount_usd)
    route = route_spend(amt)

    # Tier 3 strictly prohibits unilateral single approval
    if route.requires_dual_approval:
        return (
            False,
            f"Spend of ${amt:,.2f} exceeds ${get_settings().HITL_TIER_2_THRESHOLD_USD:,.2f}; "
            "dual sign-off from Procurement Director and VP Supply Chain is strictly required.",
        )

    _, user_roles = _extract_user_info(user)

    # Check for analyst (read-only)
    if all(r in ("analyst", "supply_chain_analyst") for r in user_roles):
        return (False, "Analyst role has read-only privileges ($0 spend authority).")

    user_max_level = max((get_role_level(r) for r in user_roles), default=0)
    target_level = get_role_level(route.primary_role)

    if user_max_level >= target_level:
        return (
            True,
            f"User has sufficient authority ({route.primary_role.value}) for spend of ${amt:,.2f}.",
        )

    return (
        False,
        f"Insufficient permissions: requested spend ${amt:,.2f} exceeds user role limit and requires '{route.primary_role.value}'.",
    )


def is_eligible_signer(
    user: AuthenticatedUser | DemoPersona | UserRole | str,
    amount_usd: Decimal | int | str,
) -> bool:
    """Check if a user is eligible to act as a signer (primary or secondary) for an amount."""
    amt = _normalize_amount(amount_usd)
    route = route_spend(amt)
    _, user_roles = _extract_user_info(user)

    # Analyst is never eligible
    if all(r in ("analyst", "supply_chain_analyst") for r in user_roles):
        return False

    user_max_level = max((get_role_level(r) for r in user_roles), default=0)

    # For Tier 1, Category Manager or higher
    if route.tier == SpendTier.CATEGORY_MGR:
        return user_max_level >= get_role_level(UserRole.CATEGORY_MANAGER)

    # For Tier 2 & 3, Procurement Director or higher
    return user_max_level >= get_role_level(UserRole.PROCUREMENT_DIRECTOR)


def validate_approval_signers(
    signers: list[AuthenticatedUser | DemoPersona | str],
    amount_usd: Decimal | int | str,
) -> tuple[bool, str]:
    """Validate a set of proposed signers against the governing spend tier policy.

    Verifies signature count, distinctness of signers, and required role coverage.
    """
    amt = _normalize_amount(amount_usd)
    route = route_spend(amt)

    if not signers:
        return (False, "No approval signers provided.")

    if len(signers) < route.required_signatures:
        return (
            False,
            f"Spend of ${amt:,.2f} requires dual approval (two signatures); only {len(signers)} provided.",
        )

    # Verify all signers are distinct individuals
    signer_ids = [_extract_user_info(s)[0] for s in signers]
    if len(set(signer_ids)) < len(signer_ids):
        return (False, "Dual approval requires signatures from two distinct individuals.")

    # Validate roles for single-signer tiers (Tier 1 & Tier 2)
    if not route.requires_dual_approval:
        primary_signer = signers[0]
        _, roles = _extract_user_info(primary_signer)
        max_level = max((get_role_level(r) for r in roles), default=0)
        required_level = get_role_level(route.primary_role)
        if max_level < required_level:
            return (
                False,
                f"Insufficient permissions: required role '{route.primary_role.value}' for spend of ${amt:,.2f}.",
            )
        return (True, "Approval signers verified successfully.")

    # Validate roles for dual sign-off (Tier 3)
    has_director = False
    has_vp = False

    for s in signers:
        _, roles = _extract_user_info(s)
        max_level = max((get_role_level(r) for r in roles), default=0)
        if max_level >= get_role_level(UserRole.VP_SUPPLY_CHAIN):
            has_vp = True
        elif max_level >= get_role_level(UserRole.PROCUREMENT_DIRECTOR):
            has_director = True

    # If both signers are VP or higher, or one is VP and one is Director
    if not has_vp:
        return (False, "Dual approval requires at least one signer with VP Supply Chain authority.")

    # Need at least one director-level or VP-level co-signer
    if not (
        has_director
        or sum(
            1
            for s in signers
            if max((get_role_level(r) for r in _extract_user_info(s)[1]), default=0)
            >= get_role_level(UserRole.VP_SUPPLY_CHAIN)
        )
        >= 2
    ):
        return (False, "Dual approval requires a Procurement Director signature.")

    return (True, "Dual approval signers verified successfully.")


def evaluate_spend_authorization(
    user: AuthenticatedUser,
    amount_usd: Decimal | int | str,
) -> None:
    """Validate that user has unilateral authority to approve spend, raising 403 if not.

    Raises:
        AuthorizationException: If user has insufficient role or spend requires dual approval.
    """
    can_approve, reason = can_user_approve_spend(user, amount_usd)
    if not can_approve:
        logger.warning(
            "Spend authorization rejected for user '%s' on amount %s: %s",
            user.user_id,
            amount_usd,
            reason,
        )
        raise AuthorizationException(reason)
