"""Sentinel calibration gate -- VAL-SENTINEL-007 through VAL-SENTINEL-010.

Creates 3 synthetic TradingR1Trace fixtures (good, mediocre, bad) and
runs the sentinel's DSPy/GPT adversarial validator on each.  Asserts:

  - Good trace     -> verdict_score in [60, 100]  (VAL-SENTINEL-007)
  - Mediocre trace -> verdict_score in [30, 60]   (VAL-SENTINEL-008)
  - Bad trace      -> verdict_score in [0, 40]    (VAL-SENTINEL-009)
  - good_score - bad_score >= 30                  (VAL-SENTINEL-010)
  - bad_score < mediocre_score < good_score       (VAL-SENTINEL-010)

These tests call the REAL OpenAI API via DSPy.  They are marked
``@pytest.mark.integration`` and require ``OPENAI_API_KEY`` in the
environment.  If calibration fails, the orchestrator must decide whether
to swap the sentinel model before Day 4 work proceeds.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime

import pytest
from prism_schemas.trace import Evidence, ThesisStep, TradingR1Trace

from sentinel.adversarial import generate_verdict

# ---------------------------------------------------------------------------
# Synthetic trace fixtures
# ---------------------------------------------------------------------------


def _good_trace() -> TradingR1Trace:
    """Well-reasoned trace with strong evidence and calibrated probabilities.

    Characteristics:
    - Multi-step thesis with logical chain
    - 4 evidence items from reputable, diverse sources
    - Confidence levels calibrated to claim strength
    - Probability adjustments justified
    - Clear risk factors identified
    - Reasonable position sizing
    """
    return TradingR1Trace(
        trace_id=str(uuid.uuid4()),
        agent_id=1,
        market_id="poly-2026-fed-rate-cut",
        market_question=(
            "Will the US Federal Reserve cut rates by at least 25bps before July 2026?"
        ),
        thesis=[
            ThesisStep(
                proposition=(
                    "Inflation has been trending below the Fed's 2% target "
                    "for 3 consecutive quarters, creating pressure for a rate cut."
                ),
                supporting_evidence_ids=[0, 1],
                risk_factors=[
                    "Inflation could rebound due to energy price spikes",
                    "Fed may prefer to wait for more data",
                ],
            ),
            ThesisStep(
                proposition=(
                    "Labor market softening (unemployment rising from 3.7% to "
                    "4.2%) gives the Fed dual-mandate justification to ease."
                ),
                supporting_evidence_ids=[1, 2],
                risk_factors=[
                    "Unemployment rise may stall",
                    "Wage growth remains elevated",
                ],
            ),
            ThesisStep(
                proposition=(
                    "Forward guidance from the March 2026 FOMC minutes signals "
                    "openness to a summer cut if data cooperates."
                ),
                supporting_evidence_ids=[2, 3],
                risk_factors=[
                    "Forward guidance is not a commitment",
                    "Data may not cooperate",
                ],
            ),
        ],
        evidence=[
            Evidence(
                source="Bureau of Labor Statistics - CPI Report (Feb 2026)",
                claim=(
                    "Core PCE inflation at 1.8% YoY, below 2% target for 3rd consecutive quarter."
                ),
                confidence=0.92,
                timestamp=datetime(2026, 2, 15, tzinfo=UTC),
            ),
            Evidence(
                source="Federal Reserve - FOMC Statement (Jan 2026)",
                claim=(
                    "Committee acknowledges progress on inflation and notes "
                    "balanced risks to dual mandate."
                ),
                confidence=0.88,
                timestamp=datetime(2026, 1, 29, tzinfo=UTC),
            ),
            Evidence(
                source=("Bureau of Labor Statistics - Employment Situation (Mar 2026)"),
                claim=(
                    "Unemployment rate rose to 4.2% from 3.7% six months "
                    "prior; job openings declined 15%."
                ),
                confidence=0.85,
                timestamp=datetime(2026, 3, 7, tzinfo=UTC),
            ),
            Evidence(
                source="Federal Reserve - FOMC Minutes (Mar 2026)",
                claim=(
                    "Several participants indicated willingness to support a "
                    "25bp cut at a future meeting if inflation data remain "
                    "subdued."
                ),
                confidence=0.80,
                timestamp=datetime(2026, 3, 18, tzinfo=UTC),
            ),
        ],
        raw_probability=0.68,
        volatility_adjustment=-0.05,
        final_probability=0.63,
        action="BUY",
        size_usdc=15.0,
        price_limit=0.63,
        rationale=(
            "Strong fundamental case: inflation below target for 3 quarters, "
            "labor market softening, and explicit forward guidance from FOMC "
            "participants signaling openness to a cut. Probability modestly "
            "above 50% reflects residual uncertainty around data dependency "
            "and potential for inflation rebound. Position sized at 15 USDC "
            "(well within 25% balance cap) to manage tail risk."
        ),
        model_family="anthropic-claude",
        model_name="claude-sonnet-4-20250514",
        created_at=datetime.now(UTC),
    )


def _mediocre_trace() -> TradingR1Trace:
    """Trace with some reasoning gaps and 1-2 weak evidence claims.

    Characteristics:
    - Thesis has logical gaps (circular reasoning, unsupported leaps)
    - 2 evidence items from mediocre/weak sources
    - Confidence overstated on weak evidence (0.90 on a forum post)
    - Volatility adjustment arbitrary and contradicts thesis direction
    - Missing risk factors (empty list for second thesis step)
    - Rationale is thin, doesn't connect evidence to action
    - No mention of alternative scenarios or contrary evidence
    - Action (BUY) contradicts the downward probability adjustment
    """
    return TradingR1Trace(
        trace_id=str(uuid.uuid4()),
        agent_id=1,
        market_id="poly-2026-fed-rate-cut",
        market_question=(
            "Will the US Federal Reserve cut rates by at least 25bps before July 2026?"
        ),
        thesis=[
            ThesisStep(
                proposition=(
                    "The Fed will cut rates because inflation is probably going to keep going down."
                ),
                supporting_evidence_ids=[0],
                risk_factors=["Inflation might change"],
            ),
            ThesisStep(
                proposition=("A rate cut is likely since the market seems to expect it."),
                supporting_evidence_ids=[1],
                risk_factors=[],
            ),
        ],
        evidence=[
            Evidence(
                source="Financial blog post on Substack - 'MacroTrends Weekly'",
                claim=(
                    "Some indicators suggest inflation might be easing, "
                    "though the data is mixed and recent months showed "
                    "slight upticks."
                ),
                confidence=0.70,
                timestamp=datetime(2026, 2, 20, tzinfo=UTC),
            ),
            Evidence(
                source="Reddit r/economics discussion thread",
                claim=(
                    "Commenters generally think a rate cut is coming, "
                    "based on their reading of market signals."
                ),
                confidence=0.90,
                timestamp=datetime(2026, 3, 10, tzinfo=UTC),
            ),
        ],
        raw_probability=0.55,
        volatility_adjustment=-0.15,
        final_probability=0.40,
        rationale=(
            "Seems like inflation is going down and people expect a cut. "
            "Going with BUY. The -0.15 adjustment is for uncertainty but "
            "I still think BUY is right."
        ),
        action="BUY",
        size_usdc=20.0,
        price_limit=0.40,
        model_family="anthropic-claude",
        model_name="claude-sonnet-4-20250514",
        created_at=datetime.now(UTC),
    )


def _bad_trace() -> TradingR1Trace:
    """Trace with poor reasoning, weak evidence, and uncalibrated probability.

    Characteristics:
    - Single-step thesis with no logical chain
    - 1 evidence item from an unreliable source
    - Confidence overstated for weak evidence
    - Probability arbitrarily set without justification
    - No meaningful risk factors
    - Large position size relative to conviction
    - Volatility adjustment contradicts the thesis
    """
    return TradingR1Trace(
        trace_id=str(uuid.uuid4()),
        agent_id=1,
        market_id="poly-2026-fed-rate-cut",
        market_question=(
            "Will the US Federal Reserve cut rates by at least 25bps before July 2026?"
        ),
        thesis=[
            ThesisStep(
                proposition=(
                    "The Fed will definitely cut rates soon because everyone knows they have to."
                ),
                supporting_evidence_ids=[0],
                risk_factors=["None really"],
            ),
        ],
        evidence=[
            Evidence(
                source="Unverified blog post on Medium",
                claim=(
                    "A random person says rates will go down because they "
                    "always do in election years."
                ),
                confidence=0.95,
                timestamp=datetime(2026, 3, 15, tzinfo=UTC),
            ),
        ],
        raw_probability=0.85,
        volatility_adjustment=0.10,
        final_probability=0.95,
        rationale=(
            "I feel like rates will be cut. It's obvious. "
            "Going big on this one since it's a sure thing."
        ),
        action="BUY",
        size_usdc=25.0,
        price_limit=0.95,
        model_family="anthropic-claude",
        model_name="claude-sonnet-4-20250514",
        created_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Calibration tests -- VAL-SENTINEL-007, 008, 009, 010
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCalibrationGate:
    """Sentinel calibration gate - 3 synthetic traces, score + gap + monotonic.

    These tests use REAL OpenAI API calls via DSPy. They require
    OPENAI_API_KEY to be set in the environment. If any test fails,
    the orchestrator must decide on a model swap before Day 4 work.
    """

    @pytest.fixture(autouse=True)
    def _ensure_openai_key(self) -> None:
        """Skip tests if OPENAI_API_KEY is not available."""
        if not os.environ.get("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set - calibration tests require real API access")

    @pytest.mark.asyncio
    async def test_good_trace_scores_60_to_100(self) -> None:
        """VAL-SENTINEL-007: Good synthetic trace -> verdict_score in [60, 100]."""
        trace = _good_trace()
        trace_json = json.dumps(trace.model_dump(mode="json"))
        verdict = await generate_verdict(
            trace_json=trace_json,
            request_hash="calibration-good",
            trace_id=trace.trace_id,
            sentinel_agent_id=2,
        )
        assert 60 <= verdict.verdict_score <= 100, (
            f"Good trace verdict_score {verdict.verdict_score} "
            f"not in [60, 100]. Label: {verdict.verdict_label}"
        )

    @pytest.mark.asyncio
    async def test_mediocre_trace_scores_30_to_60(self) -> None:
        """VAL-SENTINEL-008: Mediocre synthetic trace -> verdict_score in [30, 60]."""
        trace = _mediocre_trace()
        trace_json = json.dumps(trace.model_dump(mode="json"))
        verdict = await generate_verdict(
            trace_json=trace_json,
            request_hash="calibration-mediocre",
            trace_id=trace.trace_id,
            sentinel_agent_id=2,
        )
        assert 30 <= verdict.verdict_score <= 60, (
            f"Mediocre trace verdict_score {verdict.verdict_score} "
            f"not in [30, 60]. Label: {verdict.verdict_label}"
        )

    @pytest.mark.asyncio
    async def test_bad_trace_scores_0_to_40(self) -> None:
        """VAL-SENTINEL-009: Bad synthetic trace -> verdict_score in [0, 40]."""
        trace = _bad_trace()
        trace_json = json.dumps(trace.model_dump(mode="json"))
        verdict = await generate_verdict(
            trace_json=trace_json,
            request_hash="calibration-bad",
            trace_id=trace.trace_id,
            sentinel_agent_id=2,
        )
        assert 0 <= verdict.verdict_score <= 40, (
            f"Bad trace verdict_score {verdict.verdict_score} "
            f"not in [0, 40]. Label: {verdict.verdict_label}"
        )

    @pytest.mark.asyncio
    async def test_calibration_gap_and_monotonic_ordering(self) -> None:
        """VAL-SENTINEL-010: good-bad gap >= 30 and monotonic ordering.

        Runs all 3 traces and checks both the gap requirement and the
        strict ordering: bad_score < mediocre_score < good_score.
        """
        # Run all 3 traces
        good_trace = _good_trace()
        good_json = json.dumps(good_trace.model_dump(mode="json"))
        good_verdict = await generate_verdict(
            trace_json=good_json,
            request_hash="calibration-good-full",
            trace_id=good_trace.trace_id,
            sentinel_agent_id=2,
        )

        mediocre_trace = _mediocre_trace()
        mediocre_json = json.dumps(mediocre_trace.model_dump(mode="json"))
        mediocre_verdict = await generate_verdict(
            trace_json=mediocre_json,
            request_hash="calibration-mediocre-full",
            trace_id=mediocre_trace.trace_id,
            sentinel_agent_id=2,
        )

        bad_trace = _bad_trace()
        bad_json = json.dumps(bad_trace.model_dump(mode="json"))
        bad_verdict = await generate_verdict(
            trace_json=bad_json,
            request_hash="calibration-bad-full",
            trace_id=bad_trace.trace_id,
            sentinel_agent_id=2,
        )

        good_score = good_verdict.verdict_score
        mediocre_score = mediocre_verdict.verdict_score
        bad_score = bad_verdict.verdict_score

        # Check gap requirement
        gap = good_score - bad_score
        assert gap >= 30, (
            f"Calibration gap {gap} is less than 30 points. "
            f"Scores: good={good_score}, mediocre={mediocre_score}, "
            f"bad={bad_score}. "
            f"CALIBRATION GATE FAILED - sentinel model may need to be swapped."
        )

        # Check monotonic ordering
        assert bad_score < mediocre_score < good_score, (
            f"Scores are not monotonically ordered: bad={bad_score}, "
            f"mediocre={mediocre_score}, good={good_score}. "
            f"CALIBRATION GATE FAILED - sentinel discrimination is insufficient."
        )

        # Log summary for visibility
        import structlog

        logger = structlog.get_logger("prism.sentinel.calibration")
        logger.info(
            "calibration_gate_result",
            good_score=good_score,
            good_label=good_verdict.verdict_label,
            mediocre_score=mediocre_score,
            mediocre_label=mediocre_verdict.verdict_label,
            bad_score=bad_score,
            bad_label=bad_verdict.verdict_label,
            gap=good_score - bad_score,
            gate_passed=True,
        )
