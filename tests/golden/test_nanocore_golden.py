"""Canonical NanoCore Golden Scenario Test Suite (P7-5).

Mandate:
- CLAUDE.md Section 14: "If test_nanocore_golden() fails, the build fails. No exceptions."
- GEMINI.md Section 2: "Golden Tests: pytest tests/golden/ -v (NanoCore reference scenario)"
- BR-RULE-001 (The Triad of Responsibility): 100% deterministic Python arithmetic.
  Zero LLM math, zero floating-point drift, exact Decimal precision.

Canonical NanoCore Scenario Reference Metrics:
- Stock: 142,000 units
- Daily Consumption: 18,500 units/day
- Replenishment ETA: 9.00 days
- Unit Cost: $100.25 / unit
- Factory Halt Cost: €85,000.00 / hour
- Days of Cover: 7.68 days (142,000 / 18,500 = 7.675675... -> 7.68)
- Shortage Gap: 1.32 days (9.00 - 7.68 = 1.32)
- Shortage Volume: 24,420 units (1.32 * 18,500 = 24,420)
- Financial Exposure: $2,448,105.00 (24,420 * $100.25 = $2,448,105.00)
- Factory Halt Exposure: €2,692,800.00 (1.32 days * 24 hrs * €85,000/hr = €2,692,800.00)
- Total Financial Impact: $5,140,905.00 ($2,448,105.00 + €2,692,800.00)
- Risk Severity Level: CRITICAL
- HITL Governance Tier: DUAL_VP (> $100k exposure requires dual VP sign-off, 30-min TTL)
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from src.core.hitl_tokens import SpendTier, get_spend_tier
from src.core.spend_tier_router import route_spend
from src.kafka.schemas.risk_alert import RiskLevel
from src.services.risk.calculator import (
    RiskAssessmentInput,
    RiskCalculator,
)
from src.services.risk.scorer import RiskScorer

GOLDEN_SCENARIO_PATH = Path(__file__).parent / "nanocore_scenario.json"


def _load_golden_json() -> dict[str, Any]:
    """Helper to load and validate raw JSON structure from tests/golden/nanocore_scenario.json."""
    assert GOLDEN_SCENARIO_PATH.exists(), f"Golden file missing: {GOLDEN_SCENARIO_PATH}"
    with open(GOLDEN_SCENARIO_PATH, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------------------
# 1. Canonical Golden Assertion (Mandatory Entrypoint)
# ------------------------------------------------------------------------------


def test_nanocore_golden() -> None:
    """Canonical test_nanocore_golden() function mandated by CLAUDE.md Section 14.

    If this test fails, the build fails. No exceptions.
    Asserts exact values:
    - days_of_cover == 7.68
    - shortage_volume == 24420
    - financial_exposure == 2448105.00
    """
    raw_data = _load_golden_json()
    inputs = raw_data["inputs"]
    expected = raw_data["expected"]

    calc = RiskCalculator()
    result = calc.calculate_from_dict(inputs)

    # 1. Assert Days of Cover
    assert result.days_of_cover == Decimal("7.68"), (
        f"Days of cover mismatch: expected 7.68, got {result.days_of_cover}"
    )
    assert result.days_of_cover == Decimal(str(expected["days_of_cover"]))

    # 2. Assert Gap Days
    assert result.gap_days == Decimal("1.32"), (
        f"Gap days mismatch: expected 1.32, got {result.gap_days}"
    )
    assert result.gap_days == Decimal(str(expected["gap_days"]))

    # 3. Assert Shortage Volume
    assert result.shortage_volume == 24420, (
        f"Shortage volume mismatch: expected 24420, got {result.shortage_volume}"
    )
    assert result.shortage_volume == expected["shortage_volume"]

    # 4. Assert Financial Exposure ($USD)
    assert result.financial_exposure == Decimal("2448105.00"), (
        f"Financial exposure mismatch: expected $2448105.00, got ${result.financial_exposure}"
    )
    assert result.financial_exposure_usd == Decimal("2448105.00")
    assert result.financial_exposure == Decimal(str(expected["financial_exposure_usd"]))

    # 5. Assert Shortage Flag
    assert result.is_shortage is True


# ------------------------------------------------------------------------------
# 2. Strict Decimal Precision & Non-Floating-Point Verification
# ------------------------------------------------------------------------------


def test_nanocore_golden_strict_decimal_precision() -> None:
    """Verify that zero floating-point types or IEEE 754 representations corrupt metrics.

    All outputs must be exact Decimal instances with ROUND_HALF_UP rounding.
    """
    calc = RiskCalculator()
    input_data = RiskAssessmentInput(
        current_stock=142000,
        daily_consumption_rate=18500,
        eta_days=Decimal("9.00"),
        unit_cost_usd=Decimal("100.25"),
        factory_halt_cost_per_hour_eur=Decimal("85000.00"),
    )
    result = calc.calculate(input_data)

    assert isinstance(result.days_of_cover, Decimal)
    assert isinstance(result.gap_days, Decimal)
    assert isinstance(result.financial_exposure, Decimal)
    assert isinstance(result.downtime_hours, Decimal)
    assert isinstance(result.factory_halt_exposure, Decimal)
    assert isinstance(result.total_exposure, Decimal)
    assert isinstance(result.shortage_volume, int)

    # Verify that string representation has exactly 2 decimal places
    assert str(result.days_of_cover) == "7.68"
    assert str(result.gap_days) == "1.32"
    assert str(result.financial_exposure) == "2448105.00"


# ------------------------------------------------------------------------------
# 3. Factory Line Halt & Comprehensive Downtime Exposure
# ------------------------------------------------------------------------------


def test_nanocore_golden_factory_halt_downtime() -> None:
    """Verify factory line halt calculation for Munich Assembly Hub (€85,000/hr).

    Formula: gap_days * operating_hours_per_day * hourly_halt_rate
    - gap_days = 1.32 days
    - operating_hours = 24.0 hours/day -> 31.68 hours total downtime
    - halt_rate = €85,000.00 / hour
    - factory_halt_exposure = 31.68 * €85,000.00 = €2,692,800.00
    - total_exposure = $2,448,105.00 + €2,692,800.00 = $5,140,905.00
    """
    calc = RiskCalculator()
    input_data = RiskAssessmentInput(
        current_stock=142000,
        daily_consumption_rate=18500,
        eta_days=Decimal("9.00"),
        unit_cost_usd=Decimal("100.25"),
        factory_halt_cost_per_hour_eur=Decimal("85000.00"),
    )
    result = calc.calculate(input_data)

    assert result.downtime_hours == Decimal("31.68")
    assert result.factory_halt_exposure == Decimal("2692800.00")
    assert result.total_exposure == Decimal("5140905.00")


# ------------------------------------------------------------------------------
# 4. Cryptographic Calculation Hash Verification
# ------------------------------------------------------------------------------


def test_nanocore_golden_calculation_hash_reproducibility() -> None:
    """Verify deterministic SHA-256 calculation hash across multiple executions.

    Tampering with any single parameter must result in an entirely different hash.
    """
    calc = RiskCalculator()
    input_data = RiskAssessmentInput(
        current_stock=142000,
        daily_consumption_rate=18500,
        eta_days=Decimal("9.00"),
        unit_cost_usd=Decimal("100.25"),
        factory_halt_cost_per_hour_eur=Decimal("85000.00"),
    )

    r1 = calc.calculate(input_data)
    r2 = calc.calculate(input_data)

    assert len(r1.calculation_hash) == 64
    assert r1.calculation_hash == r2.calculation_hash

    # Single unit change must diverge the cryptographic hash
    tampered_input = RiskAssessmentInput(
        current_stock=142001,
        daily_consumption_rate=18500,
        eta_days=Decimal("9.00"),
        unit_cost_usd=Decimal("100.25"),
        factory_halt_cost_per_hour_eur=Decimal("85000.00"),
    )
    r_tampered = calc.calculate(tampered_input)
    assert r_tampered.calculation_hash != r1.calculation_hash


# ------------------------------------------------------------------------------
# 5. Deterministic Risk Scorer & Severity Level Assignment
# ------------------------------------------------------------------------------


def test_nanocore_golden_severity_and_hitl_classification() -> None:
    """Verify that RiskScorer assigns RiskLevel.CRITICAL and routes to DUAL_VP spend tier.

    Threshold logic:
    - gap (1.32) > 0 AND financial_exposure ($2,448,105.00) > $1,000,000.00 -> CRITICAL
    - financial_exposure ($2,448,105.00) > $100,000.00 -> SpendTier.DUAL_VP
    """
    raw_data = _load_golden_json()
    inputs = raw_data["inputs"]
    expected = raw_data["expected"]

    calc = RiskCalculator()
    scorer = RiskScorer()

    assessment = calc.calculate_from_dict(inputs)
    score_result = scorer.score_assessment(
        assessment=assessment,
        eta_days=Decimal(str(inputs["eta_days"])),
        supplier_risk_score=Decimal("0.885"),
        is_single_source=True,
    )

    # Verify severity classification
    assert score_result.risk_level == RiskLevel.CRITICAL
    assert score_result.risk_level.value == expected["risk_level"]

    # Verify gap days and exposure alignment
    assert score_result.gap_days == Decimal("1.32")
    assert score_result.financial_exposure == Decimal("2448105.00")

    # Verify HITL governance
    assert score_result.requires_hitl is True
    assert score_result.recommended_hitl_tier == SpendTier.DUAL_VP
    assert score_result.is_single_source is True

    # Verify explanatory reasons
    assert any("exceeds CRITICAL threshold" in r for r in score_result.reasons)
    assert any("single-sourced" in r for r in score_result.reasons)
    assert any("DUAL_VP" in r for r in score_result.reasons)


# ------------------------------------------------------------------------------
# 6. HITL Spend Tier Routing & Cryptographic Gate Governance
# ------------------------------------------------------------------------------


def test_nanocore_golden_spend_tier_dual_vp_governance() -> None:
    """Verify that the $2,448,105.00 commitment triggers Dual VP sign-off with 30-min TTL.

    Enforces BR-RULE-001 spend governance:
    - <= $25,000: Category Manager (1-hr TTL)
    - $25,001 - $100,000: Procurement Director (1-hr TTL)
    - > $100,000: Dual VP (30-min TTL, 2x distinct signers)
    """
    exposure = Decimal("2448105.00")
    tier = get_spend_tier(exposure)
    assert tier == SpendTier.DUAL_VP

    route = route_spend(exposure)
    assert route.tier == SpendTier.DUAL_VP
    assert route.required_signatures == 2
    assert route.requires_dual_approval is True
    assert route.token_ttl.total_seconds() == 1800  # 30 minutes


# ------------------------------------------------------------------------------
# 7. Serialization & Dict Roundtrip
# ------------------------------------------------------------------------------


def test_nanocore_golden_dict_serialization_roundtrip() -> None:
    """Verify serialized dictionary format preserves exact Decimal strings."""
    calc = RiskCalculator()
    input_data = RiskAssessmentInput(
        current_stock=142000,
        daily_consumption_rate=18500,
        eta_days=Decimal("9.00"),
        unit_cost_usd=Decimal("100.25"),
        factory_halt_cost_per_hour_eur=Decimal("85000.00"),
    )
    result = calc.calculate(input_data)
    d = result.to_dict()

    assert d["days_of_cover"] == "7.68"
    assert d["gap_days"] == "1.32"
    assert d["shortage_volume"] == 24420
    assert d["financial_exposure"] == "2448105.00"
    assert d["factory_halt_exposure"] == "2692800.00"
    assert d["total_exposure"] == "5140905.00"
    assert d["is_shortage"] is True
    assert isinstance(d["created_at"], str)


# ------------------------------------------------------------------------------
# 8. Deviation Resistance Guard (Build Failure on Deviation)
# ------------------------------------------------------------------------------


def test_nanocore_golden_fails_on_deviation() -> None:
    """Verify that any arithmetic or rounding deviation triggers assertion failure."""
    calc = RiskCalculator()
    input_data = RiskAssessmentInput(
        current_stock=142000,
        daily_consumption_rate=18500,
        eta_days=Decimal("9.00"),
        unit_cost_usd=Decimal("100.25"),
    )
    result = calc.calculate(input_data)

    # Intentionally test against incorrect floating point numbers to ensure strict Decimal check
    with pytest.raises(AssertionError):
        assert result.days_of_cover == Decimal("7.67")

    with pytest.raises(AssertionError):
        assert result.shortage_volume == 24419

    with pytest.raises(AssertionError):
        assert result.financial_exposure == Decimal("2448104.99")
