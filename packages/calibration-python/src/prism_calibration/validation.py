"""Validation helpers for local calibration corpus artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from prism_calibration.models import CalibrationRow


class RowLoadError(ValueError):
    """Raised when a row file cannot be loaded as JSON."""


def load_row(path: Path) -> CalibrationRow:
    """Load and validate one calibration row JSON file."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        raise RowLoadError(f"{path}: unable to read row file: {error}") from error

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        message = f"{path}: invalid JSON at line {error.lineno}, column {error.colno}"
        raise RowLoadError(message) from error

    return CalibrationRow.model_validate(payload)


def format_validation_errors(error: ValidationError) -> list[str]:
    """Format Pydantic errors as stable field-level CLI messages."""
    messages: list[str] = []
    for detail in error.errors():
        location = cast(tuple[str | int, ...], detail.get("loc", ()))
        field = ".".join(str(part) for part in location) if location else "<row>"
        message = str(detail.get("msg", "Invalid value"))
        messages.append(f"{field}: {message}")
    return messages


def row_summary(row: CalibrationRow) -> dict[str, Any]:
    """Return a compact, machine-readable row summary."""
    payload: dict[str, Any] = {
        "lineage_id": row.provenance.lineage_id,
        "parent_row_id": row.provenance.parent_row_id,
        "review_status": row.review.status,
        "row_id": row.row_id,
        "source_type": row.provenance.source_type,
        "split": row.split.name,
        "trace_id": row.trace.trace_id,
    }
    if row.review.canonical_label is not None:
        payload["canonical_label"] = row.review.canonical_label.model_dump(mode="json")
    if row.review.routing is not None:
        payload["routing"] = row.review.routing.model_dump(mode="json")
    if row.review.ai_labels:
        payload["ai_label_count"] = len(row.review.ai_labels)
    return payload
