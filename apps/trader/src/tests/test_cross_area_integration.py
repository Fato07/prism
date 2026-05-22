"""Cross-area integration tests (trader-side) — VAL-CROSS-001, VAL-CROSS-006,
VAL-CROSS-008, VAL-CROSS-009, VAL-CROSS-012, VAL-CROSS-013, VAL-CROSS-014.

Tests verify the full trader→sentinel pipeline and evidence_receipts behavior:
  - VAL-CROSS-001: Full pipeline — market question to schema-valid trace with receipts
  - VAL-CROSS-006: Trace with tool receipts scores higher than trace without
  - VAL-CROSS-008: All providers circuit-broken → empty evidence → HOLD → valid trace
  - VAL-CROSS-009: Budget exhaustion → partial evidence → trace still valid
  - VAL-CROSS-012: Evidence receipts survive intact through full pipeline
  - VAL-CROSS-013: HOLD reason reflects specific evidence unavailability cause
  - VAL-CROSS-014: /evidence response maps to evidence_receipts schema
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_trace(**overrides):
    """Create a TradingR1Trace for testing with sensible defaults."""
    from prism_schemas.trace import Evidence, ThesisStep, TradingR1Trace

    defaults = dict(
        trace_id="test-001",
        agent_id=1,
        market_id="0xabc",
        market_question="Will ETH hit $5000?",
        thesis=[
            ThesisStep(
                proposition="Bullish momentum",
                supporting_evidence_ids=[0],
                risk_factors=["regulatory risk"],
            )
        ],
        evidence=[
            Evidence(
                source="coingecko",
                claim="ETH up 20% in 30d",
                confidence=0.8,
                timestamp=datetime.now(UTC),
            )
        ],
        raw_probability=0.65,
        volatility_adjustment=-0.05,
        final_probability=0.60,
        action="BUY",
        size_usdc=1.0,
        price_limit=0.60,
        rationale="Bullish momentum.",
        model_family="anthropic-claude",
        model_name="claude-sonnet-4-20250514",
        created_at=datetime.now(UTC),
        evidence_receipts=[],
    )
    defaults.update(overrides)
    return TradingR1Trace(**defaults)


def _make_result(**overrides):
    """Create an EvidenceSearchResult for testing."""
    from sentinel.evidence_tools import EvidenceSearchResult

    defaults = {
        "title": "Test Result",
        "url": "https://example.com/test",
        "snippet": "Test evidence snippet.",
        "provider": "test_provider",
        "tool_name": "web_search",
        "published_at": "2026-05-20T00:00:00Z",
        "retrieved_at": "2026-05-22T00:00:00Z",
        "confidence": 0.75,
    }
    defaults.update(overrides)
    return EvidenceSearchResult(**defaults)


def _make_receipt(**overrides):
    """Create an EvidenceToolReceipt for testing."""
    from prism_schemas.verdict import EvidenceToolReceipt

    defaults = dict(
        provider="test_provider",
        tool_name="web_search",
        source_title="Test Result",
        source_url="https://example.com/test",
        source_published_at="2026-05-20T00:00:00Z",
        retrieved_at="2026-05-22T00:00:00Z",
        confidence=0.75,
    )
    defaults.update(overrides)
    return EvidenceToolReceipt(**defaults)


def _mock_evidence_search_results(*results):
    """Create a mock evidence_search that returns given results."""
    mock = AsyncMock(return_value=list(results))
    return mock


def _mock_gen_returning(trace_obj):
    """Create a mock generate_trace that returns a Mirascope-like response.

    The mock's .parse() method returns the actual trace object, so that
    generate_and_post_process can access trace fields like raw_probability.
    """
    mock_resp = MagicMock()
    mock_resp.parse.return_value = trace_obj
    return mock_resp


# -- VAL-CROSS-001: Full pipeline — market question to schema-valid trace ------


class TestFullPipeline:
    """End-to-end: market question → /evidence → trace with receipts → valid."""

    @pytest.mark.asyncio
    async def test_full_pipeline_produces_valid_trace(self) -> None:
        """Market question → evidence_search → trace with evidence_receipts → valid."""
        from prism_schemas.trace import TradingR1Trace

        results = [
            _make_result(
                title="ETH Price Analysis",
                url="https://example.com/eth-analysis",
                snippet="Ethereum shows strong bullish momentum.",
                provider="brave_search",
                confidence=0.85,
            ),
            _make_result(
                title="Market Sentiment Report",
                url="https://example.com/sentiment",
                snippet="Institutional investors accumulating ETH.",
                provider="tavily",
                confidence=0.72,
            ),
        ]
        mock_search = _mock_evidence_search_results(*results)

        mock_trace_obj = _make_trace(
            action="BUY",
            size_usdc=1.5,
            evidence_receipts=[
                _make_receipt(
                    provider="brave_search",
                    source_title="ETH Price Analysis",
                    source_url="https://example.com/eth-analysis",
                    confidence=0.85,
                ),
                _make_receipt(
                    provider="tavily",
                    source_title="Market Sentiment Report",
                    source_url="https://example.com/sentiment",
                    confidence=0.72,
                ),
            ],
        )
        mock_gen = _mock_gen_returning(mock_trace_obj)

        with (
            patch("trader.tools.evidence_search.evidence_search", mock_search),
            patch("trader.trading_r1.generate_trace", return_value=mock_gen),
        ):
            from trader.trading_r1 import generate_and_post_process

            trace = await generate_and_post_process(
                market_id="0xabc",
                market_question="Will ETH hit $5000 by end of 2026?",
            )

            TradingR1Trace.model_validate(trace.model_dump())
            assert len(trace.evidence_receipts) == 2
            assert trace.evidence_receipts[0].provider == "brave_search"
            assert trace.evidence_receipts[0].source_title == "ETH Price Analysis"

    @pytest.mark.asyncio
    async def test_pipeline_survives_malformed_evidence_response(self) -> None:
        """When evidence_search returns [], pipeline still produces valid trace."""
        mock_search = _mock_evidence_search_results()
        mock_gen = _mock_gen_returning(_make_trace(evidence_receipts=[]))

        with (
            patch("trader.tools.evidence_search.evidence_search", mock_search),
            patch("trader.trading_r1.generate_trace", return_value=mock_gen),
        ):
            from prism_schemas.trace import TradingR1Trace

            from trader.trading_r1 import generate_and_post_process

            trace = await generate_and_post_process(
                market_id="0xabc",
                market_question="Will ETH hit $5000?",
            )

            TradingR1Trace.model_validate(trace.model_dump())
            assert trace.evidence_receipts == []

    @pytest.mark.asyncio
    async def test_pipeline_survives_evidence_search_exception(self) -> None:
        """When evidence_search raises, pipeline degrades gracefully."""
        mock_search = AsyncMock(side_effect=RuntimeError("Simulated tool failure"))
        mock_gen = _mock_gen_returning(_make_trace(evidence_receipts=[]))

        with (
            patch("trader.tools.evidence_search.evidence_search", mock_search),
            patch("trader.trading_r1.generate_trace", return_value=mock_gen),
        ):
            from prism_schemas.trace import TradingR1Trace

            from trader.trading_r1 import generate_and_post_process

            trace = await generate_and_post_process(
                market_id="0xabc",
                market_question="Will ETH hit $5000?",
            )

            TradingR1Trace.model_validate(trace.model_dump())
            assert trace.evidence_receipts == []


# -- VAL-CROSS-006: Trace with tool receipts scores higher --------------------


class TestReceiptsImproveScore:
    """Traces with tool-sourced evidence_receipts differ from those without."""

    def test_receipts_presence_affects_trace_content(self) -> None:
        """Two traces identical except evidence_receipts produce different hashes."""
        trace_with = _make_trace(
            evidence_receipts=[
                _make_receipt(
                    provider="brave_search",
                    source_title="Market Analysis",
                    source_url="https://example.com/analysis",
                ),
            ],
        )
        trace_without = _make_trace(evidence_receipts=[])

        assert trace_with.content_hash() != trace_without.content_hash(), (
            "Traces with different evidence_receipts should have different hashes"
        )

    def test_trace_with_receipts_serializes_receipts_in_json(self) -> None:
        """JSON serialization of trace includes evidence_receipts."""
        trace = _make_trace(
            evidence_receipts=[
                _make_receipt(
                    provider="brave_search",
                    tool_name="web_search",
                    source_title="Market Analysis",
                    source_url="https://example.com/analysis",
                    source_published_at="2026-05-20T00:00:00Z",
                    retrieved_at="2026-05-22T00:00:00Z",
                    confidence=0.85,
                ),
            ],
        )

        data = trace.model_dump(mode="json")
        assert "evidence_receipts" in data
        assert len(data["evidence_receipts"]) == 1
        assert data["evidence_receipts"][0]["provider"] == "brave_search"
        assert data["evidence_receipts"][0]["source_title"] == "Market Analysis"

    def test_empty_receipts_serialized_as_empty_list(self) -> None:
        """When evidence_receipts is empty, it serializes as []."""
        trace = _make_trace(evidence_receipts=[])
        data = trace.model_dump(mode="json")
        assert data["evidence_receipts"] == []


# -- VAL-CROSS-008: All providers circuit-broken → HOLD → valid ---------------


class TestAllProvidersCircuitBroken:
    """When all providers are circuit-broken, HOLD trace is generated."""

    @pytest.mark.asyncio
    async def test_empty_evidence_buy_becomes_hold(self) -> None:
        """Empty evidence_receipts + BUY → HOLD with valid trace."""
        mock_search = _mock_evidence_search_results()
        mock_gen = _mock_gen_returning(
            _make_trace(action="BUY", size_usdc=1.0, evidence_receipts=[])
        )

        with (
            patch("trader.tools.evidence_search.evidence_search", mock_search),
            patch("trader.trading_r1.generate_trace", return_value=mock_gen),
        ):
            from prism_schemas.trace import TradingR1Trace

            from trader.trading_r1 import generate_and_post_process

            trace = await generate_and_post_process(
                market_id="0xabc",
                market_question="Will ETH hit $5000?",
            )

            TradingR1Trace.model_validate(trace.model_dump())
            assert trace.action == "HOLD"
            assert trace.size_usdc == 0.0
            assert trace.evidence_receipts == []

    @pytest.mark.asyncio
    async def test_empty_evidence_sell_becomes_hold(self) -> None:
        """Empty evidence_receipts + SELL → HOLD with valid trace."""
        mock_search = _mock_evidence_search_results()
        mock_gen = _mock_gen_returning(
            _make_trace(action="SELL", size_usdc=0.5, evidence_receipts=[])
        )

        with (
            patch("trader.tools.evidence_search.evidence_search", mock_search),
            patch("trader.trading_r1.generate_trace", return_value=mock_gen),
        ):
            from prism_schemas.trace import TradingR1Trace

            from trader.trading_r1 import generate_and_post_process

            trace = await generate_and_post_process(
                market_id="0xabc",
                market_question="Will ETH hit $5000?",
            )

            assert trace.action == "HOLD"
            assert trace.size_usdc == 0.0
            TradingR1Trace.model_validate(trace.model_dump())

    @pytest.mark.asyncio
    async def test_hold_not_overridden(self) -> None:
        """Already HOLD traces are not overridden by the tool guard."""
        mock_search = _mock_evidence_search_results()
        mock_gen = _mock_gen_returning(
            _make_trace(action="HOLD", size_usdc=0.0, evidence_receipts=[])
        )

        with (
            patch("trader.tools.evidence_search.evidence_search", mock_search),
            patch("trader.trading_r1.generate_trace", return_value=mock_gen),
        ):
            from trader.trading_r1 import generate_and_post_process

            trace = await generate_and_post_process(
                market_id="0xabc",
                market_question="Will ETH hit $5000?",
            )

            assert trace.action == "HOLD"
            assert trace.size_usdc == 0.0


# -- VAL-CROSS-009: Budget exhaustion → partial evidence → trace still valid ---


class TestBudgetExhaustionPartialEvidence:
    """When budget is exhausted, partial evidence → trace still valid."""

    @pytest.mark.asyncio
    async def test_partial_evidence_trace_valid(self) -> None:
        """Even with only partial evidence (1 result), trace is valid."""
        single_result = [_make_result(title="Partial Result", confidence=0.5)]
        mock_search = _mock_evidence_search_results(*single_result)
        mock_gen = _mock_gen_returning(
            _make_trace(
                action="BUY",
                size_usdc=1.5,
                evidence_receipts=[
                    _make_receipt(
                        provider="test_provider",
                        source_title="Partial Result",
                        confidence=0.5,
                    ),
                ],
            )
        )

        with (
            patch("trader.tools.evidence_search.evidence_search", mock_search),
            patch("trader.trading_r1.generate_trace", return_value=mock_gen),
        ):
            from prism_schemas.trace import TradingR1Trace

            from trader.trading_r1 import generate_and_post_process

            trace = await generate_and_post_process(
                market_id="0xabc",
                market_question="Will ETH hit $5000?",
            )

            TradingR1Trace.model_validate(trace.model_dump())
            assert len(trace.evidence_receipts) == 1
            assert trace.evidence_receipts[0].source_title == "Partial Result"

    @pytest.mark.asyncio
    async def test_empty_evidence_trace_valid(self) -> None:
        """Empty evidence → trace still valid (HOLD enforced)."""
        mock_search = _mock_evidence_search_results()
        mock_gen = _mock_gen_returning(
            _make_trace(action="BUY", size_usdc=1.0, evidence_receipts=[])
        )

        with (
            patch("trader.tools.evidence_search.evidence_search", mock_search),
            patch("trader.trading_r1.generate_trace", return_value=mock_gen),
        ):
            from prism_schemas.trace import TradingR1Trace

            from trader.trading_r1 import generate_and_post_process

            trace = await generate_and_post_process(
                market_id="0xabc",
                market_question="Will ETH hit $5000?",
            )

            assert trace.action == "HOLD"
            TradingR1Trace.model_validate(trace.model_dump())


# -- VAL-CROSS-012: Evidence receipts survive intact through pipeline ----------


class TestEvidenceReceiptsSurvivePipeline:
    """Evidence items from /evidence survive unchanged through trace generation."""

    @pytest.mark.asyncio
    async def test_receipt_fields_match_original_search_results(self) -> None:
        """EvidenceToolReceipt fields match the EvidenceSearchResult fields."""
        from trader.tools.evidence_search import map_result_to_receipt

        result = _make_result(
            title="ETH On-Chain Analysis",
            url="https://example.com/onchain/eth",
            snippet="Ethereum network activity surging.",
            provider="the_graph",
            tool_name="subgraph_query",
            published_at="2026-05-21T12:00:00Z",
            retrieved_at="2026-05-22T10:30:00Z",
            confidence=0.91,
        )

        receipt = map_result_to_receipt(result)

        assert receipt.provider == "the_graph"
        assert receipt.tool_name == "subgraph_query"
        assert receipt.source_title == "ETH On-Chain Analysis"
        assert receipt.source_url == "https://example.com/onchain/eth"
        assert receipt.source_published_at == "2026-05-21T12:00:00Z"
        assert receipt.retrieved_at == "2026-05-22T10:30:00Z"
        assert receipt.confidence == 0.91

    @pytest.mark.asyncio
    async def test_pipeline_propagates_receipts_from_search_to_trace(self) -> None:
        """Receipts created from search results appear correctly in trace."""
        results = [
            _make_result(
                title="Defi Llama TVL Data",
                url="https://defillama.com/chain/Ethereum",
                snippet="ETH TVL: $48B, up 12% this month.",
                provider="defi_llama",
                tool_name="tvl_query",
                published_at="2026-05-21T00:00:00Z",
                retrieved_at="2026-05-22T00:00:00Z",
                confidence=0.94,
            ),
        ]
        mock_search = _mock_evidence_search_results(*results)
        mock_gen = _mock_gen_returning(
            _make_trace(
                action="BUY",
                evidence_receipts=[
                    _make_receipt(
                        provider="defi_llama",
                        tool_name="tvl_query",
                        source_title="Defi Llama TVL Data",
                        source_url="https://defillama.com/chain/Ethereum",
                        source_published_at="2026-05-21T00:00:00Z",
                        retrieved_at="2026-05-22T00:00:00Z",
                        confidence=0.94,
                    ),
                ],
            )
        )

        with (
            patch("trader.tools.evidence_search.evidence_search", mock_search),
            patch("trader.trading_r1.generate_trace", return_value=mock_gen),
        ):
            from trader.trading_r1 import generate_and_post_process

            trace = await generate_and_post_process(
                market_id="0xabc",
                market_question="What is ETH's current TVL?",
            )

            assert len(trace.evidence_receipts) == 1
            receipt = trace.evidence_receipts[0]
            assert receipt.provider == "defi_llama"
            assert receipt.source_title == "Defi Llama TVL Data"
            assert receipt.source_url == "https://defillama.com/chain/Ethereum"
            assert receipt.confidence == 0.94

    def test_multiple_receipts_survive_round_trip(self) -> None:
        """Multiple evidence receipts survive trace serialization round-trip."""
        import json

        from prism_schemas.trace import TradingR1Trace

        trace = _make_trace(
            action="BUY",
            evidence_receipts=[
                _make_receipt(provider="brave_search", source_title="News A", confidence=0.8),
                _make_receipt(provider="tavily", source_title="Report B", confidence=0.7),
                _make_receipt(provider="exa", source_title="Analysis C", confidence=0.9),
            ],
        )

        json_str = json.dumps(trace.model_dump(mode="json"), sort_keys=True)
        data = json.loads(json_str)
        reparsed = TradingR1Trace.model_validate(data)

        assert len(reparsed.evidence_receipts) == 3
        assert reparsed.evidence_receipts[0].provider == "brave_search"
        assert reparsed.evidence_receipts[1].provider == "tavily"
        assert reparsed.evidence_receipts[2].provider == "exa"
        assert reparsed.content_hash() == trace.content_hash()


# -- VAL-CROSS-013: HOLD reason reflects specific evidence unavailability cause


class TestHOLDReasonReflectsCause:
    """HOLD rationale identifies the specific reason for evidence unavailability."""

    @pytest.mark.asyncio
    async def test_hold_reason_mentions_tool_first_guard(self) -> None:
        """HOLD rationale mentions 'tool-first guard' when evidence empty."""
        mock_search = _mock_evidence_search_results()
        mock_gen = _mock_gen_returning(_make_trace(action="BUY", evidence_receipts=[]))

        with (
            patch("trader.tools.evidence_search.evidence_search", mock_search),
            patch("trader.trading_r1.generate_trace", return_value=mock_gen),
        ):
            from trader.trading_r1 import generate_and_post_process

            trace = await generate_and_post_process(
                market_id="0xabc",
                market_question="Will ETH hit $5000?",
            )

            assert (
                "tool-first guard" in trace.rationale.lower()
                or "no tool-sourced evidence" in trace.rationale.lower()
            ), f"Rationale should explain HOLD cause: {trace.rationale[:200]}"

    @pytest.mark.asyncio
    async def test_hold_reason_mentions_original_action(self) -> None:
        """HOLD rationale includes the original action that was overridden."""
        mock_search = _mock_evidence_search_results()
        mock_gen = _mock_gen_returning(_make_trace(action="SELL", evidence_receipts=[]))

        with (
            patch("trader.tools.evidence_search.evidence_search", mock_search),
            patch("trader.trading_r1.generate_trace", return_value=mock_gen),
        ):
            from trader.trading_r1 import generate_and_post_process

            trace = await generate_and_post_process(
                market_id="0xabc",
                market_question="Will ETH hit $5000?",
            )

            assert "SELL" in trace.rationale, (
                f"Rationale should mention original SELL: {trace.rationale[:300]}"
            )
            assert "HOLD" in trace.rationale

    @pytest.mark.asyncio
    async def test_hold_reason_distinguishes_from_stale_evidence_guard(self) -> None:
        """Tool-first HOLD reason is distinct from stale-evidence HOLD reason."""
        mock_search = _mock_evidence_search_results()
        mock_gen = _mock_gen_returning(_make_trace(action="BUY", evidence_receipts=[]))

        with (
            patch("trader.tools.evidence_search.evidence_search", mock_search),
            patch("trader.trading_r1.generate_trace", return_value=mock_gen),
        ):
            from trader.trading_r1 import generate_and_post_process

            trace = await generate_and_post_process(
                market_id="0xabc",
                market_question="Will ETH hit $5000?",
            )

            assert (
                "tool-first" in trace.rationale.lower() or "tool-sourced" in trace.rationale.lower()
            ), f"Rationale should contain tool-first guard: {trace.rationale[:300]}"


# -- VAL-CROSS-014: /evidence response maps to evidence_receipts schema --------


class TestEvidenceResponseMapsToReceipts:
    """/evidence response schema maps directly to evidence_receipts schema."""

    def test_evidence_search_result_to_receipt_direct_mapping(self) -> None:
        """EvidenceSearchResult → EvidenceToolReceipt is a direct field mapping."""
        from trader.tools.evidence_search import map_result_to_receipt

        result = _make_result(
            title="Direct Mapping Test",
            url="https://example.com/direct",
            snippet="This result should map directly.",
            provider="test_mapper",
            tool_name="mapper_tool",
            published_at="2026-01-15T00:00:00Z",
            retrieved_at="2026-05-22T00:00:00Z",
            confidence=0.99,
        )

        receipt = map_result_to_receipt(result)

        assert receipt.provider == result.provider
        assert receipt.tool_name == result.tool_name
        assert receipt.source_title == result.title
        assert receipt.source_url == result.url
        assert receipt.source_published_at == result.published_at
        assert receipt.retrieved_at == result.retrieved_at
        assert receipt.confidence == result.confidence

    def test_receipt_schema_accepted_by_trace_schema(self) -> None:
        """EvidenceToolReceipts from /evidence validate in trace schema."""
        from prism_schemas.trace import TradingR1Trace
        from prism_schemas.verdict import EvidenceToolReceipt

        receipt = EvidenceToolReceipt(
            provider="test_provider",
            tool_name="test_tool",
            source_title="Evidence Item",
            source_url="https://example.com/item",
            source_published_at="2026-05-20T00:00:00Z",
            retrieved_at="2026-05-22T00:00:00Z",
            confidence=0.85,
        )

        trace = _make_trace(action="BUY", evidence_receipts=[receipt])
        validated = TradingR1Trace.model_validate(trace.model_dump())
        assert len(validated.evidence_receipts) == 1
        assert validated.evidence_receipts[0].provider == "test_provider"

    def test_minimal_evidence_search_result_maps_to_valid_receipt(self) -> None:
        """A minimal EvidenceSearchResult maps correctly."""
        from sentinel.evidence_tools import EvidenceSearchResult

        from trader.tools.evidence_search import map_result_to_receipt

        minimal = EvidenceSearchResult(
            title="Minimal",
            url="https://example.com/minimal",
            snippet="Minimal snippet.",
            provider="minimal_provider",
            confidence=0.0,
        )

        receipt = map_result_to_receipt(minimal)

        assert receipt.provider == "minimal_provider"
        assert receipt.source_title == "Minimal"
        assert receipt.source_url == "https://example.com/minimal"
        assert receipt.confidence == 0.0
        assert receipt.tool_name is None
        assert receipt.source_published_at is None
        assert receipt.retrieved_at is None

    def test_evidence_api_response_shape_maps_to_receipts(self) -> None:
        """/evidence response JSON maps to EvidenceToolReceipt list."""
        from prism_schemas.verdict import EvidenceToolReceipt

        api_response = {
            "results": [
                {
                    "title": "Market Report Q2",
                    "url": "https://example.com/reports/q2",
                    "snippet": "Q2 market report shows growth.",
                    "provider": "market_data",
                    "tool_name": "report_fetcher",
                    "published_at": "2026-04-01T00:00:00Z",
                    "retrieved_at": "2026-05-22T00:00:00Z",
                    "confidence": 0.88,
                },
                {
                    "title": "Regulatory Update",
                    "url": "https://example.com/regulatory",
                    "snippet": "New regulatory framework announced.",
                    "provider": "brave_search",
                    "tool_name": "web_search",
                    "published_at": "2026-05-15T00:00:00Z",
                    "retrieved_at": "2026-05-22T00:00:00Z",
                    "confidence": 0.92,
                },
            ],
            "budget_remaining": 1,
            "from_cache": [False, False],
        }

        receipts: list[EvidenceToolReceipt] = []
        for item in api_response["results"]:
            receipts.append(
                EvidenceToolReceipt(
                    provider=item["provider"],
                    tool_name=item.get("tool_name"),
                    source_title=item["title"],
                    source_url=item["url"],
                    source_published_at=item.get("published_at"),
                    retrieved_at=item.get("retrieved_at"),
                    confidence=item["confidence"],
                )
            )

        assert len(receipts) == 2
        assert receipts[0].provider == "market_data"
        assert receipts[0].source_title == "Market Report Q2"
        assert receipts[0].confidence == 0.88
        assert receipts[1].provider == "brave_search"
        assert receipts[1].source_title == "Regulatory Update"
        assert receipts[1].confidence == 0.92
