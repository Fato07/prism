-- Migration 001: Add fill_price column to trades table
-- Required by VAL-TRACE-016: Trade outcome block renders fill_price
-- Idempotent (ADD COLUMN IF NOT EXISTS).

ALTER TABLE trades ADD COLUMN IF NOT EXISTS fill_price NUMERIC;

COMMENT ON COLUMN trades.fill_price IS 'Fill price per share (0..1 for binary markets). NULL until order fills.';
