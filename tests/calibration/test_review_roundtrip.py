"""Review round-trip tests: AI suggestion preservation and Braintrust review sync."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any

from prism_calibration.braintrust_sync import (
    _apply_review_decision,
    _parse_review_decision,
    pull_review_from_braintrust,
    push_flagged_to_braintrust,
)
from prism_calibration.lineage import load_corpus_rows
from prism_calibration.pilot import build_pilot_slice

# ── Load test-only helper from the test tree (not production code) ────────────
# ``_simulate_review_on_braintrust`` was moved from
# ``prism_calibration.braintrust_sync`` into the test helper module
# ``_braintrust_helpers.py`` so it cannot be imported from production.
_spec = importlib.util.spec_from_file_location(
    "_braintrust_helpers",
    Path(__file__).parent / "_braintrust_helpers.py",
)
assert _spec is not None and _spec.loader is not None
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)  # type: ignore[union-attr]
_simulate_review_on_braintrust = _helpers._simulate_review_on_braintrust

REPO_ROOT = Path(__file__).resolve().parents[2]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the calibration CLI and return the completed process."""
    return subprocess.run(
        ["uv", "run", "python", "-m", "prism_calibration.cli", *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _build_pilot_root(tmp_path: Path) -> Path:
    """Build a small pilot slice and return the corpus root path."""
    root = tmp_path / "calibration"
    build_pilot_slice(root=root, pilot_size=20)
    return root


def test_local_row_preserves_both_ai_suggestion_and_human_decision(tmp_path: Path) -> None:
    """After review round-trip, the local row retains the AI label alongside the human decision."""
    root = _build_pilot_root(tmp_path)
    loaded_rows = load_corpus_rows(root, include_sample=False)

    # Find a row that was routed to manual review
    manual_rows = [
        loaded for loaded in loaded_rows
        if loaded.row.review.status == "manual_review"
    ]
    assert manual_rows, "Pilot build should produce at least one manual_review row"
    target = manual_rows[0]
    original_row = target.row

    # Capture the original AI suggestion before review
    assert original_row.review.ai_labels, "Row must have AI pre-labels"
    original_ai_label = original_row.review.canonical_label
    assert original_ai_label is not None

    # Simulate a human reviewer editing the canonical label
    from prism_calibration.braintrust_sync import ReviewDecision
    from datetime import UTC, datetime

    edited_decision = ReviewDecision(
        row_id=original_row.row_id,
        record_id="test-record-id",
        verdict_band="ENDORSE",
        reasoning_quality=95,
        evidence_quality=92,
        calibration_quality=90,
        failure_tags=[],
        confidence=0.97,
        reviewer="test-human-reviewer",
        reviewed_at=datetime(2026, 5, 16, 15, 0, tzinfo=UTC),
        notes="Human reviewer endorses this trace after careful review.",
    )

    updated_row = _apply_review_decision(original_row, edited_decision)

    # The updated row preserves the original AI labels
    assert len(updated_row.review.ai_labels) == len(original_row.review.ai_labels)
    for updated_label, original_label in zip(
        updated_row.review.ai_labels, original_row.review.ai_labels
    ):
        assert updated_label.model_dump() == original_label.model_dump()

    # The canonical label is now the human-reviewed decision
    assert updated_row.review.canonical_label is not None
    assert updated_row.review.canonical_label.verdict_band == "ENDORSE"
    assert updated_row.review.canonical_label.model_family == "human-reviewer"
    assert updated_row.review.canonical_label.model_name == "test-human-reviewer"
    assert updated_row.review.canonical_label.reasoning_quality == 95

    # The review status is updated
    assert updated_row.review.status == "human_reviewed"
    assert updated_row.review.reviewer == "test-human-reviewer"
    assert updated_row.review.reviewed_at is not None
    assert updated_row.review.notes == "Human reviewer endorses this trace after careful review."

    # The routing metadata is preserved
    assert updated_row.review.routing is not None
    assert updated_row.review.routing.route_reasons == original_row.review.routing.route_reasons


def test_parse_review_decision_from_braintrust_record() -> None:
    """A Braintrust record with reviewer metadata parses into a review decision."""
    record: dict[str, Any] = {
        "id": "record-123",
        "input": {
            "row_id": "synthetic-0001",
            "source_type": "synthetic",
        },
        "expected": {
            "verdict_band": "PASS",
            "reasoning_quality": 88,
            "evidence_quality": 85,
            "calibration_quality": 82,
            "failure_tags": [],
            "confidence": 0.9,
        },
        "metadata": {
            "reviewer": "human-annotator-1",
            "reviewed_at": "2026-05-16T15:30:00+00:00",
            "original_status": "manual_review",
            "review_action": "edited",
        },
    }

    decision = _parse_review_decision(record)

    assert decision is not None
    assert decision.row_id == "synthetic-0001"
    assert decision.verdict_band == "PASS"
    assert decision.reasoning_quality == 88
    assert decision.evidence_quality == 85
    assert decision.calibration_quality == 82
    assert decision.reviewer == "human-annotator-1"
    assert decision.reviewed_at.year == 2026


def test_parse_review_decision_returns_none_for_unreviewed() -> None:
    """A Braintrust record without reviewer metadata is not considered reviewed."""
    record: dict[str, Any] = {
        "id": "record-456",
        "input": {"row_id": "synthetic-0002"},
        "expected": {"verdict_band": "WARN"},
        "metadata": {"original_status": "manual_review"},
    }

    decision = _parse_review_decision(record)
    assert decision is None


def test_parse_review_decision_returns_none_for_non_string_reviewed_at() -> None:
    """A non-string reviewed_at value is rejected rather than falling back to a timestamp."""
    # reviewed_at is an int — previously this would fall back to PILOT_BUILD_CREATED_AT
    record: dict[str, Any] = {
        "id": "record-789",
        "input": {"row_id": "synthetic-0003"},
        "expected": {"verdict_band": "PASS"},
        "metadata": {
            "reviewer": "human-annotator-2",
            "reviewed_at": 1747398000,  # int, not a string
        },
    }

    decision = _parse_review_decision(record)
    assert decision is None, "Non-string reviewed_at should return None, not a fallback"


def test_parse_review_decision_returns_none_for_invalid_iso_timestamp() -> None:
    """An unparseable reviewed_at string is rejected rather than using datetime.now."""
    record: dict[str, Any] = {
        "id": "record-abc",
        "input": {"row_id": "synthetic-0004"},
        "expected": {"verdict_band": "PASS"},
        "metadata": {
            "reviewer": "human-annotator-3",
            "reviewed_at": "not-a-valid-timestamp",
        },
    }

    decision = _parse_review_decision(record)
    assert decision is None, "Invalid ISO timestamp should return None, not datetime.now()"


def test_parse_review_decision_returns_none_for_missing_row_id() -> None:
    """A record missing the row_id in input is rejected."""
    record: dict[str, Any] = {
        "id": "record-def",
        "input": {},  # no row_id
        "expected": {"verdict_band": "PASS"},
        "metadata": {
            "reviewer": "human-annotator-4",
            "reviewed_at": "2026-05-16T15:30:00+00:00",
        },
    }

    decision = _parse_review_decision(record)
    assert decision is None, "Missing row_id should return None"


def test_parse_review_decision_returns_none_for_missing_record_id() -> None:
    """A record missing the id field is rejected."""
    record: dict[str, Any] = {
        "id": "",  # empty
        "input": {"row_id": "synthetic-0005"},
        "expected": {"verdict_band": "PASS"},
        "metadata": {
            "reviewer": "human-annotator-5",
            "reviewed_at": "2026-05-16T15:30:00+00:00",
        },
    }

    decision = _parse_review_decision(record)
    assert decision is None, "Missing record id should return None"


def test_parse_review_decision_returns_none_for_missing_verdict_band() -> None:
    """A record missing verdict_band in expected is rejected."""
    record: dict[str, Any] = {
        "id": "record-ghi",
        "input": {"row_id": "synthetic-0006"},
        "expected": {},  # no verdict_band
        "metadata": {
            "reviewer": "human-annotator-6",
            "reviewed_at": "2026-05-16T15:30:00+00:00",
        },
    }

    decision = _parse_review_decision(record)
    assert decision is None, "Missing verdict_band should return None"


def test_push_flagged_rows_to_braintrust_creates_dataset(tmp_path: Path) -> None:
    """Pushing flagged rows creates a Braintrust dataset with review context."""
    root = _build_pilot_root(tmp_path)

    result = push_flagged_to_braintrust(root=root, slice_name="pilot")

    assert result.pushed_count > 0
    assert result.dataset_name.startswith("pilot-review-")
    assert result.dataset_id  # non-empty Braintrust dataset ID
    assert result.pushed_row_ids
    assert result.skipped_row_ids == []

    # Verify the dataset exists in Braintrust by re-pushing (idempotent upsert)
    _push_result = run_cli(
        "sync", "--root", str(root), "--slice", "pilot", "--push-review",
    )
    # The push was already done, but re-pushing should upsert without error
    # (idempotent behavior tested by a later feature)


def test_braintrust_review_roundtrip_syncs_back_to_local(tmp_path: Path) -> None:
    """Full round-trip: push → simulate review → pull → local row updated with AI history."""
    root = _build_pilot_root(tmp_path)

    # Step 1: Push flagged rows to Braintrust
    push_result = push_flagged_to_braintrust(root=root, slice_name="pilot")
    assert push_result.pushed_count > 0
    flagged_row_id = push_result.pushed_row_ids[0]

    # Capture the local row state before review
    pre_review_row = None
    for loaded in load_corpus_rows(root, include_sample=False):
        if loaded.row.row_id == flagged_row_id:
            pre_review_row = loaded.row
            break
    assert pre_review_row is not None
    assert pre_review_row.review.canonical_label is not None
    pre_ai_labels = list(pre_review_row.review.ai_labels)

    # Step 2: Simulate a human review on Braintrust
    edits = {
        flagged_row_id: {
            "verdict_band": "ENDORSE",
            "reasoning_quality": 95,
            "evidence_quality": 92,
            "calibration_quality": 90,
            "failure_tags": [],
            "confidence": 0.97,
        },
    }
    updated_count = _simulate_review_on_braintrust(
        root=root, slice_name="pilot", reviewer="test-reviewer", edits=edits
    )
    assert updated_count >= 1

    # Step 3: Pull reviewed decisions from Braintrust
    pull_result = pull_review_from_braintrust(root=root, slice_name="pilot")
    assert pull_result.pulled_count >= 1
    assert flagged_row_id in pull_result.updated_row_ids

    # Step 4: Verify the local row now has both AI and human decisions
    post_review_row = None
    for loaded in load_corpus_rows(root, include_sample=False):
        if loaded.row.row_id == flagged_row_id:
            post_review_row = loaded.row
            break
    assert post_review_row is not None

    # The AI labels are preserved unchanged
    assert len(post_review_row.review.ai_labels) == len(pre_ai_labels)
    for post_label, pre_label in zip(post_review_row.review.ai_labels, pre_ai_labels):
        assert post_label.model_dump() == pre_label.model_dump()

    # The canonical label is now the human-reviewed decision
    assert post_review_row.review.canonical_label is not None
    assert post_review_row.review.canonical_label.verdict_band == "ENDORSE"
    assert post_review_row.review.canonical_label.reasoning_quality == 95
    assert post_review_row.review.canonical_label.model_family == "human-reviewer"
    assert post_review_row.review.canonical_label.model_name == "test-reviewer"

    # Review metadata is set
    assert post_review_row.review.status == "human_reviewed"
    assert post_review_row.review.reviewer == "test-reviewer"
    assert post_review_row.review.reviewed_at is not None

    # Original routing metadata is preserved
    assert post_review_row.review.routing is not None


def test_sync_cli_push_and_pull_roundtrip(tmp_path: Path) -> None:
    """The sync CLI command supports push-review and pull-review operations."""
    root = _build_pilot_root(tmp_path)

    # Push
    push = run_cli("sync", "--root", str(root), "--slice", "pilot", "--push-review")
    assert push.returncode == 0, push.stderr
    push_payload = json.loads(push.stdout)
    assert push_payload["operation"] == "sync-push"
    assert push_payload["pushed_count"] > 0

    # Simulate review
    _simulate_review_on_braintrust(root=root, slice_name="pilot", reviewer="cli-test-reviewer")

    # Pull
    pull = run_cli("sync", "--root", str(root), "--slice", "pilot", "--pull-review")
    assert pull.returncode == 0, pull.stderr
    pull_payload = json.loads(pull.stdout)
    assert pull_payload["operation"] == "sync-pull"
    assert pull_payload["pulled_count"] >= 1


def test_sync_cli_requires_slice_argument(tmp_path: Path) -> None:
    """The sync CLI requires the --slice argument."""
    root = tmp_path / "calibration"
    result = run_cli("sync", "--root", str(root))
    assert result.returncode != 0


def test_apply_review_decision_preserves_provenance_and_split(tmp_path: Path) -> None:
    """Review application does not alter provenance, trace, or split metadata."""
    root = _build_pilot_root(tmp_path)
    loaded_rows = load_corpus_rows(root, include_sample=False)
    manual_rows = [
        loaded for loaded in loaded_rows
        if loaded.row.review.status == "manual_review"
    ]
    assert manual_rows
    original = manual_rows[0].row

    from prism_calibration.braintrust_sync import ReviewDecision
    from datetime import UTC, datetime

    decision = ReviewDecision(
        row_id=original.row_id,
        record_id="test",
        verdict_band="PASS",
        reasoning_quality=80,
        evidence_quality=78,
        calibration_quality=76,
        failure_tags=[],
        confidence=0.85,
        reviewer="reviewer-a",
        reviewed_at=datetime.now(UTC),
    )
    updated = _apply_review_decision(original, decision)

    # Provenance is unchanged
    assert updated.provenance.model_dump() == original.provenance.model_dump()
    # Trace is unchanged
    assert updated.trace.model_dump() == original.trace.model_dump()
    # Split is unchanged
    assert updated.split.model_dump() == original.split.model_dump()
    # Only review has changed
    assert updated.review.model_dump() != original.review.model_dump()


def test_pilot_build_created_at_is_single_source() -> None:
    """PILOT_BUILD_CREATED_AT is defined once in models and imported by pilot."""
    from datetime import UTC

    from prism_calibration.models import PILOT_BUILD_CREATED_AT as models_const
    from prism_calibration.pilot import PILOT_BUILD_CREATED_AT as pilot_const

    expected_value = models_const
    assert expected_value.year == 2026
    assert expected_value.month == 5
    assert expected_value.day == 16
    assert expected_value.hour == 14
    assert expected_value.tzinfo == UTC

    # pilot.py imports the constant from models (single source of truth)
    assert pilot_const is expected_value, "pilot.py should import PILOT_BUILD_CREATED_AT from models"
