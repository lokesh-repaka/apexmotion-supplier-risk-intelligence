"""Unit tests for deterministic Risk Calculator (P14-1, P7-1).

Verifies:
- The Triad of Responsibility (BR-RULE-001): 100% deterministic pure Python math.
- All monetary and inventory metrics use Decimal precision with zero float truncation.
- Exact reproduction of the canonical NanoCore golden scenario:
  days_of_cover=7.68, gap_days=1.32, shortage_volume=24420, financial_exposure=$2,448,105.00.
- Mandatory edge cases:
  1. Zero stock (current_stock = 0, micro-stock, zero stock + zero consumption)
  2. Zero consumption guard (daily_consumption_rate = 0 -> days_of_cover = 999.00, warning logged)
  3. Negative gap (ETA < days of cover -> gap_days = 0.00, shortage = 0, exposure = 0.00)
  4. Exact zero gap (ETA == days of cover -> Just-In-Time)
  5. Zero unit cost (unit_cost_usd = 0.00 -> exposure = 0.00)
  6. Negative input validations (stock < 0, rate < 0, eta < 0, cost < 0, hours < 0, halt_rate < 0)
  7. NaN and Infinity injection defense (rejects float('nan'), Decimal('NaN'), etc.)
  8. ROUND_HALF_UP precision quantization tests for days, units, and currency
  9. Cross-validation against all 5 canonical edge-case golden scenarios in tests/golden/edge_cases/
  10. Cryptographic SHA-256 calculation verification hash reproducibility & avalanche effect
  11. Dataclass immutability (frozen instance guarantees)
- 100% statement and branch coverage on src/services/risk/calculator.py.
"""

import json
import logging
from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path

import pytest
from src.services.risk.calculator import (
    DAYS_OF_COVER_MAX_CAP,
    InvalidInventoryInputError,
    RiskAssessmentInput,
    RiskCalculator,
    _to_decimal,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GOLDEN_FILE = REPO_ROOT / "tests" / "golden" / "nanocore_scenario.json"
EDGE_CASES_DIR = REPO_ROOT / "tests" / "golden" / "edge_cases"


# ------------------------------------------------------------------------------
# 1. NanoCore Canonical Golden Scenario Tests
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


def test_nanocore_golden_param_types_flexibility() -> None:
    """Verify calculate_from_params accepts raw strings, floats, ints, or Decimals cleanly."""
    calc = RiskCalculator()

    # Pass string inputs
    result_str = calc.calculate_from_params(
        current_stock="142000",
        daily_consumption_rate="18500",
        eta_days="9.00",
        unit_cost_usd="100.25",
        factory_halt_cost_per_hour_eur="85000.00",
    )
    assert result_str.days_of_cover == Decimal("7.68")
    assert result_str.gap_days == Decimal("1.32")
    assert result_str.shortage_volume == 24420
    assert result_str.financial_exposure == Decimal("2448105.00")
    assert result_str.factory_halt_exposure == Decimal("2692800.00")
    assert result_str.total_exposure == Decimal("5140905.00")

    # Pass float inputs
    result_flt = calc.calculate_from_params(
        current_stock=142000,
        daily_consumption_rate=18500.0,
        eta_days=9.0,
        unit_cost_usd=100.25,
        factory_halt_cost_per_hour_eur=85000.0,
    )
    assert result_flt.days_of_cover == Decimal("7.68")
    assert result_flt.gap_days == Decimal("1.32")
    assert result_flt.shortage_volume == 24420
    assert result_flt.financial_exposure == Decimal("2448105.00")


def test_nanocore_golden_factory_halt_hourly_scaling() -> None:
    """Verify factory halt exposure scaling across varying operating shift configurations."""
    calc = RiskCalculator()

    # 8-hour shift
    res_8h = calc.calculate_from_params(
        current_stock=142000,
        daily_consumption_rate=18500,
        eta_days="9.00",
        unit_cost_usd="100.25",
        factory_halt_cost_per_hour_eur="85000.00",
        operating_hours_per_day="8.0",
    )
    # 1.32 * 8.0 = 10.56 hours -> 10.56 * 85000 = 897,600.00
    assert res_8h.downtime_hours == Decimal("10.56")
    assert res_8h.factory_halt_exposure == Decimal("897600.00")

    # 16-hour shift
    res_16h = calc.calculate_from_params(
        current_stock=142000,
        daily_consumption_rate=18500,
        eta_days="9.00",
        unit_cost_usd="100.25",
        factory_halt_cost_per_hour_eur="85000.00",
        operating_hours_per_day="16.0",
    )
    # 1.32 * 16.0 = 21.12 hours -> 21.12 * 85000 = 1,795,200.00
    assert res_16h.downtime_hours == Decimal("21.12")
    assert res_16h.factory_halt_exposure == Decimal("1795200.00")


# ------------------------------------------------------------------------------
# 2. Edge Case 1: Zero Stock & Micro-Inventory
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


def test_edge_case_zero_stock_and_zero_consumption() -> None:
    """Verify boundary condition where current_stock = 0 and consumption_rate = 0."""
    calc = RiskCalculator()
    result = calc.calculate_from_params(
        current_stock=0,
        daily_consumption_rate=0,
        eta_days=Decimal("5.00"),
        unit_cost_usd=Decimal("10.00"),
    )
    # When consumption is 0, days of cover is capped at 999.00
    assert result.days_of_cover == DAYS_OF_COVER_MAX_CAP
    assert result.gap_days == Decimal("0.00")
    assert result.shortage_volume == 0
    assert result.financial_exposure == Decimal("0.00")
    assert result.is_shortage is False


def test_edge_case_micro_stock_rounds_to_zero_cover() -> None:
    """Verify micro-inventory (1 unit) with high consumption rounds cover to 0.00 days."""
    calc = RiskCalculator()
    # 1 / 18500 = 0.000054... -> quantizes to 0.00
    doc = calc.calculate_days_of_cover(current_stock=1, daily_consumption_rate=18500)
    assert doc == Decimal("0.00")

    result = calc.calculate_from_params(
        current_stock=1,
        daily_consumption_rate=18500,
        eta_days=Decimal("5.00"),
        unit_cost_usd=Decimal("10.00"),
    )
    assert result.days_of_cover == Decimal("0.00")
    assert result.gap_days == Decimal("5.00")
    assert result.shortage_volume == 92500
    assert result.financial_exposure == Decimal("925000.00")
    assert result.is_shortage is True


def test_edge_case_zero_stock_zero_eta() -> None:
    """Verify zero stock with immediate ETA (0.00 days) results in zero gap."""
    calc = RiskCalculator()
    result = calc.calculate_from_params(
        current_stock=0,
        daily_consumption_rate=1000,
        eta_days=Decimal("0.00"),
        unit_cost_usd=Decimal("10.00"),
    )
    assert result.days_of_cover == Decimal("0.00")
    assert result.gap_days == Decimal("0.00")
    assert result.shortage_volume == 0
    assert result.financial_exposure == Decimal("0.00")
    assert result.is_shortage is False


# ------------------------------------------------------------------------------
# 3. Edge Case 2: Zero Consumption Rate & Capping
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


def test_edge_case_zero_consumption_warning_logged(caplog: pytest.LogCaptureFixture) -> None:
    """Verify that a warning log is emitted when zero consumption rate is encountered."""
    calc = RiskCalculator()
    with caplog.at_level(logging.WARNING):
        doc = calc.calculate_days_of_cover(current_stock=10000, daily_consumption_rate=0)

    assert doc == Decimal("999.00")
    assert "Zero consumption rate detected; capping days of cover at 999.00" in caplog.text


def test_edge_case_zero_consumption_with_massive_eta() -> None:
    """Verify that even with an ETA exceeding the 999-day cap, zero rate yields zero shortage."""
    calc = RiskCalculator()
    result = calc.calculate_from_params(
        current_stock=50000,
        daily_consumption_rate=0,
        eta_days=Decimal("1500.00"),
        unit_cost_usd=Decimal("25.00"),
    )
    # Gap calculation is max(0, 1500.00 - 999.00) = 501.00
    # But shortage_volume with rate=0 is strictly 0!
    assert result.shortage_volume == 0
    assert result.financial_exposure == Decimal("0.00")


# ------------------------------------------------------------------------------
# 4. Edge Case 3: Negative Gap & Inventory Buffer Clamping
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


def test_edge_case_negative_gap_sub_day_clamping() -> None:
    """Verify that small sub-day negative differences (e.g. -0.01) are clamped to 0.00."""
    calc = RiskCalculator()
    gap = calc.calculate_gap_days(eta_days=Decimal("9.99"), days_of_cover=Decimal("10.00"))
    assert gap == Decimal("0.00")

    vol = calc.calculate_shortage_volume(gap_days=gap, daily_consumption_rate=10000)
    assert vol == 0

    exp = calc.calculate_financial_exposure(shortage_volume=vol, unit_cost_usd=Decimal("50.00"))
    assert exp == Decimal("0.00")


def test_edge_case_negative_gap_extreme_buffer() -> None:
    """Verify that multi-month inventory buffer strictly clamps gap and financial impact."""
    calc = RiskCalculator()
    result = calc.calculate_from_params(
        current_stock=500000,
        daily_consumption_rate=5000,  # 100 days cover
        eta_days=Decimal("2.00"),  # arrival in 2 days (98-day buffer)
        unit_cost_usd=Decimal("120.00"),
        factory_halt_cost_per_hour_eur=Decimal("85000.00"),
    )
    assert result.days_of_cover == Decimal("100.00")
    assert result.gap_days == Decimal("0.00")
    assert result.shortage_volume == 0
    assert result.financial_exposure == Decimal("0.00")
    assert result.downtime_hours == Decimal("0.00")
    assert result.factory_halt_exposure == Decimal("0.00")
    assert result.total_exposure == Decimal("0.00")
    assert result.is_shortage is False


# ------------------------------------------------------------------------------
# 5. Edge Case 4 & 5: Exact Zero Gap & Zero Unit Cost
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
# 6. Precision & Halfway Rounding (ROUND_HALF_UP)
# ------------------------------------------------------------------------------


def test_days_of_cover_halfway_rounding() -> None:
    """Verify ROUND_HALF_UP behavior for days of cover at .005 and .004 thresholds."""
    calc = RiskCalculator()
    # 1 / 200 = 0.005 -> rounds up to 0.01
    assert calc.calculate_days_of_cover(1, 200) == Decimal("0.01")

    # 1 / 250 = 0.004 -> rounds down to 0.00
    assert calc.calculate_days_of_cover(1, 250) == Decimal("0.00")

    # 3 / 200 = 0.015 -> rounds up to 0.02
    assert calc.calculate_days_of_cover(3, 200) == Decimal("0.02")

    # 5 / 200 = 0.025 -> rounds up to 0.03
    assert calc.calculate_days_of_cover(5, 200) == Decimal("0.03")

    # 7 / 200 = 0.035 -> rounds up to 0.04
    assert calc.calculate_days_of_cover(7, 200) == Decimal("0.04")


def test_gap_days_precision_quantization() -> None:
    """Verify ROUND_HALF_UP quantization on coverage gap days."""
    calc = RiskCalculator()
    # 10.005 - 5.000 = 5.005 -> rounds up to 5.01
    assert calc.calculate_gap_days(Decimal("10.005"), Decimal("5.000")) == Decimal("5.01")

    # 10.004 - 5.000 = 5.004 -> rounds down to 5.00
    assert calc.calculate_gap_days(Decimal("10.004"), Decimal("5.000")) == Decimal("5.00")


def test_shortage_volume_halfway_rounding() -> None:
    """Verify integer rounding of component shortage volume."""
    calc = RiskCalculator()
    # 1.5 * 3 = 4.5 -> rounds up to 5 units
    assert calc.calculate_shortage_volume(Decimal("1.5"), Decimal("3")) == 5

    # 1.4 * 3 = 4.2 -> rounds down to 4 units
    assert calc.calculate_shortage_volume(Decimal("1.4"), Decimal("3")) == 4


def test_financial_exposure_halfway_rounding() -> None:
    """Verify exact 2-decimal currency quantization with ROUND_HALF_UP."""
    calc = RiskCalculator()
    # 1 unit * 10.005 = 10.005 -> $10.01
    assert calc.calculate_financial_exposure(1, Decimal("10.005")) == Decimal("10.01")

    # 1 unit * 10.004 = 10.004 -> $10.00
    assert calc.calculate_financial_exposure(1, Decimal("10.004")) == Decimal("10.00")

    # 3 units * 10.005 = 30.015 -> $30.02
    assert calc.calculate_financial_exposure(3, Decimal("10.005")) == Decimal("30.02")


# ------------------------------------------------------------------------------
# 7. Defensive Validation & Fuzzing
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


def test_validation_rejects_negative_operating_hours() -> None:
    """Assert InvalidInventoryInputError on negative operating hours per day."""
    calc = RiskCalculator()
    with pytest.raises(
        InvalidInventoryInputError, match="Operating hours per day cannot be negative"
    ):
        calc.calculate_from_params(
            current_stock=1000,
            daily_consumption_rate=100,
            eta_days="5.0",
            unit_cost_usd="10.0",
            operating_hours_per_day="-8.0",
        )

    with pytest.raises(
        InvalidInventoryInputError, match="Operating hours per day cannot be negative"
    ):
        RiskCalculator.calculate_downtime_exposure(
            gap_days=Decimal("1.00"),
            operating_hours_per_day=Decimal("-8.0"),
        )


def test_validation_rejects_negative_halt_rate() -> None:
    """Assert InvalidInventoryInputError on negative factory halt cost."""
    calc = RiskCalculator()
    with pytest.raises(InvalidInventoryInputError, match="Hourly halt rate cannot be negative"):
        calc.calculate_from_params(
            current_stock=1000,
            daily_consumption_rate=100,
            eta_days="5.0",
            unit_cost_usd="10.0",
            factory_halt_cost_per_hour_eur="-50000.0",
        )

    with pytest.raises(InvalidInventoryInputError, match="Hourly halt rate cannot be negative"):
        RiskCalculator.calculate_downtime_exposure(
            gap_days=Decimal("1.00"),
            hourly_rate=Decimal("-50000.00"),
        )


def test_validation_rejects_nan_and_infinity() -> None:
    """Assert InvalidInventoryInputError on NaN or Infinite float and Decimal inputs."""
    calc = RiskCalculator()

    # float NaN
    with pytest.raises(InvalidInventoryInputError, match="cannot be NaN or Infinite"):
        calc.calculate_from_params(
            current_stock=1000,
            daily_consumption_rate=100,
            eta_days=float("nan"),
            unit_cost_usd=10.0,
        )

    # float Infinity
    with pytest.raises(InvalidInventoryInputError, match="cannot be NaN or Infinite"):
        calc.calculate_from_params(
            current_stock=1000,
            daily_consumption_rate=100,
            eta_days=float("inf"),
            unit_cost_usd=10.0,
        )

    # Decimal NaN
    with pytest.raises(InvalidInventoryInputError, match="cannot be NaN or Infinite"):
        calc.calculate_from_params(
            current_stock=1000,
            daily_consumption_rate=100,
            eta_days=Decimal("NaN"),
            unit_cost_usd=10.0,
        )


def test_validation_rejects_invalid_type_coercion() -> None:
    """Assert InvalidInventoryInputError on invalid non-numeric string values and None."""
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


def test_dataclass_frozen_immutability() -> None:
    """Verify that RiskAssessmentInput and RiskAssessmentResult are strictly immutable."""
    input_data = RiskAssessmentInput(
        current_stock=100,
        daily_consumption_rate=10,
        eta_days=Decimal("5.00"),
        unit_cost_usd=Decimal("10.00"),
    )
    with pytest.raises(FrozenInstanceError):
        # type ignore because we are intentionally testing runtime mutation error
        input_data.current_stock = 200  # type: ignore[misc]

    calc = RiskCalculator()
    result = calc.calculate(input_data)
    with pytest.raises(FrozenInstanceError):
        result.days_of_cover = Decimal("50.00")  # type: ignore[misc]


# ------------------------------------------------------------------------------
# 8. Cross-Validation with All 5 Canonical Edge-Case Golden Scenarios
# ------------------------------------------------------------------------------


def test_cross_validation_zero_stock_golden_dataset() -> None:
    """Cross-verify calculate_from_dict against tests/golden/edge_cases/zero_stock.json."""
    path = EDGE_CASES_DIR / "zero_stock.json"
    assert path.exists(), f"Edge case file not found: {path}"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    calc = RiskCalculator()
    res = calc.calculate_from_dict(data["inputs"])

    assert res.days_of_cover == Decimal("0.00")
    assert res.gap_days == Decimal("5.00")
    assert res.shortage_volume == 5000
    assert res.financial_exposure == Decimal("50000.00")
    assert res.is_shortage is True


def test_cross_validation_zero_gap_golden_dataset() -> None:
    """Cross-verify calculate_from_dict against tests/golden/edge_cases/zero_gap.json."""
    path = EDGE_CASES_DIR / "zero_gap.json"
    assert path.exists(), f"Edge case file not found: {path}"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    calc = RiskCalculator()
    res = calc.calculate_from_dict(data["inputs"])

    assert res.days_of_cover == Decimal("10.00")
    assert res.gap_days == Decimal("0.00")
    assert res.shortage_volume == 0
    assert res.financial_exposure == Decimal("0.00")
    assert res.is_shortage is False


def test_cross_validation_negative_gap_golden_dataset() -> None:
    """Cross-verify calculate_from_dict against tests/golden/edge_cases/negative_gap.json."""
    path = EDGE_CASES_DIR / "negative_gap.json"
    assert path.exists(), f"Edge case file not found: {path}"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    calc = RiskCalculator()
    res = calc.calculate_from_dict(data["inputs"])

    assert res.days_of_cover == Decimal("20.00")
    assert res.gap_days == Decimal("0.00")
    assert res.shortage_volume == 0
    assert res.financial_exposure == Decimal("0.00")
    assert res.is_shortage is False


def test_cross_validation_dual_approval_threshold_golden_dataset() -> None:
    """Cross-verify calculate_from_dict against tests/golden/edge_cases/dual_approval_threshold.json."""
    path = EDGE_CASES_DIR / "dual_approval_threshold.json"
    assert path.exists(), f"Edge case file not found: {path}"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    calc = RiskCalculator()
    res = calc.calculate_from_dict(data["inputs"])

    assert res.days_of_cover == Decimal("10.00")
    assert res.gap_days == Decimal("1.00")
    assert res.shortage_volume == 2000
    assert res.financial_exposure == Decimal("100050.00")
    assert res.is_shortage is True


def test_cross_validation_single_source_dependency_golden_dataset() -> None:
    """Cross-verify calculate_from_dict against tests/golden/edge_cases/single_source_dependency.json."""
    path = EDGE_CASES_DIR / "single_source_dependency.json"
    assert path.exists(), f"Edge case file not found: {path}"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    calc = RiskCalculator()
    res = calc.calculate_from_dict(data["inputs"])

    assert res.days_of_cover == Decimal("5.00")
    assert res.gap_days == Decimal("2.00")
    assert res.shortage_volume == 6000
    assert res.financial_exposure == Decimal("270000.00")
    assert res.downtime_hours == Decimal("48.00")
    assert res.factory_halt_exposure == Decimal("2400000.00")
    assert res.total_exposure == Decimal("2670000.00")
    assert res.is_shortage is True


# ------------------------------------------------------------------------------
# 9. Factory Line Halt & Downtime Exposure
# ------------------------------------------------------------------------------


def test_downtime_exposure_zero_when_gap_is_non_positive() -> None:
    """Assert calculate_downtime_exposure returns 0.00 when gap is 0 or negative."""
    assert RiskCalculator.calculate_downtime_exposure(gap_days=Decimal("0.00")) == Decimal("0.00")
    assert RiskCalculator.calculate_downtime_exposure(gap_days=Decimal("-2.00")) == Decimal("0.00")


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
# 10. Helper Static Functions, Hash Determinism & Avalanche Effect
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


def test_calculation_hash_avalanche_effect() -> None:
    """Verify cryptographic avalanche effect: minimal 1-cent/1-unit shift changes >25 hex chars."""
    calc = RiskCalculator()
    base = RiskAssessmentInput(
        current_stock=142000,
        daily_consumption_rate=18500,
        eta_days=Decimal("9.00"),
        unit_cost_usd=Decimal("100.25"),
    )
    mod = RiskAssessmentInput(
        current_stock=142000,
        daily_consumption_rate=18500,
        eta_days=Decimal("9.00"),
        unit_cost_usd=Decimal("100.26"),  # 1-cent perturbation
    )

    h_base = calc.calculate(base).calculation_hash
    h_mod = calc.calculate(mod).calculation_hash

    differing_chars = sum(1 for c1, c2 in zip(h_base, h_mod, strict=True) if c1 != c2)
    # In a 64-char SHA-256 hash, an avalanche should change roughly 50% of hex chars (>= 25)
    assert differing_chars >= 25, f"Expected avalanche effect, got only {differing_chars} diffs"


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
