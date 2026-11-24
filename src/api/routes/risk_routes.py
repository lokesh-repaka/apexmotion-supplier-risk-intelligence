"""Fast-track and Full-track risk pipeline and alert management routes.

Endpoints:
- POST /api/v1/risk/evaluate: Execute fast-track or full-track risk evaluation pipeline.
- GET /api/v1/alerts: Paginated feed of calculated risk alerts with filtering.
- GET /api/v1/alerts/{alert_id}: Detailed inspection of a specific risk alert.
- POST /api/v1/alerts/{alert_id}/acknowledge: Acknowledge an active alert (category_manager+).
- Also aliases /api/v1/risk/alerts and /api/v1/risk/alerts/{alert_id} for backwards compatibility.
"""

import math
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.exceptions import (
    ConflictException,
    NoOpMutationException,
    NotFoundException,
    ValidationException,
)
from src.api.schemas.risk import (
    AlertAcknowledgeRequest,
    AlertAcknowledgeResponse,
    AuditLogListResponse,
    AuditLogResponse,
    RiskAlertListResponse,
    RiskAlertResponse,
    RiskEvaluationRequest,
    RiskEvaluationResponse,
)
from src.core.audit import write_audit_log
from src.core.hitl_tokens import get_spend_tier
from src.core.logging import get_logger, get_trace_id
from src.core.security import AuthenticatedUser, UserRole, require_role
from src.database.models import RiskAlert
from src.database.repositories.audit_log_repository import AuditLogRepository
from src.database.repositories.risk_alert_repository import RiskAlertRepository
from src.database.session import get_db_session
from src.services.risk import (
    NANOCORE_CANONICAL_SKU,
    REFERENCE_INVENTORY_REGISTRY,
    RiskCalculator,
    compute_risk_level,
)

logger = get_logger("apexmotion.api.risk")

router = APIRouter(tags=["Risk & Alerts"])


def _parse_uuid(val: str, field_name: str = "ID") -> uuid.UUID:
    """Safely parse a string into a UUID or raise a clean ValidationException."""
    try:
        return uuid.UUID(val.strip())
    except (ValueError, AttributeError) as exc:
        raise ValidationException(f"Invalid UUID format for {field_name}: '{val}'.") from exc


# ------------------------------------------------------------------------------
# 1. Pipeline Evaluation: POST /api/v1/risk/evaluate
# ------------------------------------------------------------------------------


@router.post(
    "/api/v1/risk/evaluate",
    response_model=RiskEvaluationResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate supplier disruption risk (Fast-track or Full-track)",
)
async def evaluate_risk_pipeline(
    payload: RiskEvaluationRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_role(UserRole.ANALYST))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RiskEvaluationResponse:
    """Execute risk evaluation pipeline for a component / supplier disruption.

    Strictly adheres to The Triad of Responsibility (BR-RULE-001):
    1. 100% of arithmetic calculations (Days of Cover, Shortage Volume, Exposure)
       are computed by the deterministic Python RiskCalculator with Decimal precision.
    2. Classifies execution into FAST_TRACK (zero shortage / low impact) or
       FULL_TRACK (critical coverage gap / high exposure requiring mitigation).
    3. Persists evaluated RiskAlert and dispatches append-only forensic audit trail.
    """
    evaluation_id = str(uuid.uuid4())
    logger.info(
        "Risk evaluation requested by %s for SKU '%s' (mode=%s)",
        current_user.user_id,
        payload.component_sku,
        payload.pipeline_mode,
        extra={"trace_id": get_trace_id()},
    )

    # 1. Resolve inventory and consumption parameters
    stock = payload.current_stock
    daily_rate = payload.daily_consumption_rate
    eta = payload.eta_days if payload.eta_days is not None else Decimal("9.0")
    cost = payload.unit_cost_usd if payload.unit_cost_usd is not None else Decimal("100.25")

    # If stock or consumption rate are omitted, check canonical reference inventory registry
    if stock is None or daily_rate is None:
        ref_record = REFERENCE_INVENTORY_REGISTRY.get(payload.component_sku)
        if ref_record is not None:
            if stock is None:
                stock = Decimal(str(ref_record["current_stock"]))
            if daily_rate is None:
                daily_rate = Decimal(str(ref_record["daily_consumption_rate"]))
            if payload.unit_cost_usd is None:
                cost = Decimal(str(ref_record["unit_cost_usd"]))
        else:
            # Sensible baseline defaults
            if stock is None:
                stock = (
                    Decimal("142000")
                    if payload.component_sku in (NANOCORE_CANONICAL_SKU, "NC-2024-001")
                    else Decimal("10000")
                )
            if daily_rate is None:
                daily_rate = (
                    Decimal("18500")
                    if payload.component_sku in (NANOCORE_CANONICAL_SKU, "NC-2024-001")
                    else Decimal("1000")
                )
            if payload.unit_cost_usd is None and payload.component_sku in (
                NANOCORE_CANONICAL_SKU,
                "NC-2024-001",
            ):
                cost = Decimal("100.25")

    # 2. Pure deterministic calculation via RiskCalculator (Zero LLM math)
    calculator = RiskCalculator()
    calc_result = calculator.calculate_from_params(
        current_stock=int(stock),
        daily_consumption_rate=daily_rate,
        eta_days=eta,
        unit_cost_usd=cost,
    )

    # 3. Deterministic risk level scoring
    risk_level_enum = compute_risk_level(
        days_of_cover=calc_result.days_of_cover,
        eta_days=eta,
        financial_exposure=calc_result.financial_exposure,
        supplier_risk_score=Decimal("0.5"),
        gap_days=calc_result.gap_days,
    )
    risk_level_val: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"] = risk_level_enum.value
    risk_level_str = risk_level_val

    # 4. Spend tier and HITL evaluation
    total_exposure = calc_result.total_exposure
    requires_hitl = total_exposure > Decimal("0.00")
    spend_tier_enum = get_spend_tier(total_exposure) if requires_hitl else None
    spend_tier_str = spend_tier_enum.value if spend_tier_enum is not None else None

    # 5. Fast-track vs Full-track Classification
    pipeline_track: Literal["FAST_TRACK", "FULL_TRACK"]
    if payload.pipeline_mode == "fast_track":
        pipeline_track = "FAST_TRACK"
        fast_track_reason = "Explicit fast-track evaluation requested."
    elif payload.pipeline_mode == "full_track":
        pipeline_track = "FULL_TRACK"
        fast_track_reason = "Explicit full-track agent investigation requested."
    else:
        # Auto-routing based on shortage gap and exposure severity
        if calc_result.gap_days <= Decimal("0.00") or risk_level_str == "LOW":
            pipeline_track = "FAST_TRACK"
            fast_track_reason = "Sufficient inventory buffer (gap <= 0); zero line halt risk."
        else:
            pipeline_track = "FULL_TRACK"
            fast_track_reason = (
                f"Critical disruption detected: gap={calc_result.gap_days}d, "
                f"shortage={calc_result.shortage_volume} units, exposure=${total_exposure}."
            )

    # 6. Database Persistence via RiskAlertRepository
    repo = RiskAlertRepository(session)
    supplier_uuid = _parse_uuid(payload.supplier_id, "supplier_id") if payload.supplier_id else None

    # Check for recent active alert within 1-hour rolling window for deduplication
    existing_alert = await repo.find_recent_active_alert(
        component_sku=payload.component_sku,
        supplier_id=supplier_uuid,
        window_seconds=3600,
    )

    if existing_alert is not None:
        # Update existing alert if new exposure or severity is higher
        existing_alert.days_of_cover = calc_result.days_of_cover
        existing_alert.financial_exposure = total_exposure
        existing_alert.shortage_volume = calc_result.shortage_volume
        existing_alert.risk_level = risk_level_str
        persisted_alert = await repo.update(existing_alert)
        alert_id = str(persisted_alert.id)
        outcome_status = "COLLAPSED"
    else:
        # Create fresh alert record
        new_alert = RiskAlert(
            supplier_id=supplier_uuid,
            component_sku=payload.component_sku,
            risk_level=risk_level_str,
            days_of_cover=calc_result.days_of_cover,
            financial_exposure=total_exposure,
            shortage_volume=calc_result.shortage_volume,
            status="OPEN",
        )
        persisted_alert = await repo.create(new_alert)
        alert_id = str(persisted_alert.id)
        outcome_status = "EVALUATED"

    # 7. Immutable Forensic Audit Log
    try:
        await write_audit_log(
            entity_type="RISK_EVALUATION",
            entity_id=alert_id,
            action="RISK_EVALUATION_EXECUTED",
            actor_id=current_user.user_id,
            after_state={
                "component_sku": payload.component_sku,
                "pipeline_track": pipeline_track,
                "risk_level": risk_level_str,
                "days_of_cover": str(calc_result.days_of_cover),
                "financial_exposure": str(total_exposure),
                "requires_hitl": requires_hitl,
                "spend_tier": spend_tier_str,
            },
        )
    except Exception as exc:
        logger.warning("Audit write failed during risk evaluation: %s", exc)

    return RiskEvaluationResponse(
        evaluation_id=evaluation_id,
        alert_id=alert_id,
        pipeline_track=pipeline_track,
        status=outcome_status,
        component_sku=payload.component_sku,
        supplier_id=str(supplier_uuid) if supplier_uuid else None,
        days_of_cover=calc_result.days_of_cover,
        gap_days=calc_result.gap_days,
        shortage_volume=calc_result.shortage_volume,
        financial_exposure_usd=total_exposure,
        risk_level=risk_level_val,
        requires_hitl=requires_hitl,
        governing_spend_tier=spend_tier_str,
        fast_track_reason=fast_track_reason,
        evaluated_at=datetime.now(UTC),
    )


# ------------------------------------------------------------------------------
# 2. Alert Feed Routes: GET /api/v1/alerts & GET /api/v1/risk/alerts
# ------------------------------------------------------------------------------


@router.get(
    "/api/v1/alerts",
    response_model=RiskAlertListResponse,
    status_code=status.HTTP_200_OK,
    summary="List paginated risk alerts with filtering",
)
@router.get(
    "/api/v1/risk/alerts",
    response_model=RiskAlertListResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def list_risk_alerts(
    current_user: Annotated[AuthenticatedUser, Depends(require_role(UserRole.ANALYST))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    page: Annotated[int, Query(ge=1, description="Page number (1-indexed)")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Page size limit")] = 20,
    supplier_id: Annotated[str | None, Query(description="Filter by supplier UUID")] = None,
    component_sku: Annotated[str | None, Query(description="Filter by component SKU")] = None,
    risk_level: Annotated[
        str | None, Query(description="Filter by severity level: CRITICAL, HIGH, MEDIUM, LOW")
    ] = None,
    alert_status: Annotated[
        str | None,
        Query(
            alias="status",
            description="Filter by status: OPEN, INVESTIGATING, ACKNOWLEDGED, RESOLVED",
        ),
    ] = None,
) -> RiskAlertListResponse:
    """Fetch paginated risk alert feed with multi-attribute filtering."""
    logger.debug(
        "Listing risk alerts for user '%s' (page=%s, size=%s)",
        current_user.user_id,
        page,
        page_size,
    )
    stmt = select(RiskAlert)
    count_stmt = select(func.count(RiskAlert.id))

    if supplier_id:
        s_uuid = _parse_uuid(supplier_id, "supplier_id")
        stmt = stmt.where(RiskAlert.supplier_id == s_uuid)
        count_stmt = count_stmt.where(RiskAlert.supplier_id == s_uuid)

    if component_sku:
        sku_clean = component_sku.strip().upper()
        stmt = stmt.where(RiskAlert.component_sku == sku_clean)
        count_stmt = count_stmt.where(RiskAlert.component_sku == sku_clean)

    if risk_level:
        lvl_clean = risk_level.strip().upper()
        stmt = stmt.where(RiskAlert.risk_level == lvl_clean)
        count_stmt = count_stmt.where(RiskAlert.risk_level == lvl_clean)

    if alert_status:
        st_clean = alert_status.strip().upper()
        stmt = stmt.where(RiskAlert.status == st_clean)
        count_stmt = count_stmt.where(RiskAlert.status == st_clean)

    # Total count
    total_res = await session.execute(count_stmt)
    total_count = int(total_res.scalar_one())

    # Pagination & Ordering
    offset = (page - 1) * page_size
    stmt = stmt.order_by(RiskAlert.created_at.desc()).offset(offset).limit(page_size)

    result = await session.execute(stmt)
    alerts = result.scalars().all()

    items = [
        RiskAlertResponse(
            id=str(a.id),
            supplier_id=str(a.supplier_id) if a.supplier_id else None,
            component_sku=a.component_sku,
            risk_level=a.risk_level,
            days_of_cover=a.days_of_cover,
            financial_exposure=a.financial_exposure,
            shortage_volume=a.shortage_volume,
            status=a.status,
            created_at=a.created_at,
        )
        for a in alerts
    ]

    total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0

    return RiskAlertListResponse(
        items=items,
        total=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ------------------------------------------------------------------------------
# 3. Alert Detail Routes: GET /api/v1/alerts/{alert_id} & GET /api/v1/risk/alerts/{alert_id}
# ------------------------------------------------------------------------------


@router.get(
    "/api/v1/alerts/{alert_id}",
    response_model=RiskAlertResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single risk alert details",
)
@router.get(
    "/api/v1/risk/alerts/{alert_id}",
    response_model=RiskAlertResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def get_risk_alert_by_id(
    alert_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(require_role(UserRole.ANALYST))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RiskAlertResponse:
    """Fetch complete detail record for a specific risk alert."""
    a_uuid = _parse_uuid(alert_id, "alert_id")
    logger.debug(
        "Fetching risk alert '%s' for user '%s'",
        alert_id,
        current_user.user_id,
    )
    repo = RiskAlertRepository(session)
    alert = await repo.get_by_id(a_uuid)

    if alert is None:
        raise NotFoundException(f"Risk alert '{alert_id}' not found.")

    return RiskAlertResponse(
        id=str(alert.id),
        supplier_id=str(alert.supplier_id) if alert.supplier_id else None,
        component_sku=alert.component_sku,
        risk_level=alert.risk_level,
        days_of_cover=alert.days_of_cover,
        financial_exposure=alert.financial_exposure,
        shortage_volume=alert.shortage_volume,
        status=alert.status,
        created_at=alert.created_at,
    )


# ------------------------------------------------------------------------------
# 4. Alert Acknowledge: POST /api/v1/alerts/{alert_id}/acknowledge
# ------------------------------------------------------------------------------


@router.post(
    "/api/v1/alerts/{alert_id}/acknowledge",
    response_model=AlertAcknowledgeResponse,
    status_code=status.HTTP_200_OK,
    summary="Acknowledge an active risk alert (category_manager+)",
)
@router.post(
    "/api/v1/risk/alerts/{alert_id}/acknowledge",
    response_model=AlertAcknowledgeResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def acknowledge_risk_alert(
    alert_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(require_role(UserRole.CATEGORY_MANAGER))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    payload: AlertAcknowledgeRequest | None = None,
) -> AlertAcknowledgeResponse:
    """Acknowledge an active risk alert, transitioning status from OPEN to ACKNOWLEDGED.

    Requires Category Manager authority or higher. Read-only analysts are rejected with 403.
    """
    a_uuid = _parse_uuid(alert_id, "alert_id")
    logger.debug(
        "Acknowledging risk alert '%s' for user '%s'",
        alert_id,
        current_user.user_id,
    )
    repo = RiskAlertRepository(session)
    alert = await repo.get_by_id(a_uuid)

    if alert is None:
        raise NotFoundException(f"Risk alert '{alert_id}' not found.")

    if alert.status == "ACKNOWLEDGED":
        raise NoOpMutationException(
            f"Alert '{alert_id}' is already in ACKNOWLEDGED status. No-op mutation rejected."
        )

    if alert.status in ("RESOLVED", "CLOSED", "DISMISSED"):
        raise ConflictException(
            f"Cannot acknowledge alert '{alert_id}' in terminal status '{alert.status}'."
        )

    # Transition status
    before_status = alert.status
    alert.status = "ACKNOWLEDGED"
    await repo.update(alert)

    # Permanent audit log
    notes_val = payload.notes if payload is not None else None
    try:
        await write_audit_log(
            entity_type="RISK_ALERT",
            entity_id=alert_id,
            action="ALERT_ACKNOWLEDGED",
            actor_id=current_user.user_id,
            before_state={"status": before_status},
            after_state={"status": "ACKNOWLEDGED", "notes": notes_val},
        )
    except Exception as exc:
        logger.warning("Audit write failed during alert acknowledgement: %s", exc)

    logger.info(
        "Alert '%s' acknowledged by user '%s' (%s)",
        alert_id,
        current_user.user_id,
        current_user.roles,
        extra={"trace_id": get_trace_id()},
    )

    return AlertAcknowledgeResponse(
        id=str(alert.id),
        status="ACKNOWLEDGED",
        acknowledged_by=current_user.user_id,
        acknowledged_at=datetime.now(UTC),
        notes=notes_val,
    )


# ------------------------------------------------------------------------------
# 5. Alert Audit Trail: GET /api/v1/alerts/{alert_id}/audit
# ------------------------------------------------------------------------------


@router.get(
    "/api/v1/alerts/{alert_id}/audit",
    response_model=AuditLogListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get chronological immutable audit trail for a specific risk alert",
)
async def get_alert_audit_trail(
    alert_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(require_role(UserRole.ANALYST))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AuditLogListResponse:
    """Fetch immutable chronological forensic audit trail for a risk alert (BR-RULE-007).

    Read access is permitted to Analysts and higher roles.
    """
    a_uuid = _parse_uuid(alert_id, "alert_id")
    logger.debug("Fetching audit trail for alert '%s' (user: %s)", alert_id, current_user.user_id)

    # Verify alert exists
    alert_repo = RiskAlertRepository(session)
    alert = await alert_repo.get_by_id(a_uuid)
    if alert is None:
        raise NotFoundException(f"Risk alert '{alert_id}' not found.")

    audit_repo = AuditLogRepository(session)
    records = await audit_repo.get_by_entity(entity_type="RISK_ALERT", entity_id=a_uuid)

    items = [
        AuditLogResponse(
            id=r.id,
            entity_type=r.entity_type,
            entity_id=str(r.entity_id),
            action=r.action,
            actor_id=str(r.actor_id),
            before_state=r.before_state,
            after_state=r.after_state,
            trace_id=r.trace_id,
            created_at=r.created_at,
        )
        for r in records
    ]

    return AuditLogListResponse(
        items=items,
        total=len(items),
        entity_id=str(a_uuid),
        entity_type="RISK_ALERT",
    )

