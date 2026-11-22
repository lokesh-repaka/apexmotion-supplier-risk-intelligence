"""SQLAlchemy 2.0 async relational models for Aurora PostgreSQL.

Defines the 5 core operational tables specified in CLAUDE.md Section 9:
- Supplier (suppliers): Master supplier records with tier, risk score, and Neptune graph pointer.
- RiskAlert (risk_alerts): Real-time calculated risk alerts with deterministic metrics.
- HITLApproval (hitl_approvals): Consequential spend authorization records gated by KMS ECDSA tokens.
- AuditLog (audit_logs): Immutable, append-only forensic audit trail (BR-RULE-007).
- AgentRun (agent_runs): LangGraph execution telemetry, token usage, and Langfuse trace links.

Enforces:
- The Triad of Responsibility: All monetary values use Numeric(14,2) / Decimal.
- Anti-Replay: hitl_approvals.token_hash unique index prevents token reuse.
- Append-Only Invariant: audit_logs rejects UPDATE and DELETE operations.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    event,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    """Base declarative class for all ApexMotion relational models."""

    pass


class Supplier(Base):
    """Master supplier entity record.

    Maps to the `suppliers` table in Aurora PostgreSQL. Corresponds to nodes
    in the Amazon Neptune Knowledge Graph via `neptune_node_id`.
    """

    __tablename__ = "suppliers"
    __table_args__ = (
        CheckConstraint("tier >= 1 AND tier <= 3", name="check_supplier_tier"),
        CheckConstraint(
            "risk_score >= 0.0 AND risk_score <= 1.0",
            name="check_supplier_risk_score",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key UUID",
    )
    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Legal registered name of the supplier",
    )
    country_code: Mapped[str] = mapped_column(
        String(2),
        nullable=False,
        doc="ISO 3166-1 alpha-2 country code",
    )
    tier: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Supplier supply-chain tier: 1 (Direct), 2 (Sub-tier), or 3 (Raw materials)",
    )
    risk_score: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 3),
        nullable=True,
        doc="Composite supplier risk score between 0.000 and 1.000",
    )
    neptune_node_id: Mapped[str | None] = mapped_column(
        String(128),
        unique=True,
        index=True,
        nullable=True,
        doc="Unique identifier for corresponding Amazon Neptune node",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        doc="Timestamp of supplier creation",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
        doc="Timestamp of last supplier record update",
    )

    # Relationships
    alerts: Mapped[list["RiskAlert"]] = relationship(
        "RiskAlert",
        back_populates="supplier",
        cascade="all, delete-orphan",
        doc="Risk alerts associated with this supplier",
    )


class RiskAlert(Base):
    """Calculated supplier risk alert.

    Maps to `risk_alerts`. Populated by the streaming triage and risk engine.
    Holds deterministic inventory coverage and financial exposure metrics.
    """

    __tablename__ = "risk_alerts"
    __table_args__ = (
        CheckConstraint(
            "risk_level IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')",
            name="check_risk_alert_level",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key UUID",
    )
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Foreign key referencing disrupted supplier",
    )
    component_sku: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        doc="Impacted component SKU / Part number",
    )
    risk_level: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        doc="Assigned severity level: CRITICAL, HIGH, MEDIUM, LOW",
    )
    days_of_cover: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 2),
        nullable=True,
        doc="Deterministic days of inventory remaining (current_stock / daily_consumption)",
    )
    financial_exposure: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
        doc="Total plant downtime and shortage financial exposure in USD",
    )
    shortage_volume: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        doc="Projected component unit shortage volume",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="OPEN",
        nullable=False,
        doc="Alert lifecycle status: OPEN, INVESTIGATING, MITIGATED, RESOLVED",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        doc="Alert creation timestamp",
    )

    # Relationships
    supplier: Mapped[Supplier | None] = relationship(
        "Supplier",
        back_populates="alerts",
    )
    approvals: Mapped[list["HITLApproval"]] = relationship(
        "HITLApproval",
        back_populates="alert",
        cascade="all, delete-orphan",
    )
    agent_runs: Mapped[list["AgentRun"]] = relationship(
        "AgentRun",
        back_populates="alert",
        cascade="all, delete-orphan",
    )


class HITLApproval(Base):
    """Human-in-the-Loop spend authorization.

    Maps to `hitl_approvals`. Gated cryptographically by AWS KMS ECDSA P-256 tokens.
    Enforces spend thresholds (Category Mgr <= $25k, Director <= $100k, Dual VP > $100k).
    """

    __tablename__ = "hitl_approvals"
    __table_args__ = (
        CheckConstraint(
            "spend_tier IN ('CATEGORY_MGR', 'PROC_DIRECTOR', 'DUAL_VP')",
            name="check_spend_tier",
        ),
        Index("idx_hitl_approvals_token_hash", "token_hash", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key UUID",
    )
    alert_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("risk_alerts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Foreign key referencing associated risk alert",
    )
    action_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="Approved mitigation action type (e.g., LOGISTICS_EXPEDITE, SECONDARY_SOURCE)",
    )
    amount_usd: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        doc="Authorized spend commitment in USD",
    )
    spend_tier: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        doc="Spend tier authority: CATEGORY_MGR, PROC_DIRECTOR, DUAL_VP",
    )
    token_hash: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
        doc="SHA-256 hash of the KMS ECDSA P-256 signature token (anti-replay)",
    )
    approved_by: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(Uuid(as_uuid=True)).with_variant(JSON, "sqlite"),
        nullable=True,
        doc="List of approving user UUIDs (1 for standard, 2 for dual sign-off)",
    )
    approved_at: Mapped[list[datetime] | None] = mapped_column(
        ARRAY(DateTime(timezone=True)).with_variant(JSON, "sqlite"),
        nullable=True,
        doc="List of approval timestamps corresponding to signers",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="PENDING",
        nullable=False,
        doc="Approval status: PENDING, APPROVED, REJECTED, EXPIRED",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        doc="Token expiration timestamp (1-hr TTL for single, 30-min for dual)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        doc="Approval request creation timestamp",
    )

    # Relationships
    alert: Mapped[RiskAlert | None] = relationship(
        "RiskAlert",
        back_populates="approvals",
    )


class AuditLog(Base):
    """Forensic immutable audit log.

    Maps to `audit_logs`. Strictly append-only (BR-RULE-007).
    No UPDATE or DELETE operations are permitted on this table.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
        doc="Autoincrementing monotonic audit log ID",
    )
    entity_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="Target entity table or domain (e.g. risk_alerts, hitl_approvals)",
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
        doc="UUID of the modified entity",
    )
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="Action executed (e.g. CREATE, SIGN_APPROVAL, DISPATCH_PO)",
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
        doc="User or system service UUID executing the action",
    )
    before_state: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"),
        nullable=True,
        doc="State payload before modification",
    )
    after_state: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"),
        nullable=True,
        doc="State payload after modification",
    )
    trace_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        doc="Distributed request trace ID for cross-service observability",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        doc="Immutable creation timestamp",
    )

    def prevent_mutation(self, operation: str) -> None:
        """Enforce append-only invariant on AuditLog instances."""
        raise RuntimeError(
            f"audit_logs is append-only. {operation} operations are strictly prohibited."
        )


# ==============================================================================
# Append-Only Enforcement Hooks for AuditLog
# ==============================================================================
@event.listens_for(AuditLog, "before_update")
def _audit_log_before_update(_mapper: Any, _connection: Any, target: AuditLog) -> None:
    target.prevent_mutation("UPDATE")


@event.listens_for(AuditLog, "before_delete")
def _audit_log_before_delete(_mapper: Any, _connection: Any, target: AuditLog) -> None:
    target.prevent_mutation("DELETE")


class AgentRun(Base):
    """LangGraph execution telemetry record.

    Maps to `agent_runs`. Records multi-agent graph executions, token costs,
    durations, and Langfuse trace identifiers.
    """

    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('RUNNING', 'COMPLETED', 'FAILED')",
            name="check_agent_run_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key UUID",
    )
    alert_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("risk_alerts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Foreign key referencing associated risk alert",
    )
    graph_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Name of executed LangGraph state machine (e.g. incident_investigation_graph)",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        doc="Execution status: RUNNING, COMPLETED, FAILED",
    )
    langfuse_trace_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
        doc="External Langfuse trace identifier for LLM observability",
    )
    tokens_used: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        doc="Total LLM tokens consumed across all agent steps",
    )
    cost_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 4),
        nullable=True,
        doc="Calculated LLM inference cost in USD",
    )
    duration_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        doc="Total graph execution runtime in milliseconds",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        doc="Agent run start timestamp",
    )

    # Relationships
    alert: Mapped[RiskAlert | None] = relationship(
        "RiskAlert",
        back_populates="agent_runs",
    )
