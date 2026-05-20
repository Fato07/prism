"""Frozen-slice eval runs and Braintrust experiment tests (VAL-BT-003)."""

from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

from prism_calibration.braintrust_sync import braintrust_project
from prism_calibration.eval import (
    EvalCaseResult,
    EvalRunError,
    EvalRunResult,
    eval_summary,
    run_eval,
)
from prism_calibration.freeze import freeze_slice
from prism_calibration.pilot import build_pilot_slice

REPO_ROOT = Path(__file__).resolve().parents[2]


def _unique_experiment_name() -> str:
    """Return a unique experiment name for test isolation."""
    return f"test-eval-{uuid.uuid4().hex[:12]}"


def _build_pilot_root(tmp_path: Path) -> Path:
    """Build a small pilot slice and return the corpus root path."""
    root = tmp_path / "calibration"
    build_pilot_slice(root=root, pilot_size=20)
    return root


def _freeze_pilot(root: Path) -> Path:
    """Freeze the pilot slice and return the export directory."""
    export = freeze_slice(root, "pilot")
    return export.export_dir


def _query_experiments_via_cli() -> list[dict]:
    """List Braintrust experiments via the bt CLI."""
    result = subprocess.run(
        ["bt", "experiments", "list", "-p", braintrust_project(), "--json"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []
    return json.loads(result.stdout)


# ---------------------------------------------------------------------------
# VAL-BT-003: Eval run becomes an experiment snapshot
# ---------------------------------------------------------------------------


def test_eval_creates_braintrust_experiment_with_metadata(
    tmp_path: Path,
) -> None:
    """Running calibration against a frozen slice creates a visible Braintrust
    experiment with enough metadata to identify the slice, evaluator configuration,
    and timestamp."""
    root = _build_pilot_root(tmp_path)
    export_dir = _freeze_pilot(root)

    expt_name = _unique_experiment_name()
    result = run_eval(
        frozen_path=export_dir,
        experiment_name=expt_name,
    )

    # Result must have experiment metadata
    assert isinstance(result, EvalRunResult)
    assert result.experiment_name == expt_name
    assert result.experiment_id  # non-empty Braintrust experiment ID
    assert result.slice_name == "pilot"
    assert result.export_id  # frozen export identity
    assert result.evaluator_name  # evaluator configuration name
    assert result.evaluator_model  # evaluator model identifier
    assert result.timestamp  # ISO timestamp
    assert result.total_rows > 0

    # Verify the experiment is queryable via Braintrust CLI
    experiments = _query_experiments_via_cli()
    expt_names = [e.get("name", "") for e in experiments]
    assert expt_name in expt_names, (
        f"Experiment '{expt_name}' not found in Prism project experiments"
    )

    # Verify experiment metadata
    matching = [e for e in experiments if e.get("name") == expt_name]
    assert len(matching) == 1
    metadata = matching[0].get("metadata", {})
    assert metadata.get("slice_name") == "pilot"
    assert metadata.get("export_id") == result.export_id
    assert metadata.get("evaluator_name") == result.evaluator_name
    assert metadata.get("evaluator_model") == result.evaluator_model
    assert metadata.get("timestamp") == result.timestamp


def test_eval_experiment_has_slice_identifier_and_evaluator_config(
    tmp_path: Path,
) -> None:
    """The Braintrust experiment metadata includes the slice identifier,
    evaluator configuration, and run config."""
    root = _build_pilot_root(tmp_path)
    export_dir = _freeze_pilot(root)

    expt_name = _unique_experiment_name()
    run_config = {"threshold": 0.5, "bands": ["PASS", "WARN", "FAIL"]}
    result = run_eval(
        frozen_path=export_dir,
        experiment_name=expt_name,
        run_config=run_config,
    )

    experiments = _query_experiments_via_cli()
    matching = [e for e in experiments if e.get("name") == expt_name]
    assert matching

    metadata = matching[0].get("metadata", {})
    assert metadata["slice_name"] == "pilot"
    assert metadata["evaluator_name"] == result.evaluator_name
    assert metadata["evaluator_model"] == result.evaluator_model
    assert metadata["run_config"] == run_config
    assert "row_count" in metadata


def test_eval_produces_case_results_tied_to_slice(
    tmp_path: Path,
) -> None:
    """Each eval case result can be tied back to the local slice or case identifiers."""
    root = _build_pilot_root(tmp_path)
    export_dir = _freeze_pilot(root)

    expt_name = _unique_experiment_name()
    result = run_eval(
        frozen_path=export_dir,
        experiment_name=expt_name,
    )

    assert len(result.case_results) > 0
    for case in result.case_results:
        assert isinstance(case, EvalCaseResult)
        assert case.row_id  # stable local case identifier
        assert case.trace_id  # trace identifier
        assert case.lineage_id  # lineage group identifier
        assert case.source_type  # provenance source type
        assert case.verdict_band  # rubric verdict
        assert 0.0 <= case.confidence <= 1.0
        assert 0 <= case.reasoning_quality <= 100
        assert 0 <= case.evidence_quality <= 100
        assert 0 <= case.calibration_quality <= 100
        assert 0.0 <= case.score <= 1.0

    # Total counts add up
    assert result.passed_rows + result.failed_rows == result.total_rows


def test_eval_writes_local_results_artifact(tmp_path: Path) -> None:
    """Eval writes a machine-readable local results artifact keyed to the
    slice hash and run config."""
    root = _build_pilot_root(tmp_path)
    export_dir = _freeze_pilot(root)

    expt_name = _unique_experiment_name()
    result = run_eval(
        frozen_path=export_dir,
        experiment_name=expt_name,
    )

    # Results file must exist
    assert result.results_path.exists()
    payload = json.loads(result.results_path.read_text(encoding="utf-8"))
    assert payload["kind"] == "prism_calibration.eval_result"
    assert payload["eval_id"] == result.eval_id
    assert payload["experiment_name"] == result.experiment_name
    assert payload["slice_name"] == "pilot"
    assert payload["export_id"] == result.export_id
    assert payload["total_rows"] == result.total_rows
    assert len(payload["case_results"]) == result.total_rows


def test_eval_using_root_and_slice(tmp_path: Path) -> None:
    """Eval can find the frozen export by root and slice name."""
    root = _build_pilot_root(tmp_path)
    _freeze_pilot(root)

    expt_name = _unique_experiment_name()
    result = run_eval(
        root=root,
        slice_name="pilot",
        experiment_name=expt_name,
    )

    assert result.total_rows > 0
    assert result.slice_name == "pilot"


def test_eval_auto_freezes_if_no_frozen_export(tmp_path: Path) -> None:
    """If no frozen export exists, eval auto-freezes the slice."""
    root = _build_pilot_root(tmp_path)

    expt_name = _unique_experiment_name()
    result = run_eval(
        root=root,
        slice_name="pilot",
        experiment_name=expt_name,
    )

    assert result.total_rows > 0
    assert result.export_id  # auto-frozen export identity


# ---------------------------------------------------------------------------
# Eval CLI integration
# ---------------------------------------------------------------------------


def test_eval_cli_runs_against_frozen_slice(tmp_path: Path) -> None:
    """The eval CLI command runs against a frozen slice and creates a Braintrust experiment."""
    root = _build_pilot_root(tmp_path)
    _freeze_pilot(root)

    result = subprocess.run(
        [
            "uv", "run", "python", "-m", "prism_calibration.cli",
            "eval", "--root", str(root), "--slice", "pilot",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["operation"] == "eval-run"
    assert payload["slice"] == "pilot"
    assert payload["experiment_id"]
    assert payload["experiment_name"]
    assert payload["total_rows"] > 0


def test_eval_cli_with_frozen_path(tmp_path: Path) -> None:
    """The eval CLI accepts --frozen path directly."""
    root = _build_pilot_root(tmp_path)
    export_dir = _freeze_pilot(root)

    result = subprocess.run(
        [
            "uv", "run", "python", "-m", "prism_calibration.cli",
            "eval", "--frozen", str(export_dir),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["operation"] == "eval-run"
    assert payload["total_rows"] > 0


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_eval_without_frozen_or_root_and_slice_raises() -> None:
    """Eval raises when neither --frozen nor --root/--slice are provided."""
    try:
        run_eval()
    except EvalRunError as error:
        assert "Either --frozen" in str(error) or "--root and --slice" in str(error)
    else:
        raise AssertionError("Expected EvalRunError when no path is provided")


# ---------------------------------------------------------------------------
# Eval summary
# ---------------------------------------------------------------------------


def test_eval_summary_is_machine_readable(tmp_path: Path) -> None:
    """eval_summary returns a machine-readable JSON-compatible dict."""
    root = _build_pilot_root(tmp_path)
    export_dir = _freeze_pilot(root)

    expt_name = _unique_experiment_name()
    result = run_eval(
        frozen_path=export_dir,
        experiment_name=expt_name,
    )

    summary = eval_summary(result)
    assert summary["authority"] == "local"
    assert summary["operation"] == "eval-run"
    assert summary["eval_id"] == result.eval_id
    assert summary["experiment_id"] == result.experiment_id
    # Must be JSON-serializable
    json.dumps(summary)
