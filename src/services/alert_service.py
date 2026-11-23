"""Alert Deduplication and Management Service.

Implements real-time alert deduplication, severity escalation, and rolling window
collapsing adhering to the Triad of Responsibility (BR-RULE-001).

Guarantees:
- 100% deterministic pure Python arithmetic and comparison logic. Zero LLMs.
- Monetary values and inventory coverage retain strict Decimal precision.
- Incoming alerts for the same (supplier_id, component_sku) within the rolling window
  (default 1 hour / 3600 seconds) collapse into a single master alert record.
- Duplicate alerts reporting worse risk severity (CRITICAL > HIGH > MEDIUM > LOW)
  or higher financial exposure escalate the master alert.
- Terminal statuses (CLOSED, RESOLVED, DISMISSED) purge Redis deduplication keys
  and do not absorb new incoming disruptions.
- Layered Redis caching provides sub-millisecond deduplication with graceful fallback
  to Aurora PostgreSQL on cache outage.
"""

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.database.models import RiskAlert
from src.database.repositories.risk_alert_repository import RiskAlertRepository
from src.kafka.schemas.risk_alert import RiskAlert as RiskAlertSchema
from src.kafka.schemas.risk_alert import RiskLevel

logger = logging.getLogger(__name__)

DEFAULT_DEDUPLICATION_WINDOW_SECONDS: int = 3600

SEVERITY_RANKS: dict[str, int] = {
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "CRITICAL": 4,
}

VALID_STATUSES: frozenset[str] = frozenset(
    {"OPEN", "INVESTIGATING", "MITIGATED", "RESOLVED", "CLOSED", "DISMISSED"}
)

TERMINAL_STATUSES: frozenset[str] = frozenset({"RESOLVED", "CLOSED", "DISMISSED"})


class AlertAction(StrEnum):
    """Action outcome resulting from alert deduplication processing."""

    CREATED = "CREATED"
    COLLAPSED = "COLLAPSED"
    ESCALATED = "ESCALATED"


class AlertServiceError(Exception):
    """Base exception for alert service operations."""


class InvalidAlertOperationError(AlertServiceError):
    """Raised when an alert operation or input payload violates business invariants."""


@dataclass
class AlertCreateInput:
    """Input payload for ingesting or creating a risk alert."""

    component_sku: str
    risk_level: RiskLevel | str
    supplier_id: uuid.UUID | str | None = None
    days_of_cover: Decimal | None = None
    financial_exposure: Decimal | None = None
    shortage_volume: int | None = None
    source: str | None = None
    timestamp: datetime | None = None

    def __post_init__(self) -> None:
        """Validate input constraints and normalize timestamps."""
        if not self.component_sku or not self.component_sku.strip():
            raise InvalidAlertOperationError("Component SKU cannot be empty")

        if self.financial_exposure is not None and self.financial_exposure < Decimal("0.00"):
            raise InvalidAlertOperationError("Financial exposure cannot be negative")

        if self.days_of_cover is not None and self.days_of_cover < Decimal("0.00"):
            raise InvalidAlertOperationError("Days of cover cannot be negative")

        if self.shortage_volume is not None and self.shortage_volume < 0:
            raise InvalidAlertOperationError("Shortage volume cannot be negative")

        # Normalize supplier_id if passed as string
        if isinstance(self.supplier_id, str) and self.supplier_id.strip():
            try:
                self.supplier_id = uuid.UUID(self.supplier_id)
            except ValueError:
                self.supplier_id = None

        # Normalize timestamp
        if self.timestamp is None:
            self.timestamp = datetime.now(UTC)
        elif self.timestamp.tzinfo is None:
            self.timestamp = self.timestamp.replace(tzinfo=UTC)


@dataclass
class AlertDeduplicationResult:
    """Result returned by AlertService describing deduplication action and target alert."""

    is_duplicate: bool
    action: AlertAction
    alert: RiskAlert
    previous_alert_id: uuid.UUID | None = None
    dedup_key: str | None = None


class AlertService:
    """Service orchestrating alert creation, deduplication, and lifecycle transitions."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        redis_client: Any | None = None,
        dedup_window_seconds: int = DEFAULT_DEDUPLICATION_WINDOW_SECONDS,
    ) -> None:
        """Initialize AlertService with async database sessionmaker and optional Redis client."""
        self.session_factory = session_factory
        self.redis_client = redis_client
        self.dedup_window_seconds = dedup_window_seconds

    def format_dedup_key(self, supplier_id: uuid.UUID | str | None, component_sku: str) -> str:
        """Format consistent Redis deduplication cache key."""
        supp_part = str(supplier_id) if supplier_id else "none"
        return f"alert:dedup:{supp_part}:{component_sku}"

    async def _safe_redis_get(self, key: str) -> str | None:
        """Safely fetch string value from Redis, logging warnings on cache failure."""
        if self.redis_client is None:
            return None
        try:
            val = await self.redis_client.get(key)
            if val is None:
                return None
            if isinstance(val, bytes):
                return val.decode("utf-8")
            return str(val)
        except Exception as exc:
            logger.warning(
                "Redis GET failed for key %s (falling back to database scan): %s", key, exc
            )
            return None

    async def _safe_redis_set(self, key: str, value: str, ex: int | None = None) -> bool:
        """Safely write string value to Redis with TTL, logging warnings on cache failure."""
        if self.redis_client is None:
            return False
        try:
            await self.redis_client.set(key, value, ex=ex)
            return True
        except Exception as exc:
            logger.warning("Redis SET failed for key %s: %s", key, exc)
            return False

    async def _safe_redis_delete(self, key: str) -> bool:
        """Safely delete key from Redis, logging warnings on cache failure."""
        if self.redis_client is None:
            return False
        try:
            await self.redis_client.delete(key)
            return True
        except Exception as exc:
            logger.warning("Redis DELETE failed for key %s: %s", key, exc)
            return False

    async def process_alert(self, input_data: AlertCreateInput) -> AlertDeduplicationResult:
        """Process incoming risk signal, collapsing duplicates within rolling window."""
        ref_time = input_data.timestamp or datetime.now(UTC)
        cache_key = self.format_dedup_key(input_data.supplier_id, input_data.component_sku)

        # 1. Fast-path lookup via Redis deduplication key
        candidate_alert: RiskAlert | None = None
        cached_id_str = await self._safe_redis_get(cache_key)

        async with self.session_factory() as session:
            repo = RiskAlertRepository(session)

            if cached_id_str:
                try:
                    cached_uuid = uuid.UUID(cached_id_str)
                    existing = await repo.get_by_id(cached_uuid)
                    if existing is not None and existing.status in ("OPEN", "INVESTIGATING"):
                        cand_created = existing.created_at or ref_time
                        if cand_created.tzinfo is None:
                            cand_created = cand_created.replace(tzinfo=UTC)
                        diff_seconds = (ref_time - cand_created).total_seconds()
                        if -60.0 <= diff_seconds <= self.dedup_window_seconds:
                            candidate_alert = existing
                        else:
                            # Expired relative to input event timestamp; purge stale key
                            await self._safe_redis_delete(cache_key)
                    else:
                        # Terminal status or deleted; purge key
                        await self._safe_redis_delete(cache_key)
                except ValueError:
                    await self._safe_redis_delete(cache_key)

            # 2. Fallback to Aurora repository scan if Redis missed or failed
            if candidate_alert is None:
                supp_uuid = (
                    input_data.supplier_id
                    if isinstance(input_data.supplier_id, uuid.UUID)
                    else None
                )
                candidate_alert = await repo.find_recent_active_alert(
                    component_sku=input_data.component_sku,
                    supplier_id=supp_uuid,
                    window_seconds=self.dedup_window_seconds,
                    reference_time=ref_time,
                )

            # 3. Deduplication / Escalation Branch
            if candidate_alert is not None:
                escalated = False

                # Compare severity rank
                curr_rank = SEVERITY_RANKS.get(candidate_alert.risk_level.upper(), 0)
                new_level_str = (
                    input_data.risk_level.value
                    if isinstance(input_data.risk_level, RiskLevel)
                    else str(input_data.risk_level).upper()
                )
                new_rank = SEVERITY_RANKS.get(new_level_str, 0)

                if new_rank > curr_rank:
                    candidate_alert.risk_level = new_level_str
                    escalated = True

                # Compare financial exposure (higher is worse)
                if input_data.financial_exposure is not None:
                    if candidate_alert.financial_exposure is None:
                        candidate_alert.financial_exposure = input_data.financial_exposure
                        escalated = True
                    elif input_data.financial_exposure > candidate_alert.financial_exposure:
                        candidate_alert.financial_exposure = input_data.financial_exposure
                        escalated = True

                # Compare days of cover (lower is worse)
                if input_data.days_of_cover is not None:
                    if candidate_alert.days_of_cover is None:
                        candidate_alert.days_of_cover = input_data.days_of_cover
                        escalated = True
                    elif input_data.days_of_cover < candidate_alert.days_of_cover:
                        candidate_alert.days_of_cover = input_data.days_of_cover
                        escalated = True

                # Compare shortage volume (higher is worse)
                if input_data.shortage_volume is not None:
                    if candidate_alert.shortage_volume is None:
                        candidate_alert.shortage_volume = input_data.shortage_volume
                        escalated = True
                    elif input_data.shortage_volume > candidate_alert.shortage_volume:
                        candidate_alert.shortage_volume = input_data.shortage_volume
                        escalated = True

                action = AlertAction.ESCALATED if escalated else AlertAction.COLLAPSED
                updated_alert = await repo.update(candidate_alert)
                await session.commit()

                # Refresh Redis key TTL
                await self._safe_redis_set(
                    cache_key, str(updated_alert.id), ex=self.dedup_window_seconds
                )

                return AlertDeduplicationResult(
                    is_duplicate=True,
                    action=action,
                    alert=updated_alert,
                    previous_alert_id=updated_alert.id,
                    dedup_key=cache_key,
                )

            # 4. New Alert Creation Branch
            supp_uuid = (
                input_data.supplier_id if isinstance(input_data.supplier_id, uuid.UUID) else None
            )
            level_str = (
                input_data.risk_level.value
                if isinstance(input_data.risk_level, RiskLevel)
                else str(input_data.risk_level).upper()
            )

            new_alert = RiskAlert(
                id=uuid.uuid4(),
                supplier_id=supp_uuid,
                component_sku=input_data.component_sku,
                risk_level=level_str,
                days_of_cover=input_data.days_of_cover,
                financial_exposure=input_data.financial_exposure,
                shortage_volume=input_data.shortage_volume,
                status="OPEN",
                created_at=ref_time,
            )
            created_alert = await repo.create(new_alert)
            await session.commit()

            # Populate Redis deduplication key
            await self._safe_redis_set(
                cache_key, str(created_alert.id), ex=self.dedup_window_seconds
            )

            return AlertDeduplicationResult(
                is_duplicate=False,
                action=AlertAction.CREATED,
                alert=created_alert,
                dedup_key=cache_key,
            )

    async def update_alert_status(self, alert_id: uuid.UUID, new_status: str) -> RiskAlert:
        """Transition alert to a new workflow status and evict cache on terminal states."""
        status_upper = new_status.upper()
        if status_upper not in VALID_STATUSES:
            raise InvalidAlertOperationError(
                f"Invalid status '{new_status}'. Must be one of: {sorted(VALID_STATUSES)}"
            )

        async with self.session_factory() as session:
            repo = RiskAlertRepository(session)
            alert = await repo.get_by_id(alert_id)
            if alert is None:
                raise InvalidAlertOperationError(f"Alert not found with ID: {alert_id}")

            alert.status = status_upper
            updated = await repo.update(alert)
            await session.commit()

            if status_upper in TERMINAL_STATUSES:
                cache_key = self.format_dedup_key(updated.supplier_id, updated.component_sku)
                await self._safe_redis_delete(cache_key)

            return updated

    async def list_active_alerts(self, limit: int = 100) -> Sequence[RiskAlert]:
        """Fetch currently active alerts (OPEN or INVESTIGATING)."""
        async with self.session_factory() as session:
            repo = RiskAlertRepository(session)
            return await repo.get_active_alerts(limit=limit)

    async def list_alerts_by_sku(self, component_sku: str, limit: int = 100) -> Sequence[RiskAlert]:
        """Fetch alerts associated with a specific component SKU."""
        async with self.session_factory() as session:
            repo = RiskAlertRepository(session)
            return await repo.get_by_component_sku(component_sku, limit=limit)

    async def list_alerts_by_supplier(
        self, supplier_id: uuid.UUID, limit: int = 100
    ) -> Sequence[RiskAlert]:
        """Fetch alerts associated with a specific supplier UUID."""
        async with self.session_factory() as session:
            repo = RiskAlertRepository(session)
            return await repo.get_by_supplier_id(supplier_id, limit=limit)

    async def ingest_event(self, event: RiskAlertSchema) -> AlertDeduplicationResult:
        """Ingest Pydantic RiskAlert event schema directly from Kafka streams."""
        supp_uuid: uuid.UUID | None = None
        if event.supplier_id:
            try:
                supp_uuid = uuid.UUID(event.supplier_id)
            except ValueError:
                supp_uuid = None

        input_data = AlertCreateInput(
            component_sku=event.component_sku,
            risk_level=event.risk_level,
            supplier_id=supp_uuid,
            days_of_cover=event.days_of_cover,
            financial_exposure=event.financial_exposure,
            shortage_volume=event.shortage_volume,
        )
        return await self.process_alert(input_data)
