"""Braintrust dataset sync and review round-trip for calibration rows."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prism_calibration.layout import bootstrap_corpus_root
from prism_calibration.lineage import LoadedRow, load_corpus_rows
from prism_calibration.models import (
    CalibrationRow,
    ReviewState,
    RubricPreLabel,
)
from prism_calibration.splits import write_row

BRAINTRUST_PROJECT = "Prism"
REVIEW_DATASET_PREFIX = "pilot-review-"
SYNC_MANIFEST_PREFIX = "sync-"

# Review status that indicates a human has reviewed the row
REVIEWED_STATUSES = frozenset({"human_reviewed", "approved", "rejected"})


class BraintrustSyncError(ValueError):
    """Raised when Braintrust sync or review round-trip cannot proceed."""


@dataclass(frozen=True)
class SyncPushResult:
    """Summary of a Braintrust push (publish flagged cases for review)."""

    slice_name: str
    dataset_name: str
    dataset_id: str
    pushed_count: int
    pushed_row_ids: list[str]
    skipped_row_ids: list[str]
    manifest_path: Path


@dataclass(frozen=True)
class ReviewDecision:
    """A human-reviewed decision pulled from Braintrust."""

    row_id: str
    record_id: str
    verdict_band: str
    reasoning_quality: int
    evidence_quality: int
    calibration_quality: int
    failure_tags: list[str]
    confidence: float
    reviewer: str
    reviewed_at: datetime
    notes: str | None = None


@dataclass(frozen=True)
class SyncPullResult:
    """Summary of a Braintrust pull (sync reviewed decisions back)."""

    slice_name: str
    dataset_name: str
    dataset_id: str
    pulled_count: int
    updated_row_ids: list[str]
    unchanged_row_ids: list[str]
    not_found_row_ids: list[str]
    manifest_path: Path


def _review_context(row: CalibrationRow) -> dict[str, Any]:
    """Build the review context payload for one flagged row."""
    canonical = row.review.canonical_label
    routing = row.review.routing

    context: dict[str, Any] = {
        "row_id": row.row_id,
        "source_type": row.provenance.source_type,
        "lineage_id": row.provenance.lineage_id,
        "split": row.split.name,
        "failure_tags": row.review.failure_tags,
        "route_reasons": list(routing.route_reasons) if routing else [],
        "holdout_status": row.split.name == "holdout",
    }

    if row.provenance.source_type == "mutated":
        context["parent_row_id"] = row.provenance.parent_row_id
        context["mutation_type"] = row.provenance.mutation_type

    if canonical is not None:
        context["ai_label"] = {
            "verdict_band": canonical.verdict_band,
            "reasoning_quality": canonical.reasoning_quality,
            "evidence_quality": canonical.evidence_quality,
            "calibration_quality": canonical.calibration_quality,
            "failure_tags": canonical.failure_tags,
            "confidence": canonical.confidence,
        }

    return context


def _ai_suggestion(row: CalibrationRow) -> dict[str, Any] | None:
    """Return the AI's canonical label as the expected output for review."""
    canonical = row.review.canonical_label
    if canonical is None:
        return None
    return {
        "verdict_band": canonical.verdict_band,
        "reasoning_quality": canonical.reasoning_quality,
        "evidence_quality": canonical.evidence_quality,
        "calibration_quality": canonical.calibration_quality,
        "failure_tags": canonical.failure_tags,
        "confidence": canonical.confidence,
    }


def _review_metadata(row: CalibrationRow) -> dict[str, Any]:
    """Return metadata for the Braintrust record."""
    return {
        "confidence": row.review.canonical_label.confidence if row.review.canonical_label else 0.0,
        "route_reasons": list(row.review.routing.route_reasons) if row.review.routing else [],
        "source_type": row.provenance.source_type,
        "original_status": row.review.status,
    }


def _sync_manifest_path(root: Path, slice_name: str, operation: str) -> Path:
    """Return the manifest path for a sync operation."""
    safe_slice = "".join(
        char if char.isalnum() else "-" for char in slice_name
    ).strip("-")
    return root / "manifests" / f"{SYNC_MANIFEST_PREFIX}{operation}-{safe_slice}.json"


def push_flagged_to_braintrust(
    *,
    root: Path,
    slice_name: str,
) -> SyncPushResult:
    """Push flagged (manual_review) rows to a Braintrust review dataset."""
    try:
        import braintrust
    except ImportError as error:
        raise BraintrustSyncError(
            "braintrust package is required for sync operations"
        ) from error

    layout = bootstrap_corpus_root(root)
    loaded_rows = load_corpus_rows(layout.root, include_sample=False)

    # Select rows for the target slice
    target_rows = [
        loaded
        for loaded in loaded_rows
        if loaded.row.split.name == slice_name
    ]

    # Filter to flagged (manual_review) rows only
    flagged_rows = [
        loaded
        for loaded in target_rows
        if loaded.row.review.status == "manual_review"
        and loaded.row.review.canonical_label is not None
    ]

    if not flagged_rows:
        raise BraintrustSyncError(
            f"No flagged rows found for slice '{slice_name}'. "
            "Run prelabeling first to route rows for review."
        )

    # Create or open the Braintrust dataset
    dataset_name = f"{REVIEW_DATASET_PREFIX}{slice_name}"
    dataset = braintrust.init_dataset(project=BRAINTRUST_PROJECT, name=dataset_name)

    pushed_row_ids: list[str] = []
    skipped_row_ids: list[str] = []

    for loaded in flagged_rows:
        row = loaded.row
        ai_suggestion = _ai_suggestion(row)
        if ai_suggestion is None:
            skipped_row_ids.append(row.row_id)
            continue

        context = _review_context(row)
        metadata = _review_metadata(row)

        # Use row_id as the stable Braintrust record ID for upsert
        dataset.insert(
            id=row.row_id,
            input=context,
            expected=ai_suggestion,
            metadata=metadata,
            tags=["review", "flagged", slice_name],
        )
        pushed_row_ids.append(row.row_id)

    dataset.flush()

    manifest_path = _sync_manifest_path(layout.root, slice_name, "push")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_payload: dict[str, Any] = {
        "authority": "local",
        "dataset_id": dataset.id,
        "dataset_name": dataset_name,
        "operation": "sync-push",
        "pushed_count": len(pushed_row_ids),
        "pushed_row_ids": sorted(pushed_row_ids),
        "skipped_row_ids": sorted(skipped_row_ids),
        "slice": slice_name,
    }
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return SyncPushResult(
        slice_name=slice_name,
        dataset_name=dataset_name,
        dataset_id=dataset.id,
        pushed_count=len(pushed_row_ids),
        pushed_row_ids=pushed_row_ids,
        skipped_row_ids=skipped_row_ids,
        manifest_path=manifest_path,
    )


def _parse_review_decision(
    record: dict[str, Any],
) -> ReviewDecision | None:
    """Parse a Braintrust record into a review decision if it was human-reviewed."""
    metadata = record.get("metadata") or {}

    # Check if the record has been reviewed by examining metadata
    # The reviewer stores their decision via the Braintrust UI or SDK update
    reviewer = metadata.get("reviewer", "")
    reviewed_at_str = metadata.get("reviewed_at", "")

    if not reviewer or not reviewed_at_str:
        return None

    expected = record.get("expected") or {}
    if not isinstance(expected, dict):
        return None

    record_id = record.get("id", "")

    # Parse the reviewed-at timestamp
    try:
        if isinstance(reviewed_at_str, str):
            reviewed_at = datetime.fromisoformat(
                reviewed_at_str.replace("Z", "+00:00")
            )
        else:
            reviewed_at = PILOT_BUILD_CREATED_AT
    except (ValueError, TypeError):
        reviewed_at = datetime.now(UTC)

    return ReviewDecision(
        row_id=record.get("input", {}).get("row_id", ""),
        record_id=str(record_id),
        verdict_band=expected.get("verdict_band", "WARN"),
        reasoning_quality=int(expected.get("reasoning_quality", 50)),
        evidence_quality=int(expected.get("evidence_quality", 50)),
        calibration_quality=int(expected.get("calibration_quality", 50)),
        failure_tags=expected.get("failure_tags", []),
        confidence=float(expected.get("confidence", 0.5)),
        reviewer=reviewer,
        reviewed_at=reviewed_at,
        notes=metadata.get("reviewer_notes"),
    )


def _apply_review_decision(
    row: CalibrationRow,
    decision: ReviewDecision,
) -> CalibrationRow:
    """Apply a human-reviewed decision onto a local row, preserving AI history."""
    # Build the human-reviewed label from the decision
    human_label = RubricPreLabel(
        reasoning_quality=decision.reasoning_quality,
        evidence_quality=decision.evidence_quality,
        calibration_quality=decision.calibration_quality,
        verdict_band=decision.verdict_band,  # type: ignore[arg-type]
        failure_tags=list(decision.failure_tags),
        confidence=decision.confidence,
        model_family="human-reviewer",
        model_name=decision.reviewer,
        labeled_at=decision.reviewed_at,
    )

    # Preserve the original AI labels and update canonical + review state
    review = ReviewState(
        status="human_reviewed",
        rubric_version=row.review.rubric_version,
        failure_tags=list(decision.failure_tags),
        ai_labels=list(row.review.ai_labels),  # original AI suggestions preserved
        canonical_label=human_label,  # updated to human-reviewed decision
        routing=row.review.routing,
        notes=decision.notes or row.review.notes,
        reviewer=decision.reviewer,
        reviewed_at=decision.reviewed_at,
    )

    return row.model_copy(update={"review": review})


PILOT_BUILD_CREATED_AT = datetime(2026, 5, 16, 14, 0, tzinfo=UTC)


def pull_review_from_braintrust(
    *,
    root: Path,
    slice_name: str,
) -> SyncPullResult:
    """Pull reviewed decisions from Braintrust and sync back onto local rows."""
    try:
        import braintrust
    except ImportError as error:
        raise BraintrustSyncError(
            "braintrust package is required for sync operations"
        ) from error

    layout = bootstrap_corpus_root(root)
    loaded_rows = load_corpus_rows(layout.root, include_sample=False)

    # Index local rows by row_id
    row_index: dict[str, LoadedRow] = {}
    for lr in loaded_rows:
        row_index[lr.row.row_id] = lr

    # Open the Braintrust review dataset
    dataset_name = f"{REVIEW_DATASET_PREFIX}{slice_name}"
    try:
        dataset = braintrust.init_dataset(project=BRAINTRUST_PROJECT, name=dataset_name)
    except Exception as error:
        raise BraintrustSyncError(
            f"Unable to open Braintrust dataset '{dataset_name}': {error}"
        ) from error

    # Fetch all records from the dataset
    records = list(dataset.fetch())

    updated_row_ids: list[str] = []
    unchanged_row_ids: list[str] = []
    not_found_row_ids: list[str] = []

    for record in records:
        # Braintrust DatasetEvent is dict-like but not typed as dict[str, Any]
        record_dict: dict[str, Any] = (
            record if isinstance(record, dict) else dict(record)  # type: ignore[assignment]
        )

        input_data = record_dict.get("input") or {}
        row_id: str = input_data.get("row_id", "")
        if not row_id:
            continue

        loaded: LoadedRow | None = row_index.get(row_id)
        if loaded is None:
            not_found_row_ids.append(row_id)
            continue

        decision = _parse_review_decision(record_dict)
        if decision is None:
            unchanged_row_ids.append(row_id)
            continue

        # Apply the review decision to the local row
        updated_row = _apply_review_decision(loaded.row, decision)
        write_row(loaded.path, updated_row)
        updated_row_ids.append(row_id)

    manifest_path = _sync_manifest_path(layout.root, slice_name, "pull")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_payload: dict[str, Any] = {
        "authority": "local",
        "dataset_id": dataset.id,
        "dataset_name": dataset_name,
        "not_found_row_ids": sorted(not_found_row_ids),
        "operation": "sync-pull",
        "pulled_count": len(updated_row_ids),
        "slice": slice_name,
        "unchanged_row_ids": sorted(unchanged_row_ids),
        "updated_row_ids": sorted(updated_row_ids),
    }
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return SyncPullResult(
        slice_name=slice_name,
        dataset_name=dataset_name,
        dataset_id=dataset.id,
        pulled_count=len(updated_row_ids),
        updated_row_ids=updated_row_ids,
        unchanged_row_ids=unchanged_row_ids,
        not_found_row_ids=not_found_row_ids,
        manifest_path=manifest_path,
    )


def simulate_review_on_braintrust(
    *,
    root: Path,
    slice_name: str,
    reviewer: str = "test-reviewer",
    edits: dict[str, dict[str, Any]] | None = None,
) -> int:
    """Simulate a human review on Braintrust for testing the round-trip.

    This updates the Braintrust records for flagged rows to reflect
    a human reviewer's decision, so the pull operation can sync them back.

    Args:
        root: Local corpus root.
        slice_name: Target slice.
        reviewer: Reviewer identifier.
        edits: Optional mapping of row_id to review edits. Each edit can
            override verdict_band, reasoning_quality, evidence_quality,
            calibration_quality, failure_tags, confidence.

    Returns:
        Number of records updated.
    """
    try:
        import braintrust
    except ImportError as error:
        raise BraintrustSyncError(
            "braintrust package is required for sync operations"
        ) from error

    dataset_name = f"{REVIEW_DATASET_PREFIX}{slice_name}"
    try:
        dataset = braintrust.init_dataset(project=BRAINTRUST_PROJECT, name=dataset_name)
    except Exception as error:
        raise BraintrustSyncError(
            f"Unable to open Braintrust dataset '{dataset_name}': {error}"
        ) from error

    records = list(dataset.fetch())
    edits = edits or {}
    updated = 0

    for record in records:
        # Braintrust DatasetEvent is dict-like but not typed as dict[str, Any]
        record_dict: dict[str, Any] = (
            record if isinstance(record, dict) else dict(record)  # type: ignore[assignment]
        )

        input_data = record_dict.get("input") or {}
        row_id: str = input_data.get("row_id", "")
        record_id = record_dict.get("id", "")
        if not row_id or not record_id:
            continue

        # Get current expected (AI suggestion)
        expected = dict(record_dict.get("expected") or {})
        metadata = dict(record_dict.get("metadata") or {})

        # Apply edits if provided for this row
        row_edits = edits.get(row_id, {})

        # Determine the reviewed decision
        if row_edits:
            expected.update(row_edits)
        else:
            # Default: accept the AI suggestion (no change to expected)
            pass

        # Mark as reviewed
        reviewed_at = datetime.now(UTC).isoformat()
        metadata["reviewer"] = reviewer
        metadata["reviewed_at"] = reviewed_at
        metadata["original_status"] = "manual_review"
        metadata["review_action"] = "edited" if row_edits else "accepted"

        # Update the Braintrust record
        dataset.update(
            id=str(record_id),
            expected=expected,
            metadata=metadata,
        )
        updated += 1

    dataset.flush()
    return updated


def sync_push_summary(result: SyncPushResult) -> dict[str, Any]:
    """Return a machine-readable CLI summary for a sync push."""
    return {
        "authority": "local",
        "dataset_id": result.dataset_id,
        "dataset_name": result.dataset_name,
        "manifest_path": str(result.manifest_path),
        "operation": "sync-push",
        "pushed_count": result.pushed_count,
        "pushed_row_ids": sorted(result.pushed_row_ids),
        "skipped_row_ids": sorted(result.skipped_row_ids),
        "slice": result.slice_name,
    }


def sync_pull_summary(result: SyncPullResult) -> dict[str, Any]:
    """Return a machine-readable CLI summary for a sync pull."""
    return {
        "authority": "local",
        "dataset_id": result.dataset_id,
        "dataset_name": result.dataset_name,
        "manifest_path": str(result.manifest_path),
        "not_found_row_ids": sorted(result.not_found_row_ids),
        "operation": "sync-pull",
        "pulled_count": result.pulled_count,
        "slice": result.slice_name,
        "unchanged_row_ids": sorted(result.unchanged_row_ids),
        "updated_row_ids": sorted(result.updated_row_ids),
    }
