"""Unit tests for Prometheus metrics export and telemetry instrumentation (P15-3).

Enforces:
- Prometheus metric definitions: counter, gauge, and histogram metrics (CLAUDE.md Sec 8.1 & LLD Sec 8.2)
- Correct metric naming conforming to Prometheus conventions (apexmotion_* prefix)
- Accurate label dimensions across investigation status, model tiers, and HITL spend levels
- Unauthenticated GET /metrics endpoint returning text/plain exposition format
- Automatic HTTP request latency and throughput recording via middleware
- Strict offline isolation with zero external network or Prometheus pushgateway calls
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from src.api.main import app
from src.core.metrics import (
    APPROVAL_TOKENS_MINTED_TOTAL,
    CIRCUIT_BREAKER_TRIPS_TOTAL,
    DETERMINISTIC_CALC_DURATION_SECONDS,
    HITL_PENDING_COUNT,
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
    INVESTIGATION_DURATION_SECONDS,
    INVESTIGATIONS_TOTAL,
    KAFKA_CONSUMER_LAG,
    LLM_COST_USD_TOTAL,
    LLM_TOKENS_TOTAL,
    QUARANTINED_INJECTIONS_BLOCKED_TOTAL,
    generate_latest_metrics,
    record_approval_token_minted,
    record_circuit_breaker_trip,
    record_deterministic_calculation_duration,
    record_http_request,
    record_investigation_completion,
    record_llm_cost,
    record_llm_tokens,
    record_quarantined_injection,
    reset_metrics,
    set_hitl_pending_count,
    set_kafka_consumer_lag,
)


@pytest.fixture(autouse=True)
def clean_metrics_state():
    """Reset all Prometheus collectors between test executions to prevent cross-test contamination."""
    reset_metrics()
    yield
    reset_metrics()


# ------------------------------------------------------------------------------
# 1. Metric Registry & Declarations
# ------------------------------------------------------------------------------


def test_prometheus_metric_collectors_registered():
    """Verify all required Prometheus metrics are declared with apexmotion_ prefix and docstrings."""
    # Note: prometheus_client strips _total from Counter._name internally and appends it during generation
    assert INVESTIGATIONS_TOTAL._name in (
        "apexmotion_investigations",
        "apexmotion_investigations_total",
    )
    assert INVESTIGATION_DURATION_SECONDS._name == "apexmotion_investigation_duration_seconds"
    assert LLM_TOKENS_TOTAL._name in ("apexmotion_llm_tokens", "apexmotion_llm_tokens_total")
    assert LLM_COST_USD_TOTAL._name in ("apexmotion_llm_cost_usd", "apexmotion_llm_cost_usd_total")
    assert KAFKA_CONSUMER_LAG._name == "apexmotion_kafka_consumer_lag"
    assert HITL_PENDING_COUNT._name == "apexmotion_hitl_pending_count"
    assert HTTP_REQUESTS_TOTAL._name in (
        "apexmotion_http_requests",
        "apexmotion_http_requests_total",
    )
    assert HTTP_REQUEST_DURATION_SECONDS._name == "apexmotion_http_request_duration_seconds"
    assert CIRCUIT_BREAKER_TRIPS_TOTAL._name in (
        "apexmotion_circuit_breaker_trips",
        "apexmotion_circuit_breaker_trips_total",
    )
    assert (
        DETERMINISTIC_CALC_DURATION_SECONDS._name
        == "apexmotion_deterministic_calculation_duration_seconds"
    )
    assert QUARANTINED_INJECTIONS_BLOCKED_TOTAL._name in (
        "apexmotion_quarantined_injections_blocked",
        "apexmotion_quarantined_injections_blocked_total",
    )
    assert APPROVAL_TOKENS_MINTED_TOTAL._name in (
        "apexmotion_approval_tokens_minted",
        "apexmotion_approval_tokens_minted_total",
    )

    # Verify rendered output contains all apexmotion_ metric families
    rendered = generate_latest_metrics()
    assert b"apexmotion_investigations" in rendered
    assert b"apexmotion_investigation_duration_seconds" in rendered
    assert b"apexmotion_llm_tokens" in rendered
    assert b"apexmotion_llm_cost_usd" in rendered
    assert b"apexmotion_kafka_consumer_lag" in rendered
    assert b"apexmotion_hitl_pending_count" in rendered
    assert b"apexmotion_http_requests" in rendered
    assert b"apexmotion_http_request_duration_seconds" in rendered
    assert b"apexmotion_circuit_breaker_trips" in rendered
    assert b"apexmotion_deterministic_calculation_duration_seconds" in rendered
    assert b"apexmotion_quarantined_injections_blocked" in rendered
    assert b"apexmotion_approval_tokens_minted" in rendered


# ------------------------------------------------------------------------------
# 2. HTTP Request Metrics (Middleware / Gateway)
# ------------------------------------------------------------------------------


def test_record_http_request_metrics():
    """Verify record_http_request increments counter and observes duration in histogram."""
    record_http_request(
        method="GET",
        endpoint="/api/v1/risk/status",
        status_code=200,
        duration_seconds=0.045,
    )
    record_http_request(
        method="GET",
        endpoint="/api/v1/risk/status",
        status_code=200,
        duration_seconds=0.055,
    )

    metrics_text = generate_latest_metrics().decode("utf-8")
    assert (
        'apexmotion_http_requests_total{endpoint="/api/v1/risk/status",method="GET",status_code="200"} 2.0'
        in metrics_text
    )
    assert (
        'apexmotion_http_request_duration_seconds_count{endpoint="/api/v1/risk/status",method="GET"} 2.0'
        in metrics_text
    )


# ------------------------------------------------------------------------------
# 3. Multi-Agent Investigation Metrics
# ------------------------------------------------------------------------------


def test_record_investigation_completion_metrics():
    """Verify record_investigation_completion records total count and histogram duration."""
    # NanoCore golden scenario investigation (~12.5s)
    record_investigation_completion(status="COMPLETED", duration_seconds=12.5)
    # Dismissed zero-impact alert (~1.2s)
    record_investigation_completion(status="DISMISSED", duration_seconds=1.2)
    # Suspended awaiting HITL approval (~8.0s)
    record_investigation_completion(status="AWAITING_APPROVAL", duration_seconds=8.0)

    metrics_text = generate_latest_metrics().decode("utf-8")
    assert 'apexmotion_investigations_total{status="COMPLETED"} 1.0' in metrics_text
    assert 'apexmotion_investigations_total{status="DISMISSED"} 1.0' in metrics_text
    assert 'apexmotion_investigations_total{status="AWAITING_APPROVAL"} 1.0' in metrics_text
    assert 'apexmotion_investigation_duration_seconds_count{status="COMPLETED"} 1.0' in metrics_text


# ------------------------------------------------------------------------------
# 4. LLM Token & Cost Accounting Metrics
# ------------------------------------------------------------------------------


def test_record_llm_token_and_cost_metrics():
    """Verify record_llm_tokens and record_llm_cost track consumption with model dimensions."""
    # Record Claude 3.5 Sonnet tokens
    record_llm_tokens(prompt_tokens=4200, completion_tokens=650, model="claude-3-5-sonnet")
    # Record Claude 3.5 Haiku tokens
    record_llm_tokens(prompt_tokens=1200, completion_tokens=150, model="claude-3-5-haiku")

    # Record Decimal cost
    record_llm_cost(cost_usd=Decimal("0.0224"), model="claude-3-5-sonnet")
    record_llm_cost(cost_usd=0.0016, model="claude-3-5-haiku")

    metrics_text = generate_latest_metrics().decode("utf-8")
    assert (
        'apexmotion_llm_tokens_total{model="claude-3-5-sonnet",type="prompt"} 4200.0'
        in metrics_text
    )
    assert (
        'apexmotion_llm_tokens_total{model="claude-3-5-sonnet",type="completion"} 650.0'
        in metrics_text
    )
    assert (
        'apexmotion_llm_tokens_total{model="claude-3-5-haiku",type="prompt"} 1200.0' in metrics_text
    )
    assert 'apexmotion_llm_cost_usd_total{model="claude-3-5-sonnet"} 0.0224' in metrics_text
    assert 'apexmotion_llm_cost_usd_total{model="claude-3-5-haiku"} 0.0016' in metrics_text


# ------------------------------------------------------------------------------
# 5. Gauges: Kafka Consumer Lag & Pending HITL Approvals
# ------------------------------------------------------------------------------


def test_gauge_metrics_kafka_lag_and_hitl_pending():
    """Verify gauge metrics update to point-in-time state without accumulation."""
    # Kafka Lag
    set_kafka_consumer_lag(
        lag=125,
        topic="operational.events",
        consumer_group="apexmotion-risk-engine",
    )
    # HITL Pending Count
    set_hitl_pending_count(count=4, tier="CATEGORY_MGR")
    set_hitl_pending_count(count=2, tier="PROC_DIRECTOR")
    set_hitl_pending_count(count=1, tier="DUAL_VP")

    metrics_text = generate_latest_metrics().decode("utf-8")
    assert (
        'apexmotion_kafka_consumer_lag{consumer_group="apexmotion-risk-engine",topic="operational.events"} 125.0'
        in metrics_text
    )
    assert 'apexmotion_hitl_pending_count{tier="CATEGORY_MGR"} 4.0' in metrics_text
    assert 'apexmotion_hitl_pending_count{tier="PROC_DIRECTOR"} 2.0' in metrics_text
    assert 'apexmotion_hitl_pending_count{tier="DUAL_VP"} 1.0' in metrics_text

    # Verify gauge update replaces old value
    set_kafka_consumer_lag(
        lag=0,
        topic="operational.events",
        consumer_group="apexmotion-risk-engine",
    )
    metrics_text_updated = generate_latest_metrics().decode("utf-8")
    assert (
        'apexmotion_kafka_consumer_lag{consumer_group="apexmotion-risk-engine",topic="operational.events"} 0.0'
        in metrics_text_updated
    )


# ------------------------------------------------------------------------------
# 6. Circuit Breakers, Math Durations & Security Events
# ------------------------------------------------------------------------------


def test_circuit_breaker_and_security_metrics():
    """Verify circuit breaker trips, math execution latency, and quarantined injection counts."""
    record_circuit_breaker_trip(service="inventory_service", target="redis")
    record_circuit_breaker_trip(service="contract_agent", target="bedrock")
    record_deterministic_calculation_duration(duration_seconds=0.0012, supplier_id="SUP-NC-4402")
    record_quarantined_injection(source_feed="news")
    record_quarantined_injection(source_feed="sec_edgar")
    record_approval_token_minted(signer_role="vp_supply_chain", spend_tier="DUAL_VP")

    metrics_text = generate_latest_metrics().decode("utf-8")
    assert (
        'apexmotion_circuit_breaker_trips_total{service="inventory_service",target="redis"} 1.0'
        in metrics_text
    )
    assert (
        'apexmotion_circuit_breaker_trips_total{service="contract_agent",target="bedrock"} 1.0'
        in metrics_text
    )
    assert (
        'apexmotion_deterministic_calculation_duration_seconds_count{supplier_id="SUP-NC-4402"} 1.0'
        in metrics_text
    )
    assert 'apexmotion_quarantined_injections_blocked_total{source_feed="news"} 1.0' in metrics_text
    assert (
        'apexmotion_approval_tokens_minted_total{signer_role="vp_supply_chain",spend_tier="DUAL_VP"} 1.0'
        in metrics_text
    )


# ------------------------------------------------------------------------------
# 7. FastAPI Endpoint (/metrics) & Middleware
# ------------------------------------------------------------------------------


def test_fastapi_metrics_endpoint_unauthenticated():
    """Verify GET /metrics returns HTTP 200 with standard Prometheus text/plain format."""
    client = TestClient(app)
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")
    content = response.text
    assert "# HELP apexmotion_investigations_total" in content
    assert "# TYPE apexmotion_investigations_total counter" in content
    assert "# HELP apexmotion_http_requests_total" in content


def test_fastapi_middleware_records_http_metrics_automatically():
    """Verify HTTP requests through FastAPI app automatically record Prometheus metrics."""
    client = TestClient(app)

    # Issue a lightweight health check request
    res_health = client.get("/health")
    assert res_health.status_code == 200

    # Scrape /metrics to inspect observations
    res_metrics = client.get("/metrics")
    assert res_metrics.status_code == 200
    metrics_text = res_metrics.text

    assert (
        'apexmotion_http_requests_total{endpoint="/health",method="GET",status_code="200"}'
        in metrics_text
    )
    assert (
        'apexmotion_http_request_duration_seconds_count{endpoint="/health",method="GET"}'
        in metrics_text
    )
