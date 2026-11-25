"""OpenTelemetry Tracing and @vercel/otel-style Span Instrumentation (P15-1).

Enforces:
- @vercel/otel-style ergonomics: setup_telemetry, get_tracer, @trace_span, with trace_span
- W3C traceparent distributed context injection and extraction
- Automatic propagation of 32-hex trace_id to all structured JSON log lines
- Specialized LangGraph agent node instrumentation (@trace_agent_node)
- Pure offline isolation via InMemorySpanExporter (zero network/cloud I/O required)
"""

from __future__ import annotations

import functools
import inspect
import threading
from collections.abc import Callable, Mapping
from typing import Any, ParamSpec, TypeVar, cast

from opentelemetry import context, trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Span, SpanKind, Status, StatusCode, Tracer
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

P = ParamSpec("P")
R = TypeVar("R")

# ------------------------------------------------------------------------------
# Module-level Singletons & Synchronization
# ------------------------------------------------------------------------------

_TELEMETRY_LOCK = threading.RLock()
_TRACER_PROVIDER: TracerProvider | None = None
_IN_MEMORY_EXPORTER: InMemorySpanExporter | None = None
_PROPAGATOR = TraceContextTextMapPropagator()


def setup_telemetry(
    service_name: str = "apexmotion-supplier-risk",
    service_version: str = "0.1.0",
    environment: str = "production",
    force_reset: bool = False,
) -> Tracer:
    """Initialize or reconfigure the OpenTelemetry TracerProvider and in-memory exporter."""
    global _TRACER_PROVIDER, _IN_MEMORY_EXPORTER

    with _TELEMETRY_LOCK:
        if _TRACER_PROVIDER is not None and not force_reset:
            return _TRACER_PROVIDER.get_tracer(service_name, service_version)

        if _TRACER_PROVIDER is None:
            resource = Resource.create(
                {
                    "service.name": service_name,
                    "service.version": service_version,
                    "deployment.environment": environment,
                }
            )
            provider = TracerProvider(resource=resource)
            exporter = InMemorySpanExporter()
            processor = SimpleSpanProcessor(exporter)
            provider.add_span_processor(processor)

            trace.set_tracer_provider(provider)
            _TRACER_PROVIDER = provider
            _IN_MEMORY_EXPORTER = exporter
        else:
            if _IN_MEMORY_EXPORTER is not None:
                _IN_MEMORY_EXPORTER.clear()

        return _TRACER_PROVIDER.get_tracer(service_name, service_version)


def get_tracer(name: str = "apexmotion", version: str = "0.1.0") -> Tracer:
    """Obtain an OpenTelemetry Tracer from the active provider or initialize default."""
    global _TRACER_PROVIDER
    if _TRACER_PROVIDER is None:
        setup_telemetry()
    assert _TRACER_PROVIDER is not None
    return _TRACER_PROVIDER.get_tracer(name, version)


def get_in_memory_spans() -> list[ReadableSpan]:
    """Return a list of all finished spans captured by the in-memory exporter."""
    if _IN_MEMORY_EXPORTER is None:
        return []
    return list(_IN_MEMORY_EXPORTER.get_finished_spans())


def reset_telemetry() -> None:
    """Clear recorded spans and reset telemetry provider state for test isolation."""
    global _TRACER_PROVIDER, _IN_MEMORY_EXPORTER
    with _TELEMETRY_LOCK:
        if _IN_MEMORY_EXPORTER is not None:
            _IN_MEMORY_EXPORTER.clear()
        if _TRACER_PROVIDER is None:
            setup_telemetry()


# ------------------------------------------------------------------------------
# Trace Context Accessors & W3C Propagation
# ------------------------------------------------------------------------------


def get_current_trace_id() -> str | None:
    """Extract active trace_id formatted as a 32-hex character string, or None."""
    current_span = trace.get_current_span()
    if current_span is not None:
        span_ctx = current_span.get_span_context()
        if span_ctx.is_valid and span_ctx.trace_id != 0:
            return f"{span_ctx.trace_id:032x}"
    return None


def get_current_span_id() -> str | None:
    """Extract active span_id formatted as a 16-hex character string, or None."""
    current_span = trace.get_current_span()
    if current_span is not None:
        span_ctx = current_span.get_span_context()
        if span_ctx.is_valid and span_ctx.span_id != 0:
            return f"{span_ctx.span_id:016x}"
    return None


def inject_trace_context(
    carrier: Any = None,
) -> Any:
    """Inject current distributed trace context into carrier dict or header mapping (W3C traceparent)."""
    target = carrier if carrier is not None else {}
    _PROPAGATOR.inject(target)
    return target


def extract_trace_context(carrier: Mapping[str, str]) -> context.Context:
    """Extract distributed trace context from carrier dict containing traceparent."""
    return _PROPAGATOR.extract(carrier)


# ------------------------------------------------------------------------------
# @vercel/otel-style Span Decorator & Context Manager
# ------------------------------------------------------------------------------


class TraceSpan:
    """Callable decorator and context manager for @vercel/otel-style span management."""

    def __init__(
        self,
        name: str | None = None,
        attributes: Mapping[str, Any] | None = None,
        kind: SpanKind = SpanKind.INTERNAL,
        tracer_name: str = "apexmotion",
        otel_context: context.Context | None = None,
    ) -> None:
        self.name = name
        self.attributes = dict(attributes) if attributes else {}
        self.kind = kind
        self.tracer_name = tracer_name
        self.otel_context = otel_context
        self._span: Span | None = None
        self._token: Any = None
        self._logging_token: Any = None

    def __enter__(self) -> Span:
        tracer = get_tracer(self.tracer_name)
        span_name = self.name or "operation"

        # Attach custom context if provided
        if self.otel_context is not None:
            self._token = context.attach(self.otel_context)

        # Start span as active current span
        self._span = tracer.start_span(span_name, kind=self.kind)
        span_ctx = self._span.get_span_context()

        # Set initial attributes
        if self.attributes:
            for k, v in self.attributes.items():
                self._span.set_attribute(k, v)

        # Set active context with span
        ctx_with_span = trace.set_span_in_context(self._span)
        self._token = context.attach(ctx_with_span)

        # Bind 32-hex trace_id into src.core.logging ContextVar
        if span_ctx.is_valid and span_ctx.trace_id != 0:
            from src.core.logging import _TRACE_ID_VAR

            trace_id_str = f"{span_ctx.trace_id:032x}"
            self._logging_token = _TRACE_ID_VAR.set(trace_id_str)

        return self._span

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._span is not None:
            if exc_val is not None:
                self._span.record_exception(exc_val)
                self._span.set_status(Status(StatusCode.ERROR, str(exc_val)))
            else:
                self._span.set_status(Status(StatusCode.OK))
            self._span.end()

        # Detach OTel context token
        if self._token is not None:
            context.detach(self._token)
            self._token = None

        # Reset logging ContextVar
        if self._logging_token is not None:
            from src.core.logging import _TRACE_ID_VAR

            _TRACE_ID_VAR.reset(self._logging_token)
            self._logging_token = None

    def __call__(self, fn: Callable[P, R]) -> Callable[P, R]:
        span_name = self.name or fn.__name__

        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                with TraceSpan(
                    name=span_name,
                    attributes=self.attributes,
                    kind=self.kind,
                    tracer_name=self.tracer_name,
                    otel_context=self.otel_context,
                ):
                    return await fn(*args, **kwargs)

            return cast(Callable[P, R], async_wrapper)
        else:

            @functools.wraps(fn)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                with TraceSpan(
                    name=span_name,
                    attributes=self.attributes,
                    kind=self.kind,
                    tracer_name=self.tracer_name,
                    otel_context=self.otel_context,
                ):
                    return fn(*args, **kwargs)

            return sync_wrapper


def trace_span(
    name: str | None = None,
    attributes: Mapping[str, Any] | None = None,
    kind: SpanKind = SpanKind.INTERNAL,
    tracer_name: str = "apexmotion",
    context: context.Context | None = None,
) -> TraceSpan:
    """Create a @vercel/otel-style trace span decorator or context manager."""
    return TraceSpan(
        name=name,
        attributes=attributes,
        kind=kind,
        tracer_name=tracer_name,
        otel_context=context,
    )


# ------------------------------------------------------------------------------
# Agent Node Tracing Decorator
# ------------------------------------------------------------------------------


def trace_agent_node(node_name: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator instrumenting LangGraph agent nodes with OpenTelemetry spans and domain metadata.

    Captures:
    - Span name: agent.node.{node_name}
    - Attributes: agent.node, alert_id, supplier_id, signal_type, governing_spend_tier
    - Completion metrics: workflow_status, current_node, calculation metrics
    - Error status and exceptions
    """

    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        span_name = f"agent.node.{node_name}"

        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_agent_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                state = (
                    args[0] if args and isinstance(args[0], Mapping) else kwargs.get("state", {})
                )
                init_attrs: dict[str, Any] = {"agent.node": node_name}
                if isinstance(state, Mapping):
                    for key in ("alert_id", "supplier_id", "signal_type", "governing_spend_tier"):
                        if state.get(key) is not None:
                            init_attrs[key] = str(state[key])

                with trace_span(span_name, attributes=init_attrs) as span:
                    result = await fn(*args, **kwargs)
                    if isinstance(result, Mapping):
                        _record_node_result_attributes(span, result)
                    return result

            return cast(Callable[P, R], async_agent_wrapper)
        else:

            @functools.wraps(fn)
            def sync_agent_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                state = (
                    args[0] if args and isinstance(args[0], Mapping) else kwargs.get("state", {})
                )
                init_attrs: dict[str, Any] = {"agent.node": node_name}
                if isinstance(state, Mapping):
                    for key in ("alert_id", "supplier_id", "signal_type", "governing_spend_tier"):
                        if state.get(key) is not None:
                            init_attrs[key] = str(state[key])

                with trace_span(span_name, attributes=init_attrs) as span:
                    result = fn(*args, **kwargs)
                    if isinstance(result, Mapping):
                        _record_node_result_attributes(span, result)
                    return result

            return sync_agent_wrapper

    return decorator


def _record_node_result_attributes(span: Span, result: Mapping[str, Any]) -> None:
    """Helper recording output metrics on an agent node span."""
    for key in ("workflow_status", "current_node", "risk_level"):
        if result.get(key) is not None:
            span.set_attribute(key, str(result[key]))

    risk_metrics = result.get("risk_metrics")
    if isinstance(risk_metrics, Mapping):
        for metric_key in ("days_of_cover", "gap_days", "financial_exposure_usd"):
            if risk_metrics.get(metric_key) is not None:
                span.set_attribute(metric_key, str(risk_metrics[metric_key]))


__all__ = [
    "extract_trace_context",
    "get_current_span_id",
    "get_current_trace_id",
    "get_in_memory_spans",
    "get_tracer",
    "inject_trace_context",
    "reset_telemetry",
    "setup_telemetry",
    "trace_agent_node",
    "trace_span",
]
