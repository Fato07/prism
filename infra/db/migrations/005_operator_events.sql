-- Migration 005: Create operator_events table
-- Required by VAL-AUDIT-001..003: operator audit log for scheduler start/stop/update_interval actions.
-- Idempotent (CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS operator_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor       TEXT NOT NULL,
    action      TEXT NOT NULL CHECK (action IN ('start_scheduler', 'stop_scheduler', 'update_interval')),
    old_state   JSONB,
    new_state   JSONB,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    result      TEXT NOT NULL CHECK (result IN ('success', 'failure', 'unauthorized')),
    error       TEXT
);

CREATE INDEX IF NOT EXISTS operator_events_timestamp_idx
    ON operator_events (timestamp DESC);

CREATE INDEX IF NOT EXISTS operator_events_action_idx
    ON operator_events (action);

COMMENT ON TABLE operator_events IS 'Append-only audit log of operator actions against the trader scheduler. Every mutation attempt (success, failure, or unauthorized) writes a row. No UPDATE or DELETE is ever issued by application code.';

COMMENT ON COLUMN operator_events.id IS 'Auto-generated UUID primary key.';

COMMENT ON COLUMN operator_events.actor IS 'Label identifying who initiated the action (operator_admin, unknown, system). Never contains the actual auth token.';

COMMENT ON COLUMN operator_events.action IS 'Operator action performed: start_scheduler, stop_scheduler, or update_interval. Enforced by CHECK constraint.';

COMMENT ON COLUMN operator_events.old_state IS 'JSONB snapshot of scheduler state before the action (e.g. {"scheduler_running": false}). NULL when prior state is unknown.';

COMMENT ON COLUMN operator_events.new_state IS 'JSONB snapshot of scheduler state after the action (e.g. {"scheduler_running": true, "interval_minutes": 5}). NULL when action did not complete.';

COMMENT ON COLUMN operator_events.timestamp IS 'UTC timestamp of when the action was initiated. Defaults to NOW() at row insertion.';

COMMENT ON COLUMN operator_events.result IS 'Outcome of the action: success, failure (trader unreachable or internal error), or unauthorized (missing/invalid token). Enforced by CHECK constraint.';

COMMENT ON COLUMN operator_events.error IS 'Human-readable error message when result is failure or unauthorized. NULL on success.';
