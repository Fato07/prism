"""Frozen slice regression and immutability tests (VAL-CROSS-004, VAL-CROSS-005)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from prism_calibration.braintrust_sync import braintrust_project
from prism_calibration.eval import (
    EvalRunResult,
    run_regression,
)
from prism_calibration.freeze import (
    freeze_slice,
    validate_frozen_export,
)
from prism_calibration.pilot import build_pilot_slice

REPO_ROOT = Path(__file__).resolve().parents[2]


def run_cli(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run the calibration CLI, optionally with custom env."""
    merged_env = os.environ.copy()
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


def _build_and_freeze(tmp_path: Path) -> tuple[Path, Path, dict[str, Any]]:
    """Build a pilot slice, freeze it, and return (root, export_dir, freeze_payload)."""
    root = tmp_path / "calibration"
    build_pilot_slice(root=root, pilot_size=20)
    export = freeze_slice(root, "pilot")
    freeze_payload: dict[str, Any] = {
        "export_id": export.manifest.export_id,
        "export_path": str(export.export_dir),
        "manifest_path": str(export.manifest_path),
        "row_count": export.manifest.row_count,
        "row_ids": export.manifest.row_ids,
        "row_hashes": {entry.row_id: entry.row_hash for entry in export.manifest.rows},
        "slice": export.manifest.slice_name,
        "status": "frozen",
    }
    return root, export.export_dir, freeze_payload


# ---------------------------------------------------------------------------
# VAL-CROSS-004: Frozen export is immutable after live-corpus changes
# ---------------------------------------------------------------------------


def test_frozen_manifest_hash_unchanged_after_live_corpus_edit(tmp_path: Path) -> None:
    """Freezing a named slice writes an immutable export that does not change
    when the live corpus is edited later."""
    root, export_dir, freeze_payload = _build_and_freeze(tmp_path)

    # Capture the original manifest hash
    manifest_path = export_dir / "manifest.json"
    original_manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    # Edit the live corpus: add a new row
    rows_dir = root / "rows"
    row_file = rows_dir / "live-edit-row.json"
    row_file.write_text(
        json.dumps(
            _make_row("live-edit-row", lineage_id="lineage-edit-1"),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    # The frozen manifest hash must remain identical
    post_edit_manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    assert post_edit_manifest_hash == original_manifest_hash, (
        "Frozen manifest changed after live-corpus edit"
    )

    # Re-validate the frozen export - must still pass
    validation = validate_frozen_export(export_dir)
    assert validation.manifest_hash == original_manifest_hash
    assert validation.manifest.export_id == freeze_payload["export_id"]


def test_frozen_row_hashes_unchanged_after_live_corpus_edit(tmp_path: Path) -> None:
    """Per-row hashes in the frozen export remain stable after live-corpus edits."""
    root, export_dir, freeze_payload = _build_and_freeze(tmp_path)

    original_row_hashes = dict(freeze_payload["row_hashes"])

    # Edit a live corpus row (not the frozen one)
    from prism_calibration.lineage import load_corpus_rows

    rows = load_corpus_rows(root, include_sample=False)
    if rows:
        live_row = rows[0]
        edited_payload = json.loads(live_row.path.read_text(encoding="utf-8"))
        edited_payload["trace"]["rationale"] = "Edited after freeze for immutability test."
        live_row.path.write_text(
            json.dumps(edited_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    # Frozen row hashes must be unchanged
    validation = validate_frozen_export(export_dir)
    assert validation.row_hashes == original_row_hashes, (
        "Frozen row hashes changed after live-corpus edit"
    )


def test_frozen_export_seal_marker_prevents_tampering(tmp_path: Path) -> None:
    """A sealed frozen export detects direct tampering with its files."""
    root, export_dir, freeze_payload = _build_and_freeze(tmp_path)

    # The .sealed marker must exist
    seal_path = export_dir / ".sealed"
    assert seal_path.exists(), "Frozen export must have a .sealed marker"

    seal_payload = json.loads(seal_path.read_text(encoding="utf-8"))
    assert seal_payload["manifest_hash"] is not None
    assert seal_payload["export_id"] == freeze_payload["export_id"]

    # Tamper with a frozen row
    manifest = json.loads((export_dir / "manifest.json").read_text(encoding="utf-8"))
    row_entry = manifest["rows"][0]
    row_path = export_dir / row_entry["path"]
    row_data = json.loads(row_path.read_text(encoding="utf-8"))
    row_data["trace"]["rationale"] = "Direct tampering test."
    row_path.write_text(json.dumps(row_data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # Validation must now fail
    from prism_calibration.freeze import FrozenExportError

    try:
        validate_frozen_export(export_dir)
    except FrozenExportError:
        pass  # expected - tampered row hash mismatch
    else:
        raise AssertionError("Expected validation failure after tampering with sealed export")


def test_refreezing_after_live_edit_creates_new_export_not_old(tmp_path: Path) -> None:
    """Re-freezing after live-corpus edits creates a new export directory,
    leaving the old frozen export completely untouched."""
    root, export_dir, freeze_payload = _build_and_freeze(tmp_path)
    original_export_id = freeze_payload["export_id"]

    # Add a new row and rebuild splits
    from prism_calibration.splits import build_deterministic_splits

    rows_dir = root / "rows"
    row_file = rows_dir / "post-freeze-row.json"
    row_file.write_text(
        json.dumps(
            _make_row("post-freeze-row", lineage_id="lineage-post-freeze"),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    build_deterministic_splits(root, seed=42)

    # Re-freeze
    new_export = freeze_slice(root, "pilot")
    new_export_id = new_export.manifest.export_id

    # The new export must be in a different directory (different export_id)
    assert new_export_id != original_export_id, (
        "Re-freeze after content change must produce a different export identity"
    )

    # The old export must still be valid and untouched
    old_manifest = export_dir / "manifest.json"
    old_hash = hashlib.sha256(old_manifest.read_bytes()).hexdigest()
    validation = validate_frozen_export(export_dir)
    assert validation.manifest_hash == old_hash


# ---------------------------------------------------------------------------
# VAL-CROSS-005: Regression runs against the frozen slice
# ---------------------------------------------------------------------------


def test_regression_evaluates_exactly_manifest_rows(tmp_path: Path) -> None:
    """Regression evaluates exactly the rows named in the frozen manifest."""
    root, export_dir, _ = _build_and_freeze(tmp_path)

    result = run_regression(frozen_path=export_dir)

    assert isinstance(result, EvalRunResult)
    assert result.total_rows > 0

    # Load the manifest to verify exact row match
    manifest = json.loads((export_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest_row_ids = manifest["row_ids"]
    result_row_ids = [c.row_id for c in result.case_results]
    assert result_row_ids == manifest_row_ids, (
        f"Regression evaluated {result_row_ids}, expected {manifest_row_ids}"
    )
    assert result.total_rows == len(manifest_row_ids)


def test_regression_results_keyed_to_slice_hash_and_run_config(tmp_path: Path) -> None:
    """Regression emits machine-readable results keyed to the slice hash and run config."""
    root, export_dir, _ = _build_and_freeze(tmp_path)

    run_config = {"threshold": 0.5, "bands": ["PASS", "WARN", "FAIL"]}
    result = run_regression(
        frozen_path=export_dir,
        run_config=run_config,
    )

    # Results must be keyed to export_id (slice hash) and run_config
    assert result.export_id  # slice hash
    assert result.eval_id  # deterministic eval identity
    assert result.run_config == run_config

    # Local results artifact must exist
    assert result.results_path.exists()
    payload = json.loads(result.results_path.read_text(encoding="utf-8"))
    assert payload["kind"] == "prism_calibration.eval_result"
    assert payload["export_id"] == result.export_id
    assert payload["eval_id"] == result.eval_id
    assert payload["run_config"] == run_config
    assert len(payload["case_results"]) == result.total_rows


def test_regression_fails_if_manifest_row_missing(tmp_path: Path) -> None:
    """Regression fails if a row listed in the manifest is missing from the export."""
    root, export_dir, _ = _build_and_freeze(tmp_path)

    # Delete a row file from the frozen export
    manifest = json.loads((export_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest["rows"]:
        row_path = export_dir / manifest["rows"][0]["path"]
        row_path.unlink()

    try:
        run_regression(frozen_path=export_dir)
    except Exception as exc:
        assert "missing" in str(exc).lower() or "not found" in str(exc).lower()
    else:
        raise AssertionError("Expected error when manifest row is missing from export")


def test_regression_creates_braintrust_experiment_when_available(
    tmp_path: Path,
) -> None:
    """When Braintrust is available, regression creates a visible experiment."""
    root, export_dir, _ = _build_and_freeze(tmp_path)

    import uuid

    expt_name = f"test-regression-{uuid.uuid4().hex[:12]}"
    result = run_regression(
        frozen_path=export_dir,
        experiment_name=expt_name,
    )

    assert result.experiment_name == expt_name
    assert result.experiment_id  # non-empty Braintrust ID

    # Verify via CLI
    bt_result = subprocess.run(
        ["bt", "experiments", "list", "-p", braintrust_project(), "--json"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if bt_result.returncode == 0 and bt_result.stdout.strip():
        experiments = json.loads(bt_result.stdout)
        names = [e.get("name", "") for e in experiments]
        assert expt_name in names


def test_regression_cli_eval_frozen_flag(tmp_path: Path) -> None:
    """The eval CLI with --frozen runs regression against the frozen export."""
    root, export_dir, _ = _build_and_freeze(tmp_path)

    result = run_cli("eval", "--frozen", str(export_dir))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["operation"] == "eval-run"
    assert payload["total_rows"] > 0
    assert payload["slice"] == "pilot"


def test_regression_summary_is_machine_readable(tmp_path: Path) -> None:
    """Regression summary is JSON-compatible and includes all required fields."""
    root, export_dir, _ = _build_and_freeze(tmp_path)

    result = run_regression(frozen_path=export_dir)
    from prism_calibration.eval import eval_summary

    summary = eval_summary(result)
    json.dumps(summary)  # must be serializable
    assert summary["authority"] == "local"
    assert summary["eval_id"]
    assert summary["export_id"]
    assert summary["total_rows"] > 0
    assert summary["passed_rows"] + summary["failed_rows"] == summary["total_rows"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_row(row_id: str, *, lineage_id: str) -> dict[str, Any]:
    """Return a minimal schema-valid pilot corpus row."""
    from prism_calibration.splits import split_for_lineage

    split_name = split_for_lineage(lineage_id, seed=42)
    timestamp = "2026-05-15T12:00:00Z"
    return {
        "schema_version": "1.0",
        "row_id": row_id,
        "trace": {
            "trace_id": f"trace-{row_id}",
            "agent_id": 4140,
            "market_id": f"market-{lineage_id}",
            "market_question": f"Will {row_id} pass calibration?",
            "thesis": [
                {
                    "proposition": f"{row_id} has complete metadata.",
                    "supporting_evidence_ids": [0],
                    "risk_factors": ["Test-only fixture."],
                }
            ],
            "evidence": [
                {
                    "source": "regression-test",
                    "claim": f"{row_id} is a regression fixture.",
                    "confidence": 0.80,
                    "timestamp": timestamp,
                }
            ],
            "raw_probability": 0.55,
            "volatility_adjustment": 0.01,
            "final_probability": 0.56,
            "action": "BUY",
            "size_usdc": 1.0,
            "price_limit": 0.56,
            "rationale": f"{row_id} is a regression fixture row.",
            "model_family": "anthropic-claude",
            "model_name": "claude-opus-4-7",
            "created_at": timestamp,
        },
        "provenance": {
            "source_type": "synthetic",
            "source_ref": f"tests/generated/{row_id}.json",
            "run_id": "regression-test-run",
            "lineage_id": lineage_id,
            "content_hash": (row_id.encode().hex() * 64)[:64].ljust(64, "0"),
            "created_at": timestamp,
        },
        "review": {
            "status": "unreviewed",
            "rubric_version": "prism-calibration-v1",
            "failure_tags": [],
        },
        "split": {
            "name": split_name,
            "policy": "lineage-hash-v1",
            "seed": 42,
            "assigned_at": timestamp,
        },
    }
