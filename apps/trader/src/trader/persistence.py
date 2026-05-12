"""Neon DB persistence for trading traces.

Handles inserting traces into the Neon ``traces`` table and ensuring
the corresponding agent row exists.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import psycopg
import structlog

if TYPE_CHECKING:
    from prism_schemas.trace import TradingR1Trace

logger = structlog.get_logger("prism.trader.persistence")

# Default agent_id for the trader (overridden by TRADER_AGENT_ID env var).
DEFAULT_AGENT_ID = 1


def _dsn() -> str:
    """Return DATABASE_URL from environment."""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise OSError("DATABASE_URL is not set in environment")
    return url


def _agent_id() -> int:
    """Return the trader agent ID from environment or default."""
    raw = os.environ.get("TRADER_AGENT_ID", str(DEFAULT_AGENT_ID))
    return int(raw)


def _wallet_address() -> str:
    """Return the trader wallet address from environment."""
    addr = os.environ.get("CIRCLE_WALLET_TRADER_ADDRESS", "0x0")
    return addr


def ensure_agent_row(dsn: str | None = None) -> None:
    """Ensure the trader agent row exists in the agents table."""
    dsn = dsn or _dsn()
    agent_card_cid = os.environ.get("TRADER_AGENT_CARD_CID", "")
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO agents (agent_id, role, wallet_address, agent_card_cid) "
            "VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (agent_id) DO UPDATE "
            "SET wallet_address = EXCLUDED.wallet_address, "
            "    agent_card_cid = COALESCE(EXCLUDED.agent_card_cid, agents.agent_card_cid)",
            (_agent_id(), "trader", _wallet_address(), agent_card_cid or None),
        )
        conn.commit()
    logger.info("agent_row_ensured", agent_id=_agent_id())


def persist_trace(trace: TradingR1Trace, dsn: str | None = None) -> None:
    """Persist a trace to the Neon ``traces`` table.

    Must be called after IPFS pinning succeeds (per VAL-TRADER-003).
    """
    dsn = dsn or _dsn()
    agent_id = _agent_id()
    content_hash = trace.content_hash()

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO traces "
            "(trace_id, agent_id, market_id, ipfs_cid, content_hash) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (trace_id) DO UPDATE "
            "SET ipfs_cid = EXCLUDED.ipfs_cid, content_hash = EXCLUDED.content_hash",
            (
                trace.trace_id,
                agent_id,
                trace.market_id,
                "",  # ipfs_cid filled by caller after pin
                content_hash,
            ),
        )
        conn.commit()
    logger.info(
        "trace_persisted",
        trace_id=trace.trace_id,
        agent_id=agent_id,
    )


def update_trace_ipfs_cid(trace_id: str, ipfs_cid: str, dsn: str | None = None) -> None:
    """Update the ipfs_cid for a trace after successful IPFS pin."""
    dsn = dsn or _dsn()
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE traces SET ipfs_cid = %s WHERE trace_id = %s",
            (ipfs_cid, trace_id),
        )
        conn.commit()
    logger.info("trace_ipfs_cid_updated", trace_id=trace_id, ipfs_cid=ipfs_cid)
