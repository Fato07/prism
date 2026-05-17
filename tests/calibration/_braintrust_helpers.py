"""Private Braintrust review simulation helper for test round-trips.

This module lives in the test tree, NOT in the production calibration package.
The ``_simulate_review_on_braintrust`` function was moved here from
``prism_calibration.braintrust_sync`` because it is a test-only utility
that should never be called from production code.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prism_calibration.braintrust_sync import (
    BraintrustSyncError,
    REVIEW_DATASET_PREFIX,
    braintrust_project,
)


def _simulate_review_on_braintrust(
    *,
    root: Path,
    slice_name: str,
    reviewer: str = "test-reviewer",
    edits: dict[str, dict[str, Any]] | None = None,
) -> int:
    """Simulate a human review on Braintrust for testing the round-trip.

    This is a **test helper** — it does not belong in production code.
    It updates the Braintrust records for flagged rows to reflect a human
    reviewer's decision, so the pull operation can sync them back.

    Args:
        root: Local corpus root (unused but kept for API compatibility).
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
        dataset = braintrust.init_dataset(project=braintrust_project(), name=dataset_name)
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
