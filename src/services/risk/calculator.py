"""Deterministic supply chain risk calculator (P7-1).

Enforces:
- The Triad of Responsibility (BR-RULE-001): 100% deterministic Python arithmetic.
  LLMs and AI agents are strictly forbidden from performing inventory or financial math.
- Strict Decimal precision: all monetary and inventory metrics use Python Decimal
  with ROUND_HALF_UP rounding. Zero floating-point drift or IEEE 754 truncation.
- Core formulas:
  1. Days of Cover: days_of_cover = current_stock / daily_consumption_rate (NanoCore: 7.68)
  2. Coverage Gap: gap_days = max(0, eta_days - days_of_cover) (NanoCore: 1.32)
  3. Shortage Volume: shortage_volume = gap_days * daily_consumption_rate (NanoCore: 24,420)
  4. Financial Exposure: shortage_volume * unit_cost (NanoCore: $2,448,105.00)
  5. Factory Line Halt: downtime_hours * hourly_halt_cost
- Mandatory edge case handling:
  - Zero stock -> days_of_cover = 0.00
  - Zero consumption -> days_of_cover = 999.00 (DAYS_OF_COVER_MAX_CAP), gap = 0.00
  - Negative gap (ETA < cover) -> gap_days = 0.00, shortage = 0, exposure = 0.00
  - Negative inputs -> InvalidInventoryInputError
- Deterministic SHA-256 calculation verification hash.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from src.api.exceptions import AppException
from src.core.logging import get_logger

logger = get_logger("apexmotion.services.risk.calculator")

# Precision constants
PRECISION_DAYS = Decimal("0.01")
PRECISION_CURRENCY = Decimal("0.01")
PRECISION_UNITS = Decimal("1")
DAYS_OF_COVER_MAX_CAP = Decimal("999.00")
DEFAULT_OPERATING_HOURS_PER_DAY = Decimal("24.0")


class InvalidInventoryInputError(AppException):
    """Raised when risk calculation inputs violate physical inventory constraints."""

    def __init__(self, message: str, details: Any = None) -> None:
        super().__init__(
            code="INVALID_INVENTORY_INPUT",
            message=message,
            status_code=400,
            details=details,
        )


def _to_decimal(val: Any, field_name: str) -> Decimal:
    """Safely coerce int, float, str, or Decimal into Decimal with validation."""
    if val is None:
        raise InvalidInventoryInputError(f"Field '{field_name}' cannot be None")
    if isinstance(val, Decimal):
        dec_val = val
    else:
        try:
            dec_val = Decimal(str(val))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise InvalidInventoryInputError(
                f"Failed to parse Decimal for field '{field_name}': {val}"
            ) from exc

    if dec_val.is_nan() or dec_val.is_infinite():
        raise InvalidInventoryInputError(f"Field '{field_name}' cannot be NaN or Infinite: {val}")
    return dec_val


@dataclass(frozen=True)
class RiskAssessmentInput:
    """Input parameters for deterministic supply chain risk calculation."""

    current_stock: int
    daily_consumption_rate: int | Decimal
    eta_days: Decimal
    unit_cost_usd: Decimal
    supplier_id: str | None = None
    component_sku: str | None = None
    factory_halt_cost_per_hour_eur: Decimal | None = None
    operating_hours_per_day: Decimal = DEFAULT_OPERATING_HOURS_PER_DAY


@dataclass(frozen=True)
class RiskAssessmentResult:
    """Deterministic output of supply chain risk calculation."""

    days_of_cover: Decimal
    gap_days: Decimal
    shortage_volume: int
    financial_exposure: Decimal
    downtime_hours: Decimal = Decimal("0.00")
    factory_halt_exposure: Decimal = Decimal("0.00")
    total_exposure: Decimal = Decimal("0.00")
    is_shortage: bool = False
    calculation_hash: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def financial_exposure_usd(self) -> Decimal:
        """Alias for financial_exposure for golden scenario schema compatibility."""
        return self.financial_exposure

    def to_dict(self) -> dict[str, Any]:
        """Convert calculation results to serialized dictionary with string Decimals."""
        raw = asdict(self)
        raw["days_of_cover"] = str(self.days_of_cover)
        raw["gap_days"] = str(self.gap_days)
        raw["financial_exposure"] = str(self.financial_exposure)
        raw["downtime_hours"] = str(self.downtime_hours)
        raw["factory_halt_exposure"] = str(self.factory_halt_exposure)
        raw["total_exposure"] = str(self.total_exposure)
        raw["created_at"] = self.created_at.isoformat()
        return raw


class RiskCalculator:
    """Deterministic calculation engine for supply chain inventory coverage and financial risk."""

    @staticmethod
    def calculate_days_of_cover(
        current_stock: int | Decimal,
        daily_consumption_rate: int | Decimal,
    ) -> Decimal:
        """Calculate days of inventory cover (current_stock / daily_consumption_rate).

        Args:
            current_stock: Available on-hand inventory units.
            daily_consumption_rate: Daily factory consumption units.

        Returns:
            Days of cover quantized to 2 decimal places (ROUND_HALF_UP).
            If daily_consumption_rate is 0, returns DAYS_OF_COVER_MAX_CAP (999.00).
        """
        stock = _to_decimal(current_stock, "current_stock")
        rate = _to_decimal(daily_consumption_rate, "daily_consumption_rate")

        if stock < Decimal("0"):
            raise InvalidInventoryInputError(f"Current stock cannot be negative: {stock}")
        if rate < Decimal("0"):
            raise InvalidInventoryInputError(f"Consumption rate cannot be negative: {rate}")

        if rate == Decimal("0"):
            logger.warning(
                "Zero consumption rate detected; capping days of cover at %s", DAYS_OF_COVER_MAX_CAP
            )
            return DAYS_OF_COVER_MAX_CAP

        if stock == Decimal("0"):
            return Decimal("0.00")

        return (stock / rate).quantize(PRECISION_DAYS, rounding=ROUND_HALF_UP)

    @staticmethod
    def calculate_gap_days(
        eta_days: Decimal | int | float | str,
        days_of_cover: Decimal | int | float | str,
    ) -> Decimal:
        """Calculate coverage gap days: max(0.00, eta_days - days_of_cover).

        Args:
            eta_days: Days until next replenishment shipment arrives.
            days_of_cover: Current days of inventory cover.

        Returns:
            Coverage gap days quantized to 2 decimal places (clamped to >= 0.00).
        """
        eta = _to_decimal(eta_days, "eta_days")
        cover = _to_decimal(days_of_cover, "days_of_cover")

        if eta < Decimal("0"):
            raise InvalidInventoryInputError(f"ETA days cannot be negative: {eta}")
        if cover < Decimal("0"):
            raise InvalidInventoryInputError(f"Days of cover cannot be negative: {cover}")

        gap = eta - cover
        if gap <= Decimal("0.00"):
            return Decimal("0.00")

        return gap.quantize(PRECISION_DAYS, rounding=ROUND_HALF_UP)

    @staticmethod
    def calculate_shortage_volume(
        gap_days: Decimal | int | float | str,
        daily_consumption_rate: int | Decimal | float | str,
    ) -> int:
        """Calculate projected component unit shortage volume: gap_days * daily_rate.

        Args:
            gap_days: Coverage gap in days.
            daily_consumption_rate: Daily factory consumption units.

        Returns:
            Integer unit shortage (0 if gap_days <= 0).
        """
        gap = _to_decimal(gap_days, "gap_days")
        rate = _to_decimal(daily_consumption_rate, "daily_consumption_rate")

        if gap <= Decimal("0.00") or rate <= Decimal("0"):
            return 0

        shortage_dec = (gap * rate).quantize(PRECISION_UNITS, rounding=ROUND_HALF_UP)
        return int(shortage_dec)

    @staticmethod
    def calculate_financial_exposure(
        shortage_volume: int,
        unit_cost_usd: Decimal | int | float | str,
    ) -> Decimal:
        """Calculate direct inventory financial exposure: shortage_volume * unit_cost_usd.

        Args:
            shortage_volume: Projected component shortage volume.
            unit_cost_usd: Contract unit price in USD.

        Returns:
            Financial exposure in USD quantized to NUMERIC(14,2).
        """
        cost = _to_decimal(unit_cost_usd, "unit_cost_usd")

        if shortage_volume < 0:
            raise InvalidInventoryInputError(
                f"Shortage volume cannot be negative: {shortage_volume}"
            )
        if cost < Decimal("0.00"):
            raise InvalidInventoryInputError(f"Unit cost cannot be negative: {cost}")

        if shortage_volume == 0 or cost == Decimal("0.00"):
            return Decimal("0.00")

        exposure = Decimal(str(shortage_volume)) * cost
        return exposure.quantize(PRECISION_CURRENCY, rounding=ROUND_HALF_UP)

    @staticmethod
    def calculate_downtime_exposure(
        gap_days: Decimal | int | float | str,
        operating_hours_per_day: Decimal | int | float | str = DEFAULT_OPERATING_HOURS_PER_DAY,
        hourly_rate: Decimal | int | float | str = Decimal("85000.00"),
    ) -> Decimal:
        """Calculate factory line halt downtime financial impact.

        Args:
            gap_days: Days of factory stockout downtime.
            operating_hours_per_day: Factory operating hours per 24-hr day.
            hourly_rate: Hourly financial downtime cost (e.g. €85,000/hr).

        Returns:
            Total downtime financial exposure quantized to NUMERIC(14,2).
        """
        gap = _to_decimal(gap_days, "gap_days")
        hours = _to_decimal(operating_hours_per_day, "operating_hours_per_day")
        rate = _to_decimal(hourly_rate, "hourly_rate")

        if hours < Decimal("0.00"):
            raise InvalidInventoryInputError(f"Operating hours per day cannot be negative: {hours}")
        if rate < Decimal("0.00"):
            raise InvalidInventoryInputError(f"Hourly halt rate cannot be negative: {rate}")

        if gap <= Decimal("0.00"):
            return Decimal("0.00")

        total_downtime_hours = (gap * hours).quantize(PRECISION_DAYS, rounding=ROUND_HALF_UP)
        halt_cost = total_downtime_hours * rate
        return halt_cost.quantize(PRECISION_CURRENCY, rounding=ROUND_HALF_UP)

    def calculate(self, input_data: RiskAssessmentInput) -> RiskAssessmentResult:
        """Execute complete deterministic risk assessment from input data model.

        Args:
            input_data: RiskAssessmentInput containing validated stock, rate, ETA, and cost.

        Returns:
            RiskAssessmentResult with all calculated metrics and verification hash.
        """
        if input_data.operating_hours_per_day < Decimal("0.00"):
            raise InvalidInventoryInputError(
                f"Operating hours per day cannot be negative: {input_data.operating_hours_per_day}"
            )
        if (
            input_data.factory_halt_cost_per_hour_eur is not None
            and input_data.factory_halt_cost_per_hour_eur < Decimal("0.00")
        ):
            raise InvalidInventoryInputError(
                f"Hourly halt rate cannot be negative: {input_data.factory_halt_cost_per_hour_eur}"
            )

        # 1. Days of cover
        days_of_cover = self.calculate_days_of_cover(
            current_stock=input_data.current_stock,
            daily_consumption_rate=input_data.daily_consumption_rate,
        )

        # 2. Shortage gap
        gap_days = self.calculate_gap_days(
            eta_days=input_data.eta_days,
            days_of_cover=days_of_cover,
        )

        # 3. Shortage volume
        shortage_volume = self.calculate_shortage_volume(
            gap_days=gap_days,
            daily_consumption_rate=input_data.daily_consumption_rate,
        )

        # 4. Direct component financial exposure
        financial_exposure = self.calculate_financial_exposure(
            shortage_volume=shortage_volume,
            unit_cost_usd=input_data.unit_cost_usd,
        )

        # 5. Factory halt downtime impact (if configured)
        downtime_hours = Decimal("0.00")
        factory_halt_exposure = Decimal("0.00")
        if input_data.factory_halt_cost_per_hour_eur is not None and gap_days > Decimal("0.00"):
            hours_per_day = input_data.operating_hours_per_day
            downtime_hours = (gap_days * hours_per_day).quantize(
                PRECISION_DAYS, rounding=ROUND_HALF_UP
            )
            factory_halt_exposure = self.calculate_downtime_exposure(
                gap_days=gap_days,
                operating_hours_per_day=hours_per_day,
                hourly_rate=input_data.factory_halt_cost_per_hour_eur,
            )

        total_exposure = financial_exposure + factory_halt_exposure
        is_shortage = gap_days > Decimal("0.00")

        # 6. Cryptographic calculation verification hash
        hash_payload = {
            "current_stock": int(input_data.current_stock),
            "daily_consumption_rate": str(input_data.daily_consumption_rate),
            "days_of_cover": str(days_of_cover),
            "eta_days": str(input_data.eta_days),
            "financial_exposure": str(financial_exposure),
            "gap_days": str(gap_days),
            "shortage_volume": shortage_volume,
            "total_exposure": str(total_exposure),
            "unit_cost_usd": str(input_data.unit_cost_usd),
        }
        calc_hash = hashlib.sha256(
            json.dumps(hash_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()

        return RiskAssessmentResult(
            days_of_cover=days_of_cover,
            gap_days=gap_days,
            shortage_volume=shortage_volume,
            financial_exposure=financial_exposure,
            downtime_hours=downtime_hours,
            factory_halt_exposure=factory_halt_exposure,
            total_exposure=total_exposure,
            is_shortage=is_shortage,
            calculation_hash=calc_hash,
        )

    def calculate_from_params(
        self,
        current_stock: int | Decimal | float | str,
        daily_consumption_rate: int | Decimal | float | str,
        eta_days: Decimal | int | float | str,
        unit_cost_usd: Decimal | int | float | str,
        supplier_id: str | None = None,
        component_sku: str | None = None,
        factory_halt_cost_per_hour_eur: Decimal | int | float | str | None = None,
        operating_hours_per_day: Decimal | int | float | str = DEFAULT_OPERATING_HOURS_PER_DAY,
    ) -> RiskAssessmentResult:
        """Convenience method accepting raw parameters with automatic type coercion."""
        stock_dec = _to_decimal(current_stock, "current_stock")
        halt_cost_dec = (
            _to_decimal(factory_halt_cost_per_hour_eur, "factory_halt_cost_per_hour_eur")
            if factory_halt_cost_per_hour_eur is not None
            else None
        )
        input_data = RiskAssessmentInput(
            current_stock=int(stock_dec),
            daily_consumption_rate=_to_decimal(daily_consumption_rate, "daily_consumption_rate"),
            eta_days=_to_decimal(eta_days, "eta_days"),
            unit_cost_usd=_to_decimal(unit_cost_usd, "unit_cost_usd"),
            supplier_id=supplier_id,
            component_sku=component_sku,
            factory_halt_cost_per_hour_eur=halt_cost_dec,
            operating_hours_per_day=_to_decimal(operating_hours_per_day, "operating_hours_per_day"),
        )
        return self.calculate(input_data)

    def calculate_from_dict(self, data: dict[str, Any]) -> RiskAssessmentResult:
        """Parse dictionary payload and execute risk calculation."""
        return self.calculate_from_params(
            current_stock=data["current_stock"],
            daily_consumption_rate=data["daily_consumption_rate"],
            eta_days=data["eta_days"],
            unit_cost_usd=data["unit_cost_usd"],
            supplier_id=data.get("supplier_id"),
            component_sku=data.get("component_sku"),
            factory_halt_cost_per_hour_eur=data.get("factory_halt_cost_per_hour_eur"),
            operating_hours_per_day=data.get(
                "operating_hours_per_day", DEFAULT_OPERATING_HOURS_PER_DAY
            ),
        )
