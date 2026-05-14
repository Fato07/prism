-- Migration 003: Create treasury_events table
-- Required by VAL-MIGRATION-TREASURY-001..005: USYC park/unpark tracking for trader treasury module
-- Idempotent (CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS treasury_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        INTEGER NOT NULL,
    wallet_address  TEXT NOT NULL,
    event_type      TEXT NOT NULL CHECK (event_type IN ('park', 'unpark')),
    usdc_amount     NUMERIC(20, 6),
    usyc_amount     NUMERIC(20, 6),
    rationale       TEXT,
    tx_hash         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS treasury_events_agent_created_idx
    ON treasury_events (agent_id, created_at DESC);

COMMENT ON TABLE treasury_events IS 'Tracks USDC→USYC park and USYC→USDC unpark operations performed by the trader treasury module.';
COMMENT ON COLUMN treasury_events.event_type IS 'Operation type: park (USDC→USYC) or unpark (USYC→USDC).';
COMMENT ON COLUMN treasury_events.usdc_amount IS 'Amount of USDC moved (park: deposited, unpark: received after redeem).';
COMMENT ON COLUMN treasury_events.usyc_amount IS 'Amount of USYC received (park) or redeemed (unpark).';
COMMENT ON COLUMN treasury_events.tx_hash IS 'On-chain transaction hash on Arc Testnet. NULL when dry_run mode is active.';
COMMENT ON COLUMN treasury_events.rationale IS 'Human-readable reason for the treasury operation. Ends with (dry_run) in dry-run mode.';
