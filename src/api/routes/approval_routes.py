"""Human-in-the-Loop (HITL) approval API routes (P11-3).

Endpoints:
- GET /api/v1/approvals: Paginated HITL pending queue with status/tier filtering (category_manager+).
- GET /api/v1/approvals/{approval_id}: Detail inspection of a specific approval record.
- POST /api/v1/approvals/{approval_id}/sign: Cryptographically verified sign-off with KMS ECDSA tokens.
- POST /api/v1/approvals/{approval_id}/reject: Reject a pending approval with mandatory reason.
- POST /api/v1/cases/{approval_id}/approve: Backward-compatible alias for case approval.

Enforces:
- The Triad of Responsibility (BR-RULE-001):
  * Probabilistic AI proposes mitigation actions, but deterministic human authority gates financial spend.
  * Monetary precision using Decimal; float arithmetic strictly forbidden.
  * Explicit spend tiers:
    - CATEGORY_MGR: Spend <= $25,000 (1x token, 1-hr TTL, Category Manager+).
    - PROC_DIRECTOR: Spend $25,001 - $100,000 (1x token, 1-hr TTL, Procurement Director+).
    - DUAL_VP: Spend > $100,000 (2x distinct executive tokens, 30-min TTL, Director + VP).
- Cryptographic Anti-Replay (BR-RULE-007):
  * Rejection of replayed token hashes with HTTP 409 and security incident alerting.
"""

import math
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.exceptions import (
    AppException,
    AuthorizationException,
    ConflictException,
    NotFoundException,
    ValidationException,
)
from src.api.schemas.approval import (
    ApprovalItemResponse,
    ApprovalQueueListResponse,
    ApprovalRejectRequest,
    ApprovalRejectResponse,
    ApprovalSignRequest,
    ApprovalSignResponse,
)
from src.core.audit import write_audit_log
from src.core.hitl_tokens import (
    TokenBindingMismatchError,
    TokenExpiredError,
    TokenReplayDetectedError,
    TokenSignatureInvalidError,
)
from src.core.logging import get_logger
from src.core.security import AuthenticatedUser, UserRole, require_role
from src.database.models import HITLApproval
from src.database.repositories.hitl_approval_repository import (
    HITLApprovalRepository,
    TokenReplayError,
)
from src.database.session import get_db_session
from src.services.hitl_service import (
    ApprovalNotFoundError,
    HITLService,
    InvalidApprovalOperationError,
    TokenExpiredServiceError,
    TokenReplayServiceError,
    TokenVerificationServiceError,
    UnauthorizedSignerError,
    get_hitl_service,
)

logger = get_logger("apexmotion.api.approvals")

router = APIRouter(tags=["HITL Approvals & Governance"])


def _parse_uuid(val: str, field_name: str = "ID") -> uuid.UUID:
    """Safely parse a string into a UUID or raise a clean ValidationException."""
    try:
        return uuid.UUID(val.strip())
    except (ValueError, AttributeError) as exc:
        raise ValidationException(f"Invalid UUID format for {field_name}: '{val}'.") from exc


# ------------------------------------------------------------------------------
# 1. Approval Queue Feed: GET /api/v1/approvals
# ------------------------------------------------------------------------------


@router.get(
    "/api/v1/approvals",
    response_model=ApprovalQueueListResponse,
    status_code=status.HTTP_200_OK,
    summary="List paginated HITL approvals in pending queue",
)
async def list_approvals(
    current_user: Annotated[AuthenticatedUser, Depends(require_role(UserRole.CATEGORY_MANAGER))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    page: Annotated[int, Query(ge=1, description="Page number (1-indexed)")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Page size limit")] = 20,
    approval_status: Annotated[
        str | None,
        Query(
            alias="status",
            description="Filter by status: PENDING, PARTIALLY_APPROVED, APPROVED, REJECTED, EXPIRED, or ALL",
        ),
    ] = "PENDING",
    spend_tier: Annotated[
        str | None,
        Query(
            description="Filter by spend authority tier: CATEGORY_MGR, PROC_DIRECTOR, DUAL_VP",
        ),
    ] = None,
) -> ApprovalQueueListResponse:
    """Fetch paginated HITL approvals pending human authority action.

    Restricted to Category Managers, Procurement Directors, VPs, and Admins.
    Read-only Analysts are strictly forbidden from accessing this queue.
    Automatically expires pending approval records exceeding their cryptographic TTL.
    """
    logger.debug(
        "Listing approvals queue for user '%s' (%s) [page=%s, size=%s, status=%s, tier=%s]",
        current_user.user_id,
        ", ".join(current_user.roles),
        page,
        page_size,
        approval_status,
        spend_tier,
    )

    # 1. Bulk update expired pending approvals
    now = datetime.now(UTC)
    await session.execute(
        update(HITLApproval)
        .where(HITLApproval.status == "PENDING")
        .where(HITLApproval.expires_at < now)
        .values(status="EXPIRED")
    )
    await session.commit()

    # 2. Build filtered select and count queries
    stmt = select(HITLApproval)
    count_stmt = select(func.count(HITLApproval.id))

    if approval_status and approval_status.strip().upper() != "ALL":
        st_clean = approval_status.strip().upper()
        stmt = stmt.where(HITLApproval.status == st_clean)
        count_stmt = count_stmt.where(HITLApproval.status == st_clean)

    if spend_tier and spend_tier.strip():
        tier_clean = spend_tier.strip().upper()
        stmt = stmt.where(HITLApproval.spend_tier == tier_clean)
        count_stmt = count_stmt.where(HITLApproval.spend_tier == tier_clean)

    # Total count
    total_res = await session.execute(count_stmt)
    total_count = int(total_res.scalar_one())

    # Pagination & Ordering (oldest pending first if pending, newest first otherwise)
    offset = (page - 1) * page_size
    if approval_status and approval_status.strip().upper() == "PENDING":
        stmt = stmt.order_by(HITLApproval.created_at.asc()).offset(offset).limit(page_size)
    else:
        stmt = stmt.order_by(HITLApproval.created_at.desc()).offset(offset).limit(page_size)

    result = await session.execute(stmt)
    records = result.scalars().all()

    items = [
        ApprovalItemResponse(
            id=str(r.id),
            alert_id=str(r.alert_id) if r.alert_id else None,
            action_type=r.action_type,
            amount_usd=r.amount_usd,
            spend_tier=r.spend_tier,
            token_hash=r.token_hash,
            approved_by=[str(u) for u in (r.approved_by or [])],
            approved_at=r.approved_at or [],
            status=r.status,
            expires_at=r.expires_at,
            created_at=r.created_at,
        )
        for r in records
    ]

    total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0

    return ApprovalQueueListResponse(
        items=items,
        total=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ------------------------------------------------------------------------------
# 2. Approval Detail: GET /api/v1/approvals/{approval_id}
# ------------------------------------------------------------------------------


@router.get(
    "/api/v1/approvals/{approval_id}",
    response_model=ApprovalItemResponse,
    status_code=status.HTTP_200_OK,
    summary="Get detailed HITL approval record by ID",
)
async def get_approval_detail(
    approval_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(require_role(UserRole.CATEGORY_MANAGER))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[HITLService, Depends(get_hitl_service)],
) -> ApprovalItemResponse:
    """Retrieve an individual HITL approval record with evaluated expiration status."""
    logger.debug("Fetching approval detail '%s' for user '%s'", approval_id, current_user.user_id)
    a_uuid = _parse_uuid(approval_id, "approval_id")

    approval = await service.get_approval(session, a_uuid)
    if approval is None:
        raise NotFoundException(f"HITL approval '{approval_id}' not found.")

    return ApprovalItemResponse(
        id=str(approval.id),
        alert_id=str(approval.alert_id) if approval.alert_id else None,
        action_type=approval.action_type,
        amount_usd=approval.amount_usd,
        spend_tier=approval.spend_tier,
        token_hash=approval.token_hash,
        approved_by=[str(u) for u in (approval.approved_by or [])],
        approved_at=approval.approved_at or [],
        status=approval.status,
        expires_at=approval.expires_at,
        created_at=approval.created_at,
    )


# ------------------------------------------------------------------------------
# 3. Cryptographic Token Submission: POST /api/v1/approvals/{approval_id}/sign
# ------------------------------------------------------------------------------


@router.post(
    "/api/v1/approvals/{approval_id}/sign",
    response_model=ApprovalSignResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit cryptographic KMS ECDSA token signature for HITL approval",
)
@router.post(
    "/api/v1/cases/{approval_id}/approve",
    response_model=ApprovalSignResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def sign_approval(
    approval_id: str,
    payload: ApprovalSignRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_role(UserRole.CATEGORY_MANAGER))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[HITLService, Depends(get_hitl_service)],
) -> ApprovalSignResponse:
    """Apply an authorized cryptographic token signature to a pending approval request.

    Enforces:
    1. Spend authority eligibility matching or exceeding the approval tier:
       - Tier 1 (CATEGORY_MGR <= $25,000): Category Manager+
       - Tier 2 (PROC_DIRECTOR $25,001 - $100,000): Procurement Director+
       - Tier 3 (DUAL_VP > $100,000): Procurement Director or VP Supply Chain
    2. Cryptographic token verification (KMS ECDSA P-256 signature, parameter binding).
    3. Temporal validity: Rejects tokens where TTL has expired.
    4. Anti-replay verification: Checks unique constraint on token_hash, emits security alert if replayed.
    5. Dual-approval logic for Tier 3: First signature moves to PARTIALLY_APPROVED; second distinct moves to APPROVED.
    """
    a_uuid = _parse_uuid(approval_id, "approval_id")
    repo = HITLApprovalRepository(session)

    # 1. Lookup approval record (by ID or by alert_id for case approval alias)
    approval = await repo.get_by_id(a_uuid)
    if approval is None:
        approvals_by_alert = await repo.get_by_alert_id(a_uuid)
        if approvals_by_alert:
            approval = approvals_by_alert[0]
        else:
            raise NotFoundException(f"HITL approval '{approval_id}' not found.")

    # 2. Terminal or invalid state check
    if approval.status not in ("PENDING", "PARTIALLY_APPROVED"):
        raise ConflictException(
            f"Cannot sign approval '{approval.id}' in '{approval.status}' state."
        )

    # 3. Check record expiration
    exp = approval.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=UTC)
    if datetime.now(UTC) > exp:
        approval.status = "EXPIRED"
        await session.commit()
        raise AppException(
            code="TOKEN_EXPIRED",
            message=f"HITL approval '{approval.id}' has expired.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 4. Check signer eligibility for governing spend tier
    if not service.is_eligible_signer(current_user, approval.amount_usd):
        roles_str = ", ".join(current_user.roles)
        raise AuthorizationException(
            f"User role '{roles_str}' lacks required authority to sign approvals for tier "
            f"'{approval.spend_tier}' (amount: ${approval.amount_usd:,.2f})."
        )

    # 5. Delegate cryptographic verification and state transition to HITLService
    try:
        updated_approval = await service.sign_approval(
            session=session,
            approval_id=approval.id,
            token=payload.token,
            signer_id=current_user.user_id,
        )
    except ApprovalNotFoundError as exc:
        raise NotFoundException(str(exc)) from exc
    except InvalidApprovalOperationError as exc:
        raise ConflictException(str(exc)) from exc
    except (TokenReplayServiceError, TokenReplayError, TokenReplayDetectedError) as exc:
        raise AppException(
            code="TOKEN_REPLAY",
            message=f"Cryptographic token replay detected. {exc}",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc
    except UnauthorizedSignerError as exc:
        err_msg = str(exc)
        if "duplicate signer" in err_msg.lower():
            raise AppException(
                code="DUPLICATE_SIGNER",
                message=err_msg,
                status_code=status.HTTP_409_CONFLICT,
            ) from exc
        raise AuthorizationException(err_msg) from exc
    except (TokenExpiredServiceError, TokenExpiredError) as exc:
        raise AppException(
            code="TOKEN_EXPIRED",
            message=f"Token signature has expired: {exc}",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc
    except (TokenBindingMismatchError, TokenVerificationServiceError) as exc:
        err_msg = str(exc).lower()
        if "signature" in err_msg:
            raise AppException(
                code="INVALID_TOKEN_SIGNATURE",
                message=f"Cryptographic signature verification failed: {exc}",
                status_code=status.HTTP_400_BAD_REQUEST,
            ) from exc
        raise AppException(
            code="TOKEN_BINDING_MISMATCH",
            message=f"Token parameter binding mismatch: {exc}",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc
    except TokenSignatureInvalidError as exc:
        raise AppException(
            code="INVALID_TOKEN_SIGNATURE",
            message=f"Cryptographic signature verification failed: {exc}",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc
    except ValueError as exc:
        raise ValidationException(f"Malformed serialized token: {exc}") from exc

    # 6. Audit logging for optional notes
    if payload.notes:
        try:
            await write_audit_log(
                entity_type="HITL_APPROVAL",
                entity_id=updated_approval.id,
                action="APPROVAL_NOTES_ATTACHED",
                actor_id=current_user.user_id,
                after_state={"notes": payload.notes, "status": updated_approval.status},
            )
        except Exception as exc:
            logger.warning(
                "Audit write failed for approval notes on %s: %s", updated_approval.id, exc
            )

    # 7. Formulate human-readable message
    if updated_approval.status == "APPROVED":
        msg = f"Approval {updated_approval.id} fully authorized and committed ({updated_approval.spend_tier})."
    elif updated_approval.status == "PARTIALLY_APPROVED":
        msg = (
            f"Primary executive signature recorded for approval {updated_approval.id}. "
            "Awaiting secondary executive signature (Tier 3 DUAL_VP)."
        )
    else:
        msg = f"Approval status updated to {updated_approval.status}."

    return ApprovalSignResponse(
        id=str(updated_approval.id),
        status=updated_approval.status,
        action_type=updated_approval.action_type,
        amount_usd=updated_approval.amount_usd,
        spend_tier=updated_approval.spend_tier,
        approved_by=[str(u) for u in (updated_approval.approved_by or [])],
        approved_at=updated_approval.approved_at or [],
        message=msg,
    )


# ------------------------------------------------------------------------------
# 4. Reject Approval: POST /api/v1/approvals/{approval_id}/reject
# ------------------------------------------------------------------------------


@router.post(
    "/api/v1/approvals/{approval_id}/reject",
    response_model=ApprovalRejectResponse,
    status_code=status.HTTP_200_OK,
    summary="Reject a pending HITL approval request",
)
async def reject_approval(
    approval_id: str,
    payload: ApprovalRejectRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_role(UserRole.CATEGORY_MANAGER))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[HITLService, Depends(get_hitl_service)],
) -> ApprovalRejectResponse:
    """Reject an active approval request with recorded justification notes."""
    a_uuid = _parse_uuid(approval_id, "approval_id")

    try:
        rejected = await service.reject_approval(
            session=session,
            approval_id=a_uuid,
            reason=payload.reason,
            actor_id=current_user.user_id,
        )
    except ApprovalNotFoundError as exc:
        raise NotFoundException(str(exc)) from exc

    return ApprovalRejectResponse(
        id=str(rejected.id),
        status=rejected.status,
        message=f"Approval {rejected.id} rejected: {payload.reason}",
    )
