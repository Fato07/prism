from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from prism_cli.app import app

runner = CliRunner()


def sample_trace() -> dict:
    return {
        "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "agent_id": 4140,
        "market_id": "0xmarket",
        "market_question": "Will Polymarket volume exceed $1B this month?",
        "thesis": [
            {
                "proposition": "Volume trend supports the trade.",
                "supporting_evidence_ids": [0, 1],
                "risk_factors": ["Invalidated if volume falls for three consecutive sessions."],
            }
        ],
        "evidence": [
            {
                "source": "Polymarket",
                "claim": "Daily volume has increased week over week.",
                "confidence": 0.72,
                "timestamp": "2026-05-16T10:00:00Z",
            },
            {
                "source": "Dune",
                "claim": "Related market-maker activity has risen.",
                "confidence": 0.68,
                "timestamp": "2026-05-16T10:05:00Z",
            },
        ],
        "raw_probability": 0.62,
        "volatility_adjustment": -0.04,
        "final_probability": 0.58,
        "action": "BUY",
        "size_usdc": 1.5,
        "price_limit": 0.58,
        "rationale": "Position is small and exit if market volume fails to persist.",
        "model_family": "anthropic-claude",
        "model_name": "claude-sonnet-4-20250514",
        "created_at": "2026-05-16T10:10:00Z",
    }


def test_inspect_local_trace_outputs_reasoning_metrics_json(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.json"
    trace_path.write_text(json.dumps(sample_trace()))

    result = runner.invoke(app, ["inspect", str(trace_path), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["trace_id"] == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    assert payload["readiness"] == "usable"
    assert payload["reasoning_metrics"]["evidence_count"] == 2
    assert payload["reasoning_metrics"]["source_diversity"] == 2
    assert payload["reasoning_metrics"]["evidence_coverage"] == 1
    assert payload["reasoning_metrics"]["invalid_evidence_refs"] == 0


def test_inspect_rejects_unsupported_source() -> None:
    result = runner.invoke(app, ["inspect", "not-a-cid", "--json"])

    assert result.exit_code == 1
    assert "Unsupported trace source" in result.output
