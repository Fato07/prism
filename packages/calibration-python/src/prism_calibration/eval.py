"""Frozen-slice regression evaluation with Braintrust experiment integration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from prism_calibration.braintrust_sync import BRAINTRUST_PROJECT
from prism_calibration.freeze import FrozenExportManifest, _load_manifest
from prism_calibration.models import CalibrationRow

EVAL_SCHEMA_VERSION: Literal["1.0"] = "1.0"
EVAL_KIND: Literal["prism_calibration.eval_result"] = "prism_calibration.eval_result"
EVAL_IDENTITY_ALGORITHM: Literal["sha256:eval-result-v1"] = "sha256:eval-result-v1"

# Default evaluator configuration
DEFAULT_EVALUATOR_NAME = "prism-rubric-v1"
DEFAULT_EVALUATOR_MODEL = "local-prism-rubric-prelabeler-v1"


class EvalRunError(ValueError):
    """Raised when an eval run cannot proceed."""


@dataclass(frozen=True)
class EvalCaseResult:
    """Result of evaluating one calibration row."""

    row_id: str
    trace_id: str
    lineage_id: str
    source_type: str
    verdict_band: str
    confidence: float
    failure_tags: tuple[str, ...]
    reasoning_quality: int
    evidence_quality: int
    calibration_quality: int
    score: float
    passed: bool


@dataclass(frozen=True)
class EvalRunResult:
    """Summary of one evaluation run against a frozen slice."""

    operation: str
    eval_id: str
    experiment_name: str
    experiment_id: str
    slice_name: str
    export_id: str
    export_dir: Path
    evaluator_name: str
    evaluator_model: str
    run_config: dict[str, Any]
    timestamp: str
    total_rows: int
    passed_rows: int
    failed_rows: int
    case_results: tuple[EvalCaseResult, ...]
    results_path: Path


def _load_frozen_rows(export_dir: Path, manifest: FrozenExportManifest) -> list[CalibrationRow]:
    """Load all rows from a frozen export directory."""
    rows: list[CalibrationRow] = []
    for entry in manifest.rows:
        row_path = export_dir / entry.path
        if not row_path.exists():
            continue
        raw = row_path.read_text(encoding="utf-8")
        payload = json.loads(raw)
        rows.append(CalibrationRow.model_validate(payload))
    return rows


def _compute_eval_id(
    *,
    export_id: str,
    evaluator_name: str,
    run_config: dict[str, Any],
) -> str:
    """Compute a deterministic eval identity from slice and evaluator config."""
    import hashlib

    payload = json.dumps(
        {"export_id": export_id, "evaluator_name": evaluator_name, "run_config": run_config},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _evaluate_row(row: CalibrationRow) -> EvalCaseResult:
    """Evaluate a single calibration row against the rubric.

    Uses the row's existing review label as the ground truth and
    recomputes a score based on rubric alignment. For rows with
    canonical labels, the score measures how well the row's quality
    fields align with the expected verdict band. For unreviewed rows,
    a neutral score is assigned.
    """
    label = row.review.canonical_label
    if label is not None:
        verdict_band = label.verdict_band
        confidence = label.confidence
        failure_tags = tuple(label.failure_tags)
        reasoning_quality = label.reasoning_quality
        evidence_quality = label.evidence_quality
        calibration_quality = label.calibration_quality
    else:
        verdict_band = "WARN"
        confidence = 0.5
        failure_tags = tuple(row.review.failure_tags)
        reasoning_quality = 50
        evidence_quality = 50
        calibration_quality = 50

    # Score: normalized alignment between quality metrics and verdict band
    # PASS/ENDORSE → high scores expected; WARN → moderate; REJECT → low expected
    avg_quality = (reasoning_quality + evidence_quality + calibration_quality) / 3.0
    band_thresholds = {"REJECT": 30, "WARN": 55, "PASS": 75, "ENDORSE": 85}
    expected_min = band_thresholds.get(verdict_band, 55)

    if avg_quality >= expected_min:
        score = min(1.0, (avg_quality - expected_min + 25) / 50.0)
    else:
        score = max(0.0, (avg_quality - expected_min + 25) / 50.0)

    passed = score >= 0.5

    return EvalCaseResult(
        row_id=row.row_id,
        trace_id=row.trace.trace_id,
        lineage_id=row.provenance.lineage_id,
        source_type=row.provenance.source_type,
        verdict_band=verdict_band,
        confidence=confidence,
        failure_tags=failure_tags,
        reasoning_quality=reasoning_quality,
        evidence_quality=evidence_quality,
        calibration_quality=calibration_quality,
        score=round(score, 4),
        passed=passed,
    )


def run_eval(
    *,
    root: Path | None = None,
    frozen_path: Path | None = None,
    slice_name: str | None = None,
    evaluator_name: str = DEFAULT_EVALUATOR_NAME,
    evaluator_model: str = DEFAULT_EVALUATOR_MODEL,
    experiment_name: str | None = None,
    run_config: dict[str, Any] | None = None,
) -> EvalRunResult:
    """Run calibration evaluation against a frozen slice and create a Braintrust experiment.

    The evaluation loads rows from a frozen export, evaluates each row against
    the Prism rubric, creates a visible Braintrust experiment with slice and
    evaluator metadata, and emits machine-readable local results keyed to the
    slice hash and run config.

    Args:
        root: Local corpus root path (used to find frozen exports by slice name).
        frozen_path: Direct path to a frozen export directory or manifest.
        slice_name: Target slice name (used with root to find the export).
        evaluator_name: Name of the evaluator configuration.
        evaluator_model: Model identifier used for the evaluator.
        experiment_name: Override the Braintrust experiment name.
        run_config: Additional evaluator configuration to record.

    Returns:
        EvalRunResult with experiment metadata and per-case results.
    """
    try:
        import braintrust
    except ImportError as error:
        raise EvalRunError(
            "braintrust package is required for eval operations"
        ) from error

    # Resolve the frozen export
    export_dir: Path
    manifest: FrozenExportManifest

    if frozen_path is not None:
        manifest_path = frozen_path / "manifest.json" if frozen_path.is_dir() else frozen_path
        manifest = _load_manifest(manifest_path)
        export_dir = manifest_path.parent
    elif root is not None and slice_name is not None:
        from prism_calibration.braintrust_sync import _find_frozen_export
        from prism_calibration.layout import bootstrap_corpus_root
        from prism_calibration.models import SplitName

        layout = bootstrap_corpus_root(root)
        slice_typed: SplitName = slice_name  # type: ignore[assignment]

        found = _find_frozen_export(layout.root, slice_name)
        if found is not None:
            export_dir, manifest_path = found
            manifest = _load_manifest(manifest_path)
        else:
            # Auto-freeze if no export exists
            from prism_calibration.freeze import freeze_slice

            export = freeze_slice(layout.root, slice_typed)
            export_dir = export.export_dir
            manifest = export.manifest
    else:
        raise EvalRunError(
            "Either --frozen <path> or both --root and --slice must be provided"
        )

    # Load rows from the frozen export
    rows = _load_frozen_rows(export_dir, manifest)

    # Compute eval identity
    effective_config = run_config or {}
    eval_id = _compute_eval_id(
        export_id=manifest.export_id,
        evaluator_name=evaluator_name,
        run_config=effective_config,
    )

    # Determine experiment name
    effective_experiment_name = (
        experiment_name
        or f"eval-{manifest.slice_name}-{eval_id[:12]}"
    )

    # Create Braintrust experiment with metadata
    timestamp = datetime.now(UTC).isoformat()
    experiment_metadata: dict[str, Any] = {
        "slice_name": manifest.slice_name,
        "export_id": manifest.export_id,
        "eval_id": eval_id,
        "evaluator_name": evaluator_name,
        "evaluator_model": evaluator_model,
        "run_config": effective_config,
        "row_count": manifest.row_count,
        "timestamp": timestamp,
    }

    experiment = braintrust.init(
        project=BRAINTRUST_PROJECT,
        experiment=effective_experiment_name,
        metadata=experiment_metadata,
        tags=["calibration", "eval", manifest.slice_name],
        update=True,
    )
    experiment_id = experiment.id

    # Evaluate each row and log to Braintrust
    case_results: list[EvalCaseResult] = []
    for row in rows:
        case_result = _evaluate_row(row)
        case_results.append(case_result)

        # Log each case to the Braintrust experiment
        experiment.log(
            id=row.row_id,
            input={
                "row_id": row.row_id,
                "trace_id": row.trace.trace_id,
                "lineage_id": row.provenance.lineage_id,
                "source_type": row.provenance.source_type,
                "market_question": row.trace.market_question,
                "action": row.trace.action,
                "final_probability": row.trace.final_probability,
            },
            output={
                "verdict_band": case_result.verdict_band,
                "confidence": case_result.confidence,
                "failure_tags": list(case_result.failure_tags),
                "reasoning_quality": case_result.reasoning_quality,
                "evidence_quality": case_result.evidence_quality,
                "calibration_quality": case_result.calibration_quality,
                "score": case_result.score,
                "passed": case_result.passed,
            },
            expected={
                "verdict_band": case_result.verdict_band,
                "confidence": case_result.confidence,
            },
            scores={"rubric_alignment": case_result.score},
            metadata={
                "lineage_id": row.provenance.lineage_id,
                "source_type": row.provenance.source_type,
                "split": row.split.name,
                "export_id": manifest.export_id,
                "eval_id": eval_id,
                "slice_name": manifest.slice_name,
            },
            tags=sorted({
                manifest.slice_name,
                row.provenance.source_type,
                row.split.name,
                "eval",
            }),
        )

    experiment.flush()

    # Compute pass/fail counts
    passed_rows = sum(1 for c in case_results if c.passed)
    failed_rows = len(case_results) - passed_rows

    # Write local results artifact
    results_dir = export_dir / "eval-results"
    results_dir.mkdir(parents=True, exist_ok=True)
    results_path = results_dir / f"{eval_id}.json"

    result_payload: dict[str, Any] = {
        "kind": EVAL_KIND,
        "schema_version": EVAL_SCHEMA_VERSION,
        "identity_algorithm": EVAL_IDENTITY_ALGORITHM,
        "eval_id": eval_id,
        "experiment_name": effective_experiment_name,
        "experiment_id": experiment_id,
        "slice_name": manifest.slice_name,
        "export_id": manifest.export_id,
        "evaluator_name": evaluator_name,
        "evaluator_model": evaluator_model,
        "run_config": effective_config,
        "timestamp": timestamp,
        "total_rows": len(case_results),
        "passed_rows": passed_rows,
        "failed_rows": failed_rows,
        "case_results": [
            {
                "row_id": c.row_id,
                "trace_id": c.trace_id,
                "lineage_id": c.lineage_id,
                "source_type": c.source_type,
                "verdict_band": c.verdict_band,
                "confidence": c.confidence,
                "failure_tags": list(c.failure_tags),
                "reasoning_quality": c.reasoning_quality,
                "evidence_quality": c.evidence_quality,
                "calibration_quality": c.calibration_quality,
                "score": c.score,
                "passed": c.passed,
            }
            for c in case_results
        ],
    }
    results_path.write_text(
        json.dumps(result_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return EvalRunResult(
        operation="eval-run",
        eval_id=eval_id,
        experiment_name=effective_experiment_name,
        experiment_id=experiment_id,
        slice_name=manifest.slice_name,
        export_id=manifest.export_id,
        export_dir=export_dir,
        evaluator_name=evaluator_name,
        evaluator_model=evaluator_model,
        run_config=effective_config,
        timestamp=timestamp,
        total_rows=len(case_results),
        passed_rows=passed_rows,
        failed_rows=failed_rows,
        case_results=tuple(case_results),
        results_path=results_path,
    )


def eval_summary(result: EvalRunResult) -> dict[str, Any]:
    """Return a machine-readable CLI summary for an eval run."""
    return {
        "authority": "local",
        "eval_id": result.eval_id,
        "experiment_id": result.experiment_id,
        "experiment_name": result.experiment_name,
        "export_dir": str(result.export_dir),
        "export_id": result.export_id,
        "evaluator_model": result.evaluator_model,
        "evaluator_name": result.evaluator_name,
        "failed_rows": result.failed_rows,
        "operation": result.operation,
        "passed_rows": result.passed_rows,
        "results_path": str(result.results_path),
        "run_config": result.run_config,
        "slice": result.slice_name,
        "timestamp": result.timestamp,
        "total_rows": result.total_rows,
    }
