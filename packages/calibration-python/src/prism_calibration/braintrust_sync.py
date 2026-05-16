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
SLICE_DATASET_PREFIX = "pilot-slice-"
SYNC_MANIFEST_PREFIX = "sync-"
BRAINTRUST_REF_FILENAME = "braintrust-ref.json"

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


@dataclass(frozen=True)
class SyncSliceResult:
    """Summary of a full-slice sync to Braintrust."""

    slice_name: str
    dataset_name: str
    dataset_id: str
    row_count: int
    synced_row_ids: list[str]
    skipped_row_ids: list[str]
    export_id: str
    export_dir: Path
    manifest_path: Path
    resumed: bool


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


def _sync_state_path(root: Path, slice_name: str) -> Path:
    """Return path for durable sync state file used for resume capability."""
    return root / "state" / f"sync-slice-{slice_name}.json"


def _read_sync_state(root: Path, slice_name: str) -> dict[str, Any] | None:
    """Read durable sync state if it exists."""
    path = _sync_state_path(root, slice_name)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
    except (json.JSONDecodeError, OSError):
        return None


def _write_sync_state(root: Path, slice_name: str, state: dict[str, Any]) -> None:
    """Write durable sync state for resume capability."""
    path = _sync_state_path(root, slice_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _clear_sync_state(root: Path, slice_name: str) -> None:
    """Clear sync state after successful completion."""
    path = _sync_state_path(root, slice_name)
    if path.exists():
        path.unlink()


def _braintrust_ref_path(export_dir: Path) -> Path:
    """Return the Braintrust reference sidecar path for a frozen export."""
    return export_dir / BRAINTRUST_REF_FILENAME


def _write_braintrust_ref(
    export_dir: Path,
    *,
    dataset_id: str,
    dataset_name: str,
    export_id: str,
    last_synced_at: datetime | None = None,
) -> None:
    """Write a Braintrust reference sidecar alongside the frozen manifest.

    This preserves the link from local export to Braintrust dataset
    without modifying the immutable frozen manifest itself.
    """
    ref_path = _braintrust_ref_path(export_dir)
    payload: dict[str, Any] = {
        "dataset_id": dataset_id,
        "dataset_name": dataset_name,
        "export_id": export_id,
        "last_synced_at": (last_synced_at or datetime.now(UTC)).isoformat(),
    }
    ref_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def read_braintrust_ref(export_dir: Path) -> dict[str, Any] | None:
    """Read the Braintrust reference sidecar for a frozen export.

    Returns None if no sidecar exists (the slice has not been synced yet).
    """
    ref_path = _braintrust_ref_path(export_dir)
    if not ref_path.exists():
        return None
    try:
        return json.loads(ref_path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
    except (json.JSONDecodeError, OSError):
        return None


def _find_frozen_export(root: Path, slice_name: str) -> tuple[Path, Path] | None:
    """Find the latest frozen export for a slice.

    Returns (export_dir, manifest_path) or None if no export exists.
    """
    frozen_dir = root / "frozen" / slice_name
    if not frozen_dir.is_dir():
        return None

    export_dirs = sorted(
        (d for d in frozen_dir.iterdir() if d.is_dir()),
        key=lambda d: d.name,
    )
    if not export_dirs:
        return None

    latest = export_dirs[-1]
    manifest = latest / "manifest.json"
    if not manifest.exists():
        return None

    return latest, manifest


def sync_slice_to_braintrust(
    *,
    root: Path,
    slice_name: str,
) -> SyncSliceResult:
    """Sync a frozen local slice to a Braintrust dataset with stable case IDs.

    Creates or refreshes exactly one Braintrust dataset per slice. Uses the
    frozen local export as the authoritative source. Rows are upserted by
    stable row_id so re-syncs produce no duplicates. Durable state tracking
    enables safe resume after interruption.
    """
    try:
        import braintrust
    except ImportError as error:
        raise BraintrustSyncError(
            "braintrust package is required for sync operations"
        ) from error

    layout = bootstrap_corpus_root(root)

    # Ensure a frozen export exists with rows
    from prism_calibration.freeze import _load_manifest, freeze_slice
    from prism_calibration.models import SplitName

    slice_typed: SplitName = slice_name  # type: ignore[assignment]

    found = _find_frozen_export(layout.root, slice_name)
    if found is not None:
        export_dir, manifest_path = found
        frozen_manifest = _load_manifest(manifest_path)

        # If frozen export has 0 rows, re-freeze from live corpus
        if frozen_manifest.row_count == 0:
            export = freeze_slice(layout.root, slice_typed)
            export_dir = export.export_dir
            manifest_path = export.manifest_path
            frozen_manifest = export.manifest
    else:
        # No frozen export exists — create one
        export = freeze_slice(layout.root, slice_typed)
        export_dir = export.export_dir
        manifest_path = export.manifest_path
        frozen_manifest = export.manifest

    # Check for resume state
    resume_state = _read_sync_state(layout.root, slice_name)
    already_synced_ids: set[str] = set()
    dataset_name_from_state: str | None = None
    resumed = False

    if resume_state is not None:
        already_synced_ids = set(resume_state.get("synced_row_ids", []))
        dataset_name_from_state = resume_state.get("dataset_name")
        resumed = True

    # Create or open the Braintrust dataset
    dataset_name = dataset_name_from_state or f"{SLICE_DATASET_PREFIX}{slice_name}"
    dataset = braintrust.init_dataset(project=BRAINTRUST_PROJECT, name=dataset_name)
    dataset_id = dataset.id

    # Sync rows from frozen export
    synced_row_ids: list[str] = []
    skipped_row_ids: list[str] = []

    for row_entry in frozen_manifest.rows:
        row_id = row_entry.row_id

        # Skip already-synced rows (resume path)
        if row_id in already_synced_ids:
            synced_row_ids.append(row_id)
            continue

        # Load the row from frozen export
        row_path = export_dir / row_entry.path
        if not row_path.exists():
            skipped_row_ids.append(row_id)
            continue

        row = _load_row_from_frozen(row_path)

        # Build Braintrust record with full row context
        record_input = _slice_record_input(row)
        record_metadata = _slice_record_metadata(
            row, row_entry.row_hash, frozen_manifest.export_id
        )

        # Upsert by stable row_id
        tags = sorted({slice_name, row.provenance.source_type, row.split.name})
        dataset.insert(
            id=row_id,
            input=record_input,
            metadata=record_metadata,
            tags=tags,
        )
        synced_row_ids.append(row_id)

        # Write durable state after each row for resume capability
        _write_sync_state(layout.root, slice_name, {
            "dataset_id": dataset_id,
            "dataset_name": dataset_name,
            "export_id": frozen_manifest.export_id,
            "slice": slice_name,
            "synced_row_ids": sorted(synced_row_ids),
            "skipped_row_ids": sorted(skipped_row_ids),
            "total_rows": frozen_manifest.row_count,
        })

    dataset.flush()

    # Write Braintrust reference sidecar alongside frozen manifest
    _write_braintrust_ref(
        export_dir,
        dataset_id=dataset_id,
        dataset_name=dataset_name,
        export_id=frozen_manifest.export_id,
    )

    # Clear sync state on successful completion
    _clear_sync_state(layout.root, slice_name)

    # Write sync manifest
    sync_manifest_path = _sync_manifest_path(layout.root, slice_name, "slice-sync")
    sync_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    sync_manifest: dict[str, Any] = {
        "authority": "local",
        "dataset_id": dataset_id,
        "dataset_name": dataset_name,
        "export_id": frozen_manifest.export_id,
        "operation": "sync-slice",
        "resumed": resumed,
        "row_count": len(synced_row_ids),
        "skipped_row_ids": sorted(skipped_row_ids),
        "slice": slice_name,
        "synced_row_ids": sorted(synced_row_ids),
    }
    sync_manifest_path.write_text(
        json.dumps(sync_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return SyncSliceResult(
        slice_name=slice_name,
        dataset_name=dataset_name,
        dataset_id=dataset_id,
        row_count=len(synced_row_ids),
        synced_row_ids=sorted(synced_row_ids),
        skipped_row_ids=sorted(skipped_row_ids),
        export_id=frozen_manifest.export_id,
        export_dir=export_dir,
        manifest_path=manifest_path,
        resumed=resumed,
    )


def _load_row_from_frozen(row_path: Path) -> CalibrationRow:
    """Load one row from a frozen export path."""
    raw = row_path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    return CalibrationRow.model_validate(payload)


def _slice_record_input(row: CalibrationRow) -> dict[str, Any]:
    """Build the Braintrust record input payload for a full-slice sync."""
    record: dict[str, Any] = {
        "row_id": row.row_id,
        "trace_id": row.trace.trace_id,
        "lineage_id": row.provenance.lineage_id,
        "source_type": row.provenance.source_type,
        "split": row.split.name,
        "market_question": row.trace.market_question,
        "action": row.trace.action,
        "final_probability": row.trace.final_probability,
        "verdict_band": (
            row.review.canonical_label.verdict_band
            if row.review.canonical_label
            else None
        ),
        "confidence": (
            row.review.canonical_label.confidence
            if row.review.canonical_label
            else None
        ),
        "failure_tags": row.review.failure_tags,
        "review_status": row.review.status,
    }

    if row.provenance.source_type == "mutated":
        record["parent_row_id"] = row.provenance.parent_row_id
        record["mutation_type"] = row.provenance.mutation_type

    return record


def _slice_record_metadata(
    row: CalibrationRow,
    row_hash: str,
    export_id: str,
) -> dict[str, Any]:
    """Build the Braintrust record metadata for a full-slice sync."""
    metadata: dict[str, Any] = {
        "content_hash": row.provenance.content_hash,
        "source_ref": row.provenance.source_ref,
        "run_id": row.provenance.run_id,
        "export_id": export_id,
        "slice_hash": export_id,
        "row_hash": row_hash,
    }
    return metadata


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


def sync_slice_summary(result: SyncSliceResult) -> dict[str, Any]:
    """Return a machine-readable CLI summary for a full-slice sync."""
    return {
        "authority": "local",
        "dataset_id": result.dataset_id,
        "dataset_name": result.dataset_name,
        "export_dir": str(result.export_dir),
        "export_id": result.export_id,
        "operation": "sync-slice",
        "resumed": result.resumed,
        "row_count": result.row_count,
        "skipped_row_ids": sorted(result.skipped_row_ids),
        "slice": result.slice_name,
        "synced_row_ids": sorted(result.synced_row_ids),
    }
