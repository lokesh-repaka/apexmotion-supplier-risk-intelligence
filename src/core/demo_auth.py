"""Demo Okta authentication tokens and persona profiles for ApexMotion.

Provides:
- Standardized demo personas matching platform user roles and authority thresholds
- In-memory persona registry aligning with CLAUDE.md Section 3 and frontend mockups
- Cryptographically signed JWT token generation for development, demo, and E2E testing
- High-level resolution helper supporting role enums, string keys, and canonical aliases
- Full compatibility with Okta OIDC validation (src.core.security) and BR-RULE-001 monetary limits
"""

from datetime import timedelta
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.core.security import (
    UserRole,
    create_access_token,
    normalize_role,
)

# ------------------------------------------------------------------------------
# Demo Persona Model
# ------------------------------------------------------------------------------


class DemoPersona(BaseModel):
    """Domain model representing a pre-configured platform demo persona."""

    model_config = ConfigDict(frozen=True)

    persona_id: str = Field(
        description="Unique identifier for the demo persona (e.g. analyst, category_manager)"
    )
    user_id: str = Field(description="OIDC subject/user ID prefixed with usr-")
    email: str = Field(description="Corporate email address ending in @apexmotion.com")
    name: str = Field(description="Display full name of persona user")
    role: UserRole = Field(description="Primary UserRole assigned to this persona")
    roles: list[str] = Field(default_factory=list, description="All role names assigned to persona")
    groups: list[str] = Field(default_factory=list, description="Okta groups persona belongs to")
    spend_authority_usd: Decimal | None = Field(
        default=None,
        description="Deterministic spend authorization limit in USD adhering to BR-RULE-001 (Decimal)",
    )
    description: str = Field(
        default="", description="Summary of persona operational responsibilities"
    )


# ------------------------------------------------------------------------------
# In-Memory Demo Personas Registry
# ------------------------------------------------------------------------------

DEMO_PERSONAS: dict[str, DemoPersona] = {
    "analyst": DemoPersona(
        persona_id="analyst",
        user_id="usr-alex-chen",
        email="alex.chen@apexmotion.com",
        name="Alex Chen",
        role=UserRole.ANALYST,
        roles=["analyst", "supply_chain_analyst"],
        groups=["ApexMotion-Analysts", "SupplyChain-Ops"],
        spend_authority_usd=Decimal("0.00"),
        description="Supply Chain Analyst - Read-only risk telemetry, alerts inspection, and investigation triggers",
    ),
    "category_manager": DemoPersona(
        persona_id="category_manager",
        user_id="usr-priya-sharma",
        email="priya.sharma@apexmotion.com",
        name="Priya Sharma",
        role=UserRole.CATEGORY_MANAGER,
        roles=["category_manager"],
        groups=["ApexMotion-CategoryManagers", "Procurement-Tier1"],
        spend_authority_usd=Decimal("25000.00"),
        description="Category Manager - Authorizes procurement actions up to $25,000 (Tier 1 HITL spend gate)",
    ),
    "procurement_director": DemoPersona(
        persona_id="procurement_director",
        user_id="usr-klaus-weber",
        email="klaus.weber@apexmotion.com",
        name="Klaus Weber",
        role=UserRole.PROCUREMENT_DIRECTOR,
        roles=["procurement_director"],
        groups=["ApexMotion-Directors", "Procurement-Leadership"],
        spend_authority_usd=Decimal("100000.00"),
        description="Procurement Director - Authorizes procurement actions up to $100,000 (Tier 2 HITL spend gate)",
    ),
    "vp_supply_chain": DemoPersona(
        persona_id="vp_supply_chain",
        user_id="usr-elena-rostova",
        email="elena.rostova@apexmotion.com",
        name="Dr. Elena Rostova",
        role=UserRole.VP_SUPPLY_CHAIN,
        roles=["vp_supply_chain"],
        groups=["ApexMotion-Executive", "SupplyChain-VP", "Dual-Signoff-Authority"],
        spend_authority_usd=Decimal("2500000.00"),
        description="VP of Supply Chain - Dual sign-off authority for high-impact actions >$100,000 (Tier 3 HITL spend gate)",
    ),
    "system_admin": DemoPersona(
        persona_id="system_admin",
        user_id="usr-alex-mercer",
        email="admin@apexmotion.com",
        name="Alex Mercer",
        role=UserRole.SYSTEM_ADMIN,
        roles=["system_admin"],
        groups=["ApexMotion-Admins", "Platform-Operations"],
        spend_authority_usd=None,
        description="Platform System Administrator - Full platform administration, configuration, and audit log inspection",
    ),
}

# Persona canonical alias map
PERSONA_ALIASES: dict[str, str] = {
    "analyst": "analyst",
    "supply_chain_analyst": "analyst",
    "cat_manager": "category_manager",
    "category_manager": "category_manager",
    "director": "procurement_director",
    "proc_director": "procurement_director",
    "procurement_director": "procurement_director",
    "vp": "vp_supply_chain",
    "vp_supply_chain": "vp_supply_chain",
    "admin": "system_admin",
    "sysadmin": "system_admin",
    "system_admin": "system_admin",
}


# ------------------------------------------------------------------------------
# Persona Resolution & Token Generation Helpers
# ------------------------------------------------------------------------------


def get_demo_persona(identifier: str | UserRole) -> DemoPersona:
    """Retrieve a DemoPersona by ID, UserRole, or common alias.

    Raises:
        KeyError: If identifier does not match any known persona or alias.
    """
    if isinstance(identifier, UserRole):
        norm = normalize_role(identifier)
    else:
        norm = str(identifier).strip().lower()

    target_id = PERSONA_ALIASES.get(norm, norm)
    if target_id in DEMO_PERSONAS:
        return DEMO_PERSONAS[target_id]

    valid = list(DEMO_PERSONAS.keys())
    raise KeyError(f"Demo persona '{identifier}' not found. Available personas: {valid}")


def generate_demo_token(
    persona: str | UserRole | DemoPersona,
    expires_delta: timedelta | None = None,
) -> str:
    """Generate a signed Okta-compatible JWT for the given demo persona."""
    if isinstance(persona, DemoPersona):
        p = persona
    else:
        p = get_demo_persona(persona)

    additional_claims: dict[str, Any] = {
        "groups": p.groups,
        "persona_id": p.persona_id,
    }
    if p.spend_authority_usd is not None:
        additional_claims["spend_authority_usd"] = str(p.spend_authority_usd)

    return create_access_token(
        subject=p.user_id,
        roles=p.roles,
        email=p.email,
        name=p.name,
        expires_delta=expires_delta,
        additional_claims=additional_claims,
    )


def generate_all_demo_tokens(
    expires_delta: timedelta | None = None,
) -> dict[str, str]:
    """Generate signed JWT tokens for all registered platform demo personas."""
    return {p_id: generate_demo_token(p_id, expires_delta=expires_delta) for p_id in DEMO_PERSONAS}
