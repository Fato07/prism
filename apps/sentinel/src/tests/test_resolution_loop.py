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
    NoopEvidenceProvider,
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
                question="The market claim relies on stale evidence.",
                required_resolution="Retrieve current evidence or revise to HOLD.",
                blocking_pass=True,
                claim_ref="evidence[0]",
            )
        ],
        model_family="openai-gpt",
        model_name="gpt-4o-mini",
        created_at=datetime(2026, 5, 16, tzinfo=UTC),
    )


def _source_quality_verdict() -> SentinelVerdict:
    return _blocking_verdict().model_copy(
        update={
            "verdict_score": 65,
            "verdict_label": "PASS",
            "structured_challenges": [
                AdversarialChallenge(
                    id="source-quality-primary",
                    type="source_quality",
                    severity="blocking",
                    question="Need primary Fed rates source support.",
                    required_resolution="Provide an official primary source for Fed rates.",
                    blocking_pass=True,
                )
            ],
        }
    )


def _exa_mcp_text_result(
    *,
    title: str,
    url: str,
    highlights: str,
    published: str = "2026-05-15T00:00:00.000Z",
) -> str:
    return "\n".join(
        [
            f"Title: {title}",
            f"URL: {url}",
            f"Published: {published}",
            "Author: N/A",
            "Highlights:",
            highlights,
        ]
    )


def _exa_mcp_provider(text: str) -> McpEvidenceProvider:
    server = FastMCP("exa-resolution-evidence")

    @server.tool
    def web_search_exa(query: str, max_results: int) -> str:
        assert query
        assert max_results == 5
        return text

    return McpEvidenceProvider(
        tool_name="web_search_exa",
        result_mapper="exa_mcp_text",
        input_mapper="query_max_results",
        transport=server,
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
        evidence_provider=NoopEvidenceProvider(),
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
                    title="Official current Fed rates report",
                    url="https://example.com/current-report",
                    snippet="Current primary data confirms the relevant Fed rates condition.",
                    provider="static-test",
                    published_at="2026-05-15T00:00:00Z",
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
                    "title": "MCP official current Fed rates report",
                    "url": "https://example.com/mcp-current-report",
                    "snippet": "MCP-retrieved primary data resolves the Fed rates freshness issue.",
                    "published_at": "2026-05-15T00:00:00Z",
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
async def test_resolution_loop_accepts_exa_mcp_current_temporal_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fresh Exa MCP evidence can clear temporal blockers when it overlaps the market."""
    base = _blocking_verdict().model_copy(update={"verdict_score": 65, "verdict_label": "PASS"})

    async def fake_generate_verdict(**_: object) -> SentinelVerdict:
        return base

    monkeypatch.setattr("sentinel.resolution_loop.generate_verdict", fake_generate_verdict)
    provider = _exa_mcp_provider(
        _exa_mcp_text_result(
            title="Current Fed rates report",
            url="https://example.com/current-fed-rates",
            highlights="Current Fed rates data supports the July 2026 market evidence check.",
        )
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
    assert verdict.structured_challenges[0].resolution_status == "resolved"
    assert verdict.challenge_resolutions[0].responder == "evidence_tool"
    assert "exa_mcp" in verdict.challenge_resolutions[0].response


@pytest.mark.asyncio
async def test_resolution_loop_rejects_exa_mcp_stale_temporal_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exa MCP evidence must still pass Prism's recency gate."""
    base = _blocking_verdict().model_copy(update={"verdict_score": 65, "verdict_label": "PASS"})

    async def fake_generate_verdict(**_: object) -> SentinelVerdict:
        return base

    monkeypatch.setattr("sentinel.resolution_loop.generate_verdict", fake_generate_verdict)
    provider = _exa_mcp_provider(
        _exa_mcp_text_result(
            title="Old Fed rates report",
            url="https://example.com/old-fed-rates",
            highlights="Historical Fed rates data discusses the same market topic.",
            published="2024-01-01T00:00:00.000Z",
        )
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
    assert verdict.structured_challenges[0].resolution_status == "conceded"


@pytest.mark.asyncio
async def test_resolution_loop_rejects_exa_mcp_generic_seo_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fresh Exa MCP pages still fail closed when content is generic SEO prose."""
    base = _blocking_verdict().model_copy(update={"verdict_score": 65, "verdict_label": "PASS"})

    async def fake_generate_verdict(**_: object) -> SentinelVerdict:
        return base

    monkeypatch.setattr("sentinel.resolution_loop.generate_verdict", fake_generate_verdict)
    provider = _exa_mcp_provider(
        _exa_mcp_text_result(
            title="Best prediction market research tools in 2026",
            url="https://example.com/seo-tools",
            highlights="Compare dashboards, rankings, newsletters, and generic research workflows.",
        )
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
    assert verdict.structured_challenges[0].resolution_status == "conceded"


@pytest.mark.asyncio
async def test_resolution_loop_rejects_exa_mcp_wrong_market_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fresh Exa MCP evidence cannot resolve a different market topic."""
    base = _blocking_verdict().model_copy(update={"verdict_score": 65, "verdict_label": "PASS"})

    async def fake_generate_verdict(**_: object) -> SentinelVerdict:
        return base

    monkeypatch.setattr("sentinel.resolution_loop.generate_verdict", fake_generate_verdict)
    provider = _exa_mcp_provider(
        _exa_mcp_text_result(
            title="Apex Netflix weekly ranking update",
            url="https://example.com/apex-netflix",
            highlights="Current streaming rankings discuss Apex and global Netflix viewing.",
        )
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
    assert verdict.structured_challenges[0].resolution_status == "conceded"


@pytest.mark.asyncio
async def test_resolution_loop_accepts_exa_mcp_official_source_quality_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Official/primary Exa MCP evidence can clear source-quality blockers."""
    source_verdict = _source_quality_verdict()

    async def fake_generate_verdict(**_: object) -> SentinelVerdict:
        return source_verdict

    monkeypatch.setattr("sentinel.resolution_loop.generate_verdict", fake_generate_verdict)
    provider = _exa_mcp_provider(
        _exa_mcp_text_result(
            title="Official Federal Reserve FOMC statement",
            url="https://www.federalreserve.gov/monetarypolicy/fomc.htm",
            highlights="Official primary Federal Reserve statement for Fed rates policy.",
        )
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
    assert verdict.structured_challenges[0].resolution_status == "resolved"


@pytest.mark.asyncio
async def test_resolution_loop_rejects_exa_mcp_negated_source_quality_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Negated Exa MCP source-quality evidence must fail closed."""
    source_verdict = _source_quality_verdict()

    async def fake_generate_verdict(**_: object) -> SentinelVerdict:
        return source_verdict

    monkeypatch.setattr("sentinel.resolution_loop.generate_verdict", fake_generate_verdict)
    provider = _exa_mcp_provider(
        _exa_mcp_text_result(
            title="Fed rates blog summary",
            url="https://example.com/fed-blog",
            highlights="No primary source is provided; this is secondary source commentary.",
        )
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
    assert verdict.structured_challenges[0].resolution_status == "conceded"


@pytest.mark.asyncio
async def test_resolution_loop_keeps_blocker_when_provider_returns_irrelevant_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-empty evidence is not enough; it must satisfy the issue."""
    base = _blocking_verdict().model_copy(update={"verdict_score": 65, "verdict_label": "PASS"})

    async def fake_generate_verdict(**_: object) -> SentinelVerdict:
        return base

    monkeypatch.setattr("sentinel.resolution_loop.generate_verdict", fake_generate_verdict)
    provider = StaticEvidenceProvider(
        {
            "sys-temporal-stale-evidence": [
                EvidenceSearchResult(
                    title="Unrelated entertainment recap",
                    url="https://example.com/recap",
                    snippet="A generic article about a television recap and recipes.",
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

    assert verdict.verdict_label == "WARN"
    assert verdict.verdict_score == 50
    assert verdict.structured_challenges[0].resolution_status == "conceded"
    assert verdict.challenge_resolutions[0].responder == "system"
    assert "satisfied this issue" in verdict.challenge_resolutions[0].response
    assert verdict.resolution_metadata is not None
    assert verdict.resolution_metadata.unresolved_blocking_count == 1


@pytest.mark.asyncio
async def test_resolution_loop_rejects_market_status_evidence_for_generic_stale_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Polymarket status evidence cannot clear broad stale-source blockers."""
    base = _blocking_verdict().model_copy(update={"verdict_score": 65, "verdict_label": "PASS"})

    async def fake_generate_verdict(**_: object) -> SentinelVerdict:
        return base

    monkeypatch.setattr("sentinel.resolution_loop.generate_verdict", fake_generate_verdict)
    provider = StaticEvidenceProvider(
        {
            "sys-temporal-stale-evidence": [
                EvidenceSearchResult(
                    title="Fresh Polymarket market matched",
                    url="https://polymarket.com/search?q=fed",
                    snippet=(
                        "Prism's Polymarket gateway resolved this question to a fresh "
                        "binary CLOB market. This evidence can address market "
                        "status/structure only."
                    ),
                    provider="prism_market_evidence_mcp.search",
                    confidence=1.0,
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

    assert verdict.verdict_label == "WARN"
    assert verdict.structured_challenges[0].resolution_status == "conceded"
    assert verdict.resolution_metadata is not None
    assert verdict.resolution_metadata.unresolved_blocking_count == 1


@pytest.mark.asyncio
async def test_resolution_loop_rejects_stale_published_temporal_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Old publication dates cannot satisfy current-evidence requirements."""
    base = _blocking_verdict().model_copy(update={"verdict_score": 65, "verdict_label": "PASS"})

    async def fake_generate_verdict(**_: object) -> SentinelVerdict:
        return base

    monkeypatch.setattr("sentinel.resolution_loop.generate_verdict", fake_generate_verdict)
    provider = StaticEvidenceProvider(
        {
            "sys-temporal-stale-evidence": [
                EvidenceSearchResult(
                    title="Old Fed rates report",
                    url="https://example.com/old-fed-rates",
                    snippet="Historical Fed rates data from years before the trace.",
                    provider="static-test",
                    published_at="2024-01-01T00:00:00Z",
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

    assert verdict.verdict_label == "WARN"
    assert verdict.structured_challenges[0].resolution_status == "conceded"


@pytest.mark.asyncio
async def test_resolution_loop_rejects_undated_temporal_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fresh-sounding prose without a publication date cannot clear stale-evidence gates."""
    base = _blocking_verdict().model_copy(update={"verdict_score": 65, "verdict_label": "PASS"})

    async def fake_generate_verdict(**_: object) -> SentinelVerdict:
        return base

    monkeypatch.setattr("sentinel.resolution_loop.generate_verdict", fake_generate_verdict)
    provider = StaticEvidenceProvider(
        {
            "sys-temporal-stale-evidence": [
                EvidenceSearchResult(
                    title="Latest Fed rates report",
                    url="https://example.com/latest-fed-rates",
                    snippet="Current Fed rates discussion without a published timestamp.",
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

    assert verdict.verdict_label == "WARN"
    assert verdict.structured_challenges[0].resolution_status == "conceded"


@pytest.mark.asyncio
async def test_resolution_loop_rejects_negated_source_quality_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Evidence saying no primary source exists cannot resolve source-quality issues."""
    source_verdict = _blocking_verdict().model_copy(
        update={
            "verdict_score": 65,
            "verdict_label": "PASS",
            "structured_challenges": [
                AdversarialChallenge(
                    id="source-quality-primary",
                    type="source_quality",
                    severity="blocking",
                    question="Need primary Fed rates source support.",
                    required_resolution="Provide an official primary source for Fed rates.",
                    blocking_pass=True,
                )
            ],
        }
    )

    async def fake_generate_verdict(**_: object) -> SentinelVerdict:
        return source_verdict

    monkeypatch.setattr("sentinel.resolution_loop.generate_verdict", fake_generate_verdict)
    provider = StaticEvidenceProvider(
        {
            "source-quality-primary": [
                EvidenceSearchResult(
                    title="Fed rates blog summary",
                    url="https://example.com/blog",
                    snippet=(
                        "No primary source is cited; this is scraped data from a "
                        "secondary source."
                    ),
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

    assert verdict.verdict_label == "WARN"
    assert verdict.structured_challenges[0].resolution_status == "conceded"


@pytest.mark.asyncio
async def test_resolution_loop_rejects_generic_source_quality_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A topical report is not enough when the issue requires primary/official sourcing."""
    source_verdict = _blocking_verdict().model_copy(
        update={
            "verdict_score": 65,
            "verdict_label": "PASS",
            "structured_challenges": [
                AdversarialChallenge(
                    id="source-quality-primary",
                    type="source_quality",
                    severity="blocking",
                    question="Need primary Fed rates source support.",
                    required_resolution="Provide an official primary source for Fed rates.",
                    blocking_pass=True,
                )
            ],
        }
    )

    async def fake_generate_verdict(**_: object) -> SentinelVerdict:
        return source_verdict

    monkeypatch.setattr("sentinel.resolution_loop.generate_verdict", fake_generate_verdict)
    provider = StaticEvidenceProvider(
        {
            "source-quality-primary": [
                EvidenceSearchResult(
                    title="Fed rates analyst report",
                    url="https://example.com/analyst-report",
                    snippet=(
                        "An analyst report discusses Fed rates but does not identify "
                        "primary evidence."
                    ),
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

    assert verdict.verdict_label == "WARN"
    assert verdict.structured_challenges[0].resolution_status == "conceded"


@pytest.mark.asyncio
async def test_resolution_loop_rejects_market_status_evidence_for_wrong_market(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Market-status evidence must mention the trace topic, not just any market."""
    market_verdict = _blocking_verdict().model_copy(
        update={
            "verdict_score": 65,
            "verdict_label": "PASS",
            "structured_challenges": [
                AdversarialChallenge(
                    id="market-structure-status",
                    type="market_structure",
                    severity="blocking",
                    question="Need to confirm the market is active and token-resolved.",
                    required_resolution="Resolve the Polymarket market and token identifiers.",
                    blocking_pass=True,
                )
            ],
        }
    )

    async def fake_generate_verdict(**_: object) -> SentinelVerdict:
        return market_verdict

    monkeypatch.setattr("sentinel.resolution_loop.generate_verdict", fake_generate_verdict)
    provider = StaticEvidenceProvider(
        {
            "market-structure-status": [
                EvidenceSearchResult(
                    title="Fresh Polymarket market matched",
                    url="https://polymarket.com/search?q=unrelated",
                    snippet=(
                        "Polymarket resolved: Will Rizo Velovic win Survivor Season 50? "
                        "fresh CLOB token."
                    ),
                    provider="prism_market_evidence_mcp.search",
                    confidence=1.0,
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

    assert verdict.verdict_label == "WARN"
    assert verdict.structured_challenges[0].resolution_status == "conceded"


@pytest.mark.asyncio
async def test_resolution_loop_accepts_market_status_evidence_for_market_structure_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Market-status evidence can clear market-structure blockers."""
    market_verdict = _blocking_verdict().model_copy(
        update={
            "verdict_score": 65,
            "verdict_label": "PASS",
            "structured_challenges": [
                AdversarialChallenge(
                    id="market-structure-status",
                    type="market_structure",
                    severity="blocking",
                    question="Need to confirm the market is active and token-resolved.",
                    required_resolution="Resolve the Polymarket market and token identifiers.",
                    blocking_pass=True,
                )
            ],
        }
    )

    async def fake_generate_verdict(**_: object) -> SentinelVerdict:
        return market_verdict

    monkeypatch.setattr("sentinel.resolution_loop.generate_verdict", fake_generate_verdict)
    provider = StaticEvidenceProvider(
        {
            "market-structure-status": [
                EvidenceSearchResult(
                    title="Fresh Polymarket market matched",
                    url="https://polymarket.com/search?q=fed",
                    snippet=(
                        "Polymarket gateway resolved the Fed rates question to a fresh binary "
                        "CLOB market. conditionId=0xabc; yesTokenId=123."
                    ),
                    provider="prism_market_evidence_mcp.search",
                    confidence=1.0,
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

    assert verdict.verdict_label == "PASS"
    assert verdict.structured_challenges[0].resolution_status == "resolved"
    assert verdict.challenge_resolutions[0].responder == "evidence_tool"
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
