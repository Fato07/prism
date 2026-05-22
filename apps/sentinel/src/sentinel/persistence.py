"""Neon DB persistence for sentinel verdicts.

Handles inserting verdicts into the Neon ``validations`` table and ensuring
the sentinel agent row exists in the ``agents`` table.  Includes tx_hash
persistence for on-chain validation response transactions.
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


def update_agent_registration_tx_hash(tx_hash: str, dsn: str | None = None) -> None:
    """Update the registration_tx_hash for the sentinel agent."""
    dsn = dsn or _dsn()
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE agents SET registration_tx_hash = %s WHERE agent_id = %s",
            (tx_hash, _agent_id()),
        )
        conn.commit()
    logger.info("agent_registration_tx_hash_updated", agent_id=_agent_id(), tx_hash=tx_hash)


def persist_verdict(
    verdict: SentinelVerdict,
    *,
    requester_address: str | None = None,
    dsn: str | None = None,
) -> None:
    """Persist a verdict to the Neon ``validations`` table.

    Must be called after IPFS pinning succeeds (per VAL-SENTINEL-004).

    Args:
        verdict: The sentinel verdict to persist.
        requester_address: The on-chain address of the x402 payer, captured
            from the facilitator settlement response.  ``None`` when the
            request came through the internal bypass channel.
        dsn: Optional database connection string override.
    """
    dsn = dsn or _dsn()
    agent_id = _agent_id()

    # Use the verdict's request_hash as the primary key (bytes32 on-chain).
    # Try hex decode first (32 bytes for a 64-char hex), fall back to UTF-8.
    try:
        request_hash = bytes.fromhex(verdict.request_hash) if verdict.request_hash else b""
    except ValueError:
        request_hash = verdict.request_hash.encode("utf-8") if verdict.request_hash else b""

    # Normalise requester_address to lowercase so DB lookups are
    # case-insensitive (EIP-55 checksums vary but the DB stores only one).
    norm_address: str | None = requester_address.lower() if requester_address else None

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO validations "
            "(request_hash, trace_id, sentinel_agent_id, verdict_score, response_uri, "
            "requester_address) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (request_hash) DO UPDATE "
            "SET verdict_score = EXCLUDED.verdict_score, "
            "response_uri = EXCLUDED.response_uri, "
            "requester_address = COALESCE(validations.requester_address, "
            "EXCLUDED.requester_address)",
            (
                request_hash,
                verdict.trace_id,
                agent_id,
                verdict.verdict_score,
                "",  # response_uri filled by caller after IPFS pin
                norm_address,
            ),
        )
        conn.commit()
    logger.info(
        "verdict_persisted",
        trace_id=verdict.trace_id,
        verdict_score=verdict.verdict_score,
        verdict_label=verdict.verdict_label,
        requester_address=norm_address,
    )


def update_verdict_response_uri(
    request_hash: str, response_uri: str, dsn: str | None = None
) -> None:
    """Update the response_uri for a verdict after successful IPFS pin."""
    dsn = dsn or _dsn()
    # request_hash may be a hex string (64 chars) or a raw SHA-256 digest.
    # Try to decode as hex first (32 bytes), fall back to UTF-8 encoding.
    try:
        request_hash_bytes = bytes.fromhex(request_hash) if request_hash else b""
    except ValueError:
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


def update_validation_tx_hash(request_hash: str, tx_hash: str, dsn: str | None = None) -> None:
    """Update the on-chain tx_hash for a validation after validation response."""
    dsn = dsn or _dsn()
    # request_hash may be a hex string (64 chars) or a raw SHA-256 digest.
    # Try to decode as hex first (32 bytes), fall back to UTF-8 encoding.
    try:
        request_hash_bytes = bytes.fromhex(request_hash) if request_hash else b""
    except ValueError:
        request_hash_bytes = request_hash.encode("utf-8") if request_hash else b""
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE validations SET tx_hash = %s WHERE request_hash = %s",
            (tx_hash, request_hash_bytes),
        )
        conn.commit()
    logger.info("validation_tx_hash_updated", request_hash=request_hash, tx_hash=tx_hash)
