"""Prometheus Metrics Export & Telemetry Instrumentation (P15-3).

Enforces:
- Counter, gauge, and histogram metric exports conforming to Prometheus conventions (CLAUDE.md Sec 8.1 & LLD Sec 8.2)
- Multi-agent investigation duration tracking against the p95 <= 90s SLO (CLAUDE.md Sec 13)
- Token and cost accumulation metrics by model tier (Claude 3.5 Sonnet, Haiku, Llama 3.1 70B)
- Kafka consumer lag depth and HITL pending queue depth gauges
- Circuit breaker trip and prompt injection defense counters
- Exposition format via GET /metrics endpoint (text/plain; version=0.0.4)
- Strict offline isolation (zero external telemetry dispatch)
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from src.core.logging import get_logger

logger = get_logger("apexmotion.core.metrics")

# Prometheus Content-Type header
PROMETHEUS_CONTENT_TYPE = CONTENT_TYPE_LATEST

# ------------------------------------------------------------------------------
# 1. Metric Declarations
# ------------------------------------------------------------------------------

# HTTP Request Throughput and Latency
HTTP_REQUESTS_TOTAL = Counter(
    "apexmotion_http_requests_total",
    "Total incoming HTTP requests handled by the API gateway.",
    ["method", "endpoint", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "apexmotion_http_request_duration_seconds",
    "HTTP request processing latency in seconds.",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Multi-Agent Investigation Metrics
INVESTIGATIONS_TOTAL = Counter(
    "apexmotion_investigations_total",
    "Total multi-agent incident investigations executed.",
    ["status"],
)

INVESTIGATION_DURATION_SECONDS = Histogram(
    "apexmotion_investigation_duration_seconds",
    "Multi-agent LangGraph workflow duration in seconds (SLO: p95 <= 90s).",
    ["status"],
    buckets=(5.0, 10.0, 30.0, 60.0, 75.0, 90.0, 120.0, 180.0),
)

# LLM Token & Cost Metrics
LLM_TOKENS_TOTAL = Counter(
    "apexmotion_llm_tokens_total",
    "Total LLM tokens consumed across agents and gateways.",
    ["model", "type"],
)

LLM_COST_USD_TOTAL = Counter(
    "apexmotion_llm_cost_usd_total",
    "Accumulated LLM inference cost in USD.",
    ["model"],
)

# Operational Gauges
KAFKA_CONSUMER_LAG = Gauge(
    "apexmotion_kafka_consumer_lag",
    "Current message lag depth for Kafka consumer groups.",
    ["topic", "consumer_group"],
)

HITL_PENDING_COUNT = Gauge(
    "apexmotion_hitl_pending_count",
    "Current pending HITL authorization requests awaiting signature.",
    ["tier"],
)

# Resilience & Circuit Breaker Counters
CIRCUIT_BREAKER_TRIPS_TOTAL = Counter(
    "apexmotion_circuit_breaker_trips_total",
    "Total circuit breaker trip and fallback trigger events.",
    ["service", "target"],
)

# Mathematical Engine & Security Counters
DETERMINISTIC_CALC_DURATION_SECONDS = Histogram(
    "apexmotion_deterministic_calculation_duration_seconds",
    "Deterministic risk calculator arithmetic execution latency in seconds.",
    ["supplier_id"],
    buckets=(0.0005, 0.001, 0.005, 0.01, 0.05, 0.1),
)

QUARANTINED_INJECTIONS_BLOCKED_TOTAL = Counter(
    "apexmotion_quarantined_injections_blocked_total",
    "Total prompt injection vectors detected and sanitized by QuarantinedReader.",
    ["source_feed"],
)

APPROVAL_TOKENS_MINTED_TOTAL = Counter(
    "apexmotion_approval_tokens_minted_total",
    "Total KMS ECDSA P-256 HITL approval tokens minted.",
    ["signer_role", "spend_tier"],
)

_ALL_COLLECTORS: list[Any] = [
    HTTP_REQUESTS_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
    INVESTIGATIONS_TOTAL,
    INVESTIGATION_DURATION_SECONDS,
    LLM_TOKENS_TOTAL,
    LLM_COST_USD_TOTAL,
    KAFKA_CONSUMER_LAG,
    HITL_PENDING_COUNT,
    CIRCUIT_BREAKER_TRIPS_TOTAL,
    DETERMINISTIC_CALC_DURATION_SECONDS,
    QUARANTINED_INJECTIONS_BLOCKED_TOTAL,
    APPROVAL_TOKENS_MINTED_TOTAL,
]


# ------------------------------------------------------------------------------
# 2. Recording Helper Functions
# ------------------------------------------------------------------------------


def record_http_request(
    method: str,
    endpoint: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    """Record an HTTP request count and latency observation."""
    clean_endpoint = endpoint.split("?")[0]
    HTTP_REQUESTS_TOTAL.labels(
        method=method.upper(),
        endpoint=clean_endpoint,
        status_code=str(status_code),
    ).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(
        method=method.upper(),
        endpoint=clean_endpoint,
    ).observe(duration_seconds)


def record_investigation_completion(
    status: str,
    duration_seconds: float,
) -> None:
    """Record a completed or suspended investigation run and duration."""
    clean_status = status.upper()
    INVESTIGATIONS_TOTAL.labels(status=clean_status).inc()
    INVESTIGATION_DURATION_SECONDS.labels(status=clean_status).observe(duration_seconds)


def record_llm_tokens(
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    model: str = "claude-3-5-sonnet",
) -> None:
    """Record prompt and completion tokens for an LLM model."""
    clean_model = model.lower()
    if prompt_tokens > 0:
        LLM_TOKENS_TOTAL.labels(model=clean_model, type="prompt").inc(prompt_tokens)
    if completion_tokens > 0:
        LLM_TOKENS_TOTAL.labels(model=clean_model, type="completion").inc(completion_tokens)


def record_llm_cost(
    cost_usd: float | Decimal,
    model: str = "claude-3-5-sonnet",
) -> None:
    """Record accumulated monetary inference cost in USD."""
    float_cost = float(cost_usd)
    if float_cost > 0.0:
        LLM_COST_USD_TOTAL.labels(model=model.lower()).inc(float_cost)


def set_kafka_consumer_lag(
    lag: int | float,
    topic: str = "operational.events",
    consumer_group: str = "apexmotion-risk-engine",
) -> None:
    """Update current consumer group lag gauge."""
    KAFKA_CONSUMER_LAG.labels(topic=topic, consumer_group=consumer_group).set(float(lag))


def set_hitl_pending_count(
    count: int | float,
    tier: str = "DUAL_VP",
) -> None:
    """Update active pending approvals queue depth gauge for a spend tier."""
    HITL_PENDING_COUNT.labels(tier=tier.upper()).set(float(count))


def record_circuit_breaker_trip(
    service: str,
    target: str,
) -> None:
    """Record a circuit breaker trip or fallback event."""
    CIRCUIT_BREAKER_TRIPS_TOTAL.labels(service=service.lower(), target=target.lower()).inc()


def record_deterministic_calculation_duration(
    duration_seconds: float,
    supplier_id: str = "UNKNOWN",
) -> None:
    """Record execution latency for the deterministic Python risk calculator."""
    DETERMINISTIC_CALC_DURATION_SECONDS.labels(supplier_id=supplier_id).observe(duration_seconds)


def record_quarantined_injection(
    source_feed: str = "unknown",
) -> None:
    """Record a detected and neutralized prompt injection vector."""
    QUARANTINED_INJECTIONS_BLOCKED_TOTAL.labels(source_feed=source_feed.lower()).inc()


def record_approval_token_minted(
    signer_role: str,
    spend_tier: str,
) -> None:
    """Record minting of a cryptographically signed KMS ECDSA approval token."""
    APPROVAL_TOKENS_MINTED_TOTAL.labels(
        signer_role=signer_role.lower(),
        spend_tier=spend_tier.upper(),
    ).inc()


# ------------------------------------------------------------------------------
# 3. Exposition & Test Reset Utilities
# ------------------------------------------------------------------------------


def generate_latest_metrics(registry: CollectorRegistry = REGISTRY) -> bytes:
    """Generate Prometheus text exposition bytes."""
    return generate_latest(registry)


def reset_metrics() -> None:
    """Clear metric samples across all registered collectors for test isolation."""
    for collector in _ALL_COLLECTORS:
        try:
            # Clear multi-dimensional metric label dictionaries
            if hasattr(collector, "_metrics"):
                collector._metrics.clear()
        except Exception:
            pass


__all__ = [
    "APPROVAL_TOKENS_MINTED_TOTAL",
    "CIRCUIT_BREAKER_TRIPS_TOTAL",
    "DETERMINISTIC_CALC_DURATION_SECONDS",
    "HITL_PENDING_COUNT",
    "HTTP_REQUESTS_TOTAL",
    "HTTP_REQUEST_DURATION_SECONDS",
    "INVESTIGATIONS_TOTAL",
    "INVESTIGATION_DURATION_SECONDS",
    "KAFKA_CONSUMER_LAG",
    "LLM_COST_USD_TOTAL",
    "LLM_TOKENS_TOTAL",
    "PROMETHEUS_CONTENT_TYPE",
    "QUARANTINED_INJECTIONS_BLOCKED_TOTAL",
    "generate_latest_metrics",
    "record_approval_token_minted",
    "record_circuit_breaker_trip",
    "record_deterministic_calculation_duration",
    "record_http_request",
    "record_investigation_completion",
    "record_llm_cost",
    "record_llm_tokens",
    "record_quarantined_injection",
    "reset_metrics",
    "set_hitl_pending_count",
    "set_kafka_consumer_lag",
]
