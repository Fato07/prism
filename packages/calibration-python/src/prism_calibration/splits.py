"""Deterministic split assignment for local calibration corpus rows."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from prism_calibration.lineage import (
    LoadedRow,
    load_corpus_rows,
    validate_lineage_leaks,
    validate_orphaned_mutations,
)
from prism_calibration.models import CalibrationRow, SplitMetadata, SplitName

SPLIT_POLICY = "lineage-hash-v1"
SPLIT_ORDER: tuple[SplitName, ...] = ("pilot", "dev", "holdout", "canary")
ASSIGNED_AT = datetime(1970, 1, 1, tzinfo=UTC)


def split_for_lineage(lineage_id: str, *, seed: int) -> SplitName:
    """Return a deterministic split for a lineage group and seed."""
    digest = hashlib.sha256(f"{seed}:{lineage_id}".encode()).hexdigest()
    bucket = int(digest[:8], 16) % 100
    if bucket < 50:
        return "pilot"
    if bucket < 75:
        return "dev"
    if bucket < 90:
        return "holdout"
    return "canary"


def deterministic_row_json(row: CalibrationRow) -> str:
    """Serialize one row with stable key ordering for reproducible builds."""
    return json.dumps(row.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def write_row(path: Path, row: CalibrationRow) -> None:
    """Write one row payload deterministically."""
    path.write_text(deterministic_row_json(row), encoding="utf-8")


def group_rows_by_lineage(rows: tuple[LoadedRow, ...]) -> dict[str, list[LoadedRow]]:
    """Group rows by lineage ID with deterministic row ordering."""
    grouped: dict[str, list[LoadedRow]] = {}
    for loaded in rows:
        grouped.setdefault(loaded.row.provenance.lineage_id, []).append(loaded)
    for lineage_rows in grouped.values():
        lineage_rows.sort(key=lambda loaded: loaded.row.row_id)
    return dict(sorted(grouped.items()))


def _updated_row(row: CalibrationRow, *, split_name: SplitName, seed: int) -> CalibrationRow:
    """Return a row copy with deterministic split metadata."""
    split = SplitMetadata(
        name=split_name,
        policy=SPLIT_POLICY,
        seed=seed,
        assigned_at=ASSIGNED_AT,
    )
    return row.model_copy(update={"split": split})


def split_manifest_path(root: Path, seed: int) -> Path:
    """Return the deterministic manifest path for one split seed."""
    return root / "manifests" / f"splits-seed-{seed}.json"


def _empty_split_payload() -> dict[str, dict[str, Any]]:
    """Return an empty split payload preserving public split order."""
    return {split: {"count": 0, "row_ids": []} for split in SPLIT_ORDER}


def build_split_manifest(
    *,
    root: Path,
    seed: int,
    updated_rows: tuple[LoadedRow, ...],
) -> dict[str, Any]:
    """Build a machine-readable deterministic split manifest."""
    splits = _empty_split_payload()
    lineages: dict[str, dict[str, Any]] = {}
    grouped = group_rows_by_lineage(updated_rows)

    for lineage_id, lineage_rows in grouped.items():
        split_name = lineage_rows[0].row.split.name
        row_ids = [loaded.row.row_id for loaded in lineage_rows]
        split_payload = splits[split_name]
        split_payload["row_ids"].extend(row_ids)
        lineages[lineage_id] = {
            "row_ids": row_ids,
            "split": split_name,
        }

    for split_payload in splits.values():
        row_ids = cast(list[str], split_payload["row_ids"])
        row_ids.sort()
        split_payload["count"] = len(row_ids)

    return {
        "authority": "local",
        "lineage_count": len(lineages),
        "lineages": lineages,
        "manifest_path": str(split_manifest_path(root, seed)),
        "policy": SPLIT_POLICY,
        "root": str(root),
        "row_count": len(updated_rows),
        "seed": seed,
        "splits": splits,
    }


def write_split_manifest(root: Path, seed: int, manifest: dict[str, Any]) -> Path:
    """Write a deterministic split manifest and return its path."""
    path = split_manifest_path(root, seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def build_deterministic_splits(root: Path, *, seed: int) -> dict[str, Any]:
    """Assign private corpus rows to deterministic lineage-isolated splits."""
    all_rows = load_corpus_rows(root, include_sample=True)
    validate_orphaned_mutations(all_rows)

    private_rows = load_corpus_rows(root, include_sample=False)
    validate_lineage_leaks(private_rows)
    grouped = group_rows_by_lineage(private_rows)
    updated_rows: list[LoadedRow] = []

    for lineage_id, lineage_rows in grouped.items():
        split_name = split_for_lineage(lineage_id, seed=seed)
        for loaded in lineage_rows:
            updated = _updated_row(loaded.row, split_name=split_name, seed=seed)
            write_row(loaded.path, updated)
            updated_rows.append(LoadedRow(path=loaded.path, row=updated))

    updated_tuple = tuple(sorted(updated_rows, key=lambda loaded: loaded.row.row_id))
    validate_lineage_leaks(updated_tuple)
    manifest = build_split_manifest(root=root, seed=seed, updated_rows=updated_tuple)
    write_split_manifest(root, seed, manifest)
    return manifest
