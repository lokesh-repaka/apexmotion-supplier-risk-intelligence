"""Unit tests for structured JSON logging in src/core/logging.py."""

import json
import logging
from io import StringIO


def test_json_formatter_standard_fields():
    """Verify that log records output valid JSON with required standard fields."""
    from src.core.logging import JSONFormatter, set_trace_id

    set_trace_id(None)
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    formatter = JSONFormatter(environment="test")
    handler.setFormatter(formatter)

    logger = logging.getLogger("test.json.fields")
    logger.setLevel(logging.INFO)
    logger.handlers = [handler]
    logger.propagate = False

    logger.info("Test message for schema verification")

    output = stream.getvalue().strip()
    assert output, "Log output should not be empty"

    data = json.loads(output)
    assert data["message"] == "Test message for schema verification"
    assert data["level"] == "INFO"
    assert data["logger"] == "test.json.fields"
    assert data["environment"] == "test"
    assert "timestamp" in data
    assert data["trace_id"] is None


def test_trace_id_propagation():
    """Verify trace_id contextvar is propagated to every log record."""
    from src.core.logging import JSONFormatter, bind_trace_id, get_trace_id, set_trace_id

    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONFormatter(environment="test"))

    logger = logging.getLogger("test.trace.propagation")
    logger.setLevel(logging.INFO)
    logger.handlers = [handler]
    logger.propagate = False

    # 1. Without trace_id
    set_trace_id(None)
    assert get_trace_id() is None
    logger.info("Before trace binding")
    first_record = json.loads(stream.getvalue().strip().split("\n")[-1])
    assert first_record["trace_id"] is None

    # 2. Context manager binding
    with bind_trace_id("tr-apex-nanocore-4402"):
        assert get_trace_id() == "tr-apex-nanocore-4402"
        logger.info("Inside traced scope")
        second_record = json.loads(stream.getvalue().strip().split("\n")[-1])
        assert second_record["trace_id"] == "tr-apex-nanocore-4402"

    # 3. Restored after context exit
    assert get_trace_id() is None
    logger.info("After traced scope exit")
    third_record = json.loads(stream.getvalue().strip().split("\n")[-1])
    assert third_record["trace_id"] is None


def test_pii_masking_in_message():
    """Verify that sensitive PII (emails, cards, phones, JWTs) are masked in log messages."""
    from src.core.logging import JSONFormatter

    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONFormatter(environment="test"))

    logger = logging.getLogger("test.pii.masking")
    logger.setLevel(logging.INFO)
    logger.handlers = [handler]
    logger.propagate = False

    raw_message = (
        "User supplier_contact@nanocore.com with phone +49-89-1234567 "
        "and card 4532-1234-5678-9010 provided auth token "
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-ID"
    )

    logger.info(raw_message)

    output = stream.getvalue().strip()
    data = json.loads(output)
    formatted_msg = data["message"]

    # Raw PII must not appear in output
    assert "supplier_contact@nanocore.com" not in formatted_msg
    assert "4532-1234-5678-9010" not in formatted_msg
    assert "+49-89-1234567" not in formatted_msg
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in formatted_msg

    # Redacted tags should appear
    assert "[REDACTED_EMAIL]" in formatted_msg
    assert "[REDACTED_CARD]" in formatted_msg
    assert "[REDACTED_PHONE]" in formatted_msg
    assert "[REDACTED_TOKEN]" in formatted_msg


def test_pii_masking_in_extra_fields():
    """Verify that PII inside extra kwargs is also sanitized."""
    from src.core.logging import JSONFormatter

    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONFormatter(environment="test"))

    logger = logging.getLogger("test.pii.extra")
    logger.setLevel(logging.INFO)
    logger.handlers = [handler]
    logger.propagate = False

    logger.info(
        "Disruption alert created",
        extra={
            "supplier_email": "director@semicon.com",
            "bank_account": "1234-5678-9012-3456",
            "component_sku": "SKU-MCU-4402",
        },
    )

    output = stream.getvalue().strip()
    data = json.loads(output)

    assert data["component_sku"] == "SKU-MCU-4402"
    assert data["supplier_email"] == "[REDACTED_EMAIL]"
    assert data["bank_account"] == "[REDACTED_CARD]"


def test_get_logger_factory():
    """Verify get_logger() provides a structured logger and handles exception tracebacks."""
    from src.core.logging import get_logger

    logger = get_logger("apexmotion.risk.calculator")
    assert logger.name == "apexmotion.risk.calculator"

    stream = StringIO()
    for h in logger.handlers:
        if isinstance(h, logging.StreamHandler):
            h.stream = stream

    try:
        raise ValueError("Simulated calculation anomaly")
    except ValueError:
        logger.error("Calculation failure occurred", exc_info=True)

    output = stream.getvalue().strip()
    if output:
        data = json.loads(output.split("\n")[-1])
        assert data["level"] == "ERROR"
        assert "Simulated calculation anomaly" in data.get("exception", "")


def test_sanitize_pii_collections():
    """Verify sanitize_pii cleans lists, tuples, and nested collections."""
    from src.core.logging import sanitize_pii

    emails = ["first@domain.com", "second@domain.com"]
    sanitized = sanitize_pii(emails)
    assert sanitized == ["[REDACTED_EMAIL]", "[REDACTED_EMAIL]"]

    tuple_emails = ("user@org.com", 12345)
    sanitized_tuple = sanitize_pii(tuple_emails)
    assert sanitized_tuple == ("[REDACTED_EMAIL]", 12345)


def test_setup_logging_json_and_text():
    """Verify setup_logging configures root logger in both JSON and text mode."""
    from src.core.logging import setup_logging

    # 1. JSON mode
    setup_logging(level="DEBUG", environment="staging", json_format=True)
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert len(root.handlers) == 1

    # 2. Text mode
    setup_logging(level="WARNING", json_format=False)
    assert root.level == logging.WARNING
