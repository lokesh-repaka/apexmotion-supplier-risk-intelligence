"""Unit tests for the development database seeding script (P13-1).

Verifies requirements from TASKS.md & CLAUDE.md:
- 50 Tier-1 suppliers across >= 10 countries
- 200 components across 20 manufacturing plants
- 20 manufacturing plants represented
- Canonical NanoCore reference scenario loaded with exact golden metrics:
  - Days of cover: 7.68
  - Shortage volume: 24,420 units
  - Financial exposure: $2,448,105.00
  - Risk severity: CRITICAL
- Idempotent execution (multiple runs without duplicates or collision)
- Append-only audit trail generation
"""

import json
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from src.database.models import (
    AuditLog,
    Base,
    InventorySnapshot,
    RiskAlert,
    Supplier,
)
from src.database.seed_dev import (
    SeedDevResult,
    get_plants_catalog,
    get_raw_components_catalog,
    get_raw_suppliers_catalog,
    seed_database,
)


@pytest_asyncio.fixture
async def db_session():
    """In-memory SQLite async session for offline isolated testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        json_serializer=lambda obj: json.dumps(obj, default=str),
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session


# ------------------------------------------------------------------------------
# 1. Catalog & In-Memory Dataset Verification
# ------------------------------------------------------------------------------


def test_seed_suppliers_catalog_dimensions():
    """Verify suppliers catalog contains >= 50 Tier-1 suppliers across >= 10 countries."""
    suppliers = get_raw_suppliers_catalog()
    tier_1 = [s for s in suppliers if s["tier"] == 1]
    countries = {s["country_code"] for s in tier_1}

    assert len(tier_1) >= 50, f"Expected >= 50 Tier-1 suppliers, found {len(tier_1)}"
    assert len(countries) >= 10, (
        f"Expected >= 10 countries for Tier-1 suppliers, found {len(countries)}"
    )
    assert len(suppliers) >= 50

    # Ensure all risk scores are Decimal within [0.0, 1.0]
    for s in suppliers:
        assert isinstance(s["risk_score"], Decimal)
        assert Decimal("0.0") <= s["risk_score"] <= Decimal("1.0")
        assert len(s["country_code"]) == 2


def test_seed_plants_catalog_dimensions():
    """Verify plants catalog contains exactly 20 distinct automotive plants."""
    plants = get_plants_catalog()
    assert len(plants) == 20, f"Expected 20 plants, got {len(plants)}"

    plant_ids = {p["plant_id"] for p in plants}
    assert len(plant_ids) == 20
    assert "PLT-MUC-01" in plant_ids, "Munich Assembly Hub must be present in plants catalog"


def test_seed_components_catalog_dimensions():
    """Verify components catalog contains >= 200 distinct component SKUs."""
    components = get_raw_components_catalog()
    skus = {c["sku"] for c in components}

    assert len(components) >= 200, f"Expected >= 200 components, got {len(components)}"
    assert len(skus) >= 200, f"Expected >= 200 distinct SKUs, got {len(skus)}"

    # Check NanoCore canonical SKU is present with exact parameters
    nanocore_comp = next((c for c in components if c["sku"] == "SKU-MCU-4402"), None)
    assert nanocore_comp is not None, "SKU-MCU-4402 must be in component catalog"
    assert nanocore_comp["current_stock"] == Decimal("142000.00")
    assert nanocore_comp["daily_consumption_rate"] == Decimal("18500.00")
    assert nanocore_comp["unit_cost_usd"] == Decimal("100.25")
    assert nanocore_comp["inbound_eta_days"] == Decimal("9.00")
    assert nanocore_comp["plant_id"] == "PLT-MUC-01"


# ------------------------------------------------------------------------------
# 2. Database Seeding Execution Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seed_database_execution(db_session: AsyncSession):
    """Verify seed_database persists all suppliers, components, and NanoCore alert."""
    result: SeedDevResult = await seed_database(db_session, clear_existing=False)

    assert isinstance(result, SeedDevResult)
    assert result.tier_1_suppliers_count >= 50
    assert result.countries_count >= 10
    assert result.plants_count == 20
    assert result.components_count >= 200
    assert result.nanocore_loaded is True

    # 1. Assert suppliers in database
    suppliers_count = await db_session.scalar(select(func.count(Supplier.id)))
    tier_1_count = await db_session.scalar(
        select(func.count(Supplier.id)).where(Supplier.tier == 1)
    )
    assert suppliers_count >= 50
    assert tier_1_count >= 50

    # 2. Assert inventory snapshots in database
    inventory_count = await db_session.scalar(select(func.count(InventorySnapshot.id)))
    assert inventory_count >= 200

    # 3. Assert plant coverage across inventory
    distinct_plants = await db_session.scalars(select(InventorySnapshot.plant_id).distinct())
    plant_set = set(distinct_plants.all())
    assert len(plant_set) == 20

    # 4. Assert NanoCore golden scenario alert and inventory
    nanocore_inv = await db_session.scalar(
        select(InventorySnapshot).where(
            InventorySnapshot.component_sku == "SKU-MCU-4402",
            InventorySnapshot.plant_id == "PLT-MUC-01",
        )
    )
    assert nanocore_inv is not None
    assert nanocore_inv.current_stock == Decimal("142000.00")
    assert nanocore_inv.daily_consumption_rate == Decimal("18500.00")
    assert nanocore_inv.unit_cost_usd == Decimal("100.25")

    # 5. Assert canonical NanoCore risk alert
    nanocore_alert = await db_session.scalar(
        select(RiskAlert).where(RiskAlert.component_sku == "SKU-MCU-4402")
    )
    assert nanocore_alert is not None
    assert nanocore_alert.risk_level == "CRITICAL"
    assert nanocore_alert.days_of_cover == Decimal("7.68")
    assert nanocore_alert.financial_exposure == Decimal("2448105.00")
    assert nanocore_alert.shortage_volume == 24420
    assert nanocore_alert.status == "OPEN"


@pytest.mark.asyncio
async def test_seed_database_idempotency(db_session: AsyncSession):
    """Verify running seed_database consecutively is idempotent and produces no duplicates."""
    result1 = await seed_database(db_session, clear_existing=False)
    result2 = await seed_database(db_session, clear_existing=False)

    assert result1.nanocore_loaded is True
    assert result2.nanocore_loaded is True

    suppliers_count = await db_session.scalar(select(func.count(Supplier.id)))
    inventory_count = await db_session.scalar(select(func.count(InventorySnapshot.id)))
    alerts_count = await db_session.scalar(select(func.count(RiskAlert.id)))

    assert suppliers_count == result1.suppliers_created + result1.suppliers_updated
    assert inventory_count == result1.inventory_snapshots_count
    assert alerts_count == 1, "Only 1 canonical NanoCore alert should exist after multiple runs"


@pytest.mark.asyncio
async def test_seed_database_clear_existing(db_session: AsyncSession):
    """Verify clear_existing=True resets the database before reseeding."""
    await seed_database(db_session, clear_existing=False)
    result = await seed_database(db_session, clear_existing=True)

    assert result.nanocore_loaded is True
    suppliers_count = await db_session.scalar(select(func.count(Supplier.id)))
    assert suppliers_count >= 50


@pytest.mark.asyncio
async def test_seed_database_audit_log_entry(db_session: AsyncSession):
    """Verify an append-only audit log entry is preserved for NanoCore alert initialization."""
    await seed_database(db_session, clear_existing=False)

    logs = (await db_session.scalars(select(AuditLog))).all()
    assert len(logs) >= 1

    nanocore_log = next(
        (log for log in logs if log.entity_type == "risk_alerts" and log.action == "CREATE"),
        None,
    )
    assert nanocore_log is not None
    assert nanocore_log.trace_id is not None
    assert "SKU-MCU-4402" in str(nanocore_log.after_state)


@pytest.mark.asyncio
async def test_seed_database_verify_integrity(db_session: AsyncSession):
    """Verify verify_seed_integrity validates all constraints on seeded data."""
    await seed_database(db_session, clear_existing=False)

    from src.database.seed_dev import verify_seed_integrity

    audit = await verify_seed_integrity(db_session)
    assert audit["all_checks_passed"] is True
    assert audit["tier_1_count"] >= 50
    assert audit["countries_count"] >= 10
    assert audit["inventory_count"] >= 200
    assert audit["plants_count"] == 20
    assert audit["nanocore_golden_valid"] is True


@pytest.mark.asyncio
async def test_seed_dev_cli_dry_run(capsys):
    """Verify async_main dry-run executes cleanly with zero database side-effects."""
    import argparse

    from src.database.seed_dev import async_main

    args = argparse.Namespace(dry_run=True, clear=False, verify=False)
    exit_code = await async_main(args)
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "DRY-RUN" in captured.out
    assert "Suppliers defined:" in captured.out
    assert "Manufacturing Plants: 20" in captured.out


@pytest.mark.asyncio
async def test_seed_dev_cli_live_execution(monkeypatch, capsys):
    """Verify async_main live execution with --verify and --clear using in-memory SQLite session factory."""
    import argparse

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from src.database.models import Base
    from src.database.seed_dev import async_main

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        json_serializer=lambda obj: json.dumps(obj, default=str),
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("src.database.seed_dev.get_async_session_factory", lambda: factory)

    args = argparse.Namespace(dry_run=False, clear=True, verify=True)
    exit_code = await async_main(args)
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "Tier-1 Suppliers:" in captured.out
    assert "NanoCore Disruption Scenario: LOADED" in captured.out
    assert "[VERIFY] Auditing database integrity..." in captured.out
    assert "Database seeding completed successfully." in captured.out


def test_seed_dev_main_entrypoint(monkeypatch):
    """Verify main() parses arguments and invokes async_main."""
    import sys

    from src.database.seed_dev import main

    monkeypatch.setattr(sys, "argv", ["seed_dev", "--dry-run"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
