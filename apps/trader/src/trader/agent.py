"""Main trader agent loop.

This module re-exports the key entry points for convenience.
The FastAPI service is defined in ``trader.main``.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger("prism.trader.agent")


async def run_trading_cycle(market_id: str, market_question: str) -> dict[str, str]:
    """Execute one full trading cycle: analyze market → generate trace → pin → persist.

    Returns a dict with trace_id, ipfs_cid, and content_hash_hex.
    """
    from trader.ipfs import PinataClient
    from trader.persistence import persist_trace, update_trace_ipfs_cid
    from trader.trading_r1 import generate_and_post_process

    logger.info("trading_cycle_start", market_id=market_id)

    # Generate trace
    trace = await generate_and_post_process(
        market_id=market_id,
        market_question=market_question,
    )

    # Pin to IPFS
    pinata = PinataClient()
    ipfs_cid = await pinata.pin_json(trace.model_dump(mode="json"))
    await pinata.close()

    # Persist to DB
    persist_trace(trace)
    update_trace_ipfs_cid(trace.trace_id, ipfs_cid)

    logger.info(
        "trading_cycle_complete",
        trace_id=trace.trace_id,
        ipfs_cid=ipfs_cid,
    )

    return {
        "trace_id": trace.trace_id,
        "ipfs_cid": ipfs_cid,
        "content_hash_hex": trace.content_hash().hex(),
    }
