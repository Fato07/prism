"""Schema validation tests."""

from datetime import datetime, timezone

from prism_schemas.trace import Evidence, ThesisStep, TradingR1Trace
from prism_schemas.verdict import SentinelVerdict


def test_trading_r1_trace_validates():
    trace = TradingR1Trace(
        trace_id="test-001",
        agent_id=1,
        market_id="0xabc",
        market_question="Will ETH hit $5000 by Q3?",
        thesis=[
            ThesisStep(
                proposition="ETH momentum is bullish",
                supporting_evidence_ids=[0],
                risk_factors=["regulatory"],
            )
        ],
        evidence=[
            Evidence(
                source="coingecko",
                claim="ETH up 20% in 30d",
                confidence=0.8,
                timestamp=datetime.now(timezone.utc),
            )
        ],
        raw_probability=0.65,
        volatility_adjustment=-0.05,
        final_probability=0.60,
        action="BUY",
        size_usdc=10.0,
        price_limit=0.60,
        rationale="Bullish momentum with manageable risk.",
        model_family="anthropic-claude",
        model_name="claude-opus-4-7",
        created_at=datetime.now(timezone.utc),
    )
    assert trace.content_hash() is not None
    assert len(trace.content_hash()) == 32


def test_sentinel_verdict_validates():
    verdict = SentinelVerdict(
        request_hash="0xdeadbeef",
        trace_id="test-001",
        sentinel_agent_id=2,
        evidence_challenges=["coingecko data may be stale"],
        thesis_challenges=["regulatory risk underweighted"],
        calibration_critique="60% seems reasonable given evidence.",
        verdict_score=72,
        verdict_label="PASS",
        dialogue_messages=[
            {"role": "sentinel", "content": "Challenge: source reliability"}
        ],
        model_family="openai-gpt",
        model_name="gpt-4o-mini",
        created_at=datetime.now(timezone.utc),
    )
    assert verdict.content_hash() is not None
    assert verdict.verdict_label == "PASS"
