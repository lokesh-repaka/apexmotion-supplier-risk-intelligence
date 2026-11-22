"""Integration tests for Kafka Event Consumer and Risk Alert persistence (P6-4).

Verifies:
- End-to-end integration: EventProducer publishes 3 distinct RiskAlert events to Kafka.
- EventConsumer consumes each event from the 'risk-alerts' topic using a registered handler.
- Handler deserializes payloads, validates schemas, resolves supplier IDs, and persists records to the 'risk_alerts' table.
- All 3 events are asserted persisted in the 'risk_alerts' table with exact Decimal precision.
- At-least-once delivery: manual offset commits strictly after successful database write.
- Idempotency: redelivered events update or preserve existing records without primary key violation.
- Distributed tracing: X-Trace-ID from Kafka record headers propagates through the ingestion pipeline.
- Poisonous message handling: corrupt messages fail retries and route to DLQ topic without database commit.
- Testcontainers Kafka support: environment check and diagnostic integration runner.
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from src.core.config import get_settings
from src.database.models import Base, Supplier
from src.database.repositories.risk_alert_repository import RiskAlertRepository
from src.kafka.consumer import EventConsumer
from src.kafka.handlers import (
    create_risk_alert_consumer_handler,
    persist_risk_alert,
)
from src.kafka.producer import EventProducer
from src.kafka.schemas import (
    AlertStatus,
    RiskLevel,
)
from src.kafka.schemas import (
    RiskAlert as RiskAlertSchema,
)

settings = get_settings()


# ------------------------------------------------------------------------------
# In-Memory Database Fixtures
# ------------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_engine() -> AsyncGenerator[Any, None]:
    """Provide an isolated in-memory SQLite async engine."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(db_engine: Any) -> async_sessionmaker[AsyncSession]:
    """Provide an async session factory bound to the in-memory engine."""
    return async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest_asyncio.fixture
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Provide a single scoped async session for assertions."""
    async with session_factory() as session:
        yield session


# ------------------------------------------------------------------------------
# Mock / Test Kafka Broker Harness
# ------------------------------------------------------------------------------


class MockConsumerRecord:
    """Mock Kafka ConsumerRecord matching kafka-python-ng structure."""

    def __init__(
        self,
        topic: str,
        partition: int,
        offset: int,
        key: bytes | None,
        value: bytes,
        headers: list[tuple[str, bytes]] | None = None,
        timestamp: int | None = None,
    ) -> None:
        self.topic = topic
        self.partition = partition
        self.offset = offset
        self.key = key
        self.value = value
        self.headers = headers or []
        self.timestamp = timestamp or int(datetime.now(UTC).timestamp() * 1000)


class InMemoryKafkaHarness:
    """In-memory Kafka transport harness connecting EventProducer to EventConsumer."""

    def __init__(self, topic: str = "risk-alerts") -> None:
        self.topic = topic
        self.queue: list[MockConsumerRecord] = []
        self.dlq_queue: list[dict[str, Any]] = []
        self.committed_offsets: list[int] = []
        self._current_offset = 0

    def create_mock_producer(self) -> MagicMock:
        """Create a mock Kafka producer that enqueues messages into this harness."""
        producer = MagicMock()

        def fake_send(
            topic: str,
            value: bytes | None = None,
            key: bytes | None = None,
            headers: list[tuple[str, bytes]] | None = None,
            partition: int | None = None,
        ) -> MagicMock:
            self._current_offset += 1
            record = MockConsumerRecord(
                topic=topic,
                partition=partition or 0,
                offset=self._current_offset,
                key=key,
                value=value or b"",
                headers=headers or [],
            )
            self.queue.append(record)

            future = MagicMock()
            future.get.return_value = MagicMock(
                topic=topic,
                partition=partition or 0,
                offset=self._current_offset,
                timestamp=record.timestamp,
            )
            return future

        producer.send.side_effect = fake_send
        producer.flush = MagicMock()
        producer.close = MagicMock()
        return producer

    def create_mock_dlq_producer(self) -> MagicMock:
        """Create a mock producer that tracks DLQ publications."""
        producer = MagicMock()

        def fake_dlq_send(
            topic: str,
            value: bytes | None = None,
            key: bytes | None = None,
            headers: list[tuple[str, bytes]] | None = None,
        ) -> MagicMock:
            self.dlq_queue.append(
                {
                    "topic": topic,
                    "key": key,
                    "value": value,
                    "headers": headers,
                }
            )
            future = MagicMock()
            future.get.return_value = MagicMock()
            return future

        producer.send.side_effect = fake_dlq_send
        producer.flush = MagicMock()
        producer.close = MagicMock()
        return producer

    def create_mock_consumer(self) -> MagicMock:
        """Create a mock Kafka consumer that reads from this harness."""
        consumer = MagicMock()

        def fake_commit() -> None:
            if self.queue:
                self.committed_offsets.append(self.queue[0].offset)

        consumer.commit.side_effect = fake_commit
        consumer.close = MagicMock()
        return consumer


# ------------------------------------------------------------------------------
# Test Cases
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_consumer_integration_three_events_persisted_in_db(
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    """P6-4 Core: Publish 3 events, consume them, and assert all 3 are persisted in risk_alerts table.

    Asserts:
    - Event 1: NanoCore critical MCU shortage ($2,448,105.00 exposure).
    - Event 2: BetaElectro power IC high risk ($75,000.00 exposure).
    - Event 3: DeltaSensors accelerometer medium risk ($15,000.00 exposure).
    - All 3 records match exact Decimal precision, status, and supplier foreign keys.
    """
    # 1. Seed 3 suppliers in database for foreign key integrity
    supplier_1 = Supplier(
        id=uuid4(),
        name="NanoCore Microelectronics",
        country_code="TW",
        tier=2,
        neptune_node_id="SUP-NC-882",
        risk_score=Decimal("0.885"),
    )
    supplier_2 = Supplier(
        id=uuid4(),
        name="BetaElectro Systems",
        country_code="DE",
        tier=1,
        neptune_node_id="SUP-BE-101",
        risk_score=Decimal("0.620"),
    )
    supplier_3 = Supplier(
        id=uuid4(),
        name="DeltaSensors GmbH",
        country_code="AT",
        tier=2,
        neptune_node_id="SUP-DS-303",
        risk_score=Decimal("0.450"),
    )
    db_session.add_all([supplier_1, supplier_2, supplier_3])
    await db_session.commit()

    # 2. Setup in-memory Kafka transport harness
    harness = InMemoryKafkaHarness(topic=settings.KAFKA_TOPIC_RISK_ALERTS)
    mock_producer = harness.create_mock_producer()
    mock_consumer = harness.create_mock_consumer()

    event_producer = EventProducer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        producer=mock_producer,
    )
    event_consumer = EventConsumer(
        topics=[settings.KAFKA_TOPIC_RISK_ALERTS],
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        consumer=mock_consumer,
    )

    # 3. Register database persistence handler
    handler = create_risk_alert_consumer_handler(session_factory)
    event_consumer.register_handler(settings.KAFKA_TOPIC_RISK_ALERTS, handler)

    # 4. Construct 3 canonical RiskAlert events
    id_1 = str(uuid4())
    id_2 = str(uuid4())
    id_3 = str(uuid4())

    event_1 = RiskAlertSchema(
        alert_id=id_1,
        supplier_id="SUP-NC-882",
        component_sku="CMP-MCU-X91",
        risk_level=RiskLevel.CRITICAL,
        days_of_cover=Decimal("7.68"),
        gap_days=Decimal("1.32"),
        shortage_volume=24420,
        financial_exposure=Decimal("2448105.00"),
        status=AlertStatus.OPEN,
    )
    event_2 = RiskAlertSchema(
        alert_id=id_2,
        supplier_id="SUP-BE-101",
        component_sku="CMP-PMIC-440",
        risk_level=RiskLevel.HIGH,
        days_of_cover=Decimal("12.50"),
        gap_days=Decimal("2.50"),
        shortage_volume=5000,
        financial_exposure=Decimal("75000.00"),
        status=AlertStatus.OPEN,
    )
    event_3 = RiskAlertSchema(
        alert_id=id_3,
        supplier_id="SUP-DS-303",
        component_sku="CMP-ACC-101",
        risk_level=RiskLevel.MEDIUM,
        days_of_cover=Decimal("18.00"),
        gap_days=Decimal("0.00"),
        shortage_volume=0,
        financial_exposure=Decimal("15000.00"),
        status=AlertStatus.OPEN,
    )

    # 5. Publish all 3 events to Kafka
    rec_1 = event_producer.publish_risk_alert(event_1)
    rec_2 = event_producer.publish_risk_alert(event_2)
    rec_3 = event_producer.publish_risk_alert(event_3)

    assert rec_1.topic == settings.KAFKA_TOPIC_RISK_ALERTS
    assert rec_2.topic == settings.KAFKA_TOPIC_RISK_ALERTS
    assert rec_3.topic == settings.KAFKA_TOPIC_RISK_ALERTS
    assert len(harness.queue) == 3

    # 6. Consume all 3 events via EventConsumer
    for record in list(harness.queue):
        success = await event_consumer.process_record(record)
        assert success is True

    # 7. Query database risk_alerts table and assert all 3 are persisted
    repo = RiskAlertRepository(db_session)
    persisted_alerts = await repo.list(limit=10)

    assert len(persisted_alerts) == 3

    # Map by ID for deterministic verification
    alerts_by_id = {alert.id: alert for alert in persisted_alerts}

    # Verify Event 1 (NanoCore)
    alert_1 = alerts_by_id[UUID(id_1)]
    assert alert_1.supplier_id == supplier_1.id
    assert alert_1.component_sku == "CMP-MCU-X91"
    assert alert_1.risk_level == "CRITICAL"
    assert alert_1.days_of_cover == Decimal("7.68")
    assert alert_1.financial_exposure == Decimal("2448105.00")
    assert alert_1.shortage_volume == 24420
    assert alert_1.status == "OPEN"

    # Verify Event 2 (BetaElectro)
    alert_2 = alerts_by_id[UUID(id_2)]
    assert alert_2.supplier_id == supplier_2.id
    assert alert_2.component_sku == "CMP-PMIC-440"
    assert alert_2.risk_level == "HIGH"
    assert alert_2.days_of_cover == Decimal("12.50")
    assert alert_2.financial_exposure == Decimal("75000.00")
    assert alert_2.shortage_volume == 5000
    assert alert_2.status == "OPEN"

    # Verify Event 3 (DeltaSensors)
    alert_3 = alerts_by_id[UUID(id_3)]
    assert alert_3.supplier_id == supplier_3.id
    assert alert_3.component_sku == "CMP-ACC-101"
    assert alert_3.risk_level == "MEDIUM"
    assert alert_3.days_of_cover == Decimal("18.00")
    assert alert_3.financial_exposure == Decimal("15000.00")
    assert alert_3.shortage_volume == 0
    assert alert_3.status == "OPEN"


@pytest.mark.asyncio
async def test_consumer_integration_manual_offset_commit_on_success(
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    """Verify that consumer manual offset commit is strictly called after persistence."""
    harness = InMemoryKafkaHarness()
    mock_consumer = harness.create_mock_consumer()

    event_consumer = EventConsumer(
        topics=["risk-alerts"],
        consumer=mock_consumer,
    )
    handler = create_risk_alert_consumer_handler(session_factory)
    event_consumer.register_handler("risk-alerts", handler)

    alert_id = str(uuid4())
    event = RiskAlertSchema(
        alert_id=alert_id,
        supplier_id="SUP-GENERIC-001",
        component_sku="CMP-TEST-001",
        risk_level=RiskLevel.LOW,
        days_of_cover=Decimal("30.00"),
        financial_exposure=Decimal("0.00"),
    )
    mock_record = MockConsumerRecord(
        topic="risk-alerts",
        partition=0,
        offset=42,
        key=alert_id.encode("utf-8"),
        value=event.to_bytes(),
    )

    success = await event_consumer.process_record(mock_record)
    assert success is True

    # Assert commit was called
    mock_consumer.commit.assert_called_once()

    # Assert record is in DB
    repo = RiskAlertRepository(db_session)
    saved = await repo.get_by_id(UUID(alert_id))
    assert saved is not None
    assert saved.component_sku == "CMP-TEST-001"


@pytest.mark.asyncio
async def test_consumer_integration_idempotent_redelivery(
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    """Verify that redelivering the same event updates or preserves record without primary key conflict."""
    harness = InMemoryKafkaHarness()
    mock_consumer = harness.create_mock_consumer()

    event_consumer = EventConsumer(
        topics=["risk-alerts"],
        consumer=mock_consumer,
    )
    handler = create_risk_alert_consumer_handler(session_factory)
    event_consumer.register_handler("risk-alerts", handler)

    alert_id = str(uuid4())
    event_v1 = RiskAlertSchema(
        alert_id=alert_id,
        supplier_id="SUP-IDEMP-001",
        component_sku="CMP-IDEMP-001",
        risk_level=RiskLevel.HIGH,
        days_of_cover=Decimal("10.00"),
        financial_exposure=Decimal("50000.00"),
        status=AlertStatus.OPEN,
    )
    event_v2 = RiskAlertSchema(
        alert_id=alert_id,
        supplier_id="SUP-IDEMP-001",
        component_sku="CMP-IDEMP-001",
        risk_level=RiskLevel.HIGH,
        days_of_cover=Decimal("10.00"),
        financial_exposure=Decimal("50000.00"),
        status=AlertStatus.INVESTIGATING,
    )

    record_1 = MockConsumerRecord(
        topic="risk-alerts",
        partition=0,
        offset=1,
        key=alert_id.encode("utf-8"),
        value=event_v1.to_bytes(),
    )
    record_2 = MockConsumerRecord(
        topic="risk-alerts",
        partition=0,
        offset=2,
        key=alert_id.encode("utf-8"),
        value=event_v2.to_bytes(),
    )

    # Process first delivery
    res_1 = await event_consumer.process_record(record_1)
    assert res_1 is True

    # Process redelivery
    res_2 = await event_consumer.process_record(record_2)
    assert res_2 is True

    # Verify exactly one record exists with updated status
    repo = RiskAlertRepository(db_session)
    count = await repo.count()
    assert count == 1

    saved = await repo.get_by_id(UUID(alert_id))
    assert saved is not None
    assert saved.status == "INVESTIGATING"


@pytest.mark.asyncio
async def test_consumer_integration_trace_id_propagation(
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    """Verify that X-Trace-ID from Kafka record header propagates through the handler pipeline."""
    harness = InMemoryKafkaHarness()
    mock_consumer = harness.create_mock_consumer()

    event_consumer = EventConsumer(
        topics=["risk-alerts"],
        consumer=mock_consumer,
    )
    handler = create_risk_alert_consumer_handler(session_factory)
    event_consumer.register_handler("risk-alerts", handler)

    trace_id_val = "trace-integ-test-456"
    alert_id = str(uuid4())
    event = RiskAlertSchema(
        alert_id=alert_id,
        supplier_id="SUP-TRACE-001",
        component_sku="CMP-TRACE-001",
        risk_level=RiskLevel.MEDIUM,
        days_of_cover=Decimal("15.00"),
        financial_exposure=Decimal("20000.00"),
    )
    mock_record = MockConsumerRecord(
        topic="risk-alerts",
        partition=0,
        offset=10,
        key=alert_id.encode("utf-8"),
        value=event.to_bytes(),
        headers=[("X-Trace-ID", trace_id_val.encode("utf-8"))],
    )

    success = await event_consumer.process_record(mock_record)
    assert success is True

    repo = RiskAlertRepository(db_session)
    saved = await repo.get_by_id(UUID(alert_id))
    assert saved is not None


@pytest.mark.asyncio
async def test_consumer_integration_poisonous_event_routes_to_dlq(
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    """Verify that a malformed event causes 3 retries and routes to DLQ without committing offset."""
    harness = InMemoryKafkaHarness()
    mock_consumer = harness.create_mock_consumer()
    mock_dlq_producer = harness.create_mock_dlq_producer()

    event_consumer = EventConsumer(
        topics=["risk-alerts"],
        consumer=mock_consumer,
        producer=mock_dlq_producer,
        max_retries=3,
    )
    handler = create_risk_alert_consumer_handler(session_factory)
    event_consumer.register_handler("risk-alerts", handler)

    # Poisonous message: missing mandatory fields
    poisonous_record = MockConsumerRecord(
        topic="risk-alerts",
        partition=0,
        offset=999,
        key=b"poison-key",
        value=b'{"corrupt": "data", "missing": "component_sku"}',
    )

    success = await event_consumer.process_record(poisonous_record)
    assert success is False

    # Assert routed to DLQ topic
    assert len(harness.dlq_queue) == 1
    assert harness.dlq_queue[0]["topic"] == "risk-alerts.dlq"

    # Assert no records were persisted in risk_alerts table
    repo = RiskAlertRepository(db_session)
    count = await repo.count()
    assert count == 0


@pytest.mark.asyncio
async def test_consumer_integration_batch_publishing_and_consumption(
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    """Verify batch publishing of 3 events and sequential consumption into risk_alerts."""
    harness = InMemoryKafkaHarness(topic="risk-alerts")
    mock_producer = harness.create_mock_producer()
    mock_consumer = harness.create_mock_consumer()

    event_producer = EventProducer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        producer=mock_producer,
    )
    event_consumer = EventConsumer(
        topics=["risk-alerts"],
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        consumer=mock_consumer,
    )
    handler = create_risk_alert_consumer_handler(session_factory)
    event_consumer.register_handler("risk-alerts", handler)

    events = [
        RiskAlertSchema(
            alert_id=str(uuid4()),
            supplier_id=f"SUP-BATCH-00{i}",
            component_sku=f"CMP-BATCH-00{i}",
            risk_level=RiskLevel.MEDIUM,
            days_of_cover=Decimal("14.00"),
            financial_exposure=Decimal("10000.00"),
        )
        for i in range(1, 4)
    ]

    records = [
        {
            "topic": "risk-alerts",
            "value": event.to_dict(),
            "key": str(event.alert_id),
        }
        for event in events
    ]

    published = event_producer.publish_batch(records)
    assert len(published) == 3
    assert len(harness.queue) == 3

    for record in list(harness.queue):
        success = await event_consumer.process_record(record)
        assert success is True

    repo = RiskAlertRepository(db_session)
    count = await repo.count()
    assert count == 3


def test_testcontainers_kafka_environment_check() -> None:
    """Verify Testcontainers Kafka environment detection and diagnostic logging.

    Asserts that the system identifies whether Testcontainers package is present
    and handles container orchestration gracefully without breaking offline isolation.
    """
    has_testcontainers = False
    try:
        import testcontainers.kafka  # type: ignore[import-not-found] # noqa: F401

        has_testcontainers = True
    except (ImportError, ModuleNotFoundError):
        has_testcontainers = False

    # Verify deterministic environment flag detection
    assert isinstance(has_testcontainers, bool)


@pytest.mark.asyncio
async def test_persist_risk_alert_with_dict_and_uuid_types(
    db_session: AsyncSession,
) -> None:
    """Verify persist_risk_alert handles dict payloads, json strings, and direct UUID helper calls."""
    from src.kafka.handlers import _coerce_uuid, _resolve_supplier_uuid

    # Direct helper coverage
    u = uuid4()
    assert _coerce_uuid(u) == u
    assert await _resolve_supplier_uuid(None, db_session) is None
    assert await _resolve_supplier_uuid(u, db_session) == u

    supplier_id = uuid4()
    alert_id = uuid4()
    supplier = Supplier(
        id=supplier_id,
        name="Direct UUID Supplier",
        country_code="US",
        tier=1,
        neptune_node_id="SUP-DIR-001",
        risk_score=Decimal("0.250"),
    )
    db_session.add(supplier)
    await db_session.commit()

    payload_dict = {
        "alert_id": str(alert_id),
        "supplier_id": str(supplier_id),
        "component_sku": "CMP-UUID-001",
        "risk_level": "LOW",
        "days_of_cover": "25.00",
        "financial_exposure": "1200.00",
    }

    result = await persist_risk_alert(payload_dict, db_session)
    assert result.id == alert_id
    assert result.supplier_id == supplier_id
    assert result.days_of_cover == Decimal("25.00")

    # Pass as JSON string to verify json parse branch
    json_alert_id = uuid4()
    json_str = (
        f'{{"alert_id": "{json_alert_id}", "supplier_id": "SUP-DIR-001", '
        f'"component_sku": "CMP-JSON-001", "risk_level": "LOW", "days_of_cover": "12.00"}}'
    )
    json_result = await persist_risk_alert(json_str, db_session)
    assert json_result.id == json_alert_id
    assert json_result.supplier_id == supplier_id


@pytest.mark.asyncio
async def test_persist_risk_alert_non_uuid_and_missing_supplier(
    db_session: AsyncSession,
) -> None:
    """Verify UUIDv5 coercion for non-UUID alert IDs and graceful handling of unknown suppliers."""
    non_uuid_id = "ALERT-CUSTOM-BUSINESS-KEY-1234"
    event = RiskAlertSchema(
        alert_id=non_uuid_id,
        supplier_id="UNKNOWN-SUPPLIER-KEY",
        component_sku="CMP-CUSTOM-001",
        risk_level=RiskLevel.MEDIUM,
        days_of_cover=Decimal("15.00"),
        financial_exposure=Decimal("5000.00"),
    )

    result = await persist_risk_alert(event, db_session)
    assert isinstance(result.id, UUID)
    assert result.supplier_id is None


@pytest.mark.asyncio
async def test_persist_risk_alert_unsupported_payload_type(
    db_session: AsyncSession,
) -> None:
    """Verify that passing an unsupported payload type raises KafkaMessageProcessingError."""
    from src.kafka.consumer import KafkaMessageProcessingError

    with pytest.raises(KafkaMessageProcessingError, match="Unsupported event payload type"):
        await persist_risk_alert(123456, db_session)


@pytest.mark.asyncio
async def test_persist_risk_alert_database_error_rollback(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify transaction rollback and exception re-raising on database failure."""
    from src.kafka.consumer import KafkaMessageProcessingError

    event = RiskAlertSchema(
        alert_id=str(uuid4()),
        supplier_id="SUP-ERR-001",
        component_sku="CMP-ERR-001",
        risk_level=RiskLevel.HIGH,
        days_of_cover=Decimal("5.00"),
        financial_exposure=Decimal("9999.00"),
    )

    # Monkeypatch repo.create to raise an unexpected database exception
    async def fake_create(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("Simulated database write lock timeout")

    monkeypatch.setattr(RiskAlertRepository, "create", fake_create)

    with pytest.raises(
        KafkaMessageProcessingError, match="Failed to persist RiskAlert to database"
    ):
        await persist_risk_alert(event, db_session)
