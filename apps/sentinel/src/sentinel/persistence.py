"""Neon DB persistence for sentinel verdicts.

Handles inserting verdicts into the Neon ``validations`` table and ensuring
the sentinel agent row exists in the ``agents`` table.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import psycopg
import structlog

if TYPE_CHECKING:
    from prism_schemas.verdict import SentinelVerdict

logger = structlog.get_logger("prism.sentinel.persistence")

# Default agent_id for the sentinel (overridden by SENTINEL_AGENT_ID env var).
DEFAULT_AGENT_ID = 2


def _dsn() -> str:
    """Return DATABASE_URL from environment."""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise OSError("DATABASE_URL is not set in environment")
    return url


def _agent_id() -> int:
    """Return the sentinel agent ID from environment or default."""
    raw = os.environ.get("SENTINEL_AGENT_ID", str(DEFAULT_AGENT_ID))
    return int(raw)


def _wallet_address() -> str:
    """Return the sentinel wallet address from environment."""
    addr = os.environ.get("CIRCLE_WALLET_SENTINEL_ADDRESS", "0x0")
    return addr


def ensure_agent_row(dsn: str | None = None) -> None:
    """Ensure the sentinel agent row exists in the agents table."""
    dsn = dsn or _dsn()
    agent_card_cid = os.environ.get("SENTINEL_AGENT_CARD_CID", "")
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO agents (agent_id, role, wallet_address, agent_card_cid) "
            "VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (agent_id) DO UPDATE "
            "SET wallet_address = EXCLUDED.wallet_address, "
            "    agent_card_cid = COALESCE(EXCLUDED.agent_card_cid, agents.agent_card_cid)",
            (_agent_id(), "sentinel", _wallet_address(), agent_card_cid or None),
        )
        conn.commit()
    logger.info("agent_row_ensured", agent_id=_agent_id())


def persist_verdict(verdict: SentinelVerdict, dsn: str | None = None) -> None:
    """Persist a verdict to the Neon ``validations`` table.

    Must be called after IPFS pinning succeeds (per VAL-SENTINEL-004).
    """
    dsn = dsn or _dsn()
    agent_id = _agent_id()

    # Use the verdict's content_hash as request_hash (bytes32 on-chain).
    request_hash = verdict.request_hash.encode("utf-8") if verdict.request_hash else b""

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO validations "
            "(request_hash, trace_id, sentinel_agent_id, verdict_score, response_uri) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (request_hash) DO UPDATE "
            "SET verdict_score = EXCLUDED.verdict_score, "
            "response_uri = EXCLUDED.response_uri",
            (
                request_hash,
                verdict.trace_id,
                agent_id,
                verdict.verdict_score,
                "",  # response_uri filled by caller after IPFS pin
            ),
        )
        conn.commit()
    logger.info(
        "verdict_persisted",
        trace_id=verdict.trace_id,
        verdict_score=verdict.verdict_score,
        verdict_label=verdict.verdict_label,
    )


def update_verdict_response_uri(
    request_hash: str, response_uri: str, dsn: str | None = None
) -> None:
    """Update the response_uri for a verdict after successful IPFS pin."""
    dsn = dsn or _dsn()
    request_hash_bytes = request_hash.encode("utf-8") if request_hash else b""
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE validations SET response_uri = %s WHERE request_hash = %s",
            (response_uri, request_hash_bytes),
        )
        conn.commit()
    logger.info(
        "verdict_response_uri_updated",
        request_hash=request_hash,
        response_uri=response_uri,
    )
