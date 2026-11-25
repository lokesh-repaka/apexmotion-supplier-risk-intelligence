"""Unit tests for OpenTelemetry setup, @vercel/otel-style span instrumentation,
and log trace_id propagation (P15-1).

Enforces:
- @vercel/otel-style span instrumentation on all FastAPI routes and agent nodes
- Distributed trace context propagation via W3C traceparent headers
- Automatic trace_id propagation to every structured JSON log line
- Zero external network calls (InMemorySpanExporter)
"""

import json
import logging
from decimal import Decimal
from io import StringIO
from typing import Any

import pytest
from fastapi.testclient import TestClient
from src.core.telemetry import (
    extract_trace_context,
    get_current_span_id,
    get_current_trace_id,
    get_in_memory_spans,
    inject_trace_context,
    reset_telemetry,
    setup_telemetry,
    trace_agent_node,
    trace_span,
)


@pytest.fixture(autouse=True)
def reset_otel():
    """Reset telemetry in-memory exporter and state before each test."""
    reset_telemetry()
    yield
    reset_telemetry()


# ------------------------------------------------------------------------------
# 1. Setup & Tracer Provider Lifecycle
# ------------------------------------------------------------------------------


def test_setup_telemetry_defaults_and_tracer():
    """Verify setup_telemetry initializes TracerProvider with standard attributes."""
    tracer = setup_telemetry(service_name="apexmotion-test-service", environment="test")
    assert tracer is not None

    with trace_span("test-initialization-span", attributes={"component": "setup"}):
        pass

    spans = get_in_memory_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "test-initialization-span"
    assert span.attributes is not None
    assert span.attributes.get("component") == "setup"
    assert span.resource.attributes.get("service.name") == "apexmotion-supplier-risk"


# ------------------------------------------------------------------------------
# 2. Synchronous & Asynchronous @trace_span Decorators
# ------------------------------------------------------------------------------


def test_trace_span_sync_decorator_success_and_error():
    """Verify @trace_span wraps sync functions, sets attributes, and captures exceptions."""
    setup_telemetry(service_name="apexmotion-test")

    @trace_span("calc.sync_multiply", attributes={"math.op": "multiply"})
    def multiply(a: int, b: int) -> int:
        return a * b

    @trace_span("calc.sync_failing")
    def fail_op():
        raise ValueError("Simulated mathematical divergence")

    # 1. Success execution
    result = multiply(6, 7)
    assert result == 42

    spans = get_in_memory_spans()
    assert len(spans) == 1
    assert spans[0].name == "calc.sync_multiply"
    assert spans[0].attributes["math.op"] == "multiply"
    assert spans[0].status.is_ok

    # 2. Failure execution
    with pytest.raises(ValueError, match="Simulated mathematical divergence"):
        fail_op()

    spans = get_in_memory_spans()
    assert len(spans) == 2
    err_span = spans[1]
    assert err_span.name == "calc.sync_failing"
    assert not err_span.status.is_ok
    assert any(ev.name == "exception" for ev in err_span.events)


@pytest.mark.asyncio
async def test_trace_span_async_decorator_success_and_error():
    """Verify @trace_span wraps async coroutine functions, sets attributes, and captures errors."""
    setup_telemetry(service_name="apexmotion-test")

    @trace_span("agent.async_fetch", attributes={"agent.id": "research-01"})
    async def async_fetch(entity_id: str) -> dict[str, str]:
        return {"entity": entity_id, "status": "active"}

    @trace_span("agent.async_error")
    async def async_fail():
        raise KeyError("missing_key")

    res = await async_fetch("SUP-NC-4402")
    assert res == {"entity": "SUP-NC-4402", "status": "active"}

    spans = get_in_memory_spans()
    assert len(spans) == 1
    assert spans[0].name == "agent.async_fetch"
    assert spans[0].attributes["agent.id"] == "research-01"
    assert spans[0].status.is_ok

    with pytest.raises(KeyError):
        await async_fail()

    spans = get_in_memory_spans()
    assert len(spans) == 2
    assert spans[1].name == "agent.async_error"
    assert not spans[1].status.is_ok


# ------------------------------------------------------------------------------
# 3. Context Manager Usage
# ------------------------------------------------------------------------------


def test_trace_span_context_manager():
    """Verify with trace_span(...) context manager controls span lifecycle and attributes."""
    setup_telemetry(service_name="apexmotion-test")

    with trace_span("workflow.step_one", attributes={"step": 1}) as span:
        trace_id = get_current_trace_id()
        span_id = get_current_span_id()
        assert trace_id is not None
        assert len(trace_id) == 32
        assert span_id is not None
        assert len(span_id) == 16

        span.set_attribute("step.subtask", "validation")

    spans = get_in_memory_spans()
    assert len(spans) == 1
    assert spans[0].name == "workflow.step_one"
    assert spans[0].attributes["step"] == 1
    assert spans[0].attributes["step.subtask"] == "validation"


# ------------------------------------------------------------------------------
# 4. trace_id Log Line Propagation
# ------------------------------------------------------------------------------


def test_trace_id_automatic_propagation_to_json_logs():
    """Verify that every log line emitted inside a trace automatically contains the 32-hex trace_id."""
    from src.core.logging import JSONFormatter, get_logger

    setup_telemetry(service_name="apexmotion-test")

    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONFormatter(environment="test"))

    logger = get_logger("test.otel.log_propagation")
    logger.setLevel(logging.INFO)
    logger.handlers = [handler]
    logger.propagate = False

    # 1. Log outside span (trace_id should be None)
    logger.info("Un-traced message before span")
    pre_log = json.loads(stream.getvalue().strip().split("\n")[-1])
    assert pre_log["trace_id"] is None

    # 2. Log inside span (trace_id must be present and match span)
    captured_trace_id = None
    with trace_span("traced.operation"):
        captured_trace_id = get_current_trace_id()
        assert captured_trace_id is not None
        logger.info("Message inside active span")

    traced_log = json.loads(stream.getvalue().strip().split("\n")[-1])
    assert traced_log["trace_id"] == captured_trace_id
    assert len(traced_log["trace_id"]) == 32

    # 3. Log after span exit (trace_id restored to None)
    logger.info("Un-traced message after span")
    post_log = json.loads(stream.getvalue().strip().split("\n")[-1])
    assert post_log["trace_id"] is None


# ------------------------------------------------------------------------------
# 5. W3C traceparent Injection & Extraction
# ------------------------------------------------------------------------------


def test_w3c_traceparent_injection_and_extraction():
    """Verify injection and extraction of W3C traceparent headers."""
    setup_telemetry(service_name="apexmotion-test")

    with trace_span("parent_service_call"):
        parent_trace_id = get_current_trace_id()
        headers: dict[str, str] = {}
        inject_trace_context(headers)

        assert "traceparent" in headers
        tp = headers["traceparent"]
        parts = tp.split("-")
        assert len(parts) == 4
        assert parts[0] == "00"
        assert parts[1] == parent_trace_id

    # Test extracting the context in downstream consumer
    ctx = extract_trace_context(headers)
    with trace_span("child_service_call", context=ctx):
        child_trace_id = get_current_trace_id()
        assert child_trace_id == parent_trace_id


# ------------------------------------------------------------------------------
# 6. FastAPI Routes Instrumentation
# ------------------------------------------------------------------------------


def test_fastapi_route_instrumentation_creates_server_spans():
    """Verify FastAPI routes create HTTP server spans and attach X-Trace-ID / traceparent."""
    from src.api.main import app

    setup_telemetry(service_name="apexmotion-api-test")
    client = TestClient(app)

    response = client.get("/health")
    assert response.status_code == 200

    # Verify response headers
    assert "X-Trace-ID" in response.headers
    assert "X-Request-ID" in response.headers
    assert "traceparent" in response.headers
    trace_id_header = response.headers["X-Trace-ID"]

    # Verify OpenTelemetry server span recorded
    spans = get_in_memory_spans()
    http_spans = [s for s in spans if s.name.startswith("HTTP")]
    assert len(http_spans) >= 1
    span = http_spans[-1]

    assert span.attributes["http.method"] == "GET"
    assert "/health" in span.attributes["http.target"]
    assert span.attributes["http.status_code"] == 200
    assert f"{span.context.trace_id:032x}" == trace_id_header


def test_fastapi_route_propagates_incoming_traceparent():
    """Verify incoming W3C traceparent header is extracted and adopted by FastAPI route span."""
    from src.api.main import app

    setup_telemetry(service_name="apexmotion-api-test")
    client = TestClient(app)

    incoming_trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    incoming_parent_id = "00f067aa0ba902b7"
    incoming_traceparent = f"00-{incoming_trace_id}-{incoming_parent_id}-01"

    response = client.get(
        "/health",
        headers={"traceparent": incoming_traceparent},
    )
    assert response.status_code == 200
    assert response.headers["X-Trace-ID"] == incoming_trace_id

    spans = get_in_memory_spans()
    http_spans = [s for s in spans if s.name.startswith("HTTP")]
    assert len(http_spans) >= 1
    span = http_spans[-1]
    assert f"{span.context.trace_id:032x}" == incoming_trace_id


# ------------------------------------------------------------------------------
# 7. Agent Node Instrumentation Spans
# ------------------------------------------------------------------------------


def test_agent_node_decorator_creates_spans_with_domain_attributes():
    """Verify @trace_agent_node records domain metadata (alert_id, supplier_id, status)."""
    setup_telemetry(service_name="apexmotion-test")

    @trace_agent_node("triage")
    def mock_triage_node(_state: dict[str, Any]) -> dict[str, Any]:
        return {
            "current_node": "triage",
            "workflow_status": "INVESTIGATING",
            "execution_path": ["triage"],
        }

    sample_state = {
        "alert_id": "ALT-NC-2026-001",
        "supplier_id": "SUP-NC-4402",
        "signal_type": "news",
    }

    result = mock_triage_node(sample_state)
    assert result["workflow_status"] == "INVESTIGATING"

    spans = get_in_memory_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "agent.node.triage"
    assert span.attributes["agent.node"] == "triage"
    assert span.attributes["alert_id"] == "ALT-NC-2026-001"
    assert span.attributes["supplier_id"] == "SUP-NC-4402"
    assert span.attributes["workflow_status"] == "INVESTIGATING"


def test_all_agent_graph_nodes_are_instrumented():
    """Verify that every node in the LangGraph StateGraph executes within an OpenTelemetry span."""
    from src.agents.graph import (
        NODE_DISMISS,
        NODE_HITL_GATE,
        dismiss_node,
        hitl_gate_node,
    )
    from src.agents.state import WorkflowStatus

    setup_telemetry(service_name="apexmotion-test")

    # 1. Dismiss node span
    state_dismiss = {
        "alert_id": "ALT-TEST-DISMISS",
        "supplier_id": "SUP-001",
        "workflow_status": WorkflowStatus.INVESTIGATING,
    }
    dismiss_node(state_dismiss)

    spans = get_in_memory_spans()
    dismiss_spans = [s for s in spans if s.name == f"agent.node.{NODE_DISMISS}"]
    assert len(dismiss_spans) == 1
    assert dismiss_spans[0].attributes["alert_id"] == "ALT-TEST-DISMISS"

    # 2. HITL Gate node span
    reset_telemetry()
    state_hitl = {
        "alert_id": "ALT-TEST-HITL",
        "supplier_id": "SUP-002",
        "requires_hitl": True,
        "governing_spend_tier": "TIER_1_CATEGORY_MGR",
    }
    hitl_gate_node(state_hitl)

    spans = get_in_memory_spans()
    hitl_spans = [s for s in spans if s.name == f"agent.node.{NODE_HITL_GATE}"]
    assert len(hitl_spans) == 1
    assert hitl_spans[0].attributes["governing_spend_tier"] == "TIER_1_CATEGORY_MGR"


@pytest.mark.asyncio
async def test_orchestrator_investigation_workflow_execute_span():
    """Verify InvestigationOrchestrator creates the root span 'investigation_workflow_execute'."""
    from src.agents.orchestrator import InvestigationOrchestrator
    from src.agents.state import create_initial_state

    setup_telemetry(service_name="apexmotion-test")
    orchestrator = InvestigationOrchestrator()

    state = create_initial_state(
        alert_id="ALT-OTEL-ORCH-001",
        supplier_id="SUP-NC-4402",
        signal_type="news",
        raw_signal="Factory disruption minor event",
    )
    # Mark zero-impact metadata so it terminates cleanly at dismiss node
    state["metadata"] = {"zero_impact": True}

    res = await orchestrator.run_investigation(state)
    assert res is not None

    spans = get_in_memory_spans()
    span_names = [s.name for s in spans]

    # Verify root trace and child node spans
    assert "investigation_workflow_execute" in span_names
    assert "agent.node.triage" in span_names
    assert "agent.node.dismiss" in span_names

    root_span = next(s for s in spans if s.name == "investigation_workflow_execute")
    assert root_span.attributes["alert_id"] == "ALT-OTEL-ORCH-001"
    assert root_span.attributes["supplier_id"] == "SUP-NC-4402"


# ------------------------------------------------------------------------------
# 8. Pillar Spans (QuarantinedReader & RiskCalculator per LLD Sec 8.1)
# ------------------------------------------------------------------------------


def test_quarantined_reader_span_instrumentation():
    """Verify QuarantinedReader.sanitize creates span 'quarantined_reader.sanitize' (LLD Sec 8.1)."""
    from src.llm.quarantined_reader import QuarantinedReader

    setup_telemetry(service_name="apexmotion-test")
    reader = QuarantinedReader()

    res = reader.sanitize("Supplier report with clean contents.")
    assert res.is_safe

    spans = get_in_memory_spans()
    qr_spans = [s for s in spans if s.name == "quarantined_reader.sanitize"]
    assert len(qr_spans) == 1
    assert "input.chars" in qr_spans[0].attributes


def test_risk_calculator_span_instrumentation():
    """Verify RiskCalculator.calculate_risk creates span 'math_engine.calculate_coverage' (LLD Sec 8.1)."""
    from src.services.risk.calculator import RiskAssessmentInput, RiskCalculator

    setup_telemetry(service_name="apexmotion-test")
    calculator = RiskCalculator()

    inp = RiskAssessmentInput(
        current_stock=Decimal("142000.00"),
        daily_consumption_rate=Decimal("18500.00"),
        eta_days=Decimal("9.00"),
        unit_cost_usd=Decimal("100.25"),
        factory_halt_cost_per_hour_eur=Decimal("85000.00"),
    )
    calculator.calculate_risk(inp)

    spans = get_in_memory_spans()
    math_spans = [s for s in spans if s.name == "math_engine.calculate_coverage"]
    assert len(math_spans) == 1
    assert math_spans[0].attributes["days_of_cover"] == "7.68"
    assert math_spans[0].attributes["shortage_gap"] == "1.32"


@pytest.mark.asyncio
async def test_agent_node_async_decorator_with_metrics_and_error():
    """Verify @trace_agent_node on async nodes captures metrics and records errors."""
    setup_telemetry(service_name="apexmotion-test")

    @trace_agent_node("contract")
    async def async_contract_node(_state: dict[str, Any]) -> dict[str, Any]:
        return {
            "current_node": "contract",
            "workflow_status": "INVESTIGATING",
            "risk_metrics": {
                "days_of_cover": Decimal("7.68"),
                "gap_days": Decimal("1.32"),
                "financial_exposure_usd": Decimal("2448105.00"),
            },
        }

    @trace_agent_node("failing_node")
    async def async_failing_node(_state: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("Agent node execution failed")

    # 1. Async success with risk metrics
    state = {
        "alert_id": "ALT-ASYNC-001",
        "supplier_id": "SUP-NC-4402",
        "signal_type": "contract",
    }
    res = await async_contract_node(state)
    assert res["workflow_status"] == "INVESTIGATING"

    spans = get_in_memory_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "agent.node.contract"
    assert span.attributes["days_of_cover"] == "7.68"
    assert span.attributes["gap_days"] == "1.32"
    assert span.attributes["financial_exposure_usd"] == "2448105.00"

    # 2. Async error
    with pytest.raises(RuntimeError, match="Agent node execution failed"):
        await async_failing_node(state)

    spans = get_in_memory_spans()
    assert len(spans) == 2
    err_span = spans[1]
    assert err_span.name == "agent.node.failing_node"
    assert not err_span.status.is_ok
