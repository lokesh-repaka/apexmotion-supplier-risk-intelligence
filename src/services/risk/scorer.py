"""Deterministic supply chain risk scorer and severity classifier (P7-2).

Enforces:
- The Triad of Responsibility (BR-RULE-001): 100% deterministic pure Python classification.
  LLMs and AI agents are strictly forbidden from performing mathematical calculations or threshold evaluations.
- Strict Decimal precision: all threshold comparisons use Python Decimal.
  Zero floating-point drift or IEEE 754 truncation.
- Core severity threshold rules (CLAUDE.md:428-439):
  1. CRITICAL: gap > 0 AND financial_exposure > $1,000,000.00
  2. HIGH: gap > 0 AND financial_exposure > $250,000.00 (up to $1,000,000.00)
  3. MEDIUM: gap > 0 (exposure <= $250,000.00) OR supplier_risk_score > 0.70
  4. LOW: gap <= 0 AND supplier_risk_score <= 0.70
- HITL Governance Integration:
  - Spend <= $25,000: Category Manager approval (SpendTier.CATEGORY_MGR, 1-hr TTL)
  - Spend $25,001 - $100,000: Procurement Director approval (SpendTier.PROC_DIRECTOR, 1-hr TTL)
  - Spend > $100,000: Dual sign-off (SpendTier.DUAL_VP, 30-min TTL)
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from src.api.exceptions import AppException
from src.core.hitl_tokens import SpendTier, get_spend_tier
from src.core.logging import get_logger
from src.kafka.schemas.risk_alert import RiskLevel
from src.services.risk.calculator import (
    PRECISION_CURRENCY,
    PRECISION_DAYS,
    RiskAssessmentResult,
)

logger = get_logger("apexmotion.services.risk.scorer")

# Severity threshold boundaries (CLAUDE.md Section 3 & BR-RULE-001)
THRESHOLD_EXPOSURE_CRITICAL = Decimal("1000000.00")
THRESHOLD_EXPOSURE_HIGH = Decimal("250000.00")
THRESHOLD_SUPPLIER_RISK_MEDIUM = Decimal("0.70")


class InvalidRiskScoringInputError(AppException):
    """Raised when risk scoring inputs violate numerical or domain constraints."""

    def __init__(self, message: str, details: Any = None) -> None:
        super().__init__(
            code="INVALID_RISK_SCORING_INPUT",
            message=message,
            status_code=400,
            details=details,
        )


def _to_decimal(val: Any, field_name: str) -> Decimal:
    """Safely coerce int, float, str, or Decimal into Decimal with validation."""
    if val is None:
        raise InvalidRiskScoringInputError(f"Field '{field_name}' cannot be None")
    if isinstance(val, Decimal):
        return val
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise InvalidRiskScoringInputError(
            f"Failed to parse Decimal for field '{field_name}': {val}"
        ) from exc


def _validate_inputs(
    days_of_cover: Decimal,
    eta_days: Decimal,
    financial_exposure: Decimal,
    supplier_risk_score: Decimal,
) -> None:
    """Validate numeric boundaries for risk scoring parameters."""
    if days_of_cover < Decimal("0"):
        raise InvalidRiskScoringInputError(f"Days of cover cannot be negative: {days_of_cover}")
    if eta_days < Decimal("0"):
        raise InvalidRiskScoringInputError(f"ETA days cannot be negative: {eta_days}")
    if financial_exposure < Decimal("0"):
        raise InvalidRiskScoringInputError(
            f"Financial exposure cannot be negative: {financial_exposure}"
        )
    if supplier_risk_score < Decimal("0.0") or supplier_risk_score > Decimal("1.0"):
        raise InvalidRiskScoringInputError(
            f"Supplier risk score must be between 0.0 and 1.0: {supplier_risk_score}"
        )


def compute_risk_level(
    days_of_cover: Decimal | int | float | str,
    eta_days: Decimal | int | float | str,
    financial_exposure: Decimal | int | float | str,
    supplier_risk_score: Decimal | int | float | str = Decimal("0.00"),
    gap_days: Decimal | int | float | str | None = None,
) -> RiskLevel:
    """Determine risk severity level according to CLAUDE.md:428-439 logic.

    Rules:
    - gap = eta_days - days_of_cover
    - If gap > 0 AND financial_exposure > $1,000,000.00 -> CRITICAL
    - Else if gap > 0 AND financial_exposure > $250,000.00 -> HIGH
    - Else if gap > 0 OR supplier_risk_score > 0.70 -> MEDIUM
    - Else -> LOW
    """
    cover = _to_decimal(days_of_cover, "days_of_cover")
    eta = _to_decimal(eta_days, "eta_days")
    exposure = _to_decimal(financial_exposure, "financial_exposure")
    supplier_score = _to_decimal(supplier_risk_score, "supplier_risk_score")

    _validate_inputs(cover, eta, exposure, supplier_score)

    if gap_days is not None:
        gap = _to_decimal(gap_days, "gap_days")
    else:
        gap = eta - cover

    if gap > Decimal("0.00") and exposure > THRESHOLD_EXPOSURE_CRITICAL:
        return RiskLevel.CRITICAL
    if gap > Decimal("0.00") and exposure > THRESHOLD_EXPOSURE_HIGH:
        return RiskLevel.HIGH
    if gap > Decimal("0.00") or supplier_score > THRESHOLD_SUPPLIER_RISK_MEDIUM:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


@dataclass(frozen=True)
class RiskScoreResult:
    """Deterministic result of supply chain risk classification."""

    risk_level: RiskLevel
    days_of_cover: Decimal
    gap_days: Decimal
    financial_exposure: Decimal
    supplier_risk_score: Decimal = Decimal("0.00")
    is_single_source: bool = False
    requires_hitl: bool = False
    recommended_hitl_tier: SpendTier | None = None
    reasons: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary suitable for JSON serialization."""
        return {
            "risk_level": (
                self.risk_level.value if hasattr(self.risk_level, "value") else str(self.risk_level)
            ),
            "days_of_cover": str(self.days_of_cover),
            "gap_days": str(self.gap_days),
            "financial_exposure": str(self.financial_exposure),
            "supplier_risk_score": str(self.supplier_risk_score),
            "is_single_source": self.is_single_source,
            "requires_hitl": self.requires_hitl,
            "recommended_hitl_tier": (
                self.recommended_hitl_tier.value if self.recommended_hitl_tier else None
            ),
            "reasons": list(self.reasons),
            "created_at": self.created_at.isoformat(),
        }


class RiskScorer:
    """Deterministic risk classification and HITL requirement evaluation engine."""

    @staticmethod
    def evaluate_hitl_requirement(
        risk_level: RiskLevel,
        financial_exposure: Decimal,
    ) -> tuple[bool, SpendTier | None]:
        """Determine whether human-in-the-loop governance is mandatory and which tier applies.

        Rules:
        - Financial commitment > 0 requires cryptographic spend authorization via SpendTier:
          * <= $25,000: Category Manager (1-hr TTL)
          * $25,001 - $100,000: Procurement Director (1-hr TTL)
          * > $100,000: Dual VP sign-off (30-min TTL)
        - CRITICAL and HIGH severity disruptions always require HITL review.
        - If exposure is 0 and risk is LOW or MEDIUM without spend, HITL is False.
        """
        if financial_exposure > Decimal("0.00"):
            tier = get_spend_tier(financial_exposure)
            return True, tier

        if risk_level in (RiskLevel.CRITICAL, RiskLevel.HIGH):
            return True, SpendTier.CATEGORY_MGR

        return False, None

    def score(
        self,
        days_of_cover: Decimal | int | float | str,
        eta_days: Decimal | int | float | str,
        financial_exposure: Decimal | int | float | str,
        supplier_risk_score: Decimal | int | float | str = Decimal("0.00"),
        is_single_source: bool = False,
        gap_days: Decimal | int | float | str | None = None,
    ) -> RiskScoreResult:
        """Score risk severity and evaluate HITL requirements deterministically."""
        cover = _to_decimal(days_of_cover, "days_of_cover")
        eta = _to_decimal(eta_days, "eta_days")
        exposure = _to_decimal(financial_exposure, "financial_exposure")
        supplier_score = _to_decimal(supplier_risk_score, "supplier_risk_score")

        _validate_inputs(cover, eta, exposure, supplier_score)

        if gap_days is not None:
            gap = _to_decimal(gap_days, "gap_days")
            if gap < Decimal("0.00"):
                raise InvalidRiskScoringInputError(f"Gap days cannot be negative: {gap}")
        else:
            diff = eta - cover
            gap = max(Decimal("0.00"), diff).quantize(PRECISION_DAYS, rounding=ROUND_HALF_UP)

        risk_level = compute_risk_level(
            days_of_cover=cover,
            eta_days=eta,
            financial_exposure=exposure,
            supplier_risk_score=supplier_score,
            gap_days=gap,
        )

        requires_hitl, recommended_tier = self.evaluate_hitl_requirement(
            risk_level=risk_level,
            financial_exposure=exposure,
        )

        reasons: list[str] = []
        if risk_level == RiskLevel.CRITICAL:
            reasons.append(
                f"Financial exposure of ${exposure:.2f} exceeds CRITICAL threshold "
                f"(${THRESHOLD_EXPOSURE_CRITICAL:.2f}) with coverage gap of {gap:.2f} days"
            )
        elif risk_level == RiskLevel.HIGH:
            reasons.append(
                f"Financial exposure of ${exposure:.2f} exceeds HIGH threshold "
                f"(${THRESHOLD_EXPOSURE_HIGH:.2f}) with coverage gap of {gap:.2f} days"
            )
        elif risk_level == RiskLevel.MEDIUM:
            if gap > Decimal("0.00"):
                reasons.append(
                    f"Coverage gap of {gap:.2f} days detected with financial exposure of ${exposure:.2f}"
                )
            if supplier_score > THRESHOLD_SUPPLIER_RISK_MEDIUM:
                reasons.append(
                    f"Supplier risk score ({supplier_score:.3f}) exceeds threshold "
                    f"({THRESHOLD_SUPPLIER_RISK_MEDIUM:.2f})"
                )
        else:
            reasons.append(
                f"Inventory coverage ({cover:.2f} days) is adequate for replenishment ETA "
                f"({eta:.2f} days) and supplier risk score ({supplier_score:.3f}) is acceptable"
            )

        if is_single_source:
            reasons.append("Component is single-sourced with no secondary qualified supplier")

        if requires_hitl and recommended_tier:
            reasons.append(
                f"Requires {recommended_tier.value} cryptographic HITL spend authorization"
            )

        return RiskScoreResult(
            risk_level=risk_level,
            days_of_cover=cover.quantize(PRECISION_DAYS, rounding=ROUND_HALF_UP),
            gap_days=gap,
            financial_exposure=exposure.quantize(PRECISION_CURRENCY, rounding=ROUND_HALF_UP),
            supplier_risk_score=supplier_score,
            is_single_source=is_single_source,
            requires_hitl=requires_hitl,
            recommended_hitl_tier=recommended_tier,
            reasons=reasons,
        )

    def score_assessment(
        self,
        assessment: RiskAssessmentResult,
        eta_days: Decimal | int | float | str | None = None,
        supplier_risk_score: Decimal | int | float | str = Decimal("0.00"),
        is_single_source: bool = False,
    ) -> RiskScoreResult:
        """Score risk directly from a RiskAssessmentResult produced by RiskCalculator."""
        if eta_days is not None:
            eta = _to_decimal(eta_days, "eta_days")
        else:
            eta = assessment.days_of_cover + assessment.gap_days

        return self.score(
            days_of_cover=assessment.days_of_cover,
            eta_days=eta,
            financial_exposure=assessment.financial_exposure,
            supplier_risk_score=supplier_risk_score,
            is_single_source=is_single_source,
            gap_days=assessment.gap_days,
        )

    def score_from_dict(self, data: dict[str, Any]) -> RiskScoreResult:
        """Parse dictionary payload and execute risk scoring."""
        return self.score(
            days_of_cover=data["days_of_cover"],
            eta_days=data["eta_days"],
            financial_exposure=data["financial_exposure"],
            supplier_risk_score=data.get("supplier_risk_score", Decimal("0.00")),
            is_single_source=data.get("is_single_source", False),
            gap_days=data.get("gap_days"),
        )
