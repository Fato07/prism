"""Deterministic split assignment tests for the local calibration corpus."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the calibration CLI in the same way validators call it."""
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
) -> dict[str, Any]:
    """Return a minimal split-build corpus row."""
    timestamp = "2026-05-15T12:00:00Z"
    provenance: dict[str, Any] = {
        "source_type": source_type,
        "source_ref": f"tests/generated/{row_id}.json",
        "run_id": "split-test-run",
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
            "market_id": f"split-market-{lineage_id}",
            "market_question": "Will deterministic splits preserve lineage families?",
            "thesis": [
                {
                    "proposition": f"{row_id} belongs to a stable split.",
                    "supporting_evidence_ids": [0],
                    "risk_factors": ["Split assignment may not be deterministic."],
                }
            ],
            "evidence": [
                {
                    "source": "split-test",
                    "claim": f"{row_id} has stable split inputs.",
                    "confidence": 0.84,
                    "timestamp": timestamp,
                }
            ],
            "raw_probability": 0.58,
            "volatility_adjustment": 0.02,
            "final_probability": 0.60,
            "action": "HOLD",
            "size_usdc": 0.0,
            "price_limit": 0.60,
            "rationale": f"{row_id} is a deterministic split fixture.",
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
            "name": "pilot",
            "policy": "pre-build fixture",
            "seed": 0,
            "assigned_at": timestamp,
        },
    }


def write_rows(root: Path, rows: list[dict[str, Any]]) -> None:
    """Write private rows into a local corpus root."""
    row_dir = root / "rows"
    row_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        (row_dir / f"{row['row_id']}.json").write_text(
            json.dumps(row, indent=2, sort_keys=True),
            encoding="utf-8",
        )


def load_manifest(root: Path, seed: int) -> dict[str, Any]:
    """Load a split manifest written by the build command."""
    manifest_path = root / "manifests" / f"splits-seed-{seed}.json"
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def test_build_assigns_stable_membership_for_same_inputs_and_seed(tmp_path: Path) -> None:
    """Repeated builds with unchanged rows and seed keep identical memberships."""
    root = tmp_path / "calibration"
    initial_build = run_cli("build", "--root", str(root), "--seed", "42")
    assert initial_build.returncode == 0, initial_build.stderr
    write_rows(
        root,
        [
            corpus_row("alpha-parent", lineage_id="lineage-alpha"),
            corpus_row(
                "alpha-mutated",
                lineage_id="lineage-alpha",
                source_type="mutated",
                parent_row_id="alpha-parent",
                mutation_type="weak-evidence",
            ),
            corpus_row("beta-parent", lineage_id="lineage-beta"),
            corpus_row("gamma-parent", lineage_id="lineage-gamma"),
            corpus_row("delta-parent", lineage_id="lineage-delta"),
            corpus_row("epsilon-parent", lineage_id="lineage-epsilon"),
        ],
    )

    first = run_cli("build", "--root", str(root), "--seed", "42")
    assert first.returncode == 0, first.stderr
    first_manifest_text = (root / "manifests" / "splits-seed-42.json").read_text(
        encoding="utf-8"
    )
    first_manifest = json.loads(first_manifest_text)

    second = run_cli("build", "--root", str(root), "--seed", "42")
    assert second.returncode == 0, second.stderr
    second_manifest_text = (root / "manifests" / "splits-seed-42.json").read_text(
        encoding="utf-8"
    )
    second_manifest = json.loads(second_manifest_text)

    assert second_manifest_text == first_manifest_text
    assert second_manifest["splits"] == first_manifest["splits"]
    assert second_manifest["row_count"] == 6
    assert sum(split["count"] for split in second_manifest["splits"].values()) == 6
    assert sorted(
        row_id
        for split in second_manifest["splits"].values()
        for row_id in split["row_ids"]
    ) == [
        "alpha-mutated",
        "alpha-parent",
        "beta-parent",
        "delta-parent",
        "epsilon-parent",
        "gamma-parent",
    ]


def test_lineage_family_is_assigned_to_one_split(tmp_path: Path) -> None:
    """Parent and mutated rows in one lineage receive the same split assignment."""
    root = tmp_path / "calibration"
    build = run_cli("build", "--root", str(root), "--seed", "42")
    assert build.returncode == 0, build.stderr
    write_rows(
        root,
        [
            corpus_row("lineage-parent", lineage_id="lineage-shared"),
            corpus_row(
                "lineage-child",
                lineage_id="lineage-shared",
                source_type="mutated",
                parent_row_id="lineage-parent",
                mutation_type="missing-counterevidence",
            ),
        ],
    )

    result = run_cli("build", "--root", str(root), "--seed", "42")

    assert result.returncode == 0, result.stderr
    manifest = load_manifest(root, seed=42)
    lineage = manifest["lineages"]["lineage-shared"]
    assert lineage["row_ids"] == ["lineage-child", "lineage-parent"]
    parent = json.loads((root / "rows" / "lineage-parent.json").read_text(encoding="utf-8"))
    child = json.loads((root / "rows" / "lineage-child.json").read_text(encoding="utf-8"))
    assert parent["split"]["name"] == lineage["split"]
    assert child["split"]["name"] == lineage["split"]
    assert parent["split"]["seed"] == 42
    assert child["split"]["policy"] == "lineage-hash-v1"
