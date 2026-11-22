"""Unit tests for Kafka Event Producer (src/kafka/producer.py).

Verifies:
- Producer configuration defaults matching MSK settings (acks='all', retries, compression).
- Dedicated publishing methods for core internal topics:
  * risk-alerts (settings.KAFKA_TOPIC_RISK_ALERTS)
  * hitl-required (settings.KAFKA_TOPIC_HITL_REQUIRED)
  * audit-events (settings.KAFKA_TOPIC_AUDIT_EVENTS)
- Serialization of complex types (Decimal monetary precision, datetime, UUID, dataclass, Pydantic).
- At-least-once broker acknowledgment semantics and synchronous/asynchronous publishing.
- Distributed trace context propagation in Kafka headers.
- Comprehensive exception handling (timeout -> 504, unavailable -> 503, serialization -> 400).
- Lifecycle management (flush, close, sync/async context managers).
- 100% offline test isolation with zero live broker dependencies.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel
from src.core.config import get_settings
from src.core.logging import bind_trace_id
from src.kafka.producer import (
    EventProducer,
    KafkaBrokerUnavailableError,
    KafkaProducerError,
    KafkaPublishTimeoutError,
    KafkaSerializationError,
    PublishedRecord,
    get_event_producer,
    serialize_payload,
)


class SampleRiskModel(BaseModel):
    alert_id: str
    supplier_id: str
    sku: str
    days_of_cover: Decimal
    financial_exposure: Decimal


@dataclass
class SampleHITLData:
    action_id: str
    amount_usd: Decimal
    spend_tier: str


def create_mock_metadata(topic="test-topic", partition=0, offset=100, timestamp=1700000000000):
    metadata = MagicMock()
    metadata.topic = topic
    metadata.partition = partition
    metadata.offset = offset
    metadata.timestamp = timestamp
    return metadata


def create_mock_producer():
    producer = MagicMock()
    future = MagicMock()
    future.get.return_value = create_mock_metadata()
    producer.send.return_value = future
    return producer


# ==============================================================================
# Configuration & Initialization Tests
# ==============================================================================


def test_producer_initialization_defaults():
    """Verify EventProducer initializes with defaults from project settings."""
    settings = get_settings()
    mock_p = create_mock_producer()
    producer = EventProducer(producer=mock_p)

    assert producer.bootstrap_servers == settings.KAFKA_BOOTSTRAP_SERVERS
    assert producer.client_id == "apexmotion-event-producer"
    assert producer.acks == "all"
    assert producer.retries == 3
    assert producer.compression_type == "gzip"
    assert producer.request_timeout_ms == 10000
    assert producer.max_block_ms == 10000
    assert not producer._is_closed


def test_producer_custom_configuration():
    """Verify custom settings override defaults."""
    mock_p = create_mock_producer()
    producer = EventProducer(
        bootstrap_servers="kafka.internal:9092",
        client_id="custom-producer-1",
        acks=1,
        retries=5,
        compression_type="lz4",
        request_timeout_ms=5000,
        max_block_ms=3000,
        producer=mock_p,
    )

    assert producer.bootstrap_servers == "kafka.internal:9092"
    assert producer.client_id == "custom-producer-1"
    assert producer.acks == 1
    assert producer.retries == 5
    assert producer.compression_type == "lz4"
    assert producer.request_timeout_ms == 5000
    assert producer.max_block_ms == 3000


# ==============================================================================
# Publishing Logic & Topic Routing Tests
# ==============================================================================


def test_publish_generic_event_success():
    """Verify synchronous publish sends serialized payload, headers, and returns PublishedRecord."""
    mock_p = create_mock_producer()
    mock_p.send.return_value.get.return_value = create_mock_metadata(
        topic="custom-topic", partition=1, offset=42, timestamp=1700000050000
    )
    producer = EventProducer(producer=mock_p)

    payload = {"status": "ACTIVE", "code": 200}
    record = producer.publish(
        topic="custom-topic",
        value=payload,
        key="key-01",
        trace_id="trc-test-123",
    )

    assert isinstance(record, PublishedRecord)
    assert record.topic == "custom-topic"
    assert record.partition == 1
    assert record.offset == 42
    assert record.key == "key-01"
    assert record.trace_id == "trc-test-123"

    # Verify send call arguments
    mock_p.send.assert_called_once()
    call_args = mock_p.send.call_args
    assert call_args[0][0] == "custom-topic"
    assert json.loads(call_args[1]["value"].decode("utf-8")) == payload
    assert call_args[1]["key"] == b"key-01"

    # Verify headers contain trace ID and client ID
    headers = {k: v.decode("utf-8") for k, v in call_args[1]["headers"]}
    assert headers["X-Trace-ID"] == "trc-test-123"
    assert headers["X-Client-ID"] == "apexmotion-event-producer"
    assert "X-Timestamp" in headers


def test_publish_risk_alert_topic_and_key():
    """Verify publish_risk_alert routes to risk-alerts topic and extracts supplier_id as key."""
    settings = get_settings()
    mock_p = create_mock_producer()
    producer = EventProducer(producer=mock_p)

    alert_data = {
        "alert_id": "ALT-2026-001",
        "supplier_id": "SUP-NC-882",
        "sku": "CMP-MCU-X91",
        "financial_exposure": Decimal("2448105.00"),
    }

    record = producer.publish_risk_alert(alert_data=alert_data, trace_id="trc-alert-1")

    assert record.topic == settings.KAFKA_TOPIC_RISK_ALERTS
    assert record.key == "SUP-NC-882"
    assert record.trace_id == "trc-alert-1"

    call_args = mock_p.send.call_args
    assert call_args[0][0] == settings.KAFKA_TOPIC_RISK_ALERTS
    assert call_args[1]["key"] == b"SUP-NC-882"


def test_publish_hitl_request_topic_and_key():
    """Verify publish_hitl_request routes to hitl-required topic and extracts action_id as key."""
    settings = get_settings()
    mock_p = create_mock_producer()
    producer = EventProducer(producer=mock_p)

    hitl_data = {
        "action_id": "ACT-999",
        "alert_id": "ALT-001",
        "amount_usd": Decimal("150000.00"),
        "spend_tier": "DUAL_VP",
    }

    record = producer.publish_hitl_request(hitl_data=hitl_data)

    assert record.topic == settings.KAFKA_TOPIC_HITL_REQUIRED
    assert record.key == "ACT-999"

    call_args = mock_p.send.call_args
    assert call_args[0][0] == settings.KAFKA_TOPIC_HITL_REQUIRED
    assert call_args[1]["key"] == b"ACT-999"


def test_publish_audit_event_topic_and_key():
    """Verify publish_audit_event routes to audit-events topic and extracts entity_id as key."""
    settings = get_settings()
    mock_p = create_mock_producer()
    producer = EventProducer(producer=mock_p)

    audit_data = {
        "entity_type": "supplier",
        "entity_id": "SUP-NC-882",
        "action": "RISK_CALCULATION",
        "actor_id": "sys-engine",
    }

    record = producer.publish_audit_event(audit_data=audit_data)

    assert record.topic == settings.KAFKA_TOPIC_AUDIT_EVENTS
    assert record.key == "SUP-NC-882"

    call_args = mock_p.send.call_args
    assert call_args[0][0] == settings.KAFKA_TOPIC_AUDIT_EVENTS
    assert call_args[1]["key"] == b"SUP-NC-882"


def test_publish_explicit_key_overrides_extracted_key():
    """Verify caller-provided key overrides payload-extracted default key."""
    mock_p = create_mock_producer()
    producer = EventProducer(producer=mock_p)

    alert_data = {"supplier_id": "SUP-NC-882", "alert_id": "ALT-001"}
    record = producer.publish_risk_alert(alert_data=alert_data, key="EXPLICIT-PARTITION-KEY")

    assert record.key == "EXPLICIT-PARTITION-KEY"
    call_args = mock_p.send.call_args
    assert call_args[1]["key"] == b"EXPLICIT-PARTITION-KEY"


# ==============================================================================
# Async & Batch Publishing Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_publish_async():
    """Verify asynchronous publish methods execute non-blockingly."""
    mock_p = create_mock_producer()
    producer = EventProducer(producer=mock_p)

    # Test generic async
    rec1 = await producer.publish_async(topic="async-topic", value={"test": 1}, key="k1")
    assert rec1.topic == "async-topic"

    # Test risk alert async
    rec2 = await producer.publish_risk_alert_async(
        alert_data={"supplier_id": "SUP-1", "score": 0.9}
    )
    assert rec2.topic == get_settings().KAFKA_TOPIC_RISK_ALERTS

    # Test hitl async
    rec3 = await producer.publish_hitl_request_async(
        hitl_data={"action_id": "ACT-1", "amount": 20000}
    )
    assert rec3.topic == get_settings().KAFKA_TOPIC_HITL_REQUIRED

    # Test audit async
    rec4 = await producer.publish_audit_event_async(
        audit_data={"entity_id": "ENT-1", "action": "CREATE"}
    )
    assert rec4.topic == get_settings().KAFKA_TOPIC_AUDIT_EVENTS


def test_publish_batch():
    """Verify batch publishing sends multiple messages and returns list of PublishedRecord."""
    mock_p = create_mock_producer()
    producer = EventProducer(producer=mock_p)

    records = [
        {"topic": "topic-1", "value": {"item": 1}, "key": "k1"},
        {"topic": "topic-2", "value": {"item": 2}, "key": "k2"},
        {"topic": "topic-1", "value": {"item": 3}, "key": "k3"},
    ]

    results = producer.publish_batch(records)
    assert len(results) == 3
    assert results[0].key == "k1"
    assert results[1].key == "k2"
    assert results[2].key == "k3"
    assert mock_p.send.call_count == 3


@pytest.mark.asyncio
async def test_publish_batch_async():
    """Verify async batch publishing works properly."""
    mock_p = create_mock_producer()
    producer = EventProducer(producer=mock_p)

    records = [
        {"topic": "topic-a", "value": {"val": "a"}, "key": "ka"},
        {"topic": "topic-b", "value": {"val": "b"}, "key": "kb"},
    ]

    results = await producer.publish_batch_async(records)
    assert len(results) == 2
    assert results[0].key == "ka"
    assert results[1].key == "kb"


# ==============================================================================
# Serialization & Precision Tests (BR-RULE-001)
# ==============================================================================


def test_serialization_decimal_precision():
    """Verify Decimal monetary values serialize without IEEE 754 precision loss."""
    payload = {
        "shortage_volume": Decimal("24420.00"),
        "financial_exposure": Decimal("2448105.00"),
        "unit_cost": Decimal("100.25"),
    }

    serialized = serialize_payload(payload)
    data = json.loads(serialized.decode("utf-8"))

    assert data["shortage_volume"] == "24420.00"
    assert data["financial_exposure"] == "2448105.00"
    assert data["unit_cost"] == "100.25"


def test_serialization_datetime_and_uuid():
    """Verify datetime, date, and UUID serialize cleanly to ISO-8601 strings."""
    now = datetime(2026, 11, 22, 12, 0, 0, tzinfo=UTC)
    uid = uuid.uuid4()

    payload = {
        "timestamp": now,
        "uuid": uid,
    }

    serialized = serialize_payload(payload)
    data = json.loads(serialized.decode("utf-8"))

    assert data["timestamp"] == "2026-11-22T12:00:00+00:00"
    assert data["uuid"] == str(uid)


def test_serialization_pydantic_and_dataclass():
    """Verify Pydantic models and dataclasses serialize cleanly to JSON."""
    pydantic_model = SampleRiskModel(
        alert_id="ALT-100",
        supplier_id="SUP-NC-882",
        sku="CMP-MCU-X91",
        days_of_cover=Decimal("7.68"),
        financial_exposure=Decimal("2448105.00"),
    )

    dataclass_model = SampleHITLData(
        action_id="ACT-500",
        amount_usd=Decimal("50000.00"),
        spend_tier="PROC_DIRECTOR",
    )

    serialized_pydantic = serialize_payload(pydantic_model)
    data_pydantic = json.loads(serialized_pydantic.decode("utf-8"))
    assert data_pydantic["alert_id"] == "ALT-100"
    assert data_pydantic["days_of_cover"] == "7.68"

    serialized_dataclass = serialize_payload(dataclass_model)
    data_dataclass = json.loads(serialized_dataclass.decode("utf-8"))
    assert data_dataclass["action_id"] == "ACT-500"
    assert data_dataclass["amount_usd"] == "50000.00"


def test_serialization_raw_bytes_and_string():
    """Verify raw bytes and string payloads pass through without distortion."""
    raw_bytes = b"binary-data-stream"
    assert serialize_payload(raw_bytes) == raw_bytes

    raw_str = "simple string message"
    assert serialize_payload(raw_str) == b"simple string message"

    assert serialize_payload(None) == b""


def test_serialization_error_raises_kafka_serialization_error():
    """Verify non-serializable object raises KafkaSerializationError with HTTP 400."""

    class UnserializableObject:
        __slots__ = ()

    with pytest.raises(KafkaSerializationError) as exc_info:
        serialize_payload({"bad": UnserializableObject()})

    assert exc_info.value.status_code == 400
    assert "Failed to serialize payload" in exc_info.value.message


# ==============================================================================
# Error Handling & Broker Failure Tests
# ==============================================================================


def test_publish_timeout_raises_kafka_publish_timeout_error():
    """Verify broker timeout during future.get() raises KafkaPublishTimeoutError with HTTP 504."""
    from kafka.errors import KafkaTimeoutError

    mock_p = create_mock_producer()
    mock_p.send.return_value.get.side_effect = KafkaTimeoutError(
        "Broker request timed out after 10000ms"
    )
    producer = EventProducer(producer=mock_p)

    with pytest.raises(KafkaPublishTimeoutError) as exc_info:
        producer.publish(topic="risk-alerts", value={"test": 1})

    assert exc_info.value.status_code == 504
    assert "Timed out waiting for broker acknowledgment" in exc_info.value.message


def test_broker_unavailable_raises_kafka_broker_unavailable_error():
    """Verify BrokerNotAvailableError raises KafkaBrokerUnavailableError with HTTP 503."""
    from kafka.errors import BrokerNotAvailableError

    mock_p = create_mock_producer()
    mock_p.send.return_value.get.side_effect = BrokerNotAvailableError("Node 1 disconnected")
    producer = EventProducer(producer=mock_p)

    with pytest.raises(KafkaBrokerUnavailableError) as exc_info:
        producer.publish(topic="risk-alerts", value={"test": 1})

    assert exc_info.value.status_code == 503
    assert "Kafka broker unavailable" in exc_info.value.message


def test_generic_kafka_error_raises_kafka_producer_error():
    """Verify general KafkaError raises KafkaProducerError with HTTP 500."""
    from kafka.errors import KafkaError

    mock_p = create_mock_producer()
    mock_p.send.return_value.get.side_effect = KafkaError("Network partition detected")
    producer = EventProducer(producer=mock_p)

    with pytest.raises(KafkaProducerError) as exc_info:
        producer.publish(topic="risk-alerts", value={"test": 1})

    assert exc_info.value.status_code == 500
    assert "Kafka error publishing to topic" in exc_info.value.message


def test_producer_closed_state_denies_publish():
    """Verify publishing on closed producer raises KafkaProducerError."""
    mock_p = create_mock_producer()
    producer = EventProducer(producer=mock_p)
    producer.close()

    with pytest.raises(KafkaProducerError) as exc_info:
        producer.publish(topic="risk-alerts", value={"test": 1})

    assert "Cannot publish on a closed producer" in exc_info.value.message


# ==============================================================================
# Lifecycle & Context Manager Tests
# ==============================================================================


def test_flush_and_close_lifecycle():
    """Verify flush and close delegate to underlying producer and update state."""
    mock_p = create_mock_producer()
    producer = EventProducer(producer=mock_p)

    producer.flush(timeout=2.0)
    mock_p.flush.assert_called_once_with(timeout=2.0)

    producer.close(timeout=5.0)
    mock_p.close.assert_called_once_with(timeout=5.0)
    assert producer._is_closed

    # Second close should be idempotent
    producer.close()
    assert mock_p.close.call_count == 1


def test_context_manager_sync_and_async():
    """Verify sync and async context managers cleanly flush and close on exit."""
    mock_p1 = create_mock_producer()
    with EventProducer(producer=mock_p1) as p1:
        assert not p1._is_closed

    mock_p1.flush.assert_called_once()
    mock_p1.close.assert_called_once()
    assert p1._is_closed


@pytest.mark.asyncio
async def test_context_manager_async():
    """Verify async context manager cleanly flushes and closes on exit."""
    mock_p2 = create_mock_producer()
    async with EventProducer(producer=mock_p2) as p2:
        assert not p2._is_closed

    mock_p2.flush.assert_called_once()
    mock_p2.close.assert_called_once()
    assert p2._is_closed


def test_trace_id_propagation_and_generation():
    """Verify active context trace_id is propagated, or generated when missing."""
    mock_p = create_mock_producer()
    producer = EventProducer(producer=mock_p)

    # 1. With active context trace_id
    with bind_trace_id("trc-context-bound-999"):
        rec1 = producer.publish(topic="test-topic", value={"test": 1})
        assert rec1.trace_id == "trc-context-bound-999"

    # 2. Without active context trace_id (should auto-generate)
    with bind_trace_id(None):
        rec2 = producer.publish(topic="test-topic", value={"test": 2})
        assert rec2.trace_id is not None
        assert len(rec2.trace_id) == 32  # hex uuid length


def test_get_event_producer_singleton():
    """Verify get_event_producer returns a valid reusable producer instance."""
    with patch("kafka.KafkaProducer", return_value=create_mock_producer()):
        producer = get_event_producer()
        assert isinstance(producer, EventProducer)


def test_lazy_producer_initialization():
    """Verify _get_producer lazily instantiates KafkaProducer when None."""
    with patch("kafka.KafkaProducer") as mock_kafka_cls:
        mock_instance = create_mock_producer()
        mock_kafka_cls.return_value = mock_instance

        producer = EventProducer(producer=None)
        assert producer._producer is None

        p = producer._get_producer()
        assert p == mock_instance
        mock_kafka_cls.assert_called_once()


def test_serialization_legacy_dict_method():
    """Verify objects exposing .dict() method serialize properly."""

    class LegacyObject:
        def dict(self):
            return {"legacy_field": "legacy_val"}

    serialized = serialize_payload(LegacyObject())
    assert json.loads(serialized.decode("utf-8")) == {"legacy_field": "legacy_val"}


def test_format_headers_with_tuples_and_existing_keys():
    """Verify headers passed as list of tuples with existing trace/client headers are respected."""
    mock_p = create_mock_producer()
    producer = EventProducer(producer=mock_p)

    custom_headers = [
        ("X-Trace-ID", "pre-existing-trace"),
        ("X-Client-ID", "pre-existing-client"),
        ("Custom-Key", b"custom-val"),
    ]

    rec = producer.publish(
        topic="test-topic",
        value={"data": 1},
        headers=custom_headers,
        key=b"byte-key-direct",
    )

    assert rec.key == "byte-key-direct"
    call_args = mock_p.send.call_args
    headers = dict(call_args[1]["headers"])
    assert headers["X-Trace-ID"] == b"pre-existing-trace"
    assert headers["X-Client-ID"] == b"pre-existing-client"
    assert headers["Custom-Key"] == b"custom-val"


def test_extract_key_from_object_and_unmatched():
    """Verify key extraction from object attributes and graceful None fallback when unmatched."""
    mock_p = create_mock_producer()
    producer = EventProducer(producer=mock_p)

    class ObjectWithAttributes:
        def __init__(self):
            self.action_id = "ACT-OBJ-123"

    rec1 = producer.publish_hitl_request(hitl_data=ObjectWithAttributes())
    assert rec1.key == "ACT-OBJ-123"

    # Unmatched candidate fields
    rec2 = producer.publish_risk_alert(alert_data={"non_candidate": 123})
    assert rec2.key is None

    # Payload with None value
    rec3 = producer.publish_risk_alert(alert_data=None)
    assert rec3.key is None


def test_publish_unexpected_exception_wrapped():
    """Verify unexpected non-Kafka exception is wrapped in KafkaProducerError."""
    mock_p = create_mock_producer()
    mock_p.send.side_effect = RuntimeError("Catastrophic kernel panic")
    producer = EventProducer(producer=mock_p)

    with pytest.raises(KafkaProducerError) as exc_info:
        producer.publish(topic="risk-alerts", value={"test": 1})

    assert exc_info.value.status_code == 500
    assert "Unexpected failure publishing to Kafka topic" in exc_info.value.message


def test_publish_app_exception_reraised():
    """Verify AppException subclasses are re-raised directly without wrapping."""
    mock_p = create_mock_producer()
    mock_p.send.side_effect = KafkaSerializationError("Schema serialization error")
    producer = EventProducer(producer=mock_p)

    with pytest.raises(KafkaSerializationError) as exc_info:
        producer.publish(topic="risk-alerts", value={"test": 1})

    assert exc_info.value.status_code == 400
    assert "Schema serialization error" in exc_info.value.message
