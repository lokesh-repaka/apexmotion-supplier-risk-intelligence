"""Base schema definition for Kafka events in ApexMotion platform.

Provides:
- Pydantic v2 BaseEvent model with strict validation (extra='forbid', str_strip_whitespace=True).
- Standardized metadata attributes: schema_version, timestamp (UTC), and distributed trace_id.
- Exact Decimal monetary serialization without floating-point precision distortion (BR-RULE-001).
- Serialization and deserialization helpers (to_dict, to_json, to_bytes, from_json).
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from src.core.logging import get_trace_id


class BaseEvent(BaseModel):
    """Abstract base class for all streaming Kafka event schemas."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
        validate_assignment=True,
        ser_json_timedelta="iso8601",
    )

    schema_version: str = Field(
        default="1.0",
        description="Event schema semantic version",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Event creation timestamp in UTC ISO-8601 format",
    )
    trace_id: str = Field(
        default_factory=lambda: get_trace_id() or uuid.uuid4().hex,
        description="Distributed request trace identifier",
    )

    @field_validator("timestamp", mode="after")
    @classmethod
    def ensure_utc(cls, dt: datetime) -> datetime:
        """Ensure timestamp is timezone-aware UTC."""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt

    @field_serializer("timestamp")
    def serialize_timestamp(self, dt: datetime) -> str:
        """Serialize datetime to ISO-8601 UTC string."""
        return dt.isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Convert model to Python dictionary using JSON-compatible types."""
        return self.model_dump(mode="json")

    def to_json(self) -> str:
        """Serialize model to JSON string, preserving Decimal precision as string."""
        data = self.to_dict()
        return json.dumps(data)

    def to_bytes(self) -> bytes:
        """Serialize model to UTF-8 encoded JSON bytes for Kafka transport."""
        return self.to_json().encode("utf-8")

    @classmethod
    def from_json(cls, raw: str | bytes) -> Self:
        """Deserialize JSON string or bytes into schema model instance."""
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return cls.model_validate_json(raw)
