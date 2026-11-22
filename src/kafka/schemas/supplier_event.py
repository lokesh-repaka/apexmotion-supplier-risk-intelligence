"""Supplier disruption event schema for Kafka topic `supplier-events`.

Represents incoming real-time disruption signals from external feeds (news scrapers,
maritime AIS, plant MES, SAP ERP, EDI).
"""

from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator

from src.kafka.schemas.base import BaseEvent


class DisruptionType(StrEnum):
    """Enumeration of external disruption event categories."""

    NEWS_DISRUPTION = "NEWS_DISRUPTION"
    WEATHER_ALERT = "WEATHER_ALERT"
    LOGISTICS_DELAY = "LOGISTICS_DELAY"
    FACTORY_HALT = "FACTORY_HALT"
    GEOPOLITICAL_RISK = "GEOPOLITICAL_RISK"
    PRODUCTION_DEFECT = "PRODUCTION_DEFECT"
    CYBER_INCIDENT = "CYBER_INCIDENT"
    LABOR_STRIKE = "LABOR_STRIKE"
    TRADE_SANCTION = "TRADE_SANCTION"


class SeverityLevel(StrEnum):
    """Severity classification matching platform alert boundaries."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class SupplierEvent(BaseEvent):
    """Inbound streaming event representing a supplier disruption signal."""

    event_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for the disruption event",
    )
    event_type: DisruptionType | str = Field(
        ...,
        description="Classification category of the disruption",
    )
    supplier_id: str = Field(
        ...,
        min_length=1,
        description="Target supplier identifier (e.g. SUP-NC-882)",
    )
    source: str = Field(
        ...,
        min_length=1,
        description="Data feed origin (e.g. REUTERS, BLOOMBERG, SAP_ERP, PLANT_MES)",
    )
    severity: SeverityLevel | str = Field(
        ...,
        description="Assigned severity rating: CRITICAL, HIGH, MEDIUM, LOW",
    )
    description: str = Field(
        ...,
        min_length=1,
        description="Human-readable narrative summary of the incident",
    )
    affected_skus: list[str] = Field(
        default_factory=list,
        description="List of component SKUs directly impacted by the disruption",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional structured feed metadata",
    )

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: SeverityLevel | str) -> str:
        """Validate severity against allowed enum values."""
        val = v.value if isinstance(v, SeverityLevel) else str(v).upper()
        allowed = {s.value for s in SeverityLevel}
        if val not in allowed:
            raise ValueError(f"Invalid severity '{val}'. Must be one of: {allowed}")
        return val
