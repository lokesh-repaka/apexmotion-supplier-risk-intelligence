"""Unit tests for SQLAlchemy 2.0 async repositories layer (P3-3).

Verifies:
- BaseRepository[T]: Standard async CRUD operations (create, get_by_id, list, count, update, delete).
- SupplierRepository: Queries by Neptune node ID, tier, country, and high-risk threshold.
- RiskAlertRepository: Queries by supplier ID, component SKU, active status, risk level, and status transitions.
- HITLApprovalRepository: Anti-replay token lookup, pending queue query, and multi-role signature logging.
- AuditLogRepository: Append-only immutability invariant (BR-RULE-007) rejecting update and delete, trace queries.
- AgentRunRepository: Execution lifecycle, Langfuse trace lookup, and run completion updates.
- Session Management: Async engine and session factory dependency lifecycle.
"""

import json
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from src.database.models import (
    AgentRun,
    AuditLog,
    Base,
    HITLApproval,
    RiskAlert,
    Supplier,
)
from src.database.repositories.agent_run_repository import AgentRunRepository
from src.database.repositories.audit_log_repository import AuditLogRepository
from src.database.repositories.base import BaseRepository
from src.database.repositories.hitl_approval_repository import HITLApprovalRepository
from src.database.repositories.risk_alert_repository import RiskAlertRepository
from src.database.repositories.supplier_repository import SupplierRepository


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
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

    await engine.dispose()


@pytest.mark.asyncio
async def test_base_repository_crud(db_session: AsyncSession) -> None:
    """Verify generic BaseRepository handles create, get_by_id, list, count, update, delete."""
    repo = BaseRepository[Supplier](db_session, Supplier)

    supplier_id = uuid.uuid4()
    supplier = Supplier(
        id=supplier_id,
        name="Bosch Mobility Solutions",
        country_code="DE",
        tier=1,
        risk_score=Decimal("0.125"),
        neptune_node_id="SUP-BOSCH-001",
    )
    created = await repo.create(supplier)
    assert created.id == supplier_id

    # Get by ID
    fetched = await repo.get_by_id(supplier_id)
    assert fetched is not None
    assert fetched.name == "Bosch Mobility Solutions"

    # Count & List
    count = await repo.count()
    assert count == 1
    items = await repo.list(offset=0, limit=10)
    assert len(items) == 1
    assert items[0].id == supplier_id

    # Update
    fetched.risk_score = Decimal("0.250")
    updated = await repo.update(fetched)
    assert updated.risk_score == Decimal("0.250")

    # Delete
    deleted = await repo.delete(supplier_id)
    assert deleted is True
    assert await repo.get_by_id(supplier_id) is None
    assert await repo.count() == 0


@pytest.mark.asyncio
async def test_supplier_repository_queries(db_session: AsyncSession) -> None:
    """Verify SupplierRepository domain query methods."""
    repo = SupplierRepository(db_session)

    s1 = Supplier(
        id=uuid.uuid4(),
        name="NanoCore Semiconductor",
        country_code="TW",
        tier=1,
        risk_score=Decimal("0.850"),
        neptune_node_id="SUP-NC-882",
    )
    s2 = Supplier(
        id=uuid.uuid4(),
        name="Infineon Technologies",
        country_code="DE",
        tier=1,
        risk_score=Decimal("0.220"),
        neptune_node_id="SUP-INF-101",
    )
    s3 = Supplier(
        id=uuid.uuid4(),
        name="Kyocera Precision",
        country_code="JP",
        tier=2,
        risk_score=Decimal("0.750"),
        neptune_node_id="SUP-KYO-302",
    )
    await repo.create(s1)
    await repo.create(s2)
    await repo.create(s3)

    # By Neptune Node ID
    found_node = await repo.get_by_neptune_node_id("SUP-NC-882")
    assert found_node is not None
    assert found_node.name == "NanoCore Semiconductor"

    # By Name
    found_name = await repo.get_by_name("Infineon Technologies")
    assert found_name is not None
    assert found_name.country_code == "DE"

    # By Tier
    tier_1_suppliers = await repo.get_by_tier(tier=1)
    assert len(tier_1_suppliers) == 2

    # By Country
    de_suppliers = await repo.get_by_country("DE")
    assert len(de_suppliers) == 1
    assert de_suppliers[0].name == "Infineon Technologies"

    # High Risk Filter (threshold >= 0.700)
    high_risk = await repo.get_high_risk_suppliers(threshold=Decimal("0.700"))
    assert len(high_risk) == 2
    high_risk_names = {s.name for s in high_risk}
    assert "NanoCore Semiconductor" in high_risk_names
    assert "Kyocera Precision" in high_risk_names

    # Update risk score
    updated = await repo.update_risk_score(s1.id, Decimal("0.920"))
    assert updated is not None
    assert updated.risk_score == Decimal("0.920")


@pytest.mark.asyncio
async def test_risk_alert_repository_queries(db_session: AsyncSession) -> None:
    """Verify RiskAlertRepository filtering, lookup, and status transitions."""
    supplier_repo = SupplierRepository(db_session)
    alert_repo = RiskAlertRepository(db_session)

    supplier = await supplier_repo.create(
        Supplier(
            id=uuid.uuid4(),
            name="NanoCore Semiconductor",
            country_code="TW",
            tier=1,
            risk_score=Decimal("0.850"),
            neptune_node_id="SUP-NC-882",
        )
    )

    alert1 = RiskAlert(
        id=uuid.uuid4(),
        supplier_id=supplier.id,
        component_sku="MCU-X91",
        risk_level="CRITICAL",
        days_of_cover=Decimal("7.68"),
        financial_exposure=Decimal("2448105.00"),
        shortage_volume=24420,
        status="OPEN",
    )
    alert2 = RiskAlert(
        id=uuid.uuid4(),
        supplier_id=supplier.id,
        component_sku="SENSOR-B2",
        risk_level="MEDIUM",
        days_of_cover=Decimal("18.50"),
        financial_exposure=Decimal("45000.00"),
        shortage_volume=1200,
        status="INVESTIGATING",
    )
    alert3 = RiskAlert(
        id=uuid.uuid4(),
        supplier_id=supplier.id,
        component_sku="RES-01",
        risk_level="LOW",
        days_of_cover=Decimal("45.00"),
        financial_exposure=Decimal("5000.00"),
        shortage_volume=0,
        status="CLOSED",
    )
    await alert_repo.create(alert1)
    await alert_repo.create(alert2)
    await alert_repo.create(alert3)

    # By Supplier ID
    supplier_alerts = await alert_repo.get_by_supplier_id(supplier.id)
    assert len(supplier_alerts) == 3

    # By Component SKU
    mcu_alerts = await alert_repo.get_by_component_sku("MCU-X91")
    assert len(mcu_alerts) == 1
    assert mcu_alerts[0].financial_exposure == Decimal("2448105.00")

    # By Status
    open_alerts = await alert_repo.get_by_status("OPEN")
    assert len(open_alerts) == 1
    assert open_alerts[0].component_sku == "MCU-X91"

    # Active Alerts (OPEN + INVESTIGATING)
    active = await alert_repo.get_active_alerts()
    assert len(active) == 2
    active_skus = {a.component_sku for a in active}
    assert "MCU-X91" in active_skus
    assert "SENSOR-B2" in active_skus

    # By Risk Level
    critical_alerts = await alert_repo.get_by_risk_level("CRITICAL")
    assert len(critical_alerts) == 1
    assert critical_alerts[0].id == alert1.id

    # Update Status
    transitioned = await alert_repo.update_status(alert1.id, "INVESTIGATING")
    assert transitioned is not None
    assert transitioned.status == "INVESTIGATING"


@pytest.mark.asyncio
async def test_hitl_approval_repository_anti_replay_and_signatures(
    db_session: AsyncSession,
) -> None:
    """Verify HITLApprovalRepository token anti-replay lookup and cryptographic signatures."""
    alert_repo = RiskAlertRepository(db_session)
    hitl_repo = HITLApprovalRepository(db_session)

    alert = await alert_repo.create(
        RiskAlert(
            id=uuid.uuid4(),
            component_sku="MCU-X91",
            risk_level="CRITICAL",
            status="INVESTIGATING",
        )
    )

    token_hash_nanocore = "hash_nanocore_expedite_approval_2026_p256"
    approval = HITLApproval(
        id=uuid.uuid4(),
        alert_id=alert.id,
        action_type="LOGISTICS_EXPEDITE",
        amount_usd=Decimal("2448105.00"),
        spend_tier="DUAL_VP",
        token_hash=token_hash_nanocore,
        status="PENDING",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    await hitl_repo.create(approval)

    # Anti-Replay: Lookup by unique token hash
    found_by_hash = await hitl_repo.get_by_token_hash(token_hash_nanocore)
    assert found_by_hash is not None
    assert found_by_hash.id == approval.id
    assert found_by_hash.spend_tier == "DUAL_VP"

    # Pending approvals query
    pending = await hitl_repo.get_pending_approvals()
    assert len(pending) == 1
    assert pending[0].id == approval.id

    # By Alert ID
    alert_approvals = await hitl_repo.get_by_alert_id(alert.id)
    assert len(alert_approvals) == 1

    # Record Signature (Signer 1: Procurement Director)
    signer_1 = uuid.uuid4()
    signed_1 = await hitl_repo.record_signature(
        approval_id=approval.id,
        signer_id=signer_1,
        new_status="PENDING",  # Dual approval still waiting on VP
    )
    assert signed_1 is not None
    assert str(signer_1) in [str(x) for x in (signed_1.approved_by or [])]
    assert len(signed_1.approved_at or []) == 1

    # Record Signature (Signer 2: VP Supply Chain)
    signer_2 = uuid.uuid4()
    signed_2 = await hitl_repo.record_signature(
        approval_id=approval.id,
        signer_id=signer_2,
        new_status="APPROVED",
    )
    assert signed_2 is not None
    assert str(signer_2) in [str(x) for x in (signed_2.approved_by or [])]
    assert len(signed_2.approved_by or []) == 2
    assert signed_2.status == "APPROVED"

    # Reject approval check
    approval_to_reject = await hitl_repo.create(
        HITLApproval(
            id=uuid.uuid4(),
            alert_id=alert.id,
            action_type="SPOT_BUY",
            amount_usd=Decimal("15000.00"),
            spend_tier="CATEGORY_MGR",
            token_hash="hash_spot_buy_reject_test",
            status="PENDING",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    rejecter = uuid.uuid4()
    rejected = await hitl_repo.reject_approval(
        approval_id=approval_to_reject.id,
        rejecter_id=rejecter,
    )
    assert rejected is not None
    assert rejected.status == "REJECTED"
    assert str(rejecter) in [str(x) for x in (rejected.approved_by or [])]


@pytest.mark.asyncio
async def test_audit_log_repository_append_only_immutability(
    db_session: AsyncSession,
) -> None:
    """Verify AuditLogRepository immutability invariant (BR-RULE-007): update/delete strictly prohibited."""
    repo = AuditLogRepository(db_session)

    entity_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    trace_id = "trace-audit-repo-test-771"

    log_entry = AuditLog(
        entity_type="risk_alerts",
        entity_id=entity_id,
        action="CREATE_ALERT",
        actor_id=actor_id,
        before_state=None,
        after_state={"component_sku": "MCU-X91", "risk_level": "CRITICAL"},
        trace_id=trace_id,
    )
    created = await repo.create(log_entry)
    assert created.id is not None

    # Query by entity
    logs = await repo.get_by_entity("risk_alerts", entity_id)
    assert len(logs) == 1
    assert logs[0].action == "CREATE_ALERT"

    # Query by trace ID
    trace_logs = await repo.get_by_trace_id(trace_id)
    assert len(trace_logs) == 1
    assert trace_logs[0].id == created.id

    # Query by actor
    actor_logs = await repo.get_by_actor(actor_id)
    assert len(actor_logs) == 1

    # List recent
    recent = await repo.list_recent(limit=5)
    assert len(recent) == 1

    # BR-RULE-007 Invariant: update must raise PermissionError at repository layer
    with pytest.raises(PermissionError, match="AuditLog is append-only"):
        await repo.update(created)

    # BR-RULE-007 Invariant: delete must raise PermissionError at repository layer
    with pytest.raises(PermissionError, match="AuditLog is append-only"):
        await repo.delete(created.id)


@pytest.mark.asyncio
async def test_agent_run_repository_lifecycle(db_session: AsyncSession) -> None:
    """Verify AgentRunRepository execution telemetry recording and completion tracking."""
    repo = AgentRunRepository(db_session)
    alert_id = uuid.uuid4()

    run = AgentRun(
        id=uuid.uuid4(),
        alert_id=alert_id,
        graph_name="investigation_graph",
        status="RUNNING",
        langfuse_trace_id="lf-trace-inv-9921",
        tokens_used=1200,
        cost_usd=Decimal("0.0060"),
    )
    created = await repo.create(run)
    assert created.status == "RUNNING"

    # Query by Langfuse trace ID
    by_trace = await repo.get_by_langfuse_trace_id("lf-trace-inv-9921")
    assert by_trace is not None
    assert by_trace.id == run.id

    # Query by alert ID
    by_alert = await repo.get_by_alert_id(alert_id)
    assert len(by_alert) == 1

    # Query by graph name
    by_graph = await repo.get_by_graph_name("investigation_graph")
    assert len(by_graph) == 1

    # Complete Run
    completed = await repo.complete_run(
        run_id=run.id,
        status="COMPLETED",
        duration_ms=2350,
        tokens_used=3500,
        cost_usd=Decimal("0.0175"),
    )
    assert completed is not None
    assert completed.status == "COMPLETED"
    assert completed.duration_ms == 2350
    assert completed.tokens_used == 3500
    assert completed.cost_usd == Decimal("0.0175")


@pytest.mark.asyncio
async def test_database_session_generator(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify get_db_session yields active session and manages transaction lifecycle."""
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    from src.core.config import get_settings
    from src.database.session import (
        get_async_engine,
        get_async_session_factory,
        get_db_session,
    )

    get_settings.cache_clear()
    get_async_engine.cache_clear()
    get_async_session_factory.cache_clear()

    async for session in get_db_session():
        assert isinstance(session, AsyncSession)
        from sqlalchemy import text

        result = await session.execute(text("SELECT 1"))
        assert result.scalar() == 1

    # Verify exception rollback handling
    with pytest.raises(RuntimeError, match="Simulated route error"):
        async for _session in get_db_session():
            raise RuntimeError("Simulated route error")

    get_settings.cache_clear()
    get_async_engine.cache_clear()
    get_async_session_factory.cache_clear()
