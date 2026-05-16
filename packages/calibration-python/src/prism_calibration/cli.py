"""Public CLI surface for Prism calibration corpus operations."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, NoReturn

from pydantic import ValidationError

from prism_calibration.freeze import (
    FrozenExportError,
    freeze_slice,
    freeze_summary,
    frozen_validation_summary,
    parse_slice_name,
    validate_frozen_export,
)
from prism_calibration.harvest import (
    HarvestDatabaseError,
    HarvestSchemaError,
    HarvestSelectionError,
    harvest_summary,
    parse_selection,
    run_harvest_from_environment,
)
from prism_calibration.layout import (
    DEFAULT_CORPUS_ROOT,
    CorpusLayout,
    bootstrap_corpus_root,
    layout_payload,
)
from prism_calibration.lineage import (
    LineageValidationError,
    inspect_row_summary,
    load_lineage_context,
    load_row_reference,
    row_index,
    validate_lineage_integrity,
    validate_mutation_lineage,
)
from prism_calibration.splits import build_deterministic_splits
from prism_calibration.validation import (
    RowLoadError,
    format_validation_errors,
)

CommandHandler = Callable[[argparse.Namespace], int]


def _write_json(payload: dict[str, Any]) -> None:
    """Write deterministic JSON output to stdout."""
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _write_error(message: str) -> None:
    """Write one CLI error message to stderr."""
    sys.stderr.write(message.rstrip() + "\n")


def _parser_error(message: str) -> NoReturn:
    """Raise a parser-style fatal error."""
    raise argparse.ArgumentTypeError(message)


def _namespace_path(args: argparse.Namespace, name: str) -> Path | None:
    """Return a path argument from an argparse namespace."""
    value: object = getattr(args, name)
    if value is None:
        return None
    if isinstance(value, Path):
        return value
    if isinstance(value, str):
        return Path(value)
    _parser_error(f"{name} must be a path")


def _namespace_int(args: argparse.Namespace, name: str) -> int:
    """Return an integer argument from an argparse namespace."""
    value: object = getattr(args, name)
    if isinstance(value, int):
        return value
    _parser_error(f"{name} must be an integer")


def _handle_build(args: argparse.Namespace) -> int:
    """Bootstrap or validate the authoritative local corpus root."""
    root = _namespace_path(args, "root") or DEFAULT_CORPUS_ROOT
    seed = _namespace_int(args, "seed")
    layout = bootstrap_corpus_root(root)
    try:
        split_manifest = build_deterministic_splits(layout.root, seed=seed)
    except RowLoadError as error:
        _write_error(str(error))
        return 1
    except ValidationError as error:
        _write_error("Schema validation failed while building deterministic splits:")
        for message in format_validation_errors(error):
            _write_error(f"- {message}")
        return 1
    except LineageValidationError as error:
        _write_error(str(error))
        return 1

    payload = layout_payload(layout, seed=seed)
    payload["split_manifest"] = split_manifest
    _write_json(payload)
    return 0


def _handle_validate(args: argparse.Namespace) -> int:
    """Validate a row file, frozen export, or local root layout."""
    row_path = _namespace_path(args, "row")
    frozen_path = _namespace_path(args, "frozen")
    root = _namespace_path(args, "root") or DEFAULT_CORPUS_ROOT

    if row_path is not None and frozen_path is not None:
        _write_error("validate accepts either --row or --frozen, not both.")
        return 2
    if frozen_path is not None:
        try:
            validation = validate_frozen_export(frozen_path)
        except FrozenExportError as error:
            _write_error(str(error))
            return 1
        _write_json(frozen_validation_summary(validation))
        return 0
    if row_path is None:
        layout = CorpusLayout(root=root)
        missing = layout.missing_paths()
        if missing:
            _write_error(
                "Local calibration root is incomplete; run "
                "`uv run python -m prism_calibration.cli build` first. Missing: "
                + ", ".join(str(path) for path in missing)
            )
            return 1
        try:
            rows = load_lineage_context(root)
            validate_lineage_integrity(rows)
        except RowLoadError as error:
            _write_error(str(error))
            return 1
        except ValidationError as error:
            _write_error("Schema validation failed for local calibration rows:")
            for message in format_validation_errors(error):
                _write_error(f"- {message}")
            return 1
        except LineageValidationError as error:
            _write_error(str(error))
            return 1
        _write_json({"authority": "local", "root": str(layout.root), "status": "valid"})
        return 0

    try:
        loaded = load_row_reference(row_path, root)
        if loaded.row.provenance.source_type == "mutated":
            context = load_lineage_context(root, loaded.path)
            validate_mutation_lineage(loaded, row_index(context))
    except RowLoadError as error:
        _write_error(str(error))
        return 1
    except ValidationError as error:
        _write_error(f"Schema validation failed for {row_path}:")
        for message in format_validation_errors(error):
            _write_error(f"- {message}")
        return 1
    except LineageValidationError as error:
        _write_error(str(error))
        return 1

    _write_json({"row_id": loaded.row.row_id, "status": "valid"})
    return 0


def _handle_inspect(args: argparse.Namespace) -> int:
    """Inspect one local row or summarize the local corpus root."""
    row_path = _namespace_path(args, "row")
    root = _namespace_path(args, "root") or DEFAULT_CORPUS_ROOT
    if row_path is None:
        layout = CorpusLayout(root=root)
        _write_json(
            {
                "authority": "local",
                "missing_paths": [str(path) for path in layout.missing_paths()],
                "root": str(layout.root),
                "sample_dir": str(layout.sample_dir),
            }
        )
        return 0

    try:
        loaded = load_row_reference(row_path, root)
        context = load_lineage_context(root, loaded.path)
        summary = inspect_row_summary(loaded, context)
    except RowLoadError as error:
        _write_error(str(error))
        return 1
    except ValidationError as error:
        _write_error(f"Schema validation failed for {row_path}:")
        for message in format_validation_errors(error):
            _write_error(f"- {message}")
        return 1
    except LineageValidationError as error:
        _write_error(str(error))
        return 1

    _write_json(summary)
    return 0


def _handle_freeze(args: argparse.Namespace) -> int:
    """Freeze a named local slice into a portable export."""
    root = _namespace_path(args, "root") or DEFAULT_CORPUS_ROOT
    try:
        slice_name = parse_slice_name(getattr(args, "slice_name", None))
        export = freeze_slice(root, slice_name)
    except RowLoadError as error:
        _write_error(str(error))
        return 1
    except ValidationError as error:
        _write_error("Schema validation failed while freezing the local slice:")
        for message in format_validation_errors(error):
            _write_error(f"- {message}")
        return 1
    except (LineageValidationError, FrozenExportError) as error:
        _write_error(str(error))
        return 1

    _write_json(freeze_summary(export))
    return 0


def _handle_harvest(args: argparse.Namespace) -> int:
    """Run Neon schema preflight and deterministic trace selection."""
    root = _namespace_path(args, "root") or DEFAULT_CORPUS_ROOT
    limit = _namespace_int(args, "limit")
    selection_value = str(args.selection)
    preflight_only = bool(args.preflight_only)
    try:
        selection = parse_selection(selection_value)
        result = run_harvest_from_environment(
            root=root,
            limit=limit,
            selection=selection,
            preflight_only=preflight_only,
        )
    except (HarvestDatabaseError, HarvestSchemaError, HarvestSelectionError) as error:
        _write_error(str(error))
        return 1

    summary = harvest_summary(result)
    _write_json(summary)
    return 1 if summary.get("exit_status") == "failure" else 0


def _deferred_handler(command_name: str, milestone: str) -> CommandHandler:
    """Return a handler for commands reserved by later mission milestones."""

    def _handle_deferred(_args: argparse.Namespace) -> int:
        _write_error(
            f"`{command_name}` is part of the public corpus CLI contract, but its "
            f"implementation is reserved for the {milestone} milestone."
        )
        return 2

    return _handle_deferred


def build_parser() -> argparse.ArgumentParser:
    """Build the Prism calibration CLI parser."""
    parser = argparse.ArgumentParser(
        prog="prism-calibration",
        description=(
            "Local-first calibration corpus operations. The authoritative root is "
            "data/calibration/; Braintrust mirrors later frozen exports."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)

    build = subparsers.add_parser(
        "build",
        help="Bootstrap or rebuild the local corpus layout.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    build.add_argument("--root", type=Path, default=DEFAULT_CORPUS_ROOT)
    build.add_argument("--seed", type=int, default=42)
    build.set_defaults(handler=_handle_build)

    harvest = subparsers.add_parser(
        "harvest",
        help="Harvest real traces into local corpus rows.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    harvest.add_argument("--root", type=Path, default=DEFAULT_CORPUS_ROOT)
    harvest.add_argument("--limit", type=int, default=10)
    harvest.add_argument("--selection", choices=("recent", "oldest"), default="recent")
    harvest.add_argument("--preflight-only", action="store_true")
    harvest.set_defaults(handler=_handle_harvest)

    label = subparsers.add_parser(
        "label",
        help="Generate synthetic labels, mutations, or review routing metadata.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    label.add_argument("--root", type=Path, default=DEFAULT_CORPUS_ROOT)
    label.set_defaults(handler=_deferred_handler("label", "labeling-review"))

    freeze = subparsers.add_parser(
        "freeze",
        help="Freeze a named local slice into a portable export.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    freeze.add_argument("--root", type=Path, default=DEFAULT_CORPUS_ROOT)
    freeze.add_argument("--slice", dest="slice_name", required=True)
    freeze.set_defaults(handler=_handle_freeze)

    sync = subparsers.add_parser(
        "sync",
        help="Sync a frozen local slice to Braintrust while preserving local authority.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    sync.add_argument("--root", type=Path, default=DEFAULT_CORPUS_ROOT)
    sync.add_argument("--slice", dest="slice_name")
    sync.add_argument("--pull-review", action="store_true")
    sync.set_defaults(handler=_deferred_handler("sync", "braintrust-integration"))

    eval_command = subparsers.add_parser(
        "eval",
        help="Run calibration evals against a local or frozen slice.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    eval_command.add_argument("--root", type=Path, default=DEFAULT_CORPUS_ROOT)
    eval_command.add_argument("--slice", dest="slice_name")
    eval_command.add_argument("--frozen", type=Path)
    eval_command.set_defaults(handler=_deferred_handler("eval", "regression-gates"))

    inspect = subparsers.add_parser(
        "inspect",
        help="Inspect a local row or corpus root without Braintrust.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    inspect.add_argument("--root", type=Path, default=DEFAULT_CORPUS_ROOT)
    inspect.add_argument("--row", type=Path)
    inspect.set_defaults(handler=_handle_inspect)

    validate = subparsers.add_parser(
        "validate",
        help="Validate a row file, frozen export, or local corpus layout.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    validate.add_argument("--root", type=Path, default=DEFAULT_CORPUS_ROOT)
    validate.add_argument("--row", type=Path)
    validate.add_argument("--frozen", type=Path)
    validate.set_defaults(handler=_handle_validate)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Prism calibration CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    handler: object = getattr(args, "handler", None)
    if not callable(handler):
        parser.print_help(sys.stderr)
        return 2
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
