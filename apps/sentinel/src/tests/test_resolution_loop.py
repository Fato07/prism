"""Bounded adversarial resolution loop tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from fastmcp import FastMCP
from prism_schemas.trace import Evidence, ThesisStep, TradingR1Trace
from prism_schemas.verdict import AdversarialChallenge, SentinelVerdict

from sentinel.evidence_tools import (
    EvidenceSearchResult,
    McpEvidenceProvider,
    StaticEvidenceProvider,
)
from sentinel.resolution_loop import generate_verdict_with_resolution


def _trace() -> TradingR1Trace:
    return TradingR1Trace(
        trace_id="trace-resolution-1",
        agent_id=1,
        market_id="poly-test",
        market_question="Will the Fed cut rates by July 2026?",
        thesis=[
            ThesisStep(
                proposition="Current data supports easing.",
                supporting_evidence_ids=[0],
                risk_factors=["Inflation rebound"],
            )
        ],
        evidence=[
            Evidence(
                source="BLS",
                claim="Recent CPI came in below expectations.",
                confidence=0.85,
                timestamp=datetime(2026, 5, 1, tzinfo=UTC),
            )
        ],
        raw_probability=0.62,
        volatility_adjustment=-0.03,
        final_probability=0.59,
        action="BUY",
        size_usdc=1.0,
        price_limit=0.59,
        rationale="Recent official data supports a small position.",
        model_family="anthropic-claude",
        model_name="claude-sonnet-4-20250514",
        created_at=datetime(2026, 5, 16, tzinfo=UTC),
    )


def _blocking_verdict() -> SentinelVerdict:
    return SentinelVerdict(
        request_hash="request-1",
        trace_id="trace-resolution-1",
        sentinel_agent_id=2,
        evidence_challenges=["Evidence needs a current primary-source check."],
        thesis_challenges=["Thesis depends on data freshness."],
        calibration_critique="Probability is acceptable if current data is verified.",
        verdict_score=50,
        verdict_label="WARN",
        dialogue_messages=[{"role": "sentinel", "content": "Need current evidence."}],
        structured_challenges=[
            AdversarialChallenge(
                id="sys-temporal-stale-evidence",
                type="temporal",
                severity="blocking",
                question="Evidence is stale.",
                required_resolution="Retrieve current evidence or revise to HOLD.",
                blocking_pass=True,
                claim_ref="evidence[0]",
            )
        ],
        model_family="openai-gpt",
        model_name="gpt-4o-mini",
        created_at=datetime(2026, 5, 16, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_resolution_loop_records_unresolved_blocker_without_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_generate_verdict(**_: object) -> SentinelVerdict:
        return _blocking_verdict()

    monkeypatch.setattr("sentinel.resolution_loop.generate_verdict", fake_generate_verdict)

    verdict = await generate_verdict_with_resolution(
        trace_json=json.dumps(_trace().model_dump(mode="json")),
        request_hash="request-1",
        trace_id="trace-resolution-1",
        sentinel_agent_id=2,
        max_rounds=1,
    )

    assert verdict.verdict_label == "WARN"
    assert verdict.resolution_rounds
    assert verdict.challenge_resolutions
    assert verdict.structured_challenges[0].resolution_status == "conceded"
    assert verdict.resolution_metadata is not None
    assert verdict.resolution_metadata.unresolved_blocking_count == 1
    assert verdict.resolution_metadata.stop_reason == "unresolved_blockers"


@pytest.mark.asyncio
async def test_resolution_loop_allows_pass_after_provider_resolves_blocker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = _blocking_verdict().model_copy(update={"verdict_score": 65, "verdict_label": "PASS"})

    seen_kwargs: dict[str, object] = {}

    async def fake_generate_verdict(**kwargs: object) -> SentinelVerdict:
        seen_kwargs.update(kwargs)
        return base

    monkeypatch.setattr("sentinel.resolution_loop.generate_verdict", fake_generate_verdict)
    provider = StaticEvidenceProvider(
        {
            "sys-temporal-stale-evidence": [
                EvidenceSearchResult(
                    title="Official current report",
                    url="https://example.com/current-report",
                    snippet="Current primary data confirms the relevant condition.",
                    provider="static-test",
                    confidence=0.9,
                )
            ]
        }
    )

    verdict = await generate_verdict_with_resolution(
        trace_json=json.dumps(_trace().model_dump(mode="json")),
        request_hash="request-1",
        trace_id="trace-resolution-1",
        sentinel_agent_id=2,
        max_rounds=1,
        evidence_provider=provider,
    )

    assert seen_kwargs["apply_issue_caps"] is False
    assert verdict.verdict_label == "PASS"
    assert verdict.verdict_score == 65
    assert verdict.structured_challenges[0].resolution_status == "resolved"
    assert verdict.resolution_metadata is not None
    assert verdict.resolution_metadata.unresolved_blocking_count == 0
    assert verdict.resolution_metadata.stop_reason == "confidence_reached"


@pytest.mark.asyncio
async def test_resolution_loop_allows_pass_after_mcp_provider_resolves_blocker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MCP evidence tools can resolve blockers inside the resolution loop."""
    base = _blocking_verdict().model_copy(update={"verdict_score": 65, "verdict_label": "PASS"})

    async def fake_generate_verdict(**_: object) -> SentinelVerdict:
        return base

    server = FastMCP("resolution-evidence")

    @server.tool
    def search(query: str, limit: int) -> dict[str, object]:
        assert "Fed" in query
        assert limit == 5
        return {
            "results": [
                {
                    "title": "MCP official current report",
                    "url": "https://example.com/mcp-current-report",
                    "snippet": "MCP-retrieved primary data resolves the freshness issue.",
                    "confidence": 0.91,
                }
            ]
        }

    monkeypatch.setattr("sentinel.resolution_loop.generate_verdict", fake_generate_verdict)
    provider = McpEvidenceProvider(
        tool_name="search",
        result_mapper="generic_search",
        input_mapper="query_limit",
        transport=server,
    )

    verdict = await generate_verdict_with_resolution(
        trace_json=json.dumps(_trace().model_dump(mode="json")),
        request_hash="request-1",
        trace_id="trace-resolution-1",
        sentinel_agent_id=2,
        max_rounds=1,
        evidence_provider=provider,
    )

    assert verdict.verdict_label == "PASS"
    assert verdict.verdict_score == 65
    assert verdict.structured_challenges[0].resolution_status == "resolved"
    assert verdict.challenge_resolutions[0].responder == "evidence_tool"
    assert "mcp-current-report" in verdict.challenge_resolutions[0].response
    assert verdict.resolution_metadata is not None
    assert verdict.resolution_metadata.unresolved_blocking_count == 0


@pytest.mark.asyncio
async def test_resolution_loop_keeps_blocker_when_mcp_provider_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed MCP evidence should not falsely clear a blocker."""
    base = _blocking_verdict().model_copy(update={"verdict_score": 65, "verdict_label": "PASS"})

    async def fake_generate_verdict(**_: object) -> SentinelVerdict:
        return base

    server = FastMCP("resolution-evidence")

    @server.tool
    def search(query: str, limit: int) -> dict[str, object]:
        assert limit == 5
        return {"items": [{"text": query}]}

    monkeypatch.setattr("sentinel.resolution_loop.generate_verdict", fake_generate_verdict)
    provider = McpEvidenceProvider(
        tool_name="search",
        result_mapper="generic_search",
        input_mapper="query_limit",
        transport=server,
    )

    verdict = await generate_verdict_with_resolution(
        trace_json=json.dumps(_trace().model_dump(mode="json")),
        request_hash="request-1",
        trace_id="trace-resolution-1",
        sentinel_agent_id=2,
        max_rounds=1,
        evidence_provider=provider,
    )

    assert verdict.verdict_label == "WARN"
    assert verdict.verdict_score == 50
    assert verdict.structured_challenges[0].resolution_status == "conceded"
    assert verdict.resolution_metadata is not None
    assert verdict.resolution_metadata.unresolved_blocking_count == 1
    assert verdict.resolution_metadata.stop_reason == "unresolved_blockers"
