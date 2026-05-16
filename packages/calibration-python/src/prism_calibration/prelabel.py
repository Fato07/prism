"""AI pre-label normalization and review-routing policy for calibration rows."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast, get_args

from pydantic import ValidationError

from prism_calibration.layout import bootstrap_corpus_root
from prism_calibration.lineage import LoadedRow, load_corpus_rows, validate_lineage_integrity
from prism_calibration.models import (
    CalibrationRow,
    ReviewRouteReason,
    ReviewRouting,
    ReviewState,
    ReviewStatus,
    RubricPreLabel,
    SplitName,
    VerdictBand,
)
from prism_calibration.splits import write_row

PRELABEL_RUN_AT = datetime(2026, 5, 16, 13, 0, tzinfo=UTC)
PRELABEL_RUBRIC_VERSION = "prism-calibration-v1"
PRELABEL_MODEL_FAMILY = "openai-gpt"
PRELABEL_MODEL_NAME = "local-prism-rubric-prelabeler-v1"
PRELABEL_RUN_ID = "prelabel-local-rubric-v1"
LOW_CONFIDENCE_THRESHOLD = 0.70
HIGH_CONFIDENCE_THRESHOLD = 0.85
PRELABEL_SLICE_ALIASES = frozenset({"pilot-seed", "all-private"})
NORMALIZED_RUBRIC_FIELDS = (
    "reasoning_quality",
    "evidence_quality",
    "calibration_quality",
    "verdict_band",
    "failure_tags",
    "confidence",
)
SPLIT_NAMES = frozenset(cast(tuple[str, ...], get_args(SplitName)))

QUALITY_WORDS = {
    "excellent": 95,
    "high": 85,
    "good": 80,
    "medium": 60,
    "mixed": 55,
    "low": 30,
    "poor": 20,
}
VERDICT_ALIASES = {
    "reject": "REJECT",
    "rejected": "REJECT",
    "warn": "WARN",
    "warning": "WARN",
    "pass": "PASS",
    "passed": "PASS",
    "endorse": "ENDORSE",
    "endorsed": "ENDORSE",
}
FAILURE_TAG_ALIASES = {
    "calibration overconfidence": "calibration-overconfidence",
    "calibration_overconfidence": "calibration-overconfidence",
    "overconfidence": "calibration-overconfidence",
    "missing counterevidence": "missing-counterevidence",
    "missing_counterevidence": "missing-counterevidence",
    "weak evidence": "weak-evidence",
    "weak_evidence": "weak-evidence",
    "stale evidence": "stale-evidence",
    "stale_evidence": "stale-evidence",
}
FAILURE_TAG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class PrelabelError(ValueError):
    """Raised when pre-label normalization or routing cannot proceed."""


@dataclass(frozen=True)
class RoutedPrelabelRow:
    """One row updated by a pre-labeling run."""

    row_id: str
    path: Path
    status: ReviewStatus
    verdict_band: VerdictBand
    confidence: float
    failure_tags: tuple[str, ...]
    route_reasons: tuple[ReviewRouteReason, ...]


@dataclass(frozen=True)
class PrelabelRunResult:
    """Summary metadata for a pre-labeling run."""

    slice_name: str
    resolved_slice: str
    manifest_path: Path
    rows: tuple[RoutedPrelabelRow, ...]


def _required_value(raw: Mapping[str, object], field_name: str) -> object:
    """Return a required raw field or raise an actionable pre-label error."""
    if field_name not in raw:
        raise PrelabelError(f"AI pre-label output missing required field: {field_name}")
    return raw[field_name]


def _quality_score(value: object, *, field_name: str) -> int:
    """Normalize a rubric quality field into a 0-100 integer."""
    if isinstance(value, bool):
        raise PrelabelError(f"{field_name} must be a score or quality band, not bool")
    if isinstance(value, int):
        score = value
    elif isinstance(value, float):
        score = round(value * 100) if 0.0 <= value <= 1.0 else round(value)
    elif isinstance(value, str):
        key = value.strip().lower()
        if key not in QUALITY_WORDS:
            raise PrelabelError(
                f"{field_name} uses unknown quality band '{value}'. "
                f"Known bands: {', '.join(sorted(QUALITY_WORDS))}"
            )
        score = QUALITY_WORDS[key]
    else:
        raise PrelabelError(f"{field_name} must be a numeric score or quality band")

    if not 0 <= score <= 100:
        raise PrelabelError(f"{field_name} must normalize into the 0-100 range")
    return score


def _confidence(value: object) -> float:
    """Normalize a confidence field into the 0-1 range."""
    if isinstance(value, bool):
        raise PrelabelError("confidence must be numeric, not bool")
    if not isinstance(value, int | float):
        raise PrelabelError("confidence must be numeric")
    normalized = float(value)
    if 1.0 < normalized <= 100.0:
        normalized = normalized / 100.0
    if not 0.0 <= normalized <= 1.0:
        raise PrelabelError("confidence must normalize into the 0-1 range")
    return round(normalized, 4)


def _verdict_band(value: object) -> VerdictBand:
    """Normalize a raw verdict band into Prism's sentinel-compatible labels."""
    if not isinstance(value, str):
        raise PrelabelError("verdict_band must be a string")
    key = value.strip().lower()
    verdict = VERDICT_ALIASES.get(key, value.strip().upper())
    if verdict not in get_args(VerdictBand):
        allowed = ", ".join(get_args(VerdictBand))
        raise PrelabelError(f"Unknown verdict_band '{value}'. Expected one of: {allowed}")
    return cast(VerdictBand, verdict)


def _failure_tag(value: object) -> str:
    """Normalize one failure tag into lower-kebab form."""
    if not isinstance(value, str):
        raise PrelabelError("failure_tags entries must be strings")
    stripped = value.strip().lower()
    if not stripped:
        raise PrelabelError("failure_tags entries cannot be empty")
    aliased = FAILURE_TAG_ALIASES.get(stripped, stripped)
    normalized = re.sub(r"[^a-z0-9]+", "-", aliased).strip("-")
    if not FAILURE_TAG_PATTERN.match(normalized):
        raise PrelabelError(f"failure tag '{value}' does not normalize to lower-kebab form")
    return normalized


def _failure_tags(value: object) -> list[str]:
    """Normalize failure tags into a sorted unique lower-kebab list."""
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise PrelabelError("failure_tags must be a list of strings")
    return sorted({_failure_tag(item) for item in value})


def normalize_prelabel_output(
    raw: Mapping[str, object],
    *,
    model_name: str,
    model_family: str = PRELABEL_MODEL_FAMILY,
    labeled_at: datetime = PRELABEL_RUN_AT,
) -> RubricPreLabel:
    """Normalize raw AI pre-label output into Prism-compatible rubric fields."""
    try:
        return RubricPreLabel(
            reasoning_quality=_quality_score(
                _required_value(raw, "reasoning_quality"),
                field_name="reasoning_quality",
            ),
            evidence_quality=_quality_score(
                _required_value(raw, "evidence_quality"),
                field_name="evidence_quality",
            ),
            calibration_quality=_quality_score(
                _required_value(raw, "calibration_quality"),
                field_name="calibration_quality",
            ),
            verdict_band=_verdict_band(_required_value(raw, "verdict_band")),
            failure_tags=_failure_tags(_required_value(raw, "failure_tags")),
            confidence=_confidence(_required_value(raw, "confidence")),
            model_family=model_family,
            model_name=model_name,
            labeled_at=labeled_at,
        )
    except ValidationError as error:
        raise PrelabelError(f"Normalized AI pre-label failed schema validation: {error}") from error


def _mean_score(labels: Sequence[RubricPreLabel], field_name: str) -> int:
    """Return a rounded mean score for one rubric field."""
    values = [getattr(label, field_name) for label in labels]
    return round(sum(values) / len(values))


def _labels_disagree(labels: Sequence[RubricPreLabel]) -> bool:
    """Return whether multiple AI labels conflict on band or failure tags."""
    verdict_bands = {label.verdict_band for label in labels}
    tag_sets = {tuple(label.failure_tags) for label in labels}
    return len(verdict_bands) > 1 or len(tag_sets) > 1


def _consensus_label(labels: Sequence[RubricPreLabel]) -> RubricPreLabel:
    """Return a normalized consensus label for agreeing AI pre-labels."""
    first = labels[0]
    return RubricPreLabel(
        reasoning_quality=_mean_score(labels, "reasoning_quality"),
        evidence_quality=_mean_score(labels, "evidence_quality"),
        calibration_quality=_mean_score(labels, "calibration_quality"),
        verdict_band=first.verdict_band,
        failure_tags=list(first.failure_tags),
        confidence=min(label.confidence for label in labels),
        model_family=first.model_family,
        model_name="consensus:" + "+".join(label.model_name for label in labels),
        labeled_at=max(label.labeled_at for label in labels),
    )


def _union_failure_tags(labels: Sequence[RubricPreLabel]) -> list[str]:
    """Return all normalized failure tags present across labels."""
    return sorted({tag for label in labels for tag in label.failure_tags})


def _routing_reasons(
    row: CalibrationRow,
    labels: Sequence[RubricPreLabel],
) -> tuple[ReviewRouteReason, ...]:
    """Return explicit routing reasons for one row and its AI labels."""
    reasons: list[ReviewRouteReason] = []
    if row.split.name == "holdout":
        reasons.append("holdout_locked")
    if any(label.confidence < LOW_CONFIDENCE_THRESHOLD for label in labels):
        reasons.append("low_confidence")
    if len(labels) > 1 and _labels_disagree(labels):
        reasons.append("label_disagreement")
    return tuple(reasons)


def apply_prelabels_to_row(
    row: CalibrationRow,
    labels: Sequence[RubricPreLabel],
    *,
    routed_at: datetime = PRELABEL_RUN_AT,
) -> CalibrationRow:
    """Apply normalized labels and review-routing policy to one calibration row."""
    if not labels:
        raise PrelabelError(f"row {row.row_id}: at least one AI pre-label is required")

    reasons = _routing_reasons(row, labels)
    high_confidence_consensus = (
        not reasons
        and len(labels) > 1
        and not _labels_disagree(labels)
        and min(label.confidence for label in labels) >= HIGH_CONFIDENCE_THRESHOLD
    )
    if reasons:
        status: ReviewStatus = "manual_review"
        destination: Literal["manual_review", "auto_resolved"] = "manual_review"
        route_reasons = list(reasons)
        canonical_label = labels[0]
    elif high_confidence_consensus:
        status = "ai_resolved"
        destination = "auto_resolved"
        route_reasons = ["high_confidence_consensus"]
        canonical_label = _consensus_label(labels)
    else:
        status = "manual_review"
        destination = "manual_review"
        route_reasons = ["needs_manual_review"]
        canonical_label = labels[0] if len(labels) == 1 else _consensus_label(labels)

    review = ReviewState(
        status=status,
        rubric_version=row.review.rubric_version or PRELABEL_RUBRIC_VERSION,
        failure_tags=_union_failure_tags(labels),
        ai_labels=list(labels),
        canonical_label=canonical_label,
        routing=ReviewRouting(
            destination=destination,
            route_reasons=route_reasons,
            routed_at=routed_at,
        ),
        notes=row.review.notes,
        reviewer=row.review.reviewer,
        reviewed_at=row.review.reviewed_at,
    )
    return row.model_copy(update={"review": review})


def _raw_labels_for_row(row: CalibrationRow) -> tuple[Mapping[str, object], ...]:
    """Return deterministic local AI-label-like rubric outputs for one row."""
    tags = set(row.review.failure_tags)
    evidence_confidence = min(
        (evidence.confidence for evidence in row.trace.evidence),
        default=0.75,
    )

    if not tags and evidence_confidence >= 0.75:
        return (
            {
                "reasoning_quality": 90,
                "evidence_quality": 88,
                "calibration_quality": 86,
                "verdict_band": "PASS",
                "failure_tags": [],
                "confidence": 0.93,
            },
            {
                "reasoning_quality": 88,
                "evidence_quality": 87,
                "calibration_quality": 85,
                "verdict_band": "PASS",
                "failure_tags": [],
                "confidence": 0.9,
            },
        )

    if "calibration-overconfidence" in tags:
        return (
            {
                "reasoning_quality": 52,
                "evidence_quality": 58,
                "calibration_quality": 32,
                "verdict_band": "WARN",
                "failure_tags": ["calibration-overconfidence"],
                "confidence": 0.82,
            },
            {
                "reasoning_quality": 44,
                "evidence_quality": 50,
                "calibration_quality": 24,
                "verdict_band": "REJECT",
                "failure_tags": ["calibration-overconfidence"],
                "confidence": 0.8,
            },
        )

    if "missing-counterevidence" in tags:
        return (
            {
                "reasoning_quality": 48,
                "evidence_quality": 42,
                "calibration_quality": 55,
                "verdict_band": "WARN",
                "failure_tags": ["missing-counterevidence"],
                "confidence": 0.76,
            },
            {
                "reasoning_quality": 39,
                "evidence_quality": 34,
                "calibration_quality": 48,
                "verdict_band": "REJECT",
                "failure_tags": ["missing-counterevidence", "weak-evidence"],
                "confidence": 0.73,
            },
        )

    if "weak-evidence" in tags:
        return (
            {
                "reasoning_quality": 62,
                "evidence_quality": 41,
                "calibration_quality": 60,
                "verdict_band": "WARN",
                "failure_tags": ["weak-evidence"],
                "confidence": 0.64,
            },
            {
                "reasoning_quality": 60,
                "evidence_quality": 46,
                "calibration_quality": 58,
                "verdict_band": "WARN",
                "failure_tags": ["weak-evidence"],
                "confidence": 0.72,
            },
        )

    return (
        {
            "reasoning_quality": 58,
            "evidence_quality": 52,
            "calibration_quality": 56,
            "verdict_band": "WARN",
            "failure_tags": sorted(tags),
            "confidence": 0.68,
        },
        {
            "reasoning_quality": 57,
            "evidence_quality": 50,
            "calibration_quality": 54,
            "verdict_band": "WARN",
            "failure_tags": sorted(tags),
            "confidence": 0.71,
        },
    )


def deterministic_prelabels_for_row(row: CalibrationRow) -> tuple[RubricPreLabel, ...]:
    """Return deterministic normalized AI pre-labels for local CLI use."""
    normalized: list[RubricPreLabel] = []
    for index, raw in enumerate(_raw_labels_for_row(row), start=1):
        normalized.append(
            normalize_prelabel_output(
                raw,
                model_family=PRELABEL_MODEL_FAMILY,
                model_name=f"{PRELABEL_MODEL_NAME}:{index}",
            )
        )
    return tuple(normalized)


def _resolved_slice(slice_name: str) -> str:
    """Resolve a pre-label slice selector into a selection policy name."""
    if slice_name in PRELABEL_SLICE_ALIASES:
        return "all-private"
    if slice_name in SPLIT_NAMES:
        return slice_name
    allowed = ", ".join(sorted((*PRELABEL_SLICE_ALIASES, *SPLIT_NAMES)))
    raise PrelabelError(f"Unknown prelabel slice '{slice_name}'. Expected one of: {allowed}")


def _select_rows(rows: tuple[LoadedRow, ...], *, resolved_slice: str) -> tuple[LoadedRow, ...]:
    """Select rows for a pre-labeling run from already-loaded local rows."""
    if resolved_slice == "all-private":
        selected = [
            loaded for loaded in rows if loaded.row.split.name != "sample"
        ]
    else:
        selected = [loaded for loaded in rows if loaded.row.split.name == resolved_slice]
    return tuple(sorted(selected, key=lambda loaded: loaded.row.row_id))


def _prelabel_manifest_path(root: Path, slice_name: str) -> Path:
    """Return the local manifest path for a pre-labeling run."""
    safe_slice = re.sub(r"[^a-zA-Z0-9_.-]+", "-", slice_name).strip("-") or "slice"
    return root / "manifests" / f"prelabel-{safe_slice}-{PRELABEL_RUN_ID}.json"


def run_prelabeling(*, root: Path, slice_name: str) -> PrelabelRunResult:
    """Apply deterministic normalized AI pre-labels to rows in a local slice."""
    layout = bootstrap_corpus_root(root)
    resolved = _resolved_slice(slice_name)
    rows = load_corpus_rows(layout.root, include_sample=True)
    validate_lineage_integrity(rows)
    selected_rows = _select_rows(rows, resolved_slice=resolved)
    routed_rows: list[RoutedPrelabelRow] = []

    for loaded in selected_rows:
        labels = deterministic_prelabels_for_row(loaded.row)
        updated = apply_prelabels_to_row(loaded.row, labels)
        write_row(loaded.path, updated)
        canonical = updated.review.canonical_label
        routing = updated.review.routing
        if canonical is None or routing is None:
            raise PrelabelError(f"row {updated.row_id}: prelabel routing did not persist")
        routed_rows.append(
            RoutedPrelabelRow(
                row_id=updated.row_id,
                path=loaded.path,
                status=updated.review.status,
                verdict_band=canonical.verdict_band,
                confidence=canonical.confidence,
                failure_tags=tuple(canonical.failure_tags),
                route_reasons=tuple(routing.route_reasons),
            )
        )

    result = PrelabelRunResult(
        slice_name=slice_name,
        resolved_slice=resolved,
        manifest_path=_prelabel_manifest_path(layout.root, slice_name),
        rows=tuple(routed_rows),
    )
    _write_prelabel_manifest(result)
    return result


def _counter_payload(counter: Counter[str]) -> dict[str, int]:
    """Return a stable JSON payload for string counters."""
    return dict(sorted(counter.items()))


def prelabel_summary(result: PrelabelRunResult) -> dict[str, Any]:
    """Return the machine-readable public summary for a pre-labeling run."""
    status_counts: Counter[str] = Counter(row.status for row in result.rows)
    route_reasons: Counter[str] = Counter(
        reason for row in result.rows for reason in row.route_reasons
    )
    manual_queue_row_ids = [
        row.row_id for row in result.rows if row.status == "manual_review"
    ]
    auto_resolved_row_ids = [
        row.row_id for row in result.rows if row.status == "ai_resolved"
    ]
    return {
        "authority": "local",
        "auto_resolved_row_ids": auto_resolved_row_ids,
        "manual_queue_row_ids": manual_queue_row_ids,
        "manifest_path": str(result.manifest_path),
        "normalized_fields": list(NORMALIZED_RUBRIC_FIELDS),
        "operation": "prelabel",
        "resolved_slice": result.resolved_slice,
        "route_reason_counts": _counter_payload(route_reasons),
        "row_count": len(result.rows),
        "rows": [
            {
                "confidence": row.confidence,
                "failure_tags": list(row.failure_tags),
                "path": str(row.path),
                "route_reasons": list(row.route_reasons),
                "row_id": row.row_id,
                "status": row.status,
                "verdict_band": row.verdict_band,
            }
            for row in result.rows
        ],
        "run_id": PRELABEL_RUN_ID,
        "slice": result.slice_name,
        "status_counts": _counter_payload(status_counts),
    }


def _write_prelabel_manifest(result: PrelabelRunResult) -> None:
    """Write the pre-labeling run manifest."""
    result.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    result.manifest_path.write_text(
        json.dumps(prelabel_summary(result), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
