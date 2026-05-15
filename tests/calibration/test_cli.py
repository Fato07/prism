"""CLI contract tests for the local calibration corpus package."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]


def run_cli(
    *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the calibration CLI the same way validators invoke it."""
    merged_env = os.environ.copy()
    merged_env.pop("BRAINTRUST_API_KEY", None)
    merged_env.pop("BRAINTRUST_ORG_NAME", None)
    if env is not None:
        merged_env.update(env)

    return subprocess.run(
        [sys.executable, "-m", "prism_calibration.cli", *args],
        cwd=REPO_ROOT,
        env=merged_env,
        text=True,
        capture_output=True,
        check=False,
    )


def valid_row() -> dict[str, Any]:
    """Return a publishable, schema-valid calibration row fixture."""
    timestamp = "2026-05-15T12:00:00Z"
    return {
        "schema_version": "1.0",
        "row_id": "sample-row-001",
        "trace": {
            "trace_id": "sample-trace-001",
            "agent_id": 4140,
            "market_id": "polymarket-sample-001",
            "market_question": "Will the sample calibration row validate locally?",
            "thesis": [
                {
                    "proposition": "The CLI should validate publishable sample rows offline.",
                    "supporting_evidence_ids": [0],
                    "risk_factors": [
                        "The implementation may accidentally depend on Braintrust."
                    ],
                }
            ],
            "evidence": [
                {
                    "source": "local-fixture",
                    "claim": "The sample row contains complete provenance, split, and review metadata.",
                    "confidence": 0.91,
                    "timestamp": timestamp,
                }
            ],
            "raw_probability": 0.72,
            "volatility_adjustment": -0.02,
            "final_probability": 0.70,
            "action": "BUY",
            "size_usdc": 5.0,
            "price_limit": 0.70,
            "rationale": "A complete local fixture should pass corpus row validation.",
            "model_family": "anthropic-claude",
            "model_name": "claude-opus-4-7",
            "created_at": timestamp,
        },
        "provenance": {
            "source_type": "sample",
            "source_ref": "data/calibration/sample/rows/sample-row-001.json",
            "run_id": "sample-bootstrap-20260515",
            "lineage_id": "lineage-sample-row-001",
            "content_hash": "a" * 64,
            "created_at": timestamp,
        },
        "review": {
            "status": "unreviewed",
            "rubric_version": "prism-calibration-v1",
            "failure_tags": [],
            "notes": "Publishable sample fixture for local schema validation.",
        },
        "split": {
            "name": "sample",
            "policy": "publishable sample fixture",
            "seed": 0,
            "assigned_at": timestamp,
        },
    }


def test_help_lists_public_workflow_commands() -> None:
    """Top-level help exposes the calibration corpus workflow commands."""
    result = run_cli("--help")

    assert result.returncode == 0, result.stderr
    for command in (
        "build",
        "harvest",
        "label",
        "freeze",
        "sync",
        "eval",
        "inspect",
        "validate",
    ):
        assert command in result.stdout


def test_build_bootstraps_local_root_without_braintrust(tmp_path: Path) -> None:
    """Build creates a local authoritative root without requiring Braintrust credentials."""
    root = tmp_path / "calibration"
    result = run_cli("build", "--root", str(root), "--seed", "42")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ready"
    assert payload["root"] == str(root)
    assert (root / "sample").is_dir()
    assert (root / "sample" / "rows").is_dir()
    for private_dir in ("rows", "manifests", "frozen", "quarantine", "state"):
        assert (root / private_dir).is_dir()
    assert payload["authority"] == "local"


def test_validate_accepts_valid_row(tmp_path: Path) -> None:
    """A complete row with provenance, review, and split metadata validates."""
    row_path = tmp_path / "valid-row.json"
    row_path.write_text(json.dumps(valid_row()), encoding="utf-8")

    result = run_cli("validate", "--row", str(row_path))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {"row_id": "sample-row-001", "status": "valid"}


def test_validate_rejects_missing_provenance_review_and_split(tmp_path: Path) -> None:
    """Malformed rows fail with field-level errors naming missing metadata."""
    malformed = valid_row()
    malformed.pop("provenance")
    malformed["review"].pop("status")
    malformed["split"].pop("name")
    row_path = tmp_path / "malformed-row.json"
    row_path.write_text(json.dumps(malformed), encoding="utf-8")

    result = run_cli("validate", "--row", str(row_path))

    assert result.returncode != 0
    assert "provenance" in result.stderr
    assert "review.status" in result.stderr
    assert "split.name" in result.stderr


def test_invalid_cli_arguments_are_actionable() -> None:
    """Invalid arguments fail non-zero with usage and a specific error."""
    result = run_cli("freeze", "--slice")

    assert result.returncode != 0
    assert "usage:" in result.stderr
    assert "argument --slice: expected one argument" in result.stderr
