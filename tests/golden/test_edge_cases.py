"""Canonical Golden Edge-Case Scenario Test Suite (P13-3).

Mandate:
- CLAUDE.md Section 14: Golden dataset tests and strict deterministic verification.
- BR-RULE-001 (The Triad of Responsibility): 100% deterministic Python arithmetic.
  Zero LLM math, zero floating-point drift, exact Decimal precision.
- Tests 5 boundary condition scenarios in tests/golden/edge_cases/:
  1. zero_stock.json: Stock = 0, coverage = 0.00 days, full ETA is shortage gap.
  2. zero_gap.json: JIT delivery, ETA == days of cover, gap = 0.00 days, exposure = $0.00.
  3. negative_gap.json: Healthy buffer, ETA < days of cover, raw gap < 0 clamped to 0.00.
  4. dual_approval_threshold.json: Exposure > $100,000.00 mandates Dual VP sign-off (2 tokens, 30 min).
  5. single_source_dependency.json: is_single_source = true, single-source risk flag, halt exposure.
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from src.core.hitl_tokens import SpendTier, get_spend_tier
from src.core.spend_tier_router import route_spend
from src.kafka.schemas.risk_alert import RiskLevel
from src.services.risk.calculator import RiskCalculator
from src.services.risk.scorer import RiskScorer

EDGE_CASES_DIR = Path(__file__).parent / "edge_cases"
GOLDEN_ROOT = Path(__file__).parent


def _load_edge_case_json(filename: str) -> dict[str, Any]:
    """Load and validate raw JSON structure from tests/golden/edge_cases/<filename>."""
    file_path = EDGE_CASES_DIR / filename
    assert file_path.exists(), f"Edge case file missing: {file_path}"
    with open(file_path, encoding="utf-8") as f:
        return cast(dict[str, Any], json.load(f))


# ------------------------------------------------------------------------------
# 1. Zero Stock Edge Case
# ------------------------------------------------------------------------------


def test_edge_case_zero_stock_golden_dataset() -> None:
    """Verify zero_stock.json: 0 inventory stock yields 0.00 cover and full ETA gap."""
    data = _load_edge_case_json("zero_stock.json")
    inputs = data["inputs"]
    expected = data["expected"]

    calc = RiskCalculator()
    scorer = RiskScorer()

    # 1. Deterministic Calculation
    result = calc.calculate_from_dict(inputs)

    assert result.days_of_cover == Decimal("0.00")
    assert result.days_of_cover == Decimal(str(expected["days_of_cover"]))

    assert result.gap_days == Decimal(str(expected["gap_days"]))
    assert result.gap_days == Decimal("5.00")

    assert result.shortage_volume == expected["shortage_volume"]
    assert result.shortage_volume == 5000

    assert result.financial_exposure == Decimal(str(expected["financial_exposure_usd"]))
    assert result.financial_exposure == Decimal("50000.00")
    assert result.is_shortage is True
    assert result.is_shortage == expected["is_shortage"]

    # 2. Risk Scoring & HITL Governance
    score_result = scorer.score_assessment(
        assessment=result,
        eta_days=Decimal(str(inputs["eta_days"])),
        supplier_risk_score=Decimal(str(inputs["supplier_risk_score"])),
        is_single_source=inputs["is_single_source"],
    )

    assert score_result.risk_level.value == expected["risk_level"]
    assert score_result.risk_level == RiskLevel.MEDIUM

    assert score_result.requires_hitl is True
    assert score_result.requires_hitl == expected["hitl_required"]

    assert score_result.recommended_hitl_tier is not None
    assert score_result.recommended_hitl_tier == SpendTier.PROC_DIRECTOR
    assert score_result.recommended_hitl_tier.value == expected["hitl_tier"]


# ------------------------------------------------------------------------------
# 2. Zero Gap (Just-In-Time) Edge Case
# ------------------------------------------------------------------------------


def test_edge_case_zero_gap_golden_dataset() -> None:
    """Verify zero_gap.json: JIT delivery ETA == days_of_cover yields gap=0, shortage=0, exposure=0."""
    data = _load_edge_case_json("zero_gap.json")
    inputs = data["inputs"]
    expected = data["expected"]

    calc = RiskCalculator()
    scorer = RiskScorer()

    result = calc.calculate_from_dict(inputs)

    assert result.days_of_cover == Decimal(str(expected["days_of_cover"]))
    assert result.days_of_cover == Decimal("10.00")

    assert result.gap_days == Decimal(str(expected["gap_days"]))
    assert result.gap_days == Decimal("0.00")

    assert result.shortage_volume == expected["shortage_volume"]
    assert result.shortage_volume == 0

    assert result.financial_exposure == Decimal(str(expected["financial_exposure_usd"]))
    assert result.financial_exposure == Decimal("0.00")
    assert result.is_shortage is False

    score_result = scorer.score_assessment(
        assessment=result,
        eta_days=Decimal(str(inputs["eta_days"])),
        supplier_risk_score=Decimal(str(inputs["supplier_risk_score"])),
        is_single_source=inputs["is_single_source"],
    )

    assert score_result.risk_level.value == expected["risk_level"]
    assert score_result.risk_level == RiskLevel.LOW
    assert score_result.requires_hitl is False
    assert score_result.requires_hitl == expected["hitl_required"]
    assert score_result.recommended_hitl_tier is None


# ------------------------------------------------------------------------------
# 3. Negative Gap (Healthy Buffer) Edge Case
# ------------------------------------------------------------------------------


def test_edge_case_negative_gap_golden_dataset() -> None:
    """Verify negative_gap.json: ETA < days_of_cover is strictly clamped to 0.00 gap."""
    data = _load_edge_case_json("negative_gap.json")
    inputs = data["inputs"]
    expected = data["expected"]

    calc = RiskCalculator()
    scorer = RiskScorer()

    result = calc.calculate_from_dict(inputs)

    assert result.days_of_cover == Decimal(str(expected["days_of_cover"]))
    assert result.days_of_cover == Decimal("20.00")

    # Clamping guarantee: raw diff is 5.0 - 20.0 = -15.0, clamped to 0.00
    assert result.gap_days == Decimal(str(expected["gap_days"]))
    assert result.gap_days == Decimal("0.00")

    assert result.shortage_volume == expected["shortage_volume"]
    assert result.shortage_volume == 0

    assert result.financial_exposure == Decimal(str(expected["financial_exposure_usd"]))
    assert result.financial_exposure == Decimal("0.00")
    assert result.is_shortage is False

    score_result = scorer.score_assessment(
        assessment=result,
        eta_days=Decimal(str(inputs["eta_days"])),
        supplier_risk_score=Decimal(str(inputs["supplier_risk_score"])),
        is_single_source=inputs["is_single_source"],
    )

    assert score_result.risk_level.value == expected["risk_level"]
    assert score_result.risk_level == RiskLevel.LOW
    assert score_result.requires_hitl is False
    assert score_result.requires_hitl == expected["hitl_required"]
    assert score_result.recommended_hitl_tier is None


# ------------------------------------------------------------------------------
# 4. Dual-Approval Threshold Boundary Edge Case
# ------------------------------------------------------------------------------


def test_edge_case_dual_approval_threshold_golden_dataset() -> None:
    """Verify dual_approval_threshold.json: Exposure > $100k triggers DUAL_VP (2 signatures, 30m TTL)."""
    data = _load_edge_case_json("dual_approval_threshold.json")
    inputs = data["inputs"]
    expected = data["expected"]

    calc = RiskCalculator()
    scorer = RiskScorer()

    result = calc.calculate_from_dict(inputs)

    assert result.days_of_cover == Decimal(str(expected["days_of_cover"]))
    assert result.days_of_cover == Decimal("10.00")

    assert result.gap_days == Decimal(str(expected["gap_days"]))
    assert result.gap_days == Decimal("1.00")

    assert result.shortage_volume == expected["shortage_volume"]
    assert result.shortage_volume == 2000

    # Exposure crossing: $100,050.00 > $100,000.00 threshold
    assert result.financial_exposure == Decimal(str(expected["financial_exposure_usd"]))
    assert result.financial_exposure == Decimal("100050.00")
    assert result.is_shortage is True

    # 1. Spend Tier Resolution
    tier = get_spend_tier(result.financial_exposure)
    assert tier == SpendTier.DUAL_VP

    # 2. Spend Tier Routing Policy
    route = route_spend(result.financial_exposure)
    assert route.tier == SpendTier.DUAL_VP
    assert route.required_signatures == expected["required_signatures"]
    assert route.required_signatures == 2
    assert route.requires_dual_approval is True
    assert route.token_ttl.total_seconds() == expected["token_ttl_seconds"]
    assert route.token_ttl.total_seconds() == 1800

    # Boundary comparison: exactly $100,000.00 must be single PROC_DIRECTOR
    boundary_route = route_spend(Decimal("100000.00"))
    assert boundary_route.tier == SpendTier.PROC_DIRECTOR
    assert boundary_route.required_signatures == 1
    assert boundary_route.token_ttl.total_seconds() == 3600

    # 3. Risk Scorer Evaluation
    score_result = scorer.score_assessment(
        assessment=result,
        eta_days=Decimal(str(inputs["eta_days"])),
        supplier_risk_score=Decimal(str(inputs["supplier_risk_score"])),
        is_single_source=inputs["is_single_source"],
    )

    assert score_result.risk_level.value == expected["risk_level"]
    assert score_result.requires_hitl is True
    assert score_result.recommended_hitl_tier is not None
    assert score_result.recommended_hitl_tier == SpendTier.DUAL_VP
    assert score_result.recommended_hitl_tier.value == expected["hitl_tier"]


# ------------------------------------------------------------------------------
# 5. Single-Source Dependency Edge Case
# ------------------------------------------------------------------------------


def test_edge_case_single_source_dependency_golden_dataset() -> None:
    """Verify single_source_dependency.json: Single-source flag, factory halt, and elevated severity."""
    data = _load_edge_case_json("single_source_dependency.json")
    inputs = data["inputs"]
    expected = data["expected"]

    calc = RiskCalculator()
    scorer = RiskScorer()

    result = calc.calculate_from_dict(inputs)

    assert result.days_of_cover == Decimal(str(expected["days_of_cover"]))
    assert result.days_of_cover == Decimal("5.00")

    assert result.gap_days == Decimal(str(expected["gap_days"]))
    assert result.gap_days == Decimal("2.00")

    assert result.shortage_volume == expected["shortage_volume"]
    assert result.shortage_volume == 6000

    assert result.financial_exposure == Decimal(str(expected["financial_exposure_usd"]))
    assert result.financial_exposure == Decimal("270000.00")

    # Factory halt impact (€50,000/hr * 48 hrs = €2,400,000.00)
    assert result.downtime_hours == Decimal(str(expected["downtime_hours"]))
    assert result.downtime_hours == Decimal("48.00")
    assert result.factory_halt_exposure == Decimal(str(expected["factory_halt_exposure_eur"]))
    assert result.factory_halt_exposure == Decimal("2400000.00")
    assert result.total_exposure == Decimal(str(expected["total_financial_impact_usd"]))
    assert result.total_exposure == Decimal("2670000.00")
    assert result.is_shortage is True

    # Risk Scoring
    score_result = scorer.score_assessment(
        assessment=result,
        eta_days=Decimal(str(inputs["eta_days"])),
        supplier_risk_score=Decimal(str(inputs["supplier_risk_score"])),
        is_single_source=inputs["is_single_source"],
    )

    assert score_result.risk_level.value == expected["risk_level"]
    assert score_result.risk_level == RiskLevel.HIGH
    assert score_result.is_single_source is True
    assert score_result.requires_hitl is True
    assert score_result.recommended_hitl_tier == SpendTier.DUAL_VP
    assert score_result.recommended_hitl_tier.value == expected["hitl_tier"]
    assert any("single-sourced" in r for r in score_result.reasons)


# ------------------------------------------------------------------------------
# 6. Schema Integrity Across All Golden Datasets
# ------------------------------------------------------------------------------


def test_all_golden_datasets_schema_integrity() -> None:
    """Verify that all JSON files in tests/golden/ adhere to mandatory schema structure."""
    all_json_files = [GOLDEN_ROOT / "nanocore_scenario.json"] + list(EDGE_CASES_DIR.glob("*.json"))
    assert len(all_json_files) == 6, f"Expected 6 golden JSON files, found {len(all_json_files)}"

    required_top_keys = {"scenario_id", "name", "description", "inputs", "expected"}
    required_input_keys = {
        "supplier_id",
        "supplier_name",
        "component_sku",
        "current_stock",
        "daily_consumption_rate",
        "eta_days",
        "unit_cost_usd",
    }
    required_expected_keys = {
        "days_of_cover",
        "gap_days",
        "shortage_volume",
        "financial_exposure_usd",
        "risk_level",
        "hitl_required",
        "is_shortage",
    }

    for json_file in all_json_files:
        with open(json_file, encoding="utf-8") as f:
            content = json.load(f)

        assert required_top_keys.issubset(content.keys()), (
            f"Missing top-level keys in {json_file.name}: {required_top_keys - content.keys()}"
        )
        assert required_input_keys.issubset(content["inputs"].keys()), (
            f"Missing input keys in {json_file.name}: {required_input_keys - content['inputs'].keys()}"
        )
        assert required_expected_keys.issubset(content["expected"].keys()), (
            f"Missing expected keys in {json_file.name}: {required_expected_keys - content['expected'].keys()}"
        )

        # Validate types
        assert isinstance(content["inputs"]["current_stock"], int)
        assert content["inputs"]["current_stock"] >= 0
        assert isinstance(content["inputs"]["daily_consumption_rate"], int)
        assert content["inputs"]["daily_consumption_rate"] >= 0
        assert isinstance(content["expected"]["shortage_volume"], int)
        assert content["expected"]["shortage_volume"] >= 0
        assert isinstance(content["expected"]["is_shortage"], bool)
        assert isinstance(content["expected"]["hitl_required"], bool)
        assert content["expected"]["risk_level"] in [
            "CRITICAL",
            "HIGH",
            "MEDIUM",
            "LOW",
        ]


# ------------------------------------------------------------------------------
# 7. Calculation Hash Reproducibility Across All Golden Datasets
# ------------------------------------------------------------------------------


def test_all_golden_datasets_calculation_hash_reproducibility() -> None:
    """Verify that every golden dataset generates a deterministic SHA-256 calculation hash."""
    calc = RiskCalculator()
    all_json_files = [GOLDEN_ROOT / "nanocore_scenario.json"] + list(EDGE_CASES_DIR.glob("*.json"))

    hashes: set[str] = set()

    for json_file in all_json_files:
        with open(json_file, encoding="utf-8") as f:
            content = json.load(f)

        r1 = calc.calculate_from_dict(content["inputs"])
        r2 = calc.calculate_from_dict(content["inputs"])

        assert len(r1.calculation_hash) == 64
        assert r1.calculation_hash == r2.calculation_hash
        assert r1.calculation_hash not in hashes, f"Hash collision detected for {json_file.name}"
        hashes.add(r1.calculation_hash)
