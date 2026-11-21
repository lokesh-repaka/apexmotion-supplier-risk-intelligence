"""Structured JSON logging module for ApexMotion Supplier Risk Intelligence Platform.

Enforces:
- trace_id on every log record via contextvars
- Zero PII in raw logs (automatic redaction of emails, cards, phones, and tokens)
- Standardized ISO-8601 UTC timestamps and structured JSON output
"""

import json
import logging
import re
import sys
import traceback
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# ContextVar storing the current distributed trace_id
_TRACE_ID_VAR: ContextVar[str | None] = ContextVar("trace_id", default=None)

# ------------------------------------------------------------------------------
# PII Sanitization Patterns
# ------------------------------------------------------------------------------
_EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_CARD_REGEX = re.compile(r"\b(?:\d{4}[- ]?){3}\d{4}\b")
_PHONE_REGEX = re.compile(r"(?:\+\d{1,3}[- ]?)?\(?\d{2,4}\)?[- ]?\d{3,4}[- ]?\d{3,4}\b")
_BEARER_TOKEN_REGEX = re.compile(
    r"(Bearer\s+)[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+\.?[A-Za-z0-9\-_.+/=]*",
    re.IGNORECASE,
)


def get_trace_id() -> str | None:
    """Return the active trace_id in current context."""
    return _TRACE_ID_VAR.get()


def set_trace_id(trace_id: str | None) -> None:
    """Explicitly set the active trace_id in current context."""
    _TRACE_ID_VAR.set(trace_id)


@contextmanager
def bind_trace_id(trace_id: str | None) -> Generator[str | None, None, None]:
    """Context manager binding a trace_id to the execution scope and restoring upon exit."""
    token = _TRACE_ID_VAR.set(trace_id)
    try:
        yield trace_id
    finally:
        _TRACE_ID_VAR.reset(token)


def sanitize_pii(value: Any) -> Any:
    """Recursively redact PII (emails, cards, phones, bearer tokens) from log inputs."""
    if isinstance(value, str):
        sanitized = _EMAIL_REGEX.sub("[REDACTED_EMAIL]", value)
        sanitized = _CARD_REGEX.sub("[REDACTED_CARD]", sanitized)
        sanitized = _PHONE_REGEX.sub("[REDACTED_PHONE]", sanitized)
        sanitized = _BEARER_TOKEN_REGEX.sub(r"\1[REDACTED_TOKEN]", sanitized)
        return sanitized
    elif isinstance(value, Mapping):
        return {k: sanitize_pii(v) for k, v in value.items()}
    elif isinstance(value, list | tuple | set):
        sanitized_items = [sanitize_pii(item) for item in value]
        return type(value)(sanitized_items)
    return value


class JSONFormatter(logging.Formatter):
    """Formats log records as structured, single-line JSON entries."""

    # Standard attributes present on logging.LogRecord to exclude from 'extra'
    _STANDARD_RECORD_ATTRS = frozenset(
        {
            "args",
            "asctime",
            "created",
            "exc_info",
            "exc_text",
            "filename",
            "funcName",
            "id",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "message",
            "msg",
            "name",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "thread",
            "threadName",
            "trace_id",
        }
    )

    def __init__(self, environment: str = "production"):
        super().__init__()
        self.environment = environment

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record into a single JSON line."""
        # Get raw message and format with args if needed
        record_message = record.getMessage()
        sanitized_message = sanitize_pii(record_message)

        # Resolve trace_id (contextvar first, then record attribute)
        trace_id = get_trace_id() or getattr(record, "trace_id", None)

        log_data: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": sanitized_message,
            "trace_id": trace_id,
            "environment": self.environment,
        }

        # Extract and sanitize custom 'extra' kwargs passed to logger
        for key, val in record.__dict__.items():
            if key not in self._STANDARD_RECORD_ATTRS and not key.startswith("_"):
                log_data[key] = sanitize_pii(val)

        # Capture formatted exception tracebacks
        if record.exc_info:
            log_data["exception"] = "".join(traceback.format_exception(*record.exc_info)).strip()

        return json.dumps(log_data, default=str)


def get_logger(name: str = "apexmotion") -> logging.Logger:
    """Factory creating or returning a configured structured JSON logger."""
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False

    return logger


def setup_logging(
    level: str = "INFO", environment: str = "production", json_format: bool = True
) -> None:
    """Initialize global root logging configuration."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level.upper())

    # Clear existing handlers
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    if json_format:
        handler.setFormatter(JSONFormatter(environment=environment))
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] [%(name)s] [trace_id=%(trace_id)s] %(message)s"
            )
        )

    root_logger.addHandler(handler)
