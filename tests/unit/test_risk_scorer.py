"""Unit tests for deterministic Risk Scorer (P7-2).

Verifies:
- The Triad of Responsibility (BR-RULE-001): 100% deterministic pure Python risk classification.
- Threshold boundaries for CRITICAL, HIGH, MEDIUM, LOW severity levels:
  * CRITICAL: gap > 0 AND financial_exposure > $1,000,000.00
  * HIGH: gap > 0 AND $250,000.00 < financial_exposure <= $1,000,000.00
  * MEDIUM: gap > 0 (exposure <= $250,000.00) OR supplier_risk_score > 0.70
  * LOW: gap <= 0 AND supplier_risk_score <= 0.70
- Exact NanoCore golden scenario evaluation (gap=1.32, exposure=$2,448,105.00 -> CRITICAL).
- HITL governance routing and tier assignment (CATEGORY_MGR, PROC_DIRECTOR, DUAL_VP).
- Integration with RiskCalculator and RiskAssessmentResult.
- Input validation and exception trapping for negative or malformed values.
- 100% statement and branch coverage on src/services/risk/scorer.py.
"""

from decimal import Decimal

import pytest
from src.core.hitl_tokens import SpendTier
from src.kafka.schemas.risk_alert import RiskLevel
from src.services.risk.calculator import (
    RiskAssessmentInput,
    RiskCalculator,
)
from src.services.risk.scorer import (
    InvalidRiskScoringInputError,
    RiskScorer,
    compute_risk_level,
)

# ------------------------------------------------------------------------------
# NanoCore Canonical Golden Scenario
# ------------------------------------------------------------------------------


def test_nanocore_golden_scenario_scoring() -> None:
    """Verify that the canonical NanoCore scenario assigns RiskLevel.CRITICAL and requires DUAL_VP HITL.

    NanoCore reference inputs:
    - days_of_cover: 7.68 days
    - eta_days: 9.00 days (gap: 1.32 days)
    - financial_exposure: $2,448,105.00
    - supplier_risk_score: 0.885
    """
    level = compute_risk_level(
        days_of_cover=Decimal("7.68"),
        eta_days=Decimal("9.00"),
        financial_exposure=Decimal("2448105.00"),
        supplier_risk_score=Decimal("0.885"),
    )
    assert level == RiskLevel.CRITICAL

    scorer = RiskScorer()
    result = scorer.score(
        days_of_cover=Decimal("7.68"),
        eta_days=Decimal("9.00"),
        financial_exposure=Decimal("2448105.00"),
        supplier_risk_score=Decimal("0.885"),
        is_single_source=True,
    )

    assert result.risk_level == RiskLevel.CRITICAL
    assert result.gap_days == Decimal("1.32")
    assert result.requires_hitl is True
    assert result.recommended_hitl_tier == SpendTier.DUAL_VP
    assert result.is_single_source is True
    assert any("exceeds CRITICAL threshold" in r for r in result.reasons)


# ------------------------------------------------------------------------------
# Threshold Boundary Tests: CRITICAL
# ------------------------------------------------------------------------------


def test_scoring_critical_threshold_boundary() -> None:
    """Verify CRITICAL requires strictly gap > 0 and exposure > $1,000,000.00."""
    # Just above threshold ($1,000,000.01) -> CRITICAL
    assert (
        compute_risk_level(
            days_of_cover=Decimal("5.00"),
            eta_days=Decimal("6.00"),
            financial_exposure=Decimal("1000000.01"),
        )
        == RiskLevel.CRITICAL
    )

    # Exactly at threshold ($1,000,000.00) -> HIGH (strictly > $1M required for CRITICAL)
    assert (
        compute_risk_level(
            days_of_cover=Decimal("5.00"),
            eta_days=Decimal("6.00"),
            financial_exposure=Decimal("1000000.00"),
        )
        == RiskLevel.HIGH
    )

    # Exposure > $1M but gap <= 0 (healthy buffer) -> NOT critical
    assert (
        compute_risk_level(
            days_of_cover=Decimal("10.00"),
            eta_days=Decimal("5.00"),
            financial_exposure=Decimal("5000000.00"),
            supplier_risk_score=Decimal("0.20"),
        )
        == RiskLevel.LOW
    )


# ------------------------------------------------------------------------------
# Threshold Boundary Tests: HIGH
# ------------------------------------------------------------------------------


def test_scoring_high_threshold_boundary() -> None:
    """Verify HIGH requires gap > 0 and exposure > $250,000.00 (up to $1,000,000.00)."""
    # Just above lower boundary ($250,000.01) -> HIGH
    assert (
        compute_risk_level(
            days_of_cover=Decimal("4.00"),
            eta_days=Decimal("5.00"),
            financial_exposure=Decimal("250000.01"),
        )
        == RiskLevel.HIGH
    )

    # Exactly at boundary ($250,000.00) -> MEDIUM (strictly > $250k required for HIGH)
    assert (
        compute_risk_level(
            days_of_cover=Decimal("4.00"),
            eta_days=Decimal("5.00"),
            financial_exposure=Decimal("250000.00"),
        )
        == RiskLevel.MEDIUM
    )

    # Middle of HIGH range ($500,000.00) -> HIGH
    assert (
        compute_risk_level(
            days_of_cover=Decimal("4.00"),
            eta_days=Decimal("5.00"),
            financial_exposure=Decimal("500000.00"),
        )
        == RiskLevel.HIGH
    )


# ------------------------------------------------------------------------------
# Threshold Boundary Tests: MEDIUM
# ------------------------------------------------------------------------------


def test_scoring_medium_threshold_boundary() -> None:
    """Verify MEDIUM assigned when gap > 0 (exposure <= $250k) OR supplier_risk_score > 0.70."""
    # Gap > 0 with low financial exposure ($1,000.00) -> MEDIUM
    assert (
        compute_risk_level(
            days_of_cover=Decimal("7.00"),
            eta_days=Decimal("8.00"),
            financial_exposure=Decimal("1000.00"),
            supplier_risk_score=Decimal("0.10"),
        )
        == RiskLevel.MEDIUM
    )

    # Gap == 0 (no shortage), but supplier_risk_score > 0.70 (0.701) -> MEDIUM
    assert (
        compute_risk_level(
            days_of_cover=Decimal("10.00"),
            eta_days=Decimal("10.00"),
            financial_exposure=Decimal("0.00"),
            supplier_risk_score=Decimal("0.701"),
        )
        == RiskLevel.MEDIUM
    )

    # Gap == 0 and supplier_risk_score exactly 0.700 -> LOW (strictly > 0.70 required)
    assert (
        compute_risk_level(
            days_of_cover=Decimal("10.00"),
            eta_days=Decimal("10.00"),
            financial_exposure=Decimal("0.00"),
            supplier_risk_score=Decimal("0.700"),
        )
        == RiskLevel.LOW
    )


# ------------------------------------------------------------------------------
# Threshold Boundary Tests: LOW
# ------------------------------------------------------------------------------


def test_scoring_low_threshold_boundary() -> None:
    """Verify LOW assigned when gap <= 0 and supplier_risk_score <= 0.70."""
    # Zero gap, zero exposure, zero risk score -> LOW
    assert (
        compute_risk_level(
            days_of_cover=Decimal("12.00"),
            eta_days=Decimal("8.00"),
            financial_exposure=Decimal("0.00"),
            supplier_risk_score=Decimal("0.00"),
        )
        == RiskLevel.LOW
    )

    # Negative gap (cover 20, ETA 5), supplier_risk_score = 0.50 -> LOW
    assert (
        compute_risk_level(
            days_of_cover=Decimal("20.00"),
            eta_days=Decimal("5.00"),
            financial_exposure=Decimal("0.00"),
            supplier_risk_score=Decimal("0.50"),
        )
        == RiskLevel.LOW
    )


# ------------------------------------------------------------------------------
# Integration with RiskCalculator
# ------------------------------------------------------------------------------


def test_scorer_integration_with_risk_calculator() -> None:
    """Verify end-to-end integration: RiskCalculator output fed directly into RiskScorer."""
    calc = RiskCalculator()
    scorer = RiskScorer()

    # Scenario: High risk component disruption
    calc_input = RiskAssessmentInput(
        current_stock=50000,
        daily_consumption_rate=5000,
        eta_days=Decimal("12.00"),  # cover = 10.00, gap = 2.00
        unit_cost_usd=Decimal("50.00"),  # shortage = 10,000, exposure = $500,000.00
    )
    assessment = calc.calculate(calc_input)
    assert assessment.gap_days == Decimal("2.00")
    assert assessment.financial_exposure == Decimal("500000.00")

    score_result = scorer.score_assessment(
        assessment=assessment,
        eta_days=Decimal("12.00"),
        supplier_risk_score=Decimal("0.65"),
    )

    assert score_result.risk_level == RiskLevel.HIGH
    assert score_result.financial_exposure == Decimal("500000.00")
    assert score_result.requires_hitl is True
    assert score_result.recommended_hitl_tier == SpendTier.DUAL_VP  # > $100k requires dual VP


# ------------------------------------------------------------------------------
# HITL Governance Routing
# ------------------------------------------------------------------------------


def test_hitl_governance_tiers() -> None:
    """Verify proper HITL spend tier derivation across spend boundaries."""
    scorer = RiskScorer()

    # Tier 1: Spend <= $25,000 -> CATEGORY_MGR
    r1 = scorer.score(
        days_of_cover=Decimal("5.00"),
        eta_days=Decimal("6.00"),
        financial_exposure=Decimal("25000.00"),
    )
    assert r1.risk_level == RiskLevel.MEDIUM
    assert r1.requires_hitl is True
    assert r1.recommended_hitl_tier == SpendTier.CATEGORY_MGR

    # Tier 2: Spend $25,001 - $100,000 -> PROC_DIRECTOR
    r2 = scorer.score(
        days_of_cover=Decimal("5.00"),
        eta_days=Decimal("6.00"),
        financial_exposure=Decimal("75000.00"),
    )
    assert r2.risk_level == RiskLevel.MEDIUM
    assert r2.requires_hitl is True
    assert r2.recommended_hitl_tier == SpendTier.PROC_DIRECTOR

    # Tier 3: Spend > $100,000 -> DUAL_VP
    r3 = scorer.score(
        days_of_cover=Decimal("5.00"),
        eta_days=Decimal("6.00"),
        financial_exposure=Decimal("150000.00"),
    )
    assert r3.risk_level == RiskLevel.MEDIUM
    assert r3.requires_hitl is True
    assert r3.recommended_hitl_tier == SpendTier.DUAL_VP

    # Zero spend and LOW risk -> No HITL required
    r0 = scorer.score(
        days_of_cover=Decimal("10.00"),
        eta_days=Decimal("5.00"),
        financial_exposure=Decimal("0.00"),
    )
    assert r0.risk_level == RiskLevel.LOW
    assert r0.requires_hitl is False
    assert r0.recommended_hitl_tier is None


# ------------------------------------------------------------------------------
# Input Validation & Error Handling
# ------------------------------------------------------------------------------


def test_validation_rejects_negative_parameters() -> None:
    """Verify InvalidRiskScoringInputError on negative values."""
    scorer = RiskScorer()

    with pytest.raises(InvalidRiskScoringInputError, match="Days of cover cannot be negative"):
        scorer.score(days_of_cover=-1, eta_days=5, financial_exposure=1000)

    with pytest.raises(InvalidRiskScoringInputError, match="ETA days cannot be negative"):
        scorer.score(days_of_cover=5, eta_days=-1, financial_exposure=1000)

    with pytest.raises(InvalidRiskScoringInputError, match="Financial exposure cannot be negative"):
        scorer.score(days_of_cover=5, eta_days=5, financial_exposure=-100)

    with pytest.raises(
        InvalidRiskScoringInputError, match="Supplier risk score must be between 0.0 and 1.0"
    ):
        scorer.score(days_of_cover=5, eta_days=5, financial_exposure=1000, supplier_risk_score=1.5)

    with pytest.raises(
        InvalidRiskScoringInputError, match="Supplier risk score must be between 0.0 and 1.0"
    ):
        scorer.score(days_of_cover=5, eta_days=5, financial_exposure=1000, supplier_risk_score=-0.1)


def test_validation_rejects_invalid_type_coercion() -> None:
    """Verify InvalidRiskScoringInputError on non-numeric or None parameters."""
    scorer = RiskScorer()

    with pytest.raises(InvalidRiskScoringInputError, match="Field 'days_of_cover' cannot be None"):
        scorer.score(days_of_cover=None, eta_days=5, financial_exposure=1000)  # type: ignore[arg-type]

    with pytest.raises(InvalidRiskScoringInputError, match="Failed to parse Decimal"):
        scorer.score(days_of_cover="invalid", eta_days=5, financial_exposure=1000)


# ------------------------------------------------------------------------------
# Helper & Dictionary APIs
# ------------------------------------------------------------------------------


def test_score_from_dict_and_serialization() -> None:
    """Verify dictionary parsing and serialization of RiskScoreResult."""
    scorer = RiskScorer()
    payload = {
        "days_of_cover": "7.68",
        "eta_days": "9.00",
        "financial_exposure": "2448105.00",
        "supplier_risk_score": "0.885",
        "is_single_source": True,
    }

    result = scorer.score_from_dict(payload)
    assert result.risk_level == RiskLevel.CRITICAL
    assert result.is_single_source is True

    d = result.to_dict()
    assert d["risk_level"] == "CRITICAL"
    assert d["days_of_cover"] == "7.68"
    assert d["gap_days"] == "1.32"
    assert d["financial_exposure"] == "2448105.00"
    assert d["requires_hitl"] is True
    assert d["recommended_hitl_tier"] == "DUAL_VP"
    assert d["is_single_source"] is True
    assert isinstance(d["reasons"], list)


def test_score_assessment_default_eta_derivation() -> None:
    """Verify score_assessment computes eta_days from cover + gap when omitted."""
    calc = RiskCalculator()
    scorer = RiskScorer()
    calc_input = RiskAssessmentInput(
        current_stock=20000,
        daily_consumption_rate=2000,
        eta_days=Decimal("15.00"),  # cover = 10.00, gap = 5.00
        unit_cost_usd=Decimal("10.00"),
    )
    assessment = calc.calculate(calc_input)
    score_result = scorer.score_assessment(assessment=assessment)
    assert score_result.days_of_cover == Decimal("10.00")
    assert score_result.gap_days == Decimal("5.00")
    assert score_result.risk_level == RiskLevel.MEDIUM


def test_scoring_medium_supplier_risk_reason() -> None:
    """Verify supplier risk score above threshold populates explanatory reason."""
    scorer = RiskScorer()
    result = scorer.score(
        days_of_cover=Decimal("10.00"),
        eta_days=Decimal("10.00"),
        financial_exposure=Decimal("0.00"),
        supplier_risk_score=Decimal("0.850"),
    )
    assert result.risk_level == RiskLevel.MEDIUM
    assert any("Supplier risk score" in r for r in result.reasons)


def test_validation_rejects_negative_gap_days() -> None:
    """Verify InvalidRiskScoringInputError when explicit gap_days is negative."""
    scorer = RiskScorer()
    with pytest.raises(InvalidRiskScoringInputError, match="Gap days cannot be negative"):
        scorer.score(
            days_of_cover=Decimal("5.00"),
            eta_days=Decimal("5.00"),
            financial_exposure=Decimal("0.00"),
            gap_days=Decimal("-1.00"),
        )


def test_evaluate_hitl_requirement_critical_zero_exposure() -> None:
    """Verify critical severity with zero monetary exposure still flags HITL category manager."""
    req, tier = RiskScorer.evaluate_hitl_requirement(
        risk_level=RiskLevel.CRITICAL,
        financial_exposure=Decimal("0.00"),
    )
    assert req is True
    assert tier == SpendTier.CATEGORY_MGR
