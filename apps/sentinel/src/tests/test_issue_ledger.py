"""Structured issue ledger regression tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from prism_schemas.trace import Evidence, ThesisStep, TradingR1Trace

from sentinel.issues import apply_unresolved_issue_caps, build_structured_challenges


def _lebron_stale_trace() -> TradingR1Trace:
    """Trace based on the stale-evidence LeBron regression observed in production."""
    return TradingR1Trace(
        trace_id="13fa6f0c-0650-4695-9f7e-5e4069bbce96",
        agent_id=1001,
        market_id="0xc0f6fc1ef71052492781bf8f1614cb3e767fd4a71fc2f1dfd1899dbb195fefea",
        market_question="Will LeBron break the scoring record during the Feb 7 game vs. OKC?",
        thesis=[
            ThesisStep(
                proposition="LeBron is close to the scoring record.",
                supporting_evidence_ids=[0, 1],
                risk_factors=["Injury", "Load management"],
            ),
            ThesisStep(
                proposition="LeBron is capable of a high-scoring performance.",
                supporting_evidence_ids=[2],
                risk_factors=["Age-related performance decline"],
            ),
        ],
        evidence=[
            Evidence(
                source="NBA official statistics tracking",
                claim="LeBron is within 36-40 points of Kareem's record.",
                confidence=0.95,
                timestamp=datetime(2024, 2, 6, 12, 0, tzinfo=UTC),
            ),
            Evidence(
                source="Historical NBA record-breaking context",
                claim="Most NBA scoring records are broken during regular season games.",
                confidence=0.80,
                timestamp=datetime(2024, 2, 6, 12, 0, tzinfo=UTC),
            ),
            Evidence(
                source="LeBron's 2022-23 season statistics",
                claim="LeBron has averaged around 29-30 points per game.",
                confidence=0.85,
                timestamp=datetime(2024, 2, 6, 12, 0, tzinfo=UTC),
            ),
        ],
        raw_probability=0.75,
        volatility_adjustment=-0.15,
        final_probability=0.60,
        action="BUY",
        size_usdc=1.0,
        price_limit=0.65,
        rationale="Buying at 65% or below provides positive expected value.",
        model_family="anthropic-claude",
        model_name="claude-sonnet-4-20250514",
        created_at=datetime(2026, 5, 16, 15, 38, tzinfo=UTC),
    )


def _recent_trace() -> TradingR1Trace:
    return TradingR1Trace(
        trace_id="recent-001",
        agent_id=1,
        market_id="poly-2026-fed-rate-cut",
        market_question="Will the Fed cut rates by July 2026?",
        thesis=[
            ThesisStep(
                proposition="Recent inflation data supports easing.",
                supporting_evidence_ids=[0],
                risk_factors=["Inflation rebound"],
            )
        ],
        evidence=[
            Evidence(
                source="BLS CPI report",
                claim="Recent CPI print came in below expectations.",
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


def test_stale_lebron_trace_creates_blocking_temporal_issue_and_caps_pass() -> None:
    trace = _lebron_stale_trace()
    challenges = build_structured_challenges(
        trace_json=json.dumps(trace.model_dump(mode="json")),
        evidence_challenges=["The evidence quality is concerning."],
        thesis_challenges=["The thesis depends on game-flow variables."],
        calibration_critique="The probability may be overconfident.",
    )

    stale = [c for c in challenges if c.id == "sys-temporal-stale-evidence"]
    assert stale, "stale evidence should become a structured issue"
    assert stale[0].blocking_pass is True
    assert stale[0].severity == "blocking"

    score, label, metadata = apply_unresolved_issue_caps(
        score=65,
        label="PASS",
        challenges=challenges,
    )

    assert score <= 50
    assert label == "WARN"
    assert metadata.unresolved_blocking_count >= 1
    assert metadata.stop_reason == "unresolved_blockers"


def test_recent_trace_does_not_create_temporal_blocker() -> None:
    trace = _recent_trace()
    challenges = build_structured_challenges(
        trace_json=json.dumps(trace.model_dump(mode="json")),
        evidence_challenges=["Source should be corroborated."],
        thesis_challenges=["Risk factors could be expanded."],
        calibration_critique="Probability calibration is acceptable but should be monitored.",
    )

    assert all(c.id != "sys-temporal-stale-evidence" for c in challenges)
    score, label, metadata = apply_unresolved_issue_caps(
        score=65,
        label="PASS",
        challenges=challenges,
    )
    assert score == 65
    assert label == "PASS"
    assert metadata.unresolved_blocking_count == 0
