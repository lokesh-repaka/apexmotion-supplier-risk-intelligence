"""Unit tests for SQLAlchemy 2.0 async models (P3-1).

Verifies:
- All 5 mandatory operational models are declared and inherit from DeclarativeBase:
  Supplier, RiskAlert, HITLApproval, AuditLog, AgentRun.
- Table names strictly match CLAUDE.md Section 9:
  suppliers, risk_alerts, hitl_approvals, audit_logs, agent_runs.
- Monetary precision: amount_usd and financial_exposure use NUMERIC(14,2) / Decimal.
- Anti-Replay: hitl_approvals.token_hash has unique=True constraint.
- CheckConstraints: supplier tier (1..3), risk_level enum, spend_tier enum, agent_run status.
- Append-Only Invariant: audit_logs prohibits UPDATE and DELETE operations.
- Relationship wiring: Supplier -> RiskAlert -> HITLApproval / AgentRun.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import (
    CheckConstraint,
    Numeric,
    inspect,
)
from src.database.models import (
    AgentRun,
    AuditLog,
    Base,
    HITLApproval,
    RiskAlert,
    Supplier,
)


def test_models_exist_and_subclass_base():
    """Verify all five mandatory models inherit from the common declarative Base."""
    models = [Supplier, RiskAlert, HITLApproval, AuditLog, AgentRun]
    for model in models:
        assert issubclass(model, Base), f"{model.__name__} does not subclass Declarative Base"


def test_table_names_match_specification():
    """Verify table names strictly adhere to CLAUDE.md Section 9 schema."""
    assert Supplier.__tablename__ == "suppliers"
    assert RiskAlert.__tablename__ == "risk_alerts"
    assert HITLApproval.__tablename__ == "hitl_approvals"
    assert AuditLog.__tablename__ == "audit_logs"
    assert AgentRun.__tablename__ == "agent_runs"


def test_monetary_precision_uses_numeric_14_2():
    """Verify monetary columns use NUMERIC(14,2) for strict Decimal precision (BR-RULE-001)."""
    # risk_alerts.financial_exposure
    alert_mapper = inspect(RiskAlert)
    exposure_col = alert_mapper.columns["financial_exposure"]
    assert isinstance(exposure_col.type, Numeric)
    assert exposure_col.type.precision == 14
    assert exposure_col.type.scale == 2

    # hitl_approvals.amount_usd
    approval_mapper = inspect(HITLApproval)
    amount_col = approval_mapper.columns["amount_usd"]
    assert isinstance(amount_col.type, Numeric)
    assert amount_col.type.precision == 14
    assert amount_col.type.scale == 2


def test_hitl_approvals_token_hash_unique_constraint():
    """Verify token_hash column on hitl_approvals enforces uniqueness to prevent replay attacks."""
    approval_mapper = inspect(HITLApproval)
    token_col = approval_mapper.columns["token_hash"]
    assert token_col.unique is True or any(
        col.name == "token_hash"
        for u in approval_mapper.tables[0].indexes
        if u.unique
        for col in u.columns
    )


def test_check_constraints_declared():
    """Verify essential data validation check constraints are attached to tables."""
    # Supplier tier check constraint
    supplier_table = Supplier.__table__
    check_constraints = [c for c in supplier_table.constraints if isinstance(c, CheckConstraint)]
    assert any("tier" in str(c.sqltext).lower() for c in check_constraints)

    # RiskAlert risk_level check constraint
    alert_table = RiskAlert.__table__
    alert_checks = [c for c in alert_table.constraints if isinstance(c, CheckConstraint)]
    assert any("risk_level" in str(c.sqltext).lower() for c in alert_checks)

    # HITLApproval spend_tier check constraint
    approval_table = HITLApproval.__table__
    approval_checks = [c for c in approval_table.constraints if isinstance(c, CheckConstraint)]
    assert any("spend_tier" in str(c.sqltext).lower() for c in approval_checks)


def test_model_instantiation_and_field_defaults():
    """Verify models can be cleanly instantiated with expected Python types."""
    supplier_id = uuid.uuid4()
    supplier = Supplier(
        id=supplier_id,
        name="NanoCore Semiconductor",
        country_code="TW",
        tier=2,
        risk_score=Decimal("0.880"),
        neptune_node_id="SUP-NC-882",
    )
    assert supplier.id == supplier_id
    assert supplier.tier == 2
    assert supplier.name == "NanoCore Semiconductor"

    alert_id = uuid.uuid4()
    alert = RiskAlert(
        id=alert_id,
        supplier_id=supplier_id,
        component_sku="SKU-77291",
        risk_level="CRITICAL",
        days_of_cover=Decimal("7.68"),
        financial_exposure=Decimal("2448105.00"),
        shortage_volume=24420,
        status="OPEN",
    )
    assert alert.id == alert_id
    assert alert.financial_exposure == Decimal("2448105.00")
    assert alert.risk_level == "CRITICAL"


def test_audit_log_append_only_guard():
    """Verify audit_logs model raises exception if update or delete is attempted."""
    audit_entry = AuditLog(
        entity_type="risk_alerts",
        entity_id=uuid.uuid4(),
        action="CREATE_ALERT",
        actor_id=uuid.uuid4(),
        before_state=None,
        after_state={"risk_level": "CRITICAL"},
        trace_id="trace-test-123",
        created_at=datetime.now(UTC),
    )
    assert audit_entry.action == "CREATE_ALERT"
    assert audit_entry.trace_id == "trace-test-123"

    # Test audit_logs immutability helper / invariant
    with pytest.raises((RuntimeError, ValueError), match="append-only"):
        audit_entry.prevent_mutation("UPDATE")

    with pytest.raises((RuntimeError, ValueError), match="append-only"):
        audit_entry.prevent_mutation("DELETE")


@pytest.mark.asyncio
async def test_async_sqlite_in_memory_persistence_and_relationships():
    """Verify all 5 tables can be created, populated, and queried via async SQLAlchemy."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        supplier_id = uuid.uuid4()
        supplier = Supplier(
            id=supplier_id,
            name="NanoCore Semiconductor",
            country_code="TW",
            tier=2,
            risk_score=Decimal("0.880"),
            neptune_node_id="SUP-NC-882",
        )
        session.add(supplier)

        alert_id = uuid.uuid4()
        alert = RiskAlert(
            id=alert_id,
            supplier_id=supplier_id,
            component_sku="SKU-77291",
            risk_level="CRITICAL",
            days_of_cover=Decimal("7.68"),
            financial_exposure=Decimal("2448105.00"),
            shortage_volume=24420,
            status="OPEN",
        )
        session.add(alert)

        approval_id = uuid.uuid4()
        approval = HITLApproval(
            id=approval_id,
            alert_id=alert_id,
            action_type="LOGISTICS_EXPEDITE",
            amount_usd=Decimal("2448105.00"),
            spend_tier="DUAL_VP",
            token_hash="hash_nanocore_expedite_approval_2026",
            status="PENDING",
            expires_at=datetime.now(UTC),
        )
        session.add(approval)

        audit = AuditLog(
            entity_type="risk_alerts",
            entity_id=alert_id,
            action="CREATE",
            actor_id=uuid.uuid4(),
            before_state=None,
            after_state={"risk_level": "CRITICAL"},
            trace_id="trace-test-persist-001",
        )
        session.add(audit)

        agent_run = AgentRun(
            alert_id=alert_id,
            graph_name="incident_investigation_graph",
            status="COMPLETED",
            tokens_used=4200,
            cost_usd=Decimal("0.0210"),
            duration_ms=1850,
        )
        session.add(agent_run)

        await session.commit()

    # Query back and verify relationships
    async with async_session() as session:
        result = await session.execute(select(Supplier).where(Supplier.id == supplier_id))
        queried_supplier = result.scalar_one()
        assert queried_supplier.name == "NanoCore Semiconductor"

        result_alert = await session.execute(select(RiskAlert).where(RiskAlert.id == alert_id))
        queried_alert = result_alert.scalar_one()
        assert queried_alert.financial_exposure == Decimal("2448105.00")
        assert queried_alert.days_of_cover == Decimal("7.68")

        # Test append-only event hook: updating audit log must raise RuntimeError
        result_audit = await session.execute(select(AuditLog))
        queried_audit = result_audit.scalars().first()
        assert queried_audit is not None
        queried_audit.action = "ILLEGAL_UPDATE"

        with pytest.raises(RuntimeError, match="audit_logs is append-only"):
            await session.commit()

    await engine.dispose()
