"""Frozen export tests for local calibration corpus slices."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from prism_calibration.models import SplitName
from prism_calibration.splits import split_for_lineage


REPO_ROOT = Path(__file__).resolve().parents[2]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the calibration CLI with Braintrust env unset."""
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


def lineage_for_split(target: SplitName, *, seed: int = 42) -> str:
    """Return a deterministic lineage ID that maps to the requested split."""
    for index in range(1_000):
        lineage_id = f"lineage-{target}-{index}"
        if split_for_lineage(lineage_id, seed=seed) == target:
            return lineage_id
    raise AssertionError(f"Could not find lineage for split {target}")


def corpus_row(
    row_id: str,
    *,
    lineage_id: str,
    source_type: str = "synthetic",
    parent_row_id: str | None = None,
    mutation_type: str | None = None,
) -> dict[str, Any]:
    """Return a minimal schema-valid corpus row for freeze tests."""
    timestamp = "2026-05-15T12:00:00Z"
    provenance: dict[str, Any] = {
        "source_type": source_type,
        "source_ref": f"tests/generated/{row_id}.json",
        "run_id": "freeze-test-run",
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
            "market_id": f"freeze-market-{lineage_id}",
            "market_question": "Will frozen exports remain portable and stable?",
            "thesis": [
                {
                    "proposition": f"{row_id} can be frozen into a local export.",
                    "supporting_evidence_ids": [0],
                    "risk_factors": ["Frozen export identity may drift."],
                }
            ],
            "evidence": [
                {
                    "source": "freeze-test",
                    "claim": f"{row_id} has complete local corpus metadata.",
                    "confidence": 0.87,
                    "timestamp": timestamp,
                }
            ],
            "raw_probability": 0.61,
            "volatility_adjustment": 0.01,
            "final_probability": 0.62,
            "action": "BUY",
            "size_usdc": 2.5,
            "price_limit": 0.62,
            "rationale": f"{row_id} is a focused freeze fixture.",
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
            "policy": "pre-freeze fixture",
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


def prepare_pilot_root(root: Path) -> None:
    """Build a local root containing pilot rows and an excluded dev row."""
    initial = run_cli("build", "--root", str(root), "--seed", "42")
    assert initial.returncode == 0, initial.stderr

    pilot_lineage = lineage_for_split("pilot")
    dev_lineage = lineage_for_split("dev")
    write_rows(
        root,
        [
            corpus_row("pilot-parent", lineage_id=pilot_lineage),
            corpus_row(
                "pilot-mutated",
                lineage_id=pilot_lineage,
                source_type="mutated",
                parent_row_id="pilot-parent",
                mutation_type="weakened-evidence",
            ),
            corpus_row("dev-row", lineage_id=dev_lineage),
        ],
    )

    build = run_cli("build", "--root", str(root), "--seed", "42")
    assert build.returncode == 0, build.stderr


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object from disk."""
    return json.loads(path.read_text(encoding="utf-8"))


def test_freeze_pilot_slice_emits_manifest_rows_and_split_metadata(tmp_path: Path) -> None:
    """Freezing a named slice writes normalized rows and a stable manifest."""
    root = tmp_path / "calibration"
    prepare_pilot_root(root)

    result = run_cli("freeze", "--root", str(root), "--slice", "pilot")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "frozen"
    assert payload["slice"] == "pilot"
    assert payload["row_ids"] == ["pilot-mutated", "pilot-parent"]
    assert payload["row_count"] == 2

    export_path = Path(payload["export_path"])
    manifest_path = Path(payload["manifest_path"])
    assert manifest_path == export_path / "manifest.json"
    manifest = load_json(manifest_path)
    assert manifest["kind"] == "prism_calibration.frozen_export"
    assert manifest["export_id"] == payload["export_id"]
    assert manifest["row_count"] == 2
    assert manifest["row_ids"] == ["pilot-mutated", "pilot-parent"]
    assert manifest["split_metadata"]["name"] == "pilot"
    assert manifest["split_metadata"]["count"] == 2
    assert manifest["split_metadata"]["row_ids"] == ["pilot-mutated", "pilot-parent"]
    assert list(manifest["split_metadata"]["lineages"].values()) == [
        ["pilot-mutated", "pilot-parent"]
    ]

    for entry in manifest["rows"]:
        row_path = export_path / entry["path"]
        row_text = row_path.read_text(encoding="utf-8")
        row_payload = json.loads(row_text)
        assert row_payload["row_id"] == entry["row_id"]
        assert row_payload["split"]["name"] == "pilot"
        assert entry["row_hash"] == hashlib.sha256(row_text.encode("utf-8")).hexdigest()
        assert payload["row_hashes"][entry["row_id"]] == entry["row_hash"]


def test_refreezing_unchanged_slice_preserves_export_identity(tmp_path: Path) -> None:
    """Freezing an unchanged slice twice keeps the same identity and bytes."""
    root = tmp_path / "calibration"
    prepare_pilot_root(root)

    first = run_cli("freeze", "--root", str(root), "--slice", "pilot")
    second = run_cli("freeze", "--root", str(root), "--slice", "pilot")

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    first_payload = json.loads(first.stdout)
    second_payload = json.loads(second.stdout)
    assert second_payload["export_id"] == first_payload["export_id"]
    assert second_payload["export_path"] == first_payload["export_path"]
    assert second_payload["manifest_path"] == first_payload["manifest_path"]

    manifest_path = Path(first_payload["manifest_path"])
    first_manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    second_manifest_hash = hashlib.sha256(Path(second_payload["manifest_path"]).read_bytes()).hexdigest()
    assert second_manifest_hash == first_manifest_hash
    assert json.loads(first.stdout)["row_hashes"] == json.loads(second.stdout)["row_hashes"]
