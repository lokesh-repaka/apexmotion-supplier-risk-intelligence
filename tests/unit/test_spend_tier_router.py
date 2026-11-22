"""Unit tests for Spend-Tier Router and HITL Authorization Governance.

Validates:
- Mapping of spend amounts to HITL tiers adhering to BR-RULE-001 and CLAUDE.md Section 3:
    * Tier 1 (CATEGORY_MGR): Spend <= $25,000 (1x token, 1-hr TTL)
    * Tier 2 (PROC_DIRECTOR): Spend $25,001 - $100,000 (1x token, 1-hr TTL)
    * Tier 3 (DUAL_VP): Spend > $100,000 (Dual sign-off, 30-min TTL)
- Strict Decimal monetary precision enforcement and rejection of negative or unsafe float values
- Single and dual signer authority validation across all platform user roles
- Alignment with canonical golden reference scenarios (NanoCore $2,448,105.00, PRD $180,000.00)
- Compatibility with demo personas (Alex Chen, Priya Sharma, Klaus Weber, Dr. Elena Rostova)
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from src.api.exceptions import AuthorizationException
from src.core.demo_auth import DEMO_PERSONAS, get_demo_persona
from src.core.hitl_tokens import SpendTier
from src.core.security import AuthenticatedUser, UserRole
from src.core.spend_tier_router import (
    SpendTierRoute,
    can_user_approve_spend,
    evaluate_spend_authorization,
    get_required_roles,
    get_required_signatures_count,
    get_spend_tier,
    is_eligible_signer,
    route_spend,
    validate_approval_signers,
)


def test_route_spend_tier_1_boundaries():
    """Verify amounts <= $25,000 map to CATEGORY_MGR tier with 1x signature and 1-hr TTL."""
    test_amounts = [
        Decimal("0.00"),
        Decimal("1.00"),
        Decimal("5000.50"),
        Decimal("24999.99"),
        Decimal("25000.00"),
    ]

    for amt in test_amounts:
        route: SpendTierRoute = route_spend(amt)
        assert route.tier == SpendTier.CATEGORY_MGR
        assert route.amount_usd == amt
        assert route.required_signatures == 1
        assert route.token_ttl == timedelta(hours=1)
        assert route.requires_dual_approval is False
        assert UserRole.CATEGORY_MANAGER in route.required_roles
        assert route.max_amount_usd == Decimal("25000.00")
        assert route.min_amount_usd == Decimal("0.00")


def test_route_spend_tier_2_boundaries():
    """Verify amounts $25,001 - $100,000 map to PROC_DIRECTOR tier with 1x signature and 1-hr TTL."""
    test_amounts = [
        Decimal("25000.01"),
        Decimal("25001.00"),
        Decimal("75000.00"),
        Decimal("99999.99"),
        Decimal("100000.00"),
    ]

    for amt in test_amounts:
        route: SpendTierRoute = route_spend(amt)
        assert route.tier == SpendTier.PROC_DIRECTOR
        assert route.amount_usd == amt
        assert route.required_signatures == 1
        assert route.token_ttl == timedelta(hours=1)
        assert route.requires_dual_approval is False
        assert UserRole.PROCUREMENT_DIRECTOR in route.required_roles
        assert route.max_amount_usd == Decimal("100000.00")
        assert route.min_amount_usd == Decimal("25000.01")


def test_route_spend_tier_3_boundaries_and_reference_scenarios():
    """Verify amounts > $100,000 map to DUAL_VP tier with dual sign-off and 30-min TTL."""
    test_amounts = [
        Decimal("100000.01"),
        Decimal("100001.00"),
        Decimal("180000.00"),  # PRD Emergency air freight scenario
        Decimal("2448105.00"),  # NanoCore golden reference scenario
        Decimal("10000000.00"),
    ]

    for amt in test_amounts:
        route: SpendTierRoute = route_spend(amt)
        assert route.tier == SpendTier.DUAL_VP
        assert route.amount_usd == amt
        assert route.required_signatures == 2
        assert route.token_ttl == timedelta(minutes=30)
        assert route.requires_dual_approval is True
        assert UserRole.PROCUREMENT_DIRECTOR in route.required_roles
        assert UserRole.VP_SUPPLY_CHAIN in route.required_roles
        assert route.max_amount_usd is None
        assert route.min_amount_usd == Decimal("100000.01")


def test_route_spend_invalid_amounts_raise_errors():
    """Verify negative amounts, invalid types, and raw floats raise appropriate exceptions."""
    # Negative amounts are rejected
    with pytest.raises(ValueError, match="cannot be negative"):
        route_spend(Decimal("-0.01"))

    with pytest.raises(ValueError, match="cannot be negative"):
        route_spend("-100.00")

    # Native floats are rejected to protect against binary floating-point drift per BR-RULE-001
    with pytest.raises(TypeError, match="Float values are strictly prohibited"):
        route_spend(25000.0)  # type: ignore[arg-type]

    # Non-numeric strings raise ValueError
    with pytest.raises(ValueError):
        route_spend("invalid-number")


def test_convenience_helpers():
    """Verify helper functions get_required_roles and get_required_signatures_count."""
    assert get_required_signatures_count(Decimal("15000.00")) == 1
    assert get_required_signatures_count(Decimal("85000.00")) == 1
    assert get_required_signatures_count(Decimal("250000.00")) == 2

    assert get_required_roles(Decimal("15000.00")) == [UserRole.CATEGORY_MANAGER]
    assert get_required_roles(Decimal("85000.00")) == [UserRole.PROCUREMENT_DIRECTOR]
    assert get_required_roles(Decimal("250000.00")) == [
        UserRole.PROCUREMENT_DIRECTOR,
        UserRole.VP_SUPPLY_CHAIN,
    ]


def test_can_user_approve_spend_tier_1():
    """Verify single signer approvals for Tier 1 (<= $25k)."""
    amt = Decimal("25000.00")

    # Category manager passes
    cat_user = AuthenticatedUser(user_id="u1", roles=["category_manager"])
    can_approve, reason = can_user_approve_spend(cat_user, amt)
    assert can_approve is True

    # Higher roles pass via hierarchy elevation
    dir_user = AuthenticatedUser(user_id="u2", roles=["procurement_director"])
    assert can_user_approve_spend(dir_user, amt)[0] is True

    vp_user = AuthenticatedUser(user_id="u3", roles=["vp_supply_chain"])
    assert can_user_approve_spend(vp_user, amt)[0] is True

    # Analyst fails
    analyst_user = AuthenticatedUser(user_id="u4", roles=["analyst"])
    can_analyst, msg = can_user_approve_spend(analyst_user, amt)
    assert can_analyst is False
    assert "Analyst" in msg or "Insufficient" in msg


def test_can_user_approve_spend_tier_2():
    """Verify single signer approvals for Tier 2 ($25k - $100k)."""
    amt = Decimal("75000.00")

    # Procurement director passes
    dir_user = AuthenticatedUser(user_id="u2", roles=["procurement_director"])
    can_approve, _ = can_user_approve_spend(dir_user, amt)
    assert can_approve is True

    # VP passes via hierarchy elevation
    vp_user = AuthenticatedUser(user_id="u3", roles=["vp_supply_chain"])
    assert can_user_approve_spend(vp_user, amt)[0] is True

    # Category manager fails (exceeds $25k limit)
    cat_user = AuthenticatedUser(user_id="u1", roles=["category_manager"])
    can_cat, msg = can_user_approve_spend(cat_user, amt)
    assert can_cat is False
    assert "limit" in msg.lower() or "director" in msg.lower()


def test_can_user_approve_spend_tier_3():
    """Verify single signer cannot unilaterally approve Tier 3 (> $100k) without dual sign-off."""
    amt = Decimal("180000.00")

    vp_user = AuthenticatedUser(user_id="u3", roles=["vp_supply_chain"])
    can_approve, msg = can_user_approve_spend(vp_user, amt)
    # A single user cannot unilaterally authorize Tier 3
    assert can_approve is False
    assert "dual" in msg.lower() or "sign-off" in msg.lower()


def test_is_eligible_signer():
    """Verify is_eligible_signer checks role participation eligibility for an amount."""
    amt_tier_1 = Decimal("20000.00")
    amt_tier_3 = Decimal("2448105.00")

    analyst = get_demo_persona("analyst")
    manager = get_demo_persona("category_manager")
    director = get_demo_persona("procurement_director")
    vp = get_demo_persona("vp_supply_chain")

    # Analyst is never eligible to sign any spend
    assert is_eligible_signer(analyst, amt_tier_1) is False
    assert is_eligible_signer(analyst, amt_tier_3) is False

    # Manager is eligible for Tier 1, not Tier 3
    assert is_eligible_signer(manager, amt_tier_1) is True
    assert is_eligible_signer(manager, amt_tier_3) is False

    # Director and VP are eligible for Tier 1 and Tier 3
    assert is_eligible_signer(director, amt_tier_1) is True
    assert is_eligible_signer(director, amt_tier_3) is True
    assert is_eligible_signer(vp, amt_tier_1) is True
    assert is_eligible_signer(vp, amt_tier_3) is True


def test_validate_approval_signers_tier_1_and_tier_2():
    """Verify validate_approval_signers for single-signer tiers."""
    amt_1 = Decimal("25000.00")
    amt_2 = Decimal("100000.00")

    manager = DEMO_PERSONAS["category_manager"]
    director = DEMO_PERSONAS["procurement_director"]
    analyst = DEMO_PERSONAS["analyst"]

    # Tier 1 with manager passes
    valid, _ = validate_approval_signers([manager], amt_1)
    assert valid is True

    # Tier 1 with analyst fails
    valid, reason = validate_approval_signers([analyst], amt_1)
    assert valid is False
    assert "Insufficient" in reason or "required" in reason

    # Tier 2 with director passes
    valid, _ = validate_approval_signers([director], amt_2)
    assert valid is True

    # Tier 2 with manager fails
    valid, reason = validate_approval_signers([manager], amt_2)
    assert valid is False

    # Tier 1 empty signers fails
    valid_empty, _ = validate_approval_signers([], amt_1)
    assert valid_empty is False


def test_validate_approval_signers_tier_3_dual_signoff():
    """Verify validate_approval_signers enforces two distinct authorized executives for Tier 3."""
    amt_3 = Decimal("180000.00")

    analyst = DEMO_PERSONAS["analyst"]
    manager = DEMO_PERSONAS["category_manager"]
    director = DEMO_PERSONAS["procurement_director"]
    vp = DEMO_PERSONAS["vp_supply_chain"]

    # Director + VP passes
    valid, _ = validate_approval_signers([director, vp], amt_3)
    assert valid is True

    # VP + Director (reversed order) passes
    valid, _ = validate_approval_signers([vp, director], amt_3)
    assert valid is True

    # Single signer fails (missing second signature)
    valid, reason = validate_approval_signers([director], amt_3)
    assert valid is False
    assert "dual" in reason.lower() or "two" in reason.lower()

    # Identical signers (same user twice) fails
    valid, reason = validate_approval_signers([director, director], amt_3)
    assert valid is False
    assert "distinct" in reason.lower() or "identical" in reason.lower()

    # Manager + Director fails (missing VP role for Tier 3 dual sign-off)
    valid, reason = validate_approval_signers([manager, director], amt_3)
    assert valid is False
    assert "vp" in reason.lower() or "role" in reason.lower()

    # VP + Analyst fails (missing Director role for Tier 3 dual sign-off)
    valid, reason = validate_approval_signers([vp, analyst], amt_3)
    assert valid is False
    assert "director" in reason.lower()

    # Empty signers list fails
    valid_empty, reason_empty = validate_approval_signers([], amt_3)
    assert valid_empty is False
    assert "no approval signers" in reason_empty.lower()


def test_convenience_helpers_and_type_coercion():
    """Verify get_spend_tier, string and int input coercion, and role inputs."""
    assert get_spend_tier(Decimal("15000.00")) == SpendTier.CATEGORY_MGR
    assert get_spend_tier(Decimal("85000.00")) == SpendTier.PROC_DIRECTOR
    assert get_spend_tier(Decimal("250000.00")) == SpendTier.DUAL_VP

    # String input
    assert route_spend("20000.00").tier == SpendTier.CATEGORY_MGR
    # Integer input
    assert route_spend(75000).tier == SpendTier.PROC_DIRECTOR

    # can_user_approve_spend with UserRole and string
    assert can_user_approve_spend(UserRole.CATEGORY_MANAGER, Decimal("10000.00"))[0] is True
    assert can_user_approve_spend("category_manager", Decimal("10000.00"))[0] is True

    # is_eligible_signer with UserRole and string
    assert is_eligible_signer(UserRole.CATEGORY_MANAGER, Decimal("10000.00")) is True
    assert is_eligible_signer("category_manager", Decimal("10000.00")) is True
    assert is_eligible_signer("analyst", Decimal("10000.00")) is False


def test_evaluate_spend_authorization_exception():
    """Verify evaluate_spend_authorization raises AuthorizationException when unauthorized."""
    analyst_user = AuthenticatedUser(user_id="u_a", roles=["analyst"])
    manager_user = AuthenticatedUser(user_id="u_m", roles=["category_manager"])

    # Analyst trying to approve $10,000 raises 403 AuthorizationException
    with pytest.raises(AuthorizationException) as exc:
        evaluate_spend_authorization(analyst_user, Decimal("10000.00"))
    assert exc.value.status_code == 403
    assert exc.value.code == "INSUFFICIENT_ROLE"

    # Manager trying to approve $50,000 raises 403 AuthorizationException
    with pytest.raises(AuthorizationException) as exc2:
        evaluate_spend_authorization(manager_user, Decimal("50000.00"))
    assert exc2.value.status_code == 403

    # Manager approving $20,000 does not raise
    evaluate_spend_authorization(manager_user, Decimal("20000.00"))
