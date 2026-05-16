from __future__ import annotations

from prism_cli.metrics import inspect_trace
from prism_cli.models import TradingR1Trace


def make_trace(**updates: object) -> TradingR1Trace:
    data = {
        "trace_id": "trace-1",
        "agent_id": 4140,
        "market_id": "0xmarket",
        "market_question": "Will ETH exceed $5k?",
        "thesis": [
            {
                "proposition": "Evidence supports upside.",
                "supporting_evidence_ids": [0, 5],
                "risk_factors": [],
            }
        ],
        "evidence": [
            {
                "source": "Polymarket",
                "claim": "Odds moved up.",
                "confidence": 0.8,
                "timestamp": "2026-05-16T10:00:00Z",
            }
        ],
        "raw_probability": 0.8,
        "volatility_adjustment": -0.1,
        "final_probability": 0.7,
        "action": "BUY",
        "size_usdc": 1,
        "price_limit": 0.7,
        "rationale": "Small position.",
        "model_family": "anthropic-claude",
        "model_name": "claude-sonnet-4-20250514",
        "created_at": "2026-05-16T10:10:00Z",
    }
    data.update(updates)
    return TradingR1Trace.model_validate(data)


def test_metrics_detect_invalid_evidence_references() -> None:
    result = inspect_trace(make_trace())

    assert result.readiness == "not_ready"
    assert result.reasoning_metrics.invalid_evidence_refs == 1
    assert "missing evidence IDs" in " ".join(result.warnings)


def test_metrics_classifies_thin_but_valid_trace_as_needs_review() -> None:
    result = inspect_trace(
        make_trace(
            thesis=[
                {
                    "proposition": "One source supports the thesis.",
                    "supporting_evidence_ids": [0],
                    "risk_factors": ["Invalidated by reversal."],
                }
            ],
        )
    )

    assert result.readiness == "needs_review"
    assert result.reasoning_metrics.evidence_count == 1
    assert result.reasoning_metrics.evidence_coverage == 1
