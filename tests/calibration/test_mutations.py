"""Mutation generation tests for calibration labeling rows."""

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


def _seed_parent(root: Path) -> str:
    """Create one synthetic parent row and return its row ID."""
    seeded = run_cli("label", "generate-synthetic", "--root", str(root), "--count", "1")
    assert seeded.returncode == 0, seeded.stderr
    payload: dict[str, Any] = json.loads(seeded.stdout)
    return str(payload["row_ids"][0])


def test_generate_mutations_preserves_lineage_and_changes_reasoning(
    tmp_path: Path,
) -> None:
    """Mutated rows keep market identity while changing reasoning behavior."""
    root = tmp_path / "calibration"
    parent_row_id = _seed_parent(root)
    parent = load_row(root / "rows" / f"{parent_row_id}.json")

    result = run_cli(
        "label",
        "generate-mutations",
        "--root",
        str(root),
        "--source",
        parent_row_id,
        "--count",
        "4",
    )

    assert result.returncode == 0, result.stderr
    payload: dict[str, Any] = json.loads(result.stdout)
    assert payload["operation"] == "generate-mutations"
    assert payload["parent_row_id"] == parent_row_id
    assert payload["requested_count"] == 4
    assert payload["written_count"] == 4
    assert payload["source_counts"] == {"mutated": 4}
    assert set(payload["mutation_types"]) >= {
        "weak-evidence",
        "probability-overstatement",
        "missing-counterevidence",
        "stale-evidence",
    }

    for mutated_id in payload["row_ids"]:
        mutated = load_row(root / "rows" / f"{mutated_id}.json")
        assert mutated.provenance.source_type == "mutated"
        assert mutated.provenance.parent_row_id == parent_row_id
        assert mutated.provenance.lineage_id == parent.provenance.lineage_id
        assert mutated.provenance.mutation_type in payload["mutation_types"]
        assert mutated.provenance.content_hash == mutated.trace.content_hash().hex()
        assert mutated.review.failure_tags
        assert mutated.trace.market_id == parent.trace.market_id
        assert mutated.trace.market_question == parent.trace.market_question
        assert mutated.trace.content_hash() != parent.trace.content_hash()
        assert (
            mutated.trace.rationale != parent.trace.rationale
            or mutated.trace.evidence != parent.trace.evidence
            or mutated.trace.thesis != parent.trace.thesis
        )

        inspected = run_cli("inspect", "--root", str(root), "--row", mutated_id)
        assert inspected.returncode == 0, inspected.stderr
        inspected_payload = json.loads(inspected.stdout)
        assert inspected_payload["source_type"] == "mutated"
        assert inspected_payload["parent"]["row_id"] == parent_row_id


def test_generate_mutations_rejects_missing_source(tmp_path: Path) -> None:
    """Mutation generation fails loudly when the requested parent row is absent."""
    root = tmp_path / "calibration"

    result = run_cli(
        "label",
        "generate-mutations",
        "--root",
        str(root),
        "--source",
        "missing-row",
        "--count",
        "1",
    )

    assert result.returncode != 0
    assert "unable to resolve row reference" in result.stderr
