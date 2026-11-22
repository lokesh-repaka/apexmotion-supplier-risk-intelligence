"""High-reliability Kafka Event Producer for ApexMotion platform.

Publishes internal streaming events conforming to enterprise architecture (CLAUDE.md Sec 17):
- `risk-alerts` (settings.KAFKA_TOPIC_RISK_ALERTS): Real-time calculated risk alerts.
- `hitl-required` (settings.KAFKA_TOPIC_HITL_REQUIRED): Human-in-the-loop spend approvals.
- `audit-events` (settings.KAFKA_TOPIC_AUDIT_EVENTS): Immutable audit event stream.

Key capabilities:
- Enforces at-least-once delivery semantics via `acks='all'` and broker acknowledgment.
- Automated JSON serialization preserving `Decimal` monetary precision (BR-RULE-001) without float error.
- Distributed `trace_id` injection and correlation in Kafka message headers.
- Automatic partition key resolution based on canonical domain identifiers.
- Synchronous and asynchronous publishing APIs.
- Offline isolation via injectable mock producer.
"""

import asyncio
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from src.api.exceptions import AppException
from src.core.config import get_settings
from src.core.logging import get_logger, get_trace_id

logger = get_logger("apexmotion.kafka.producer")


# ------------------------------------------------------------------------------
# Exceptions
# ------------------------------------------------------------------------------


class KafkaProducerError(AppException):
    """Base exception for Kafka producer failures."""

    def __init__(
        self,
        message: str,
        code: str = "KAFKA_PRODUCER_ERROR",
        status_code: int = 500,
        details: Any = None,
    ):
        super().__init__(
            code=code,
            message=message,
            status_code=status_code,
            details=details,
        )


class KafkaPublishTimeoutError(KafkaProducerError):
    """Raised when broker fails to acknowledge message publication within deadline."""

    def __init__(self, message: str, details: Any = None):
        super().__init__(
            code="KAFKA_PUBLISH_TIMEOUT",
            message=message,
            status_code=504,
            details=details,
        )


class KafkaSerializationError(KafkaProducerError):
    """Raised when message payload fails JSON serialization."""

    def __init__(self, message: str, details: Any = None):
        super().__init__(
            code="KAFKA_SERIALIZATION_ERROR",
            message=message,
            status_code=400,
            details=details,
        )


class KafkaBrokerUnavailableError(KafkaProducerError):
    """Raised when target Kafka broker or cluster is unreachable."""

    def __init__(self, message: str, details: Any = None):
        super().__init__(
            code="KAFKA_BROKER_UNAVAILABLE",
            message=message,
            status_code=503,
            details=details,
        )


# ------------------------------------------------------------------------------
# Data Models & Serialization
# ------------------------------------------------------------------------------


@dataclass(frozen=True)
class PublishedRecord:
    """Metadata container for a successfully published Kafka record."""

    topic: str
    partition: int
    offset: int
    timestamp: int
    key: str | None
    trace_id: str


class EventJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder handling Decimal, datetime, UUID, Pydantic, and dataclass models."""

    def default(self, o: Any) -> Any:
        if isinstance(o, Decimal):
            # Preserve exact financial precision as string representation (BR-RULE-001)
            return str(o)
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if isinstance(o, uuid.UUID):
            return str(o)
        if hasattr(o, "model_dump"):
            return o.model_dump(mode="json")
        if hasattr(o, "dict"):
            return o.dict()
        if hasattr(o, "__dataclass_fields__"):
            return asdict(o)
        if hasattr(o, "__dict__"):
            return vars(o)
        return super().default(o)


def serialize_payload(value: Any) -> bytes:
    """Serialize payload to UTF-8 bytes, with JSON encoding for complex structures.

    Args:
        value: Any payload object (dict, Pydantic model, dataclass, str, bytes, None).

    Returns:
        Encoded bytes.

    Raises:
        KafkaSerializationError: If payload cannot be serialized to JSON.
    """
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")

    try:
        return json.dumps(value, cls=EventJSONEncoder).encode("utf-8")
    except Exception as exc:
        raise KafkaSerializationError(
            f"Failed to serialize payload to JSON: {exc}",
            details={"type": type(value).__name__, "error": str(exc)},
        ) from exc


def encode_key(key: Any) -> bytes | None:
    """Encode partition key to bytes."""
    if key is None:
        return None
    if isinstance(key, bytes):
        return key
    return str(key).encode("utf-8")


def format_headers(
    headers: dict[str, str | bytes] | list[tuple[str, str | bytes]] | None,
    trace_id: str,
    client_id: str,
) -> list[tuple[str, bytes]]:
    """Format and enrich Kafka record headers with trace ID and operational metadata.

    Args:
        headers: Caller-supplied headers (dict or list of tuples).
        trace_id: Distributed trace identifier.
        client_id: Producer client identifier.

    Returns:
        List of (header_name, header_value_bytes) tuples suitable for KafkaProducer.
    """
    result: list[tuple[str, bytes]] = []
    seen_keys: set[str] = set()

    if headers:
        items = headers.items() if isinstance(headers, dict) else headers
        for k, v in items:
            k_str = str(k)
            v_bytes = v if isinstance(v, bytes) else str(v).encode("utf-8")
            result.append((k_str, v_bytes))
            seen_keys.add(k_str.lower())

    if "x-trace-id" not in seen_keys and "trace_id" not in seen_keys:
        result.append(("X-Trace-ID", trace_id.encode("utf-8")))

    if "x-client-id" not in seen_keys:
        result.append(("X-Client-ID", client_id.encode("utf-8")))

    if "x-timestamp" not in seen_keys:
        result.append(("X-Timestamp", datetime.now(UTC).isoformat().encode("utf-8")))

    return result


# ------------------------------------------------------------------------------
# Producer Implementation
# ------------------------------------------------------------------------------


class EventProducer:
    """High-reliability Kafka producer for internal streaming events."""

    def __init__(
        self,
        bootstrap_servers: str | None = None,
        client_id: str | None = None,
        acks: str | int = "all",
        retries: int = 3,
        compression_type: str = "gzip",
        request_timeout_ms: int = 10000,
        max_block_ms: int = 10000,
        producer: Any = None,
    ):
        """Initialize the event producer.

        Args:
            bootstrap_servers: Kafka broker addresses.
            client_id: Producer client identifier.
            acks: Acknowledgment mode ('all', 1, 0) enforcing at-least-once durability.
            retries: Broker publish retry attempts.
            compression_type: Message compression algorithm ('gzip', 'lz4', 'snappy').
            request_timeout_ms: Broker response deadline in milliseconds.
            max_block_ms: Maximum blocking time for metadata and buffer memory.
            producer: Optional pre-configured KafkaProducer instance for unit testing.
        """
        settings = get_settings()
        self.bootstrap_servers = bootstrap_servers or settings.KAFKA_BOOTSTRAP_SERVERS
        self.client_id = client_id or "apexmotion-event-producer"
        self.acks = acks
        self.retries = retries
        self.compression_type = compression_type
        self.request_timeout_ms = request_timeout_ms
        self.max_block_ms = max_block_ms
        self._producer = producer
        self._is_closed = False

    def _get_producer(self) -> Any:
        """Lazily initialize underlying Kafka producer if not injected."""
        if self._producer is None:
            from kafka import KafkaProducer  # type: ignore[import-untyped]

            self._producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                client_id=self.client_id,
                acks=self.acks,
                retries=self.retries,
                compression_type=self.compression_type,
                request_timeout_ms=self.request_timeout_ms,
                max_block_ms=self.max_block_ms,
            )
            logger.info(
                "Initialized Kafka producer for client '%s' on %s",
                self.client_id,
                self.bootstrap_servers,
            )
        return self._producer

    def _extract_key(self, payload: Any, candidates: list[str]) -> str | None:
        """Attempt to extract partition key from payload based on candidate field names."""
        if isinstance(payload, dict):
            for candidate in candidates:
                val = payload.get(candidate)
                if val is not None:
                    return str(val)
        elif hasattr(payload, "__dict__") or hasattr(payload, "__dataclass_fields__"):
            for candidate in candidates:
                val = getattr(payload, candidate, None)
                if val is not None:
                    return str(val)
        return None

    def publish(
        self,
        topic: str,
        value: Any,
        key: str | bytes | None = None,
        headers: dict[str, str | bytes] | list[tuple[str, str | bytes]] | None = None,
        trace_id: str | None = None,
        timeout: float | None = None,
    ) -> PublishedRecord:
        """Synchronously publish an event to a Kafka topic and wait for broker acknowledgment.

        Args:
            topic: Target Kafka topic name.
            value: Message payload (dict, model, dataclass, string, or bytes).
            key: Optional message partition routing key.
            headers: Optional custom headers.
            trace_id: Optional distributed trace identifier.
            timeout: Optional broker acknowledgment deadline in seconds.

        Returns:
            PublishedRecord containing partition, offset, timestamp, and metadata.

        Raises:
            KafkaProducerError: On closed producer or general broker failure.
            KafkaPublishTimeoutError: When broker fails to acknowledge within deadline.
            KafkaBrokerUnavailableError: When Kafka broker is disconnected or unreachable.
            KafkaSerializationError: When payload cannot be converted to JSON.
        """
        if self._is_closed:
            raise KafkaProducerError("Cannot publish on a closed producer.")

        from kafka.errors import (  # type: ignore[import-untyped]
            BrokerNotAvailableError,
            KafkaError,
            KafkaTimeoutError,
            RequestTimedOutError,
        )

        producer = self._get_producer()
        encoded_value = serialize_payload(value)
        encoded_key = encode_key(key)

        resolved_trace_id = trace_id or get_trace_id() or uuid.uuid4().hex
        formatted_headers = format_headers(headers, resolved_trace_id, self.client_id)
        ack_timeout = timeout if timeout is not None else (self.request_timeout_ms / 1000.0)

        try:
            future = producer.send(
                topic,
                value=encoded_value,
                key=encoded_key,
                headers=formatted_headers,
            )
            metadata = future.get(timeout=ack_timeout)
        except (KafkaTimeoutError, RequestTimedOutError, TimeoutError) as exc:
            logger.error("Kafka publish timeout on topic '%s': %s", topic, exc)
            raise KafkaPublishTimeoutError(
                f"Timed out waiting for broker acknowledgment on topic '{topic}': {exc}",
                details={"topic": topic, "key": str(key) if key else None, "error": str(exc)},
            ) from exc
        except BrokerNotAvailableError as exc:
            logger.error("Kafka broker unavailable when publishing to topic '%s': %s", topic, exc)
            raise KafkaBrokerUnavailableError(
                f"Kafka broker unavailable when publishing to topic '{topic}': {exc}",
                details={"topic": topic, "error": str(exc)},
            ) from exc
        except KafkaError as exc:
            logger.error("Kafka error publishing to topic '%s': %s", topic, exc)
            raise KafkaProducerError(
                f"Kafka error publishing to topic '{topic}': {exc}",
                details={"topic": topic, "error": str(exc)},
            ) from exc
        except Exception as exc:
            if isinstance(exc, (KafkaProducerError, AppException)):
                raise
            logger.error("Unexpected error publishing to Kafka topic '%s': %s", topic, exc)
            raise KafkaProducerError(
                f"Unexpected failure publishing to Kafka topic '{topic}': {exc}",
                details={"topic": topic, "error": str(exc)},
            ) from exc

        partition = getattr(metadata, "partition", 0)
        offset = getattr(metadata, "offset", 0)
        timestamp = getattr(metadata, "timestamp", int(datetime.now(UTC).timestamp() * 1000))

        key_str = (
            key.decode("utf-8")
            if isinstance(key, bytes)
            else (str(key) if key is not None else None)
        )

        logger.debug(
            "Published event to topic '%s' [partition=%s, offset=%s, key=%s, trace_id=%s]",
            topic,
            partition,
            offset,
            key_str,
            resolved_trace_id,
        )

        return PublishedRecord(
            topic=topic,
            partition=partition,
            offset=offset,
            timestamp=timestamp,
            key=key_str,
            trace_id=resolved_trace_id,
        )

    def publish_risk_alert(
        self,
        alert_data: dict[str, Any] | Any,
        key: str | None = None,
        trace_id: str | None = None,
        headers: dict[str, str | bytes] | list[tuple[str, str | bytes]] | None = None,
        timeout: float | None = None,
    ) -> PublishedRecord:
        """Publish a risk alert to the risk-alerts topic.

        Args:
            alert_data: Risk alert payload (dict, model, or dataclass).
            key: Optional message partition key (defaults to supplier_id, alert_id, or sku).
            trace_id: Optional distributed trace identifier.
            headers: Optional custom headers.
            timeout: Optional broker acknowledgment deadline in seconds.

        Returns:
            PublishedRecord with topic, partition, offset, and timestamp.
        """
        topic = get_settings().KAFKA_TOPIC_RISK_ALERTS
        resolved_key = key or self._extract_key(
            alert_data, ["supplier_id", "alert_id", "sku", "id"]
        )
        return self.publish(
            topic=topic,
            value=alert_data,
            key=resolved_key,
            headers=headers,
            trace_id=trace_id,
            timeout=timeout,
        )

    def publish_hitl_request(
        self,
        hitl_data: dict[str, Any] | Any,
        key: str | None = None,
        trace_id: str | None = None,
        headers: dict[str, str | bytes] | list[tuple[str, str | bytes]] | None = None,
        timeout: float | None = None,
    ) -> PublishedRecord:
        """Publish a HITL approval request to the hitl-required topic.

        Args:
            hitl_data: HITL request payload (dict, model, or dataclass).
            key: Optional message partition key (defaults to action_id, alert_id, or supplier_id).
            trace_id: Optional distributed trace identifier.
            headers: Optional custom headers.
            timeout: Optional broker acknowledgment deadline in seconds.

        Returns:
            PublishedRecord with topic, partition, offset, and timestamp.
        """
        topic = get_settings().KAFKA_TOPIC_HITL_REQUIRED
        resolved_key = key or self._extract_key(
            hitl_data, ["action_id", "alert_id", "supplier_id", "id"]
        )
        return self.publish(
            topic=topic,
            value=hitl_data,
            key=resolved_key,
            headers=headers,
            trace_id=trace_id,
            timeout=timeout,
        )

    def publish_audit_event(
        self,
        audit_data: dict[str, Any] | Any,
        key: str | None = None,
        trace_id: str | None = None,
        headers: dict[str, str | bytes] | list[tuple[str, str | bytes]] | None = None,
        timeout: float | None = None,
    ) -> PublishedRecord:
        """Publish an immutable audit event to the audit-events topic.

        Args:
            audit_data: Audit event payload (dict, model, or dataclass).
            key: Optional message partition key (defaults to entity_id, trace_id, or actor_id).
            trace_id: Optional distributed trace identifier.
            headers: Optional custom headers.
            timeout: Optional broker acknowledgment deadline in seconds.

        Returns:
            PublishedRecord with topic, partition, offset, and timestamp.
        """
        topic = get_settings().KAFKA_TOPIC_AUDIT_EVENTS
        resolved_key = key or self._extract_key(
            audit_data, ["entity_id", "trace_id", "actor_id", "id"]
        )
        return self.publish(
            topic=topic,
            value=audit_data,
            key=resolved_key,
            headers=headers,
            trace_id=trace_id,
            timeout=timeout,
        )

    async def publish_async(
        self,
        topic: str,
        value: Any,
        key: str | bytes | None = None,
        headers: dict[str, str | bytes] | list[tuple[str, str | bytes]] | None = None,
        trace_id: str | None = None,
        timeout: float | None = None,
    ) -> PublishedRecord:
        """Asynchronously publish an event to a Kafka topic without blocking the event loop."""
        return await asyncio.to_thread(
            self.publish,
            topic=topic,
            value=value,
            key=key,
            headers=headers,
            trace_id=trace_id,
            timeout=timeout,
        )

    async def publish_risk_alert_async(
        self,
        alert_data: dict[str, Any] | Any,
        key: str | None = None,
        trace_id: str | None = None,
        headers: dict[str, str | bytes] | list[tuple[str, str | bytes]] | None = None,
        timeout: float | None = None,
    ) -> PublishedRecord:
        """Asynchronously publish a risk alert."""
        return await asyncio.to_thread(
            self.publish_risk_alert,
            alert_data=alert_data,
            key=key,
            trace_id=trace_id,
            headers=headers,
            timeout=timeout,
        )

    async def publish_hitl_request_async(
        self,
        hitl_data: dict[str, Any] | Any,
        key: str | None = None,
        trace_id: str | None = None,
        headers: dict[str, str | bytes] | list[tuple[str, str | bytes]] | None = None,
        timeout: float | None = None,
    ) -> PublishedRecord:
        """Asynchronously publish a HITL request."""
        return await asyncio.to_thread(
            self.publish_hitl_request,
            hitl_data=hitl_data,
            key=key,
            trace_id=trace_id,
            headers=headers,
            timeout=timeout,
        )

    async def publish_audit_event_async(
        self,
        audit_data: dict[str, Any] | Any,
        key: str | None = None,
        trace_id: str | None = None,
        headers: dict[str, str | bytes] | list[tuple[str, str | bytes]] | None = None,
        timeout: float | None = None,
    ) -> PublishedRecord:
        """Asynchronously publish an audit event."""
        return await asyncio.to_thread(
            self.publish_audit_event,
            audit_data=audit_data,
            key=key,
            trace_id=trace_id,
            headers=headers,
            timeout=timeout,
        )

    def publish_batch(
        self,
        records: list[dict[str, Any]],
        timeout: float | None = None,
    ) -> list[PublishedRecord]:
        """Publish a batch of records, waiting for broker acknowledgments.

        Args:
            records: List of dictionaries with keys:
                - 'topic' (str, required)
                - 'value' (Any, required)
                - 'key' (str | bytes, optional)
                - 'headers' (dict | list, optional)
                - 'trace_id' (str, optional)
            timeout: Optional overall timeout.

        Returns:
            List of PublishedRecord in the same order as records.
        """
        results: list[PublishedRecord] = []
        for item in records:
            topic = item["topic"]
            value = item["value"]
            key = item.get("key")
            headers = item.get("headers")
            trace_id = item.get("trace_id")
            rec = self.publish(
                topic=topic,
                value=value,
                key=key,
                headers=headers,
                trace_id=trace_id,
                timeout=timeout,
            )
            results.append(rec)
        return results

    async def publish_batch_async(
        self,
        records: list[dict[str, Any]],
        timeout: float | None = None,
    ) -> list[PublishedRecord]:
        """Asynchronously publish a batch of records."""
        return await asyncio.to_thread(self.publish_batch, records=records, timeout=timeout)

    def flush(self, timeout: float | None = None) -> None:
        """Flush pending messages in the producer buffer to the broker."""
        if self._producer is not None:
            if timeout is not None:
                self._producer.flush(timeout=timeout)
            else:
                self._producer.flush()

    def close(self, timeout: float | None = None) -> None:
        """Flush pending messages and cleanly terminate producer connections."""
        if not self._is_closed:
            if self._producer is not None:
                if timeout is not None:
                    self._producer.close(timeout=timeout)
                else:
                    self._producer.close()
            self._is_closed = True
            logger.info("Kafka producer '%s' cleanly closed.", self.client_id)

    def __enter__(self) -> "EventProducer":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.flush()
        self.close()

    async def __aenter__(self) -> "EventProducer":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await asyncio.to_thread(self.flush)
        await asyncio.to_thread(self.close)


# ------------------------------------------------------------------------------
# Singleton Accessor
# ------------------------------------------------------------------------------

_GLOBAL_PRODUCER: EventProducer | None = None


def get_event_producer() -> EventProducer:
    """Retrieve or initialize the global reusable EventProducer instance."""
    global _GLOBAL_PRODUCER
    if _GLOBAL_PRODUCER is None or _GLOBAL_PRODUCER._is_closed:
        _GLOBAL_PRODUCER = EventProducer()
    return _GLOBAL_PRODUCER
