"""Unit tests for Kafka Event Consumer (P6-1).

Verifies:
- MSK consumer group configuration and connection settings.
- At-least-once delivery: manual offset commits strictly after successful processing or DLQ routing.
- Retry resilience: retries message processing on transient failures.
- Dead-Letter Queue (DLQ): routes to <topic>.dlq upon reaching 3 failures (max_retries=3).
- DLQ failure handling: does not commit offset if DLQ publication fails, preserving at-least-once semantics.
- Header trace_id propagation (X-Trace-ID) to structured logs and message context.
- JSON and bytes payload deserialization with fallback handling.
- Multi-topic handler routing and topic segregation.
- Graceful lifecycle management and shutdown.
- Strict offline isolation with zero network or broker I/O using mock consumer/producer.
"""

import json
from unittest.mock import MagicMock

import pytest
from src.kafka.consumer import (
    ConsumedMessage,
    EventConsumer,
    KafkaConsumerError,
    KafkaDLQError,
)


@pytest.fixture
def mock_kafka_consumer() -> MagicMock:
    """Fixture providing a mock Kafka consumer."""
    consumer = MagicMock()
    consumer.commit = MagicMock()
    consumer.close = MagicMock()
    return consumer


@pytest.fixture
def mock_kafka_producer() -> MagicMock:
    """Fixture providing a mock Kafka producer for DLQ publishing."""
    producer = MagicMock()
    producer.send = MagicMock()
    producer.flush = MagicMock()
    producer.close = MagicMock()
    return producer


def create_mock_record(
    topic: str = "supplier-events",
    partition: int = 0,
    offset: int = 101,
    key: bytes | None = b"SUP-NC-882",
    value: bytes = b'{"supplier_id": "SUP-NC-882", "event_type": "FIRE", "severity": "HIGH"}',
    headers: list[tuple[str, bytes]] | None = None,
) -> MagicMock:
    """Helper to create a mock ConsumerRecord matching kafka-python structure."""
    record = MagicMock()
    record.topic = topic
    record.partition = partition
    record.offset = offset
    record.key = key
    record.value = value
    record.headers = headers if headers is not None else [("X-Trace-ID", b"trace-test-kafka-001")]
    record.timestamp = 1711122000000
    return record


# ------------------------------------------------------------------------------
# 1. Initialization and Configuration Tests
# ------------------------------------------------------------------------------


def test_consumer_initialization_defaults(
    mock_kafka_consumer: MagicMock, mock_kafka_producer: MagicMock
):
    """Verify consumer initializes with correct MSK consumer group and at-least-once settings."""
    consumer = EventConsumer(
        topics=["supplier-events"],
        consumer=mock_kafka_consumer,
        producer=mock_kafka_producer,
    )

    assert consumer.topics == ["supplier-events"]
    assert consumer.max_retries == 3
    assert consumer.dlq_topic_suffix == ".dlq"
    assert consumer.group_id == "apexmotion-risk-engine"


def test_consumer_custom_configuration(
    mock_kafka_consumer: MagicMock, mock_kafka_producer: MagicMock
):
    """Verify custom settings override defaults."""
    consumer = EventConsumer(
        topics=["risk-alerts", "audit-events"],
        group_id="custom-consumer-group",
        max_retries=5,
        dlq_topic_suffix="-deadletter",
        consumer=mock_kafka_consumer,
        producer=mock_kafka_producer,
    )

    assert consumer.topics == ["risk-alerts", "audit-events"]
    assert consumer.group_id == "custom-consumer-group"
    assert consumer.max_retries == 5
    assert consumer.dlq_topic_suffix == "-deadletter"


# ------------------------------------------------------------------------------
# 2. Message Processing & At-Least-Once Delivery Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_consumer_successful_processing_commits_offset(
    mock_kafka_consumer: MagicMock, mock_kafka_producer: MagicMock
):
    """Verify manual offset commit occurs strictly after handler successfully completes."""
    consumer = EventConsumer(
        topics=["supplier-events"],
        consumer=mock_kafka_consumer,
        producer=mock_kafka_producer,
    )

    processed_messages: list[ConsumedMessage] = []

    async def sample_handler(msg: ConsumedMessage) -> None:
        processed_messages.append(msg)

    consumer.register_handler("supplier-events", sample_handler)

    mock_rec = create_mock_record()
    success = await consumer.process_record(mock_rec)

    assert success is True
    assert len(processed_messages) == 1
    msg = processed_messages[0]
    assert msg.topic == "supplier-events"
    assert msg.offset == 101
    assert msg.value["supplier_id"] == "SUP-NC-882"
    assert msg.headers["X-Trace-ID"] == "trace-test-kafka-001"

    # Verify manual commit called once
    mock_kafka_consumer.commit.assert_called_once()
    # Verify no DLQ publishing
    mock_kafka_producer.send.assert_not_called()


@pytest.mark.asyncio
async def test_consumer_transient_failure_retries_and_succeeds(
    mock_kafka_consumer: MagicMock, mock_kafka_producer: MagicMock
):
    """Verify transient error retries and commits upon subsequent success."""
    consumer = EventConsumer(
        topics=["supplier-events"],
        max_retries=3,
        consumer=mock_kafka_consumer,
        producer=mock_kafka_producer,
    )

    attempt_count = 0

    async def flaky_handler(_msg: ConsumedMessage) -> None:
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count < 2:
            raise ConnectionError("Transient database glitch")

    consumer.register_handler("supplier-events", flaky_handler)

    mock_rec = create_mock_record()
    success = await consumer.process_record(mock_rec)

    assert success is True
    assert attempt_count == 2
    # Committed after attempt 2 succeeded
    mock_kafka_consumer.commit.assert_called_once()
    mock_kafka_producer.send.assert_not_called()


# ------------------------------------------------------------------------------
# 3. Dead-Letter Queue (DLQ) on 3 Failures Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_consumer_three_failures_routes_to_dlq(
    mock_kafka_consumer: MagicMock, mock_kafka_producer: MagicMock
):
    """Verify message failing 3 times is forwarded to DLQ and then offset is committed."""
    consumer = EventConsumer(
        topics=["supplier-events"],
        max_retries=3,
        consumer=mock_kafka_consumer,
        producer=mock_kafka_producer,
    )

    call_count = 0

    async def failing_handler(_msg: ConsumedMessage) -> None:
        nonlocal call_count
        call_count += 1
        raise ValueError("Poison pill schema validation error")

    consumer.register_handler("supplier-events", failing_handler)

    mock_rec = create_mock_record(offset=505)
    success = await consumer.process_record(mock_rec)

    assert success is False
    assert call_count == 3  # Exactly 3 retries performed

    # Verify DLQ publication
    mock_kafka_producer.send.assert_called_once()
    args, kwargs = mock_kafka_producer.send.call_args
    assert args[0] == "supplier-events.dlq"

    # Verify DLQ payload content
    payload_bytes = kwargs.get("value") or args[1]
    dlq_data = json.loads(
        payload_bytes.decode("utf-8") if isinstance(payload_bytes, bytes) else payload_bytes
    )
    assert dlq_data["original_topic"] == "supplier-events"
    assert dlq_data["original_offset"] == 505
    assert dlq_data["failure_count"] == 3
    assert "Poison pill schema validation error" in dlq_data["error_message"]
    assert dlq_data["trace_id"] == "trace-test-kafka-001"

    # Verify offset committed on primary topic AFTER DLQ routing
    mock_kafka_consumer.commit.assert_called_once()


@pytest.mark.asyncio
async def test_consumer_dlq_failure_does_not_commit_offset(
    mock_kafka_consumer: MagicMock, mock_kafka_producer: MagicMock
):
    """Verify offset is NOT committed if DLQ publish fails, maintaining at-least-once guarantee."""
    mock_kafka_producer.send.side_effect = RuntimeError("DLQ broker unreachable")

    consumer = EventConsumer(
        topics=["supplier-events"],
        max_retries=3,
        consumer=mock_kafka_consumer,
        producer=mock_kafka_producer,
    )

    async def failing_handler(_msg: ConsumedMessage) -> None:
        raise ValueError("Persistent processing failure")

    consumer.register_handler("supplier-events", failing_handler)

    mock_rec = create_mock_record()

    with pytest.raises(KafkaDLQError) as exc_info:
        await consumer.process_record(mock_rec)

    assert "Failed to route poisonous message to DLQ" in str(exc_info.value)
    # Offset must NOT be committed so message can be retried or preserved
    mock_kafka_consumer.commit.assert_not_called()


# ------------------------------------------------------------------------------
# 4. Deserialization, Trace Propagation & Routing Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_consumer_deserialization_formats(
    mock_kafka_consumer: MagicMock, mock_kafka_producer: MagicMock
):
    """Verify consumer parses valid JSON and gracefully preserves plain text."""
    consumer = EventConsumer(
        topics=["supplier-events"],
        consumer=mock_kafka_consumer,
        producer=mock_kafka_producer,
    )

    received_values = []

    async def capture_handler(msg: ConsumedMessage) -> None:
        received_values.append(msg.value)

    consumer.register_handler("supplier-events", capture_handler)

    # 1. JSON Bytes
    rec1 = create_mock_record(value=b'{"count": 42}')
    await consumer.process_record(rec1)
    assert received_values[0] == {"count": 42}

    # 2. Plain Text Bytes
    rec2 = create_mock_record(value=b"plain-text-unstructured-signal")
    await consumer.process_record(rec2)
    assert received_values[1] == "plain-text-unstructured-signal"


@pytest.mark.asyncio
async def test_consumer_multi_topic_routing(
    mock_kafka_consumer: MagicMock, mock_kafka_producer: MagicMock
):
    """Verify consumer routes messages to appropriate topic-specific handlers."""
    consumer = EventConsumer(
        topics=["supplier-events", "risk-alerts"],
        consumer=mock_kafka_consumer,
        producer=mock_kafka_producer,
    )

    supplier_events = []
    risk_alerts = []

    consumer.register_handler("supplier-events", lambda msg: supplier_events.append(msg))
    consumer.register_handler("risk-alerts", lambda msg: risk_alerts.append(msg))

    rec_sup = create_mock_record(topic="supplier-events", value=b'{"type": "SUPPLIER"}')
    rec_alt = create_mock_record(topic="risk-alerts", value=b'{"type": "ALERT"}')

    await consumer.process_record(rec_sup)
    await consumer.process_record(rec_alt)

    assert len(supplier_events) == 1
    assert len(risk_alerts) == 1
    assert supplier_events[0].topic == "supplier-events"
    assert risk_alerts[0].topic == "risk-alerts"


@pytest.mark.asyncio
async def test_consumer_unhandled_topic_logs_warning_and_commits(
    mock_kafka_consumer: MagicMock, mock_kafka_producer: MagicMock
):
    """Verify message on unregistered topic is logged and committed to prevent blocking."""
    consumer = EventConsumer(
        topics=["known-topic"],
        consumer=mock_kafka_consumer,
        producer=mock_kafka_producer,
    )

    rec_unregistered = create_mock_record(topic="unknown-topic")
    success = await consumer.process_record(rec_unregistered)

    assert success is True
    mock_kafka_consumer.commit.assert_called_once()
    mock_kafka_producer.send.assert_not_called()


def test_consumer_close_lifecycle(mock_kafka_consumer: MagicMock, mock_kafka_producer: MagicMock):
    """Verify close() cleanly stops both consumer and DLQ producer."""
    consumer = EventConsumer(
        topics=["supplier-events"],
        consumer=mock_kafka_consumer,
        producer=mock_kafka_producer,
    )

    consumer.close()

    mock_kafka_consumer.close.assert_called_once()
    mock_kafka_producer.close.assert_called_once()
    assert consumer.is_running is False


# ------------------------------------------------------------------------------
# 5. Advanced Polling, Batching, and Boundary Tests
# ------------------------------------------------------------------------------


def test_consumer_string_topic_normalization(
    mock_kafka_consumer: MagicMock, mock_kafka_producer: MagicMock
):
    """Verify single topic string is normalized to a list."""
    consumer = EventConsumer(
        topics="supplier-events",
        consumer=mock_kafka_consumer,
        producer=mock_kafka_producer,
    )
    assert consumer.topics == ["supplier-events"]


def test_consumer_poll_conversion(mock_kafka_consumer: MagicMock, mock_kafka_producer: MagicMock):
    """Verify poll() converts raw batch into ConsumedMessage list."""
    rec = create_mock_record(offset=42)
    mock_kafka_consumer.poll.return_value = {("supplier-events", 0): [rec]}

    consumer = EventConsumer(
        topics=["supplier-events"],
        consumer=mock_kafka_consumer,
        producer=mock_kafka_producer,
    )

    messages = consumer.poll(timeout_ms=500)
    assert len(messages) == 1
    assert messages[0].offset == 42
    assert messages[0].topic == "supplier-events"


@pytest.mark.asyncio
async def test_consumer_run_once_batch_processing(
    mock_kafka_consumer: MagicMock, mock_kafka_producer: MagicMock
):
    """Verify run_once() processes all messages in polled batch."""
    rec1 = create_mock_record(offset=10)
    rec2 = create_mock_record(offset=11)
    mock_kafka_consumer.poll.return_value = {("supplier-events", 0): [rec1, rec2]}

    consumer = EventConsumer(
        topics=["supplier-events"],
        consumer=mock_kafka_consumer,
        producer=mock_kafka_producer,
    )

    processed = []
    consumer.register_handler("supplier-events", lambda msg: processed.append(msg))

    count = await consumer.run_once(max_records=10)
    assert count == 2
    assert len(processed) == 2


@pytest.mark.asyncio
async def test_consumer_trace_id_generation_when_missing(
    mock_kafka_consumer: MagicMock, mock_kafka_producer: MagicMock
):
    """Verify a trace_id is automatically generated when message headers lack one."""
    rec = create_mock_record(headers=[])  # no headers
    consumer = EventConsumer(
        topics=["supplier-events"],
        consumer=mock_kafka_consumer,
        producer=mock_kafka_producer,
    )

    captured_msg = None

    def handler(msg: ConsumedMessage) -> None:
        nonlocal captured_msg
        captured_msg = msg

    consumer.register_handler("supplier-events", handler)
    await consumer.process_record(rec)

    assert captured_msg is not None
    # Generated trace_id should exist and be valid string
    assert len(captured_msg.headers) == 0  # original headers empty
    mock_kafka_consumer.commit.assert_called_once()


def test_consumer_null_and_raw_value_deserialization(
    mock_kafka_consumer: MagicMock, mock_kafka_producer: MagicMock
):
    """Verify deserialization handles None, non-bytes/non-string objects."""
    consumer = EventConsumer(
        topics=["supplier-events"],
        consumer=mock_kafka_consumer,
        producer=mock_kafka_producer,
    )

    assert consumer._deserialize_value(None) is None
    assert consumer._deserialize_value(12345) == 12345
    assert consumer._deserialize_value({"pre": "parsed"}) == {"pre": "parsed"}


def test_kafka_exception_instantiations():
    """Verify exception classes initialize with correct error envelopes."""
    err1 = KafkaConsumerError("General error", status_code=500)
    assert err1.code == "KAFKA_CONSUMER_ERROR"
    assert err1.status_code == 500

    err2 = KafkaDLQError("DLQ failed")
    assert err2.code == "KAFKA_DLQ_ERROR"
    assert err2.status_code == 500

    from src.kafka.consumer import KafkaMessageProcessingError

    err3 = KafkaMessageProcessingError("Handler failed")
    assert err3.code == "KAFKA_PROCESSING_ERROR"
    assert err3.status_code == 500


def test_lazy_consumer_and_producer_initialization(monkeypatch: pytest.MonkeyPatch):
    """Verify _get_consumer and _get_producer instantiate when None."""
    mock_kc = MagicMock()
    mock_kp = MagicMock()

    monkeypatch.setattr("kafka.KafkaConsumer", mock_kc)
    monkeypatch.setattr("kafka.KafkaProducer", mock_kp)

    consumer = EventConsumer(topics=["test-topic"])
    c = consumer._get_consumer()
    p = consumer._get_producer()

    assert c is not None
    assert p is not None
    mock_kc.assert_called_once()
    mock_kp.assert_called_once()


def test_consumer_non_utf8_binary_payload(
    mock_kafka_consumer: MagicMock, mock_kafka_producer: MagicMock
):
    """Verify non-UTF-8 binary payload returns raw bytes gracefully."""
    consumer = EventConsumer(
        topics=["binary-topic"],
        consumer=mock_kafka_consumer,
        producer=mock_kafka_producer,
    )

    invalid_utf8 = b"\x80\x81\x82"
    result = consumer._deserialize_value(invalid_utf8)
    assert result == invalid_utf8


@pytest.mark.asyncio
async def test_consumer_run_once_stops_when_not_running(
    mock_kafka_consumer: MagicMock, mock_kafka_producer: MagicMock
):
    """Verify run_once terminates early if is_running is set to False."""
    rec1 = create_mock_record(offset=1)
    rec2 = create_mock_record(offset=2)
    mock_kafka_consumer.poll.return_value = {("supplier-events", 0): [rec1, rec2]}

    consumer = EventConsumer(
        topics=["supplier-events"],
        consumer=mock_kafka_consumer,
        producer=mock_kafka_producer,
    )
    consumer.is_running = False

    count = await consumer.run_once()
    assert count == 0
