"""Review queue context tests: VAL-BT-005 and VAL-BT-006.

VAL-BT-005: Flagged cases appear in the Braintrust review queue with stable IDs
    rather than being buried only in raw dataset rows.

VAL-BT-006: Opening a review item shows balanced context for human review:
    source type, lineage, AI label, confidence, route reason, and holdout status
    before a reviewer finalizes a decision.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from prism_calibration.braintrust_sync import (
    _review_context,
    _review_metadata,
    publish_review,
    publish_review_summary,
    push_flagged_to_braintrust,
)
from prism_calibration.lineage import load_corpus_rows
from prism_calibration.pilot import build_pilot_slice

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


# ---------------------------------------------------------------------------
# VAL-BT-005: Flagged cases appear in the review queue with stable IDs
# ---------------------------------------------------------------------------


def test_flagged_cases_appear_in_review_queue(tmp_path: Path) -> None:
    """Low-confidence and disagreement cases are pushed to the review dataset."""
    root = _build_pilot_root(tmp_path)
    loaded_rows = load_corpus_rows(root, include_sample=False)

    # Identify manual_review rows from the pilot build
    manual_rows = [
        loaded for loaded in loaded_rows
        if loaded.row.review.status == "manual_review"
    ]
    assert manual_rows, "Pilot build should produce flagged manual_review rows"

    # Push flagged rows to Braintrust review
    result = push_flagged_to_braintrust(root=root, slice_name="pilot")

    # All manual_review rows appear in the pushed result
    assert result.pushed_count > 0
    expected_ids = sorted(loaded.row.row_id for loaded in manual_rows
                         if loaded.row.review.canonical_label is not None)
    assert result.pushed_row_ids == expected_ids


def test_review_queue_uses_stable_row_ids(tmp_path: Path) -> None:
    """Pushed review rows use row_id as the stable Braintrust record ID."""
    root = _build_pilot_root(tmp_path)
    result = push_flagged_to_braintrust(root=root, slice_name="pilot")

    # Each pushed row ID is a non-empty stable identifier
    assert result.pushed_row_ids
    for row_id in result.pushed_row_ids:
        assert len(row_id) > 0


def test_review_queue_is_separate_from_raw_dataset(tmp_path: Path) -> None:
    """The review dataset name is distinct from the full-slice dataset name."""
    root = _build_pilot_root(tmp_path)
    result = push_flagged_to_braintrust(root=root, slice_name="pilot")

    # Review dataset uses 'pilot-review-' prefix, not 'pilot-slice-'
    assert result.dataset_name.startswith("pilot-review-")
    assert "pilot-slice-" not in result.dataset_name


# ---------------------------------------------------------------------------
# VAL-BT-006: Review rows show balanced context
# ---------------------------------------------------------------------------


def test_review_context_contains_source_type(tmp_path: Path) -> None:
    """Review context surfaces the source_type field for every flagged row."""
    root = _build_pilot_root(tmp_path)
    loaded_rows = load_corpus_rows(root, include_sample=False)
    manual_rows = [
        loaded for loaded in loaded_rows
        if loaded.row.review.status == "manual_review"
        and loaded.row.review.canonical_label is not None
    ]
    assert manual_rows

    for loaded in manual_rows:
        context = _review_context(loaded.row)
        assert "source_type" in context
        assert context["source_type"] in ("synthetic", "mutated", "real")


def test_review_context_contains_lineage(tmp_path: Path) -> None:
    """Review context surfaces a structured lineage dict with lineage_id."""
    root = _build_pilot_root(tmp_path)
    loaded_rows = load_corpus_rows(root, include_sample=False)
    manual_rows = [
        loaded for loaded in loaded_rows
        if loaded.row.review.status == "manual_review"
        and loaded.row.review.canonical_label is not None
    ]
    assert manual_rows

    for loaded in manual_rows:
        context = _review_context(loaded.row)
        assert "lineage" in context
        lineage = context["lineage"]
        assert isinstance(lineage, dict)
        assert "lineage_id" in lineage
        assert len(lineage["lineage_id"]) > 0

        # Mutated rows include parent_row_id and mutation_type
        if loaded.row.provenance.source_type == "mutated":
            assert "parent_row_id" in lineage
            assert "mutation_type" in lineage


def test_review_context_contains_ai_label(tmp_path: Path) -> None:
    """Review context surfaces the AI label with full rubric breakdown."""
    root = _build_pilot_root(tmp_path)
    loaded_rows = load_corpus_rows(root, include_sample=False)
    manual_rows = [
        loaded for loaded in loaded_rows
        if loaded.row.review.status == "manual_review"
        and loaded.row.review.canonical_label is not None
    ]
    assert manual_rows

    for loaded in manual_rows:
        context = _review_context(loaded.row)
        assert "ai_label" in context
        ai_label = context["ai_label"]
        assert isinstance(ai_label, dict)
        # Required rubric fields
        assert "verdict_band" in ai_label
        assert "reasoning_quality" in ai_label
        assert "evidence_quality" in ai_label
        assert "calibration_quality" in ai_label
        assert "failure_tags" in ai_label
        assert "confidence" in ai_label


def test_review_context_contains_confidence_at_top_level(tmp_path: Path) -> None:
    """Review context surfaces confidence as a top-level field (VAL-BT-006)."""
    root = _build_pilot_root(tmp_path)
    loaded_rows = load_corpus_rows(root, include_sample=False)
    manual_rows = [
        loaded for loaded in loaded_rows
        if loaded.row.review.status == "manual_review"
        and loaded.row.review.canonical_label is not None
    ]
    assert manual_rows

    for loaded in manual_rows:
        context = _review_context(loaded.row)
        assert "confidence" in context
        assert isinstance(context["confidence"], float)
        assert 0.0 <= context["confidence"] <= 1.0

        # Top-level confidence must match the AI label confidence
        if context["ai_label"] is not None:
            assert context["confidence"] == context["ai_label"]["confidence"]


def test_review_context_contains_route_reasons(tmp_path: Path) -> None:
    """Review context surfaces the route_reasons field for every flagged row."""
    root = _build_pilot_root(tmp_path)
    loaded_rows = load_corpus_rows(root, include_sample=False)
    manual_rows = [
        loaded for loaded in loaded_rows
        if loaded.row.review.status == "manual_review"
        and loaded.row.review.canonical_label is not None
    ]
    assert manual_rows

    for loaded in manual_rows:
        context = _review_context(loaded.row)
        assert "route_reasons" in context
        assert isinstance(context["route_reasons"], list)
        # Manual review rows must have at least one route reason
        assert len(context["route_reasons"]) > 0


def test_review_context_contains_holdout_status(tmp_path: Path) -> None:
    """Review context surfaces holdout_status as a boolean field."""
    root = _build_pilot_root(tmp_path)
    loaded_rows = load_corpus_rows(root, include_sample=False)
    manual_rows = [
        loaded for loaded in loaded_rows
        if loaded.row.review.status == "manual_review"
        and loaded.row.review.canonical_label is not None
    ]
    assert manual_rows

    for loaded in manual_rows:
        context = _review_context(loaded.row)
        assert "holdout_status" in context
        assert isinstance(context["holdout_status"], bool)
        # Pilot split rows are not holdout
        if loaded.row.split.name == "holdout":
            assert context["holdout_status"] is True
        else:
            assert context["holdout_status"] is False


def test_review_context_all_six_val_bt_006_fields_present(tmp_path: Path) -> None:
    """All six VAL-BT-006 context fields appear in the review context."""
    required_fields = [
        "source_type",
        "lineage",
        "ai_label",
        "confidence",
        "route_reasons",
        "holdout_status",
    ]
    root = _build_pilot_root(tmp_path)
    loaded_rows = load_corpus_rows(root, include_sample=False)
    manual_rows = [
        loaded for loaded in loaded_rows
        if loaded.row.review.status == "manual_review"
        and loaded.row.review.canonical_label is not None
    ]
    assert manual_rows

    for loaded in manual_rows:
        context = _review_context(loaded.row)
        for field in required_fields:
            assert field in context, f"Missing VAL-BT-006 field: {field}"


# ---------------------------------------------------------------------------
# VAL-BT-008 parity: CLI and Braintrust metadata agree
# ---------------------------------------------------------------------------


def test_review_metadata_matches_context_fields(tmp_path: Path) -> None:
    """Review metadata carries the same context fields as the input payload."""
    root = _build_pilot_root(tmp_path)
    loaded_rows = load_corpus_rows(root, include_sample=False)
    manual_rows = [
        loaded for loaded in loaded_rows
        if loaded.row.review.status == "manual_review"
        and loaded.row.review.canonical_label is not None
    ]
    assert manual_rows

    for loaded in manual_rows:
        context = _review_context(loaded.row)
        metadata = _review_metadata(loaded.row)

        # Metadata must agree with context on core fields
        assert metadata["source_type"] == context["source_type"]
        assert metadata["confidence"] == context["confidence"]
        assert metadata["route_reasons"] == context["route_reasons"]
        assert metadata["holdout_status"] == context["holdout_status"]


# ---------------------------------------------------------------------------
# CLI: --publish-review flag
# ---------------------------------------------------------------------------


def test_publish_review_cli_flag(tmp_path: Path) -> None:
    """The --publish-review flag pushes flagged rows to the review queue."""
    root = _build_pilot_root(tmp_path)

    result = run_cli("sync", "--root", str(root), "--slice", "pilot", "--publish-review")
    assert result.returncode == 0, result.stderr

    payload = json.loads(result.stdout)
    assert payload["operation"] == "publish-review"
    assert payload["pushed_count"] > 0
    assert payload["dataset_name"].startswith("pilot-review-")
    assert payload["pushed_row_ids"]


def test_publish_review_freezes_if_needed(tmp_path: Path) -> None:
    """publish_review freezes the slice if no frozen export exists."""
    root = _build_pilot_root(tmp_path)

    result = publish_review(root=root, slice_name="pilot")
    assert result.pushed_count > 0
    # First publish should have performed a freeze
    assert result.freeze_skipped is False
    assert result.export_id is not None


def test_publish_review_skips_freeze_when_frozen_exists(tmp_path: Path) -> None:
    """publish_review skips freezing when a frozen export already exists."""
    root = _build_pilot_root(tmp_path)

    from prism_calibration.freeze import freeze_slice

    # Pre-freeze the slice
    freeze_slice(root, "pilot")

    # Now publish — should skip the freeze step
    result = publish_review(root=root, slice_name="pilot")
    assert result.pushed_count > 0
    assert result.freeze_skipped is True


def test_publish_review_summary_is_machine_readable(tmp_path: Path) -> None:
    """publish_review_summary returns a well-formed JSON-serializable dict."""
    root = _build_pilot_root(tmp_path)
    result = publish_review(root=root, slice_name="pilot")

    summary = publish_review_summary(result)
    # Must be JSON-serializable
    serialized = json.dumps(summary, sort_keys=True)
    assert serialized

    parsed = json.loads(serialized)
    assert parsed["operation"] == "publish-review"
    assert parsed["pushed_count"] > 0
    assert parsed["slice"] == "pilot"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_review_context_for_row_without_canonical_label(tmp_path: Path) -> None:
    """Review context handles rows with no canonical label gracefully."""
    root = _build_pilot_root(tmp_path)
    loaded_rows = load_corpus_rows(root, include_sample=False)

    # Find a row and strip its canonical label
    target = loaded_rows[0]
    row = target.row.model_copy(update={
        "review": target.row.review.model_copy(update={"canonical_label": None}),
    })

    context = _review_context(row)
    assert context["ai_label"] is None
    assert context["confidence"] == 0.0
    # Other fields still present
    assert "source_type" in context
    assert "lineage" in context
    assert "route_reasons" in context
    assert "holdout_status" in context


def test_review_context_for_mutated_row_includes_parent(tmp_path: Path) -> None:
    """Mutated rows include parent_row_id and mutation_type in lineage."""
    root = _build_pilot_root(tmp_path)
    loaded_rows = load_corpus_rows(root, include_sample=False)

    # Find a mutated row
    mutated_rows = [
        loaded for loaded in loaded_rows
        if loaded.row.provenance.source_type == "mutated"
    ]
    if not mutated_rows:
        # Pilot build may not always produce mutated manual_review rows;
        # synthesize one by patching a row's provenance
        target = loaded_rows[0]
        row = target.row.model_copy(update={
            "provenance": target.row.provenance.model_copy(update={
                "source_type": "mutated",
                "parent_row_id": "parent-0001",
                "mutation_type": "calibration-overconfidence",
            }),
        })
    else:
        row = mutated_rows[0].row

    context = _review_context(row)
    assert context["source_type"] == "mutated"
    assert "parent_row_id" in context["lineage"]
    assert "mutation_type" in context["lineage"]
