"""Portable frozen export support for local calibration corpus slices."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast, get_args

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from prism_calibration.layout import bootstrap_corpus_root
from prism_calibration.lineage import (
    LoadedRow,
    load_corpus_rows,
    validate_lineage_integrity,
)
from prism_calibration.models import CalibrationRow, SourceType, SplitName
from prism_calibration.splits import deterministic_row_json

EXPORT_SCHEMA_VERSION: Literal["1.0"] = "1.0"
EXPORT_KIND: Literal["prism_calibration.frozen_export"] = "prism_calibration.frozen_export"
IDENTITY_ALGORITHM: Literal["sha256:frozen-export-v1"] = "sha256:frozen-export-v1"
ROW_HASH_ALGORITHM: Literal["sha256:normalized-row-json-v1"] = (
    "sha256:normalized-row-json-v1"
)
SPLIT_NAMES = frozenset(cast(tuple[str, ...], get_args(SplitName)))
TUNING_EXPORT_SLICES = frozenset({"pilot", "dev"})


class FrozenExportError(ValueError):
    """Raised when a frozen export cannot be created or validated."""


class FrozenRowManifest(BaseModel):
    """Manifest entry for one normalized row file in a frozen export."""

    model_config = ConfigDict(extra="forbid")

    row_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    lineage_id: str = Field(min_length=1)
    source_type: SourceType
    split: SplitName
    path: str = Field(min_length=1)
    row_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class FrozenSplitMetadata(BaseModel):
    """Split metadata captured in a portable frozen export manifest."""

    model_config = ConfigDict(extra="forbid")

    name: SplitName
    count: int = Field(ge=0)
    row_ids: list[str]
    policies: list[str]
    seeds: list[int]
    lineages: dict[str, list[str]]


class FrozenExportManifest(BaseModel):
    """Machine-readable manifest for one frozen local slice."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["prism_calibration.frozen_export"] = EXPORT_KIND
    schema_version: Literal["1.0"] = EXPORT_SCHEMA_VERSION
    identity_algorithm: Literal["sha256:frozen-export-v1"] = IDENTITY_ALGORITHM
    row_hash_algorithm: Literal["sha256:normalized-row-json-v1"] = ROW_HASH_ALGORITHM
    export_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    slice_name: SplitName
    row_count: int = Field(ge=0)
    row_ids: list[str]
    rows: list[FrozenRowManifest]
    split_metadata: FrozenSplitMetadata


@dataclass(frozen=True)
class FrozenExport:
    """A created frozen export and its resolved local paths."""

    export_dir: Path
    manifest_path: Path
    manifest: FrozenExportManifest


@dataclass(frozen=True)
class FrozenValidation:
    """Validation result for a frozen export reloaded from disk."""

    export_dir: Path
    manifest_path: Path
    manifest: FrozenExportManifest
    manifest_hash: str
    row_hashes: dict[str, str]


def parse_slice_name(value: str | None) -> SplitName:
    """Parse and validate a public slice name."""
    if value is None:
        raise FrozenExportError("--slice is required")
    if value not in SPLIT_NAMES:
        allowed = ", ".join(sorted(SPLIT_NAMES))
        raise FrozenExportError(f"Unknown slice '{value}'. Expected one of: {allowed}")
    return cast(SplitName, value)


def _canonical_json(payload: dict[str, Any]) -> bytes:
    """Return compact canonical JSON bytes for stable identity hashing."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _hash_bytes(payload: bytes) -> str:
    """Return a SHA-256 hex digest for bytes."""
    return hashlib.sha256(payload).hexdigest()


def normalized_row_bytes(row: CalibrationRow) -> bytes:
    """Return the normalized row payload bytes used by frozen exports."""
    return deterministic_row_json(row).encode("utf-8")


def normalized_row_hash(row: CalibrationRow) -> str:
    """Return the stable hash for a normalized calibration row payload."""
    return _hash_bytes(normalized_row_bytes(row))


def _selected_rows(root: Path, slice_name: SplitName) -> tuple[LoadedRow, ...]:
    """Load and select rows belonging to one local slice."""
    # Load all rows once (including sample) for lineage validation.
    all_rows = load_corpus_rows(root, include_sample=True)
    _validate_holdout_export_policy(all_rows, slice_name)
    validate_lineage_integrity(all_rows)

    # Filter from the single load above.  Sample rows carry split.name="sample"
    # (enforced by the CalibrationRow validator), so a non-sample slice_name
    # will never match them — no need for a separate include_sample=False load.
    selected = [loaded for loaded in all_rows if loaded.row.split.name == slice_name]

    return tuple(sorted(selected, key=lambda loaded: loaded.row.row_id))


def _validate_holdout_export_policy(
    rows: tuple[LoadedRow, ...],
    slice_name: SplitName,
) -> None:
    """Reject holdout lineages that are merged into tuning/dev exports."""
    if slice_name not in TUNING_EXPORT_SLICES:
        return

    selected_lineages = {
        loaded.row.provenance.lineage_id
        for loaded in rows
        if loaded.row.split.name == slice_name
    }
    if not selected_lineages:
        return

    for lineage_id in sorted(selected_lineages):
        holdout_rows = sorted(
            loaded.row.row_id
            for loaded in rows
            if loaded.row.split.name == "holdout"
            and loaded.row.provenance.lineage_id == lineage_id
        )
        if holdout_rows:
            joined_rows = ", ".join(holdout_rows)
            raise FrozenExportError(
                f"Holdout lineage '{lineage_id}' is locked for manual/eval only "
                f"and cannot be merged into the {slice_name} tuning/dev export. "
                f"Holdout rows: {joined_rows}"
            )


def _row_entry(row: CalibrationRow) -> FrozenRowManifest:
    """Build a manifest entry for one row."""
    return FrozenRowManifest(
        row_id=row.row_id,
        trace_id=row.trace.trace_id,
        lineage_id=row.provenance.lineage_id,
        source_type=row.provenance.source_type,
        split=row.split.name,
        path=f"rows/{row.row_id}.json",
        row_hash=normalized_row_hash(row),
    )


def _split_metadata(slice_name: SplitName, rows: tuple[LoadedRow, ...]) -> FrozenSplitMetadata:
    """Build split metadata for the selected rows."""
    row_ids = [loaded.row.row_id for loaded in rows]
    lineages: dict[str, list[str]] = {}
    for loaded in rows:
        lineage_id = loaded.row.provenance.lineage_id
        lineages.setdefault(lineage_id, []).append(loaded.row.row_id)

    for lineage_rows in lineages.values():
        lineage_rows.sort()

    return FrozenSplitMetadata(
        name=slice_name,
        count=len(rows),
        row_ids=row_ids,
        policies=sorted({loaded.row.split.policy for loaded in rows}),
        seeds=sorted({loaded.row.split.seed for loaded in rows}),
        lineages=dict(sorted(lineages.items())),
    )


def _identity_payload(
    *,
    slice_name: SplitName,
    row_entries: list[FrozenRowManifest],
    split_metadata: FrozenSplitMetadata,
) -> dict[str, Any]:
    """Return the export identity payload excluding the identity itself."""
    row_ids = [entry.row_id for entry in row_entries]
    return {
        "kind": EXPORT_KIND,
        "schema_version": EXPORT_SCHEMA_VERSION,
        "identity_algorithm": IDENTITY_ALGORITHM,
        "row_hash_algorithm": ROW_HASH_ALGORITHM,
        "slice_name": slice_name,
        "row_count": len(row_entries),
        "row_ids": row_ids,
        "rows": [entry.model_dump(mode="json") for entry in row_entries],
        "split_metadata": split_metadata.model_dump(mode="json"),
    }


def _export_id(
    *,
    slice_name: SplitName,
    row_entries: list[FrozenRowManifest],
    split_metadata: FrozenSplitMetadata,
) -> str:
    """Compute the stable export identity for one slice."""
    payload = _identity_payload(
        slice_name=slice_name,
        row_entries=row_entries,
        split_metadata=split_metadata,
    )
    return _hash_bytes(_canonical_json(payload))


def _manifest_bytes(manifest: FrozenExportManifest) -> bytes:
    """Return deterministic, human-readable manifest JSON bytes."""
    payload = manifest.model_dump(mode="json")
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def build_frozen_manifest(
    *,
    slice_name: SplitName,
    rows: tuple[LoadedRow, ...],
) -> FrozenExportManifest:
    """Build a deterministic frozen export manifest for selected rows."""
    row_entries = [_row_entry(loaded.row) for loaded in rows]
    split_metadata = _split_metadata(slice_name, rows)
    export_id = _export_id(
        slice_name=slice_name,
        row_entries=row_entries,
        split_metadata=split_metadata,
    )
    return FrozenExportManifest(
        export_id=export_id,
        slice_name=slice_name,
        row_count=len(row_entries),
        row_ids=[entry.row_id for entry in row_entries],
        rows=row_entries,
        split_metadata=split_metadata,
    )


def freeze_slice(root: Path, slice_name: SplitName) -> FrozenExport:
    """Freeze a named local slice into a portable export directory."""
    layout = bootstrap_corpus_root(root)
    rows = _selected_rows(layout.root, slice_name)
    manifest = build_frozen_manifest(slice_name=slice_name, rows=rows)

    export_dir = layout.root / "frozen" / slice_name / manifest.export_id
    rows_dir = export_dir / "rows"
    rows_dir.mkdir(parents=True, exist_ok=True)

    for loaded, entry in zip(rows, manifest.rows, strict=True):
        row_path = export_dir / entry.path
        row_path.write_bytes(normalized_row_bytes(loaded.row))

    manifest_path = export_dir / "manifest.json"
    manifest_path.write_bytes(_manifest_bytes(manifest))
    return FrozenExport(export_dir=export_dir, manifest_path=manifest_path, manifest=manifest)


def _resolve_manifest_path(path: Path) -> Path:
    """Resolve a frozen export path as either a directory or manifest file."""
    if path.is_dir():
        return path / "manifest.json"
    return path


def _relative_export_row_path(export_dir: Path, relative_path: str) -> Path:
    """Resolve a manifest row path while rejecting absolute or parent traversal."""
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise FrozenExportError(f"Invalid frozen row path '{relative_path}' in manifest")
    return export_dir / path


def _load_manifest(manifest_path: Path) -> FrozenExportManifest:
    """Load and validate a frozen export manifest."""
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise FrozenExportError(
            f"{manifest_path}: unable to read frozen manifest: {error}"
        ) from error
    except json.JSONDecodeError as error:
        message = (
            f"{manifest_path}: invalid manifest JSON at line "
            f"{error.lineno}, column {error.colno}"
        )
        raise FrozenExportError(message) from error

    try:
        return FrozenExportManifest.model_validate(payload)
    except ValidationError as error:
        raise FrozenExportError(f"{manifest_path}: invalid frozen manifest: {error}") from error


def _validate_identity(manifest: FrozenExportManifest) -> None:
    """Recompute and verify a frozen export's stable identity."""
    expected = _export_id(
        slice_name=manifest.slice_name,
        row_entries=manifest.rows,
        split_metadata=manifest.split_metadata,
    )
    if manifest.export_id != expected:
        raise FrozenExportError(
            "Frozen export identity mismatch: manifest export_id "
            f"{manifest.export_id} does not match recomputed {expected}"
        )


def _validate_manifest_counts(manifest: FrozenExportManifest) -> None:
    """Validate manifest row IDs, counts, and split metadata agree."""
    row_ids = [entry.row_id for entry in manifest.rows]
    if manifest.row_ids != row_ids:
        raise FrozenExportError("Frozen manifest row_ids do not match row entry order")
    if manifest.row_count != len(manifest.rows):
        raise FrozenExportError(
            f"Frozen manifest row_count={manifest.row_count} but has "
            f"{len(manifest.rows)} row entries"
        )
    if manifest.split_metadata.count != manifest.row_count:
        raise FrozenExportError(
            "Frozen split metadata count does not match manifest row_count"
        )
    if manifest.split_metadata.row_ids != manifest.row_ids:
        raise FrozenExportError("Frozen split metadata row_ids do not match manifest row_ids")


def _load_frozen_row(row_path: Path) -> CalibrationRow:
    """Load one frozen row as a validated calibration row."""
    try:
        raw = row_path.read_text(encoding="utf-8")
    except OSError as error:
        raise FrozenExportError(f"{row_path}: unable to read frozen row: {error}") from error

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        message = f"{row_path}: invalid row JSON at line {error.lineno}, column {error.colno}"
        raise FrozenExportError(message) from error

    try:
        row = CalibrationRow.model_validate(payload)
    except ValidationError as error:
        raise FrozenExportError(f"{row_path}: invalid frozen row: {error}") from error

    normalized = normalized_row_bytes(row).decode("utf-8")
    if raw != normalized:
        raise FrozenExportError(f"{row_path}: row payload is not normalized JSON")
    return row


def validate_frozen_export(path: Path) -> FrozenValidation:
    """Validate a frozen export from any clean local path."""
    manifest_path = _resolve_manifest_path(path)
    export_dir = manifest_path.parent
    manifest = _load_manifest(manifest_path)
    _validate_manifest_counts(manifest)
    _validate_identity(manifest)

    row_hashes: dict[str, str] = {}
    for entry in manifest.rows:
        if entry.split != manifest.slice_name:
            raise FrozenExportError(
                f"Manifest entry {entry.row_id} uses split {entry.split}, "
                f"not frozen slice {manifest.slice_name}"
            )
        row_path = _relative_export_row_path(export_dir, entry.path)
        row = _load_frozen_row(row_path)
        if row.row_id != entry.row_id:
            raise FrozenExportError(
                f"{row_path}: row_id {row.row_id} does not match manifest entry "
                f"{entry.row_id}"
            )
        if row.trace.trace_id != entry.trace_id:
            raise FrozenExportError(
                f"{row_path}: trace_id {row.trace.trace_id} does not match manifest "
                f"entry {entry.trace_id}"
            )
        if row.provenance.lineage_id != entry.lineage_id:
            raise FrozenExportError(
                f"{row_path}: lineage_id {row.provenance.lineage_id} does not match "
                f"manifest entry {entry.lineage_id}"
            )
        if row.provenance.source_type != entry.source_type:
            raise FrozenExportError(
                f"{row_path}: source_type {row.provenance.source_type} does not match "
                f"manifest entry {entry.source_type}"
            )
        if row.split.name != manifest.slice_name:
            raise FrozenExportError(
                f"{row_path}: split {row.split.name} does not match frozen slice "
                f"{manifest.slice_name}"
            )

        row_hash = normalized_row_hash(row)
        if row_hash != entry.row_hash:
            raise FrozenExportError(
                f"{row_path}: row hash mismatch for {entry.row_id}: "
                f"manifest has {entry.row_hash}, recomputed {row_hash}"
            )
        row_hashes[row.row_id] = row_hash

    if list(row_hashes) != manifest.row_ids:
        raise FrozenExportError("Reloaded row IDs do not match manifest row_ids")

    try:
        manifest_hash = _hash_bytes(manifest_path.read_bytes())
    except OSError as error:
        raise FrozenExportError(f"{manifest_path}: unable to hash manifest: {error}") from error

    return FrozenValidation(
        export_dir=export_dir,
        manifest_path=manifest_path,
        manifest=manifest,
        manifest_hash=manifest_hash,
        row_hashes=row_hashes,
    )


def freeze_summary(export: FrozenExport) -> dict[str, Any]:
    """Return a machine-readable CLI summary for a frozen slice."""
    return {
        "authority": "local",
        "export_id": export.manifest.export_id,
        "export_path": str(export.export_dir),
        "manifest_path": str(export.manifest_path),
        "row_count": export.manifest.row_count,
        "row_hashes": {
            entry.row_id: entry.row_hash for entry in export.manifest.rows
        },
        "row_ids": export.manifest.row_ids,
        "slice": export.manifest.slice_name,
        "status": "frozen",
    }


def frozen_validation_summary(validation: FrozenValidation) -> dict[str, Any]:
    """Return a machine-readable CLI summary for a validated frozen export."""
    return {
        "authority": "local",
        "export_id": validation.manifest.export_id,
        "export_path": str(validation.export_dir),
        "manifest_hash": validation.manifest_hash,
        "manifest_path": str(validation.manifest_path),
        "row_count": validation.manifest.row_count,
        "row_hashes": validation.row_hashes,
        "row_ids": validation.manifest.row_ids,
        "slice": validation.manifest.slice_name,
        "status": "valid",
    }
