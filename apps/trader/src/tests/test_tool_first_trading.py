"""Tests for tool-first trace generation — VAL-TOOL-014 through VAL-TOOL-021.

Tests cover:
  - VAL-TOOL-014: evidence_search called before generate_trace
  - VAL-TOOL-015: Retrieved evidence injected into Mirascope prompt
  - VAL-TOOL-016: Trace contains evidence_receipts with tool receipts
  - VAL-TOOL-017: Trace evidence_receipts empty when no evidence retrieved
  - VAL-TOOL-018: Trader forces HOLD when evidence_receipts empty and BUY/SELL
  - VAL-TOOL-019: HOLD-forcing preserves original action in rationale
  - VAL-TOOL-020: HOLD-forcing guard independent of stale-evidence guard
  - VAL-TOOL-021: Evidence search timeout does not block trace generation
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import httpx
import pytest

from trader.prompts import build_evidence_context

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
        "confidence": 0.75,
    }
    defaults.update(overrides)
    return EvidenceSearchResult(**defaults)


def _make_fresh_evidence():
    """Make a fresh (non-stale) Evidence object."""
    from prism_schemas.trace import Evidence

    return Evidence(
        source="coingecko",
        claim="ETH up 20% in 30d",
        confidence=0.8,
        timestamp=datetime.now(UTC),
    )


def _make_old_evidence():
    """Make an old (stale, >365 days) Evidence object."""
    from prism_schemas.trace import Evidence

    return Evidence(
        source="historical source",
        claim="Historical claim",
        confidence=0.8,
        timestamp=datetime(2024, 1, 15, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# VAL-TOOL-014: evidence_search called before generate_trace
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evidence_search_called_before_llm() -> None:
    """evidence_search is called before generate_trace(). LLM still proceeds."""
    mock_trace = _make_trace(action="BUY")

    mock_response = MagicMock()
    mock_response.parse.return_value = mock_trace

    with (
        patch("trader.trading_r1.generate_trace", return_value=mock_response) as mock_gen,
        patch("trader.tools.evidence_search.evidence_search") as mock_search,
    ):
        mock_search.return_value = []  # Return empty evidence

        from trader.trading_r1 import generate_and_post_process

        trace = await generate_and_post_process(
            market_id="0xtest",
            market_question="Will ETH hit $5000?",
        )

        # evidence_search should have been called
        mock_search.assert_called_once()
        # generate_trace should still have been called (even with empty evidence)
        mock_gen.assert_called_once()
        # Trace should be valid
        assert trace.market_id == "0xtest"


@pytest.mark.asyncio
async def test_llm_proceeds_when_evidence_search_fails() -> None:
    """When evidence_search raises, LLM generation still proceeds."""
    mock_trace = _make_trace(action="HOLD")

    mock_response = MagicMock()
    mock_response.parse.return_value = mock_trace

    with (
        patch("trader.trading_r1.generate_trace", return_value=mock_response) as mock_gen,
        patch("trader.tools.evidence_search.evidence_search") as mock_search,
    ):
        mock_search.side_effect = RuntimeError("simulated failure")

        from trader.trading_r1 import generate_and_post_process

        trace = await generate_and_post_process(
            market_id="0xtest",
            market_question="Will ETH hit $5000?",
        )

        # evidence_search was called (and failed)
        mock_search.assert_called_once()
        # generate_trace still called — degraded mode
        mock_gen.assert_called_once()
        # Trace is valid
        assert trace.action == "HOLD"


# ---------------------------------------------------------------------------
# VAL-TOOL-015: Retrieved evidence injected into Mirascope prompt
# ---------------------------------------------------------------------------


def test_evidence_context_present_when_results_non_empty() -> None:
    """When evidence_search returns results, evidence_context is non-empty."""
    results = [
        _make_result(title="Result A"),
        _make_result(title="Result B"),
    ]
    context = build_evidence_context(results)
    assert "TOOL-SOURCED EVIDENCE" in context
    assert "Result A" in context
    assert "Result B" in context
    assert "test_provider" in context


def test_evidence_context_absent_when_results_empty() -> None:
    """When search_results is empty, evidence_context is empty string."""
    assert build_evidence_context([]) == ""


@pytest.mark.asyncio
async def test_evidence_injected_into_prompt() -> None:
    """Evidence context is passed to generate_trace when results are available."""
    results = [_make_result(title="Injected Evidence")]
    mock_trace = _make_trace(action="BUY")

    mock_response = MagicMock()
    mock_response.parse.return_value = mock_trace

    with (
        patch("trader.trading_r1.generate_trace", return_value=mock_response) as mock_gen,
        patch("trader.tools.evidence_search.evidence_search", return_value=results),
    ):
        from trader.trading_r1 import generate_and_post_process

        await generate_and_post_process(
            market_id="0xtest",
            market_question="Will ETH hit $5000?",
        )

        # generate_trace should have been called with non-empty evidence_context
        call_kwargs = mock_gen.call_args.kwargs
        assert call_kwargs["evidence_context"] != ""
        assert "Injected Evidence" in call_kwargs["evidence_context"]


@pytest.mark.asyncio
async def test_evidence_context_empty_when_no_results() -> None:
    """Evidence context is empty string when no results from evidence_search."""
    mock_trace = _make_trace(action="BUY")

    mock_response = MagicMock()
    mock_response.parse.return_value = mock_trace

    with (
        patch("trader.trading_r1.generate_trace", return_value=mock_response) as mock_gen,
        patch("trader.tools.evidence_search.evidence_search", return_value=[]),
    ):
        from trader.trading_r1 import generate_and_post_process

        await generate_and_post_process(
            market_id="0xtest",
            market_question="Will ETH hit $5000?",
        )

        call_kwargs = mock_gen.call_args.kwargs
        assert call_kwargs["evidence_context"] == ""


# ---------------------------------------------------------------------------
# VAL-TOOL-016: Trace contains evidence_receipts with tool receipts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trace_has_evidence_receipts_when_evidence_retrieved() -> None:
    """Trace has non-empty evidence_receipts when evidence_search returns results."""
    results = [
        _make_result(
            title="Evidence A",
            provider="brave_search",
            tool_name="web_search",
            url="https://example.com/a",
            confidence=0.85,
            published_at="2026-05-20T00:00:00Z",
            retrieved_at="2026-05-22T00:00:00Z",
        ),
    ]
    mock_trace = _make_trace(action="BUY")

    mock_response = MagicMock()
    mock_response.parse.return_value = mock_trace

    with (
        patch("trader.trading_r1.generate_trace", return_value=mock_response),
        patch("trader.tools.evidence_search.evidence_search", return_value=results),
    ):
        from trader.trading_r1 import generate_and_post_process

        trace = await generate_and_post_process(
            market_id="0xtest",
            market_question="Will ETH hit $5000?",
        )

        assert len(trace.evidence_receipts) == 1
        receipt = trace.evidence_receipts[0]
        assert receipt.provider == "brave_search"
        assert receipt.source_title == "Evidence A"
        assert receipt.source_url == "https://example.com/a"
        assert receipt.confidence == 0.85


# ---------------------------------------------------------------------------
# VAL-TOOL-017: Trace evidence_receipts empty when no evidence retrieved
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trace_evidence_receipts_empty_when_no_evidence() -> None:
    """Trace evidence_receipts is [] when evidence_search returns []."""
    mock_trace = _make_trace(action="BUY")

    mock_response = MagicMock()
    mock_response.parse.return_value = mock_trace

    with (
        patch("trader.trading_r1.generate_trace", return_value=mock_response),
        patch("trader.tools.evidence_search.evidence_search", return_value=[]),
    ):
        from trader.trading_r1 import generate_and_post_process

        trace = await generate_and_post_process(
            market_id="0xtest",
            market_question="Will ETH hit $5000?",
        )

        assert trace.evidence_receipts == []
        # Trace still valid
        assert trace.market_id == "0xtest"


# ---------------------------------------------------------------------------
# VAL-TOOL-018: Trader forces HOLD when evidence_receipts empty and BUY/SELL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_buy_with_empty_receipts_forced_to_hold() -> None:
    """BUY + empty evidence_receipts → HOLD."""
    mock_trace = _make_trace(
        action="BUY",
        size_usdc=1.0,
        price_limit=0.60,
        raw_probability=0.65,
        final_probability=0.60,
        evidence=[_make_fresh_evidence()],
    )

    mock_response = MagicMock()
    mock_response.parse.return_value = mock_trace

    with (
        patch("trader.trading_r1.generate_trace", return_value=mock_response),
        patch("trader.tools.evidence_search.evidence_search", return_value=[]),
    ):
        from trader.trading_r1 import generate_and_post_process

        trace = await generate_and_post_process(
            market_id="0xtest",
            market_question="Will ETH hit $5000?",
        )

        assert trace.action == "HOLD"
        assert trace.size_usdc == 0.0
        assert trace.price_limit == 0.5


@pytest.mark.asyncio
async def test_sell_with_empty_receipts_forced_to_hold() -> None:
    """SELL + empty evidence_receipts → HOLD."""
    mock_trace = _make_trace(
        action="SELL",
        size_usdc=1.0,
        price_limit=0.40,
        raw_probability=0.35,
        final_probability=0.30,
        evidence=[_make_fresh_evidence()],
    )

    mock_response = MagicMock()
    mock_response.parse.return_value = mock_trace

    with (
        patch("trader.trading_r1.generate_trace", return_value=mock_response),
        patch("trader.tools.evidence_search.evidence_search", return_value=[]),
    ):
        from trader.trading_r1 import generate_and_post_process

        trace = await generate_and_post_process(
            market_id="0xtest",
            market_question="Will ETH hit $5000?",
        )

        assert trace.action == "HOLD"
        assert trace.size_usdc == 0.0
        assert trace.price_limit == 0.5


@pytest.mark.asyncio
async def test_hold_already_not_overridden_by_tool_guard() -> None:
    """HOLD action is left alone by the tool-first guard (no double-guard)."""
    mock_trace = _make_trace(action="HOLD", size_usdc=0.0, price_limit=0.5)

    mock_response = MagicMock()
    mock_response.parse.return_value = mock_trace

    with (
        patch("trader.trading_r1.generate_trace", return_value=mock_response),
        patch("trader.tools.evidence_search.evidence_search", return_value=[]),
    ):
        from trader.trading_r1 import generate_and_post_process

        trace = await generate_and_post_process(
            market_id="0xtest",
            market_question="Will ETH hit $5000?",
        )

        assert trace.action == "HOLD"


# ---------------------------------------------------------------------------
# VAL-TOOL-019: HOLD-forcing preserves original action in rationale
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hold_guard_preserves_original_buy_in_rationale() -> None:
    """Rationale includes 'BUY' when a BUY action is forced to HOLD."""
    mock_trace = _make_trace(action="BUY", evidence=[_make_fresh_evidence()])

    mock_response = MagicMock()
    mock_response.parse.return_value = mock_trace

    with (
        patch("trader.trading_r1.generate_trace", return_value=mock_response),
        patch("trader.tools.evidence_search.evidence_search", return_value=[]),
    ):
        from trader.trading_r1 import generate_and_post_process

        trace = await generate_and_post_process(
            market_id="0xtest",
            market_question="Will ETH hit $5000?",
        )

        assert "BUY" in trace.rationale
        assert "HOLD" in trace.rationale
        assert "tool-first guard" in trace.rationale


@pytest.mark.asyncio
async def test_hold_guard_preserves_original_sell_in_rationale() -> None:
    """Rationale includes 'SELL' when a SELL action is forced to HOLD."""
    mock_trace = _make_trace(action="SELL", evidence=[_make_fresh_evidence()])

    mock_response = MagicMock()
    mock_response.parse.return_value = mock_trace

    with (
        patch("trader.trading_r1.generate_trace", return_value=mock_response),
        patch("trader.tools.evidence_search.evidence_search", return_value=[]),
    ):
        from trader.trading_r1 import generate_and_post_process

        trace = await generate_and_post_process(
            market_id="0xtest",
            market_question="Will ETH hit $5000?",
        )

        assert "SELL" in trace.rationale
        assert "HOLD" in trace.rationale
        assert "tool-first guard" in trace.rationale


# ---------------------------------------------------------------------------
# VAL-TOOL-020: HOLD-forcing guard independent of stale-evidence guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fresh_evidence_with_receipts_no_guard() -> None:
    """Fresh evidence + receipts → no guard applied. Action unchanged."""
    results = [_make_result(title="Fresh evidence")]
    mock_trace = _make_trace(
        action="BUY",
        evidence=[_make_fresh_evidence()],
    )

    mock_response = MagicMock()
    mock_response.parse.return_value = mock_trace

    with (
        patch("trader.trading_r1.generate_trace", return_value=mock_response),
        patch("trader.tools.evidence_search.evidence_search", return_value=results),
    ):
        from trader.trading_r1 import generate_and_post_process

        trace = await generate_and_post_process(
            market_id="0xtest",
            market_question="Will ETH hit $5000?",
        )

        # Should still be BUY — fresh evidence + tool receipts present
        assert trace.action == "BUY"


@pytest.mark.asyncio
async def test_stale_evidence_with_receipts_only_stale_guard() -> None:
    """Stale evidence + receipts → only stale guard fires."""
    results = [_make_result(title="Tool evidence")]
    mock_trace = _make_trace(
        action="BUY",
        evidence=[_make_old_evidence()],
    )

    mock_response = MagicMock()
    mock_response.parse.return_value = mock_trace

    with (
        patch("trader.trading_r1.generate_trace", return_value=mock_response),
        patch("trader.tools.evidence_search.evidence_search", return_value=results),
    ):
        from trader.trading_r1 import generate_and_post_process

        trace = await generate_and_post_process(
            market_id="0xtest",
            market_question="Will ETH hit $5000?",
        )

        assert trace.action == "HOLD"
        assert "all cited evidence is stale" in trace.rationale
        # Tool-first guard should NOT be in rationale (we had receipts)
        assert "tool-first guard" not in trace.rationale


@pytest.mark.asyncio
async def test_fresh_evidence_no_receipts_buy_tool_guard_only() -> None:
    """Fresh evidence + no receipts + BUY → only tool guard fires."""
    mock_trace = _make_trace(
        action="BUY",
        evidence=[_make_fresh_evidence()],
    )

    mock_response = MagicMock()
    mock_response.parse.return_value = mock_trace

    with (
        patch("trader.trading_r1.generate_trace", return_value=mock_response),
        patch("trader.tools.evidence_search.evidence_search", return_value=[]),
    ):
        from trader.trading_r1 import generate_and_post_process

        trace = await generate_and_post_process(
            market_id="0xtest",
            market_question="Will ETH hit $5000?",
        )

        assert trace.action == "HOLD"
        assert "tool-first guard" in trace.rationale
        # Stale guard should NOT be in rationale (evidence is fresh)
        assert "all cited evidence is stale" not in trace.rationale


@pytest.mark.asyncio
async def test_stale_evidence_no_receipts_both_guards_fire() -> None:
    """Stale evidence + no receipts + BUY → both guards fire."""
    mock_trace = _make_trace(
        action="BUY",
        evidence=[_make_old_evidence()],
    )

    mock_response = MagicMock()
    mock_response.parse.return_value = mock_trace

    with (
        patch("trader.trading_r1.generate_trace", return_value=mock_response),
        patch("trader.tools.evidence_search.evidence_search", return_value=[]),
    ):
        from trader.trading_r1 import generate_and_post_process

        trace = await generate_and_post_process(
            market_id="0xtest",
            market_question="Will ETH hit $5000?",
        )

        assert trace.action == "HOLD"
        assert "all cited evidence is stale" in trace.rationale
        assert "tool-first guard" in trace.rationale


# ---------------------------------------------------------------------------
# VAL-TOOL-021: Evidence search timeout does not block trace generation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evidence_search_delay_does_not_block_trace() -> None:
    """When evidence_search errors, trace still completes."""
    mock_trace = _make_trace(action="HOLD")

    mock_response = MagicMock()
    mock_response.parse.return_value = mock_trace

    with (
        patch("trader.trading_r1.generate_trace", return_value=mock_response) as mock_gen,
        patch("trader.tools.evidence_search.evidence_search") as mock_search,
    ):
        mock_search.side_effect = httpx.TimeoutException("Timeout")

        from trader.trading_r1 import generate_and_post_process

        trace = await generate_and_post_process(
            market_id="0xtest",
            market_question="Will ETH hit $5000?",
        )

        # evidence_search was called
        mock_search.assert_called_once()
        # generate_trace was still called
        mock_gen.assert_called_once()
        # Trace is valid
        assert trace.action == "HOLD"
        assert trace.evidence_receipts == []
