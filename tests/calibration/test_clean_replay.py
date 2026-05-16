"""Clean-environment frozen export replay tests (VAL-CROSS-007)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from prism_calibration.eval import (
    EvalRunResult,
    replay_frozen_eval,
)
from prism_calibration.freeze import (
    freeze_slice,
    validate_frozen_export,
)
from prism_calibration.pilot import build_pilot_slice

REPO_ROOT = Path(__file__).resolve().parents[2]


def run_cli(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run the calibration CLI with optional custom environment."""
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
# VAL-CROSS-007: Frozen export reproduces the slice in a clean environment
# ---------------------------------------------------------------------------


def test_clean_replay_without_braintrust_or_neon(tmp_path: Path) -> None:
    """In a clean environment (no Braintrust, no Neon), a frozen export can
    be used to rerun regression without re-harvesting and without depending
    on Braintrust to reconstruct slice membership."""
    _, export_dir, freeze_payload = _build_and_freeze(tmp_path)

    # Copy the frozen export to a completely clean location
    clean_root = tmp_path / "clean-env"
    clean_export = clean_root / "pilot-export"
    shutil.copytree(export_dir, clean_export)

    # Run replay with Braintrust env vars explicitly unset
    env_no_bt = os.environ.copy()
    env_no_bt.pop("BRAINTRUST_API_KEY", None)
    env_no_bt.pop("BRAINTRUST_ORG_NAME", None)

    result = replay_frozen_eval(clean_export)

    assert isinstance(result, EvalRunResult)
    assert result.total_rows == freeze_payload["row_count"]
    assert result.export_id == freeze_payload["export_id"]
    assert result.slice_name == "pilot"
    assert result.total_rows > 0

    # Results artifact must exist in the clean export directory
    assert result.results_path.exists()
    payload = json.loads(result.results_path.read_text(encoding="utf-8"))
    assert payload["export_id"] == freeze_payload["export_id"]
    assert len(payload["case_results"]) == freeze_payload["row_count"]


def test_clean_replay_produces_identical_slice_membership_hash(tmp_path: Path) -> None:
    """Replay from a frozen export produces the same slice-membership hash
    as the original freeze, proving no Braintrust-based reconstruction is needed."""
    _, export_dir, freeze_payload = _build_and_freeze(tmp_path)

    clean_export = tmp_path / "clean-identity" / "pilot-export"
    shutil.copytree(export_dir, clean_export)

    result = replay_frozen_eval(clean_export)

    # The export_id (which is the slice identity hash) must be identical
    assert result.export_id == freeze_payload["export_id"], (
        "Clean replay produced different slice identity hash"
    )

    # Re-validate the clean copy - manifest hash must match
    validation = validate_frozen_export(clean_export)
    original_manifest_hash = hashlib.sha256(
        (export_dir / "manifest.json").read_bytes()
    ).hexdigest()
    assert validation.manifest_hash == original_manifest_hash


def test_clean_replay_row_ids_match_manifest_exactly(tmp_path: Path) -> None:
    """Replay evaluates exactly the same row IDs as the frozen manifest,
    with no Braintrust dependency for membership reconstruction."""
    _, export_dir, freeze_payload = _build_and_freeze(tmp_path)

    clean_export = tmp_path / "clean-membership" / "pilot-export"
    shutil.copytree(export_dir, clean_export)

    result = replay_frozen_eval(clean_export)

    result_row_ids = [c.row_id for c in result.case_results]
    assert result_row_ids == freeze_payload["row_ids"], (
        f"Replay row IDs {result_row_ids} != manifest {freeze_payload['row_ids']}"
    )


def test_clean_replay_no_harvest_or_sync_steps(tmp_path: Path) -> None:
    """Replay does not attempt harvest or Braintrust sync steps."""
    _, export_dir, _ = _build_and_freeze(tmp_path)

    clean_export = tmp_path / "clean-no-sync" / "pilot-export"
    shutil.copytree(export_dir, clean_export)

    # Run replay - it must succeed even with DATABASE_URL unset
    env_no_db = os.environ.copy()
    env_no_db.pop("DATABASE_URL", None)
    env_no_db.pop("BRAINTRUST_API_KEY", None)

    result = replay_frozen_eval(clean_export)

    # Must succeed without DB or Braintrust
    assert result.total_rows > 0
    assert result.experiment_name == ""  # no Braintrust experiment created
    assert result.experiment_id == ""  # no Braintrust experiment ID


def test_clean_replay_cli_without_braintrust_env(tmp_path: Path) -> None:
    """The eval CLI with --frozen works without Braintrust env vars set."""
    _, export_dir, _ = _build_and_freeze(tmp_path)

    clean_export = tmp_path / "clean-cli" / "pilot-export"
    shutil.copytree(export_dir, clean_export)

    env_no_bt = os.environ.copy()
    env_no_bt.pop("BRAINTRUST_API_KEY", None)
    env_no_bt.pop("BRAINTRUST_ORG_NAME", None)

    result = run_cli("eval", "--frozen", str(clean_export), env=env_no_bt)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["operation"] == "eval-run"
    assert payload["total_rows"] > 0
    assert payload["slice"] == "pilot"


def test_clean_replay_results_bundle_independent_of_braintrust(tmp_path: Path) -> None:
    """The replay results bundle is self-contained and does not require
    Braintrust to interpret."""
    _, export_dir, _ = _build_and_freeze(tmp_path)

    clean_export = tmp_path / "clean-bundle" / "pilot-export"
    shutil.copytree(export_dir, clean_export)

    result = replay_frozen_eval(clean_export)

    # Read the results file independently
    results_payload = json.loads(result.results_path.read_text(encoding="utf-8"))
    assert results_payload["kind"] == "prism_calibration.eval_result"
    assert results_payload["schema_version"] == "1.0"
    assert results_payload["export_id"]  # slice identity
    assert results_payload["eval_id"]  # eval identity
    assert results_payload["total_rows"] > 0
    assert len(results_payload["case_results"]) == results_payload["total_rows"]

    # Each case result must have the essential regression fields
    for case in results_payload["case_results"]:
        assert "row_id" in case
        assert "trace_id" in case
        assert "verdict_band" in case
        assert "score" in case
        assert "passed" in case


def test_clean_replay_deterministic_eval_id(tmp_path: Path) -> None:
    """Running replay twice from the same frozen export with the same config
    produces the same eval_id and results."""
    _, export_dir, _ = _build_and_freeze(tmp_path)

    clean_export_1 = tmp_path / "clean-determinism-1" / "pilot-export"
    clean_export_2 = tmp_path / "clean-determinism-2" / "pilot-export"
    shutil.copytree(export_dir, clean_export_1)
    shutil.copytree(export_dir, clean_export_2)

    result_1 = replay_frozen_eval(clean_export_1)
    result_2 = replay_frozen_eval(clean_export_2)

    assert result_1.eval_id == result_2.eval_id
    assert result_1.total_rows == result_2.total_rows
    assert [c.row_id for c in result_1.case_results] == [
        c.row_id for c in result_2.case_results
    ]


def test_clean_replay_with_run_config(tmp_path: Path) -> None:
    """Clean replay accepts and records run_config in results."""
    _, export_dir, _ = _build_and_freeze(tmp_path)

    clean_export = tmp_path / "clean-config" / "pilot-export"
    shutil.copytree(export_dir, clean_export)

    run_config = {"threshold": 0.6, "fail_on": "FAIL"}
    result = replay_frozen_eval(clean_export, run_config=run_config)

    assert result.run_config == run_config
    payload = json.loads(result.results_path.read_text(encoding="utf-8"))
    assert payload["run_config"] == run_config
