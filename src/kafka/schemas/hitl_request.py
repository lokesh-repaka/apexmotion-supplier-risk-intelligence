"""Human-in-the-Loop spend approval request schema for Kafka topic `hitl-required`.

Represents pending spend commitments gated cryptographically by AWS KMS ECDSA P-256
signatures in accordance with the spend-tier router and BR-RULE-001.
"""

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import Field, field_serializer, field_validator, model_validator

from src.kafka.schemas.base import BaseEvent
from src.kafka.schemas.risk_alert import SpendTier


class HITLActionType(StrEnum):
    """Mitigation actions subject to human authorization."""

    LOGISTICS_EXPEDITE = "LOGISTICS_EXPEDITE"
    SECONDARY_SOURCE_SPOT_BUY = "SECONDARY_SOURCE_SPOT_BUY"
    BUFFER_REALLOCATION = "BUFFER_REALLOCATION"
    PRODUCTION_RESCHEDULE = "PRODUCTION_RESCHEDULE"
    INVENTORY_TRANSFER = "INVENTORY_TRANSFER"


class HITLStatus(StrEnum):
    """Lifecycle status of the human approval workflow."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class HITLRequest(BaseEvent):
    """Event payload requesting human executive authorization for mitigation spend."""

    action_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for the mitigation action commitment",
    )
    alert_id: str = Field(
        ...,
        min_length=1,
        description="Referenced risk alert identifier",
    )
    supplier_id: str = Field(
        ...,
        min_length=1,
        description="Target supplier identifier (e.g. SUP-NC-882)",
    )
    action_type: HITLActionType | str = Field(
        ...,
        description="Mitigation action category",
    )
    amount_usd: Decimal = Field(
        ...,
        gt=0,
        description="Authorized financial spend commitment in USD (NUMERIC(14,2))",
    )
    spend_tier: SpendTier | str = Field(
        ...,
        description="Required governance tier: CATEGORY_MGR, PROC_DIRECTOR, DUAL_VP",
    )
    required_signers_count: int = Field(
        default=1,
        ge=1,
        le=2,
        description="Number of distinct executive signatures required (1 or 2)",
    )
    status: HITLStatus | str = Field(
        default=HITLStatus.PENDING,
        description="Current authorization status",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Authorization request creation timestamp",
    )
    expires_at: datetime = Field(
        ...,
        description="Token expiration timestamp (1-hr TTL for single, 30-min for dual)",
    )
    justification: str | None = Field(
        default=None,
        description="Narrative business justification for the spend action",
    )

    @field_serializer("amount_usd")
    def serialize_amount(self, v: Decimal) -> str:
        """Preserve exact Decimal currency precision as string representation."""
        return str(v)

    @field_validator("created_at", "expires_at", mode="after")
    @classmethod
    def ensure_utc_datetimes(cls, dt: datetime) -> datetime:
        """Ensure datetimes are timezone-aware UTC."""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt

    @model_validator(mode="after")
    def validate_tier_and_expiration(self) -> "HITLRequest":
        """Verify spend tier matches monetary amount and expiration is in future."""
        # 1. Verify expiration is strictly after creation
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be strictly greater than created_at")

        tier_str = (
            self.spend_tier.value
            if isinstance(self.spend_tier, SpendTier)
            else str(self.spend_tier)
        )

        # 2. Verify tier alignment with monetary amount
        if self.amount_usd <= Decimal("25000.00"):
            expected_tier = SpendTier.CATEGORY_MGR.value
            expected_signers = 1
        elif self.amount_usd <= Decimal("100000.00"):
            expected_tier = SpendTier.PROC_DIRECTOR.value
            expected_signers = 1
        else:
            expected_tier = SpendTier.DUAL_VP.value
            expected_signers = 2

        if tier_str != expected_tier:
            raise ValueError(
                f"Spend amount ${self.amount_usd} is inconsistent with spend_tier '{tier_str}'. "
                f"Expected tier '{expected_tier}'."
            )

        if self.required_signers_count != expected_signers:
            raise ValueError(
                f"Spend tier '{tier_str}' requires exactly {expected_signers} signers, "
                f"but received required_signers_count={self.required_signers_count}."
            )

        return self


# Canonical alias for compatibility
HITLRequestEvent = HITLRequest
