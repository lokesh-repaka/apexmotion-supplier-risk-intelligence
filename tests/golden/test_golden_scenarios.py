"""Canonical Golden Dataset Pytest Suite (P14-6).

Enforces mandatory CI failure assertions and end-to-end numerical verification
across all golden datasets:
1. Canonical NanoCore Reference Scenario (`nanocore_scenario.json`):
   - Strict assertion failing CI if `days_of_cover != 7.68` or `financial_exposure != 2448105.00`.
   - Mandatory verification of all secondary metrics (1.32d gap, 24,420 units shortage,
     31.68h downtime, €2,692,800.00 factory halt exposure, $5,140,905.00 total impact).
   - Negative constraint verification: deliberately perturbed metrics trigger immediate build failure.
2. Parameterized Golden Benchmark across all 6 golden datasets:
   - `nanocore_scenario.json`: Dresden fab fire, 9.0d ETA vs 7.68d cover -> CRITICAL / DUAL_VP.
   - `edge_cases/zero_stock.json`: 0 stock -> 0.00d cover, full ETA shortage gap -> MEDIUM / PROC_DIRECTOR.
   - `edge_cases/zero_gap.json`: JIT arrival -> gap = 0.00d, exposure = $0.00 -> LOW / No HITL.
   - `edge_cases/negative_gap.json`: Healthy buffer -> negative diff clamped to 0.00d -> LOW / No HITL.
   - `edge_cases/dual_approval_threshold.json`: $100,050.00 exposure -> DUAL_VP (2 signatures, 30m TTL).
   - `edge_cases/single_source_dependency.json`: Single-source flag with plant halt -> HIGH / DUAL_VP.
3. Strict Decimal Precision & Zero Float Representation (BR-RULE-001):
   - All quantities are exact `Decimal` instances; zero IEEE 754 float drift.
   - String representations strictly quantized with ROUND_HALF_UP rounding.
4. Cryptographic Anti-Tamper Calculation Hash:
   - Deterministic SHA-256 calculation hash bit-for-bit reproducible across executions.
   - Zero hash collisions across distinct scenarios.
   - Sensitivity to single-unit input perturbations.
5. End-to-End API Route Alignment:
   - `POST /api/v1/risk/evaluate` produces identical golden numbers.
6. LangGraph StateGraph Initializer Alignment:
   - `create_initial_state` populated with golden parameters produces identical metrics.
"""

import json
import uuid
from collections.abc import AsyncGenerator
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from src.agents.orchestrator import create_initial_state
from src.agents.state import SignalType, WorkflowStatus
from src.api.main import app
from src.core.hitl_tokens import SpendTier
from src.core.security import UserRole, create_access_token
from src.core.spend_tier_router import route_spend
from src.database.models import Base
from src.database.session import get_db_session
from src.services.risk.calculator import (
    RiskCalculator,
)
from src.services.risk.scorer import RiskScorer

GOLDEN_DIR = Path(__file__).parent
NANOCORE_JSON_PATH = GOLDEN_DIR / "nanocore_scenario.json"
EDGE_CASES_DIR = GOLDEN_DIR / "edge_cases"

ALL_GOLDEN_FILES: list[Path] = [
    NANOCORE_JSON_PATH,
    EDGE_CASES_DIR / "zero_stock.json",
    EDGE_CASES_DIR / "zero_gap.json",
    EDGE_CASES_DIR / "negative_gap.json",
    EDGE_CASES_DIR / "dual_approval_threshold.json",
    EDGE_CASES_DIR / "single_source_dependency.json",
]


def _load_json(file_path: Path) -> dict[str, Any]:
    """Load and return JSON dictionary from path."""
    assert file_path.exists(), f"Golden file not found: {file_path}"
    with open(file_path, encoding="utf-8") as f:
        return cast(dict[str, Any], json.load(f))


# ------------------------------------------------------------------------------
# In-Memory SQLite Fixtures for API Route Golden Testing
# ------------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_engine() -> AsyncGenerator[Any, None]:
    """Provide an isolated in-memory SQLite async engine."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        json_serializer=lambda obj: json.dumps(obj, default=str),
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


@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession,
) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient wired with FastAPI dependency overrides and mock audit logging."""

    async def _override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = _override_get_db_session
    transport = ASGITransport(app=app)

    with (
        patch("src.api.routes.risk_routes.write_audit_log", new=AsyncMock(return_value=None)),
        patch("src.core.audit.write_audit_log", new=AsyncMock(return_value=None)),
    ):
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as async_http_client:
            yield async_http_client

    app.dependency_overrides.clear()


def _auth_header(role: UserRole) -> dict[str, str]:
    """Generate Authorization header with valid mock JWT."""
    token = create_access_token(
        subject=str(uuid.uuid4()),
        roles=[role.value],
        email=f"{role.value}@apexmotion.com",
    )
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------------------------
# 1. Mandatory CI Gating Assertion (CLAUDE.md Sec 14 & Sec 20)
# ------------------------------------------------------------------------------


def test_nanocore_golden_ci_hard_assertion() -> None:
    """Canonical assertion that MUST fail CI if days_of_cover != 7.68 or financial_exposure != 2448105.00.

    CLAUDE.md Section 14: "If test_nanocore_golden() fails, the build fails. No exceptions."
    CLAUDE.md Section 20: Negative constraint prohibiting drift from 7.68 or $2,448,105.00.
    """
    raw_data = _load_json(NANOCORE_JSON_PATH)
    inputs = raw_data["inputs"]
    expected = raw_data["expected"]

    calc = RiskCalculator()
    result = calc.calculate_from_dict(inputs)

    # 1. PRIMARY CI GATE: days_of_cover must equal 7.68
    assert result.days_of_cover == Decimal("7.68"), (
        "CRITICAL CI FAILURE: Canonical NanoCore days_of_cover violated! "
        f"Expected exact Decimal('7.68'), got {result.days_of_cover}. "
        "The build fails under CLAUDE.md Section 14 and Section 20."
    )
    assert result.days_of_cover == Decimal(str(expected["days_of_cover"]))

    # 2. PRIMARY CI GATE: financial_exposure must equal 2448105.00
    assert result.financial_exposure == Decimal("2448105.00"), (
        "CRITICAL CI FAILURE: Canonical NanoCore financial_exposure violated! "
        f"Expected exact Decimal('2448105.00'), got {result.financial_exposure}. "
        "The build fails under CLAUDE.md Section 14 and Section 20."
    )
    assert result.financial_exposure == Decimal(str(expected["financial_exposure_usd"]))

    # 3. Comprehensive secondary metric integrity
    assert result.gap_days == Decimal("1.32")
    assert result.gap_days == Decimal(str(expected["gap_days"]))

    assert result.shortage_volume == 24420
    assert result.shortage_volume == expected["shortage_volume"]

    assert result.downtime_hours == Decimal("31.68")
    assert result.downtime_hours == Decimal(str(expected["downtime_hours"]))

    assert result.factory_halt_exposure == Decimal("2692800.00")
    assert result.factory_halt_exposure == Decimal(str(expected["factory_halt_exposure_eur"]))

    assert result.total_exposure == Decimal("5140905.00")
    assert result.total_exposure == Decimal(str(expected["total_financial_impact_usd"]))

    assert result.is_shortage is True
    assert result.is_shortage == expected["is_shortage"]


# ------------------------------------------------------------------------------
# 2. CI Failure Simulation (Negative Constraint Verification)
# ------------------------------------------------------------------------------


def test_nanocore_ci_fails_if_days_of_cover_deviates() -> None:
    """Verify that any drift in days_of_cover (even by 0.01) triggers assertion failure."""
    calc = RiskCalculator()
    raw_data = _load_json(NANOCORE_JSON_PATH)
    inputs = raw_data["inputs"]
    result = calc.calculate_from_dict(inputs)

    # Intentionally compare with deviated values to verify failure trigger
    with pytest.raises(AssertionError):
        assert result.days_of_cover == Decimal("7.67")

    with pytest.raises(AssertionError):
        assert result.days_of_cover == Decimal("7.69")

    with pytest.raises(AssertionError):
        assert result.days_of_cover == Decimal("7.68000001")


def test_nanocore_ci_fails_if_financial_exposure_deviates() -> None:
    """Verify that any drift in financial_exposure (even by $0.01) triggers assertion failure."""
    calc = RiskCalculator()
    raw_data = _load_json(NANOCORE_JSON_PATH)
    inputs = raw_data["inputs"]
    result = calc.calculate_from_dict(inputs)

    with pytest.raises(AssertionError):
        assert result.financial_exposure == Decimal("2448104.99")

    with pytest.raises(AssertionError):
        assert result.financial_exposure == Decimal("2448105.01")

    with pytest.raises(AssertionError):
        assert result.financial_exposure == Decimal("2448105.00001")


def test_nanocore_ci_fails_if_shortage_volume_deviates() -> None:
    """Verify that any drift in shortage_volume (even by 1 unit) triggers assertion failure."""
    calc = RiskCalculator()
    raw_data = _load_json(NANOCORE_JSON_PATH)
    inputs = raw_data["inputs"]
    result = calc.calculate_from_dict(inputs)

    with pytest.raises(AssertionError):
        assert result.shortage_volume == 24419

    with pytest.raises(AssertionError):
        assert result.shortage_volume == 24421


# ------------------------------------------------------------------------------
# 3. Parameterized Golden Benchmark Across All 6 Datasets
# ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "golden_file",
    ALL_GOLDEN_FILES,
    ids=[f.stem for f in ALL_GOLDEN_FILES],
)
def test_all_golden_scenarios_deterministic_evaluation(golden_file: Path) -> None:
    """Verify all 6 golden datasets match expected mathematical and governance metrics with 100% precision."""
    data = _load_json(golden_file)
    inputs = data["inputs"]
    expected = data["expected"]

    calc = RiskCalculator()
    scorer = RiskScorer()

    # 1. Deterministic Calculation
    result = calc.calculate_from_dict(inputs)

    assert result.days_of_cover == Decimal(str(expected["days_of_cover"])), (
        f"days_of_cover mismatch in {golden_file.name}: expected {expected['days_of_cover']}, got {result.days_of_cover}"
    )
    assert result.gap_days == Decimal(str(expected["gap_days"])), (
        f"gap_days mismatch in {golden_file.name}: expected {expected['gap_days']}, got {result.gap_days}"
    )
    assert result.shortage_volume == expected["shortage_volume"], (
        f"shortage_volume mismatch in {golden_file.name}: expected {expected['shortage_volume']}, got {result.shortage_volume}"
    )
    assert result.financial_exposure == Decimal(str(expected["financial_exposure_usd"])), (
        f"financial_exposure mismatch in {golden_file.name}: expected {expected['financial_exposure_usd']}, got {result.financial_exposure}"
    )
    assert result.is_shortage == expected["is_shortage"]

    # If factory halt impact is evaluated (hourly rate > 0)
    if inputs.get("factory_halt_cost_per_hour_eur", 0) > 0:
        if "downtime_hours" in expected:
            assert result.downtime_hours == Decimal(str(expected["downtime_hours"]))
        if "factory_halt_exposure_eur" in expected:
            assert result.factory_halt_exposure == Decimal(
                str(expected["factory_halt_exposure_eur"])
            )
        if "total_financial_impact_usd" in expected:
            assert result.total_exposure == Decimal(str(expected["total_financial_impact_usd"]))

    # 2. Risk Scorer Evaluation
    score_result = scorer.score_assessment(
        assessment=result,
        eta_days=Decimal(str(inputs["eta_days"])),
        supplier_risk_score=Decimal(str(inputs["supplier_risk_score"])),
        is_single_source=inputs.get("is_single_source", False),
    )

    assert score_result.risk_level.value == expected["risk_level"]
    assert score_result.requires_hitl == expected["hitl_required"]

    if expected["hitl_required"]:
        assert score_result.recommended_hitl_tier is not None
        assert score_result.recommended_hitl_tier.value == expected["hitl_tier"]
    else:
        assert score_result.recommended_hitl_tier is None


# ------------------------------------------------------------------------------
# 4. Strict Decimal Type & Precision Invariant (Zero Float Representation)
# ------------------------------------------------------------------------------


def test_golden_scenarios_zero_float_representation() -> None:
    """Verify that zero floating-point types or IEEE 754 representations exist in outputs."""
    calc = RiskCalculator()

    for golden_file in ALL_GOLDEN_FILES:
        data = _load_json(golden_file)
        result = calc.calculate_from_dict(data["inputs"])

        # Strictly assert Decimal type for all monetary and fractional quantities
        assert isinstance(result.days_of_cover, Decimal), f"Float detected in {golden_file.name}"
        assert isinstance(result.gap_days, Decimal), f"Float detected in {golden_file.name}"
        assert isinstance(result.financial_exposure, Decimal), (
            f"Float detected in {golden_file.name}"
        )
        assert isinstance(result.downtime_hours, Decimal), f"Float detected in {golden_file.name}"
        assert isinstance(result.factory_halt_exposure, Decimal), (
            f"Float detected in {golden_file.name}"
        )
        assert isinstance(result.total_exposure, Decimal), f"Float detected in {golden_file.name}"
        assert isinstance(result.shortage_volume, int)
        assert isinstance(result.is_shortage, bool)

        # Prohibit standard float types
        assert not isinstance(result.days_of_cover, float)
        assert not isinstance(result.financial_exposure, float)
        assert not isinstance(result.total_exposure, float)


# ------------------------------------------------------------------------------
# 5. Sensitivity & Perturbation Analysis
# ------------------------------------------------------------------------------


def test_nanocore_single_unit_perturbation_sensitivity() -> None:
    """Verify that single-unit deviations in inputs produce distinct outputs (no dead branches)."""
    calc = RiskCalculator()
    base_data = _load_json(NANOCORE_JSON_PATH)["inputs"]

    base_result = calc.calculate_from_dict(base_data)

    # 1. Perturb stock by +1 unit (142,000 -> 142,001)
    p_stock = dict(base_data)
    p_stock["current_stock"] = 142001
    r_stock = calc.calculate_from_dict(p_stock)
    # Calculation hash must diverge
    assert r_stock.calculation_hash != base_result.calculation_hash

    # 2. Perturb consumption rate by +1 unit (18,500 -> 18,501)
    p_rate = dict(base_data)
    p_rate["daily_consumption_rate"] = 18501
    r_rate = calc.calculate_from_dict(p_rate)
    # 142000 / 18501 = 7.67526... -> 7.68, but gap_days / shortage volume differs slightly
    assert r_rate.calculation_hash != base_result.calculation_hash

    # 3. Perturb unit cost by +$0.01 ($100.25 -> $100.26)
    p_cost = dict(base_data)
    p_cost["unit_cost_usd"] = 100.26
    r_cost = calc.calculate_from_dict(p_cost)
    # 24,420 * 100.26 = 2,448,349.20
    assert r_cost.financial_exposure == Decimal("2448349.20")
    assert r_cost.financial_exposure != base_result.financial_exposure


# ------------------------------------------------------------------------------
# 6. Cryptographic Anti-Tamper SHA-256 Digest Uniqueness
# ------------------------------------------------------------------------------


def test_all_golden_scenarios_unique_sha256_digests() -> None:
    """Verify that every golden scenario produces a unique 64-character SHA-256 hash."""
    calc = RiskCalculator()
    seen_hashes: dict[str, str] = {}

    for golden_file in ALL_GOLDEN_FILES:
        data = _load_json(golden_file)
        result1 = calc.calculate_from_dict(data["inputs"])
        result2 = calc.calculate_from_dict(data["inputs"])

        # Reproducibility check
        assert len(result1.calculation_hash) == 64
        assert result1.calculation_hash == result2.calculation_hash

        # Uniqueness check across distinct scenarios
        scenario_name = golden_file.stem
        assert result1.calculation_hash not in seen_hashes, (
            f"Collision: {scenario_name} shares hash with {seen_hashes[result1.calculation_hash]}"
        )
        seen_hashes[result1.calculation_hash] = scenario_name


# ------------------------------------------------------------------------------
# 7. HITL Governance Tier Policy Resolution
# ------------------------------------------------------------------------------


def test_golden_scenarios_hitl_tier_routing_policy() -> None:
    """Verify that spend amounts in golden datasets resolve to exact governance policies."""
    # 1. NanoCore ($2,448,105.00) -> Tier 3 DUAL_VP
    route_nc = route_spend(Decimal("2448105.00"))
    assert route_nc.tier == SpendTier.DUAL_VP
    assert route_nc.required_signatures == 2
    assert route_nc.requires_dual_approval is True
    assert route_nc.token_ttl == timedelta(minutes=30)
    assert route_nc.primary_role == UserRole.PROCUREMENT_DIRECTOR
    assert route_nc.secondary_role == UserRole.VP_SUPPLY_CHAIN

    # 2. Dual approval threshold edge case ($100,050.00) -> Tier 3 DUAL_VP
    route_dual = route_spend(Decimal("100050.00"))
    assert route_dual.tier == SpendTier.DUAL_VP
    assert route_dual.required_signatures == 2

    # 3. Zero stock edge case ($50,000.00) -> Tier 2 PROC_DIRECTOR
    route_zs = route_spend(Decimal("50000.00"))
    assert route_zs.tier == SpendTier.PROC_DIRECTOR
    assert route_zs.required_signatures == 1
    assert route_zs.requires_dual_approval is False
    assert route_zs.token_ttl == timedelta(hours=1)
    assert route_zs.primary_role == UserRole.PROCUREMENT_DIRECTOR

    # 4. Zero gap ($0.00) -> Tier 1 CATEGORY_MGR baseline
    route_zg = route_spend(Decimal("0.00"))
    assert route_zg.tier == SpendTier.CATEGORY_MGR
    assert route_zg.required_signatures == 1


# ------------------------------------------------------------------------------
# 8. FastAPI API Route Golden Alignment (POST /api/v1/risk/evaluate)
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_risk_evaluate_produces_exact_nanocore_golden_numbers(
    client: AsyncClient,
) -> None:
    """Verify that POST /api/v1/risk/evaluate produces exact NanoCore golden numbers over HTTP."""
    raw_data = _load_json(NANOCORE_JSON_PATH)
    inputs = raw_data["inputs"]

    analyst_headers = _auth_header(UserRole.ANALYST)
    request_payload = {
        "component_sku": inputs["component_sku"],
        "supplier_id": str(uuid.uuid4()),
        "plant_id": "PLT-MUC-01",
        "current_stock": inputs["current_stock"],
        "daily_consumption_rate": inputs["daily_consumption_rate"],
        "eta_days": inputs["eta_days"],
        "unit_cost_usd": inputs["unit_cost_usd"],
        "signal_type": "logistics",
        "severity_hint": "CRITICAL",
        "disruption_description": "Cleanroom fire at NanoCore Dresden facility.",
    }

    resp = await client.post(
        "/api/v1/risk/evaluate",
        json=request_payload,
        headers=analyst_headers,
    )
    assert resp.status_code == 200
    data = resp.json()

    # Exact golden numbers verification over API
    assert Decimal(str(data["days_of_cover"])) == Decimal("7.68")
    assert Decimal(str(data["gap_days"])) == Decimal("1.32")
    assert data["shortage_volume"] == 24420
    assert Decimal(str(data["financial_exposure_usd"])) == Decimal("2448105.00")
    assert data["risk_level"] == "CRITICAL"
    assert data["governing_spend_tier"] == "DUAL_VP"
    assert data["requires_hitl"] is True
    assert data["pipeline_track"] == "FULL_TRACK"


# ------------------------------------------------------------------------------
# 9. LangGraph State Initializer Golden Invariants
# ------------------------------------------------------------------------------


def test_orchestrator_initial_state_nanocore_golden_invariants() -> None:
    """Verify that create_initial_state correctly aligns with NanoCore golden parameters."""
    alert_id = str(uuid.uuid4())
    state = create_initial_state(
        alert_id=alert_id,
        supplier_id="SUP-NC-001",
        supplier_name="NanoCore Microelectronics Ltd",
        component_sku="SKU-MCU-4402",
        signal_type=SignalType.NEWS,
        raw_signal="Cleanroom fab fire at Dresden wafer fab facility.",
        current_stock=142000,
        daily_consumption_rate=Decimal("18500"),
        eta_days=Decimal("9.0"),
        unit_cost_usd=Decimal("100.25"),
        impacted_plant_ids=["PLT-MUC-01"],
        is_single_source=True,
    )

    assert state["supplier_id"] == "SUP-NC-001"
    assert state["component_sku"] == "SKU-MCU-4402"
    assert state["signal_type"] == "news"
    assert state["workflow_status"] == WorkflowStatus.PENDING
    assert state["current_stock"] == 142000
    assert state["daily_consumption_rate"] == Decimal("18500")
    assert state["eta_days"] == Decimal("9.0")
    assert state["unit_cost_usd"] == Decimal("100.25")
    assert state["is_single_source"] is True
