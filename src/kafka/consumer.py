"""Amazon MSK / Kafka event consumer with at-least-once delivery and DLQ (P6-1).

Enforces:
- MSK consumer group coordination for horizontal scaling across worker pods.
- Strict at-least-once delivery semantics via explicit manual offset commits.
- Offsets committed strictly AFTER successful message processing or successful DLQ routing.
- Dead-Letter Queue (DLQ) routing upon reaching 3 processing failures (max_retries=3).
- DLQ failure protection: offset is NOT committed if DLQ publish fails, preventing message loss.
- Distributed trace_id propagation from Kafka headers (X-Trace-ID) to structured logs.
- Automatic payload deserialization with fallback handling for JSON and plain text.
- Clean lifecycle management (poll loop, run_once, graceful shutdown).
- Offline isolation with injectable consumer and producer for unit testing.
"""

import inspect
import json
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.api.exceptions import AppException
from src.core.config import get_settings
from src.core.logging import get_logger, get_trace_id

logger = get_logger("apexmotion.kafka.consumer")


# ------------------------------------------------------------------------------
# Exceptions
# ------------------------------------------------------------------------------


class KafkaConsumerError(AppException):
    """Base exception for Kafka consumer failures."""

    def __init__(
        self,
        message: str,
        code: str = "KAFKA_CONSUMER_ERROR",
        status_code: int = 500,
        details: Any = None,
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            status_code=status_code,
            details=details,
        )


class KafkaDLQError(KafkaConsumerError):
    """Raised when publishing a poisonous message to the Dead-Letter Queue fails."""

    def __init__(self, message: str, details: Any = None) -> None:
        super().__init__(
            message=message,
            code="KAFKA_DLQ_ERROR",
            status_code=500,
            details=details,
        )


class KafkaMessageProcessingError(KafkaConsumerError):
    """Raised when message processing logic encounters an unrecoverable error."""

    def __init__(self, message: str, details: Any = None) -> None:
        super().__init__(
            message=message,
            code="KAFKA_PROCESSING_ERROR",
            status_code=500,
            details=details,
        )


# ------------------------------------------------------------------------------
# Data Models
# ------------------------------------------------------------------------------


@dataclass
class ConsumedMessage:
    """Standardized ingested Kafka message container."""

    topic: str
    partition: int
    offset: int
    key: str | None
    value: Any
    headers: dict[str, str] = field(default_factory=dict)
    timestamp: int | None = None


@dataclass
class DLQMessage:
    """Standardized Dead-Letter Queue message payload."""

    original_topic: str
    original_partition: int
    original_offset: int
    original_key: str | None
    original_payload: Any
    error_message: str
    failure_count: int
    failed_at: str
    trace_id: str


# ------------------------------------------------------------------------------
# Kafka Event Consumer Implementation
# ------------------------------------------------------------------------------


class EventConsumer:
    """High-reliability Kafka consumer enforcing at-least-once delivery and DLQ routing."""

    def __init__(
        self,
        topics: list[str] | str,
        bootstrap_servers: str | None = None,
        group_id: str | None = None,
        client_id: str | None = None,
        max_retries: int = 3,
        auto_offset_reset: str = "earliest",
        dlq_topic_suffix: str = ".dlq",
        consumer: Any | None = None,
        producer: Any | None = None,
    ) -> None:
        """Initialize the event consumer.

        Args:
            topics: Single topic string or list of topic strings to subscribe to.
            bootstrap_servers: Kafka broker addresses (defaults to settings.KAFKA_BOOTSTRAP_SERVERS).
            group_id: Consumer group identifier (defaults to settings.KAFKA_CONSUMER_GROUP).
            client_id: Optional client identifier for logging and monitoring.
            max_retries: Number of processing attempts before routing to DLQ (default: 3).
            auto_offset_reset: Offset reset strategy ('earliest' or 'latest').
            dlq_topic_suffix: Suffix appended to topic name for DLQ routing (default: '.dlq').
            consumer: Optional pre-configured or mock Kafka consumer instance.
            producer: Optional pre-configured or mock Kafka producer for DLQ publication.
        """
        settings = get_settings()

        if isinstance(topics, str):
            self.topics = [topics]
        else:
            self.topics = list(topics)

        self.bootstrap_servers = bootstrap_servers or settings.KAFKA_BOOTSTRAP_SERVERS
        self.group_id = group_id or settings.KAFKA_CONSUMER_GROUP
        self.client_id = client_id or f"{self.group_id}-client"
        self.max_retries = max_retries
        self.auto_offset_reset = auto_offset_reset
        self.dlq_topic_suffix = dlq_topic_suffix

        self._consumer = consumer
        self._producer = producer
        self._handlers: dict[
            str,
            Callable[[ConsumedMessage], Coroutine[Any, Any, None] | Any],
        ] = {}
        self.is_running = True

    def _get_consumer(self) -> Any:
        """Lazily initialize Kafka consumer if not injected."""
        if self._consumer is None:
            from kafka import KafkaConsumer  # type: ignore[import-untyped]

            self._consumer = KafkaConsumer(
                *self.topics,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                client_id=self.client_id,
                enable_auto_commit=False,
                auto_offset_reset=self.auto_offset_reset,
            )
        return self._consumer

    def _get_producer(self) -> Any:
        """Lazily initialize Kafka producer for DLQ publication if not injected."""
        if self._producer is None:
            from kafka import KafkaProducer

            self._producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                client_id=f"{self.client_id}-dlq-producer",
            )
        return self._producer

    def register_handler(
        self,
        topic: str,
        handler: Callable[[ConsumedMessage], Coroutine[Any, Any, None] | Any],
    ) -> None:
        """Register a message processing handler for a specific topic.

        Args:
            topic: Kafka topic name.
            handler: Callable (sync or async) accepting ConsumedMessage.
        """
        self._handlers[topic] = handler
        logger.info(
            "Registered handler for topic '%s' on consumer group '%s'",
            topic,
            self.group_id,
        )

    def _extract_headers(self, record: Any) -> tuple[dict[str, str], str]:
        """Extract headers dictionary and trace_id from Kafka record headers."""
        headers: dict[str, str] = {}
        trace_id: str | None = None

        raw_headers = getattr(record, "headers", None)
        if raw_headers:
            for k, v in raw_headers:
                decoded_val = v.decode("utf-8") if isinstance(v, bytes) else str(v)
                headers[k] = decoded_val
                if k.lower() in ("x-trace-id", "trace_id", "traceid"):
                    trace_id = decoded_val

        if not trace_id:
            ctx_trace = get_trace_id()
            trace_id = ctx_trace if ctx_trace else uuid.uuid4().hex

        return headers, trace_id

    def _deserialize_value(self, raw_value: Any) -> Any:
        """Deserialize message value, attempting JSON parse with string fallback."""
        if raw_value is None:
            return None

        text_content: str
        if isinstance(raw_value, bytes):
            try:
                text_content = raw_value.decode("utf-8")
            except UnicodeDecodeError:
                return raw_value
        elif isinstance(raw_value, str):
            text_content = raw_value
        else:
            return raw_value

        try:
            return json.loads(text_content)
        except (json.JSONDecodeError, TypeError):
            return text_content

    async def _route_to_dlq(
        self,
        record: Any,
        parsed_value: Any,
        key_str: str | None,
        last_error_message: str,
        trace_id: str,
    ) -> None:
        """Route poisonous message to Dead-Letter Queue (<topic>.dlq)."""
        dlq_topic = f"{record.topic}{self.dlq_topic_suffix}"
        dlq_payload = {
            "original_topic": record.topic,
            "original_partition": record.partition,
            "original_offset": record.offset,
            "original_key": key_str,
            "original_payload": parsed_value,
            "error_message": last_error_message,
            "failure_count": self.max_retries,
            "failed_at": datetime.now(UTC).isoformat(),
            "trace_id": trace_id,
        }

        logger.warning(
            "Publishing poisonous message to DLQ topic '%s' (offset %d, trace_id: %s)",
            dlq_topic,
            record.offset,
            trace_id,
            extra={"trace_id": trace_id},
        )

        try:
            producer = self._get_producer()
            raw_dlq_bytes = json.dumps(dlq_payload, default=str).encode("utf-8")

            # Support both mock and real kafka producer signatures
            producer.send(
                dlq_topic,
                key=record.key,
                value=raw_dlq_bytes,
            )
            if hasattr(producer, "flush"):
                producer.flush()
        except Exception as exc:
            logger.error(
                "CRITICAL: Failed to publish message to DLQ topic '%s': %s",
                dlq_topic,
                exc,
                exc_info=True,
                extra={"trace_id": trace_id},
            )
            raise KafkaDLQError(
                f"Failed to route poisonous message to DLQ topic '{dlq_topic}': {exc}",
                details={"dlq_topic": dlq_topic, "original_offset": record.offset},
            ) from exc

    async def process_record(self, record: Any) -> bool:
        """Process a single Kafka record with retries, DLQ routing, and manual commit.

        Args:
            record: Kafka ConsumerRecord or mock record.

        Returns:
            True if successfully processed or skipped; False if routed to DLQ.

        Raises:
            KafkaDLQError: If DLQ publication fails (offset is NOT committed).
        """
        headers, trace_id = self._extract_headers(record)
        parsed_value = self._deserialize_value(record.value)

        key_str: str | None = None
        if record.key is not None:
            key_str = (
                record.key.decode("utf-8") if isinstance(record.key, bytes) else str(record.key)
            )

        consumed_msg = ConsumedMessage(
            topic=record.topic,
            partition=record.partition,
            offset=record.offset,
            key=key_str,
            value=parsed_value,
            headers=headers,
            timestamp=getattr(record, "timestamp", None),
        )

        handler = self._handlers.get(record.topic)
        if handler is None:
            logger.warning(
                "No registered handler for topic '%s'. Skipping and committing offset %d.",
                record.topic,
                record.offset,
                extra={"trace_id": trace_id},
            )
            consumer = self._get_consumer()
            consumer.commit()
            return True

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug(
                    "Processing message topic='%s' offset=%d attempt=%d/%d (trace_id: %s)",
                    record.topic,
                    record.offset,
                    attempt,
                    self.max_retries,
                    trace_id,
                    extra={"trace_id": trace_id},
                )
                if inspect.iscoroutinefunction(handler):
                    await handler(consumed_msg)
                else:
                    res = handler(consumed_msg)
                    if inspect.isawaitable(res):
                        await res

                # Successful processing: commit offset manually (at-least-once)
                consumer = self._get_consumer()
                consumer.commit()
                logger.info(
                    "Successfully processed and committed message topic='%s' offset=%d (trace_id: %s)",
                    record.topic,
                    record.offset,
                    trace_id,
                    extra={"trace_id": trace_id},
                )
                return True

            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Failure processing message topic='%s' offset=%d attempt=%d/%d: %s",
                    record.topic,
                    record.offset,
                    attempt,
                    self.max_retries,
                    exc,
                    extra={"trace_id": trace_id},
                )

        # Retries exhausted: Route to DLQ
        error_msg = str(last_error) if last_error else "Unknown processing failure"
        await self._route_to_dlq(
            record=record,
            parsed_value=parsed_value,
            key_str=key_str,
            last_error_message=error_msg,
            trace_id=trace_id,
        )

        # Commit offset on primary topic only AFTER successful DLQ route
        consumer = self._get_consumer()
        consumer.commit()
        return False

    def poll(self, timeout_ms: int = 1000) -> list[ConsumedMessage]:
        """Poll raw records from Kafka and convert to ConsumedMessage objects.

        Args:
            timeout_ms: Milliseconds to block waiting for records.

        Returns:
            List of ConsumedMessage objects.
        """
        consumer = self._get_consumer()
        raw_batch = consumer.poll(timeout_ms=timeout_ms)
        messages: list[ConsumedMessage] = []

        for _topic_partition, records in raw_batch.items():
            for rec in records:
                headers, _trace_id = self._extract_headers(rec)
                parsed_val = self._deserialize_value(rec.value)
                key_str = (
                    rec.key.decode("utf-8")
                    if isinstance(rec.key, bytes)
                    else str(rec.key)
                    if rec.key is not None
                    else None
                )
                messages.append(
                    ConsumedMessage(
                        topic=rec.topic,
                        partition=rec.partition,
                        offset=rec.offset,
                        key=key_str,
                        value=parsed_val,
                        headers=headers,
                        timestamp=getattr(rec, "timestamp", None),
                    )
                )
        return messages

    async def run_once(self, max_records: int = 100) -> int:
        """Poll and process available records up to max_records.

        Args:
            max_records: Maximum records to consume in this iteration.

        Returns:
            Count of messages processed.
        """
        consumer = self._get_consumer()
        raw_batch = consumer.poll(timeout_ms=1000, max_records=max_records)
        processed_count = 0

        for _topic_partition, records in raw_batch.items():
            for rec in records:
                if not self.is_running:
                    break
                await self.process_record(rec)
                processed_count += 1

        return processed_count

    def close(self) -> None:
        """Close Kafka consumer and producer instances cleanly."""
        self.is_running = False
        if self._consumer is not None and hasattr(self._consumer, "close"):
            self._consumer.close()
            logger.info("Closed Kafka consumer for group '%s'", self.group_id)

        if self._producer is not None and hasattr(self._producer, "close"):
            self._producer.close()
            logger.info("Closed DLQ Kafka producer for group '%s'", self.group_id)
