"""Kafka event consumer handlers and persistence services (P6-4).

Provides:
- `persist_risk_alert`: Asynchronously parses, validates, and persists a RiskAlert event
  to the Aurora PostgreSQL `risk_alerts` table using `RiskAlertRepository`.
- `create_risk_alert_consumer_handler`: Factory creating a topic consumer handler closure
  bound to an `async_sessionmaker[AsyncSession]`.
- Idempotency guard: handles redelivered events gracefully by updating existing alert records
  rather than failing on primary key conflict.
- The Triad of Responsibility (BR-RULE-001): maintains exact Decimal precision for
  `days_of_cover`, `gap_days`, and `financial_exposure`.
- Distributed trace propagation: logs with contextual `trace_id`.
"""

import json
import uuid
from collections.abc import Callable, Coroutine
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.logging import get_logger, get_trace_id
from src.database.models import RiskAlert as RiskAlertModel
from src.database.models import Supplier
from src.database.repositories.risk_alert_repository import RiskAlertRepository
from src.kafka.consumer import ConsumedMessage, KafkaMessageProcessingError
from src.kafka.schemas.risk_alert import RiskAlert as RiskAlertSchema

logger = get_logger("apexmotion.kafka.handlers")


def _coerce_uuid(val: Any) -> UUID:
    """Coerce string or UUID into a valid UUID, falling back to deterministic UUIDv5."""
    if isinstance(val, UUID):
        return val
    val_str = str(val).strip()
    try:
        return UUID(val_str)
    except (ValueError, AttributeError):
        return uuid.uuid5(uuid.NAMESPACE_DNS, val_str)


async def _resolve_supplier_uuid(supplier_id_raw: Any, session: AsyncSession) -> UUID | None:
    """Resolve raw supplier_id (UUID or neptune_node_id) to Supplier UUID."""
    if not supplier_id_raw:
        return None

    if isinstance(supplier_id_raw, UUID):
        return supplier_id_raw

    supplier_str = str(supplier_id_raw).strip()
    try:
        return UUID(supplier_str)
    except (ValueError, AttributeError):
        # Look up by neptune_node_id in database
        stmt = select(Supplier.id).where(Supplier.neptune_node_id == supplier_str)
        result = await session.execute(stmt)
        matched_id = result.scalar_one_or_none()
        return matched_id


async def persist_risk_alert(
    event_payload: Any,
    session: AsyncSession,
    trace_id: str | None = None,
) -> RiskAlertModel:
    """Validate and persist a RiskAlert event to the database.

    Args:
        event_payload: Raw JSON bytes, dict, or pre-parsed RiskAlertSchema instance.
        session: Active SQLAlchemy AsyncSession.
        trace_id: Optional distributed trace identifier.

    Returns:
        Persisted or updated RiskAlertModel database instance.

    Raises:
        KafkaMessageProcessingError: If validation or persistence fails.
    """
    effective_trace = trace_id or get_trace_id() or "unknown-trace"

    # 1. Parse into RiskAlertSchema
    schema_instance: RiskAlertSchema
    try:
        if isinstance(event_payload, RiskAlertSchema):
            schema_instance = event_payload
        elif isinstance(event_payload, (bytes, str)):
            schema_instance = RiskAlertSchema.from_json(event_payload)
        elif isinstance(event_payload, dict):
            schema_instance = RiskAlertSchema.model_validate(event_payload)
        else:
            raise ValueError(f"Unsupported event payload type: {type(event_payload)}")
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        logger.error(
            "Validation failed for RiskAlert event: %s (trace_id: %s)",
            exc,
            effective_trace,
            extra={"trace_id": effective_trace},
        )
        raise KafkaMessageProcessingError(
            f"Invalid RiskAlert event payload: {exc}",
            details={"payload": str(event_payload)[:200]},
        ) from exc

    alert_uuid = _coerce_uuid(schema_instance.alert_id)
    supplier_uuid = await _resolve_supplier_uuid(schema_instance.supplier_id, session)

    # 2. Check for existing alert (Idempotent delivery)
    repo = RiskAlertRepository(session)
    existing_alert = await repo.get_by_id(alert_uuid)

    if existing_alert is not None:
        logger.info(
            "Idempotent redelivery: updating existing alert id=%s (trace_id: %s)",
            alert_uuid,
            effective_trace,
            extra={"trace_id": effective_trace},
        )
        existing_alert.status = (
            schema_instance.status.value
            if hasattr(schema_instance.status, "value")
            else str(schema_instance.status)
        )
        existing_alert.days_of_cover = schema_instance.days_of_cover
        existing_alert.financial_exposure = schema_instance.financial_exposure
        existing_alert.shortage_volume = schema_instance.shortage_volume
        existing_alert.risk_level = (
            schema_instance.risk_level.value
            if hasattr(schema_instance.risk_level, "value")
            else str(schema_instance.risk_level)
        )
        await session.commit()
        return existing_alert

    # 3. Create new database model
    risk_level_str = (
        schema_instance.risk_level.value
        if hasattr(schema_instance.risk_level, "value")
        else str(schema_instance.risk_level)
    )
    status_str = (
        schema_instance.status.value
        if hasattr(schema_instance.status, "value")
        else str(schema_instance.status)
    )

    db_alert = RiskAlertModel(
        id=alert_uuid,
        supplier_id=supplier_uuid,
        component_sku=schema_instance.component_sku,
        risk_level=risk_level_str,
        days_of_cover=schema_instance.days_of_cover,
        financial_exposure=schema_instance.financial_exposure,
        shortage_volume=schema_instance.shortage_volume,
        status=status_str,
        created_at=schema_instance.timestamp,
    )

    try:
        persisted = await repo.create(db_alert)
        await session.commit()
        logger.info(
            "Persisted RiskAlert id=%s supplier_id=%s sku=%s risk=%s exposure=$%s (trace_id: %s)",
            persisted.id,
            persisted.supplier_id,
            persisted.component_sku,
            persisted.risk_level,
            persisted.financial_exposure,
            effective_trace,
            extra={"trace_id": effective_trace},
        )
        return persisted
    except Exception as exc:
        await session.rollback()
        logger.error(
            "Database error persisting RiskAlert id=%s: %s (trace_id: %s)",
            alert_uuid,
            exc,
            effective_trace,
            extra={"trace_id": effective_trace},
        )
        raise KafkaMessageProcessingError(
            f"Failed to persist RiskAlert to database: {exc}",
            details={"alert_id": str(alert_uuid)},
        ) from exc


def create_risk_alert_consumer_handler(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[ConsumedMessage], Coroutine[Any, Any, RiskAlertModel]]:
    """Factory creating an asynchronous consumer message handler for the 'risk-alerts' topic.

    Args:
        session_factory: Bound SQLAlchemy async_sessionmaker.

    Returns:
        Async handler callable accepting ConsumedMessage and returning persisted RiskAlertModel.
    """

    async def _handle_risk_alert(message: ConsumedMessage) -> RiskAlertModel:
        trace_id = message.headers.get("X-Trace-ID") or message.headers.get("trace_id")
        async with session_factory() as session:
            return await persist_risk_alert(
                event_payload=message.value,
                session=session,
                trace_id=trace_id,
            )

    return _handle_risk_alert
