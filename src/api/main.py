"""ApexMotion Supplier Risk Intelligence Platform - Main FastAPI Application.

Initializes FastAPI application instance, lifespan context manager, CORS middleware,
request ID / distributed tracing middleware, and global error handling envelopes.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api.exceptions import AppException, format_error_response
from src.api.routes.health import router as health_router
from src.api.routes.risk_routes import router as risk_router
from src.core.logging import bind_trace_id, get_logger, get_trace_id, setup_logging

logger = get_logger("apexmotion.api")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager initializing logging and shared resources."""
    setup_logging()
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
    """Extract or generate X-Request-ID and X-Trace-ID, bind to context, and attach to response."""
    incoming_id = request.headers.get("x-request-id") or request.headers.get("x-trace-id")
    trace_id = incoming_id if incoming_id else str(uuid.uuid4())

    request.state.trace_id = trace_id

    with bind_trace_id(trace_id):
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = trace_id
        response.headers["X-Trace-ID"] = trace_id
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
    expose_headers=["X-Request-ID", "X-Trace-ID"],
)


# ------------------------------------------------------------------------------
# Global Exception Handlers (CLAUDE.md Section 10 Specification)
# ------------------------------------------------------------------------------


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle custom application exceptions and format standard error envelope."""
    trace_id = getattr(request.state, "trace_id", None) or get_trace_id()
    return JSONResponse(
        status_code=exc.status_code,
        content=format_error_response(
            code=exc.code,
            message=exc.message,
            trace_id=trace_id,
            details=exc.details,
        ),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic schema validation failures with VALIDATION_ERROR code."""
    trace_id = getattr(request.state, "trace_id", None) or get_trace_id()
    return JSONResponse(
        status_code=400,
        content=format_error_response(
            code="VALIDATION_ERROR",
            message="Request validation failed. Verify request parameters and payload.",
            trace_id=trace_id,
            details=exc.errors(),
        ),
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle standard HTTP exceptions (e.g. 404, 405) with standardized envelope."""
    trace_id = getattr(request.state, "trace_id", None) or get_trace_id()

    code_map: dict[int, str] = {
        400: "BAD_REQUEST",
        401: "AUTHENTICATION_REQUIRED",
        403: "INSUFFICIENT_ROLE",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        429: "RATE_LIMITED",
        500: "INTERNAL_ERROR",
        503: "DEPENDENCY_UNAVAILABLE",
    }
    code = code_map.get(exc.status_code, f"HTTP_{exc.status_code}")
    headers = getattr(exc, "headers", None) or {}

    return JSONResponse(
        status_code=exc.status_code,
        content=format_error_response(
            code=code,
            message=str(exc.detail),
            trace_id=trace_id,
        ),
        headers=headers,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Mask unexpected internal server errors to prevent credential or stack trace leakage."""
    trace_id = getattr(request.state, "trace_id", None) or get_trace_id()
    logger.error(
        "Unhandled internal server exception: %s", exc, exc_info=True, extra={"trace_id": trace_id}
    )
    return JSONResponse(
        status_code=500,
        content=format_error_response(
            code="INTERNAL_ERROR",
            message="An unexpected internal server error occurred. Please contact support.",
            trace_id=trace_id,
        ),
    )


# ------------------------------------------------------------------------------
# API Routers Mount
# ------------------------------------------------------------------------------

app.include_router(health_router)
app.include_router(risk_router)
