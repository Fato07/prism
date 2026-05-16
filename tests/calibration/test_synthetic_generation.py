"""Synthetic row generation tests for the calibration labeling surface."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

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


def test_generate_synthetic_writes_valid_rows_across_quality_bands(
    tmp_path: Path,
) -> None:
    """Synthetic seeding writes requested Prism rows with varied review coverage."""
    root = tmp_path / "calibration"

    result = run_cli("label", "generate-synthetic", "--root", str(root), "--count", "12")

    assert result.returncode == 0, result.stderr
    payload: dict[str, Any] = json.loads(result.stdout)
    assert payload["operation"] == "generate-synthetic"
    assert payload["requested_count"] == 12
    assert payload["written_count"] == 12
    assert payload["source_counts"] == {"synthetic": 12}
    assert set(payload["quality_bands"]) >= {"high", "medium", "low"}
    assert len(payload["row_ids"]) == 12
    assert len(set(payload["row_ids"])) == 12

    generated_failure_tags: set[str] = set()
    for row_id in payload["row_ids"]:
        row = load_row(root / "rows" / f"{row_id}.json")
        generated_failure_tags.update(row.review.failure_tags)
        assert row.provenance.source_type == "synthetic"
        assert row.provenance.parent_row_id is None
        assert row.provenance.mutation_type is None
        assert row.provenance.content_hash == row.trace.content_hash().hex()
        assert row.provenance.source_ref.startswith("synthetic:")
        assert row.trace.thesis
        assert row.trace.evidence
        assert 0.0 <= row.trace.final_probability <= 1.0

    assert {
        "weak-evidence",
        "calibration-overconfidence",
        "missing-counterevidence",
    }.issubset(generated_failure_tags)


def test_generate_synthetic_rejects_non_positive_count(tmp_path: Path) -> None:
    """Synthetic generation fails loudly for invalid count values."""
    root = tmp_path / "calibration"

    result = run_cli("label", "generate-synthetic", "--root", str(root), "--count", "0")

    assert result.returncode != 0
    assert "count must be greater than 0" in result.stderr
