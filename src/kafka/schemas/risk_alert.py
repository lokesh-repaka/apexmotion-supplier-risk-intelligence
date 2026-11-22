"""Risk alert event schema for Kafka topic `risk-alerts`.

Represents calculated risk assessment events emitted by the deterministic risk engine
conforming to the Triad of Responsibility (BR-RULE-001).
"""

from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import Field, field_serializer, field_validator, model_validator

from src.kafka.schemas.base import BaseEvent


class RiskLevel(StrEnum):
    """Calculated risk severity levels."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class AlertStatus(StrEnum):
    """Lifecycle status of the risk alert."""

    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    MITIGATED = "MITIGATED"
    RESOLVED = "RESOLVED"


class SpendTier(StrEnum):
    """Spend authority tiers defined by BR-RULE-001."""

    CATEGORY_MGR = "CATEGORY_MGR"
    PROC_DIRECTOR = "PROC_DIRECTOR"
    DUAL_VP = "DUAL_VP"
    NONE = "NONE"


class RiskAlert(BaseEvent):
    """Event payload emitted when a supplier risk threshold is breached."""

    alert_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for the risk alert",
    )
    supplier_id: str = Field(
        ...,
        min_length=1,
        description="Target supplier identifier (e.g. SUP-NC-882)",
    )
    component_sku: str = Field(
        ...,
        min_length=1,
        description="Impacted component part number (e.g. CMP-MCU-X91)",
    )
    risk_level: RiskLevel | str = Field(
        ...,
        description="Severity classification: CRITICAL, HIGH, MEDIUM, LOW",
    )
    days_of_cover: Decimal = Field(
        ...,
        ge=0,
        description="Inventory days of cover (current_stock / daily_consumption_rate)",
    )
    gap_days: Decimal | None = Field(
        default=None,
        description="Coverage gap days (eta_days - days_of_cover)",
    )
    shortage_volume: int = Field(
        default=0,
        ge=0,
        description="Projected component shortage unit volume",
    )
    financial_exposure: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        description="Total projected financial downtime exposure in USD (NUMERIC(14,2))",
    )
    current_stock: int | None = Field(
        default=None,
        ge=0,
        description="Current available stock units",
    )
    daily_consumption_rate: int | None = Field(
        default=None,
        ge=0,
        description="Daily consumption rate in units/day",
    )
    eta_days: Decimal | None = Field(
        default=None,
        ge=0,
        description="Estimated delivery time in days",
    )
    status: AlertStatus | str = Field(
        default=AlertStatus.OPEN,
        description="Current lifecycle status of the alert",
    )
    hitl_required: bool = Field(
        default=False,
        description="Whether this alert requires human-in-the-loop spend intervention",
    )
    hitl_tier: SpendTier | str | None = Field(
        default=None,
        description="Required HITL approval authority tier",
    )

    @field_serializer("days_of_cover", "gap_days", "financial_exposure", "eta_days")
    def serialize_decimal(self, v: Decimal | None) -> str | None:
        """Serialize Decimal instances as strings to preserve financial precision."""
        return str(v) if v is not None else None

    @field_validator("risk_level")
    @classmethod
    def validate_risk_level(cls, v: RiskLevel | str) -> str:
        """Validate risk level against allowed enum values."""
        val = v.value if isinstance(v, RiskLevel) else str(v).upper()
        allowed = {r.value for r in RiskLevel}
        if val not in allowed:
            raise ValueError(f"Invalid risk_level '{val}'. Must be one of: {allowed}")
        return val

    @model_validator(mode="before")
    @classmethod
    def auto_derive_hitl_and_precision(cls, data: Any) -> Any:
        """Ensure hitl_required is set appropriately and convert string decimals."""
        if isinstance(data, dict):
            # Auto-derive hitl_required if not explicitly set
            if "hitl_required" not in data:
                level = str(data.get("risk_level", "")).upper()
                exposure = Decimal(str(data.get("financial_exposure", 0)))
                data["hitl_required"] = level in ("CRITICAL", "HIGH") or exposure > 0
        return data


# Canonical alias for compatibility
RiskAlertEvent = RiskAlert
