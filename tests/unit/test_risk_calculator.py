"""Unit tests for deterministic Risk Calculator (P7-1).

Verifies:
- The Triad of Responsibility (BR-RULE-001): 100% deterministic pure Python math.
- All monetary and inventory metrics use Decimal precision with zero float truncation.
- Exact reproduction of the canonical NanoCore golden scenario:
  days_of_cover=7.68, gap_days=1.32, shortage_volume=24420, financial_exposure=$2,448,105.00.
- Mandatory edge cases:
  1. Zero stock (current_stock = 0)
  2. Zero consumption (daily_consumption_rate = 0 -> days_of_cover = 999.00)
  3. Negative gap (ETA < days of cover -> gap_days = 0.00, shortage = 0, exposure = 0.00)
  4. Exact zero gap (ETA == days of cover)
  5. Zero unit cost (unit_cost_usd = 0.00 -> exposure = 0.00)
  6. Negative input validations (stock < 0, rate < 0, eta < 0, cost < 0)
- Factory halt downtime exposure calculations (€85,000/hr factory line impact).
- Deterministic SHA-256 calculation verification hash.
- 100% statement and branch coverage on src/services/risk/calculator.py.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from src.services.risk.calculator import (
    DAYS_OF_COVER_MAX_CAP,
    InvalidInventoryInputError,
    RiskAssessmentInput,
    RiskCalculator,
)

REPO_ROOT = Path(__file__).parent.parent.parent
GOLDEN_FILE = REPO_ROOT / "tests" / "golden" / "nanocore_scenario.json"


# ------------------------------------------------------------------------------
# NanoCore Canonical Golden Scenario Tests
# ------------------------------------------------------------------------------


def test_nanocore_golden_scenario_math_exact() -> None:
    """Verify canonical NanoCore golden scenario matches required values to the cent.

    NanoCore reference numbers:
    - current_stock: 142,000 units
    - daily_consumption_rate: 18,500 units/day
    - eta_days: 9.00 days
    - unit_cost_usd: $100.25 / unit
    - expected days_of_cover: 7.68 days (142000 / 18500 = 7.6756... -> 7.68)
    - expected gap_days: 1.32 days (9.00 - 7.68 = 1.32)
    - expected shortage_volume: 24,420 units (1.32 * 18500 = 24420)
    - expected financial_exposure: $2,448,105.00 (24420 * $100.25 = $2,448,105.00)
    """
    calc = RiskCalculator()
    input_data = RiskAssessmentInput(
        current_stock=142000,
        daily_consumption_rate=18500,
        eta_days=Decimal("9.00"),
        unit_cost_usd=Decimal("100.25"),
        supplier_id="SUP-NC-001",
        component_sku="SKU-MCU-4402",
        factory_halt_cost_per_hour_eur=Decimal("85000.00"),
    )

    result = calc.calculate(input_data)

    assert result.days_of_cover == Decimal("7.68")
    assert result.gap_days == Decimal("1.32")
    assert result.shortage_volume == 24420
    assert result.financial_exposure == Decimal("2448105.00")
    assert result.financial_exposure_usd == Decimal("2448105.00")
    assert result.is_shortage is True
    assert len(result.calculation_hash) == 64


def test_nanocore_golden_json_file_integration() -> None:
    """Verify direct calculation from tests/golden/nanocore_scenario.json."""
    assert GOLDEN_FILE.exists(), f"Golden file not found at {GOLDEN_FILE}"

    with open(GOLDEN_FILE, encoding="utf-8") as f:
        data = json.load(f)

    inputs = data["inputs"]
    expected = data["expected"]

    calc = RiskCalculator()
    result = calc.calculate_from_dict(inputs)

    assert result.days_of_cover == Decimal(str(expected["days_of_cover"]))
    assert result.gap_days == Decimal(str(expected["gap_days"]))
    assert result.shortage_volume == expected["shortage_volume"]
    assert result.financial_exposure == Decimal(str(expected["financial_exposure_usd"]))
    assert result.is_shortage is True


# ------------------------------------------------------------------------------
# Edge Case 1: Zero Stock
# ------------------------------------------------------------------------------


def test_edge_case_zero_stock() -> None:
    """Verify calculation when inventory is completely depleted (current_stock = 0).

    Expected:
    - days_of_cover: 0.00
    - gap_days: equals eta_days (e.g. 5.00)
    - shortage_volume: eta_days * daily_rate (5.00 * 1,000 = 5,000 units)
    - financial_exposure: shortage_volume * unit_cost (5,000 * $10.00 = $50,000.00)
    """
    calc = RiskCalculator()
    input_data = RiskAssessmentInput(
        current_stock=0,
        daily_consumption_rate=1000,
        eta_days=Decimal("5.00"),
        unit_cost_usd=Decimal("10.00"),
    )

    result = calc.calculate(input_data)

    assert result.days_of_cover == Decimal("0.00")
    assert result.gap_days == Decimal("5.00")
    assert result.shortage_volume == 5000
    assert result.financial_exposure == Decimal("50000.00")
    assert result.is_shortage is True


# ------------------------------------------------------------------------------
# Edge Case 2: Zero Consumption Rate
# ------------------------------------------------------------------------------


def test_edge_case_zero_consumption_rate() -> None:
    """Verify calculation when daily consumption rate is 0.

    Per FRD and engineering rules:
    - Zero consumption means inventory will never deplete.
    - days_of_cover = 999.00 (DAYS_OF_COVER_MAX_CAP).
    - gap_days = 0.00 (no disruption possible).
    - shortage_volume = 0.
    - financial_exposure = 0.00.
    """
    calc = RiskCalculator()
    input_data = RiskAssessmentInput(
        current_stock=50000,
        daily_consumption_rate=0,
        eta_days=Decimal("10.00"),
        unit_cost_usd=Decimal("25.00"),
    )

    result = calc.calculate(input_data)

    assert result.days_of_cover == DAYS_OF_COVER_MAX_CAP
    assert result.days_of_cover == Decimal("999.00")
    assert result.gap_days == Decimal("0.00")
    assert result.shortage_volume == 0
    assert result.financial_exposure == Decimal("0.00")
    assert result.is_shortage is False


# ------------------------------------------------------------------------------
# Edge Case 3: Negative Gap (Healthy Inventory / ETA < Days of Cover)
# ------------------------------------------------------------------------------


def test_edge_case_negative_gap_healthy_buffer() -> None:
    """Verify that when delivery arrives before stock depletes, gap is strictly clamped to 0.00.

    Scenario:
    - current_stock: 200,000
    - daily_consumption_rate: 10,000 (days_of_cover = 20.00)
    - eta_days: 5.00 days (arrival 15 days before stockout)
    - gap_days = max(0.00, 5.00 - 20.00) = 0.00
    - shortage_volume = 0
    - financial_exposure = 0.00
    """
    calc = RiskCalculator()
    input_data = RiskAssessmentInput(
        current_stock=200000,
        daily_consumption_rate=10000,
        eta_days=Decimal("5.00"),
        unit_cost_usd=Decimal("50.00"),
    )

    result = calc.calculate(input_data)

    assert result.days_of_cover == Decimal("20.00")
    assert result.gap_days == Decimal("0.00")
    assert result.shortage_volume == 0
    assert result.financial_exposure == Decimal("0.00")
    assert result.is_shortage is False


# ------------------------------------------------------------------------------
# Edge Case 4: Exact Zero Gap (Just-In-Time Delivery)
# ------------------------------------------------------------------------------


def test_edge_case_exact_zero_gap() -> None:
    """Verify calculation when ETA exactly matches days of cover."""
    calc = RiskCalculator()
    input_data = RiskAssessmentInput(
        current_stock=100000,
        daily_consumption_rate=10000,
        eta_days=Decimal("10.00"),
        unit_cost_usd=Decimal("15.00"),
    )

    result = calc.calculate(input_data)

    assert result.days_of_cover == Decimal("10.00")
    assert result.gap_days == Decimal("0.00")
    assert result.shortage_volume == 0
    assert result.financial_exposure == Decimal("0.00")
    assert result.is_shortage is False


# ------------------------------------------------------------------------------
# Edge Case 5: Zero Unit Cost
# ------------------------------------------------------------------------------


def test_edge_case_zero_unit_cost() -> None:
    """Verify financial exposure is 0.00 when component unit cost is zero."""
    calc = RiskCalculator()
    input_data = RiskAssessmentInput(
        current_stock=1000,
        daily_consumption_rate=500,
        eta_days=Decimal("4.00"),
        unit_cost_usd=Decimal("0.00"),
    )

    result = calc.calculate(input_data)

    assert result.days_of_cover == Decimal("2.00")
    assert result.gap_days == Decimal("2.00")
    assert result.shortage_volume == 1000
    assert result.financial_exposure == Decimal("0.00")


# ------------------------------------------------------------------------------
# Negative Input Validation Tests
# ------------------------------------------------------------------------------


def test_validation_rejects_negative_stock() -> None:
    """Assert InvalidInventoryInputError on negative inventory stock."""
    calc = RiskCalculator()
    with pytest.raises(InvalidInventoryInputError, match="Current stock cannot be negative"):
        calc.calculate_from_params(
            current_stock=-100,
            daily_consumption_rate=1000,
            eta_days="5.0",
            unit_cost_usd="10.0",
        )


def test_validation_rejects_negative_consumption_rate() -> None:
    """Assert InvalidInventoryInputError on negative daily consumption rate."""
    calc = RiskCalculator()
    with pytest.raises(InvalidInventoryInputError, match="Consumption rate cannot be negative"):
        calc.calculate_from_params(
            current_stock=1000,
            daily_consumption_rate=-50,
            eta_days="5.0",
            unit_cost_usd="10.0",
        )


def test_validation_rejects_negative_eta() -> None:
    """Assert InvalidInventoryInputError on negative ETA."""
    calc = RiskCalculator()
    with pytest.raises(InvalidInventoryInputError, match="ETA days cannot be negative"):
        calc.calculate_from_params(
            current_stock=1000,
            daily_consumption_rate=100,
            eta_days="-1.0",
            unit_cost_usd="10.0",
        )


def test_validation_rejects_negative_unit_cost() -> None:
    """Assert InvalidInventoryInputError on negative unit cost."""
    calc = RiskCalculator()
    with pytest.raises(InvalidInventoryInputError, match="Unit cost cannot be negative"):
        calc.calculate_from_params(
            current_stock=1000,
            daily_consumption_rate=100,
            eta_days="5.0",
            unit_cost_usd="-10.0",
        )


def test_validation_rejects_invalid_type_coercion() -> None:
    """Assert InvalidInventoryInputError on invalid non-numeric string values and None."""
    from src.services.risk.calculator import _to_decimal

    calc = RiskCalculator()
    with pytest.raises(InvalidInventoryInputError, match="Failed to parse Decimal"):
        calc.calculate_from_params(
            current_stock=1000,
            daily_consumption_rate=100,
            eta_days="not-a-number",
            unit_cost_usd="10.0",
        )

    with pytest.raises(InvalidInventoryInputError, match="Field 'test_none' cannot be None"):
        _to_decimal(None, "test_none")


def test_validation_rejects_negative_days_of_cover_and_shortage_volume() -> None:
    """Assert InvalidInventoryInputError on negative days_of_cover and shortage_volume."""
    with pytest.raises(InvalidInventoryInputError, match="Days of cover cannot be negative"):
        RiskCalculator.calculate_gap_days(eta_days=5, days_of_cover=-2)

    with pytest.raises(InvalidInventoryInputError, match="Shortage volume cannot be negative"):
        RiskCalculator.calculate_financial_exposure(shortage_volume=-10, unit_cost_usd=10)


def test_downtime_exposure_zero_when_gap_is_non_positive() -> None:
    """Assert calculate_downtime_exposure returns 0.00 when gap is 0 or negative."""
    assert RiskCalculator.calculate_downtime_exposure(gap_days=Decimal("0.00")) == Decimal("0.00")
    assert RiskCalculator.calculate_downtime_exposure(gap_days=Decimal("-2.00")) == Decimal("0.00")


# ------------------------------------------------------------------------------
# Factory Line Halt Exposure Calculations
# ------------------------------------------------------------------------------


def test_factory_halt_downtime_exposure() -> None:
    """Verify factory line halt calculation with hours per day and hourly rate.

    Scenario:
    - gap_days: 1.32 days
    - operating_hours_per_day: 24.0 hours
    - hourly_halt_rate: €85,000.00
    - downtime_hours: 1.32 * 24.0 = 31.68 hours
    - expected halt cost: 31.68 * 85000 = €2,692,800.00
    """
    calc = RiskCalculator()
    input_data = RiskAssessmentInput(
        current_stock=142000,
        daily_consumption_rate=18500,
        eta_days=Decimal("9.00"),
        unit_cost_usd=Decimal("100.25"),
        factory_halt_cost_per_hour_eur=Decimal("85000.00"),
        operating_hours_per_day=Decimal("24.0"),
    )

    result = calc.calculate(input_data)

    assert result.downtime_hours == Decimal("31.68")
    assert result.factory_halt_exposure == Decimal("2692800.00")
    # Total exposure = component shortage exposure ($2,448,105.00) + factory halt exposure (€2,692,800.00)
    assert result.total_exposure == Decimal("5140905.00")


def test_factory_halt_zero_when_no_gap() -> None:
    """Verify factory halt exposure is 0.00 when there is no coverage gap."""
    calc = RiskCalculator()
    input_data = RiskAssessmentInput(
        current_stock=100000,
        daily_consumption_rate=10000,
        eta_days=Decimal("5.00"),
        unit_cost_usd=Decimal("10.00"),
        factory_halt_cost_per_hour_eur=Decimal("85000.00"),
    )

    result = calc.calculate(input_data)

    assert result.downtime_hours == Decimal("0.00")
    assert result.factory_halt_exposure == Decimal("0.00")
    assert result.total_exposure == Decimal("0.00")


# ------------------------------------------------------------------------------
# Helper Static Functions & Hash Determinism
# ------------------------------------------------------------------------------


def test_static_calculation_helpers() -> None:
    """Verify individual static calculation formulas."""
    # Days of cover
    doc = RiskCalculator.calculate_days_of_cover(142000, 18500)
    assert doc == Decimal("7.68")

    # Gap days
    gap = RiskCalculator.calculate_gap_days(Decimal("9.00"), Decimal("7.68"))
    assert gap == Decimal("1.32")

    # Shortage volume
    vol = RiskCalculator.calculate_shortage_volume(Decimal("1.32"), 18500)
    assert vol == 24420

    # Financial exposure
    exp = RiskCalculator.calculate_financial_exposure(24420, Decimal("100.25"))
    assert exp == Decimal("2448105.00")

    # Downtime exposure
    downtime_exp = RiskCalculator.calculate_downtime_exposure(
        gap_days=Decimal("1.32"),
        operating_hours_per_day=Decimal("24.0"),
        hourly_rate=Decimal("85000.00"),
    )
    assert downtime_exp == Decimal("2692800.00")


def test_calculation_hash_reproducibility() -> None:
    """Verify calculation hash is identical for identical inputs and changes on variation."""
    calc = RiskCalculator()
    input_1 = RiskAssessmentInput(
        current_stock=142000,
        daily_consumption_rate=18500,
        eta_days=Decimal("9.00"),
        unit_cost_usd=Decimal("100.25"),
    )
    input_2 = RiskAssessmentInput(
        current_stock=142000,
        daily_consumption_rate=18500,
        eta_days=Decimal("9.00"),
        unit_cost_usd=Decimal("100.25"),
    )
    input_diff = RiskAssessmentInput(
        current_stock=142001,
        daily_consumption_rate=18500,
        eta_days=Decimal("9.00"),
        unit_cost_usd=Decimal("100.25"),
    )

    res_1 = calc.calculate(input_1)
    res_2 = calc.calculate(input_2)
    res_diff = calc.calculate(input_diff)

    assert res_1.calculation_hash == res_2.calculation_hash
    assert res_1.calculation_hash != res_diff.calculation_hash


def test_to_dict_and_json_serialization() -> None:
    """Verify RiskAssessmentResult serialization to dict and JSON preserving Decimal precision."""
    calc = RiskCalculator()
    input_data = RiskAssessmentInput(
        current_stock=142000,
        daily_consumption_rate=18500,
        eta_days=Decimal("9.00"),
        unit_cost_usd=Decimal("100.25"),
    )
    result = calc.calculate(input_data)
    d = result.to_dict()

    assert d["days_of_cover"] == "7.68"
    assert d["gap_days"] == "1.32"
    assert d["shortage_volume"] == 24420
    assert d["financial_exposure"] == "2448105.00"
    assert d["is_shortage"] is True
    assert isinstance(d["calculation_hash"], str)
