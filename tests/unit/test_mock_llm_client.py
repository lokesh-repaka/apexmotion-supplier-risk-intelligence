"""Unit tests for Mock LLM Client & Schema Fixture Engine (P8-5).

Verifies:
- Offline First Isolation (CLAUDE.md Sec 14 & Rule 8):
  * Unit tests execute with zero external network or Bedrock calls.
  * Activated by USE_MOCK_LLM=true (or use_mock=True).
- Fixture Schema Compliance (P8-3 models):
  * ResearchAnalysis, ContractAnalysis, RiskNarrative, RecommendationReport, IncidentCaseDossier.
  * Strict adherence to Pydantic v2 schemas with extra='forbid' and exact Decimal precision.
- Intelligent Schema Inference & Explicit Binding:
  * Returns target fixture JSON when response_model is provided or inferred from prompt.
- Response Queuing & Fixture Overrides:
  * Supports FIFO test response queues and dynamic fixture overrides for golden scenarios.
- LiteLLMGateway Integration:
  * LiteLLMGateway delegates mock structured completions to MockLLMClient seamlessly.
- Monitory & Governance Precision (BR-RULE-001):
  * Mock cost tracking reports Decimal('0.000000') with simulated token counts.
"""

from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import BaseModel
from src.core.hitl_tokens import SpendTier
from src.core.logging import bind_trace_id
from src.kafka.schemas.risk_alert import RiskLevel
from src.llm.gateway import LiteLLMGateway, LLMResponse
from src.llm.mock_client import (
    MockLLMClient,
    _resolve_schema_filename,
    get_fixture_model,
    get_mock_llm_client,
    load_fixture_json,
)
from src.llm.models import (
    ContractAnalysis,
    IncidentCaseDossier,
    RecommendationReport,
    ResearchAnalysis,
    RiskNarrative,
    parse_structured_llm_response,
)

# ------------------------------------------------------------------------------
# 1. Fixture Schema Loading & Parsing
# ------------------------------------------------------------------------------


def test_load_fixture_json_all_schemas() -> None:
    """Verify all canonical schema JSON fixtures load as non-empty valid JSON strings."""
    for schema_cls in (
        ResearchAnalysis,
        ContractAnalysis,
        RiskNarrative,
        RecommendationReport,
        IncidentCaseDossier,
    ):
        raw_json = load_fixture_json(schema_cls)
        assert isinstance(raw_json, str)
        assert len(raw_json) > 50

        # Validate string can be parsed by parse_structured_llm_response
        parsed = parse_structured_llm_response(raw_json, schema_cls)
        assert isinstance(parsed, schema_cls)


def test_get_fixture_model_all_schemas() -> None:
    """Verify get_fixture_model returns validated Pydantic models for each canonical schema."""
    research = get_fixture_model(ResearchAnalysis)
    assert isinstance(research, ResearchAnalysis)
    assert research.has_disruption_signal is True
    assert research.confidence_score >= 0.90

    contract = get_fixture_model(ContractAnalysis)
    assert isinstance(contract, ContractAnalysis)
    assert contract.supplier_id == "SUP-NC-001"
    assert isinstance(contract.delay_penalty_percentage_per_day, Decimal)
    assert isinstance(contract.liability_cap_usd, Decimal)

    narrative = get_fixture_model(RiskNarrative)
    assert isinstance(narrative, RiskNarrative)
    assert len(narrative.executive_summary) >= 20
    assert len(narrative.runway_and_exposure_commentary) >= 20

    recommendations = get_fixture_model(RecommendationReport)
    assert isinstance(recommendations, RecommendationReport)
    assert len(recommendations.scenarios) >= 1
    assert recommendations.recommended_scenario_id == recommendations.scenarios[0].scenario_id
    assert recommendations.requires_hitl is True
    assert recommendations.governing_spend_tier in (
        SpendTier.CATEGORY_MGR,
        SpendTier.PROC_DIRECTOR,
        SpendTier.DUAL_VP,
    )

    dossier = get_fixture_model(IncidentCaseDossier)
    assert isinstance(dossier, IncidentCaseDossier)
    assert dossier.case_id.startswith("CASE-")
    assert dossier.severity == RiskLevel.CRITICAL
    assert dossier.days_of_cover == Decimal("7.68")
    assert dossier.shortage_gap_days == Decimal("1.32")
    assert dossier.financial_exposure_usd == Decimal("2448105.00")


def test_load_fixture_by_string_identifier() -> None:
    """Verify fixtures can be loaded via string alias (case-insensitive)."""
    for alias in ("research_analysis", "ResearchAnalysis", "research"):
        raw_json = load_fixture_json(alias)
        assert "disruption" in raw_json or "Cleanroom" in raw_json

    for alias in ("contract_analysis", "ContractAnalysis", "contract"):
        raw_json = load_fixture_json(alias)
        assert "SUP-NC-001" in raw_json


def test_load_fixture_unknown_schema_raises_error() -> None:
    """Verify requesting an unsupported schema raises KeyError."""

    class CustomUnsupportedModel(BaseModel):
        foo: str

    with pytest.raises(KeyError) as exc_info:
        load_fixture_json(CustomUnsupportedModel)
    assert "Unsupported fixture schema" in str(exc_info.value)

    with pytest.raises(KeyError) as exc_info2:
        load_fixture_json("non_existent_schema_xyz")
    assert "Unsupported fixture schema" in str(exc_info2.value)


# ------------------------------------------------------------------------------
# 2. MockLLMClient Initialization & Basics
# ------------------------------------------------------------------------------


def test_mock_llm_client_initialization_defaults() -> None:
    """Verify MockLLMClient initializes with expected default configuration."""
    client = MockLLMClient()
    assert client.use_mock is True
    assert "claude" in client.model.lower() or "mock" in client.model.lower()
    assert client.call_count == 0
    assert client.total_tokens == 0
    assert client.total_cost_usd == Decimal("0.000000")


def test_mock_llm_client_custom_initialization() -> None:
    """Verify MockLLMClient accepts custom model names and simulated latency."""
    client = MockLLMClient(
        model="mock-bedrock-sonnet",
        simulated_latency_ms=10.0,
    )
    assert client.model == "mock-bedrock-sonnet"
    assert client.simulated_latency_ms == 10.0


# ------------------------------------------------------------------------------
# 3. Asynchronous & Synchronous Completions with Explicit response_model
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_client_acomplete_with_explicit_response_model() -> None:
    """Verify acomplete returns schema-compliant JSON when response_model is explicitly passed."""
    client = MockLLMClient()

    for schema_cls in (
        ResearchAnalysis,
        ContractAnalysis,
        RiskNarrative,
        RecommendationReport,
        IncidentCaseDossier,
    ):
        response = await client.acomplete(
            prompt="Perform deep analysis of supplier signal.",
            response_model=schema_cls,
        )
        assert isinstance(response, LLMResponse)
        assert response.cost_usd == Decimal("0.000000")
        assert response.prompt_tokens > 0
        assert response.completion_tokens > 0

        # Validate with parse_structured_llm_response
        parsed = parse_structured_llm_response(response.content, schema_cls)
        assert isinstance(parsed, schema_cls)


def test_mock_client_complete_sync_with_response_model() -> None:
    """Verify synchronous complete() returns structured LLMResponse."""
    client = MockLLMClient()
    response = client.complete(
        prompt="Analyze contract clauses",
        response_model=ContractAnalysis,
    )
    assert isinstance(response, LLMResponse)
    parsed = parse_structured_llm_response(response.content, ContractAnalysis)
    assert parsed.supplier_id == "SUP-NC-001"
    assert parsed.has_force_majeure is True


# ------------------------------------------------------------------------------
# 4. Prompt-Based Schema Inference
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_client_infers_schema_from_prompt_keywords() -> None:
    """Verify MockLLMClient detects target schema from prompt context without response_model."""
    client = MockLLMClient()

    # Research Agent prompt
    res_news = await client.acomplete(
        "Extract news disruption details and incident category for supplier SUP-01"
    )
    parsed_res = parse_structured_llm_response(res_news.content, ResearchAnalysis)
    assert isinstance(parsed_res, ResearchAnalysis)

    # Contract Agent prompt
    res_contract = await client.acomplete(
        "Extract governing contract clauses, payment terms and force majeure provisions"
    )
    parsed_contract = parse_structured_llm_response(res_contract.content, ContractAnalysis)
    assert isinstance(parsed_contract, ContractAnalysis)

    # Risk Agent prompt
    res_risk = await client.acomplete(
        "Synthesize executive summary and operational impact risk narrative explaining inventory runway"
    )
    parsed_risk = parse_structured_llm_response(res_risk.content, RiskNarrative)
    assert isinstance(parsed_risk, RiskNarrative)

    # Recommendation Agent prompt
    res_rec = await client.acomplete(
        "Generate ranked mitigation options and recommendation report for line halt avoidance"
    )
    parsed_rec = parse_structured_llm_response(res_rec.content, RecommendationReport)
    assert isinstance(parsed_rec, RecommendationReport)

    # Dossier prompt
    res_dossier = await client.acomplete(
        "Compile comprehensive incident case dossier integrating all agent findings"
    )
    parsed_dossier = parse_structured_llm_response(res_dossier.content, IncidentCaseDossier)
    assert isinstance(parsed_dossier, IncidentCaseDossier)


@pytest.mark.asyncio
async def test_mock_client_generic_fallback_when_no_schema_inferred() -> None:
    """Verify generic unstructured completion returned when prompt has no schema keywords."""
    client = MockLLMClient()
    response = await client.acomplete("Hello world, are you there?")
    assert isinstance(response, LLMResponse)
    assert "[MOCK]" in response.content or "mock completion" in response.content.lower()


# ------------------------------------------------------------------------------
# 5. Response Queuing & Fixture Overrides
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_client_response_queue_fifo() -> None:
    """Verify enqueued custom responses are returned in FIFO order before default fixtures."""
    client = MockLLMClient()

    custom_text_1 = '{"custom": "first_response"}'
    custom_text_2 = '{"custom": "second_response"}'
    client.enqueue_response(custom_text_1)
    client.enqueue_response(custom_text_2)

    res1 = await client.acomplete("Prompt 1")
    assert res1.content == custom_text_1

    res2 = await client.acomplete("Prompt 2")
    assert res2.content == custom_text_2

    # Queue empty -> returns default fixture or generic
    res3 = await client.acomplete("Prompt 3", response_model=ResearchAnalysis)
    assert "disruption" in res3.content


@pytest.mark.asyncio
async def test_mock_client_enqueue_multiple_responses_and_clear() -> None:
    """Verify enqueue_responses and clear_queue work as expected."""
    client = MockLLMClient()
    client.enqueue_responses(["Resp 1", "Resp 2", "Resp 3"])
    assert len(client._response_queue) == 3

    client.clear_queue()
    assert len(client._response_queue) == 0


def test_mock_client_set_fixture_override_and_reset() -> None:
    """Verify dynamic fixture overriding and resetting."""
    client = MockLLMClient()

    override_contract = ContractAnalysis(
        supplier_id="SUP-CUSTOM-99",
        contract_id="CNT-CUSTOM-99",
        payment_terms="Net 45",
        notice_period_days=21,
        delay_penalty_percentage_per_day=Decimal("0.05"),
        air_freight_surcharge_liability="APEXMOTION",
        has_force_majeure=False,
        force_majeure_clause=None,
        alternate_suppliers_authorized=["TSMC"],
        liability_cap_usd=Decimal("1000000.00"),
        citations=[],
    )

    client.set_fixture(ContractAnalysis, override_contract)
    resp = client.complete("Extract contract", response_model=ContractAnalysis)
    parsed = parse_structured_llm_response(resp.content, ContractAnalysis)
    assert parsed.supplier_id == "SUP-CUSTOM-99"
    assert parsed.payment_terms == "Net 45"

    # Reset
    client.reset_fixtures()
    resp_reset = client.complete("Extract contract", response_model=ContractAnalysis)
    parsed_reset = parse_structured_llm_response(resp_reset.content, ContractAnalysis)
    assert parsed_reset.supplier_id == "SUP-NC-001"


# ------------------------------------------------------------------------------
# 6. Observability, Metrics & Distributed Trace ID Propagation
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_client_metrics_and_trace_id() -> None:
    """Verify cumulative call count, token usage, and active trace_id propagation."""
    client = MockLLMClient()

    with bind_trace_id("test-trace-uuid-999"):
        resp = await client.acomplete(
            prompt="Extract news details",
            response_model=ResearchAnalysis,
        )
        assert resp.trace_id == "test-trace-uuid-999"
        assert client.call_count == 1
        assert client.total_tokens > 0

    client.reset_metrics()
    assert client.call_count == 0
    assert client.total_tokens == 0


def test_mock_client_singleton_getter() -> None:
    """Verify get_mock_llm_client returns a thread-safe singleton."""
    c1 = get_mock_llm_client()
    c2 = get_mock_llm_client()
    assert c1 is c2


# ------------------------------------------------------------------------------
# 7. Integration with LiteLLMGateway
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_litellm_gateway_uses_mock_client_for_structured_models() -> None:
    """Verify LiteLLMGateway(use_mock=True) leverages MockLLMClient when response_model passed."""
    gateway = LiteLLMGateway(use_mock=True)

    # Calling gateway with response_model returns valid fixture JSON
    resp = await gateway.acomplete(
        prompt="Synthesize news analysis",
        response_model=ResearchAnalysis,
    )
    assert isinstance(resp, LLMResponse)
    parsed = parse_structured_llm_response(resp.content, ResearchAnalysis)
    assert isinstance(parsed, ResearchAnalysis)
    assert parsed.incident_category.value == "FACILITY_FIRE"

    # Contract analysis via gateway
    resp_contract = await gateway.acomplete(
        prompt="Extract contract clauses",
        response_model=ContractAnalysis,
    )
    parsed_contract = parse_structured_llm_response(resp_contract.content, ContractAnalysis)
    assert parsed_contract.supplier_id == "SUP-NC-001"


@pytest.mark.asyncio
async def test_litellm_gateway_infers_schema_in_mock_mode_when_requested() -> None:
    """Verify LiteLLMGateway infers schema from prompt text in mock mode."""
    gateway = LiteLLMGateway(use_mock=True)

    resp = await gateway.acomplete(
        prompt="Please generate the RecommendationReport for the supplier disruption",
    )
    parsed = parse_structured_llm_response(resp.content, RecommendationReport)
    assert isinstance(parsed, RecommendationReport)
    assert parsed.alert_id.startswith("ALT-")


# ------------------------------------------------------------------------------
# 8. Boundary Conditions & 100% Statement/Branch Coverage
# ------------------------------------------------------------------------------


def test_resolve_schema_filename_fallback_and_missing_file() -> None:
    """Verify schema resolution fallback via lowercase classname and FileNotFoundError."""

    # Class whose __name__.lower() matches a key in FIXTURE_SCHEMAS but is not the class object itself
    class researchanalysis(BaseModel):
        pass

    filename = _resolve_schema_filename(researchanalysis)
    assert filename == "research_analysis.json"

    # Missing fixture file raises FileNotFoundError
    with pytest.raises(FileNotFoundError, match="Fixture file not found"):
        load_fixture_json(ResearchAnalysis, fixtures_dir=Path("/nonexistent_dir_apexmotion"))


def test_mock_client_enqueue_various_types() -> None:
    """Verify enqueue_response accepts BaseModel, LLMResponse, and arbitrary primitives."""
    client = MockLLMClient()

    # 1. BaseModel instance
    model_inst = get_fixture_model(ResearchAnalysis)
    client.enqueue_response(model_inst)
    resp1 = client.complete("any prompt")
    assert resp1.content == model_inst.model_dump_json(indent=2)

    # 2. LLMResponse instance
    llm_resp = LLMResponse(
        content="enqueued llm response", model="test-model", usage={"total_tokens": 42}
    )
    client.enqueue_response(llm_resp)
    resp2 = client.complete("any prompt")
    assert resp2.content == "enqueued llm response"

    # 3. Arbitrary primitive object (e.g. integer)
    client.enqueue_response(12345)
    resp3 = client.complete("any prompt")
    assert resp3.content == "12345"


def test_mock_client_set_fixture_various_types_and_lowercase_key() -> None:
    """Verify set_fixture handles dict, raw str, and custom objects, plus lowercase schema keys."""
    client = MockLLMClient()

    # Dict override
    client.set_fixture(ResearchAnalysis, {"summary": "dict override text"})
    resp_dict = client.complete("test", response_model=ResearchAnalysis)
    assert '"summary": "dict override text"' in resp_dict.content

    # Raw string override
    client.set_fixture(ResearchAnalysis, '{"summary": "raw str override"}')
    resp_str = client.complete("test", response_model=ResearchAnalysis)
    assert resp_str.content == '{"summary": "raw str override"}'

    # Arbitrary object override
    client.set_fixture(ResearchAnalysis, 99999)
    resp_obj = client.complete("test", response_model=ResearchAnalysis)
    assert resp_obj.content == "99999"

    # Lowercase string key override in _resolve_completion_content
    client.reset_fixtures()
    client.set_fixture("researchanalysis", '{"summary": "lowercase key override"}')
    resp_lower = client.complete("test", response_model=ResearchAnalysis)
    assert resp_lower.content == '{"summary": "lowercase key override"}'


def test_mock_client_extract_prompt_text_formats() -> None:
    """Verify _extract_prompt_text handles list of message dicts and non-str inputs."""
    client = MockLLMClient()

    # List of message dicts (including non-dict item to test comprehension filter)
    messages = [
        {"role": "system", "content": "system context"},
        "invalid_item_ignored",
        {"role": "user", "content": "user query"},
    ]
    resp = client.complete(messages)  # type: ignore[arg-type]
    assert "system context user query" in resp.content

    # Non-str, non-list input (e.g. integer)
    resp_int = client.complete(777)  # type: ignore[arg-type]
    assert "777" in resp_int.content


def test_mock_client_fixture_loading_exception_fallback() -> None:
    """Verify graceful fallback to generic unstructured response when fixture loading raises."""
    client = MockLLMClient()

    with patch("src.llm.mock_client.load_fixture_json", side_effect=RuntimeError("Disk failure")):
        resp = client.complete("synthesize news", response_model=ResearchAnalysis)
        assert "Disk failure" not in resp.content
        assert "[MOCK-" in resp.content
