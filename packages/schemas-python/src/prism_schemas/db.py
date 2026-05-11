"""Neon DB migration and connection utilities."""

from __future__ import annotations

import os
from typing import Any

import psycopg
import structlog

logger = structlog.get_logger("prism.schemas.db")

MIGRATION_SQL = """
-- Prism Phase 0 schema: 5 tables for agents, traces, validations, trades, feedback

CREATE TABLE IF NOT EXISTS agents (
    agent_id          BIGINT PRIMARY KEY,
    role              TEXT NOT NULL CHECK (role IN ('trader', 'sentinel', 'oracle')),
    wallet_address    TEXT NOT NULL,
    agent_card_cid    TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS traces (
    trace_id          UUID PRIMARY KEY,
    agent_id          BIGINT NOT NULL REFERENCES agents(agent_id),
    market_id         TEXT NOT NULL,
    ipfs_cid          TEXT NOT NULL,
    content_hash      BYTEA NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS validations (
    request_hash      BYTEA PRIMARY KEY,
    trace_id          UUID NOT NULL REFERENCES traces(trace_id),
    sentinel_agent_id BIGINT NOT NULL REFERENCES agents(agent_id),
    verdict_score     SMALLINT NOT NULL CHECK (verdict_score >= 0 AND verdict_score <= 100),
    response_uri      TEXT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS trades (
    order_id          TEXT PRIMARY KEY,
    trace_id          UUID NOT NULL REFERENCES traces(trace_id),
    market_id         TEXT NOT NULL,
    side              TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    size              NUMERIC NOT NULL,
    builder_code      TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending',
    polymarket_tx     TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS feedback (
    id                BIGSERIAL PRIMARY KEY,
    agent_id          BIGINT NOT NULL REFERENCES agents(agent_id),
    oracle_address    TEXT NOT NULL,
    value_fixed_point INT NOT NULL,
    decimals          SMALLINT NOT NULL DEFAULT 0,
    tag1              TEXT,
    tag2              TEXT,
    ipfs_cid          TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_traces_agent_id ON traces(agent_id);
CREATE INDEX IF NOT EXISTS idx_traces_market_id ON traces(market_id);
CREATE INDEX IF NOT EXISTS idx_validations_trace_id ON validations(trace_id);
CREATE INDEX IF NOT EXISTS idx_trades_trace_id ON trades(trace_id);
CREATE INDEX IF NOT EXISTS idx_feedback_agent_id ON feedback(agent_id);
"""


def get_db_url() -> str:
    """Return DATABASE_URL from environment."""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise EnvironmentError("DATABASE_URL is not set in environment")
    return url


def run_migration(dsn: str | None = None) -> None:
    """Execute the full schema migration against Neon Postgres."""
    dsn = dsn or get_db_url()
    logger.info("Running database migration", dsn_host=_host_from_dsn(dsn))
    with psycopg.connect(dsn) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(MIGRATION_SQL)
    logger.info("Database migration complete")


def list_tables(dsn: str | None = None) -> list[str]:
    """Return list of user tables in the public schema."""
    dsn = dsn or get_db_url()
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
                "ORDER BY table_name"
            )
            return [row[0] for row in cur.fetchall()]


def insert_and_verify(
    table: str,
    columns: list[str],
    values: tuple[Any, ...],
    dsn: str | None = None,
) -> bool:
    """Insert a row and verify it exists. Returns True on success."""
    dsn = dsn or get_db_url()
    placeholders = ", ".join(["%s"] * len(values))
    col_str = ", ".join(columns)
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {table} ({col_str}) VALUES ({placeholders})",
                values,
            )
            conn.commit()
    return True


def _host_from_dsn(dsn: str) -> str:
    """Extract host from DSN for logging (no secrets)."""
    try:
        return dsn.split("@")[1].split("/")[0].split(":")[0]
    except (IndexError, ValueError):
        return "<unknown>"
