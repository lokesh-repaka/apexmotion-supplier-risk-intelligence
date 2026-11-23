"""Unit tests for Inventory Aggregation Service (P7-3).

Verifies:
- Real-time stock pull from Aurora PostgreSQL + Redis cache.
- The Triad of Responsibility (BR-RULE-001): pure deterministic Python arithmetic and data aggregation with zero LLM math.
- Decimal precision across all inventory counts and currency metrics (zero float drift).
- Redis caching lifecycle:
  * Cache key format: inventory:stock:{sku} (and inventory:stock:{sku}:{plant_id})
  * Cache TTL: 1800 seconds (30 minutes per LLD Section 6.1)
  * Cache hit returns cached record with data_source='REDIS_CACHE' and is_cached=True
  * Cache miss queries Aurora and populates Redis cache
  * Cache invalidation and force_refresh flags
- Graceful degradation:
  * Redis outage/timeout transparently falls back to Aurora PostgreSQL
  * Aurora outage falls back to Redis cached balance (LLD Section 6.1 circuit breaker fallback)
- Canonical NanoCore golden scenario stock pull (142,000 units, 18,500 burn, 9.0 ETA, $100.25 unit cost).
- Multi-plant stock aggregation (Munich, Bengaluru, Pune).
- Stock level updates with negative underflow prevention (InvalidInventoryOperationError).
- Unknown SKU handling (InventoryNotFoundError with 404 status).
- End-to-end integration with RiskCalculator (7.68 days cover, 1.32 days gap, $2,448,105.00 exposure).
- 100% statement and branch coverage on src/services/risk/inventory_service.py.
"""

import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from src.database.models import Base
from src.database.repositories.inventory_repository import InventoryRepository
from src.services.risk.calculator import DAYS_OF_COVER_MAX_CAP, RiskCalculator
from src.services.risk.inventory_service import (
    DEFAULT_CACHE_TTL_SECONDS,
    NANOCORE_CANONICAL_SKU,
    InvalidInventoryOperationError,
    InventoryNotFoundError,
    InventoryRecord,
    InventoryService,
    PlantInventoryAggregate,
)


class MockRedisAsync:
    """In-memory mock for redis.asyncio.Redis supporting caching, TTL, and simulated failure."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.simulate_failure: bool = False
        self.call_count: dict[str, int] = {
            "get": 0,
            "set": 0,
            "delete": 0,
            "mget": 0,
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

    async def mget(self, keys: list[str]) -> list[str | None]:
        self.call_count["mget"] += 1
        if self.simulate_failure:
            raise ConnectionError("Simulated Redis connection failure")
        return [self.store.get(k) for k in keys]

    async def aclose(self) -> None:
        pass

    async def close(self) -> None:
        pass


@pytest_asyncio.fixture
async def async_db_engine() -> AsyncGenerator[Any, None]:
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


@pytest.fixture
def inventory_service(
    session_factory: async_sessionmaker[AsyncSession], mock_redis: MockRedisAsync
) -> InventoryService:
    """Fixture providing configured InventoryService with mock Redis and async DB."""
    return InventoryService(
        session_factory=session_factory,
        redis_client=mock_redis,
        cache_ttl_seconds=DEFAULT_CACHE_TTL_SECONDS,
        enable_reference_fallback=True,
    )


# ==============================================================================
# 1. Domain Model: InventoryRecord Tests
# ==============================================================================


def test_inventory_record_initialization_and_decimal_types() -> None:
    """Verify InventoryRecord strictly enforces Decimal types for all metrics."""
    record = InventoryRecord(
        component_sku="SKU-MCU-4402",
        current_stock=Decimal("142000"),
        daily_consumption_rate=Decimal("18500"),
        safety_stock_units=Decimal("20000"),
        unit_cost_usd=Decimal("100.25"),
        inbound_eta_days=Decimal("9.0"),
        inbound_shipment_units=Decimal("80000"),
        inbound_shipment_po="PO-88921",
        supplier_id="SUP-NC-001",
        plant_id="PLT-MUC-01",
    )

    assert record.component_sku == "SKU-MCU-4402"
    assert isinstance(record.current_stock, Decimal)
    assert record.current_stock == Decimal("142000")
    assert isinstance(record.daily_consumption_rate, Decimal)
    assert record.daily_consumption_rate == Decimal("18500")
    assert isinstance(record.unit_cost_usd, Decimal)
    assert record.unit_cost_usd == Decimal("100.25")
    assert record.days_of_cover == Decimal("7.68")
    assert record.total_valuation_usd == Decimal("14235500.00")


def test_inventory_record_serialization_and_cache_payload() -> None:
    """Verify exact serialization to JSON with string representation of Decimal fields."""
    record = InventoryRecord(
        component_sku="SKU-TEST-001",
        current_stock=Decimal("50000.50"),
        daily_consumption_rate=Decimal("2500.25"),
        safety_stock_units=Decimal("5000"),
        unit_cost_usd=Decimal("45.75"),
        inbound_eta_days=Decimal("4.5"),
        inbound_shipment_units=Decimal("12000"),
        inbound_shipment_po="PO-TEST-99",
        supplier_id="SUP-TEST-01",
        plant_id="PLT-BLR-01",
        data_source="AURORA_DB",
        is_cached=False,
    )

    payload = record.to_cache_payload()
    assert isinstance(payload, str)
    assert '"50000.50"' in payload
    assert '"2500.25"' in payload

    # Reconstruct from cache payload
    reconstructed = InventoryRecord.from_cache_payload(payload)
    assert reconstructed.component_sku == record.component_sku
    assert reconstructed.current_stock == Decimal("50000.50")
    assert reconstructed.daily_consumption_rate == Decimal("2500.25")
    assert reconstructed.unit_cost_usd == Decimal("45.75")
    assert reconstructed.inbound_eta_days == Decimal("4.5")
    assert reconstructed.inbound_shipment_po == "PO-TEST-99"
    assert reconstructed.plant_id == "PLT-BLR-01"


def test_inventory_record_to_risk_input_conversion() -> None:
    """Verify to_risk_input bridges seamlessly with RiskCalculator for NanoCore evaluation."""
    record = InventoryRecord(
        component_sku=NANOCORE_CANONICAL_SKU,
        current_stock=Decimal("142000"),
        daily_consumption_rate=Decimal("18500"),
        safety_stock_units=Decimal("20000"),
        unit_cost_usd=Decimal("100.25"),
        inbound_eta_days=Decimal("9.0"),
        inbound_shipment_units=Decimal("80000"),
        inbound_shipment_po="PO-88921",
        supplier_id="SUP-NC-001",
        plant_id="PLT-MUC-01",
    )

    risk_input = record.to_risk_input(factory_halt_cost_per_hour_eur=Decimal("85000.00"))
    assert risk_input.current_stock == Decimal("142000")
    assert risk_input.daily_consumption_rate == Decimal("18500")
    assert risk_input.eta_days == Decimal("9.0")
    assert risk_input.unit_cost_usd == Decimal("100.25")
    assert risk_input.component_sku == NANOCORE_CANONICAL_SKU

    # Assess via RiskCalculator
    calc = RiskCalculator()
    assessment = calc.calculate(risk_input)
    assert assessment.days_of_cover == Decimal("7.68")
    assert assessment.gap_days == Decimal("1.32")
    assert assessment.shortage_volume == 24420
    assert assessment.financial_exposure == Decimal("2448105.00")


# ==============================================================================
# 2. Redis Caching & Retrieval Lifecycle Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_nanocore_stock_pull_cache_miss_then_cache_hit(
    inventory_service: InventoryService, mock_redis: MockRedisAsync
) -> None:
    """Verify first query hits database and caches, second query hits Redis cache immediately."""
    # First pull: Cache Miss -> Aurora/Reference -> Set in Redis
    rec1 = await inventory_service.get_stock(NANOCORE_CANONICAL_SKU, plant_id="PLT-MUC-01")
    assert rec1.component_sku == NANOCORE_CANONICAL_SKU
    assert rec1.current_stock == Decimal("142000")
    assert rec1.daily_consumption_rate == Decimal("18500")
    assert rec1.is_cached is False
    assert mock_redis.call_count["get"] == 1
    assert mock_redis.call_count["set"] == 1

    cache_key = inventory_service.format_cache_key(NANOCORE_CANONICAL_SKU, "PLT-MUC-01")
    assert cache_key in mock_redis.store
    assert mock_redis.ttls[cache_key] == DEFAULT_CACHE_TTL_SECONDS

    # Second pull: Cache Hit from Redis
    rec2 = await inventory_service.get_stock(NANOCORE_CANONICAL_SKU, plant_id="PLT-MUC-01")
    assert rec2.component_sku == NANOCORE_CANONICAL_SKU
    assert rec2.current_stock == Decimal("142000")
    assert rec2.is_cached is True
    assert rec2.data_source == "REDIS_CACHE"
    assert mock_redis.call_count["get"] == 2
    assert mock_redis.call_count["set"] == 1  # No extra write


@pytest.mark.asyncio
async def test_cache_invalidation_and_force_refresh(
    inventory_service: InventoryService, mock_redis: MockRedisAsync
) -> None:
    """Verify cache invalidation purges key, and force_refresh bypasses Redis cache."""
    # Seed cache
    await inventory_service.get_stock(NANOCORE_CANONICAL_SKU, plant_id="PLT-MUC-01")
    cache_key = inventory_service.format_cache_key(NANOCORE_CANONICAL_SKU, "PLT-MUC-01")
    assert cache_key in mock_redis.store

    # Invalidate cache
    deleted = await inventory_service.invalidate_cache(NANOCORE_CANONICAL_SKU, "PLT-MUC-01")
    assert deleted is True
    assert cache_key not in mock_redis.store

    # Repopulate
    await inventory_service.get_stock(NANOCORE_CANONICAL_SKU, plant_id="PLT-MUC-01")
    assert cache_key in mock_redis.store

    # Force refresh bypasses cache read
    rec = await inventory_service.get_stock(
        NANOCORE_CANONICAL_SKU, plant_id="PLT-MUC-01", force_refresh=True
    )
    assert rec.is_cached is False
    assert rec.data_source in {"AURORA_DB", "REFERENCE_SEED"}


# ==============================================================================
# 3. Stock Level Mutations and Cache Sync
# ==============================================================================


@pytest.mark.asyncio
async def test_stock_level_mutations_and_cache_invalidation(
    inventory_service: InventoryService,
) -> None:
    """Verify stock delta increments/decrements update Aurora and sync Redis."""
    # Seed NanoCore record
    await inventory_service.get_stock(NANOCORE_CANONICAL_SKU)

    # Positive mutation (+10,000 units on goods receipt)
    updated = await inventory_service.update_stock(
        component_sku=NANOCORE_CANONICAL_SKU,
        delta_units=Decimal("10000"),
        plant_id="PLT-MUC-01",
    )
    assert updated.current_stock == Decimal("152000")
    assert updated.days_of_cover == Decimal("8.22")  # 152000 / 18500 = 8.216 -> 8.22

    # Negative mutation (-5,000 units consumed by factory shift)
    consumed = await inventory_service.update_stock(
        component_sku=NANOCORE_CANONICAL_SKU,
        delta_units=Decimal("-5000"),
        plant_id="PLT-MUC-01",
    )
    assert consumed.current_stock == Decimal("147000")

    # Verify cached value in Redis reflects updated stock
    cached = await inventory_service.get_stock(NANOCORE_CANONICAL_SKU, plant_id="PLT-MUC-01")
    assert cached.current_stock == Decimal("147000")
    assert cached.is_cached is True


@pytest.mark.asyncio
async def test_stock_mutation_rejects_negative_underflow(
    inventory_service: InventoryService,
) -> None:
    """Verify stock mutation raises InvalidInventoryOperationError if stock drops below 0."""
    await inventory_service.get_stock(NANOCORE_CANONICAL_SKU)

    with pytest.raises(InvalidInventoryOperationError, match="cannot drop below zero"):
        await inventory_service.update_stock(
            component_sku=NANOCORE_CANONICAL_SKU,
            delta_units=Decimal("-200000"),  # Current is 142000
            plant_id="PLT-MUC-01",
        )


@pytest.mark.asyncio
async def test_set_stock_record_persists_and_caches(
    inventory_service: InventoryService,
) -> None:
    """Verify custom InventoryRecord can be explicitly set and retrieved."""
    new_record = InventoryRecord(
        component_sku="SKU-INVERTER-770",
        current_stock=Decimal("35000"),
        daily_consumption_rate=Decimal("4500"),
        safety_stock_units=Decimal("5000"),
        unit_cost_usd=Decimal("320.00"),
        inbound_eta_days=Decimal("6.0"),
        inbound_shipment_units=Decimal("15000"),
        inbound_shipment_po="PO-INV-102",
        supplier_id="SUP-INV-009",
        plant_id="PLT-PUN-01",
    )

    persisted = await inventory_service.set_stock(new_record)
    assert persisted.component_sku == "SKU-INVERTER-770"
    assert persisted.current_stock == Decimal("35000")

    # Fetch should hit Redis
    cached = await inventory_service.get_stock("SKU-INVERTER-770", plant_id="PLT-PUN-01")
    assert cached.is_cached is True
    assert cached.current_stock == Decimal("35000")
    assert cached.unit_cost_usd == Decimal("320.00")


# ==============================================================================
# 4. Batch Stock Queries & Multi-Plant Aggregation
# ==============================================================================


@pytest.mark.asyncio
async def test_batch_stock_query_aggregation(inventory_service: InventoryService) -> None:
    """Verify get_stock_batch retrieves multiple component SKUs concurrently."""
    skus = [NANOCORE_CANONICAL_SKU, "SKU-BAT-CELL-2170", "SKU-HARNESS-HV-01"]
    batch_results = await inventory_service.get_stock_batch(skus)

    assert len(batch_results) == 3
    assert NANOCORE_CANONICAL_SKU in batch_results
    assert batch_results[NANOCORE_CANONICAL_SKU].current_stock == Decimal("142000")
    assert batch_results["SKU-BAT-CELL-2170"].current_stock == Decimal("850000")
    assert batch_results["SKU-HARNESS-HV-01"].current_stock == Decimal("42000")


@pytest.mark.asyncio
async def test_multi_plant_stock_aggregation(inventory_service: InventoryService) -> None:
    """Verify multi-plant stock aggregation calculates composite stock and days of cover."""
    # Seed multiple plants for MCU-X91
    sku = "SKU-MCU-X91-GLOBAL"
    plant_munich = InventoryRecord(
        component_sku=sku,
        current_stock=Decimal("142000"),
        daily_consumption_rate=Decimal("18500"),
        safety_stock_units=Decimal("20000"),
        unit_cost_usd=Decimal("100.25"),
        plant_id="PLT-MUC-01",
    )
    plant_blr = InventoryRecord(
        component_sku=sku,
        current_stock=Decimal("50000"),
        daily_consumption_rate=Decimal("6500"),
        safety_stock_units=Decimal("8000"),
        unit_cost_usd=Decimal("100.25"),
        plant_id="PLT-BLR-01",
    )
    plant_pune = InventoryRecord(
        component_sku=sku,
        current_stock=Decimal("30000"),
        daily_consumption_rate=Decimal("4000"),
        safety_stock_units=Decimal("5000"),
        unit_cost_usd=Decimal("100.25"),
        plant_id="PLT-PUN-01",
    )

    await inventory_service.set_stock(plant_munich)
    await inventory_service.set_stock(plant_blr)
    await inventory_service.set_stock(plant_pune)

    aggregate: PlantInventoryAggregate = await inventory_service.get_plant_stock_aggregation(sku)
    assert aggregate.component_sku == sku
    assert aggregate.total_usable_stock == Decimal("222000")  # 142000 + 50000 + 30000
    assert aggregate.total_daily_burn == Decimal("29000")  # 18500 + 6500 + 4000
    assert aggregate.total_safety_stock == Decimal("33000")  # 20000 + 8000 + 5000
    # Composite days of cover: 222000 / 29000 = 7.655... -> 7.66 days
    assert aggregate.aggregate_days_of_cover == Decimal("7.66")
    assert len(aggregate.plant_breakdown) == 3


# ==============================================================================
# 5. Fault Tolerance & Outage Graceful Fallbacks
# ==============================================================================


@pytest.mark.asyncio
async def test_redis_outage_graceful_fallback_to_aurora(
    inventory_service: InventoryService, mock_redis: MockRedisAsync
) -> None:
    """Verify service gracefully falls back to Aurora when Redis throws connection error."""
    # Simulate Redis network partition
    mock_redis.simulate_failure = True

    # Pull should succeed directly from Aurora without crashing
    record = await inventory_service.get_stock(NANOCORE_CANONICAL_SKU)
    assert record.component_sku == NANOCORE_CANONICAL_SKU
    assert record.current_stock == Decimal("142000")
    assert record.is_cached is False
    assert record.data_source in {"AURORA_DB", "REFERENCE_SEED"}


@pytest.mark.asyncio
async def test_aurora_outage_fallback_to_redis_cache(
    mock_redis: MockRedisAsync,
) -> None:
    """Verify circuit breaker fallback: when Aurora is down, return Redis cached balance."""
    # Pre-populate Redis cache directly
    cache_record = InventoryRecord(
        component_sku="SKU-FAILOVER-001",
        current_stock=Decimal("95000"),
        daily_consumption_rate=Decimal("12000"),
        safety_stock_units=Decimal("10000"),
        unit_cost_usd=Decimal("55.00"),
        plant_id="PLT-MUC-01",
    )
    cache_key = "inventory:stock:SKU-FAILOVER-001:PLT-MUC-01"
    await mock_redis.set(cache_key, cache_record.to_cache_payload())

    # Create service with dummy broken DB session
    class FailingSessionFactory:
        def __call__(self) -> Any:
            raise RuntimeError("Aurora cluster unreachable")

    service = InventoryService(
        session_factory=FailingSessionFactory(),  # type: ignore
        redis_client=mock_redis,
        enable_reference_fallback=False,
    )

    # Should successfully serve from Redis cache without database
    record = await service.get_stock("SKU-FAILOVER-001", plant_id="PLT-MUC-01")
    assert record.current_stock == Decimal("95000")
    assert record.is_cached is True
    assert record.data_source == "REDIS_CACHE"


@pytest.mark.asyncio
async def test_unknown_sku_raises_inventory_not_found(
    inventory_service: InventoryService,
) -> None:
    """Verify querying an unregistered SKU raises typed InventoryNotFoundError."""
    with pytest.raises(InventoryNotFoundError, match="not found in inventory registry"):
        await inventory_service.get_stock("SKU-UNKNOWN-99999999")


# ==============================================================================
# 6. End-to-End Risk Assessment Integration Bridge
# ==============================================================================


@pytest.mark.asyncio
async def test_assess_component_risk_bridge(inventory_service: InventoryService) -> None:
    """Verify assess_component_risk bridge computes exact canonical NanoCore risk metrics."""
    assessment = await inventory_service.assess_component_risk(
        component_sku=NANOCORE_CANONICAL_SKU,
        eta_days=Decimal("9.0"),
    )

    assert assessment.days_of_cover == Decimal("7.68")
    assert assessment.gap_days == Decimal("1.32")
    assert assessment.shortage_volume == 24420
    assert assessment.financial_exposure == Decimal("2448105.00")
    assert assessment.calculation_hash != ""


# ==============================================================================
# 7. InventoryRepository Direct CRUD Lifecycle Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_inventory_repository_crud_lifecycle(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verify direct async CRUD operations via InventoryRepository on SQLite/Aurora."""
    from src.database.models import InventorySnapshot

    async with session_factory() as session:
        repo = InventoryRepository(session)

        # Create
        snapshot = InventorySnapshot(
            id=uuid.uuid4(),
            component_sku="SKU-REPO-TEST",
            plant_id="PLT-BLR-01",
            current_stock=Decimal("75000.00"),
            daily_consumption_rate=Decimal("10000.00"),
            safety_stock_units=Decimal("8000.00"),
            unit_cost_usd=Decimal("150.00"),
            inbound_eta_days=Decimal("5.0"),
            inbound_shipment_units=Decimal("20000.00"),
            inbound_shipment_po="PO-BLR-881",
        )
        saved = await repo.create(snapshot)
        assert saved.component_sku == "SKU-REPO-TEST"

        # Read by SKU and plant
        found = await repo.get_by_sku("SKU-REPO-TEST", plant_id="PLT-BLR-01")
        assert found is not None
        assert found.current_stock == Decimal("75000.00")

        # Read all plants for SKU
        all_plants = await repo.get_by_sku_all_plants("SKU-REPO-TEST")
        assert len(all_plants) == 1
        assert all_plants[0].plant_id == "PLT-BLR-01"

        # Read by supplier_id
        supp_uuid = uuid.uuid4()
        saved.supplier_id = supp_uuid
        await repo.update(saved)
        supp_snapshots = await repo.get_by_supplier_id(supp_uuid)
        assert len(supp_snapshots) == 1
        assert supp_snapshots[0].component_sku == "SKU-REPO-TEST"

        # Update stock quantity
        updated = await repo.update_stock_quantity(
            component_sku="SKU-REPO-TEST",
            delta_units=Decimal("-5000.00"),
            plant_id="PLT-BLR-01",
        )
        assert updated is not None
        assert updated.current_stock == Decimal("70000.00")

        # Update stock non-existent returns None
        missing = await repo.update_stock_quantity("SKU-MISSING", Decimal("100"))
        assert missing is None

        # Negative balance raises ValueError
        with pytest.raises(ValueError, match="Negative inventory balance"):
            await repo.update_stock_quantity(
                "SKU-REPO-TEST", Decimal("-100000"), plant_id="PLT-BLR-01"
            )

        # Upsert update existing
        saved.current_stock = Decimal("88000.00")
        upserted = await repo.upsert_inventory(saved)
        assert upserted.current_stock == Decimal("88000.00")


# ==============================================================================
# 8. Boundary Conditions, Coercion, and Error Handling Coverage
# ==============================================================================


def test_inventory_record_input_coercion_and_validation_errors() -> None:
    """Verify input coercion failure triggers InvalidInventoryOperationError."""
    # Invalid current_stock
    with pytest.raises(InvalidInventoryOperationError):
        InventoryRecord(
            component_sku="SKU-ERR",
            current_stock="INVALID_DECIMAL",  # type: ignore
            daily_consumption_rate=Decimal("100"),
        )

    # Invalid daily_consumption_rate
    with pytest.raises(InvalidInventoryOperationError):
        InventoryRecord(
            component_sku="SKU-ERR",
            current_stock=Decimal("100"),
            daily_consumption_rate="INVALID_DECIMAL",  # type: ignore
        )

    # Negative daily_consumption_rate
    with pytest.raises(InvalidInventoryOperationError, match="Negative consumption rate"):
        InventoryRecord(
            component_sku="SKU-ERR",
            current_stock=Decimal("100"),
            daily_consumption_rate=Decimal("-50"),
        )

    # Invalid unit_cost_usd
    with pytest.raises(InvalidInventoryOperationError):
        InventoryRecord(
            component_sku="SKU-ERR",
            current_stock=Decimal("100"),
            daily_consumption_rate=Decimal("100"),
            unit_cost_usd="NOT_A_NUMBER",  # type: ignore
        )

    # Invalid inbound_eta_days
    with pytest.raises(InvalidInventoryOperationError):
        InventoryRecord(
            component_sku="SKU-ERR",
            current_stock=Decimal("100"),
            daily_consumption_rate=Decimal("100"),
            inbound_eta_days="NOT_A_NUMBER",  # type: ignore
        )

    # Invalid safety_stock_units
    with pytest.raises(InvalidInventoryOperationError):
        InventoryRecord(
            component_sku="SKU-ERR",
            current_stock=Decimal("100"),
            daily_consumption_rate=Decimal("100"),
            safety_stock_units="NOT_A_NUMBER",  # type: ignore
        )

    # Invalid inbound_shipment_units
    with pytest.raises(InvalidInventoryOperationError):
        InventoryRecord(
            component_sku="SKU-ERR",
            current_stock=Decimal("100"),
            daily_consumption_rate=Decimal("100"),
            inbound_shipment_units="NOT_A_NUMBER",  # type: ignore
        )


def test_inventory_record_zero_consumption_days_of_cover() -> None:
    """Verify zero daily consumption caps days of cover at DAYS_OF_COVER_MAX_CAP."""
    record = InventoryRecord(
        component_sku="SKU-IDLE-001",
        current_stock=Decimal("50000"),
        daily_consumption_rate=Decimal("0.00"),
    )
    assert record.days_of_cover == DAYS_OF_COVER_MAX_CAP


def test_inventory_record_from_cache_payload_dict() -> None:
    """Verify from_cache_payload accepts direct dictionary representation."""
    raw_dict = {
        "component_sku": "SKU-DICT-01",
        "current_stock": "1000",
        "daily_consumption_rate": "100",
        "last_sync_time": "",
    }
    rec = InventoryRecord.from_cache_payload(raw_dict)
    assert rec.component_sku == "SKU-DICT-01"
    assert rec.current_stock == Decimal("1000")
    assert rec.is_cached is True


@pytest.mark.asyncio
async def test_get_stock_from_aurora_db_snapshot(
    inventory_service: InventoryService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verify get_stock retrieves and parses an Aurora database record (data_source='AURORA_DB')."""
    from src.database.models import InventorySnapshot

    test_sku = "SKU-AURORA-LIVE-01"
    async with session_factory() as session:
        repo = InventoryRepository(session)
        await repo.create(
            InventorySnapshot(
                id=uuid.uuid4(),
                component_sku=test_sku,
                plant_id="PLT-MUC-01",
                current_stock=Decimal("60000.00"),
                daily_consumption_rate=Decimal("5000.00"),
                safety_stock_units=Decimal("4000.00"),
                unit_cost_usd=Decimal("75.00"),
                inbound_eta_days=Decimal("3.0"),
                inbound_shipment_units=Decimal("10000.00"),
            )
        )

    # Fetch via inventory service with force_refresh
    rec = await inventory_service.get_stock(test_sku, plant_id="PLT-MUC-01", force_refresh=True)
    assert rec.component_sku == test_sku
    assert rec.current_stock == Decimal("60000.00")
    assert rec.data_source == "AURORA_DB"
    assert rec.is_cached is False


@pytest.mark.asyncio
async def test_get_stock_batch_missing_sku_logged(
    inventory_service: InventoryService,
) -> None:
    """Verify get_stock_batch safely skips missing SKUs and returns available records."""
    batch = await inventory_service.get_stock_batch(
        [NANOCORE_CANONICAL_SKU, "SKU-NONEXISTENT-XYZ-999"]
    )
    assert NANOCORE_CANONICAL_SKU in batch
    assert "SKU-NONEXISTENT-XYZ-999" not in batch


@pytest.mark.asyncio
async def test_multi_plant_aggregation_zero_burn_and_reference(
    inventory_service: InventoryService,
) -> None:
    """Verify multi-plant aggregation caps days of cover when aggregate burn is zero."""
    sku = "SKU-IDLE-PARTS"
    p1 = InventoryRecord(
        component_sku=sku,
        current_stock=Decimal("10000"),
        daily_consumption_rate=Decimal("0.00"),
        plant_id="PLT-MUC-01",
    )
    p2 = InventoryRecord(
        component_sku=sku,
        current_stock=Decimal("20000"),
        daily_consumption_rate=Decimal("0.00"),
        plant_id="PLT-BLR-01",
    )
    await inventory_service.set_stock(p1)
    await inventory_service.set_stock(p2)

    agg = await inventory_service.get_plant_stock_aggregation(sku)
    assert agg.total_usable_stock == Decimal("30000")
    assert agg.total_daily_burn == Decimal("0.00")
    assert agg.aggregate_days_of_cover == DAYS_OF_COVER_MAX_CAP


@pytest.mark.asyncio
async def test_multi_plant_aggregation_reference_fallback(
    inventory_service: InventoryService,
) -> None:
    """Verify multi-plant aggregation loads from reference registry if DB has no plant rows."""
    agg = await inventory_service.get_plant_stock_aggregation(NANOCORE_CANONICAL_SKU)
    assert agg.component_sku == NANOCORE_CANONICAL_SKU
    assert agg.total_usable_stock == Decimal("142000")
    assert agg.total_daily_burn == Decimal("18500")


@pytest.mark.asyncio
async def test_set_stock_with_invalid_supplier_uuid(
    inventory_service: InventoryService,
) -> None:
    """Verify non-UUID supplier_id strings are safely handled during set_stock."""
    rec = InventoryRecord(
        component_sku="SKU-STR-SUPP",
        current_stock=Decimal("5000"),
        daily_consumption_rate=Decimal("500"),
        supplier_id="NOT-A-VALID-UUID",
        plant_id="PLT-MUC-01",
    )
    saved = await inventory_service.set_stock(rec)
    assert saved.component_sku == "SKU-STR-SUPP"


@pytest.mark.asyncio
async def test_set_stock_and_invalidate_redis_failure_handled(
    inventory_service: InventoryService, mock_redis: MockRedisAsync
) -> None:
    """Verify set_stock and invalidate_cache do not crash when Redis throws errors."""
    mock_redis.simulate_failure = True

    rec = InventoryRecord(
        component_sku="SKU-FAIL-REDIS",
        current_stock=Decimal("5000"),
        daily_consumption_rate=Decimal("500"),
        plant_id="PLT-MUC-01",
    )
    # set_stock should succeed despite Redis write failure
    persisted = await inventory_service.set_stock(rec)
    assert persisted.component_sku == "SKU-FAIL-REDIS"

    # invalidate_cache should return False on Redis error
    deleted = await inventory_service.invalidate_cache("SKU-FAIL-REDIS")
    assert deleted is False


@pytest.mark.asyncio
async def test_inventory_service_close_and_lazy_initialization() -> None:
    """Verify close lifecycle and default session factory initialization."""
    # Service with no injected clients
    service = InventoryService(session_factory=None, redis_client=None)
    session_factory = service._get_session_factory()
    assert session_factory is not None

    # Close when no redis owned
    await service.close()

    # Close when redis client is owned
    service._owns_redis = True
    service._redis = MockRedisAsync()
    await service.close()
