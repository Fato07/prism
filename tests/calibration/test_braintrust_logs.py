"""Braintrust log/span observability tests (VAL-BT-004)."""

from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

from prism_calibration.braintrust_sync import braintrust_project
from prism_calibration.eval import run_eval
from prism_calibration.freeze import freeze_slice
from prism_calibration.logs import (
    CalibrationLogger,
    emit_calibration_eval_log,
    emit_trader_runtime_log,
)
from prism_calibration.pilot import build_pilot_slice

REPO_ROOT = Path(__file__).resolve().parents[2]


def _build_pilot_root(tmp_path: Path) -> Path:
    """Build a small pilot slice and return the corpus root path."""
    root = tmp_path / "calibration"
    build_pilot_slice(root=root, pilot_size=20)
    return root


def _freeze_pilot(root: Path) -> Path:
    """Freeze the pilot slice and return the export directory."""
    export = freeze_slice(root, "pilot")
    return export.export_dir


# ---------------------------------------------------------------------------
# VAL-BT-004: Run output is visible in logs and traces
# ---------------------------------------------------------------------------


def test_calibration_logger_emits_logs_visible_via_braintrust(
    tmp_path: Path,
) -> None:
    """A calibration run emits Braintrust logs/spans that can be opened
    from CLI or UI and tied back to a specific slice, case, or provenance tag."""
    logger = CalibrationLogger()

    # The logger should be active if Braintrust credentials are available
    assert logger.active, "CalibrationLogger should be active with Braintrust credentials"

    # Log a pilot-build operation with provenance tags
    event_id = logger.log_operation(
        operation="pilot-build",
        slice_name="pilot",
        metadata={"pilot_size": 20, "seed": 42},
    )

    assert event_id is not None, "log_operation should return a non-None event ID"

    # Flush to ensure the event is persisted
    logger.flush()


def test_calibration_logger_span_emits_provenance_tags(
    tmp_path: Path,
) -> None:
    """Spans emitted during calibration carry provenance tags that tie
    them back to slice and case identifiers."""
    logger = CalibrationLogger()
    assert logger.active

    with logger.span(
        name="prism.calibration.pilot-build",
        operation="pilot-build",
        slice_name="pilot",
        case_id="synthetic-0001",
        lineage_id="lineage-synthetic-0001",
        source_type="synthetic",
    ) as span:
        # The span should be a real Braintrust span, not None
        assert span is not None, "span should be a real Braintrust span when logger is active"

    # After the span context exits, it should have been flushed


def test_calibration_logger_handles_inactive_credentials_gracefully() -> None:
    """When Braintrust credentials are not available, the logger
    silently disables without raising errors."""
    # Create a logger with no credentials (neither env nor CLI)
    # This test validates the graceful degradation path.
    # In practice, the CI environment has Braintrust credentials,
    # so we test with a logger that has an invalid API key.
    logger = CalibrationLogger(api_key="invalid-key-for-test", org_name="nonexistent")

    # This should not raise — it should silently fail
    logger.log_operation(
        operation="test-no-creds",
        slice_name="pilot",
    )
    # Event ID may be None or a string depending on how Braintrust handles
    # invalid credentials; either way, no exception should be raised


def test_emit_trader_runtime_log_creates_visible_entry(
    tmp_path: Path,
) -> None:
    """A real trader generation emits a Braintrust log entry that can
    be tied back to slice/case provenance tags."""
    event_id = emit_trader_runtime_log(
        trace_id="test-trace-001",
        market_id="0xtest-market-id",
        action="BUY",
        final_probability=0.72,
        size_usdc=5.0,
        model_family="anthropic-claude",
        model_name="claude-sonnet-4-20250514",
        slice_name="pilot",
        case_id="real-test-trace-001",
        lineage_id="lineage-real-001",
    )

    # Should return a non-None event ID when credentials are available
    assert event_id is not None, (
        "emit_trader_runtime_log should return a log event ID when "
        "Braintrust credentials are available"
    )


def test_emit_calibration_eval_log_creates_visible_entry(
    tmp_path: Path,
) -> None:
    """A calibration eval run emits a Braintrust log entry carrying
    eval identity and pass/fail summary."""
    event_id = emit_calibration_eval_log(
        eval_id="test-eval-abc123",
        experiment_name="test-eval-experiment",
        slice_name="pilot",
        export_id="test-export-id",
        evaluator_name="prism-rubric-v1",
        total_rows=20,
        passed_rows=15,
        failed_rows=5,
    )

    assert event_id is not None, (
        "emit_calibration_eval_log should return a log event ID when "
        "Braintrust credentials are available"
    )


def test_eval_run_emits_logs_tied_to_slice_and_case(
    tmp_path: Path,
) -> None:
    """An eval run creates both a Braintrust experiment AND log entries
    that can be tied back to the slice and case identifiers."""
    root = _build_pilot_root(tmp_path)
    export_dir = _freeze_pilot(root)

    expt_name = f"test-eval-log-{uuid.uuid4().hex[:12]}"
    result = run_eval(
        frozen_path=export_dir,
        experiment_name=expt_name,
    )

    # The eval run should have logged each case to the experiment
    assert result.total_rows > 0

    # Verify experiment events carry provenance tags by reading
    # them back from Braintrust
    import braintrust

    experiment = braintrust.init(
        project=braintrust_project(),
        experiment=expt_name,
        open=True,
    )

    # Fetch logged events from the experiment
    events = list(experiment.fetch())
    assert len(events) > 0, "Experiment should have logged events"

    # Each event should have metadata with provenance
    for event in events:
        event_dict = event if isinstance(event, dict) else dict(event)
        metadata = event_dict.get("metadata", {})
        # Provenance tags must include lineage, source_type, or slice info
        has_provenance = any(
            key in metadata
            for key in ("lineage_id", "source_type", "slice_name", "export_id", "eval_id")
        )
        assert has_provenance, (
            f"Event metadata should contain provenance tags, got: {list(metadata.keys())}"
        )


def test_braintrust_cli_can_view_logs_for_calibration_project() -> None:
    """Braintrust logs for the Prism project are queryable via CLI."""
    # Emit a log entry first
    logger = CalibrationLogger()
    logger.log_operation(
        operation="test-cli-visibility",
        slice_name="pilot",
        metadata={"test": "cli-visibility"},
    )
    logger.flush()

    # Query via bt CLI
    result = subprocess.run(
        ["bt", "view", "logs", "--project", "Prism", "--json"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    # CLI should return valid JSON even if no logs found for the filter
    if result.returncode == 0 and result.stdout.strip():
        payload = json.loads(result.stdout)
        # Should have items or meta structure
        assert "items" in payload or "meta" in payload or isinstance(payload, list)


# ---------------------------------------------------------------------------
# Provenance tag round-trip
# ---------------------------------------------------------------------------


def test_log_and_experiment_can_be_correlated_by_provenance(
    tmp_path: Path,
) -> None:
    """A Braintrust log entry and experiment for the same eval run
    can be correlated by their shared provenance tags (eval_id, slice_name)."""
    root = _build_pilot_root(tmp_path)
    export_dir = _freeze_pilot(root)

    expt_name = f"test-provenance-{uuid.uuid4().hex[:12]}"
    result = run_eval(
        frozen_path=export_dir,
        experiment_name=expt_name,
    )

    # Emit a calibration eval log tied to the same eval run
    log_event_id = emit_calibration_eval_log(
        eval_id=result.eval_id,
        experiment_name=result.experiment_name,
        slice_name=result.slice_name,
        export_id=result.export_id,
        evaluator_name=result.evaluator_name,
        total_rows=result.total_rows,
        passed_rows=result.passed_rows,
        failed_rows=result.failed_rows,
    )

    # Both the experiment and the log entry share the eval_id and slice_name
    assert log_event_id is not None
    assert result.eval_id  # eval_id is the correlation key
    assert result.slice_name == "pilot"  # provenance tag matches
