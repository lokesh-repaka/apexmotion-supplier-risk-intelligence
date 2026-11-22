"""Asynchronous repository for HITLApproval domain entities and cryptographic anti-replay verification."""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import HITLApproval
from src.database.repositories.base import BaseRepository


class TokenReplayError(Exception):
    """Raised when an approval token hash has already been used (cryptographic replay attack)."""


class HITLApprovalRepository(BaseRepository[HITLApproval]):
    """Repository managing HITLApproval persistence and cryptographic verification."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model_cls=HITLApproval)

    async def get_by_token_hash(self, token_hash: str) -> HITLApproval | None:
        """Fetch approval by cryptographic token hash for anti-replay verification."""
        stmt = select(HITLApproval).where(HITLApproval.token_hash == token_hash)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def is_token_used(self, token_hash: str) -> bool:
        """Check if a token hash has already been registered in hitl_approvals."""
        approval = await self.get_by_token_hash(token_hash)
        return approval is not None

    async def create_approval(self, approval: HITLApproval) -> HITLApproval:
        """Create an approval while enforcing cryptographic anti-replay validation.

        Raises:
            TokenReplayError: If the token_hash was already used in a previous approval.
        """
        if await self.is_token_used(approval.token_hash):
            raise TokenReplayError(f"Replay detected for token hash: {approval.token_hash}")

        try:
            return await self.create(approval)
        except IntegrityError as exc:
            await self.session.rollback()
            raise TokenReplayError(
                f"Replay detected for token hash: {approval.token_hash}"
            ) from exc

    async def get_by_alert_id(self, alert_id: UUID) -> Sequence[HITLApproval]:
        """Fetch approvals triggered by an incident alert."""
        stmt = (
            select(HITLApproval)
            .where(HITLApproval.alert_id == alert_id)
            .order_by(HITLApproval.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_pending_approvals(self, limit: int = 100) -> Sequence[HITLApproval]:
        """Fetch pending approvals requiring human authority action."""
        stmt = (
            select(HITLApproval)
            .where(HITLApproval.status == "PENDING")
            .order_by(HITLApproval.created_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_spend_tier(self, spend_tier: str, limit: int = 100) -> Sequence[HITLApproval]:
        """Fetch approvals categorized by spend governance tier."""
        stmt = (
            select(HITLApproval)
            .where(HITLApproval.spend_tier == spend_tier.upper())
            .order_by(HITLApproval.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def record_signature(
        self,
        approval_id: UUID,
        signer_id: UUID,
        new_status: str = "APPROVED",
    ) -> HITLApproval | None:
        """Record an authorized signature and update approval workflow state."""
        approval = await self.get_by_id(approval_id)
        if approval is None:
            return None

        current_signers = list(approval.approved_by or [])
        current_signers.append(signer_id)
        approval.approved_by = current_signers

        current_times = list(approval.approved_at or [])
        current_times.append(datetime.now(UTC))
        approval.approved_at = current_times

        approval.status = new_status.upper()
        return await self.update(approval)

    async def reject_approval(self, approval_id: UUID, rejecter_id: UUID) -> HITLApproval | None:
        """Mark approval rejected by authorized user and record rejection actor."""
        approval = await self.get_by_id(approval_id)
        if approval is None:
            return None
        current_actors = list(approval.approved_by or [])
        current_actors.append(rejecter_id)
        approval.approved_by = current_actors

        current_times = list(approval.approved_at or [])
        current_times.append(datetime.now(UTC))
        approval.approved_at = current_times

        approval.status = "REJECTED"
        return await self.update(approval)
