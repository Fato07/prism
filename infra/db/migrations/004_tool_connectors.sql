-- Migration 004: Create tool_connectors table
-- Connector Passport v1: MCP-first evidence connector registry for Prism.
-- Idempotent (CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS tool_connectors (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_scope              TEXT NOT NULL DEFAULT 'workspace' CHECK (owner_scope IN ('workspace')),
    connector_kind           TEXT NOT NULL DEFAULT 'evidence' CHECK (connector_kind IN ('evidence')),
    name                     TEXT NOT NULL,
    transport                TEXT NOT NULL CHECK (transport IN ('mcp_http', 'x402_http', 'custom_webhook', 'direct_adapter')),
    provider                 TEXT NOT NULL DEFAULT 'mcp',
    server_url               TEXT,
    tool_name                TEXT,
    input_mapper             TEXT NOT NULL DEFAULT 'query',
    result_mapper            TEXT NOT NULL DEFAULT 'generic_search',
    allowed_tools            TEXT[] NOT NULL DEFAULT '{}',
    timeout_seconds          NUMERIC(8, 3) NOT NULL DEFAULT 20.0 CHECK (timeout_seconds > 0),
    max_results              INTEGER NOT NULL DEFAULT 5 CHECK (max_results >= 1 AND max_results <= 20),
    max_usdc                 NUMERIC(20, 6),
    auth_secret_ciphertext   TEXT,
    auth_secret_hint         TEXT,
    smoke_status             TEXT NOT NULL DEFAULT 'not_run' CHECK (smoke_status IN ('not_run', 'passed', 'failed')),
    smoke_receipt            JSONB,
    armed                    BOOLEAN NOT NULL DEFAULT FALSE,
    fail_closed              BOOLEAN NOT NULL DEFAULT TRUE,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS tool_connectors_kind_created_idx
    ON tool_connectors (connector_kind, created_at DESC);

CREATE INDEX IF NOT EXISTS tool_connectors_transport_idx
    ON tool_connectors (transport);

CREATE UNIQUE INDEX IF NOT EXISTS tool_connectors_one_armed_per_kind_idx
    ON tool_connectors (connector_kind)
    WHERE armed;

COMMENT ON TABLE tool_connectors IS 'Connector Passport v1 registry for MCP-first Prism evidence connectors.';
COMMENT ON COLUMN tool_connectors.owner_scope IS 'Single-workspace scope in v1. Kept explicit so future hosted multi-tenant migration is additive.';
COMMENT ON COLUMN tool_connectors.connector_kind IS 'Connector purpose. v1 supports evidence connectors only.';
COMMENT ON COLUMN tool_connectors.transport IS 'Transport family: MCP HTTP first, x402/custom-webhook/direct adapters as controlled extensions.';
COMMENT ON COLUMN tool_connectors.server_url IS 'Connector endpoint URL. Redact in public/UI APIs if it may disclose private infrastructure.';
COMMENT ON COLUMN tool_connectors.auth_secret_ciphertext IS 'Encrypted bearer/API token blob. Never expose through dashboard, MCP tools, logs, receipts, or pinned artifacts.';
COMMENT ON COLUMN tool_connectors.auth_secret_hint IS 'Non-secret operator hint such as last four characters or token label.';
COMMENT ON COLUMN tool_connectors.smoke_receipt IS 'Redacted JSON smoke proof: transport/schema/mapper/fail-closed/cost-cap checks.';
COMMENT ON COLUMN tool_connectors.armed IS 'Only armed connectors may be used by sentinel resolution; unique partial index enforces one armed connector per kind.';
COMMENT ON COLUMN tool_connectors.fail_closed IS 'If true, connector failure produces no evidence and leaves sentinel issues unresolved.';
