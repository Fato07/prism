"""AI pre-label normalization tests for calibration rows."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from prism_calibration.prelabel import normalize_prelabel_output
from prism_calibration.validation import load_row


REPO_ROOT = Path(__file__).resolve().parents[2]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the calibration CLI through its public module surface."""
    env = os.environ.copy()
    env.pop("BRAINTRUST_API_KEY", None)
    env.pop("BRAINTRUST_ORG_NAME", None)
    return subprocess.run(
        [sys.executable, "-m", "prism_calibration.cli", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_normalize_ai_prelabel_output_uses_prism_rubric_fields() -> None:
    """Raw AI output is normalized into the Prism calibration rubric shape."""
    prelabel = normalize_prelabel_output(
        {
            "reasoning_quality": "high",
            "evidence_quality": 72,
            "calibration_quality": 0.64,
            "verdict_band": "pass",
            "failure_tags": ["Weak Evidence", "calibration_overconfidence"],
            "confidence": 87,
        },
        model_name="local-prelabel-test",
        model_family="openai-gpt",
    )

    assert prelabel.reasoning_quality == 85
    assert prelabel.evidence_quality == 72
    assert prelabel.calibration_quality == 64
    assert prelabel.verdict_band == "PASS"
    assert prelabel.failure_tags == [
        "calibration-overconfidence",
        "weak-evidence",
    ]
    assert prelabel.confidence == 0.87


def test_prelabel_cli_writes_normalized_rubric_outputs(tmp_path: Path) -> None:
    """The public prelabel command persists normalized rubric output on rows."""
    root = tmp_path / "calibration"
    seeded = run_cli("label", "generate-synthetic", "--root", str(root), "--count", "8")
    assert seeded.returncode == 0, seeded.stderr

    result = run_cli("label", "prelabel", "--root", str(root), "--slice", "pilot-seed")

    assert result.returncode == 0, result.stderr
    payload: dict[str, Any] = json.loads(result.stdout)
    assert payload["operation"] == "prelabel"
    assert payload["slice"] == "pilot-seed"
    assert payload["resolved_slice"] == "all-private"
    assert payload["row_count"] == 8
    assert payload["normalized_fields"] == [
        "reasoning_quality",
        "evidence_quality",
        "calibration_quality",
        "verdict_band",
        "failure_tags",
        "confidence",
    ]
    assert payload["status_counts"]["ai_resolved"] >= 1
    assert payload["status_counts"]["manual_review"] >= 1
    assert payload["manual_queue_row_ids"]
    assert payload["auto_resolved_row_ids"]

    for row_summary in payload["rows"]:
        row = load_row(root / "rows" / f"{row_summary['row_id']}.json")
        label = row.review.canonical_label
        routing = row.review.routing
        assert label is not None
        assert routing is not None
        assert row.review.ai_labels
        assert 0 <= label.reasoning_quality <= 100
        assert 0 <= label.evidence_quality <= 100
        assert 0 <= label.calibration_quality <= 100
        assert label.verdict_band in {"REJECT", "WARN", "PASS", "ENDORSE"}
        assert 0 <= label.confidence <= 1
        assert label.failure_tags == sorted(set(label.failure_tags))
        assert routing.destination in {"manual_review", "auto_resolved"}
        if row.review.status == "manual_review":
            assert routing.route_reasons
