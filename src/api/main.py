"""ApexMotion Supplier Risk Intelligence Platform - Main FastAPI Application.

Initializes FastAPI application instance, lifespan context manager, CORS middleware,
request ID / distributed tracing middleware, and global error handling envelopes.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.trace import SpanKind

from src.api.routes.approval_routes import router as approval_router
from src.api.routes.error_handlers import register_error_handlers
from src.api.routes.health import router as health_router
from src.api.routes.investigation_routes import router as investigation_router
from src.api.routes.risk_routes import router as risk_router
from src.api.routes.supplier_routes import router as supplier_router
from src.api.routes.websocket_routes import router as websocket_router
from src.core.logging import bind_trace_id, get_logger, setup_logging
from src.core.telemetry import (
    extract_trace_context,
    get_current_trace_id,
    inject_trace_context,
    setup_telemetry,
    trace_span,
)

logger = get_logger("apexmotion.api")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager initializing logging and shared resources."""
    setup_logging()
    setup_telemetry()
    logger.info("ApexMotion Supplier Risk Intelligence Platform starting up")
    yield
    logger.info("ApexMotion Supplier Risk Intelligence Platform shutting down")


app = FastAPI(
    title="ApexMotion Supplier Risk Intelligence Platform",
    description="Multi-agent supplier risk intelligence platform with deterministic risk calculation and cryptographically governed HITL approval gates.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ------------------------------------------------------------------------------
# Global Middleware Configuration
# ------------------------------------------------------------------------------


# Request ID and Trace Propagation Middleware
@app.middleware("http")
async def trace_and_request_id_middleware(request: Request, call_next: Any) -> Response:
    """Extract or generate W3C traceparent, X-Request-ID, and X-Trace-ID, bind to context, and attach to response."""
    extracted_ctx = extract_trace_context(request.headers)
    span_name = f"HTTP {request.method} {request.url.path}"
    attributes: dict[str, Any] = {
        "http.method": request.method,
        "http.url": str(request.url),
        "http.target": request.url.path,
        "http.host": request.url.hostname or "localhost",
        "http.scheme": request.url.scheme,
        "http.client_ip": request.client.host if request.client else "unknown",
        "http.user_agent": request.headers.get("user-agent", ""),
    }

    incoming_id = request.headers.get("x-request-id") or request.headers.get("x-trace-id")

    with trace_span(
        span_name, attributes=attributes, kind=SpanKind.SERVER, context=extracted_ctx
    ) as span:
        otel_trace_id = get_current_trace_id()
        trace_id = incoming_id or otel_trace_id or str(uuid.uuid4())
        request.state.trace_id = trace_id

        with bind_trace_id(trace_id):
            response: Response = await call_next(request)
            span.set_attribute("http.status_code", response.status_code)
            response.headers["X-Request-ID"] = trace_id
            response.headers["X-Trace-ID"] = trace_id
            inject_trace_context(response.headers)
            return response


# CORS Middleware Configuration
ALLOWED_ORIGINS = [
    "http://localhost:5173",  # Vite dev server
    "http://localhost:3000",  # Next.js / alternative dev server
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Trace-ID", "traceparent"],
)


# ------------------------------------------------------------------------------
# Global Exception Handlers (CLAUDE.md Section 10 Specification)
# ------------------------------------------------------------------------------

register_error_handlers(app)


# ------------------------------------------------------------------------------
# API Routers Mount
# ------------------------------------------------------------------------------

app.include_router(health_router)
app.include_router(risk_router)
app.include_router(investigation_router)
app.include_router(approval_router)
app.include_router(supplier_router)
app.include_router(websocket_router)
