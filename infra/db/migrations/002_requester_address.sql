-- Migration 002: Add requester_address column to validations table
-- Required by VAL-MIGRATION-REQADDR-001..005: self-serve x402 payer capture
-- Idempotent (ADD COLUMN IF NOT EXISTS, CREATE INDEX IF NOT EXISTS).

ALTER TABLE validations ADD COLUMN IF NOT EXISTS requester_address TEXT;

CREATE INDEX IF NOT EXISTS validations_requester_idx ON validations (requester_address);

COMMENT ON COLUMN validations.requester_address IS 'Wallet address of the external requester who paid for this validation via x402. NULL for internal (trader-initiated) validations.';
