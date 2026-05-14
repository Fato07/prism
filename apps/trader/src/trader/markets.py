"""Market selection for autonomous pipeline runs.

Tries to fetch real Polymarket market data from the gateway at startup /
first call. Falls back to a curated list of questions when the gateway
is unreachable (e.g. local dev without the gateway running).

Real markets supply genuine ``conditionId`` and ``tokenId`` values so
that live trades actually land on Polymarket.
"""

from __future__ import annotations

import os
import random
from typing import Any

import httpx
import structlog

logger = structlog.get_logger("prism.markets")

# ---------------------------------------------------------------------------
# Fallback curated list — used when the gateway is unreachable
# ---------------------------------------------------------------------------

MARKET_QUESTIONS: list[dict[str, str]] = [
    {
        "id": "0xfed_rate_june_2026",
        "question": "Will the Federal Reserve cut interest rates at the June 2026 FOMC meeting?",
    },
    {
        "id": "0xbtc_150k_2026",
        "question": "Will Bitcoin exceed $150,000 before the end of 2026?",
    },
    {
        "id": "0xeu_ai_regulation_2026",
        "question": "Will the EU AI Act enforcement actions exceed 50 by end of 2026?",
    },
    {
        "id": "0xai_agent_market_2026",
        "question": "Will AI agent market cap exceed $10B by end of 2026?",
    },
    {
        "id": "0xopen_source_ai_2026",
        "question": "Will an open-source AI model top the LMSYS leaderboard by December 2026?",
    },
    {
        "id": "0xarc_tvl_2026",
        "question": "Will Arc testnet TVL exceed $500M by end of 2026?",
    },
    {
        "id": "0xpolymarket_volume_2026",
        "question": "Will Polymarket monthly volume exceed $1B in 2026?",
    },
    {
        "id": "0xusdc_supply_2026",
        "question": "Will USDC total supply exceed $100B by end of 2026?",
    },
]

# ---------------------------------------------------------------------------
# Gateway-sourced real markets (lazy-loaded on first pick_market() call)
# ---------------------------------------------------------------------------

_real_markets: list[dict[str, str]] | None = None
"""Cached list of real markets from the Polymarket gateway.
None means "not yet attempted". An empty list means "attempted but
gateway returned no markets" — in that case we keep the cached empty
list to avoid hammering the gateway on every pick_market() call.
"""


def _gateway_url() -> str:
    """Return the Polymarket gateway base URL from env."""
    return os.environ.get("GATEWAY_URL", "http://localhost:3203").rstrip("/")


async def _fetch_real_markets() -> list[dict[str, str]]:
    """Fetch real markets from the gateway's ``GET /markets`` endpoint.

    Returns a list of dicts with keys ``id``, ``question``, ``tokenId``.
    The ``id`` field is the real Polymarket ``conditionId`` (66-char hex).
    The ``tokenId`` field is the YES outcome's ERC-1155 token ID.

    Returns an empty list (and logs a warning) if the gateway is
    unreachable or returns no usable markets.
    """
    url = f"{_gateway_url()}/markets"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            body: dict[str, Any] = resp.json()

        raw_markets: list[dict[str, Any]] = body.get("markets", [])
        markets: list[dict[str, str]] = []
        for m in raw_markets:
            condition_id = m.get("conditionId", "")
            question = m.get("question", "")
            yes_token_id = m.get("yesTokenId") or ""
            # Only include markets that have both a conditionId and a yesTokenId
            if condition_id and question and yes_token_id:
                markets.append(
                    {
                        "id": condition_id,
                        "question": question,
                        "tokenId": yes_token_id,
                    }
                )
        logger.info(
            "fetched_real_markets",
            source="gateway",
            count=len(markets),
            total_returned=len(raw_markets),
        )
        return markets
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        logger.warning(
            "gateway_unreachable",
            url=url,
            error=str(exc),
            fallback="using curated market list",
        )
        return []
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "gateway_http_error",
            url=url,
            status_code=exc.response.status_code,
            fallback="using curated market list",
        )
        return []
    except Exception as exc:
        logger.error(
            "gateway_fetch_failed",
            url=url,
            error=str(exc),
            fallback="using curated market list",
        )
        return []


async def _ensure_real_markets() -> list[dict[str, str]]:
    """Lazily fetch and cache real markets from the gateway.

    On the first call, contacts the gateway. Subsequent calls return
    the cached result. If the gateway was unreachable, the cached
    list will be empty and ``pick_market()`` will fall back to the
    curated list.
    """
    global _real_markets  # noqa: PLW0603
    if _real_markets is None:
        _real_markets = await _fetch_real_markets()
    return _real_markets


def invalidate_real_market_cache() -> None:
    """Clear the cached real-market list so the next call re-fetches."""
    global _real_markets  # noqa: PLW0603
    _real_markets = None


async def pick_market() -> dict[str, str]:
    """Return a random market, preferring real Polymarket data.

    Resolution order:
    1. Real markets from the gateway (with ``conditionId`` + ``tokenId``)
    2. Curated fallback list (internal IDs, no ``tokenId``)

    The returned dict always has ``id`` and ``question`` keys.
    Real markets additionally have a ``tokenId`` key.
    """
    real = await _ensure_real_markets()
    if real:
        return random.choice(real)
    # Fallback: curated list (no tokenId — paper-trade or graceful failure)
    return random.choice(MARKET_QUESTIONS)
