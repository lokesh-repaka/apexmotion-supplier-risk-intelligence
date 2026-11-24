"""Centralized API error handlers, exception standardization, and no-op mutation guards (P11-6).

Enforces:
- Strict error envelope standardization according to CLAUDE.md Section 10:
  ```json
  {
    "error": {
      "code": "ERROR_CODE",
      "message": "Human readable message",
      "trace_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
    }
  }
  ```
- Canonical mapping of HTTP status codes to standardized error codes:
  * 400: VALIDATION_ERROR / BAD_REQUEST
  * 401: AUTHENTICATION_REQUIRED
  * 403: INSUFFICIENT_ROLE / HITL_TOKEN_INVALID / HITL_TOKEN_EXPIRED
  * 404: NOT_FOUND
  * 405: METHOD_NOT_ALLOWED
  * 409: CONFLICT / NO_OP_MUTATION_REJECTED / TOKEN_REPLAY / HITL_TOKEN_REPLAYED
  * 422: VALIDATION_ERROR
  * 429: RATE_LIMITED
  * 500: INTERNAL_ERROR (all internal stack traces and credentials masked)
  * 503: DEPENDENCY_UNAVAILABLE
- No-op mutation guards (CLAUDE.md Section 20):
  * Rejects operations where `before_state == after_state` with 409 NO_OP_MUTATION_REJECTED.
- Token replay & cryptographic integrity guards:
  * Rejects used or duplicate tokens with 409 TOKEN_REPLAY.
  * Catches SQLAlchemy IntegrityError and maps to clean envelopes without SQL leaks.
"""

from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api.exceptions import (
    AppException,
    NoOpMutationException,
    format_error_response,
)
from src.core.hitl_tokens import (
    TokenExpiredError,
    TokenReplayDetectedError,
    TokenSignatureInvalidError,
)
from src.core.logging import get_logger, get_trace_id
from src.database.repositories.hitl_approval_repository import (
    TokenReplayError,
)
from src.services.hitl_service import (
    TokenReplayServiceError,
)

logger = get_logger("apexmotion.api.errors")


# ------------------------------------------------------------------------------
# 1. No-Op Mutation Guard Helper (CLAUDE.md Section 20)
# ------------------------------------------------------------------------------


def check_no_op_mutation(
    entity_id: Any,
    current_state: Any,
    target_state: Any,
    message: str | None = None,
) -> None:
    """Enforce the no-op mutation invariant (CLAUDE.md Section 20).

    Rejects requests where `before_state == after_state` to prevent spurious state
    transitions or empty audit log rows.

    Args:
        entity_id: Entity identifier being mutated.
        current_state: Current state value (before mutation).
        target_state: Target requested state value.
        message: Optional custom rejection message.

    Raises:
        NoOpMutationException: If current_state == target_state (HTTP 409 NO_OP_MUTATION_REJECTED).
    """
    if current_state == target_state:
        err_msg = (
            message
            or f"Operation on entity '{entity_id}' rejected: target state '{target_state}' "
            f"is identical to current state (no-op mutation)."
        )
        logger.warning(
            "No-op mutation rejected for entity '%s' (current: '%s', target: '%s')",
            entity_id,
            current_state,
            target_state,
            extra={"trace_id": get_trace_id() or "unknown-trace"},
        )
        raise NoOpMutationException(message=err_msg)


# ------------------------------------------------------------------------------
# 2. Exception Handlers
# ------------------------------------------------------------------------------


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


async def starlette_http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Handle standard HTTP exceptions (e.g. 404, 405, 429) with standardized envelope."""
    trace_id = getattr(request.state, "trace_id", None) or get_trace_id()

    code_map: dict[int, str] = {
        400: "BAD_REQUEST",
        401: "AUTHENTICATION_REQUIRED",
        403: "INSUFFICIENT_ROLE",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
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


async def token_replay_exception_handler(
    request: Request,
    exc: TokenReplayServiceError | TokenReplayError | TokenReplayDetectedError,
) -> JSONResponse:
    """Handle cryptographic token replay detection exceptions with 409 TOKEN_REPLAY envelope."""
    trace_id = getattr(request.state, "trace_id", None) or get_trace_id()
    logger.error(
        "Security incident: Cryptographic token replay intercepted: %s",
        exc,
        extra={"trace_id": trace_id},
    )
    return JSONResponse(
        status_code=409,
        content=format_error_response(
            code="TOKEN_REPLAY",
            message=f"Cryptographic token replay detected. {exc}",
            trace_id=trace_id,
        ),
    )


async def token_expired_exception_handler(
    request: Request,
    exc: TokenExpiredError,
) -> JSONResponse:
    """Handle cryptographic token expiration exceptions."""
    trace_id = getattr(request.state, "trace_id", None) or get_trace_id()
    return JSONResponse(
        status_code=400,
        content=format_error_response(
            code="TOKEN_EXPIRED",
            message=f"Token signature has expired: {exc}",
            trace_id=trace_id,
        ),
    )


async def token_signature_invalid_exception_handler(
    request: Request,
    exc: TokenSignatureInvalidError,
) -> JSONResponse:
    """Handle cryptographic token signature invalid exceptions."""
    trace_id = getattr(request.state, "trace_id", None) or get_trace_id()
    return JSONResponse(
        status_code=400,
        content=format_error_response(
            code="INVALID_TOKEN_SIGNATURE",
            message=f"Cryptographic signature verification failed: {exc}",
            trace_id=trace_id,
        ),
    )


async def integrity_error_handler(
    request: Request,
    exc: IntegrityError,
) -> JSONResponse:
    """Handle database constraint violations, masking raw SQL statements."""
    trace_id = getattr(request.state, "trace_id", None) or get_trace_id()
    err_str = str(exc).lower()

    if "token_hash" in err_str:
        code = "TOKEN_REPLAY"
        message = "Cryptographic token has already been used. Replay detected."
    else:
        code = "CONFLICT"
        message = "Database unique constraint or foreign key integrity violation occurred."

    logger.warning(
        "Database IntegrityError caught at API boundary: %s (trace_id: %s)",
        code,
        trace_id,
        extra={"trace_id": trace_id},
    )

    return JSONResponse(
        status_code=409,
        content=format_error_response(
            code=code,
            message=message,
            trace_id=trace_id,
        ),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Mask unexpected internal server errors to prevent credential or stack trace leakage."""
    trace_id = getattr(request.state, "trace_id", None) or get_trace_id()
    logger.error(
        "Unhandled internal server exception: %s",
        exc,
        exc_info=True,
        extra={"trace_id": trace_id},
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
# 3. Registration Function
# ------------------------------------------------------------------------------


def register_error_handlers(app: FastAPI) -> None:
    """Register all centralized exception handlers with the FastAPI application instance."""
    app.add_exception_handler(AppException, cast(Any, app_exception_handler))
    app.add_exception_handler(RequestValidationError, cast(Any, validation_exception_handler))
    app.add_exception_handler(StarletteHTTPException, cast(Any, starlette_http_exception_handler))
    app.add_exception_handler(TokenReplayError, cast(Any, token_replay_exception_handler))
    app.add_exception_handler(TokenReplayDetectedError, cast(Any, token_replay_exception_handler))
    app.add_exception_handler(TokenReplayServiceError, cast(Any, token_replay_exception_handler))
    app.add_exception_handler(TokenExpiredError, cast(Any, token_expired_exception_handler))
    app.add_exception_handler(
        TokenSignatureInvalidError, cast(Any, token_signature_invalid_exception_handler)
    )
    app.add_exception_handler(IntegrityError, cast(Any, integrity_error_handler))
    app.add_exception_handler(Exception, cast(Any, unhandled_exception_handler))
