"""Lineage validation and inspection tests for local calibration rows."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the calibration CLI exactly through its public module surface."""
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
    source_type: str = "synthetic",
    parent_row_id: str | None = None,
    mutation_type: str | None = None,
    split_name: str = "pilot",
) -> dict[str, Any]:
    """Return a minimal schema-valid corpus row for lineage tests."""
    timestamp = "2026-05-15T12:00:00Z"
    provenance: dict[str, Any] = {
        "source_type": source_type,
        "source_ref": f"tests/generated/{row_id}.json",
        "run_id": "lineage-test-run",
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
            "market_id": "lineage-market",
            "market_question": "Will lineage inspection stay local and deterministic?",
            "thesis": [
                {
                    "proposition": f"{row_id} has auditable lineage.",
                    "supporting_evidence_ids": [0],
                    "risk_factors": ["Lineage metadata may be incomplete."],
                }
            ],
            "evidence": [
                {
                    "source": "lineage-test",
                    "claim": f"{row_id} contains complete local lineage metadata.",
                    "confidence": 0.86,
                    "timestamp": timestamp,
                }
            ],
            "raw_probability": 0.62,
            "volatility_adjustment": 0.01,
            "final_probability": 0.63,
            "action": "BUY",
            "size_usdc": 3.0,
            "price_limit": 0.63,
            "rationale": f"{row_id} is a focused lineage fixture.",
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
            "policy": "lineage test fixture",
            "seed": 0,
            "assigned_at": timestamp,
        },
    }


def write_row(root: Path, payload: dict[str, Any]) -> None:
    """Write one private corpus row fixture."""
    row_dir = root / "rows"
    row_dir.mkdir(parents=True, exist_ok=True)
    row_path = row_dir / f"{payload['row_id']}.json"
    row_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_inspect_mutated_row_exposes_parent_lineage_by_row_id(tmp_path: Path) -> None:
    """Inspecting a mutated row by ID shows the local parent lineage details."""
    root = tmp_path / "calibration"
    build = run_cli("build", "--root", str(root), "--seed", "42")
    assert build.returncode == 0, build.stderr
    write_row(root, corpus_row("parent-row-001", lineage_id="lineage-alpha"))
    write_row(
        root,
        corpus_row(
            "mutated-row-001",
            lineage_id="lineage-alpha",
            source_type="mutated",
            parent_row_id="parent-row-001",
            mutation_type="weakened-evidence",
        ),
    )

    result = run_cli("inspect", "--root", str(root), "--row", "mutated-row-001")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["row_id"] == "mutated-row-001"
    assert payload["source_type"] == "mutated"
    assert payload["lineage_id"] == "lineage-alpha"
    assert payload["mutation_type"] == "weakened-evidence"
    assert payload["parent"]["row_id"] == "parent-row-001"
    assert payload["parent"]["lineage_id"] == "lineage-alpha"


def test_validate_rejects_orphaned_mutation_fixture() -> None:
    """An orphaned mutated row fails loudly with the missing parent ID."""
    fixture = REPO_ROOT / "tests" / "fixtures" / "calibration" / "orphaned-mutation.json"

    result = run_cli("validate", "--row", str(fixture))

    assert result.returncode != 0
    assert "Orphaned mutated row" in result.stderr
    assert "orphaned-mutated-row" in result.stderr
    assert "missing-parent-row" in result.stderr


def test_validate_root_rejects_lineage_split_leak(tmp_path: Path) -> None:
    """A lineage family cannot already span conflicting non-sample splits."""
    root = tmp_path / "calibration"
    build = run_cli("build", "--root", str(root), "--seed", "42")
    assert build.returncode == 0, build.stderr
    write_row(root, corpus_row("leaky-parent", lineage_id="lineage-leaky", split_name="dev"))
    write_row(
        root,
        corpus_row(
            "leaky-child",
            lineage_id="lineage-leaky",
            source_type="mutated",
            parent_row_id="leaky-parent",
            mutation_type="probability-overstatement",
            split_name="holdout",
        ),
    )

    result = run_cli("validate", "--root", str(root))

    assert result.returncode != 0
    assert "Lineage leak" in result.stderr
    assert "lineage-leaky" in result.stderr
    assert "leaky-parent" in result.stderr
    assert "leaky-child" in result.stderr

    build_result = run_cli("build", "--root", str(root), "--seed", "42")
    assert build_result.returncode != 0
    assert "Lineage leak" in build_result.stderr
    assert "lineage-leaky" in build_result.stderr
