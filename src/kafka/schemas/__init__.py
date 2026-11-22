"""Kafka event schemas package for ApexMotion platform.

Exports standardized Pydantic v2 event models for core streaming topics:
- `supplier-events`: SupplierEvent (DisruptionType, SeverityLevel)
- `risk-alerts`: RiskAlert, RiskAlertEvent (RiskLevel, AlertStatus, SpendTier)
- `hitl-required`: HITLRequest, HITLRequestEvent (HITLActionType, HITLStatus)
- `audit-events`: AuditEvent, AuditEventSchema

All schemas enforce the Triad of Responsibility (BR-RULE-001) with exact
Decimal precision for financial values and zero IEEE 754 floating-point distortion.
"""

from src.kafka.schemas.audit_event import AuditEvent, AuditEventSchema
from src.kafka.schemas.base import BaseEvent
from src.kafka.schemas.hitl_request import (
    HITLActionType,
    HITLRequest,
    HITLRequestEvent,
    HITLStatus,
)
from src.kafka.schemas.risk_alert import (
    AlertStatus,
    RiskAlert,
    RiskAlertEvent,
    RiskLevel,
    SpendTier,
)
from src.kafka.schemas.supplier_event import (
    DisruptionType,
    SeverityLevel,
    SupplierEvent,
)

__all__ = [
    "AlertStatus",
    "AuditEvent",
    "AuditEventSchema",
    "BaseEvent",
    "DisruptionType",
    "HITLActionType",
    "HITLRequest",
    "HITLRequestEvent",
    "HITLStatus",
    "RiskAlert",
    "RiskAlertEvent",
    "RiskLevel",
    "SeverityLevel",
    "SpendTier",
    "SupplierEvent",
]
