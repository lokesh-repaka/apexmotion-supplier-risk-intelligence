"""Forensic audit event schema for Kafka topic `audit-events`.

Represents immutable audit log entries streaming to S3 WORM Object Lock storage
conforming to BR-RULE-007. Automatically sanitizes credential and token data.
"""

import re
from typing import Any

from pydantic import Field, model_validator

from src.kafka.schemas.base import BaseEvent

_SENSITIVE_KEY_PATTERN = re.compile(
    r"(password|token|secret|kms_key|private_key|credential|api_key)",
    re.IGNORECASE,
)


def _sanitize_payload(payload: Any) -> Any:
    """Recursively redact sensitive credential keys from audit state payloads."""
    if isinstance(payload, dict):
        sanitized = {}
        for k, v in payload.items():
            if _SENSITIVE_KEY_PATTERN.search(str(k)):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = _sanitize_payload(v)
        return sanitized
    if isinstance(payload, list):
        return [_sanitize_payload(item) for item in payload]
    return payload


class AuditEvent(BaseEvent):
    """Forensic immutable audit log event streaming to S3 WORM archive."""

    event_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for the audit event",
    )
    entity_type: str = Field(
        ...,
        min_length=1,
        description="Target domain entity type (e.g. risk_alert, hitl_approval, supplier)",
    )
    entity_id: str = Field(
        ...,
        min_length=1,
        description="Primary identifier of the audited entity",
    )
    action: str = Field(
        ...,
        min_length=1,
        description="Operational action performed (e.g. CREATE, SIGN_APPROVAL, DISPATCH_PO)",
    )
    actor_id: str = Field(
        ...,
        min_length=1,
        description="User or system service identifier performing the action",
    )
    actor_role: str | None = Field(
        default=None,
        description="RBAC persona or role of the actor (e.g. category_manager, vp_supply_chain)",
    )
    before_state: dict[str, Any] | None = Field(
        default=None,
        description="State payload prior to the action",
    )
    after_state: dict[str, Any] | None = Field(
        default=None,
        description="State payload resulting from the action",
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Additional forensic context or execution parameters",
    )

    @model_validator(mode="before")
    @classmethod
    def sanitize_sensitive_states(cls, data: Any) -> Any:
        """Sanitize passwords, tokens, and KMS keys from audit payloads before persistence."""
        if isinstance(data, dict):
            if "before_state" in data and data["before_state"] is not None:
                data["before_state"] = _sanitize_payload(data["before_state"])
            if "after_state" in data and data["after_state"] is not None:
                data["after_state"] = _sanitize_payload(data["after_state"])
        return data


# Canonical alias for compatibility
AuditEventSchema = AuditEvent
