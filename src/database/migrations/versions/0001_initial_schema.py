"""Baseline initial relational schema for Aurora PostgreSQL.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-21 22:30:00.000000

Creates the 5 core operational tables:
- suppliers
- risk_alerts
- hitl_approvals
- audit_logs
- agent_runs
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --------------------------------------------------------------------------
    # 1. Table: suppliers
    # --------------------------------------------------------------------------
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("tier", sa.Integer(), nullable=False),
        sa.Column("risk_score", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("neptune_node_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("tier >= 1 AND tier <= 3", name="check_supplier_tier"),
        sa.CheckConstraint(
            "risk_score >= 0.0 AND risk_score <= 1.0", name="check_supplier_risk_score"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("neptune_node_id"),
    )
    op.create_index("idx_suppliers_neptune_node", "suppliers", ["neptune_node_id"])

    # --------------------------------------------------------------------------
    # 2. Table: risk_alerts
    # --------------------------------------------------------------------------
    op.create_table(
        "risk_alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=True),
        sa.Column("component_sku", sa.String(length=100), nullable=False),
        sa.Column("risk_level", sa.String(length=20), nullable=False),
        sa.Column("days_of_cover", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("financial_exposure", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("shortage_volume", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="OPEN"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "risk_level IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')",
            name="check_risk_alert_level",
        ),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_risk_alerts_supplier", "risk_alerts", ["supplier_id"])
    op.create_index("idx_risk_alerts_component_sku", "risk_alerts", ["component_sku"])

    # --------------------------------------------------------------------------
    # 3. Table: hitl_approvals
    # --------------------------------------------------------------------------
    op.create_table(
        "hitl_approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("alert_id", sa.Uuid(), nullable=True),
        sa.Column("action_type", sa.String(length=50), nullable=False),
        sa.Column("amount_usd", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("spend_tier", sa.String(length=30), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("approved_by", postgresql.ARRAY(sa.Uuid()), nullable=True),
        sa.Column("approved_at", postgresql.ARRAY(sa.DateTime(timezone=True)), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="PENDING"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "spend_tier IN ('CATEGORY_MGR', 'PROC_DIRECTOR', 'DUAL_VP')",
            name="check_spend_tier",
        ),
        sa.ForeignKeyConstraint(["alert_id"], ["risk_alerts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("idx_hitl_approvals_alert", "hitl_approvals", ["alert_id"])
    op.create_index("idx_hitl_approvals_token_hash", "hitl_approvals", ["token_hash"], unique=True)

    # --------------------------------------------------------------------------
    # 4. Table: audit_logs (Append-Only)
    # --------------------------------------------------------------------------
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("before_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"])
    op.create_index("idx_audit_logs_actor", "audit_logs", ["actor_id"])
    op.create_index("idx_audit_logs_trace_id", "audit_logs", ["trace_id"])

    # --------------------------------------------------------------------------
    # 5. Table: agent_runs
    # --------------------------------------------------------------------------
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("alert_id", sa.Uuid(), nullable=True),
        sa.Column("graph_name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("langfuse_trace_id", sa.String(length=128), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'COMPLETED', 'FAILED')",
            name="check_agent_run_status",
        ),
        sa.ForeignKeyConstraint(["alert_id"], ["risk_alerts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_agent_runs_alert", "agent_runs", ["alert_id"])
    op.create_index("idx_agent_runs_langfuse_trace", "agent_runs", ["langfuse_trace_id"])


def downgrade() -> None:
    op.drop_table("agent_runs")
    op.drop_table("audit_logs")
    op.drop_table("hitl_approvals")
    op.drop_table("risk_alerts")
    op.drop_table("suppliers")
