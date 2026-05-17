"""Demo MCP evidence server tests."""

from __future__ import annotations

import pytest
from fastmcp import Client

from sentinel.demo_evidence_mcp import build_demo_evidence_mcp_server


@pytest.mark.asyncio
async def test_demo_evidence_mcp_returns_smoke_proof_only_for_smoke_query() -> None:
    server = build_demo_evidence_mcp_server()

    async with Client(server) as client:
        smoke = await client.call_tool(
            "search",
            {"query": "Prism connector smoke test: latest public evidence for a prediction market claim", "limit": 5},
        )
        regular = await client.call_tool(
            "search",
            {"query": "Will this market resolve YES?", "limit": 5},
        )

    assert smoke.data is not None
    assert smoke.data["results"][0]["provider"] == "prism_demo_evidence_mcp.search"
    assert "Replace this connector" in smoke.data["results"][0]["snippet"]
    assert regular.data == {"results": []}


@pytest.mark.asyncio
async def test_demo_evidence_mcp_does_not_answer_marker_inside_real_query() -> None:
    server = build_demo_evidence_mcp_server()

    async with Client(server) as client:
        result = await client.call_tool(
            "search",
            {
                "query": (
                    "Will Prism connector smoke test: latest public evidence for a prediction "
                    "market claim resolve YES? latest current evidence status date"
                ),
                "limit": 5,
            },
        )

    assert result.data == {"results": []}


@pytest.mark.asyncio
async def test_demo_evidence_mcp_can_be_explicitly_enabled_for_demo_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRISM_DEMO_EVIDENCE_ALLOW_RESOLUTION", "1")
    server = build_demo_evidence_mcp_server()

    async with Client(server) as client:
        result = await client.call_tool(
            "search",
            {"query": "Will this market resolve YES?", "limit": 3},
        )

    assert result.data is not None
    assert len(result.data["results"]) == 1
    assert result.data["results"][0]["confidence"] == 0.99
