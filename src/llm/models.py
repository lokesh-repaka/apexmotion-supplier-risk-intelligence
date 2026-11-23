"""Pydantic structured output response models for LLM interactions (P8-3).

Enforces:
- Layering Invariants (CLAUDE.md Sec 5.2 & Sec 20.4): Structured outputs everywhere.
  Every LLM call uses a strongly-typed Pydantic response model. Free-text parsing is strictly rejected.
- The Triad of Responsibility (BR-RULE-001):
  * Mathematical numbers (days of cover, gap days, shortage volume, financial exposure)
    are calculated by pure deterministic Python microservices.
  * The LLM synthesizes evidence, extracts contract clauses, and explains the situation in narrative form.
  * All financial and penalty values are strictly typed as Python Decimal.
- Prompt injection defense: All schemas enforce `extra='forbid'`, rejecting untrusted injected fields.
- Mandatory Human Approval Gating (HITL): Actions requiring financial commitments cannot bypass human authorization.
"""

import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from src.core.hitl_tokens import SpendTier
from src.kafka.schemas.risk_alert import RiskLevel

# Regex to strip markdown code blocks around JSON payloads
MARKDOWN_JSON_FENCE_REGEX = re.compile(
    r"^\s*```(?:json)?\s*([\s\S]*?)\s*```\s*$",
    re.IGNORECASE,
)


# ------------------------------------------------------------------------------
# Exceptions
# ------------------------------------------------------------------------------


class StructuredOutputParsingError(Exception):
    """Raised when an LLM produces free-text, malformed JSON, or schema-violating output."""

    def __init__(
        self,
        message: str = "LLM response failed structured schema validation.",
        raw_output: str = "",
        target_model: str = "",
        validation_error: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = 422
        self.error_code = "ERR_422_UNSTRUCTURED_OUTPUT"
        self.raw_output = raw_output
        self.target_model = target_model
        self.validation_error = validation_error


# ------------------------------------------------------------------------------
# Common Enums & Sub-models
# ------------------------------------------------------------------------------


class CitationSourceType(StrEnum):
    """Source provenance types for verifiable ground truth citations."""

    NEWS = "NEWS"
    CONTRACT = "CONTRACT"
    ERP_PURCHASE_ORDER = "ERP_PURCHASE_ORDER"
    MES_TELEMETRY = "MES_TELEMETRY"
    GRAPH_EDGE = "GRAPH_EDGE"
    SEC_FILING = "SEC_FILING"
    GEOPOLITICAL_FEED = "GEOPOLITICAL_FEED"
    CUSTOMS_MANIFEST = "CUSTOMS_MANIFEST"


class IncidentCategory(StrEnum):
    """Taxonomy of supply chain disruption incidents."""

    FACILITY_FIRE = "FACILITY_FIRE"
    NATURAL_DISASTER = "NATURAL_DISASTER"
    LABOR_STRIKE = "LABOR_STRIKE"
    GEOPOLITICAL_SANCTION = "GEOPOLITICAL_SANCTION"
    PORT_CONGESTION = "PORT_CONGESTION"
    SUPPLIER_INSOLVENCY = "SUPPLIER_INSOLVENCY"
    QUALITY_DEFECT = "QUALITY_DEFECT"
    LOGISTICS_DELAY = "LOGISTICS_DELAY"
    CYBERATTACK = "CYBERATTACK"
    UNKNOWN = "UNKNOWN"


class MitigationStrategyType(StrEnum):
    """Types of supply chain mitigation strategies."""

    LOGISTICS_ACCELERATION = "LOGISTICS_ACCELERATION"
    SECONDARY_SOURCING = "SECONDARY_SOURCING"
    PRODUCTION_REBALANCING = "PRODUCTION_REBALANCING"
    BUFFER_DEPLETION = "BUFFER_DEPLETION"
    SPOT_PURCHASE = "SPOT_PURCHASE"


class Citation(BaseModel):
    """Grounding citation linking an LLM assertion to source documents or ERP data."""

    source_id: str = Field(..., description="Unique source document or record identifier")
    source_type: CitationSourceType = Field(
        ..., description="Classification of the ground truth artifact"
    )
    document_name: str | None = Field(default=None, description="Human-readable title or filename")
    page_or_section: str | None = Field(default=None, description="Location within source document")
    verbatim_quote: str = Field(
        ..., min_length=1, description="Verbatim text extracted from source"
    )
    url_or_reference: str | None = Field(default=None, description="Link or reference key")

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


# ------------------------------------------------------------------------------
# Node-Specific Response Models
# ------------------------------------------------------------------------------


class ResearchAnalysis(BaseModel):
    """Structured output for Research Agent node (news, SEC filings, geopolitical feeds)."""

    summary: str = Field(
        ..., min_length=10, description="Distilled executive summary of external intelligence"
    )
    incident_category: IncidentCategory = Field(..., description="Classified disruption category")
    event_date: str | None = Field(
        default=None, description="Reported date or timeframe of the incident"
    )
    affected_locations: list[str] = Field(
        default_factory=list,
        description="Geographic regions, facilities, or ports affected",
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Extraction confidence score bounded within [0.0, 1.0]",
    )
    key_findings: list[str] = Field(
        ...,
        min_length=1,
        description="Bulleted evidence points extracted from quarantined input",
    )
    citations: list[Citation] = Field(
        default_factory=list,
        description="Verifiable source citations for extracted claims",
    )
    has_disruption_signal: bool = Field(
        ...,
        description="Whether evidence indicates an operational supply chain disruption",
    )

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class ContractAnalysis(BaseModel):
    """Structured output for Contract Agent node (extracted clauses via vLLM)."""

    supplier_id: str = Field(..., description="Target supplier identifier")
    contract_id: str | None = Field(default=None, description="Contract agreement reference ID")
    payment_terms: str | None = Field(
        default=None, description="Commercial payment terms (e.g. Net 30)"
    )
    notice_period_days: int | None = Field(
        default=None,
        ge=0,
        description="Minimum contractual notice period for delivery delays",
    )
    delay_penalty_percentage_per_day: Decimal | None = Field(
        default=None,
        ge=0,
        description="Daily delay penalty percentage in Decimal format",
    )
    air_freight_surcharge_liability: str = Field(
        default="UNSPECIFIED",
        description="Liability allocation for expedited air freight (SUPPLIER, APEXMOTION, SPLIT_50_50, UNSPECIFIED)",
    )
    has_force_majeure: bool = Field(
        ..., description="Whether contract contains an active force majeure clause"
    )
    force_majeure_clause: str | None = Field(
        default=None,
        description="Verbatim text of the governing force majeure provision",
    )
    alternate_suppliers_authorized: list[str] = Field(
        default_factory=list,
        description="List of pre-approved secondary manufacturers from AML clauses",
    )
    liability_cap_usd: Decimal | None = Field(
        default=None,
        ge=0,
        description="Maximum contractual liability ceiling in USD Decimal",
    )
    citations: list[Citation] = Field(
        default_factory=list,
        description="Clause citations with section headings and page references",
    )

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    @field_validator("delay_penalty_percentage_per_day", "liability_cap_usd", mode="before")
    @classmethod
    def _coerce_decimal(cls, val: Any) -> Decimal | None:
        if val is None or val == "":
            return None
        return Decimal(str(val))


class RiskNarrative(BaseModel):
    """Structured output for Risk Synthesis node (narrative explaining deterministic numbers).

    CRITICAL ARCHITECTURAL INVARIANT:
    The LLM writes the narrative explaining the situation and numbers.
    It is STRICTLY FORBIDDEN from calculating days of cover or financial exposure (BR-RULE-001).
    """

    executive_summary: str = Field(
        ...,
        min_length=20,
        description="High-level C-suite summary explaining why the supplier is at risk",
    )
    root_cause_analysis: str = Field(
        ...,
        min_length=20,
        description="Contextual analysis connecting external signal to manufacturing disruption",
    )
    operational_impact: str = Field(
        ...,
        min_length=20,
        description="Explanation of affected automotive assembly hubs and vehicle programs",
    )
    runway_and_exposure_commentary: str = Field(
        ...,
        min_length=20,
        description="Contextual commentary on the deterministic Days of Cover and dollar exposure",
    )
    citations: list[Citation] = Field(
        default_factory=list,
        description="Grounding links to ERP purchase orders, telemetry, and news",
    )

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class MitigationScenario(BaseModel):
    """Discrete actionable mitigation option ranked by financial benefit."""

    scenario_id: str = Field(..., description="Identifier e.g. SCENARIO-1, SCENARIO-2")
    title: str = Field(..., description="Short descriptive title of the action")
    strategy_type: MitigationStrategyType = Field(
        ..., description="Category of mitigation strategy"
    )
    description: str = Field(
        ..., min_length=15, description="Detailed operational execution instructions"
    )
    estimated_cost_usd: Decimal = Field(
        ..., ge=0, description="Cost to execute mitigation in Decimal USD"
    )
    avoided_loss_usd: Decimal = Field(..., ge=0, description="Downtime loss avoided in Decimal USD")
    net_financial_benefit_usd: Decimal = Field(
        ...,
        description="Net benefit calculated as avoided_loss_usd - estimated_cost_usd",
    )
    implementation_lead_time_days: Decimal = Field(
        ..., ge=0, description="Lead time to enact mitigation in days"
    )
    lead_time_reduction_days: Decimal = Field(..., ge=0, description="Shortage days eliminated")
    feasibility_score: float = Field(
        ..., ge=0.0, le=1.0, description="Feasibility score in [0.0, 1.0]"
    )
    required_spend_tier: SpendTier = Field(
        ..., description="HITL spend governance tier determined by cost"
    )
    target_supplier_id: str | None = Field(
        default=None, description="Target alternate or primary supplier ID"
    )
    target_sku: str = Field(..., description="Part SKU affected")
    target_plant_id: str = Field(..., description="Assembly plant ID")
    action_type: str = Field(
        ...,
        description="Deterministic action code e.g. AMEND_PO_AIR_FREIGHT, DISPATCH_SECONDARY_PO",
    )
    risk_notes: list[str] = Field(
        default_factory=list, description="Residual operational risks or caveats"
    )

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    @field_validator(
        "estimated_cost_usd",
        "avoided_loss_usd",
        "net_financial_benefit_usd",
        "implementation_lead_time_days",
        "lead_time_reduction_days",
        mode="before",
    )
    @classmethod
    def _coerce_decimal_fields(cls, val: Any) -> Decimal:
        return Decimal(str(val))

    @model_validator(mode="after")
    def _validate_net_financial_benefit(self) -> "MitigationScenario":
        expected_net = self.avoided_loss_usd - self.estimated_cost_usd
        if self.net_financial_benefit_usd != expected_net:
            raise ValueError(
                f"Net financial benefit ({self.net_financial_benefit_usd}) does not match "
                f"avoided_loss_usd ({self.avoided_loss_usd}) - estimated_cost_usd ({self.estimated_cost_usd}) = {expected_net}"
            )
        return self


class RecommendationReport(BaseModel):
    """Structured output for Recommendation Agent node (ranked mitigation options & HITL routing)."""

    alert_id: str = Field(..., description="Associated risk alert ID")
    component_sku: str = Field(..., description="Component part number")
    supplier_id: str = Field(..., description="Primary supplier identifier")
    scenarios: list[MitigationScenario] = Field(
        ...,
        min_length=1,
        max_length=5,
        description="Ranked list of mitigation options (typically 3)",
    )
    recommended_scenario_id: str = Field(
        ..., description="Scenario ID recommended for human sign-off"
    )
    justification: str = Field(
        ..., min_length=10, description="Executive justification for the recommended option"
    )
    requires_hitl: bool = Field(
        default=True,
        description="Whether action mandates authenticated human authorization",
    )
    governing_spend_tier: SpendTier = Field(
        ...,
        description="Highest spend tier required among the proposed actions",
    )

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    @model_validator(mode="after")
    def _validate_recommendations(self) -> "RecommendationReport":
        scenario_ids = {s.scenario_id for s in self.scenarios}
        if self.recommended_scenario_id not in scenario_ids:
            raise ValueError(
                f"recommended_scenario_id '{self.recommended_scenario_id}' not found in scenarios list: {sorted(scenario_ids)}"
            )

        # Enforce BR-RULE-001: Any scenario involving financial spend CANNOT bypass HITL
        any_spend = any(s.estimated_cost_usd > Decimal("0.00") for s in self.scenarios)
        if any_spend and not self.requires_hitl:
            raise ValueError(
                "requires_hitl cannot be False when mitigation scenarios require financial spend (BR-RULE-001)"
            )

        return self


class IncidentCaseDossier(BaseModel):
    """Composite Investigation Case Dossier integrating all agent findings and deterministic math."""

    case_id: str = Field(..., description="Unique case dossier identifier")
    supplier_id: str = Field(..., description="Target supplier ID")
    component_sku: str = Field(..., description="Critical component part number")
    severity: RiskLevel = Field(..., description="Deterministic risk severity level")
    research_analysis: ResearchAnalysis = Field(
        ..., description="External news and intelligence findings"
    )
    contract_analysis: ContractAnalysis = Field(
        ..., description="Extracted contract clauses and liabilities"
    )
    risk_narrative: RiskNarrative = Field(
        ..., description="Grounded narrative synthesized by the LLM"
    )
    recommendations: RecommendationReport = Field(
        ..., description="Proposed mitigation scenarios and HITL tier"
    )
    days_of_cover: Decimal = Field(..., ge=0, description="Deterministic inventory runway in days")
    shortage_gap_days: Decimal = Field(
        ..., ge=0, description="Deterministic replenishment coverage gap in days"
    )
    shortage_volume: int = Field(..., ge=0, description="Deterministic unit deficit volume")
    financial_exposure_usd: Decimal = Field(
        ..., ge=0, description="Deterministic total plant exposure in Decimal USD"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC creation timestamp",
    )

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    @field_validator(
        "days_of_cover",
        "shortage_gap_days",
        "financial_exposure_usd",
        mode="before",
    )
    @classmethod
    def _coerce_decimal_metrics(cls, val: Any) -> Decimal:
        return Decimal(str(val))


# ------------------------------------------------------------------------------
# Structured Output Parsing & Validation Infrastructure
# ------------------------------------------------------------------------------


def parse_structured_llm_response[T: BaseModel](raw_text: str, schema_class: type[T]) -> T:
    """Parse and validate an LLM completion string against a target Pydantic model.

    Enforces:
    1. Rejection of unstructured free-text responses (raises StructuredOutputParsingError)
    2. Stripping of markdown code blocks (```json ... ```)
    3. Strict validation against schema_class with extra='forbid'
    4. Exact Decimal coercion for financial fields
    """
    if not raw_text or not raw_text.strip():
        raise StructuredOutputParsingError(
            message="LLM returned empty or whitespace output; expected structured JSON.",
            raw_output=raw_text,
            target_model=schema_class.__name__,
        )

    # 1. Strip markdown fences if present
    cleaned = raw_text.strip()
    fence_match = MARKDOWN_JSON_FENCE_REGEX.match(cleaned)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    # 2. Parse JSON
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise StructuredOutputParsingError(
            message=f"LLM produced non-JSON free-text output: {exc}",
            raw_output=raw_text,
            target_model=schema_class.__name__,
            validation_error=str(exc),
        ) from exc

    if not isinstance(data, dict):
        raise StructuredOutputParsingError(
            message=f"Expected JSON object (dict) from LLM, got {type(data).__name__}.",
            raw_output=raw_text,
            target_model=schema_class.__name__,
        )

    # 3. Validate against Pydantic schema
    try:
        return schema_class.model_validate(data)
    except ValidationError as val_err:
        raise StructuredOutputParsingError(
            message=f"LLM output violated {schema_class.__name__} schema constraints: {val_err}",
            raw_output=raw_text,
            target_model=schema_class.__name__,
            validation_error=str(val_err),
        ) from val_err
