"""Pydantic v2 schemas for risk evaluation and alert API routes."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RiskEvaluationRequest(BaseModel):
    """Request payload for evaluating supplier risk signal via fast-track or full-track pipeline."""

    model_config = ConfigDict(extra="forbid")

    component_sku: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Canonical component SKU or MPN (e.g. NC-2024, MCU-X91)",
    )
    supplier_id: str | None = Field(
        default=None,
        description="Disrupted supplier UUID or identifier",
    )
    plant_id: str | None = Field(
        default=None,
        description="Affected manufacturing plant identifier (e.g. PLT-MUC-01)",
    )
    current_stock: Decimal | None = Field(
        default=None,
        ge=0,
        description="Current usable inventory units (if omitted, looked up via inventory service)",
    )
    daily_consumption_rate: Decimal | None = Field(
        default=None,
        gt=0,
        description="Daily unit burn rate (if omitted, looked up via inventory service)",
    )
    eta_days: Decimal | None = Field(
        default=None,
        ge=0,
        description="Estimated replacement delivery lead time in days",
    )
    unit_cost_usd: Decimal | None = Field(
        default=None,
        gt=0,
        description="Unit replacement cost in USD (NUMERIC(14,2))",
    )
    signal_type: str | None = Field(
        default="logistics",
        description="Disruption signal category: logistics, financial, geopolitical, or news",
    )
    severity_hint: str | None = Field(
        default=None,
        description="Upstream disruption signal severity hint: LOW, MEDIUM, HIGH, CRITICAL",
    )
    disruption_description: str | None = Field(
        default=None,
        max_length=2000,
        description="Unstructured disruption narrative or news text",
    )
    pipeline_mode: Literal["auto", "fast_track", "full_track"] = Field(
        default="auto",
        description="Pipeline execution track: 'fast_track', 'full_track', or 'auto'",
    )

    @field_validator("component_sku")
    @classmethod
    def validate_sku(cls, v: str) -> str:
        cleaned = v.strip().upper()
        if not cleaned:
            raise ValueError("Component SKU must not be empty or whitespace.")
        return cleaned


class RiskEvaluationResponse(BaseModel):
    """Response payload returned by the risk evaluation pipeline."""

    model_config = ConfigDict(from_attributes=True)

    evaluation_id: str = Field(description="Unique evaluation transaction identifier")
    alert_id: str | None = Field(default=None, description="Persisted RiskAlert UUID")
    pipeline_track: Literal["FAST_TRACK", "FULL_TRACK"] = Field(
        description="Pipeline route taken: FAST_TRACK (sub-second deterministic) or FULL_TRACK (agentic)"
    )
    status: str = Field(description="Evaluation outcome status: EVALUATED, ESCALATED, COLLAPSED")
    component_sku: str = Field(description="Evaluated component SKU")
    supplier_id: str | None = Field(default=None, description="Supplier UUID or identifier")
    days_of_cover: Decimal | None = Field(
        default=None, description="Deterministic days of inventory remaining"
    )
    gap_days: Decimal | None = Field(
        default=None, description="Calculated coverage shortage gap in days"
    )
    shortage_volume: int | None = Field(default=None, description="Calculated shortage unit volume")
    financial_exposure_usd: Decimal | None = Field(
        default=None, description="Total plant downtime and shortage financial exposure in USD"
    )
    risk_level: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"] = Field(
        description="Evaluated risk severity rating"
    )
    requires_hitl: bool = Field(
        description="Whether mitigation expenditure requires Human-in-the-Loop authorization"
    )
    governing_spend_tier: str | None = Field(
        default=None, description="HITL spend authority tier: CATEGORY_MGR, PROC_DIRECTOR, DUAL_VP"
    )
    fast_track_reason: str | None = Field(
        default=None, description="Explanation of fast-track vs full-track classification"
    )
    evaluated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Evaluation timestamp in UTC",
    )


class RiskAlertResponse(BaseModel):
    """Domain model representing a single calculated risk alert."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="Risk alert UUID")
    supplier_id: str | None = Field(default=None, description="Supplier UUID")
    component_sku: str = Field(description="Impacted component SKU")
    risk_level: str = Field(description="Severity rating: CRITICAL, HIGH, MEDIUM, LOW")
    days_of_cover: Decimal | None = Field(
        default=None, description="Days of cover remaining at alert creation"
    )
    financial_exposure: Decimal | None = Field(
        default=None, description="Financial exposure amount in USD"
    )
    shortage_volume: int | None = Field(default=None, description="Shortage volume units")
    status: str = Field(
        description="Alert status: OPEN, INVESTIGATING, ACKNOWLEDGED, RESOLVED, CLOSED"
    )
    created_at: datetime = Field(description="Alert creation timestamp in UTC")


class RiskAlertListResponse(BaseModel):
    """Paginated risk alert feed."""

    items: list[RiskAlertResponse] = Field(description="Page of risk alert items")
    total: int = Field(ge=0, description="Total matching alert records")
    page: int = Field(ge=1, description="Current page number (1-indexed)")
    page_size: int = Field(ge=1, description="Page size limit")
    total_pages: int = Field(ge=0, description="Total available pages")


class AlertAcknowledgeRequest(BaseModel):
    """Request payload for acknowledging an active risk alert."""

    model_config = ConfigDict(extra="forbid")

    notes: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional acknowledgement or triage notes",
    )


class AlertAcknowledgeResponse(BaseModel):
    """Response payload returned when an alert is acknowledged."""

    id: str = Field(description="Risk alert UUID")
    status: Literal["ACKNOWLEDGED"] = Field(default="ACKNOWLEDGED")
    acknowledged_by: str = Field(description="User ID or username of acknowledging authority")
    acknowledged_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Acknowledgement timestamp in UTC",
    )
    notes: str | None = Field(default=None, description="Recorded acknowledgement notes")
