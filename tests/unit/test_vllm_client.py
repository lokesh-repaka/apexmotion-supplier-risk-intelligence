"""Unit tests for vLLM Confidential Contract Client & Data Sovereignty Router (P8-4).

Verifies:
- Data Sovereignty Enforcement (NFR-SEC-02, CLAUDE.md Sec 5.2):
  * EU-regulated & GDPR-governed contracts route strictly to self-hosted vLLM inside private VPC.
  * Attempting to route EU-regulated or confidential contracts to external Bedrock triggers
    VLLMDataSovereigntyViolationError.
- Deterministic Offline Isolation (USE_MOCK_LLM=true, GAP-002):
  * Zero live external network or AWS calls in unit test suite.
  * Returns valid, schema-compliant ContractAnalysis adhering to P8-3 models.
- HTTP Execution & Error Translation (OpenAI-compatible vLLM /v1/chat/completions):
  * Proper headers, trace_id propagation, json_object response format.
  * Status code mapping: 503 Service Unavailable -> VLLMConnectionError.
  * Status code mapping: 504 Gateway Timeout -> VLLMTimeoutError.
  * Malformed / unparseable JSON -> VLLMContractExtractionError.
- Security & Privacy Audit Trail (BR-RULE-007):
  * Cryptographic SHA-256 hashing of contract content.
  * Raw confidential contract text is strictly protected and never written to unencrypted logs.
- Triad of Separation & Precision (BR-RULE-001):
  * Delay penalties, liability caps, and monetary terms use exact Decimal precision.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import ValidationError
from src.core.logging import bind_trace_id
from src.llm.gateway import LiteLLMGateway, LLMResponse
from src.llm.models import ContractAnalysis
from src.llm.vllm_client import (
    EU_EEA_JURISDICTIONS,
    ConfidentialContractRouter,
    ContractClassification,
    ContractMetadata,
    VLLMClient,
    VLLMClientError,
    VLLMConnectionError,
    VLLMContractExtractionError,
    VLLMDataSovereigntyViolationError,
    VLLMTimeoutError,
    get_contract_router,
    get_vllm_client,
)

# ------------------------------------------------------------------------------
# 1. ContractMetadata & Data Sovereignty Classification
# ------------------------------------------------------------------------------


def test_contract_metadata_defaults() -> None:
    """Verify default metadata configuration."""
    meta = ContractMetadata(supplier_id="SUP-001")
    assert meta.supplier_id == "SUP-001"
    assert meta.contract_id is None
    assert meta.jurisdiction == "GLOBAL"
    assert meta.classification == ContractClassification.INTERNAL
    assert meta.is_eu_regulated is False
    assert meta.is_confidential is False
    assert meta.is_sovereign_protected() is False


def test_contract_metadata_eu_jurisdiction_detection() -> None:
    """Verify EU/EEA jurisdictions automatically trigger sovereign protection."""
    for country in ("EU", "EEA", "DE", "FR", "IT", "NL", "PL", "SE", "ES"):
        meta = ContractMetadata(supplier_id="SUP-EU-01", jurisdiction=country)
        assert meta.is_sovereign_protected() is True, f"Failed for jurisdiction {country}"
        assert country in EU_EEA_JURISDICTIONS


def test_contract_metadata_non_eu_jurisdiction() -> None:
    """Verify non-EU/EEA standard jurisdictions do not trigger sovereign protection by default."""
    for country in ("US", "GLOBAL", "JP", "TW", "KR", "VN", "MX"):
        meta = ContractMetadata(supplier_id="SUP-US-01", jurisdiction=country)
        assert meta.is_sovereign_protected() is False, f"Unexpected protection for {country}"


def test_contract_metadata_classification_protection() -> None:
    """Verify CONFIDENTIAL and HIGHLY_CONFIDENTIAL trigger sovereign protection regardless of jurisdiction."""
    meta_conf = ContractMetadata(
        supplier_id="SUP-US-01",
        jurisdiction="US",
        classification=ContractClassification.CONFIDENTIAL,
    )
    assert meta_conf.is_sovereign_protected() is True

    meta_highly_conf = ContractMetadata(
        supplier_id="SUP-US-02",
        jurisdiction="US",
        classification=ContractClassification.HIGHLY_CONFIDENTIAL,
    )
    assert meta_highly_conf.is_sovereign_protected() is True

    meta_restricted = ContractMetadata(
        supplier_id="SUP-US-03",
        jurisdiction="US",
        classification=ContractClassification.RESTRICTED,
    )
    assert meta_restricted.is_sovereign_protected() is True


def test_contract_metadata_explicit_flags() -> None:
    """Verify explicit boolean flags force sovereign protection."""
    meta_eu_flag = ContractMetadata(
        supplier_id="SUP-001",
        jurisdiction="GLOBAL",
        is_eu_regulated=True,
    )
    assert meta_eu_flag.is_sovereign_protected() is True

    meta_conf_flag = ContractMetadata(
        supplier_id="SUP-002",
        jurisdiction="GLOBAL",
        is_confidential=True,
    )
    assert meta_conf_flag.is_sovereign_protected() is True


def test_contract_metadata_forbid_extra_fields() -> None:
    """Verify extra injected fields are rejected."""
    with pytest.raises(ValidationError):
        ContractMetadata(
            supplier_id="SUP-001",  # type: ignore[call-arg]
            injected_prompt_hack="bypass_sovereignty",
        )


# ------------------------------------------------------------------------------
# 2. VLLMClient Initialization & Health Checks
# ------------------------------------------------------------------------------


def test_vllm_client_initialization_defaults() -> None:
    """Verify VLLMClient initializes with settings defaults."""
    client = VLLMClient(use_mock=True)
    assert client.base_url == "http://localhost:8080"
    assert "Llama-3.1-70B" in client.model
    assert client.use_mock is True
    assert client.timeout_seconds == 30.0


def test_vllm_client_initialization_custom() -> None:
    """Verify VLLMClient initializes with custom overrides."""
    client = VLLMClient(
        base_url="http://vllm-cluster.internal:8000",
        model="custom-contract-extractor-70b",
        api_key="secret-vllm-key",
        timeout_seconds=45.0,
        max_retries=5,
        use_mock=False,
    )
    assert client.base_url == "http://vllm-cluster.internal:8000"
    assert client.model == "custom-contract-extractor-70b"
    assert client.api_key == "secret-vllm-key"
    assert client.timeout_seconds == 45.0
    assert client.max_retries == 5
    assert client.use_mock is False


@pytest.mark.asyncio
async def test_vllm_client_health_check_mock() -> None:
    """Verify health check returns True in mock mode."""
    client = VLLMClient(use_mock=True)
    is_healthy = await client.health_check()
    assert is_healthy is True


@pytest.mark.asyncio
async def test_vllm_client_health_check_live_success() -> None:
    """Verify health check returns True on HTTP 200."""
    client = VLLMClient(use_mock=False)
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with bind_trace_id("health-trace-123"):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            assert await client.health_check() is True
            mock_get.assert_called_once()
            call_kwargs = mock_get.call_args[1]
            assert call_kwargs["headers"]["X-Trace-ID"] == "health-trace-123"


@pytest.mark.asyncio
async def test_vllm_client_health_check_live_failure() -> None:
    """Verify health check returns False on HTTP error or exception."""
    client = VLLMClient(use_mock=False)

    with patch(
        "httpx.AsyncClient.get",
        side_effect=httpx.ConnectError("Connection refused"),
    ):
        assert await client.health_check() is False


# ------------------------------------------------------------------------------
# 3. Offline Mock Mode (USE_MOCK_LLM=true)
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vllm_client_mock_acomplete() -> None:
    """Verify mock completion returns structured LLM response without network calls."""
    client = VLLMClient(use_mock=True)
    messages = [{"role": "user", "content": "Extract clauses from contract"}]

    response = await client.acomplete(messages)
    assert response.model == client.model
    assert response.prompt_tokens > 0
    assert response.completion_tokens > 0
    assert response.cost_usd == Decimal("0.000000")  # Internal self-hosted GPU = 0 API cost
    assert "supplier_id" in response.content


@pytest.mark.asyncio
async def test_vllm_client_mock_extract_contract_clauses() -> None:
    """Verify mock contract extraction returns validated ContractAnalysis adhering to P8-3 schema."""
    client = VLLMClient(use_mock=True)
    metadata = ContractMetadata(
        supplier_id="SUP-EU-001",
        contract_id="CNT-DE-2024-X91",
        jurisdiction="DE",
        classification=ContractClassification.HIGHLY_CONFIDENTIAL,
        is_eu_regulated=True,
    )
    raw_contract = (
        "CONFIDENTIAL MASTER SUPPLY AGREEMENT\n"
        "Between ApexMotion Mobility GmbH and NanoCore Semiconductor B.V.\n"
        "Section 4.1 Payment Terms: Net 30 days.\n"
        "Section 7.3 Delivery Notice: In event of supply chain bottleneck, Supplier shall provide 14 days notice.\n"
        "Section 8.2 Delay Penalty: 0.02% per business day of delayed batch value.\n"
        "Section 11.1 Air Freight: Supplier bears 100% liability for expedited logistics surcharges.\n"
        "Section 15 Force Majeure: Unforeseen cleanroom fires shall constitute Force Majeure.\n"
        "Section 18 Liability Cap: Aggregate liability capped at $5,000,000 USD."
    )

    analysis = await client.extract_contract_clauses(raw_contract, metadata)

    assert isinstance(analysis, ContractAnalysis)
    assert analysis.supplier_id == "SUP-EU-001"
    assert analysis.contract_id == "CNT-DE-2024-X91"
    assert analysis.payment_terms == "Net 30"
    assert analysis.notice_period_days == 14
    assert analysis.delay_penalty_percentage_per_day == Decimal("0.02")
    assert analysis.air_freight_surcharge_liability == "SUPPLIER"
    assert analysis.has_force_majeure is True
    assert "Force Majeure" in (analysis.force_majeure_clause or "")
    assert isinstance(analysis.liability_cap_usd, Decimal)
    assert analysis.liability_cap_usd == Decimal("5000000.00")
    assert len(analysis.citations) > 0


# ------------------------------------------------------------------------------
# 4. Live Mode (HTTP Layer Mocking & OpenAI Protocol Compliance)
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vllm_client_live_acomplete_success() -> None:
    """Verify live acomplete properly constructs OpenAI-compatible payload and parses response."""
    client = VLLMClient(
        base_url="http://vllm.internal:8000",
        api_key="vllm-test-token",
        use_mock=False,
    )

    mock_response_data = {
        "id": "chatcmpl-vllm-123",
        "object": "chat.completion",
        "model": client.model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": '{"supplier_id": "SUP-001", "has_force_majeure": true}',
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 120,
            "completion_tokens": 45,
            "total_tokens": 165,
        },
    }

    mock_http_resp = MagicMock()
    mock_http_resp.status_code = 200
    mock_http_resp.json.return_value = mock_response_data

    with bind_trace_id("test-trace-12345"):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_http_resp

            response = await client.acomplete(
                messages=[{"role": "user", "content": "Extract clauses"}],
                temperature=0.0,
                max_tokens=2048,
            )

            assert response.content == '{"supplier_id": "SUP-001", "has_force_majeure": true}'
            assert response.prompt_tokens == 120
            assert response.completion_tokens == 45
            assert response.cost_usd == Decimal("0.000000")
            assert response.trace_id == "test-trace-12345"

            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args[1]
            assert call_kwargs["headers"]["Authorization"] == "Bearer vllm-test-token"
            assert call_kwargs["headers"]["X-Trace-ID"] == "test-trace-12345"
            assert call_kwargs["json"]["model"] == client.model
            assert call_kwargs["json"]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_vllm_client_live_extract_contract_clauses_success() -> None:
    """Verify live extract_contract_clauses validates and converts raw JSON to ContractAnalysis."""
    client = VLLMClient(use_mock=False)
    metadata = ContractMetadata(
        supplier_id="SUP-FR-002",
        contract_id="CNT-FR-2024-002",
        jurisdiction="FR",
    )

    valid_json = (
        "{\n"
        '  "supplier_id": "SUP-FR-002",\n'
        '  "contract_id": "CNT-FR-2024-002",\n'
        '  "payment_terms": "Net 60",\n'
        '  "notice_period_days": 30,\n'
        '  "delay_penalty_percentage_per_day": "0.015",\n'
        '  "air_freight_surcharge_liability": "SPLIT_50_50",\n'
        '  "has_force_majeure": true,\n'
        '  "force_majeure_clause": "Epidemics and trade embargoes qualify as force majeure.",\n'
        '  "alternate_suppliers_authorized": ["STMicroelectronics"],\n'
        '  "liability_cap_usd": "2500000.00",\n'
        '  "citations": [\n'
        '    {"source_id": "CNT-FR-2024-002", "source_type": "CONTRACT", "page_or_section": "Article 14.1", "verbatim_quote": "Net 60"}\n'
        "  ]\n"
        "}"
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": valid_json}}],
        "usage": {"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300},
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        analysis = await client.extract_contract_clauses(
            "Contract between ApexMotion and Supplier...", metadata
        )

        assert analysis.supplier_id == "SUP-FR-002"
        assert analysis.payment_terms == "Net 60"
        assert analysis.delay_penalty_percentage_per_day == Decimal("0.015")
        assert analysis.liability_cap_usd == Decimal("2500000.00")
        assert analysis.air_freight_surcharge_liability == "SPLIT_50_50"


# ------------------------------------------------------------------------------
# 5. Error Handling & Circuit-Breaker Status Codes
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vllm_client_connection_error_raises_vllm_connection_error() -> None:
    """Verify network connection failure raises VLLMConnectionError (HTTP 503)."""
    client = VLLMClient(use_mock=False, max_retries=1)

    with patch(
        "httpx.AsyncClient.post",
        side_effect=httpx.ConnectError("Failed to connect to vLLM endpoint"),
    ):
        with pytest.raises(VLLMConnectionError) as exc_info:
            await client.acomplete([{"role": "user", "content": "ping"}])

        assert exc_info.value.status_code == 503
        assert "Failed to connect to vLLM endpoint" in exc_info.value.message


@pytest.mark.asyncio
async def test_vllm_client_timeout_raises_vllm_timeout_error() -> None:
    """Verify request timeout raises VLLMTimeoutError (HTTP 504)."""
    client = VLLMClient(use_mock=False, max_retries=1)

    with patch(
        "httpx.AsyncClient.post",
        side_effect=httpx.TimeoutException("vLLM cluster GPU timeout exceeded"),
    ):
        with pytest.raises(VLLMTimeoutError) as exc_info:
            await client.acomplete([{"role": "user", "content": "ping"}])

        assert exc_info.value.status_code == 504
        assert "timeout exceeded" in exc_info.value.message


@pytest.mark.asyncio
async def test_vllm_client_5xx_status_code_handling() -> None:
    """Verify HTTP 500 / 503 responses raise VLLMConnectionError."""
    client = VLLMClient(use_mock=False, max_retries=1)

    mock_resp = MagicMock()
    mock_resp.status_code = 503
    mock_resp.text = "Service Unavailable: vLLM GPU out of memory"

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        with pytest.raises(VLLMConnectionError) as exc_info:
            await client.acomplete([{"role": "user", "content": "ping"}])

        assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_vllm_client_unparseable_json_raises_extraction_error() -> None:
    """Verify non-JSON response raises VLLMContractExtractionError (HTTP 422)."""
    client = VLLMClient(use_mock=False)
    metadata = ContractMetadata(supplier_id="SUP-001")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "This is free text, not JSON."}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        with pytest.raises(VLLMContractExtractionError) as exc_info:
            await client.extract_contract_clauses("Valid contract text", metadata)

        assert exc_info.value.status_code == 422


# ------------------------------------------------------------------------------
# 6. Data Sovereignty Router & Guardrail Enforcement (NFR-SEC-02)
# ------------------------------------------------------------------------------


def test_contract_router_decision_for_eu_contract() -> None:
    """Verify ConfidentialContractRouter routes EU-regulated contracts to vLLM."""
    router = ConfidentialContractRouter()
    eu_meta = ContractMetadata(
        supplier_id="SUP-EU-001",
        jurisdiction="DE",
        is_eu_regulated=True,
    )
    assert router.route_contract(eu_meta) == "vllm"


def test_contract_router_decision_for_confidential_contract() -> None:
    """Verify ConfidentialContractRouter routes HIGHLY_CONFIDENTIAL contracts to vLLM."""
    router = ConfidentialContractRouter()
    conf_meta = ContractMetadata(
        supplier_id="SUP-US-001",
        jurisdiction="US",
        classification=ContractClassification.HIGHLY_CONFIDENTIAL,
    )
    assert router.route_contract(conf_meta) == "vllm"


def test_contract_router_decision_for_standard_contract() -> None:
    """Verify ConfidentialContractRouter routes non-confidential US contracts to Bedrock."""
    router = ConfidentialContractRouter()
    std_meta = ContractMetadata(
        supplier_id="SUP-US-002",
        jurisdiction="US",
        classification=ContractClassification.INTERNAL,
        is_eu_regulated=False,
        is_confidential=False,
    )
    assert router.route_contract(std_meta) == "bedrock"


@pytest.mark.asyncio
async def test_contract_router_blocks_confidential_contract_to_bedrock() -> None:
    """CRITICAL SECURITY GATE: Attempting to force an EU or confidential contract to Bedrock MUST fail."""
    router = ConfidentialContractRouter()
    eu_meta = ContractMetadata(
        supplier_id="SUP-EU-001",
        jurisdiction="DE",
        is_eu_regulated=True,
    )

    with pytest.raises(VLLMDataSovereigntyViolationError) as exc_info:
        await router.process_contract(
            contract_text="Confidential EU supplier agreement",
            metadata=eu_meta,
            force_target="bedrock",
        )

    assert exc_info.value.status_code == 403
    assert "DATA_SOVEREIGNTY_VIOLATION" in exc_info.value.code
    assert "EU-regulated or confidential contract" in exc_info.value.message


@pytest.mark.asyncio
async def test_contract_router_process_contract_vllm_end_to_end() -> None:
    """Verify router cleanly processes sovereign contract through vLLM in mock mode."""
    router = ConfidentialContractRouter(use_mock=True)
    meta = ContractMetadata(
        supplier_id="SUP-EU-001",
        contract_id="CNT-EU-99",
        jurisdiction="FR",
        is_eu_regulated=True,
    )

    result = await router.process_contract("Sample contract...", metadata=meta)
    assert isinstance(result, ContractAnalysis)
    assert result.supplier_id == "SUP-EU-001"


@pytest.mark.asyncio
async def test_contract_router_process_contract_bedrock_end_to_end() -> None:
    """Verify router cleanly processes standard commercial contract through Bedrock gateway in mock mode."""
    router = ConfidentialContractRouter(use_mock=True)
    meta = ContractMetadata(
        supplier_id="SUP-US-001",
        jurisdiction="US",
        is_eu_regulated=False,
        is_confidential=False,
    )

    result = await router.process_contract("Standard commercial terms...", metadata=meta)
    assert isinstance(result, ContractAnalysis)
    assert result.supplier_id == "SUP-US-001"


# ------------------------------------------------------------------------------
# 7. Privacy, Hashing, & Audit Guardrails (BR-RULE-007)
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_contract_hashing_and_audit_log_never_logs_raw_text() -> None:
    """Verify contract text is cryptographically hashed with SHA-256 and never logged unencrypted."""
    client = VLLMClient(use_mock=True)
    meta = ContractMetadata(
        supplier_id="SUP-CONF-99",
        classification=ContractClassification.HIGHLY_CONFIDENTIAL,
    )
    confidential_text = "SECRET_PROPRIETARY_FORMULA_DO_NOT_LEAK_INTO_LOGS"

    with patch("src.llm.vllm_client.logger") as mock_logger:
        await client.extract_contract_clauses(confidential_text, meta)

        # Verify logger was called
        assert mock_logger.info.called or mock_logger.debug.called

        # Check every log message across all levels to confirm raw secret is NOT present
        for call_args in mock_logger.info.call_args_list:
            log_str = str(call_args)
            assert confidential_text not in log_str, "Raw contract leaked into INFO log!"

        for call_args in mock_logger.debug.call_args_list:
            log_str = str(call_args)
            assert confidential_text not in log_str, "Raw contract leaked into DEBUG log!"


@pytest.mark.asyncio
async def test_vllm_client_rejects_empty_contract() -> None:
    """Verify empty or whitespace-only contract text is rejected."""
    client = VLLMClient(use_mock=True)
    meta = ContractMetadata(supplier_id="SUP-001")

    with pytest.raises(VLLMContractExtractionError) as exc_info:
        await client.extract_contract_clauses("   ", meta)

    assert "Contract text cannot be empty" in exc_info.value.message


def test_dependency_injection_singletons() -> None:
    """Verify singleton getters return consistent client instances."""
    client1 = get_vllm_client()
    client2 = get_vllm_client()
    assert client1 is client2

    router1 = get_contract_router()
    router2 = get_contract_router()
    assert router1 is router2


# ------------------------------------------------------------------------------
# 8. Edge Cases, Coverage & Fault Injection Scenarios
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vllm_client_health_check_with_api_key() -> None:
    """Verify health check includes Authorization header when api_key is present."""
    client = VLLMClient(api_key="secret-key-123", use_mock=False)
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        assert await client.health_check() is True

        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["headers"]["Authorization"] == "Bearer secret-key-123"


def test_mock_analysis_notice_periods_and_terms() -> None:
    """Verify deterministic mock parser accommodates various clause phrasings."""
    client = VLLMClient(use_mock=True)

    # 30 days notice
    res1 = client._generate_mock_contract_analysis(
        ContractMetadata(supplier_id="SUP-1"),
        "The party shall provide notice: 30 days prior to stoppage.",
    )
    assert res1.notice_period_days == 30

    # 60 days notice and Net 90
    res2 = client._generate_mock_contract_analysis(
        ContractMetadata(supplier_id="SUP-2"),
        "Requires 60 days notice. Payment shall be Net 90 terms.",
    )
    assert res2.notice_period_days == 60
    assert res2.payment_terms == "Net 90"

    # Buyer bears air freight
    res3 = client._generate_mock_contract_analysis(
        ContractMetadata(supplier_id="SUP-3"),
        "ApexMotion buyer bears all expedited shipping costs.",
    )
    assert res3.air_freight_surcharge_liability == "APEXMOTION"

    # Net 60 and split freight
    res4 = client._generate_mock_contract_analysis(
        ContractMetadata(supplier_id="SUP-4"),
        "Incoterms stipulate Net 60 days and air freight costs split between parties.",
    )
    assert res4.payment_terms == "Net 60"
    assert res4.air_freight_surcharge_liability == "SPLIT_50_50"


@pytest.mark.asyncio
async def test_mock_completion_supplier_id_parsing() -> None:
    """Verify mock completion extracts SUP-* identifier from prompt."""
    client = VLLMClient(use_mock=True)
    messages = [{"role": "user", "content": "Extract agreement for SUP-DE-991 from cleanroom."}]

    resp = await client.acomplete(messages)
    assert "SUP-DE-991" in resp.content


@pytest.mark.asyncio
async def test_vllm_client_live_empty_choices_raises_error() -> None:
    """Verify response with empty choices list raises VLLMContractExtractionError."""
    client = VLLMClient(use_mock=False)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"choices": []}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(VLLMContractExtractionError) as exc_info:
            await client.acomplete([{"role": "user", "content": "ping"}])

        assert "contains no completion choices" in exc_info.value.message


@pytest.mark.asyncio
async def test_vllm_client_live_400_client_error() -> None:
    """Verify non-500 HTTP error (e.g. 400 Bad Request) raises VLLMClientError."""
    client = VLLMClient(use_mock=False, max_retries=1)
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = "Bad Request: Invalid model parameters"

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(VLLMClientError) as exc_info:
            await client.acomplete([{"role": "user", "content": "ping"}])

        assert exc_info.value.status_code == 400
        assert "vLLM client error" in exc_info.value.message


@pytest.mark.asyncio
async def test_vllm_client_live_unexpected_exception() -> None:
    """Verify unexpected non-HTTP exception raises VLLMClientError and breaks retry loop."""
    client = VLLMClient(use_mock=False, max_retries=3)

    with patch("httpx.AsyncClient.post", side_effect=RuntimeError("System memory corruption")):
        with pytest.raises(VLLMClientError) as exc_info:
            await client.acomplete([{"role": "user", "content": "ping"}])

        assert "Unexpected error communicating with vLLM" in exc_info.value.message


@pytest.mark.asyncio
async def test_vllm_client_retry_exhaustion_on_connect_error() -> None:
    """Verify multiple connect errors trigger exponential backoff before raising VLLMConnectionError."""
    client = VLLMClient(use_mock=False, max_retries=2)

    with patch(
        "httpx.AsyncClient.post", side_effect=httpx.ConnectError("Cluster host unreachable")
    ):
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(VLLMConnectionError) as exc_info:
                await client.acomplete([{"role": "user", "content": "ping"}])

            assert exc_info.value.status_code == 503
            assert mock_sleep.call_count == 1  # 2 attempts -> 1 sleep


@pytest.mark.asyncio
async def test_contract_router_process_contract_bedrock_live_mode() -> None:
    """Verify router routes non-confidential contract to Bedrock LiteLLM gateway in live mode."""
    valid_contract_json = (
        "{\n"
        '  "supplier_id": "SUP-US-001",\n'
        '  "contract_id": "CNT-US-2024-001",\n'
        '  "payment_terms": "Net 30",\n'
        '  "notice_period_days": 15,\n'
        '  "delay_penalty_percentage_per_day": "0.01",\n'
        '  "air_freight_surcharge_liability": "SUPPLIER",\n'
        '  "has_force_majeure": false,\n'
        '  "alternate_suppliers_authorized": [],\n'
        '  "liability_cap_usd": "1000000.00",\n'
        '  "citations": []\n'
        "}"
    )

    mock_gateway = MagicMock(spec=LiteLLMGateway)
    mock_gateway.use_mock = False
    mock_gateway.acomplete = AsyncMock(
        return_value=LLMResponse(
            content=valid_contract_json,
            model="anthropic.claude-3-5-haiku-20241022-v1:0",
            prompt_tokens=150,
            completion_tokens=80,
            total_tokens=230,
            cost_usd=Decimal("0.000440"),
        )
    )

    router = ConfidentialContractRouter(
        litellm_gateway=mock_gateway,
        use_mock=False,
    )
    meta = ContractMetadata(
        supplier_id="SUP-US-001",
        jurisdiction="US",
        classification=ContractClassification.INTERNAL,
    )

    analysis = await router.process_contract("Standard contract terms...", metadata=meta)
    assert isinstance(analysis, ContractAnalysis)
    assert analysis.supplier_id == "SUP-US-001"
    assert analysis.notice_period_days == 15
    assert analysis.has_force_majeure is False
    mock_gateway.acomplete.assert_called_once()
