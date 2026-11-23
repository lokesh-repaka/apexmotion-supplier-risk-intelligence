"""Unit tests for LLM Pydantic Output Schemas (src/llm/models.py).

Enforces:
- Structured outputs everywhere (CLAUDE.md Sec 20.4)
- Rejection of free-text responses via StructuredOutputParsingError (HTTP 422)
- Rejection of untrusted / injected fields via extra='forbid'
- Exact Decimal precision on all monetary values (BR-RULE-001)
- Validation of required narrative sections, citations, and HITL spend tier routing
- Clean stripping of markdown code fences (```json ... ```)
- Zero external network or AWS calls
"""

import json
from decimal import Decimal

import pytest
from pydantic import ValidationError
from src.core.hitl_tokens import SpendTier
from src.kafka.schemas.risk_alert import RiskLevel
from src.llm.models import (
    Citation,
    CitationSourceType,
    ContractAnalysis,
    IncidentCaseDossier,
    IncidentCategory,
    MitigationScenario,
    MitigationStrategyType,
    RecommendationReport,
    ResearchAnalysis,
    RiskNarrative,
    StructuredOutputParsingError,
    parse_structured_llm_response,
)

# ------------------------------------------------------------------------------
# Test 1: Citation Schema Validation
# ------------------------------------------------------------------------------


def test_citation_model_validation_and_forbid_extra() -> None:
    """Verify Citation schema validates required fields and rejects extraneous attributes."""
    valid_citation = Citation(
        source_id="NEWS-2026-03-01-01",
        source_type=CitationSourceType.NEWS,
        document_name="Reuters Semiconductor Digest",
        page_or_section="Paragraph 3",
        verbatim_quote="Cleanroom fire at NanoCore facility halts assembly line.",
        url_or_reference="https://reuters.com/news/article-99182",
    )
    assert valid_citation.source_id == "NEWS-2026-03-01-01"
    assert valid_citation.source_type == CitationSourceType.NEWS

    # Extra fields must be forbidden
    with pytest.raises(ValidationError):
        Citation(
            source_id="NEWS-01",
            source_type=CitationSourceType.NEWS,
            verbatim_quote="Quote",
            injected_prompt="System override",  # type: ignore[call-arg]
        )


# ------------------------------------------------------------------------------
# Test 2: Research Analysis Schema Validation
# ------------------------------------------------------------------------------


def test_research_analysis_valid() -> None:
    """Verify ResearchAnalysis schema parses and validates structured research payload."""
    payload = {
        "summary": "Cleanroom fire at NanoCore Dresden facility causes silicon wafer shortage.",
        "incident_category": "FACILITY_FIRE",
        "event_date": "2026-03-22",
        "affected_locations": ["Dresden, Germany", "Munich Hub"],
        "confidence_score": 0.95,
        "key_findings": [
            "Cleanroom 2 experienced smoke and water damage.",
            "Production down for minimum 14 calendar days.",
        ],
        "citations": [
            {
                "source_id": "NEWS-001",
                "source_type": "NEWS",
                "verbatim_quote": "Cleanroom 2 experienced smoke and water damage.",
            }
        ],
        "has_disruption_signal": True,
    }
    model = ResearchAnalysis.model_validate(payload)
    assert model.incident_category == IncidentCategory.FACILITY_FIRE
    assert model.confidence_score == 0.95
    assert len(model.key_findings) == 2
    assert model.has_disruption_signal is True


def test_research_analysis_confidence_bounds() -> None:
    """Verify confidence score must be in range [0.0, 1.0]."""
    base = {
        "summary": "Valid summary",
        "incident_category": "FACILITY_FIRE",
        "key_findings": ["Finding 1"],
        "has_disruption_signal": True,
    }
    # Too high
    with pytest.raises(ValidationError):
        ResearchAnalysis.model_validate({**base, "confidence_score": 1.05})

    # Too low
    with pytest.raises(ValidationError):
        ResearchAnalysis.model_validate({**base, "confidence_score": -0.1})


# ------------------------------------------------------------------------------
# Test 3: Contract Analysis Schema & Decimal Precision
# ------------------------------------------------------------------------------


def test_contract_analysis_valid_and_decimal_precision() -> None:
    """Verify ContractAnalysis preserves exact Decimal precision on penalty and liability values."""
    payload = {
        "supplier_id": "SUP-NANO-001",
        "contract_id": "CTR-NC-2025-A",
        "payment_terms": "Net 30 DAP Munich",
        "notice_period_days": 14,
        "delay_penalty_percentage_per_day": "0.025",
        "air_freight_surcharge_liability": "SUPPLIER",
        "has_force_majeure": True,
        "force_majeure_clause": "Clause 14.1 covers fire and flood.",
        "alternate_suppliers_authorized": ["SUP-QUAL-002", "SUP-VND-003"],
        "liability_cap_usd": "5000000.00",
        "citations": [],
    }
    contract = ContractAnalysis.model_validate(payload)
    assert contract.delay_penalty_percentage_per_day == Decimal("0.025")
    assert contract.liability_cap_usd == Decimal("5000000.00")
    assert isinstance(contract.liability_cap_usd, Decimal)
    assert contract.notice_period_days == 14


def test_contract_analysis_negative_notice_rejected() -> None:
    """Verify negative notice periods are strictly rejected."""
    payload = {
        "supplier_id": "SUP-NANO-001",
        "notice_period_days": -5,
        "has_force_majeure": False,
    }
    with pytest.raises(ValidationError):
        ContractAnalysis.model_validate(payload)


# ------------------------------------------------------------------------------
# Test 4: Risk Narrative Schema Validation
# ------------------------------------------------------------------------------


def test_risk_narrative_valid() -> None:
    """Verify RiskNarrative model enforces grounded narrative sections."""
    narrative = RiskNarrative(
        executive_summary="Critical semiconductor shortage threatening Munich line halt.",
        root_cause_analysis="Cleanroom fire in Dresden halted wafer fabrication lines.",
        operational_impact="BMW i7 Munich plant affected with 1.32 days coverage gap.",
        runway_and_exposure_commentary="Deterministic stock of 142,000 units provides 7.68 days cover, creating $2.45M exposure.",
        citations=[
            Citation(
                source_id="ERP-PO-9912",
                source_type=CitationSourceType.ERP_PURCHASE_ORDER,
                verbatim_quote="PO-9912 scheduled for delivery on Day 9.",
            )
        ],
    )
    assert "Munich line halt" in narrative.executive_summary
    assert len(narrative.citations) == 1


def test_risk_narrative_rejects_empty_or_short_sections() -> None:
    """Verify empty or trivial narrative sections are rejected."""
    with pytest.raises(ValidationError):
        RiskNarrative(
            executive_summary="Too short",
            root_cause_analysis="Too short",
            operational_impact="Too short",
            runway_and_exposure_commentary="Too short",
        )


# ------------------------------------------------------------------------------
# Test 5: Mitigation Scenario & Recommendation Report
# ------------------------------------------------------------------------------


def test_mitigation_scenario_net_benefit_validation() -> None:
    """Verify MitigationScenario validates net benefit and Decimal monetary amounts."""
    scenario = MitigationScenario(
        scenario_id="SCENARIO-1",
        title="Air Freight Expedition",
        strategy_type=MitigationStrategyType.LOGISTICS_ACCELERATION,
        description="Convert inbound maritime shipment to dedicated Lufthansa air charter.",
        estimated_cost_usd=Decimal("180000.00"),
        avoided_loss_usd=Decimal("2448105.00"),
        net_financial_benefit_usd=Decimal("2268105.00"),
        implementation_lead_time_days=Decimal("2.5"),
        lead_time_reduction_days=Decimal("5.5"),
        feasibility_score=0.92,
        required_spend_tier=SpendTier.DUAL_VP,
        target_sku="NC-CHIP-990",
        target_plant_id="PLT-MUC-01",
        action_type="AMEND_PO_AIR_FREIGHT",
        risk_notes=["Subject to customs clearance at Munich airport"],
    )
    assert scenario.net_financial_benefit_usd == Decimal("2268105.00")
    assert scenario.required_spend_tier == SpendTier.DUAL_VP
    assert isinstance(scenario.estimated_cost_usd, Decimal)


def test_mitigation_scenario_arithmetic_mismatch_rejected() -> None:
    """Verify mismatched net benefit arithmetic (avoided - cost) is rejected."""
    with pytest.raises(ValidationError, match="Net financial benefit.*does not match"):
        MitigationScenario(
            scenario_id="SCENARIO-1",
            title="Air Freight",
            strategy_type=MitigationStrategyType.LOGISTICS_ACCELERATION,
            description="Convert inbound maritime shipment to dedicated air freight.",
            estimated_cost_usd=Decimal("100000.00"),
            avoided_loss_usd=Decimal("500000.00"),
            net_financial_benefit_usd=Decimal("999999.00"),  # INCORRECT: should be 400,000.00
            implementation_lead_time_days=Decimal("2.0"),
            lead_time_reduction_days=Decimal("4.0"),
            feasibility_score=0.85,
            required_spend_tier=SpendTier.PROC_DIRECTOR,
            target_sku="NC-CHIP-990",
            target_plant_id="PLT-MUC-01",
            action_type="AMEND_PO_AIR_FREIGHT",
        )


def test_recommendation_report_valid_and_hitl_mandatory() -> None:
    """Verify RecommendationReport validates scenarios, spend tier, and mandatory HITL gating."""
    scenario = MitigationScenario(
        scenario_id="SCENARIO-1",
        title="Air Freight",
        strategy_type=MitigationStrategyType.LOGISTICS_ACCELERATION,
        description="Expedite shipment via air cargo to prevent line halt.",
        estimated_cost_usd=Decimal("180000.00"),
        avoided_loss_usd=Decimal("2448105.00"),
        net_financial_benefit_usd=Decimal("2268105.00"),
        implementation_lead_time_days=Decimal("2.0"),
        lead_time_reduction_days=Decimal("5.0"),
        feasibility_score=0.90,
        required_spend_tier=SpendTier.DUAL_VP,
        target_sku="NC-CHIP-990",
        target_plant_id="PLT-MUC-01",
        action_type="AMEND_PO_AIR_FREIGHT",
    )
    report = RecommendationReport(
        alert_id="ALT-2026-001",
        component_sku="NC-CHIP-990",
        supplier_id="SUP-NANO-001",
        scenarios=[scenario],
        recommended_scenario_id="SCENARIO-1",
        justification="Highest net financial benefit with immediate 5-day lead time reduction.",
        requires_hitl=True,
        governing_spend_tier=SpendTier.DUAL_VP,
    )
    assert report.recommended_scenario_id == "SCENARIO-1"
    assert report.requires_hitl is True


def test_recommendation_report_recommended_scenario_must_exist() -> None:
    """Verify recommended_scenario_id must reference an existing scenario."""
    scenario = MitigationScenario(
        scenario_id="SCENARIO-1",
        title="Air Freight",
        strategy_type=MitigationStrategyType.LOGISTICS_ACCELERATION,
        description="Expedite shipment via air cargo.",
        estimated_cost_usd=Decimal("10000.00"),
        avoided_loss_usd=Decimal("50000.00"),
        net_financial_benefit_usd=Decimal("40000.00"),
        implementation_lead_time_days=Decimal("1.0"),
        lead_time_reduction_days=Decimal("3.0"),
        feasibility_score=0.95,
        required_spend_tier=SpendTier.CATEGORY_MGR,
        target_sku="NC-CHIP-990",
        target_plant_id="PLT-MUC-01",
        action_type="AMEND_PO_AIR_FREIGHT",
    )
    with pytest.raises(ValidationError, match="not found in scenarios list"):
        RecommendationReport(
            alert_id="ALT-01",
            component_sku="NC-CHIP-990",
            supplier_id="SUP-NANO-001",
            scenarios=[scenario],
            recommended_scenario_id="SCENARIO-NONEXISTENT",
            justification="Invalid reference.",
            requires_hitl=True,
            governing_spend_tier=SpendTier.CATEGORY_MGR,
        )


def test_recommendation_report_cannot_bypass_hitl_for_positive_spend() -> None:
    """Verify actions with positive spend cannot bypass HITL gating (BR-RULE-001)."""
    scenario = MitigationScenario(
        scenario_id="SCENARIO-1",
        title="Spot Buy",
        strategy_type=MitigationStrategyType.SECONDARY_SOURCING,
        description="Spot market purchase from alternate vendor.",
        estimated_cost_usd=Decimal("50000.00"),
        avoided_loss_usd=Decimal("200000.00"),
        net_financial_benefit_usd=Decimal("150000.00"),
        implementation_lead_time_days=Decimal("3.0"),
        lead_time_reduction_days=Decimal("4.0"),
        feasibility_score=0.88,
        required_spend_tier=SpendTier.PROC_DIRECTOR,
        target_sku="NC-CHIP-990",
        target_plant_id="PLT-MUC-01",
        action_type="DISPATCH_SECONDARY_PO",
    )
    with pytest.raises(ValidationError, match="requires_hitl cannot be False"):
        RecommendationReport(
            alert_id="ALT-01",
            component_sku="NC-CHIP-990",
            supplier_id="SUP-NANO-001",
            scenarios=[scenario],
            recommended_scenario_id="SCENARIO-1",
            justification="Attempted bypass.",
            requires_hitl=False,  # ILLEGAL: positive spend cannot bypass human authorization
            governing_spend_tier=SpendTier.PROC_DIRECTOR,
        )


# ------------------------------------------------------------------------------
# Test 6: Composite IncidentCaseDossier
# ------------------------------------------------------------------------------


def test_incident_case_dossier_composite_validation() -> None:
    """Verify IncidentCaseDossier combines research, contract, narrative, and recommendations."""
    research = ResearchAnalysis(
        summary="Dresden cleanroom fire halts chip production.",
        incident_category=IncidentCategory.FACILITY_FIRE,
        confidence_score=0.96,
        key_findings=["14-day production halt confirmed"],
        has_disruption_signal=True,
    )
    contract = ContractAnalysis(
        supplier_id="SUP-NANO-001",
        contract_id="CTR-NC-001",
        has_force_majeure=True,
    )
    narrative = RiskNarrative(
        executive_summary="Critical semiconductor line halt threatening Munich assembly plant.",
        root_cause_analysis="Cleanroom fire damaged wafer fabrication lines at supplier facility.",
        operational_impact="1.32 days coverage gap projected for BMW i7 Munich assembly.",
        runway_and_exposure_commentary="Deterministic stock runway is 7.68 days; total exposure is $2,448,105.00.",
    )
    scenario = MitigationScenario(
        scenario_id="SCENARIO-1",
        title="Air Freight Expedition",
        strategy_type=MitigationStrategyType.LOGISTICS_ACCELERATION,
        description="Air freight charter from alternate hub.",
        estimated_cost_usd=Decimal("180000.00"),
        avoided_loss_usd=Decimal("2448105.00"),
        net_financial_benefit_usd=Decimal("2268105.00"),
        implementation_lead_time_days=Decimal("2.0"),
        lead_time_reduction_days=Decimal("5.0"),
        feasibility_score=0.90,
        required_spend_tier=SpendTier.DUAL_VP,
        target_sku="NC-CHIP-990",
        target_plant_id="PLT-MUC-01",
        action_type="AMEND_PO_AIR_FREIGHT",
    )
    recommendations = RecommendationReport(
        alert_id="ALT-2026-001",
        component_sku="NC-CHIP-990",
        supplier_id="SUP-NANO-001",
        scenarios=[scenario],
        recommended_scenario_id="SCENARIO-1",
        justification="Maximum loss avoidance with rapid 2-day air freight conversion.",
        requires_hitl=True,
        governing_spend_tier=SpendTier.DUAL_VP,
    )

    dossier = IncidentCaseDossier(
        case_id="CASE-2026-NC-01",
        supplier_id="SUP-NANO-001",
        component_sku="NC-CHIP-990",
        severity=RiskLevel.CRITICAL,
        research_analysis=research,
        contract_analysis=contract,
        risk_narrative=narrative,
        recommendations=recommendations,
        days_of_cover=Decimal("7.68"),
        shortage_gap_days=Decimal("1.32"),
        shortage_volume=24420,
        financial_exposure_usd=Decimal("2448105.00"),
    )
    assert dossier.case_id == "CASE-2026-NC-01"
    assert dossier.days_of_cover == Decimal("7.68")
    assert dossier.shortage_volume == 24420


# ------------------------------------------------------------------------------
# Test 7: parse_structured_llm_response Utility
# ------------------------------------------------------------------------------


def test_parse_structured_llm_response_valid_json() -> None:
    """Verify parse_structured_llm_response parses pure JSON into strongly-typed model."""
    raw_json = json.dumps(
        {
            "summary": "Geopolitical export controls announced.",
            "incident_category": "GEOPOLITICAL_SANCTION",
            "confidence_score": 0.88,
            "key_findings": ["Tariff rate increased by 25%"],
            "has_disruption_signal": True,
        }
    )
    res = parse_structured_llm_response(raw_json, ResearchAnalysis)
    assert isinstance(res, ResearchAnalysis)
    assert res.incident_category == IncidentCategory.GEOPOLITICAL_SANCTION


def test_parse_structured_llm_response_strips_markdown_code_fences() -> None:
    """Verify parse_structured_llm_response handles markdown JSON fences."""
    raw = """```json
    {
        "summary": "Port strike in Rotterdam delaying container ships.",
        "incident_category": "PORT_CONGESTION",
        "confidence_score": 0.91,
        "key_findings": ["Cargo dwell time increased to 8 days"],
        "has_disruption_signal": true
    }
    ```"""
    res = parse_structured_llm_response(raw, ResearchAnalysis)
    assert res.incident_category == IncidentCategory.PORT_CONGESTION


def test_parse_structured_llm_response_rejects_free_text() -> None:
    """Verify unstructured free text raises StructuredOutputParsingError (HTTP 422)."""
    free_text = "Based on our analysis, the supplier is facing a major delay due to a fire."
    with pytest.raises(StructuredOutputParsingError) as exc_info:
        parse_structured_llm_response(free_text, ResearchAnalysis)

    err = exc_info.value
    assert err.status_code == 422
    assert err.error_code == "ERR_422_UNSTRUCTURED_OUTPUT"


def test_parse_structured_llm_response_rejects_extra_fields() -> None:
    """Verify extra/injected fields trigger StructuredOutputParsingError (extra='forbid')."""
    injected_json = json.dumps(
        {
            "summary": "Valid summary",
            "incident_category": "FACILITY_FIRE",
            "confidence_score": 0.9,
            "key_findings": ["Finding"],
            "has_disruption_signal": True,
            "prompt_injection_flag": "bypass_system_prompt",  # Extra field forbidden
        }
    )
    with pytest.raises(StructuredOutputParsingError) as exc_info:
        parse_structured_llm_response(injected_json, ResearchAnalysis)

    assert exc_info.value.status_code == 422


def test_parse_structured_llm_response_rejects_malformed_json() -> None:
    """Verify malformed JSON raises StructuredOutputParsingError."""
    malformed = '{"summary": "Incomplete json'
    with pytest.raises(StructuredOutputParsingError):
        parse_structured_llm_response(malformed, ResearchAnalysis)


def test_contract_analysis_none_or_empty_decimal_fields() -> None:
    """Verify None or empty strings in Decimal fields coerce to None."""
    contract = ContractAnalysis(
        supplier_id="SUP-NANO-001",
        has_force_majeure=False,
        delay_penalty_percentage_per_day=None,
        liability_cap_usd=None,
    )
    assert contract.delay_penalty_percentage_per_day is None
    assert contract.liability_cap_usd is None


def test_parse_structured_llm_response_rejects_empty_string() -> None:
    """Verify empty or pure whitespace string raises StructuredOutputParsingError."""
    with pytest.raises(StructuredOutputParsingError, match="empty or whitespace output"):
        parse_structured_llm_response("   \n\t  ", ResearchAnalysis)


def test_parse_structured_llm_response_rejects_non_dict_json() -> None:
    """Verify JSON array or scalar raises StructuredOutputParsingError."""
    with pytest.raises(StructuredOutputParsingError, match="Expected JSON object"):
        parse_structured_llm_response(json.dumps(["item1", "item2"]), ResearchAnalysis)


# ------------------------------------------------------------------------------
# Test 8: JSON Schema Generation for Tool Calling
# ------------------------------------------------------------------------------


def test_json_schema_export_for_llm_tool_calling() -> None:
    """Verify models provide compliant JSON schemas for Bedrock / LiteLLM function calling."""
    schema = ResearchAnalysis.model_json_schema()
    assert schema["type"] == "object"
    assert "summary" in schema["properties"]
    assert "incident_category" in schema["properties"]
    assert schema["additionalProperties"] is False
