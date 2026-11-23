"""Unit tests for Alert Deduplication and Management Service (P7-4).

Verifies:
- Alert deduplication: same supplier + component within 1-hour window collapses to one alert.
- The Triad of Responsibility (BR-RULE-001): 100% deterministic pure Python logic. Zero LLMs.
- Monetary & Inventory precision: Decimal precision across days_of_cover and financial_exposure.
- Severity escalation: duplicate signal with worse risk metrics escalates existing alert level.
- Window boundary enforcement: signals outside 1-hour window create new distinct alerts.
- Supplier and SKU isolation: differing SKUs or differing suppliers never collapse together.
- Terminal status isolation: closed/resolved alerts do not absorb new disruption signals.
- Canonical NanoCore golden scenario: 3 successive disruption signals collapse into 1 master alert.
- Layered Redis caching: fast-path deduplication keys with 1-hour TTL, gracefully degrading to Aurora.
- 100% statement and branch coverage on src/services/alert_service.py.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from src.database.models import Base, Supplier
from src.database.repositories.risk_alert_repository import RiskAlertRepository
from src.database.repositories.supplier_repository import SupplierRepository
from src.kafka.schemas.risk_alert import RiskAlert as RiskAlertSchema
from src.kafka.schemas.risk_alert import RiskLevel
from src.services.alert_service import (
    DEFAULT_DEDUPLICATION_WINDOW_SECONDS,
    AlertAction,
    AlertCreateInput,
    AlertDeduplicationResult,
    AlertService,
    InvalidAlertOperationError,
)


class MockRedisAsync:
    """In-memory mock for redis.asyncio.Redis supporting deduplication keys, TTL, and outage simulation."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.simulate_failure: bool = False
        self.call_count: dict[str, int] = {
            "get": 0,
            "set": 0,
            "delete": 0,
        }

    async def get(self, name: str) -> str | None:
        self.call_count["get"] += 1
        if self.simulate_failure:
            raise ConnectionError("Simulated Redis connection failure")
        return self.store.get(name)

    async def set(
        self,
        name: str,
        value: str,
        ex: int | None = None,
        px: int | None = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        _ = (px, nx, xx)
        self.call_count["set"] += 1
        if self.simulate_failure:
            raise ConnectionError("Simulated Redis connection failure")
        self.store[name] = value
        if ex is not None:
            self.ttls[name] = ex
        return True

    async def delete(self, *names: str) -> int:
        self.call_count["delete"] += 1
        if self.simulate_failure:
            raise ConnectionError("Simulated Redis connection failure")
        count = 0
        for name in names:
            if name in self.store:
                del self.store[name]
                self.ttls.pop(name, None)
                count += 1
        return count

    async def close(self) -> None:
        pass


@pytest_asyncio.fixture
async def async_db_engine():
    """In-memory SQLite async engine for isolated unit testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(async_db_engine: Any) -> async_sessionmaker[AsyncSession]:
    """Async sessionmaker bound to in-memory database."""
    return async_sessionmaker(async_db_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
def mock_redis() -> MockRedisAsync:
    """Fixture providing isolated in-memory mock Redis instance."""
    return MockRedisAsync()


@pytest_asyncio.fixture
async def seeded_supplier(
    session_factory: async_sessionmaker[AsyncSession],
) -> Supplier:
    """Seed NanoCore supplier record in database."""
    async with session_factory() as session:
        repo = SupplierRepository(session)
        supp = Supplier(
            id=uuid.uuid4(),
            name="NanoCore Semiconductor Ltd",
            country_code="TW",
            tier=2,
            risk_score=Decimal("0.885"),
            neptune_node_id="SUP-NC-001",
        )
        return await repo.create(supp)


@pytest.fixture
def alert_service(
    session_factory: async_sessionmaker[AsyncSession], mock_redis: MockRedisAsync
) -> AlertService:
    """Fixture providing configured AlertService with mock Redis and async DB."""
    return AlertService(
        session_factory=session_factory,
        redis_client=mock_redis,
        dedup_window_seconds=DEFAULT_DEDUPLICATION_WINDOW_SECONDS,
    )


# ==============================================================================
# 1. Deduplication Core Lifecycle Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_create_alert_when_none_exists(
    alert_service: AlertService, seeded_supplier: Supplier, mock_redis: MockRedisAsync
) -> None:
    """Verify first alert for a component and supplier creates a new RiskAlert record."""
    input_data = AlertCreateInput(
        supplier_id=seeded_supplier.id,
        component_sku="SKU-MCU-4402",
        risk_level=RiskLevel.CRITICAL,
        days_of_cover=Decimal("7.68"),
        financial_exposure=Decimal("2448105.00"),
        shortage_volume=24420,
    )

    result: AlertDeduplicationResult = await alert_service.process_alert(input_data)

    assert result.is_duplicate is False
    assert result.action == AlertAction.CREATED
    assert result.alert.component_sku == "SKU-MCU-4402"
    assert result.alert.supplier_id == seeded_supplier.id
    assert result.alert.risk_level == "CRITICAL"
    assert result.alert.financial_exposure == Decimal("2448105.00")
    assert result.alert.days_of_cover == Decimal("7.68")
    assert result.alert.status == "OPEN"

    # Verify Redis deduplication key populated with 1-hour TTL (3600s)
    cache_key = alert_service.format_dedup_key(seeded_supplier.id, "SKU-MCU-4402")
    assert cache_key in mock_redis.store
    assert mock_redis.ttls[cache_key] == DEFAULT_DEDUPLICATION_WINDOW_SECONDS


@pytest.mark.asyncio
async def test_deduplicate_identical_alert_within_1_hour_collapses(
    alert_service: AlertService,
    seeded_supplier: Supplier,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verify second identical signal within 1 hour collapses into existing alert with zero DB duplicate."""
    now = datetime.now(UTC)

    # Initial Alert
    first_input = AlertCreateInput(
        supplier_id=seeded_supplier.id,
        component_sku="SKU-MCU-4402",
        risk_level=RiskLevel.HIGH,
        days_of_cover=Decimal("8.00"),
        financial_exposure=Decimal("500000.00"),
        shortage_volume=5000,
        timestamp=now,
    )
    first_result = await alert_service.process_alert(first_input)
    assert first_result.action == AlertAction.CREATED
    initial_id = first_result.alert.id

    # Duplicate Alert 20 minutes later
    second_input = AlertCreateInput(
        supplier_id=seeded_supplier.id,
        component_sku="SKU-MCU-4402",
        risk_level=RiskLevel.HIGH,
        days_of_cover=Decimal("8.00"),
        financial_exposure=Decimal("500000.00"),
        shortage_volume=5000,
        timestamp=now + timedelta(minutes=20),
    )
    second_result = await alert_service.process_alert(second_input)

    assert second_result.is_duplicate is True
    assert second_result.action == AlertAction.COLLAPSED
    assert second_result.alert.id == initial_id
    assert second_result.alert.financial_exposure == Decimal("500000.00")

    # Assert exactly 1 row exists in the database table
    async with session_factory() as session:
        repo = RiskAlertRepository(session)
        alerts = await repo.get_by_component_sku("SKU-MCU-4402")
        assert len(alerts) == 1
        assert alerts[0].id == initial_id


@pytest.mark.asyncio
async def test_deduplicate_escalates_severity_on_worse_metrics(
    alert_service: AlertService,
    seeded_supplier: Supplier,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verify duplicate signal reporting higher severity escalates the existing master alert."""
    now = datetime.now(UTC)

    # Initial signal: MEDIUM severity ($200k exposure, 12 days cover)
    alert1 = await alert_service.process_alert(
        AlertCreateInput(
            supplier_id=seeded_supplier.id,
            component_sku="SKU-MCU-4402",
            risk_level=RiskLevel.MEDIUM,
            days_of_cover=Decimal("12.00"),
            financial_exposure=Decimal("200000.00"),
            shortage_volume=2000,
            timestamp=now,
        )
    )
    assert alert1.alert.risk_level == "MEDIUM"

    # Escalation signal 15 minutes later: CRITICAL ($2.45M exposure, 7.68 days cover)
    alert2 = await alert_service.process_alert(
        AlertCreateInput(
            supplier_id=seeded_supplier.id,
            component_sku="SKU-MCU-4402",
            risk_level=RiskLevel.CRITICAL,
            days_of_cover=Decimal("7.68"),
            financial_exposure=Decimal("2448105.00"),
            shortage_volume=24420,
            timestamp=now + timedelta(minutes=15),
        )
    )

    assert alert2.is_duplicate is True
    assert alert2.action == AlertAction.ESCALATED
    assert alert2.alert.id == alert1.alert.id
    assert alert2.alert.risk_level == "CRITICAL"
    assert alert2.alert.financial_exposure == Decimal("2448105.00")
    assert alert2.alert.days_of_cover == Decimal("7.68")
    assert alert2.alert.shortage_volume == 24420

    # Verify persisted in database with escalated values
    async with session_factory() as session:
        repo = RiskAlertRepository(session)
        queried = await repo.get_by_id(alert1.alert.id)
        assert queried is not None
        assert queried.risk_level == "CRITICAL"
        assert queried.financial_exposure == Decimal("2448105.00")


@pytest.mark.asyncio
async def test_deduplicate_preserves_worse_metrics_on_milder_second_alert(
    alert_service: AlertService, seeded_supplier: Supplier
) -> None:
    """Verify duplicate with lower exposure does not dilute an already CRITICAL alert."""
    now = datetime.now(UTC)

    # First alert: CRITICAL ($2.45M)
    first = await alert_service.process_alert(
        AlertCreateInput(
            supplier_id=seeded_supplier.id,
            component_sku="SKU-MCU-4402",
            risk_level=RiskLevel.CRITICAL,
            days_of_cover=Decimal("7.68"),
            financial_exposure=Decimal("2448105.00"),
            shortage_volume=24420,
            timestamp=now,
        )
    )
    assert first.action == AlertAction.CREATED

    # Second alert 30 min later: reports milder numbers (MEDIUM, $150k)
    second = await alert_service.process_alert(
        AlertCreateInput(
            supplier_id=seeded_supplier.id,
            component_sku="SKU-MCU-4402",
            risk_level=RiskLevel.MEDIUM,
            days_of_cover=Decimal("15.00"),
            financial_exposure=Decimal("150000.00"),
            shortage_volume=1000,
            timestamp=now + timedelta(minutes=30),
        )
    )

    assert second.is_duplicate is True
    assert second.action == AlertAction.COLLAPSED
    # Retains CRITICAL and worst exposure
    assert second.alert.risk_level == "CRITICAL"
    assert second.alert.financial_exposure == Decimal("2448105.00")
    assert second.alert.days_of_cover == Decimal("7.68")


# ==============================================================================
# 2. Window and Isolation Boundaries
# ==============================================================================


@pytest.mark.asyncio
async def test_alerts_outside_1_hour_window_do_not_deduplicate(
    alert_service: AlertService,
    seeded_supplier: Supplier,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verify signal arriving outside 1-hour window (e.g. 65 min later) creates a new alert."""
    now = datetime.now(UTC)

    alert1 = await alert_service.process_alert(
        AlertCreateInput(
            supplier_id=seeded_supplier.id,
            component_sku="SKU-MCU-4402",
            risk_level=RiskLevel.HIGH,
            days_of_cover=Decimal("8.00"),
            financial_exposure=Decimal("500000.00"),
            timestamp=now,
        )
    )

    # Signal 65 minutes later (outside 1-hour window)
    alert2 = await alert_service.process_alert(
        AlertCreateInput(
            supplier_id=seeded_supplier.id,
            component_sku="SKU-MCU-4402",
            risk_level=RiskLevel.HIGH,
            days_of_cover=Decimal("7.50"),
            financial_exposure=Decimal("600000.00"),
            timestamp=now + timedelta(minutes=65),
        )
    )

    assert alert2.is_duplicate is False
    assert alert2.action == AlertAction.CREATED
    assert alert2.alert.id != alert1.alert.id

    async with session_factory() as session:
        repo = RiskAlertRepository(session)
        records = await repo.get_by_component_sku("SKU-MCU-4402")
        assert len(records) == 2


@pytest.mark.asyncio
async def test_alerts_different_sku_same_supplier_do_not_deduplicate(
    alert_service: AlertService, seeded_supplier: Supplier
) -> None:
    """Verify different component SKUs for the same supplier create independent alerts."""
    now = datetime.now(UTC)

    res1 = await alert_service.process_alert(
        AlertCreateInput(
            supplier_id=seeded_supplier.id,
            component_sku="SKU-MCU-4402",
            risk_level=RiskLevel.HIGH,
            timestamp=now,
        )
    )
    res2 = await alert_service.process_alert(
        AlertCreateInput(
            supplier_id=seeded_supplier.id,
            component_sku="SKU-POWER-PMIC-01",
            risk_level=RiskLevel.HIGH,
            timestamp=now + timedelta(minutes=10),
        )
    )

    assert res1.action == AlertAction.CREATED
    assert res2.action == AlertAction.CREATED
    assert res1.alert.id != res2.alert.id


@pytest.mark.asyncio
async def test_alerts_different_supplier_same_sku_do_not_deduplicate(
    alert_service: AlertService,
    seeded_supplier: Supplier,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verify distinct suppliers supplying the same component SKU create separate alerts."""
    # Create second supplier
    async with session_factory() as session:
        repo = SupplierRepository(session)
        supp2 = await repo.create(
            Supplier(
                id=uuid.uuid4(),
                name="BetaElectro Systems",
                country_code="DE",
                tier=1,
                risk_score=Decimal("0.450"),
            )
        )

    now = datetime.now(UTC)
    res1 = await alert_service.process_alert(
        AlertCreateInput(
            supplier_id=seeded_supplier.id,
            component_sku="SKU-COMMON-RESISTOR",
            risk_level=RiskLevel.MEDIUM,
            timestamp=now,
        )
    )
    res2 = await alert_service.process_alert(
        AlertCreateInput(
            supplier_id=supp2.id,
            component_sku="SKU-COMMON-RESISTOR",
            risk_level=RiskLevel.MEDIUM,
            timestamp=now + timedelta(minutes=5),
        )
    )

    assert res1.action == AlertAction.CREATED
    assert res2.action == AlertAction.CREATED
    assert res1.alert.id != res2.alert.id


@pytest.mark.asyncio
async def test_closed_or_resolved_alert_does_not_deduplicate(
    alert_service: AlertService, seeded_supplier: Supplier
) -> None:
    """Verify resolved or closed alert does not absorb new incoming disruptions."""
    now = datetime.now(UTC)

    first = await alert_service.process_alert(
        AlertCreateInput(
            supplier_id=seeded_supplier.id,
            component_sku="SKU-MCU-4402",
            risk_level=RiskLevel.HIGH,
            timestamp=now,
        )
    )

    # Transition alert to RESOLVED
    await alert_service.update_alert_status(first.alert.id, "RESOLVED")

    # New disruption signal 10 minutes later
    second = await alert_service.process_alert(
        AlertCreateInput(
            supplier_id=seeded_supplier.id,
            component_sku="SKU-MCU-4402",
            risk_level=RiskLevel.HIGH,
            timestamp=now + timedelta(minutes=10),
        )
    )

    assert second.is_duplicate is False
    assert second.action == AlertAction.CREATED
    assert second.alert.id != first.alert.id
    assert second.alert.status == "OPEN"


# ==============================================================================
# 3. NanoCore Canonical Golden Scenario
# ==============================================================================


@pytest.mark.asyncio
async def test_nanocore_golden_scenario_three_events_collapse_to_one(
    alert_service: AlertService,
    seeded_supplier: Supplier,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verify 3 sequential NanoCore disruption signals within 45 minutes collapse to 1 master alert.

    NanoCore canonical scenario:
    - Event 1 (T=0m): Cleanroom fire news signal -> CRITICAL ($2,448,105.00 exposure, 7.68 days cover)
    - Event 2 (T=15m): Plant MES buffer warning -> CRITICAL ($2,448,105.00 exposure, 7.68 days cover)
    - Event 3 (T=40m): Logistics shipment ETA delay -> CRITICAL ($2,448,105.00 exposure, 7.68 days cover)
    Result: Exactly 1 alert in database with exact NanoCore golden metrics.
    """
    t0 = datetime.now(UTC)

    # Event 1: Cleanroom fire news signal
    e1 = await alert_service.process_alert(
        AlertCreateInput(
            supplier_id=seeded_supplier.id,
            component_sku="SKU-MCU-4402",
            risk_level=RiskLevel.CRITICAL,
            days_of_cover=Decimal("7.68"),
            financial_exposure=Decimal("2448105.00"),
            shortage_volume=24420,
            source="NEWS_WIRE_REUTERS",
            timestamp=t0,
        )
    )
    assert e1.action == AlertAction.CREATED

    # Event 2: Plant MES buffer warning at +15m
    e2 = await alert_service.process_alert(
        AlertCreateInput(
            supplier_id=seeded_supplier.id,
            component_sku="SKU-MCU-4402",
            risk_level=RiskLevel.CRITICAL,
            days_of_cover=Decimal("7.68"),
            financial_exposure=Decimal("2448105.00"),
            shortage_volume=24420,
            source="PLANT_MES_MUNICH",
            timestamp=t0 + timedelta(minutes=15),
        )
    )
    assert e2.action == AlertAction.COLLAPSED
    assert e2.alert.id == e1.alert.id

    # Event 3: Logistics shipment ETA delay at +40m
    e3 = await alert_service.process_alert(
        AlertCreateInput(
            supplier_id=seeded_supplier.id,
            component_sku="SKU-MCU-4402",
            risk_level=RiskLevel.CRITICAL,
            days_of_cover=Decimal("7.68"),
            financial_exposure=Decimal("2448105.00"),
            shortage_volume=24420,
            source="SAP_LOGISTICS_EDI",
            timestamp=t0 + timedelta(minutes=40),
        )
    )
    assert e3.action == AlertAction.COLLAPSED
    assert e3.alert.id == e1.alert.id

    # Verify single persistent master alert in Aurora
    async with session_factory() as session:
        repo = RiskAlertRepository(session)
        alerts = await repo.get_by_component_sku("SKU-MCU-4402")
        assert len(alerts) == 1
        master = alerts[0]
        assert master.id == e1.alert.id
        assert master.risk_level == "CRITICAL"
        assert master.days_of_cover == Decimal("7.68")
        assert master.financial_exposure == Decimal("2448105.00")
        assert master.shortage_volume == 24420


# ==============================================================================
# 4. Redis Fast Deduplication & Outage Fault Tolerance
# ==============================================================================


@pytest.mark.asyncio
async def test_fast_deduplication_via_redis_cache(
    alert_service: AlertService, seeded_supplier: Supplier, mock_redis: MockRedisAsync
) -> None:
    """Verify Redis deduplication key hit bypasses Aurora search scan."""
    now = datetime.now(UTC)

    # First event sets key in Redis
    res1 = await alert_service.process_alert(
        AlertCreateInput(
            supplier_id=seeded_supplier.id,
            component_sku="SKU-MCU-4402",
            risk_level=RiskLevel.HIGH,
            timestamp=now,
        )
    )
    cache_key = alert_service.format_dedup_key(seeded_supplier.id, "SKU-MCU-4402")
    assert cache_key in mock_redis.store
    assert mock_redis.call_count["get"] == 1

    # Second event hits Redis key directly
    res2 = await alert_service.process_alert(
        AlertCreateInput(
            supplier_id=seeded_supplier.id,
            component_sku="SKU-MCU-4402",
            risk_level=RiskLevel.HIGH,
            timestamp=now + timedelta(minutes=5),
        )
    )
    assert res2.is_duplicate is True
    assert res2.alert.id == res1.alert.id
    assert mock_redis.call_count["get"] == 2


@pytest.mark.asyncio
async def test_redis_outage_graceful_fallback_to_aurora_dedup(
    alert_service: AlertService, seeded_supplier: Supplier, mock_redis: MockRedisAsync
) -> None:
    """Verify deduplication works via Aurora database query when Redis is down."""
    now = datetime.now(UTC)

    # First event
    res1 = await alert_service.process_alert(
        AlertCreateInput(
            supplier_id=seeded_supplier.id,
            component_sku="SKU-MCU-4402",
            risk_level=RiskLevel.HIGH,
            timestamp=now,
        )
    )

    # Simulate Redis failure
    mock_redis.simulate_failure = True

    # Second event within window should still collapse via Aurora
    res2 = await alert_service.process_alert(
        AlertCreateInput(
            supplier_id=seeded_supplier.id,
            component_sku="SKU-MCU-4402",
            risk_level=RiskLevel.HIGH,
            timestamp=now + timedelta(minutes=10),
        )
    )

    assert res2.is_duplicate is True
    assert res2.action == AlertAction.COLLAPSED
    assert res2.alert.id == res1.alert.id


# ==============================================================================
# 5. Queries, Status Transitions, and Invalidation
# ==============================================================================


@pytest.mark.asyncio
async def test_status_transition_lifecycle_and_redis_purge(
    alert_service: AlertService, seeded_supplier: Supplier, mock_redis: MockRedisAsync
) -> None:
    """Verify transition to terminal status (CLOSED) clears Redis deduplication key."""
    res = await alert_service.process_alert(
        AlertCreateInput(
            supplier_id=seeded_supplier.id,
            component_sku="SKU-MCU-4402",
            risk_level=RiskLevel.HIGH,
        )
    )
    cache_key = alert_service.format_dedup_key(seeded_supplier.id, "SKU-MCU-4402")
    assert cache_key in mock_redis.store

    # Transition to CLOSED
    updated = await alert_service.update_alert_status(res.alert.id, "CLOSED")
    assert updated.status == "CLOSED"
    assert cache_key not in mock_redis.store


@pytest.mark.asyncio
async def test_list_and_filter_alerts(
    alert_service: AlertService, seeded_supplier: Supplier
) -> None:
    """Verify query methods: list_active_alerts, get_by_sku, get_by_supplier."""
    a1 = await alert_service.process_alert(
        AlertCreateInput(
            supplier_id=seeded_supplier.id,
            component_sku="SKU-PART-A",
            risk_level=RiskLevel.CRITICAL,
        )
    )
    a2 = await alert_service.process_alert(
        AlertCreateInput(
            supplier_id=seeded_supplier.id,
            component_sku="SKU-PART-B",
            risk_level=RiskLevel.LOW,
        )
    )
    assert a2.action == AlertAction.CREATED

    active = await alert_service.list_active_alerts()
    assert len(active) >= 2

    by_sku = await alert_service.list_alerts_by_sku("SKU-PART-A")
    assert len(by_sku) == 1
    assert by_sku[0].id == a1.alert.id

    by_supp = await alert_service.list_alerts_by_supplier(seeded_supplier.id)
    assert len(by_supp) >= 2


@pytest.mark.asyncio
async def test_ingest_alert_from_schema_event(
    alert_service: AlertService, seeded_supplier: Supplier
) -> None:
    """Verify AlertService can directly ingest Pydantic RiskAlert event schemas."""
    schema_event = RiskAlertSchema(
        alert_id=str(uuid.uuid4()),
        supplier_id=str(seeded_supplier.id),
        component_sku="SKU-SCHEMA-TEST",
        risk_level=RiskLevel.CRITICAL,
        days_of_cover=Decimal("7.68"),
        financial_exposure=Decimal("2448105.00"),
        shortage_volume=24420,
    )

    result = await alert_service.ingest_event(schema_event)
    assert result.action == AlertAction.CREATED
    assert result.alert.component_sku == "SKU-SCHEMA-TEST"
    assert result.alert.financial_exposure == Decimal("2448105.00")


def test_invalid_alert_inputs_raise_errors() -> None:
    """Verify validation traps empty SKU, negative exposure, or invalid status."""
    with pytest.raises(InvalidAlertOperationError, match="Component SKU cannot be empty"):
        AlertCreateInput(
            component_sku="",
            risk_level=RiskLevel.HIGH,
        )

    with pytest.raises(InvalidAlertOperationError, match="Financial exposure cannot be negative"):
        AlertCreateInput(
            component_sku="SKU-TEST",
            risk_level=RiskLevel.HIGH,
            financial_exposure=Decimal("-100.00"),
        )

    with pytest.raises(InvalidAlertOperationError, match="Days of cover cannot be negative"):
        AlertCreateInput(
            component_sku="SKU-TEST",
            risk_level=RiskLevel.HIGH,
            days_of_cover=Decimal("-1.00"),
        )

    with pytest.raises(InvalidAlertOperationError, match="Shortage volume cannot be negative"):
        AlertCreateInput(
            component_sku="SKU-TEST",
            risk_level=RiskLevel.HIGH,
            shortage_volume=-10,
        )


def test_alert_create_input_normalization() -> None:
    """Verify AlertCreateInput normalizes naive datetimes and UUID strings."""
    # Naive timestamp
    naive_dt = datetime(2026, 11, 23, 10, 0, 0)
    uid = uuid.uuid4()
    inp = AlertCreateInput(
        component_sku="SKU-NORM",
        risk_level="HIGH",
        supplier_id=str(uid),
        timestamp=naive_dt,
    )
    assert inp.timestamp.tzinfo is UTC
    assert inp.supplier_id == uid

    # Non-UUID string supplier_id
    inp_invalid_uid = AlertCreateInput(
        component_sku="SKU-NORM",
        risk_level="HIGH",
        supplier_id="NOT-A-UUID",
    )
    assert inp_invalid_uid.supplier_id is None


@pytest.mark.asyncio
async def test_alert_service_without_redis(
    session_factory: async_sessionmaker[AsyncSession], seeded_supplier: Supplier
) -> None:
    """Verify AlertService operates flawlessly when no Redis client is configured."""
    service = AlertService(session_factory=session_factory, redis_client=None)

    # Creation
    res1 = await service.process_alert(
        AlertCreateInput(
            supplier_id=seeded_supplier.id,
            component_sku="SKU-NO-REDIS",
            risk_level=RiskLevel.HIGH,
        )
    )
    assert res1.action == AlertAction.CREATED

    # Duplicate within window
    res2 = await service.process_alert(
        AlertCreateInput(
            supplier_id=seeded_supplier.id,
            component_sku="SKU-NO-REDIS",
            risk_level=RiskLevel.HIGH,
        )
    )
    assert res2.action == AlertAction.COLLAPSED
    assert res2.alert.id == res1.alert.id


@pytest.mark.asyncio
async def test_update_alert_status_validation_and_not_found(
    alert_service: AlertService,
) -> None:
    """Verify update_alert_status rejects invalid statuses and missing alert IDs."""
    fake_id = uuid.uuid4()

    with pytest.raises(InvalidAlertOperationError, match="Invalid status 'INVALID_STATUS'"):
        await alert_service.update_alert_status(fake_id, "INVALID_STATUS")

    with pytest.raises(InvalidAlertOperationError, match="Alert not found with ID"):
        await alert_service.update_alert_status(fake_id, "CLOSED")


@pytest.mark.asyncio
async def test_redis_edge_cases_bytes_and_corruption(
    session_factory: async_sessionmaker[AsyncSession], seeded_supplier: Supplier
) -> None:
    """Verify handling of bytes responses from Redis and corrupted cache keys."""
    mock_redis = MockRedisAsync()
    service = AlertService(session_factory=session_factory, redis_client=mock_redis)

    # 1. Create alert
    res = await service.process_alert(
        AlertCreateInput(
            supplier_id=seeded_supplier.id,
            component_sku="SKU-BYTES-TEST",
            risk_level=RiskLevel.HIGH,
        )
    )
    key = service.format_dedup_key(seeded_supplier.id, "SKU-BYTES-TEST")

    # Manually store as bytes in mock
    mock_redis.store[key] = str(res.alert.id).encode("utf-8")  # type: ignore[assignment]
    res_bytes = await service.process_alert(
        AlertCreateInput(
            supplier_id=seeded_supplier.id,
            component_sku="SKU-BYTES-TEST",
            risk_level=RiskLevel.HIGH,
        )
    )
    assert res_bytes.is_duplicate is True

    # 2. Corrupt Redis key with non-UUID string
    mock_redis.store[key] = "CORRUPTED-UUID-NOT-VALID"
    res_corrupt = await service.process_alert(
        AlertCreateInput(
            supplier_id=seeded_supplier.id,
            component_sku="SKU-BYTES-TEST",
            risk_level=RiskLevel.HIGH,
        )
    )
    assert res_corrupt.is_duplicate is True  # Falls back to Aurora repository scan!

    # 3. Cached UUID points to nonexistent DB record
    mock_redis.store[key] = str(uuid.uuid4())
    res_missing_db = await service.process_alert(
        AlertCreateInput(
            supplier_id=seeded_supplier.id,
            component_sku="SKU-BYTES-TEST",
            risk_level=RiskLevel.HIGH,
        )
    )
    assert res_missing_db.is_duplicate is True

    # 4. Redis delete failure during status transition
    mock_redis.simulate_failure = True
    updated = await service.update_alert_status(res.alert.id, "CLOSED")
    assert updated.status == "CLOSED"

    # 5. Safe delete when redis_client is None
    service_no_redis = AlertService(session_factory=session_factory, redis_client=None)
    deleted = await service_no_redis._safe_redis_delete("any-key")
    assert deleted is False


@pytest.mark.asyncio
async def test_escalation_when_initial_alert_fields_were_none(
    alert_service: AlertService, seeded_supplier: Supplier
) -> None:
    """Verify metrics escalation when existing alert had None values for exposure/cover/volume."""
    # Alert with None exposure, cover, and volume
    first = await alert_service.process_alert(
        AlertCreateInput(
            supplier_id=seeded_supplier.id,
            component_sku="SKU-NONE-METRICS",
            risk_level=RiskLevel.LOW,
        )
    )
    assert first.alert.financial_exposure is None
    assert first.alert.days_of_cover is None
    assert first.alert.shortage_volume is None

    # Second alert supplies metrics -> escalates
    second = await alert_service.process_alert(
        AlertCreateInput(
            supplier_id=seeded_supplier.id,
            component_sku="SKU-NONE-METRICS",
            risk_level=RiskLevel.HIGH,
            financial_exposure=Decimal("150000.00"),
            days_of_cover=Decimal("5.00"),
            shortage_volume=1000,
        )
    )
    assert second.action == AlertAction.ESCALATED
    assert second.alert.financial_exposure == Decimal("150000.00")
    assert second.alert.days_of_cover == Decimal("5.00")
    assert second.alert.shortage_volume == 1000


@pytest.mark.asyncio
async def test_ingest_event_with_non_uuid_supplier(
    alert_service: AlertService,
) -> None:
    """Verify ingest_event handles non-UUID supplier identifier strings safely."""
    schema_event = RiskAlertSchema(
        alert_id=str(uuid.uuid4()),
        supplier_id="SUP-STRING-ID",
        component_sku="SKU-NON-UUID-SUPP",
        risk_level=RiskLevel.MEDIUM,
        days_of_cover=Decimal("10.00"),
    )
    result = await alert_service.ingest_event(schema_event)
    assert result.action == AlertAction.CREATED
    assert result.alert.supplier_id is None
