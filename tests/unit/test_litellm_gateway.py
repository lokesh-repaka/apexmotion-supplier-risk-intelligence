"""Unit tests for LiteLLM Gateway Client (P8-1).

Verifies:
- Task routing: SYNTHESIS -> Bedrock Claude 3.5 Sonnet, TRIAGE/EXTRACTION -> Bedrock Claude 3.5 Haiku.
- Automated fallback on primary model failure (429 RateLimit, 503 ServiceUnavailable, 504 Timeout).
- Rate limit handling and error standardisation (HTTP 429 RATE_LIMITED).
- Token usage metering and strict Decimal monetary cost tracking (BR-RULE-001).
- Offline test isolation via mock mode (USE_MOCK_LLM=true) with zero external I/O.
- In-memory and Redis prompt caching support.
- Distributed trace_id propagation.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from litellm.exceptions import (
    APIConnectionError,
    ContextWindowExceededError,
    RateLimitError,
    Timeout,
)
from src.core.logging import bind_trace_id
from src.llm.gateway import (
    CostReport,
    LiteLLMGateway,
    LLMContextWindowExceededError,
    LLMGatewayError,
    LLMRateLimitError,
    LLMResponse,
    LLMServiceUnavailableError,
    LLMTimeoutError,
    TaskType,
    calculate_token_cost,
    get_litellm_gateway,
)

# ------------------------------------------------------------------------------
# 1. Initialization & Model Routing
# ------------------------------------------------------------------------------


def test_gateway_initialization_and_defaults() -> None:
    """Verify gateway initializes with canonical model settings and zero cost baseline."""
    gateway = LiteLLMGateway(use_mock=True)

    assert "claude-3-5-sonnet" in gateway.primary_model
    assert "claude-3-5-haiku" in gateway.fallback_model
    assert gateway.use_mock is True

    report = gateway.get_cost_report()
    assert isinstance(report, CostReport)
    assert report.total_tokens == 0
    assert report.total_cost_usd == Decimal("0.000000")
    assert report.call_count == 0


def test_route_model_by_task_type() -> None:
    """Verify task complexity routing: Sonnet for Synthesis, Haiku for Triage/Extraction."""
    gateway = LiteLLMGateway(use_mock=True)

    # Synthesis -> Claude 3.5 Sonnet
    assert gateway.route_model(TaskType.SYNTHESIS) == gateway.primary_model
    assert gateway.route_model("synthesis") == gateway.primary_model

    # Triage -> Claude 3.5 Haiku
    assert gateway.route_model(TaskType.TRIAGE) == gateway.fallback_model
    assert gateway.route_model("triage") == gateway.fallback_model

    # Extraction -> Claude 3.5 Haiku
    assert gateway.route_model(TaskType.EXTRACTION) == gateway.fallback_model
    assert gateway.route_model("extraction") == gateway.fallback_model

    # General / Unknown -> Defaults to primary model
    assert gateway.route_model(TaskType.GENERAL) == gateway.primary_model
    assert gateway.route_model("unknown_task") == gateway.primary_model


# ------------------------------------------------------------------------------
# 2. Mock Mode Execution (Offline Isolation)
# ------------------------------------------------------------------------------


def test_mock_llm_completion_sync() -> None:
    """Verify synchronous completion executes offline without external network calls."""
    gateway = LiteLLMGateway(use_mock=True)
    prompt = "Synthesize supply chain disruption impact for NanoCore Semiconductor."

    response = gateway.complete(prompt=prompt, task_type=TaskType.SYNTHESIS)

    assert isinstance(response, LLMResponse)
    assert len(response.content) > 0
    assert response.model == gateway.primary_model
    assert response.prompt_tokens > 0
    assert response.completion_tokens > 0
    assert response.total_tokens == response.prompt_tokens + response.completion_tokens
    assert response.cost_usd > Decimal("0.000000")
    assert response.is_fallback is False
    assert response.is_cached is False


@pytest.mark.asyncio
async def test_mock_llm_completion_async() -> None:
    """Verify asynchronous completion executes offline without external network calls."""
    gateway = LiteLLMGateway(use_mock=True)
    messages = [{"role": "user", "content": "Extract suppliers and SKUs from contract."}]

    response = await gateway.acomplete(prompt=messages, task_type=TaskType.EXTRACTION)

    assert isinstance(response, LLMResponse)
    assert response.model == gateway.fallback_model
    assert response.total_tokens > 0
    assert isinstance(response.cost_usd, Decimal)
    assert response.is_fallback is False


# ------------------------------------------------------------------------------
# 3. Monetary Cost Calculation & Precision (BR-RULE-001)
# ------------------------------------------------------------------------------


def test_calculate_token_cost_precision() -> None:
    """Verify strict Decimal precision in LLM token cost computation."""
    # Sonnet: $3.00/1M input, $15.00/1M output
    # 1,000 prompt tokens = $0.003; 500 completion tokens = $0.0075 -> Total = $0.010500
    sonnet_cost = calculate_token_cost(
        model="anthropic.claude-3-5-sonnet-20241022-v2:0",
        prompt_tokens=1000,
        completion_tokens=500,
    )
    assert isinstance(sonnet_cost, Decimal)
    assert sonnet_cost == Decimal("0.010500")

    # Haiku: $0.80/1M input, $4.00/1M output
    # 10,000 prompt tokens = $0.008; 2,000 completion tokens = $0.008 -> Total = $0.016000
    haiku_cost = calculate_token_cost(
        model="anthropic.claude-3-5-haiku-20241022-v1:0",
        prompt_tokens=10000,
        completion_tokens=2000,
    )
    assert isinstance(haiku_cost, Decimal)
    assert haiku_cost == Decimal("0.016000")


def test_cumulative_cost_tracking_and_reset() -> None:
    """Verify gateway maintains running cumulative token and cost ledger across calls."""
    gateway = LiteLLMGateway(use_mock=True)
    gateway.reset_cost_tracking()

    gateway.complete("First prompt", task_type=TaskType.SYNTHESIS)
    gateway.complete("Second prompt", task_type=TaskType.EXTRACTION)

    report = gateway.get_cost_report()
    assert report.call_count == 2
    assert report.total_tokens > 0
    assert report.total_cost_usd > Decimal("0.000000")
    assert gateway.primary_model in report.model_breakdown
    assert gateway.fallback_model in report.model_breakdown

    # Test reset
    gateway.reset_cost_tracking()
    reset_report = gateway.get_cost_report()
    assert reset_report.call_count == 0
    assert reset_report.total_cost_usd == Decimal("0.000000")


# ------------------------------------------------------------------------------
# 4. Fallback Routing Mechanics
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_routing_on_rate_limit_429() -> None:
    """Verify automatic fallback to Haiku when primary model Sonnet returns 429 RateLimit."""
    gateway = LiteLLMGateway(use_mock=False)

    mock_success_response = MagicMock()
    mock_success_response.choices = [
        MagicMock(message=MagicMock(content="Fallback extraction succeeded."))
    ]
    mock_success_response.usage = MagicMock(
        prompt_tokens=120, completion_tokens=40, total_tokens=160
    )
    mock_success_response.model = gateway.fallback_model

    async def side_effect(*_args: object, **kwargs: object) -> object:
        model = kwargs.get("model", "")
        if gateway.primary_model in str(model):
            raise RateLimitError(
                message="Bedrock rate limit exceeded",
                model=gateway.primary_model,
                llm_provider="bedrock",
            )
        return mock_success_response

    with patch("litellm.acompletion", side_effect=side_effect):
        response = await gateway.acomplete(
            prompt="Analyze high-volume disruption",
            task_type=TaskType.SYNTHESIS,
        )

    assert response.is_fallback is True
    assert response.model == gateway.fallback_model
    assert "Fallback extraction succeeded" in response.content

    report = gateway.get_cost_report()
    assert report.fallback_count == 1


@pytest.mark.asyncio
async def test_fallback_routing_on_service_unavailable_503() -> None:
    """Verify automatic fallback to Haiku when primary model returns 503 ServiceUnavailable."""
    gateway = LiteLLMGateway(use_mock=False)

    mock_success_response = MagicMock()
    mock_success_response.choices = [
        MagicMock(message=MagicMock(content="Fallback synthesis recovered."))
    ]
    mock_success_response.usage = MagicMock(
        prompt_tokens=100, completion_tokens=30, total_tokens=130
    )
    mock_success_response.model = gateway.fallback_model

    async def side_effect(*_args: object, **kwargs: object) -> object:
        model = kwargs.get("model", "")
        if gateway.primary_model in str(model):
            raise APIConnectionError(
                message="Bedrock endpoint unreachable",
                llm_provider="bedrock",
                model=gateway.primary_model,
            )
        return mock_success_response

    with patch("litellm.acompletion", side_effect=side_effect):
        response = await gateway.acomplete(
            prompt="Investigate Taiwanese fab fire",
            task_type=TaskType.SYNTHESIS,
        )

    assert response.is_fallback is True
    assert response.model == gateway.fallback_model
    assert "Fallback synthesis recovered" in response.content


# ------------------------------------------------------------------------------
# 5. Error Standardisation & Exception Trapping
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_error_standardisation_when_all_models_rate_limited() -> None:
    """Verify LLMRateLimitError (HTTP 429) raised when both primary and fallback fail with 429."""
    gateway = LiteLLMGateway(use_mock=False)

    with patch(
        "litellm.acompletion",
        side_effect=RateLimitError(
            message="All Bedrock models throttled",
            model="bedrock",
            llm_provider="bedrock",
        ),
    ):
        with pytest.raises(LLMRateLimitError) as exc_info:
            await gateway.acomplete("Critical prompt", task_type=TaskType.SYNTHESIS)

    assert exc_info.value.status_code == 429
    assert exc_info.value.code == "RATE_LIMITED"
    assert "rate limit" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_error_standardisation_when_all_models_timeout() -> None:
    """Verify LLMTimeoutError (HTTP 504) raised when both primary and fallback timeout."""
    gateway = LiteLLMGateway(use_mock=False)

    with patch(
        "litellm.acompletion",
        side_effect=Timeout(
            message="Call exceeded 5000ms deadline",
            model="bedrock",
            llm_provider="bedrock",
        ),
    ):
        with pytest.raises(LLMTimeoutError) as exc_info:
            await gateway.acomplete("Timeout prompt", task_type=TaskType.SYNTHESIS)

    assert exc_info.value.status_code == 504
    assert exc_info.value.code == "GATEWAY_TIMEOUT"


@pytest.mark.asyncio
async def test_error_standardisation_when_all_models_service_unavailable() -> None:
    """Verify LLMServiceUnavailableError (HTTP 503) raised when both primary and fallback fail with connection error."""
    gateway = LiteLLMGateway(use_mock=False)

    with patch(
        "litellm.acompletion",
        side_effect=APIConnectionError(
            message="Bedrock connection refused",
            model="bedrock",
            llm_provider="bedrock",
        ),
    ):
        with pytest.raises(LLMServiceUnavailableError) as exc_info:
            await gateway.acomplete("Prompt for offline bedrock", task_type=TaskType.SYNTHESIS)

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "SERVICE_UNAVAILABLE"


def test_validation_rejects_empty_prompt() -> None:
    """Verify gateway rejects empty strings and empty message lists."""
    gateway = LiteLLMGateway(use_mock=True)

    with pytest.raises(LLMGatewayError, match="Prompt cannot be empty"):
        gateway.complete("")

    with pytest.raises(LLMGatewayError, match="Prompt cannot be empty"):
        gateway.complete("   ")

    with pytest.raises(LLMGatewayError, match="Prompt cannot be empty"):
        gateway.complete([])

    with pytest.raises(LLMGatewayError, match="Invalid prompt type"):
        gateway.complete(123)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_error_context_window_exceeded() -> None:
    """Verify ContextWindowExceededError translates to LLMContextWindowExceededError (HTTP 400)."""
    gateway = LiteLLMGateway(use_mock=False)

    with patch(
        "litellm.acompletion",
        side_effect=ContextWindowExceededError(
            message="Prompt has 300,000 tokens",
            model="bedrock",
            llm_provider="bedrock",
        ),
    ):
        with pytest.raises(LLMContextWindowExceededError) as exc_info:
            await gateway.acomplete("Gigantic prompt", task_type=TaskType.SYNTHESIS)

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "CONTEXT_WINDOW_EXCEEDED"


@pytest.mark.asyncio
async def test_error_generic_failure_translates_to_gateway_error() -> None:
    """Verify unexpected third-party runtime errors translate to LLMGatewayError (HTTP 500)."""
    gateway = LiteLLMGateway(use_mock=False)

    with patch(
        "litellm.acompletion",
        side_effect=RuntimeError("Internal LiteLLM proxy crash"),
    ):
        with pytest.raises(LLMGatewayError) as exc_info:
            await gateway.acomplete("Prompt", task_type=TaskType.SYNTHESIS)

    assert exc_info.value.status_code == 500
    assert exc_info.value.code == "LLM_GATEWAY_ERROR"


@pytest.mark.asyncio
async def test_fallback_disabled_raises_primary_exception_directly() -> None:
    """Verify primary failure raises directly when fallback model equals primary."""
    gateway = LiteLLMGateway(use_mock=False)

    with patch(
        "litellm.acompletion",
        side_effect=RateLimitError(
            message="Throttled without fallback",
            model=gateway.primary_model,
            llm_provider="bedrock",
        ),
    ):
        with pytest.raises(LLMRateLimitError):
            await gateway.acomplete(
                "Prompt without fallback",
                task_type=TaskType.SYNTHESIS,
                fallback_model=gateway.primary_model,
            )


# ------------------------------------------------------------------------------
# 6. Caching & Traceability
# ------------------------------------------------------------------------------


def test_prompt_caching_hit_and_miss() -> None:
    """Verify in-memory prompt caching returns cached response on identical input."""
    gateway = LiteLLMGateway(use_mock=True)
    gateway.clear_cache()
    prompt = "Unique cache test query for supplier NanoCore"

    # First call -> Cache MISS
    r1 = gateway.complete(prompt, task_type=TaskType.EXTRACTION, use_cache=True)
    assert r1.is_cached is False

    # Second call -> Cache HIT
    r2 = gateway.complete(prompt, task_type=TaskType.EXTRACTION, use_cache=True)
    assert r2.is_cached is True
    assert r2.content == r1.content

    report = gateway.get_cost_report()
    assert report.cache_hit_count == 1


def test_distributed_trace_id_propagation() -> None:
    """Verify distributed trace_id is attached to response metadata."""
    gateway = LiteLLMGateway(use_mock=True)
    test_trace_id = "trace-llm-gate-9988"

    with bind_trace_id(test_trace_id):
        response = gateway.complete("Test prompt with trace")
        assert response.trace_id == test_trace_id


@pytest.mark.asyncio
async def test_sync_complete_inside_existing_event_loop() -> None:
    """Verify synchronous complete() executed inside a running loop dispatches to threadpool."""
    gateway = LiteLLMGateway(use_mock=True)
    res = gateway.complete("Test synchronous execution inside loop", task_type=TaskType.SYNTHESIS)
    assert isinstance(res, LLMResponse)
    assert len(res.content) > 0


def test_singleton_accessor() -> None:
    """Verify get_litellm_gateway returns consistent singleton instance."""
    g1 = get_litellm_gateway()
    g2 = get_litellm_gateway()
    assert g1 is g2
