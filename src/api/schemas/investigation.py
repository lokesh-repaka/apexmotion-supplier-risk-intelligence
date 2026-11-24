"""Pydantic v2 schemas for investigation API routes (P11-2).

Enforces:
- Layering Invariants (CLAUDE.md Sec 5.2): Schema validation only; zero risk math.
- Prompt Injection Defense: extra='forbid' to prevent unvalidated attribute injection.
- Decimal precision for monetary and coverage quantities (BR-RULE-001).
- Standardized asynchronous polling envelopes for LangGraph state machine telemetry.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class InvestigationStartRequest(BaseModel):
    """Payload to initiate a multi-agent disruption investigation."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    supplier_id: str = Field(
        ...,
        description="Target supplier identifier or UUID",
        min_length=1,
    )
    alert_id: str | None = Field(
        default=None,
        description="Optional associated risk alert UUID",
    )
    component_sku: str | None = Field(
        default=None,
        description="Optional impacted component SKU",
    )
    signal_type: str = Field(
        default="news",
        description="Disruption signal taxonomy: news, financial, logistics, geopolitical",
    )
    raw_signal: str = Field(
        default="",
        description="Raw unstructured disruption text (news report, SEC disclosure, email)",
    )
    external_source_url: str | None = Field(
        default=None,
        description="Optional source evidence or publication URL",
    )
    target_supplier_hint: str | None = Field(
        default=None,
        description="Optional human-readable supplier name hint",
    )
    severity_hint: str | None = Field(
        default=None,
        description="Optional initial severity indicator: CRITICAL, HIGH, MEDIUM, LOW",
    )
    current_stock: int | None = Field(
        default=None,
        description="Optional known current inventory on hand",
        ge=0,
    )
    daily_consumption_rate: Decimal | None = Field(
        default=None,
        description="Optional daily consumption rate (burn rate)",
        ge=Decimal("0.00"),
    )
    eta_days: Decimal | None = Field(
        default=None,
        description="Optional inbound delivery arrival timeline in days",
        ge=Decimal("0.00"),
    )
    unit_cost_usd: Decimal | None = Field(
        default=None,
        description="Optional component unit acquisition cost in USD",
        ge=Decimal("0.00"),
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional additional routing or contextual metadata",
    )
    wait_for_completion: bool = Field(
        default=False,
        description="If True, execute synchronously before responding; if False, dispatch background task",
    )


class InvestigationStartResponse(BaseModel):
    """Acknowledgement response when an investigation pipeline is launched."""

    model_config = ConfigDict(extra="forbid")

    investigation_id: str = Field(
        ...,
        description="Unique investigation run identifier (UUID)",
    )
    case_id: str = Field(
        ...,
        description="Canonical case dossier identifier, e.g. CASE-2026-...",
    )
    alert_id: str | None = Field(
        default=None,
        description="Associated risk alert identifier if linked",
    )
    status: str = Field(
        default="RUNNING",
        description="Initial lifecycle status: PENDING, RUNNING, INVESTIGATING",
    )
    poll_url: str = Field(
        ...,
        description="Polling endpoint URL for polling investigation status and results",
    )
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Investigation start timestamp in UTC",
    )
    estimated_completion_seconds: int = Field(
        default=90,
        description="Target SLO completion SLA duration in seconds (p95 <= 90s)",
    )
    message: str = Field(
        default="Investigation pipeline started successfully",
        description="Informational status message",
    )


class InvestigationDetailResponse(BaseModel):
    """Full detail record representing current status or finalized results of an investigation."""

    model_config = ConfigDict(extra="forbid")

    investigation_id: str = Field(
        ...,
        description="Unique investigation run identifier (UUID)",
    )
    case_id: str = Field(
        ...,
        description="Canonical case dossier identifier",
    )
    alert_id: str | None = Field(
        default=None,
        description="Associated risk alert identifier",
    )
    supplier_id: str = Field(
        ...,
        description="Disrupted supplier identifier",
    )
    component_sku: str | None = Field(
        default=None,
        description="Impacted component SKU",
    )
    status: str = Field(
        ...,
        description="Current execution status: PENDING, RUNNING, AWAITING_APPROVAL, COMPLETED, DISMISSED, FAILED",
    )
    current_node: str | None = Field(
        default=None,
        description="Currently active or last executed LangGraph state machine node",
    )
    execution_path: list[str] = Field(
        default_factory=list,
        description="Chronological sequence of executed graph nodes",
    )
    risk_metrics: dict[str, Any] | None = Field(
        default=None,
        description="Quantitative deterministic risk metrics (Days of Cover, Shortage, Exposure)",
    )
    severity: str | None = Field(
        default=None,
        description="Calculated risk severity: CRITICAL, HIGH, MEDIUM, LOW",
    )
    narrative: str | None = Field(
        default=None,
        description="Synthesized executive narrative explaining the calculated risk numbers",
    )
    research_analysis: dict[str, Any] | None = Field(
        default=None,
        description="Extracted external news, geopolitical, and regulatory intelligence",
    )
    contract_analysis: dict[str, Any] | None = Field(
        default=None,
        description="Analyzed master supply agreement terms, delay penalties, and liability limits",
    )
    recommendations: list[dict[str, Any]] | None = Field(
        default=None,
        description="Ranked mitigation scenarios evaluated by the recommendation agent",
    )
    recommended_action_id: str | None = Field(
        default=None,
        description="Top-recommended mitigation scenario identifier",
    )
    requires_hitl: bool = Field(
        default=False,
        description="Whether this investigation requires human authorization sign-off",
    )
    governing_spend_tier: str | None = Field(
        default=None,
        description="Required spend approval authority tier: CATEGORY_MGR, PROC_DIRECTOR, DUAL_VP",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="List of captured execution errors or warning notices",
    )
    started_at: datetime = Field(
        ...,
        description="Investigation creation timestamp in UTC",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="Investigation completion or suspension timestamp in UTC",
    )
    duration_ms: int | None = Field(
        default=None,
        description="Elapsed runtime in milliseconds",
    )
    tokens_used: int | None = Field(
        default=None,
        description="Total LLM tokens consumed across all agent steps",
    )
    cost_usd: Decimal | None = Field(
        default=None,
        description="Total calculated LLM inference cost in USD",
    )
