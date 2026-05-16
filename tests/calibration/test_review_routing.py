"""Review-routing policy tests for AI pre-label decisions."""

from __future__ import annotations

from pathlib import Path

from prism_calibration.labeling import generate_synthetic_rows
from prism_calibration.prelabel import apply_prelabels_to_row, normalize_prelabel_output
from prism_calibration.validation import load_row


def _one_pilot_row(root: Path):
    """Generate and load one synthetic row coerced to the pilot split for routing tests."""
    result = generate_synthetic_rows(root=root, count=1)
    row = load_row(root / "rows" / f"{result.rows[0].row_id}.json")
    split = row.split.model_copy(update={"name": "pilot"})
    return row.model_copy(update={"split": split})


def test_low_confidence_and_disagreement_route_to_manual_review(tmp_path: Path) -> None:
    """Low confidence and conflicting verdict bands produce explicit route reasons."""
    row = _one_pilot_row(tmp_path / "calibration")
    low_confidence = normalize_prelabel_output(
        {
            "reasoning_quality": 42,
            "evidence_quality": 38,
            "calibration_quality": 44,
            "verdict_band": "WARN",
            "failure_tags": ["weak-evidence"],
            "confidence": 0.41,
        },
        model_name="judge-a",
        model_family="openai-gpt",
    )
    disagreeing = normalize_prelabel_output(
        {
            "reasoning_quality": 31,
            "evidence_quality": 34,
            "calibration_quality": 29,
            "verdict_band": "REJECT",
            "failure_tags": ["weak-evidence", "missing-counterevidence"],
            "confidence": 0.82,
        },
        model_name="judge-b",
        model_family="openai-gpt",
    )

    routed = apply_prelabels_to_row(row, (low_confidence, disagreeing))

    assert routed.review.status == "manual_review"
    assert routed.review.routing is not None
    assert routed.review.routing.destination == "manual_review"
    assert set(routed.review.routing.route_reasons) == {
        "label_disagreement",
        "low_confidence",
    }
    assert routed.review.canonical_label is not None
    assert routed.review.canonical_label.verdict_band == "WARN"
    assert routed.review.failure_tags == [
        "missing-counterevidence",
        "weak-evidence",
    ]


def test_high_confidence_consensus_auto_resolves_without_manual_queue(
    tmp_path: Path,
) -> None:
    """High-confidence agreeing labels can resolve without entering manual review."""
    row = _one_pilot_row(tmp_path / "calibration")
    first = normalize_prelabel_output(
        {
            "reasoning_quality": 91,
            "evidence_quality": 88,
            "calibration_quality": 86,
            "verdict_band": "PASS",
            "failure_tags": [],
            "confidence": 0.94,
        },
        model_name="judge-a",
        model_family="openai-gpt",
    )
    second = normalize_prelabel_output(
        {
            "reasoning_quality": 89,
            "evidence_quality": 90,
            "calibration_quality": 87,
            "verdict_band": "PASS",
            "failure_tags": [],
            "confidence": 0.91,
        },
        model_name="judge-b",
        model_family="openai-gpt",
    )

    routed = apply_prelabels_to_row(row, (first, second))

    assert routed.review.status == "ai_resolved"
    assert routed.review.routing is not None
    assert routed.review.routing.destination == "auto_resolved"
    assert routed.review.routing.route_reasons == ["high_confidence_consensus"]
    assert routed.review.canonical_label is not None
    assert routed.review.canonical_label.confidence == 0.91
    assert routed.review.failure_tags == []
