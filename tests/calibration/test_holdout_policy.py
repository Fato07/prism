"""Holdout lockout tests for pre-labeling and frozen exports."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from prism_calibration.labeling import generate_synthetic_rows
from prism_calibration.prelabel import apply_prelabels_to_row, normalize_prelabel_output
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


def corpus_row(
    row_id: str,
    *,
    lineage_id: str,
    split_name: str,
    source_type: str = "synthetic",
    parent_row_id: str | None = None,
    mutation_type: str | None = None,
) -> dict[str, Any]:
    """Return a schema-valid row for holdout export policy tests."""
    timestamp = "2026-05-15T12:00:00Z"
    provenance: dict[str, Any] = {
        "source_type": source_type,
        "source_ref": f"tests/generated/{row_id}.json",
        "run_id": "holdout-policy-test-run",
        "lineage_id": lineage_id,
        "content_hash": (row_id.encode().hex() * 64)[:64].ljust(64, "0"),
        "created_at": timestamp,
    }
    if parent_row_id is not None:
        provenance["parent_row_id"] = parent_row_id
    if mutation_type is not None:
        provenance["mutation_type"] = mutation_type

    return {
        "schema_version": "1.0",
        "row_id": row_id,
        "trace": {
            "trace_id": f"trace-{row_id}",
            "agent_id": 4140,
            "market_id": f"holdout-market-{lineage_id}",
            "market_question": "Will holdout rows stay locked out of tuning exports?",
            "thesis": [
                {
                    "proposition": f"{row_id} exercises holdout export policy.",
                    "supporting_evidence_ids": [0],
                    "risk_factors": ["Holdout leakage would contaminate tuning."],
                }
            ],
            "evidence": [
                {
                    "source": "holdout-policy-test",
                    "claim": f"{row_id} has explicit split metadata.",
                    "confidence": 0.86,
                    "timestamp": timestamp,
                }
            ],
            "raw_probability": 0.61,
            "volatility_adjustment": 0.01,
            "final_probability": 0.62,
            "action": "BUY",
            "size_usdc": 2.5,
            "price_limit": 0.62,
            "rationale": f"{row_id} is a holdout-policy fixture.",
            "model_family": "anthropic-claude",
            "model_name": "claude-opus-4-7",
            "created_at": timestamp,
        },
        "provenance": provenance,
        "review": {
            "status": "unreviewed",
            "rubric_version": "prism-calibration-v1",
            "failure_tags": [],
        },
        "split": {
            "name": split_name,
            "policy": "holdout-policy-test",
            "seed": 0,
            "assigned_at": timestamp,
        },
    }


def write_rows(root: Path, rows: list[dict[str, Any]]) -> None:
    """Write private corpus rows under a local root."""
    row_dir = root / "rows"
    row_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        (row_dir / f"{row['row_id']}.json").write_text(
            json.dumps(row, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def test_holdout_prelabel_stays_manual_review_locked(tmp_path: Path) -> None:
    """Holdout rows remain manual/eval-only even with high-confidence consensus."""
    root = tmp_path / "calibration"
    result = generate_synthetic_rows(root=root, count=1)
    row = load_row(root / "rows" / f"{result.rows[0].row_id}.json")
    split = row.split.model_copy(update={"name": "holdout"})
    holdout_row = row.model_copy(update={"split": split})
    label = normalize_prelabel_output(
        {
            "reasoning_quality": 92,
            "evidence_quality": 90,
            "calibration_quality": 88,
            "verdict_band": "PASS",
            "failure_tags": [],
            "confidence": 0.95,
        },
        model_name="judge-a",
        model_family="openai-gpt",
    )

    routed = apply_prelabels_to_row(holdout_row, (label, label))

    assert routed.review.status == "manual_review"
    assert routed.review.routing is not None
    assert routed.review.routing.destination == "manual_review"
    assert routed.review.routing.route_reasons == ["holdout_locked"]


def test_dev_freeze_excludes_holdout_rows(tmp_path: Path) -> None:
    """A dev export selects dev rows and leaves holdout rows out of the manifest."""
    root = tmp_path / "calibration"
    bootstrap = run_cli("build", "--root", str(root))
    assert bootstrap.returncode == 0, bootstrap.stderr
    write_rows(
        root,
        [
            corpus_row("dev-row", lineage_id="lineage-dev-only", split_name="dev"),
            corpus_row(
                "holdout-row",
                lineage_id="lineage-holdout-only",
                split_name="holdout",
            ),
        ],
    )

    result = run_cli("freeze", "--root", str(root), "--slice", "dev")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["row_ids"] == ["dev-row"]
    manifest = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["split_metadata"]["name"] == "dev"
    assert "holdout-row" not in manifest["row_ids"]


def test_dev_freeze_fails_when_holdout_lineage_is_merged(tmp_path: Path) -> None:
    """A holdout lineage cannot be merged into a dev/tuning export."""
    root = tmp_path / "calibration"
    bootstrap = run_cli("build", "--root", str(root))
    assert bootstrap.returncode == 0, bootstrap.stderr
    write_rows(
        root,
        [
            corpus_row(
                "holdout-parent",
                lineage_id="lineage-leaky-holdout",
                split_name="holdout",
            ),
            corpus_row(
                "dev-child",
                lineage_id="lineage-leaky-holdout",
                split_name="dev",
                source_type="mutated",
                parent_row_id="holdout-parent",
                mutation_type="weak-evidence",
            ),
        ],
    )

    result = run_cli("freeze", "--root", str(root), "--slice", "dev")

    assert result.returncode != 0
    assert "Holdout lineage 'lineage-leaky-holdout'" in result.stderr
    assert "tuning/dev export" in result.stderr
