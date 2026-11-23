"""LangGraph AgentState & State Schema Definitions (P9-1).

Enforces:
- Layering Invariants (CLAUDE.md Sec 5.2 & Sec 11):
  * Typed state schema across multi-agent LangGraph workflow.
  * Explicit separation between deterministic data (metrics, plant IDs, stock) and synthesized text (narrative).
- The Triad of Responsibility (BR-RULE-001):
  * Numerical risk metrics (`days_of_cover`, `gap_days`, `shortage_volume`, `financial_exposure`)
    are strictly managed via Python Decimals produced by deterministic services.
- Immutable Audit & Forensic Tracing:
  * Reducer channels (`operator.add`) accumulate `execution_path`, `errors`, and `audit_events`.
"""

import operator
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal, TypedDict

from src.core.hitl_tokens import SpendTier
from src.kafka.schemas.risk_alert import RiskLevel

# ------------------------------------------------------------------------------
# Enums
# ------------------------------------------------------------------------------


class SignalType(StrEnum):
    """Classification taxonomy for incoming disruption signals."""

    NEWS = "news"
    FINANCIAL = "financial"
    LOGISTICS = "logistics"
    GEOPOLITICAL = "geopolitical"
    CUSTOM = "custom"


class WorkflowStatus(StrEnum):
    """Lifecycle progression states for the LangGraph detective agent workflow."""

    PENDING = "PENDING"
    TRIAGED = "TRIAGED"
    INVESTIGATING = "INVESTIGATING"
    RESEARCHING = "RESEARCHING"
    ANALYZING_CONTRACTS = "ANALYZING_CONTRACTS"
    CALCULATING_RISK = "CALCULATING_RISK"
    SYNTHESIZING = "SYNTHESIZING"
    PLANNING = "PLANNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
    DISMISSED = "DISMISSED"
    FAILED = "FAILED"


# ------------------------------------------------------------------------------
# Sub-structures
# ------------------------------------------------------------------------------


class EvidenceItem(TypedDict, total=False):
    """Ground truth evidence extracted from external or internal sources."""

    source_id: str
    source_type: str
    document_name: str | None
    verbatim_quote: str
    confidence: float
    timestamp: str | None


class RiskMetrics(TypedDict, total=False):
    """Deterministic mathematical outputs calculated strictly by Python risk engine."""

    days_of_cover: Decimal
    gap_days: Decimal
    shortage_volume: int
    financial_exposure: Decimal
    factory_halt_exposure: Decimal
    total_exposure: Decimal
    is_shortage: bool
    calculation_hash: str


class HITLDecision(TypedDict, total=False):
    """Human-in-the-loop governance sign-off payload."""

    approved: bool
    token_hash: str | None
    signer_id: str | None
    signer_role: str | None
    spend_tier: SpendTier | str | None
    reason: str | None
    timestamp: str | None


# ------------------------------------------------------------------------------
# Core LangGraph State Schema
# ------------------------------------------------------------------------------


class SupplierRiskState(TypedDict, total=False):
    """Comprehensive state channel schema for the LangGraph Detective Agent workflow.

    Uses `operator.add` reducers for list channels that accumulate entries across nodes
    (`execution_path`, `errors`, `audit_events`, `evidence`).
    """

    # Identity & Correlation
    alert_id: str
    case_id: str
    supplier_id: str
    supplier_name: str | None
    component_sku: str | None
    trace_id: str | None

    # Ingestion & Signal Data
    signal_type: Literal["financial", "logistics", "geopolitical", "news"] | str
    raw_signal: str
    quarantined_signal: str | None
    metadata: dict[str, Any]

    # Graph & Inventory Context
    impacted_plant_ids: list[str]
    is_single_source: bool
    current_stock: int | None
    daily_consumption_rate: Decimal | None
    eta_days: Decimal | None
    unit_cost_usd: Decimal | None

    # Quantitative Risk Metrics (Calculated by deterministic engine — never LLM)
    risk_metrics: dict[str, Any] | None
    severity: RiskLevel | str | None

    # Intelligence & Evidence (Quarantined text, research, contract clauses)
    evidence: Annotated[list[dict[str, Any]], operator.add]
    research_analysis: dict[str, Any] | None
    contract_analysis: dict[str, Any] | None

    # Qualitative Synthesis (LLM narrative explaining metrics)
    narrative: str | None

    # Mitigation & Governance
    recommendations: list[dict[str, Any]] | None
    recommended_action_id: str | None
    requires_hitl: bool
    governing_spend_tier: SpendTier | str | None
    hitl_decision: dict[str, Any] | None

    # Execution Telemetry & Error Reducers
    workflow_status: str
    current_node: str | None
    execution_path: Annotated[list[str], operator.add]
    errors: Annotated[list[str], operator.add]
    audit_events: Annotated[list[dict[str, Any]], operator.add]


# Alias for direct alignment with CLAUDE.md Section 11
AgentState = SupplierRiskState


# ------------------------------------------------------------------------------
# State Factory Helpers
# ------------------------------------------------------------------------------


def create_initial_state(
    alert_id: str,
    supplier_id: str,
    signal_type: SignalType | str = SignalType.NEWS,
    raw_signal: str = "",
    case_id: str | None = None,
    supplier_name: str | None = None,
    component_sku: str | None = None,
    trace_id: str | None = None,
    current_stock: int | None = None,
    daily_consumption_rate: Decimal | None = None,
    eta_days: Decimal | None = None,
    unit_cost_usd: Decimal | None = None,
    impacted_plant_ids: list[str] | None = None,
    is_single_source: bool = False,
    metadata: dict[str, Any] | None = None,
) -> SupplierRiskState:
    """Initialize a new clean SupplierRiskState instance with normalized defaults."""
    sig_str = signal_type.value if isinstance(signal_type, SignalType) else str(signal_type).lower()

    return {
        "alert_id": alert_id,
        "case_id": case_id or f"CASE-{alert_id}",
        "supplier_id": supplier_id,
        "supplier_name": supplier_name,
        "component_sku": component_sku,
        "trace_id": trace_id,
        "signal_type": sig_str,
        "raw_signal": raw_signal,
        "quarantined_signal": None,
        "metadata": metadata.copy() if metadata else {},
        "impacted_plant_ids": list(impacted_plant_ids) if impacted_plant_ids else [],
        "is_single_source": is_single_source,
        "current_stock": current_stock,
        "daily_consumption_rate": daily_consumption_rate,
        "eta_days": eta_days,
        "unit_cost_usd": unit_cost_usd,
        "risk_metrics": None,
        "severity": None,
        "evidence": [],
        "research_analysis": None,
        "contract_analysis": None,
        "narrative": None,
        "recommendations": None,
        "recommended_action_id": None,
        "requires_hitl": False,
        "governing_spend_tier": None,
        "hitl_decision": None,
        "workflow_status": WorkflowStatus.PENDING,
        "current_node": None,
        "execution_path": [],
        "errors": [],
        "audit_events": [],
    }
