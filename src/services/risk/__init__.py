"""Deterministic supply chain risk engine package for ApexMotion platform.

Enforces:
- The Triad of Responsibility (BR-RULE-001): 100% deterministic pure Python math.
- All monetary and inventory numbers use Decimal precision with zero float truncation.
"""

from src.services.risk.calculator import (
    DAYS_OF_COVER_MAX_CAP,
    DEFAULT_OPERATING_HOURS_PER_DAY,
    InvalidInventoryInputError,
    RiskAssessmentInput,
    RiskAssessmentResult,
    RiskCalculator,
)
from src.services.risk.inventory_service import (
    DEFAULT_CACHE_TTL_SECONDS,
    NANOCORE_CANONICAL_SKU,
    REFERENCE_INVENTORY_REGISTRY,
    InvalidInventoryOperationError,
    InventoryNotFoundError,
    InventoryRecord,
    InventoryService,
    InventoryServiceError,
    PlantInventoryAggregate,
)
from src.services.risk.scorer import (
    THRESHOLD_EXPOSURE_CRITICAL,
    THRESHOLD_EXPOSURE_HIGH,
    THRESHOLD_SUPPLIER_RISK_MEDIUM,
    InvalidRiskScoringInputError,
    RiskScorer,
    RiskScoreResult,
    compute_risk_level,
)

__all__ = [
    "DAYS_OF_COVER_MAX_CAP",
    "DEFAULT_CACHE_TTL_SECONDS",
    "DEFAULT_OPERATING_HOURS_PER_DAY",
    "InvalidInventoryInputError",
    "InvalidInventoryOperationError",
    "InvalidRiskScoringInputError",
    "InventoryNotFoundError",
    "InventoryRecord",
    "InventoryService",
    "InventoryServiceError",
    "NANOCORE_CANONICAL_SKU",
    "PlantInventoryAggregate",
    "REFERENCE_INVENTORY_REGISTRY",
    "RiskAssessmentInput",
    "RiskAssessmentResult",
    "RiskCalculator",
    "RiskScoreResult",
    "RiskScorer",
    "THRESHOLD_EXPOSURE_CRITICAL",
    "THRESHOLD_EXPOSURE_HIGH",
    "THRESHOLD_SUPPLIER_RISK_MEDIUM",
    "compute_risk_level",
]
