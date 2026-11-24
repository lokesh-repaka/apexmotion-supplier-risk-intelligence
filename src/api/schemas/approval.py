"""Pydantic v2 schemas for Human-in-the-Loop (HITL) approval API routes (P11-3).

Enforces:
- The Triad of Responsibility (BR-RULE-001):
  * Monetary precision using Decimal (NUMERIC(14,2)); native float arithmetic is strictly forbidden.
  * Explicit spend governance tier routing: CATEGORY_MGR, PROC_DIRECTOR, DUAL_VP.
- Cryptographic Token Signatures:
  * Strict schema validation for serialized AWS KMS ECDSA P-256 tokens.
- Strict Pydantic v2 validation with extra="forbid".
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ApprovalItemResponse(BaseModel):
    """Detailed response representation of an individual HITL approval item."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="HITL approval record UUID")
    alert_id: str | None = Field(default=None, description="Associated risk alert UUID")
    action_type: str = Field(
        description="Mitigation action type (e.g. LOGISTICS_EXPEDITE, SECONDARY_SOURCE)"
    )
    amount_usd: Decimal = Field(
        description="Authorized monetary spend commitment in USD (NUMERIC(14,2))"
    )
    spend_tier: str = Field(
        description="Governing spend tier authority: CATEGORY_MGR, PROC_DIRECTOR, DUAL_VP"
    )
    token_hash: str = Field(description="Cryptographic SHA-256 hash of the KMS ECDSA P-256 token")
    approved_by: list[str] = Field(
        default_factory=list,
        description="List of approving user UUID strings",
    )
    approved_at: list[datetime] = Field(
        default_factory=list,
        description="List of approval timestamps corresponding to signers",
    )
    status: str = Field(
        description="Approval workflow status: PENDING, PARTIALLY_APPROVED, APPROVED, REJECTED, EXPIRED"
    )
    expires_at: datetime = Field(
        description="UTC timestamp when the approval authorization token expires"
    )
    created_at: datetime = Field(description="UTC timestamp when the approval record was created")


class ApprovalQueueListResponse(BaseModel):
    """Paginated collection of HITL approval queue items."""

    model_config = ConfigDict(extra="forbid")

    items: list[ApprovalItemResponse] = Field(
        description="List of approval items matching filter criteria"
    )
    total: int = Field(ge=0, description="Total number of matching approval records")
    page: int = Field(ge=1, description="Current page number (1-indexed)")
    page_size: int = Field(ge=1, le=100, description="Page size limit")
    total_pages: int = Field(ge=0, description="Total number of pages available")


class ApprovalSignRequest(BaseModel):
    """Request payload submitting a cryptographically signed KMS ECDSA token."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(
        ...,
        min_length=10,
        max_length=10000,
        description="Serialized URL-safe Base64 KMS ECDSA P-256 approval token string",
    )
    notes: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional justification notes or audit rationale for authorization",
    )


class ApprovalSignResponse(BaseModel):
    """Response returned upon successful processing of an approval signature."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="HITL approval record UUID")
    status: str = Field(
        description="Updated approval workflow state: PARTIALLY_APPROVED or APPROVED"
    )
    action_type: str = Field(description="Mitigation action type")
    amount_usd: Decimal = Field(description="Authorized monetary commitment in USD")
    spend_tier: str = Field(description="Governing spend tier authority")
    approved_by: list[str] = Field(
        default_factory=list,
        description="List of approving user UUID strings",
    )
    approved_at: list[datetime] = Field(
        default_factory=list,
        description="List of approval timestamps",
    )
    message: str = Field(description="Human-readable status summary")


class ApprovalRejectRequest(BaseModel):
    """Request payload for rejecting an active HITL approval request."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Mandatory justification or rationale for rejection",
    )


class ApprovalRejectResponse(BaseModel):
    """Response returned upon successful rejection of an approval request."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="HITL approval record UUID")
    status: str = Field(default="REJECTED", description="Approval workflow status: REJECTED")
    message: str = Field(description="Human-readable status summary")
