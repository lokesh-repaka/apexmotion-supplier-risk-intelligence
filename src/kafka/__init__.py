"""Kafka streaming package for ApexMotion platform.

Exports:
- EventConsumer: High-reliability MSK Kafka consumer with at-least-once delivery and DLQ.
- ConsumedMessage: Standardized consumed message container.
- DLQMessage: Dead-letter queue message representation.
- KafkaConsumerError: Base Kafka consumer exception.
- KafkaDLQError: Dead-letter queue publishing exception.
- KafkaMessageProcessingError: Handler processing failure exception.
- EventProducer: High-reliability Kafka producer with at-least-once delivery.
- PublishedRecord: Published message metadata record.
- EventJSONEncoder: JSON encoder preserving Decimal precision and datetime formats.
- serialize_payload: Safe payload serializer.
- get_event_producer: Global EventProducer singleton accessor.
- KafkaProducerError: Base Kafka producer exception.
- KafkaPublishTimeoutError: Broker publish timeout exception (504).
- KafkaSerializationError: Payload serialization exception (400).
- KafkaBrokerUnavailableError: Broker unreachable exception (503).
"""

from src.kafka.consumer import (
    ConsumedMessage,
    DLQMessage,
    EventConsumer,
    KafkaConsumerError,
    KafkaDLQError,
    KafkaMessageProcessingError,
)
from src.kafka.producer import (
    EventJSONEncoder,
    EventProducer,
    KafkaBrokerUnavailableError,
    KafkaProducerError,
    KafkaPublishTimeoutError,
    KafkaSerializationError,
    PublishedRecord,
    get_event_producer,
    serialize_payload,
)
from src.kafka.schemas import (
    AlertStatus,
    AuditEvent,
    AuditEventSchema,
    BaseEvent,
    DisruptionType,
    HITLActionType,
    HITLRequest,
    HITLRequestEvent,
    HITLStatus,
    RiskAlert,
    RiskAlertEvent,
    RiskLevel,
    SeverityLevel,
    SpendTier,
    SupplierEvent,
)

__all__ = [
    "AlertStatus",
    "AuditEvent",
    "AuditEventSchema",
    "BaseEvent",
    "ConsumedMessage",
    "DLQMessage",
    "DisruptionType",
    "EventConsumer",
    "EventJSONEncoder",
    "EventProducer",
    "HITLActionType",
    "HITLRequest",
    "HITLRequestEvent",
    "HITLStatus",
    "KafkaBrokerUnavailableError",
    "KafkaConsumerError",
    "KafkaDLQError",
    "KafkaMessageProcessingError",
    "KafkaProducerError",
    "KafkaPublishTimeoutError",
    "KafkaSerializationError",
    "PublishedRecord",
    "RiskAlert",
    "RiskAlertEvent",
    "RiskLevel",
    "SeverityLevel",
    "SpendTier",
    "SupplierEvent",
    "get_event_producer",
    "serialize_payload",
]
