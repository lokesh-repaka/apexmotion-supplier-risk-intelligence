"""Kafka streaming package for ApexMotion platform.

Exports:
- EventConsumer: High-reliability MSK Kafka consumer with at-least-once delivery and DLQ.
- ConsumedMessage: Standardized consumed message container.
- DLQMessage: Dead-letter queue message representation.
- KafkaConsumerError: Base Kafka consumer exception.
- KafkaDLQError: Dead-letter queue publishing exception.
- KafkaMessageProcessingError: Handler processing failure exception.
"""

from src.kafka.consumer import (
    ConsumedMessage,
    DLQMessage,
    EventConsumer,
    KafkaConsumerError,
    KafkaDLQError,
    KafkaMessageProcessingError,
)

__all__ = [
    "ConsumedMessage",
    "DLQMessage",
    "EventConsumer",
    "KafkaConsumerError",
    "KafkaDLQError",
    "KafkaMessageProcessingError",
]
