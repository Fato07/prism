"""Market evidence MCP server tests."""

from __future__ import annotations

import httpx
import pytest
from fastmcp import Client

from sentinel.market_evidence_mcp import build_market_evidence_mcp_server

SMOKE_QUERY = "Prism connector smoke test: latest public evidence for a prediction market claim"
RIZO_QUESTION = "Will Rizo Velovic win Survivor Season 50?"
RIZO_TOKEN_ID = "60170194291888261156581402202700948575463111971929944319443581000603115704607"
RIZO_CONDITION_ID = "0x355093713e6bd18745724e2c42a8bdfeb8433a08a441b93a7ce27a97b707a9d6"


@pytest.mark.asyncio
async def test_market_evidence_mcp_returns_smoke_proof(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRISM_MARKET_EVIDENCE_GATEWAY_URL", "https://gateway.example")
    server = build_market_evidence_mcp_server()

    async with Client(server) as client:
        result = await client.call_tool(
            "search",
            {
                "query": SMOKE_QUERY,
                "max_results": 5,
                "market_question": "Will the connector return current external evidence?",
                "challenge": {
                    "id": "smoke-temporal-001",
                    "type": "temporal",
                    "severity": "material",
                    "question": "Can this tool return recent evidence?",
                    "required_resolution": "Return one result.",
                    "blocking_pass": False,
                    "resolution_status": "open",
                },
            },
        )

    assert result.data is not None
    assert result.data["results"][0]["provider"] == "prism_market_evidence_mcp.search"


@pytest.mark.asyncio
async def test_market_evidence_mcp_resolves_market_structure_issue_from_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRISM_MARKET_EVIDENCE_GATEWAY_URL", "https://gateway.example")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/markets/resolve"
        assert request.url.params["query"] == RIZO_QUESTION
        return httpx.Response(
            200,
            json={
                "query": RIZO_QUESTION,
                "resolution": {
                    "status": "resolved",
                    "tokenId": RIZO_TOKEN_ID,
                    "conditionId": RIZO_CONDITION_ID,
                    "confidence": 1,
                    "source": "question_fuzzy",
                    "matchedQuestion": RIZO_QUESTION,
                    "reason": "matched significant question terms to a fresh binary CLOB market",
                },
            },
        )

    server = build_market_evidence_mcp_server(transport=httpx.MockTransport(handler))

    async with Client(server) as client:
        result = await client.call_tool(
            "search",
            {
                "query": f"{RIZO_QUESTION} Polymarket end date resolved active",
                "max_results": 5,
                "market_question": RIZO_QUESTION,
                "challenge": {
                    "id": "market-structure-status",
                    "type": "market_structure",
                    "severity": "material",
                    "question": "Need to confirm the market is active and token-resolved.",
                    "required_resolution": "Resolve the Polymarket market and token identifiers.",
                    "blocking_pass": False,
                    "resolution_status": "open",
                },
            },
        )

    assert result.data is not None
    evidence = result.data["results"][0]
    assert evidence["provider"] == "prism_market_evidence_mcp.search"
    assert "fresh binary CLOB market" in evidence["snippet"]
    assert "conditionId=" in evidence["snippet"]
    assert evidence["confidence"] == 1


@pytest.mark.asyncio
async def test_market_evidence_mcp_fails_closed_for_generic_temporal_stale_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRISM_MARKET_EVIDENCE_GATEWAY_URL", "https://gateway.example")

    def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("unsupported challenge types must not call the gateway")

    server = build_market_evidence_mcp_server(transport=httpx.MockTransport(handler))

    async with Client(server) as client:
        result = await client.call_tool(
            "search",
            {
                "query": f"{RIZO_QUESTION} latest current evidence status date",
                "max_results": 5,
                "market_question": RIZO_QUESTION,
                "challenge": {
                    "id": "sys-temporal-stale-evidence",
                    "type": "temporal",
                    "severity": "material",
                    "question": (
                        "Evidence items are older than 365 days relative to trace creation."
                    ),
                    "required_resolution": "Provide current evidence about the underlying claim.",
                    "blocking_pass": False,
                    "resolution_status": "open",
                },
            },
        )

    assert result.data == {"results": []}


@pytest.mark.asyncio
async def test_market_evidence_mcp_fails_closed_when_gateway_cannot_resolve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRISM_MARKET_EVIDENCE_GATEWAY_URL", "https://gateway.example")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"resolution": {"status": "unresolved", "reason": "no match"}},
        )

    server = build_market_evidence_mcp_server(transport=httpx.MockTransport(handler))

    async with Client(server) as client:
        result = await client.call_tool(
            "search",
            {
                "query": "Unknown market latest current evidence status date",
                "max_results": 5,
                "market_question": "Unknown market",
                "challenge": {
                    "id": "sys-temporal-stale-evidence",
                    "type": "temporal",
                    "severity": "material",
                    "question": "Evidence is stale.",
                    "required_resolution": "Provide current evidence.",
                    "blocking_pass": False,
                    "resolution_status": "open",
                },
            },
        )

    assert result.data == {"results": []}
