"""Lineage loading, inspection, and leak checks for calibration rows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from prism_calibration.layout import CorpusLayout
from prism_calibration.models import CalibrationRow
from prism_calibration.validation import RowLoadError, load_row, row_summary


class LineageValidationError(ValueError):
    """Raised when local row lineage is incomplete or split-leaky."""


@dataclass(frozen=True)
class LoadedRow:
    """A validated row plus its local filesystem path."""

    path: Path
    row: CalibrationRow


def iter_row_paths(root: Path, *, include_sample: bool) -> tuple[Path, ...]:
    """Return deterministic row file paths under the local corpus root."""
    layout = CorpusLayout(root=root)
    directories = [layout.root / "rows"]
    if include_sample:
        directories.append(layout.sample_dir / "rows")

    paths: list[Path] = []
    for directory in directories:
        if directory.is_dir():
            paths.extend(sorted(directory.glob("*.json")))
    return tuple(paths)


def load_corpus_rows(root: Path, *, include_sample: bool = True) -> tuple[LoadedRow, ...]:
    """Load all local corpus rows in deterministic path order."""
    return tuple(
        LoadedRow(path=path, row=load_row(path))
        for path in iter_row_paths(root, include_sample=include_sample)
    )


def resolve_row_reference(row_ref: Path, root: Path) -> Path:
    """Resolve a CLI row argument as either a path or a local row ID."""
    if row_ref.exists():
        return row_ref

    candidate_names = [row_ref.name]
    if row_ref.suffix != ".json":
        candidate_names.insert(0, f"{row_ref.name}.json")

    layout = CorpusLayout(root=root)
    for directory in (layout.root / "rows", layout.sample_dir / "rows"):
        for candidate_name in candidate_names:
            candidate = directory / candidate_name
            if candidate.exists():
                return candidate

    raise RowLoadError(
        f"{row_ref}: unable to resolve row reference as a file path or local row ID "
        f"under {root}"
    )


def load_row_reference(row_ref: Path, root: Path) -> LoadedRow:
    """Load one row by path or local row ID."""
    row_path = resolve_row_reference(row_ref, root)
    return LoadedRow(path=row_path, row=load_row(row_path))


def row_index(rows: tuple[LoadedRow, ...]) -> dict[str, LoadedRow]:
    """Index rows by stable row ID and reject duplicates."""
    indexed: dict[str, LoadedRow] = {}
    for loaded in rows:
        existing = indexed.get(loaded.row.row_id)
        if existing is not None and existing.path != loaded.path:
            raise LineageValidationError(
                "Duplicate row_id "
                f"'{loaded.row.row_id}' found at {existing.path} and {loaded.path}"
            )
        indexed[loaded.row.row_id] = loaded
    return indexed


def load_lineage_context(root: Path, row_path: Path | None = None) -> tuple[LoadedRow, ...]:
    """Load local rows plus adjacent fixture rows for parent lookup."""
    loaded_rows = list(load_corpus_rows(root, include_sample=True))
    seen_paths = {loaded.path.resolve() for loaded in loaded_rows if loaded.path.exists()}

    if row_path is not None and row_path.exists():
        candidate_paths = sorted(row_path.parent.glob("*.json"))
        for candidate_path in candidate_paths:
            resolved = candidate_path.resolve()
            if resolved in seen_paths:
                continue
            loaded_rows.append(LoadedRow(path=candidate_path, row=load_row(candidate_path)))
            seen_paths.add(resolved)

    return tuple(sorted(loaded_rows, key=lambda loaded: (loaded.row.row_id, str(loaded.path))))


def validate_mutation_lineage(
    loaded: LoadedRow,
    indexed_rows: dict[str, LoadedRow],
) -> None:
    """Ensure one mutated row has a locally recoverable parent lineage."""
    row = loaded.row
    if row.provenance.source_type != "mutated":
        return

    parent_row_id = row.provenance.parent_row_id
    if parent_row_id is None:
        raise LineageValidationError(
            f"Orphaned mutated row '{row.row_id}': parent_row_id is missing"
        )

    parent = indexed_rows.get(parent_row_id)
    if parent is None:
        raise LineageValidationError(
            f"Orphaned mutated row '{row.row_id}': parent_row_id "
            f"'{parent_row_id}' was not found locally"
        )

    if parent.row.provenance.lineage_id != row.provenance.lineage_id:
        raise LineageValidationError(
            f"Lineage mismatch for mutated row '{row.row_id}': parent "
            f"'{parent_row_id}' has lineage_id "
            f"'{parent.row.provenance.lineage_id}', child has "
            f"'{row.provenance.lineage_id}'"
        )


def validate_orphaned_mutations(rows: tuple[LoadedRow, ...]) -> None:
    """Reject mutated rows whose parent row is absent from local context."""
    indexed_rows = row_index(rows)
    for loaded in rows:
        validate_mutation_lineage(loaded, indexed_rows)


def validate_lineage_leaks(rows: tuple[LoadedRow, ...]) -> None:
    """Reject lineage families that span conflicting non-sample splits."""
    by_lineage: dict[str, list[LoadedRow]] = {}
    for loaded in rows:
        if loaded.row.split.name == "sample":
            continue
        by_lineage.setdefault(loaded.row.provenance.lineage_id, []).append(loaded)

    for lineage_id, lineage_rows in sorted(by_lineage.items()):
        split_names = {loaded.row.split.name for loaded in lineage_rows}
        if len(split_names) <= 1:
            continue
        row_details = ", ".join(
            f"{loaded.row.row_id}:{loaded.row.split.name}"
            for loaded in sorted(lineage_rows, key=lambda item: item.row.row_id)
        )
        raise LineageValidationError(
            f"Lineage leak for '{lineage_id}': related rows cross conflicting "
            f"splits ({row_details})"
        )


def validate_lineage_integrity(rows: tuple[LoadedRow, ...]) -> None:
    """Run all local lineage integrity checks."""
    validate_orphaned_mutations(rows)
    validate_lineage_leaks(rows)


def inspect_row_summary(loaded: LoadedRow, context_rows: tuple[LoadedRow, ...]) -> dict[str, Any]:
    """Return a row summary that includes parent lineage for mutations."""
    summary = row_summary(loaded.row)
    summary["mutation_type"] = loaded.row.provenance.mutation_type

    if loaded.row.provenance.source_type != "mutated":
        return summary

    indexed_rows = row_index(context_rows)
    validate_mutation_lineage(loaded, indexed_rows)
    parent_row_id = loaded.row.provenance.parent_row_id
    if parent_row_id is None:
        return summary
    parent = indexed_rows[parent_row_id]
    summary["parent"] = {
        "lineage_id": parent.row.provenance.lineage_id,
        "row_id": parent.row.row_id,
        "source_type": parent.row.provenance.source_type,
        "split": parent.row.split.name,
        "trace_id": parent.row.trace.trace_id,
    }
    return summary
