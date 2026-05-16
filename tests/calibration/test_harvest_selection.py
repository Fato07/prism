"""Deterministic harvest selection tests for real-trace manifests."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from prism_calibration.harvest import REQUIRED_HARVEST_COLUMNS, run_harvest


class SortingFakeCursor:
    """DB-API cursor fake that sorts trace rows according to the SQL policy."""

    def __init__(self, connection: SortingFakeConnection) -> None:
        self.connection = connection
        self._rows: list[tuple[object, ...]] = []

    def __enter__(self) -> SortingFakeCursor:
        """Enter the fake cursor context manager."""
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """Exit the fake cursor context manager."""

    def execute(self, query: str, params: Sequence[object] | None = None) -> object:
        """Apply fake information_schema or deterministic trace selection."""
        self.connection.queries.append(query)
        self.connection.params.append(tuple(params or ()))
        if "information_schema.columns" in query:
            self._rows = sorted(self.connection.schema_rows)
        elif "FROM public.traces" in query:
            limit = int((params or (0,))[0])
            reverse = "t.created_at DESC" in query
            if reverse:
                sorted_rows = sorted(
                    self.connection.trace_rows,
                    key=lambda row: (-row[1].timestamp(), row[0]),
                )
            else:
                sorted_rows = sorted(
                    self.connection.trace_rows,
                    key=lambda row: (row[1], row[0]),
                )
            self._rows = sorted_rows[:limit]
        else:
            raise AssertionError(f"Unexpected query: {query}")
        return self

    def fetchall(self) -> list[tuple[object, ...]]:
        """Return rows for the last fake query."""
        return list(self._rows)


class SortingFakeConnection:
    """Connection fake for deterministic selection tests."""

    def __init__(self, trace_rows: list[tuple[str, datetime]]) -> None:
        self.schema_rows = {
            (required.table, required.column)
            for required in REQUIRED_HARVEST_COLUMNS
        }
        self.trace_rows = trace_rows
        self.queries: list[str] = []
        self.params: list[tuple[object, ...]] = []

    def cursor(self) -> SortingFakeCursor:
        """Return a context-manageable fake cursor."""
        return SortingFakeCursor(self)


def test_repeated_harvest_selection_is_ordered_and_manifested(tmp_path: Path) -> None:
    """Same inputs produce the same ordered trace IDs and selection policy."""
    root = tmp_path / "calibration"
    trace_rows = [
        ("trace-002", datetime(2026, 5, 15, 12, 5, tzinfo=UTC)),
        ("trace-003", datetime(2026, 5, 15, 12, 5, tzinfo=UTC)),
        ("trace-001", datetime(2026, 5, 15, 12, 1, tzinfo=UTC)),
    ]

    first = run_harvest(
        root=root,
        connection=SortingFakeConnection(trace_rows),
        limit=2,
        selection="recent",
        preflight_only=False,
    )
    second = run_harvest(
        root=root,
        connection=SortingFakeConnection(trace_rows),
        limit=2,
        selection="recent",
        preflight_only=False,
    )

    assert first.status == "selected"
    assert second.status == "selected"
    assert first.manifest is not None
    assert second.manifest is not None
    assert first.manifest.manifest_id == second.manifest.manifest_id
    assert first.manifest.selected_trace_ids == ["trace-002", "trace-003"]
    assert second.manifest.selected_trace_ids == first.manifest.selected_trace_ids
    assert first.manifest.selection_policy.name == "recent"
    assert first.manifest.selection_policy.limit == 2
    assert first.manifest.selection_policy.order_by == [
        "traces.created_at DESC",
        "traces.trace_id ASC",
    ]
    assert first.manifest_path == second.manifest_path
    assert first.manifest_path is not None

    manifest_payload = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    assert manifest_payload["kind"] == "prism_calibration.harvest_selection"
    assert manifest_payload["selected_trace_ids"] == ["trace-002", "trace-003"]
    assert manifest_payload["selection_policy"]["name"] == "recent"
    assert manifest_payload["selection_policy"]["order_by"] == [
        "traces.created_at DESC",
        "traces.trace_id ASC",
    ]


def test_oldest_selection_uses_stable_ascending_order(tmp_path: Path) -> None:
    """The oldest policy orders by created_at ascending with trace_id tie-breaks."""
    root = tmp_path / "calibration"
    trace_rows = [
        ("trace-003", datetime(2026, 5, 15, 12, 1, tzinfo=UTC)),
        ("trace-001", datetime(2026, 5, 15, 12, 1, tzinfo=UTC)),
        ("trace-002", datetime(2026, 5, 15, 12, 5, tzinfo=UTC)),
    ]

    result = run_harvest(
        root=root,
        connection=SortingFakeConnection(trace_rows),
        limit=2,
        selection="oldest",
        preflight_only=False,
    )

    assert result.manifest is not None
    assert result.manifest.selected_trace_ids == ["trace-001", "trace-003"]
    assert result.manifest.selection_policy.order_by == [
        "traces.created_at ASC",
        "traces.trace_id ASC",
    ]
