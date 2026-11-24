"""Investigation API routes for triggering and polling multi-agent investigations (P11-2).

Endpoints:
- POST /api/v1/investigations/start: Trigger an automated sub-90s multi-agent investigation.
- GET /api/v1/investigations/{investigation_id}: Poll progress, active node, and finalized case dossier.
- POST /api/v1/investigations/trigger: Backward-compatible alias for /start.
- GET /api/v1/cases/{case_id}: Backward-compatible alias for polling by case dossier identifier.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.exceptions import NotFoundException
from src.api.schemas.investigation import (
    InvestigationDetailResponse,
    InvestigationStartRequest,
    InvestigationStartResponse,
)
from src.core.logging import get_logger, get_trace_id
from src.core.security import AuthenticatedUser, UserRole, require_role
from src.database.session import get_db_session
from src.services.investigation_service import (
    InvestigationService,
    get_investigation_service,
)

logger = get_logger("apexmotion.api.investigations")

router = APIRouter(tags=["Investigations & Cases"])


@router.post(
    "/api/v1/investigations/start",
    response_model=InvestigationStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger automated multi-agent risk investigation pipeline",
)
@router.post(
    "/api/v1/investigations/trigger",
    response_model=InvestigationStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
    include_in_schema=False,
)
async def start_investigation(
    payload: InvestigationStartRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_role(UserRole.ANALYST))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[InvestigationService, Depends(get_investigation_service)],
) -> InvestigationStartResponse:
    """Trigger an automated multi-agent incident investigation pipeline (SLO p95 <= 90s).

    1. Quarantines raw signal text and extracts disruption taxonomy.
    2. Initializes and registers the LangGraph StateMachine workflow.
    3. Asynchronously invokes research, contract, deterministic risk, and recommendation nodes.
    4. Returns immediately with HTTP 202 Accepted and a polling URL.
    """
    logger.info(
        "Investigation requested by %s for supplier '%s' (sku='%s')",
        current_user.user_id,
        payload.supplier_id,
        payload.component_sku,
        extra={"trace_id": get_trace_id()},
    )

    record = await service.start_investigation(
        payload=payload,
        current_user=current_user,
        session=session,
    )

    poll_url = f"/api/v1/investigations/{record.investigation_id}"

    return InvestigationStartResponse(
        investigation_id=record.investigation_id,
        case_id=record.case_id,
        alert_id=record.alert_id,
        status=record.status,
        poll_url=poll_url,
        started_at=record.started_at,
        estimated_completion_seconds=90,
        message="Investigation pipeline started successfully",
    )


@router.get(
    "/api/v1/investigations/{investigation_id}",
    response_model=InvestigationDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Poll investigation status or retrieve grounded case dossier",
)
@router.get(
    "/api/v1/cases/{investigation_id}",
    response_model=InvestigationDetailResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def get_investigation_details(
    investigation_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(require_role(UserRole.ANALYST))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[InvestigationService, Depends(get_investigation_service)],
) -> InvestigationDetailResponse:
    """Retrieve the current execution state, active node, or finalized case dossier for an investigation.

    Accepts investigation_id (UUID), case_id (CASE-...), or linked alert_id.
    """
    logger.debug(
        "User %s polling investigation '%s'",
        current_user.user_id,
        investigation_id,
        extra={"trace_id": get_trace_id()},
    )

    record = await service.get_investigation(
        identifier=investigation_id,
        session=session,
    )

    if record is None:
        raise NotFoundException(f"Investigation '{investigation_id}' not found.")

    return InvestigationDetailResponse(
        investigation_id=record.investigation_id,
        case_id=record.case_id,
        alert_id=record.alert_id,
        supplier_id=record.supplier_id,
        component_sku=record.component_sku,
        status=record.status,
        current_node=record.current_node,
        execution_path=record.execution_path,
        risk_metrics=record.risk_metrics,
        severity=record.severity,
        narrative=record.narrative,
        research_analysis=record.research_analysis,
        contract_analysis=record.contract_analysis,
        recommendations=record.recommendations,
        recommended_action_id=record.recommended_action_id,
        requires_hitl=record.requires_hitl,
        governing_spend_tier=record.governing_spend_tier,
        errors=record.errors,
        started_at=record.started_at,
        completed_at=record.completed_at,
        duration_ms=record.duration_ms,
        tokens_used=record.tokens_used,
        cost_usd=record.cost_usd,
    )
