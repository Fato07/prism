"""Harvest schema preflight tests for the Neon-backed corpus surface."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from prism_calibration.harvest import (
    REQUIRED_HARVEST_COLUMNS,
    HarvestSchemaError,
    run_harvest,
)


class FakeCursor:
    """Tiny DB-API cursor fake that records preflight versus row-read order."""

    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self._rows: list[tuple[object, ...]] = []

    def __enter__(self) -> FakeCursor:
        """Enter the fake cursor context manager."""
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """Exit the fake cursor context manager."""

    def execute(self, query: str, params: Sequence[object] | None = None) -> object:
        """Record a query and load the corresponding fake result rows."""
        self.connection.queries.append(query)
        if "information_schema.columns" in query:
            self._rows = sorted(self.connection.schema_rows)
        elif "FROM public.traces" in query:
            self.connection.row_read_attempted = True
            self._rows = self.connection.selection_rows
        else:
            raise AssertionError(f"Unexpected query: {query}")
        self.connection.params.append(tuple(params or ()))
        return self

    def fetchall(self) -> list[tuple[object, ...]]:
        """Return fake rows for the last executed query."""
        return list(self._rows)


class FakeConnection:
    """Tiny connection fake exposing the cursor protocol used by harvest."""

    def __init__(
        self,
        *,
        schema_rows: set[tuple[str, str]],
        selection_rows: list[tuple[object, ...]] | None = None,
    ) -> None:
        self.schema_rows = schema_rows
        self.selection_rows = selection_rows or []
        self.queries: list[str] = []
        self.params: list[tuple[object, ...]] = []
        self.row_read_attempted = False

    def cursor(self) -> FakeCursor:
        """Return a context-manageable fake cursor."""
        return FakeCursor(self)


def complete_schema() -> set[tuple[str, str]]:
    """Return all required harvest columns as fake information_schema rows."""
    return {
        (required.table, required.column)
        for required in REQUIRED_HARVEST_COLUMNS
    }


def test_preflight_only_lists_checked_columns_before_reading_rows(tmp_path: Path) -> None:
    """Preflight output names every checked column and does not read traces."""
    connection = FakeConnection(schema_rows=complete_schema())

    result = run_harvest(
        root=tmp_path / "calibration",
        connection=connection,
        limit=5,
        selection="recent",
        preflight_only=True,
    )

    assert result.status == "preflight_passed"
    assert connection.row_read_attempted is False
    assert "information_schema.columns" in connection.queries[0]
    checked = [f"{column.table}.{column.column}" for column in result.preflight.checked_columns]
    assert checked == [
        f"{required.table}.{required.column}"
        for required in REQUIRED_HARVEST_COLUMNS
    ]


def test_missing_required_columns_fail_fast_with_migration_style_error(
    tmp_path: Path,
) -> None:
    """Missing Neon provenance columns fail before any trace row is read."""
    schema_rows = complete_schema()
    schema_rows.remove(("validations", "requester_address"))
    connection = FakeConnection(schema_rows=schema_rows)

    with pytest.raises(HarvestSchemaError) as error:
        run_harvest(
            root=tmp_path / "calibration",
            connection=connection,
            limit=5,
            selection="recent",
            preflight_only=False,
        )

    message = str(error.value)
    assert "Neon schema preflight failed" in message
    assert "validations.requester_address" in message
    assert "ALTER TABLE validations ADD COLUMN requester_address TEXT;" in message
    assert connection.row_read_attempted is False
