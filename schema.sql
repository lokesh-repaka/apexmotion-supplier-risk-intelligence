-- ==============================================================================
-- ApexMotion Supplier Risk Intelligence Platform — Aurora PostgreSQL Schema DDL
-- Operational Database Schema Baseline
-- Reference: CLAUDE.md Section 9 & LLD Section 3.1
-- ==============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ------------------------------------------------------------------------------
-- 1. Table: suppliers (Master Supplier Directory)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS suppliers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    country_code    CHAR(2) NOT NULL,
    tier            INT NOT NULL CHECK (tier BETWEEN 1 AND 3),
    risk_score      NUMERIC(4,3) CHECK (risk_score BETWEEN 0.0 AND 1.0),
    neptune_node_id TEXT UNIQUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_suppliers_tier_country ON suppliers (tier, country_code);
CREATE INDEX IF NOT EXISTS idx_suppliers_neptune_node ON suppliers (neptune_node_id);

-- ------------------------------------------------------------------------------
-- 2. Table: risk_alerts (Calculated Disruption Signals & Exposures)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS risk_alerts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supplier_id         UUID REFERENCES suppliers(id) ON DELETE SET NULL,
    component_sku       TEXT NOT NULL,
    risk_level          TEXT NOT NULL CHECK (risk_level IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')),
    days_of_cover       NUMERIC(8,2),
    financial_exposure  NUMERIC(14,2),
    shortage_volume     INT,
    status              TEXT NOT NULL DEFAULT 'OPEN',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_risk_alerts_supplier ON risk_alerts (supplier_id);
CREATE INDEX IF NOT EXISTS idx_risk_alerts_component_sku ON risk_alerts (component_sku);
CREATE INDEX IF NOT EXISTS idx_risk_alerts_status_level ON risk_alerts (status, risk_level);
CREATE INDEX IF NOT EXISTS idx_risk_alerts_created_at ON risk_alerts (created_at DESC);

-- ------------------------------------------------------------------------------
-- 3. Table: hitl_approvals (Cryptographic Spend Authorizations)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hitl_approvals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_id        UUID REFERENCES risk_alerts(id) ON DELETE SET NULL,
    action_type     TEXT NOT NULL,
    amount_usd      NUMERIC(14,2) NOT NULL,
    spend_tier      TEXT NOT NULL CHECK (spend_tier IN ('CATEGORY_MGR', 'PROC_DIRECTOR', 'DUAL_VP')),
    token_hash      TEXT NOT NULL UNIQUE,
    approved_by     UUID[],
    approved_at     TIMESTAMPTZ[],
    status          TEXT NOT NULL DEFAULT 'PENDING',
    expires_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_hitl_approvals_alert ON hitl_approvals (alert_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_hitl_approvals_token_hash ON hitl_approvals (token_hash);
CREATE INDEX IF NOT EXISTS idx_hitl_approvals_status_expires ON hitl_approvals (status, expires_at);

-- ------------------------------------------------------------------------------
-- 4. Table: audit_logs (Forensic Immutable Audit Trail - BR-RULE-007)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_logs (
    id              BIGSERIAL PRIMARY KEY,
    entity_type     TEXT NOT NULL,
    entity_id       UUID NOT NULL,
    action          TEXT NOT NULL,
    actor_id        UUID NOT NULL,
    before_state    JSONB,
    after_state     JSONB,
    trace_id        TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_entity ON audit_logs (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor ON audit_logs (actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_trace_id ON audit_logs (trace_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs (created_at DESC);

-- Append-Only Invariant: Block UPDATE and DELETE on audit_logs
CREATE OR REPLACE FUNCTION enforce_audit_logs_append_only()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs is append-only. UPDATE and DELETE operations are strictly prohibited (BR-RULE-007).';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_logs_append_only ON audit_logs;
CREATE TRIGGER trg_audit_logs_append_only
BEFORE UPDATE OR DELETE ON audit_logs
FOR EACH ROW
EXECUTE FUNCTION enforce_audit_logs_append_only();

-- ------------------------------------------------------------------------------
-- 5. Table: agent_runs (LangGraph Multi-Agent Execution Telemetry)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_id            UUID REFERENCES risk_alerts(id) ON DELETE SET NULL,
    graph_name          TEXT NOT NULL,
    status              TEXT NOT NULL CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
    langfuse_trace_id   TEXT,
    tokens_used         INT,
    cost_usd            NUMERIC(8,4),
    duration_ms         INT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_alert ON agent_runs (alert_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_langfuse_trace ON agent_runs (langfuse_trace_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_created_at ON agent_runs (created_at DESC);
