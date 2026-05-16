"""Pilot slice build tests."""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path

from prism_calibration.lineage import load_corpus_rows, validate_lineage_integrity

REPO_ROOT = Path(__file__).resolve().parents[2]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the calibration CLI and return the completed process."""
    return subprocess.run(
        ["uv", "run", "python", "-m", "prism_calibration.cli", *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_build_pilot_size_creates_mixed_50_row_slice(tmp_path: Path) -> None:
    """The pilot build creates exactly 50 stable mixed-source rows."""
    root = tmp_path / "calibration"

    result = run_cli("build", "--root", str(root), "--pilot-size", "50")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["operation"] == "pilot-build"
    assert payload["row_count"] == 50
    assert payload["source_counts"]["synthetic"] > 0
    assert payload["source_counts"]["mutated"] > 0
    assert payload["source_counts"]["real"] > 0
    assert payload["duplicate_row_ids"] == []
    assert payload["manual_review_count"] > 0
    assert payload["auto_resolved_count"] > 0

    manifest = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["row_count"] == 50
    assert manifest["source_counts"] == payload["source_counts"]
    assert manifest["row_ids"] == payload["row_ids"]

    loaded_rows = load_corpus_rows(root, include_sample=False)
    validate_lineage_integrity(loaded_rows)
    pilot_rows = [loaded.row for loaded in loaded_rows if loaded.row.split.name == "pilot"]
    assert len(pilot_rows) == 50
    assert len({row.row_id for row in pilot_rows}) == 50
    assert Counter(row.provenance.source_type for row in pilot_rows) == Counter(
        payload["source_counts"]
    )

    for row in pilot_rows:
        assert row.row_id in payload["row_ids"]
        assert row.provenance.content_hash == row.trace.content_hash().hex()
        assert row.provenance.lineage_id
        assert row.split.name == "pilot"
        assert row.review.ai_labels
        assert row.review.canonical_label is not None
        assert row.review.routing is not None


def test_pilot_build_is_stable_for_unchanged_inputs(tmp_path: Path) -> None:
    """Rebuilding the same pilot slice preserves stable row identity."""
    root = tmp_path / "calibration"

    first = run_cli("build", "--root", str(root), "--pilot-size", "50")
    second = run_cli("build", "--root", str(root), "--pilot-size", "50")

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    first_payload = json.loads(first.stdout)
    second_payload = json.loads(second.stdout)
    assert second_payload["row_ids"] == first_payload["row_ids"]
    assert second_payload["source_counts"] == first_payload["source_counts"]
    assert second_payload["manifest_id"] == first_payload["manifest_id"]
