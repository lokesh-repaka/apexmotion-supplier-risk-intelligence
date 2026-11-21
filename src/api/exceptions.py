"""API exception classes and error formatting for ApexMotion platform.

Standardizes all error envelopes according to CLAUDE.md Section 10:
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable message",
    "trace_id": "uuid-v4-string"
  }
}
"""

from typing import Any


class AppException(Exception):
    """Base application exception for standardized API error responses."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: Any = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


class ValidationException(AppException):
    """Raised when request payload fails schema validation."""

    def __init__(self, message: str, details: Any = None):
        super().__init__(
            code="VALIDATION_ERROR",
            message=message,
            status_code=400,
            details=details,
        )


class AuthenticationException(AppException):
    """Raised when authentication credentials are missing or invalid."""

    def __init__(self, message: str = "Authentication credentials required or invalid."):
        super().__init__(
            code="AUTHENTICATION_REQUIRED",
            message=message,
            status_code=401,
        )


class AuthorizationException(AppException):
    """Raised when authenticated user lacks sufficient RBAC role."""

    def __init__(self, message: str = "Insufficient permissions for this operation."):
        super().__init__(
            code="INSUFFICIENT_ROLE",
            message=message,
            status_code=403,
        )


class NotFoundException(AppException):
    """Raised when requested entity does not exist."""

    def __init__(self, message: str = "Requested resource not found."):
        super().__init__(
            code="NOT_FOUND",
            message=message,
            status_code=404,
        )


class ConflictException(AppException):
    """Raised when operation conflicts with current entity state."""

    def __init__(self, message: str = "Operation conflict occurred."):
        super().__init__(
            code="CONFLICT",
            message=message,
            status_code=409,
        )


def format_error_response(
    code: str,
    message: str,
    trace_id: str | None,
    details: Any = None,
) -> dict[str, Any]:
    """Format an error dictionary conforming to the standard ApexMotion API contract."""
    payload: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "trace_id": trace_id,
        }
    }
    if details is not None:
        payload["error"]["details"] = details
    return payload
