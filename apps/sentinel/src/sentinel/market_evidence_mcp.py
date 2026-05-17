"""MCP evidence server backed by Prism's Polymarket gateway.

This connector is intentionally narrow: it can corroborate market-structure and
freshness issues with the live gateway's token-resolution view, but it does not
pretend to answer broad source-quality or logic challenges. Unsupported issues
return no evidence so the resolution loop fails closed.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote_plus

import httpx
from fastmcp import FastMCP

MARKET_EVIDENCE_SERVER_NAME = "prism-market-evidence"
SMOKE_QUERY = "Prism connector smoke test: latest public evidence for a prediction market claim"
SUPPORTED_CHALLENGE_TYPES = frozenset({"market_structure"})
SUPPORTED_TEMPORAL_MARKET_TERMS = frozenset(
    {"end date", "closed", "active", "resolved", "accepting orders"}
)


def build_market_evidence_mcp_server(
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FastMCP:
    """Build the read-only market evidence MCP server."""
    server = FastMCP(MARKET_EVIDENCE_SERVER_NAME)

    @server.tool
    async def search(
        query: str,
        max_results: int = 5,
        market_question: str | None = None,
        challenge: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Return market evidence for supported sentinel issue types."""
        if query.strip() == SMOKE_QUERY:
            return {"results": [_smoke_result(max_results=limit or max_results)]}

        if not _supports_challenge(challenge):
            return {"results": []}

        question = (market_question or "").strip()
        if not question:
            return {"results": []}

        resolution = await _resolve_market(question=question, transport=transport)
        if resolution is None:
            return {"results": []}

        return {"results": [_market_resolution_result(question=question, resolution=resolution)]}

    return server


def _smoke_result(*, max_results: int) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    return {
        "title": "Prism market evidence connector smoke proof",
        "url": "https://polymarket.com/",
        "snippet": (
            "Market evidence MCP server is reachable and returned a "
            "generic_search-compatible result for "
            f"{min(max(max_results, 1), 20)} requested item(s). "
            "Real issue resolution is limited to market-structure and market-status "
            "temporal challenges."
        ),
        "provider": "prism_market_evidence_mcp.search",
        "published_at": None,
        "retrieved_at": now,
        "confidence": 0.99,
    }


def _supports_challenge(challenge: dict[str, Any] | None) -> bool:
    challenge_type = _challenge_type(challenge)
    if challenge_type in SUPPORTED_CHALLENGE_TYPES:
        return True
    if challenge_type != "temporal" or not isinstance(challenge, dict):
        return False

    text = " ".join(
        _string_or_none(challenge.get(key)) or ""
        for key in ("id", "question", "required_resolution")
    ).lower()
    if "market" not in text:
        return False
    return any(term in text for term in SUPPORTED_TEMPORAL_MARKET_TERMS)


def _challenge_type(challenge: dict[str, Any] | None) -> str:
    if not isinstance(challenge, dict):
        return ""
    value = challenge.get("type")
    return value.strip().lower() if isinstance(value, str) else ""


async def _resolve_market(
    *,
    question: str,
    transport: httpx.AsyncBaseTransport | None,
) -> dict[str, Any] | None:
    gateway_url = _gateway_base_url()
    if gateway_url is None:
        return None

    timeout_s = _timeout_seconds()
    try:
        async with httpx.AsyncClient(timeout=timeout_s, transport=transport) as client:
            response = await client.get(
                f"{gateway_url}/markets/resolve",
                params={"query": question, "marketQuestion": question},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        return None

    if not isinstance(payload, dict):
        return None
    resolution = payload.get("resolution")
    if not isinstance(resolution, dict):
        return None
    if resolution.get("status") != "resolved":
        return None
    return resolution


def _market_resolution_result(*, question: str, resolution: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    matched_question = _string_or_none(resolution.get("matchedQuestion")) or question
    condition_id = _string_or_none(resolution.get("conditionId"))
    token_id = _string_or_none(resolution.get("tokenId"))
    reason = _string_or_none(resolution.get("reason")) or "matched by Prism Polymarket gateway"
    source = _string_or_none(resolution.get("source")) or "polymarket_gateway"
    confidence = _confidence(resolution.get("confidence"))

    identifiers = []
    if condition_id:
        identifiers.append(f"conditionId={condition_id}")
    if token_id:
        identifiers.append(f"yesTokenId={token_id}")
    identifier_text = "; ".join(identifiers) if identifiers else "token identifiers unavailable"

    return {
        "title": f"Fresh Polymarket market matched: {matched_question}",
        "url": f"https://polymarket.com/search?q={quote_plus(question)}",
        "snippet": (
            "Prism's Polymarket gateway resolved this question to a fresh binary CLOB market. "
            f"Resolver source: {source}. Reason: {reason}. {identifier_text}. "
            "This evidence can address market status/structure only; it is not a general "
            "news or contestant-quality source."
        ),
        "provider": "prism_market_evidence_mcp.search",
        "published_at": None,
        "retrieved_at": now,
        "confidence": confidence,
    }


def _gateway_base_url() -> str | None:
    raw = (
        os.environ.get("PRISM_MARKET_EVIDENCE_GATEWAY_URL")
        or os.environ.get("POLYMARKET_GATEWAY_URL")
        or os.environ.get("RAILWAY_SERVICE_PRISM_POLYMARKET_GATEWAY_URL")
        or ""
    ).strip()
    if not raw:
        return None
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    return raw.rstrip("/")


def _timeout_seconds() -> float:
    raw = os.environ.get("PRISM_MARKET_EVIDENCE_TIMEOUT_SECONDS", "10")
    try:
        parsed = float(raw)
    except ValueError:
        return 10.0
    return parsed if parsed > 0 else 10.0


def _confidence(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.7
    return min(max(parsed, 0.0), 1.0)


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
