"""Neon harvest preflight and deterministic trace selection."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field

from prism_calibration.layout import bootstrap_corpus_root

HARVEST_SCHEMA_VERSION: Literal["1.0"] = "1.0"
HARVEST_MANIFEST_KIND: Literal["prism_calibration.harvest_selection"] = (
    "prism_calibration.harvest_selection"
)
HARVEST_SELECTION_POLICY_VERSION: Literal["neon-trace-selection-v1"] = (
    "neon-trace-selection-v1"
)
HarvestSelectionName = Literal["recent", "oldest"]


class HarvestDatabaseError(ValueError):
    """Raised when the harvest command cannot connect to or query Neon."""


class HarvestSchemaError(ValueError):
    """Raised when Neon schema preflight finds missing harvest columns."""


class HarvestSelectionError(ValueError):
    """Raised when deterministic trace selection cannot be completed."""


@dataclass(frozen=True)
class RequiredHarvestColumn:
    """A Neon column required before real trace harvest may read rows."""

    table: Literal["traces", "validations"]
    column: str
    migration_type: str

    @property
    def qualified_name(self) -> str:
        """Return ``table.column`` for error messages and manifests."""
        return f"{self.table}.{self.column}"


REQUIRED_HARVEST_COLUMNS: tuple[RequiredHarvestColumn, ...] = (
    RequiredHarvestColumn("traces", "trace_id", "UUID"),
    RequiredHarvestColumn("traces", "agent_id", "BIGINT"),
    RequiredHarvestColumn("traces", "market_id", "TEXT"),
    RequiredHarvestColumn("traces", "ipfs_cid", "TEXT"),
    RequiredHarvestColumn("traces", "content_hash", "BYTEA"),
    RequiredHarvestColumn("traces", "tx_hash", "TEXT"),
    RequiredHarvestColumn("traces", "created_at", "TIMESTAMPTZ"),
    RequiredHarvestColumn("validations", "request_hash", "BYTEA"),
    RequiredHarvestColumn("validations", "trace_id", "UUID"),
    RequiredHarvestColumn("validations", "sentinel_agent_id", "BIGINT"),
    RequiredHarvestColumn("validations", "verdict_score", "SMALLINT"),
    RequiredHarvestColumn("validations", "response_uri", "TEXT"),
    RequiredHarvestColumn("validations", "requester_address", "TEXT"),
    RequiredHarvestColumn("validations", "tx_hash", "TEXT"),
    RequiredHarvestColumn("validations", "created_at", "TIMESTAMPTZ"),
)

_RECENT_ORDER_BY = ["traces.created_at DESC", "traces.trace_id ASC"]
_OLDEST_ORDER_BY = ["traces.created_at ASC", "traces.trace_id ASC"]
_SELECTION_SQL_ORDER_BY: dict[HarvestSelectionName, str] = {
    "recent": "t.created_at DESC, t.trace_id ASC",
    "oldest": "t.created_at ASC, t.trace_id ASC",
}

_COLUMN_PREFLIGHT_SQL = """
SELECT table_name, column_name
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('traces', 'validations')
ORDER BY table_name ASC, column_name ASC
"""


class CursorLike(Protocol):
    """Subset of DB cursor behavior required by harvest."""

    def execute(self, query: str, params: Sequence[object] | None = None) -> object:
        """Execute a SQL query."""

    def fetchall(self) -> Sequence[Sequence[object]]:
        """Fetch all rows for the last query."""


class ConnectionLike(Protocol):
    """Subset of DB connection behavior required by harvest."""

    def cursor(self) -> AbstractContextManager[CursorLike]:
        """Return a context-manageable cursor."""


class CheckedHarvestColumn(BaseModel):
    """Preflight status for one required harvest column."""

    model_config = ConfigDict(extra="forbid")

    table: Literal["traces", "validations"]
    column: str = Field(min_length=1)
    qualified_name: str = Field(min_length=1)
    expected_type: str = Field(min_length=1)
    present: bool


class HarvestPreflight(BaseModel):
    """Schema preflight result captured before any trace rows are read."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["passed"] = "passed"
    checked_columns: list[CheckedHarvestColumn]


class HarvestSelectionPolicy(BaseModel):
    """Deterministic trace selection policy stored in the manifest."""

    model_config = ConfigDict(extra="forbid")

    version: Literal["neon-trace-selection-v1"] = HARVEST_SELECTION_POLICY_VERSION
    name: HarvestSelectionName
    limit: int = Field(ge=1)
    order_by: list[str]
    source_table: Literal["traces"] = "traces"


class SelectedTrace(BaseModel):
    """One trace selected from Neon for a later normalization harvest pass."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(min_length=1)
    created_at: datetime


class HarvestSelectionManifest(BaseModel):
    """Machine-readable manifest for a deterministic real-trace selection."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["prism_calibration.harvest_selection"] = HARVEST_MANIFEST_KIND
    schema_version: Literal["1.0"] = HARVEST_SCHEMA_VERSION
    manifest_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    preflight: HarvestPreflight
    selection_policy: HarvestSelectionPolicy
    row_count: int = Field(ge=0)
    selected_trace_ids: list[str]
    selected_traces: list[SelectedTrace]


@dataclass(frozen=True)
class HarvestRunResult:
    """Result returned by a harvest preflight or selection run."""

    root: Path
    status: Literal["preflight_passed", "selected"]
    preflight: HarvestPreflight
    manifest: HarvestSelectionManifest | None = None
    manifest_path: Path | None = None


def _canonical_json(payload: dict[str, object]) -> bytes:
    """Return compact canonical JSON bytes for stable manifest IDs."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_hex(payload: bytes) -> str:
    """Return a SHA-256 hex digest."""
    return hashlib.sha256(payload).hexdigest()


def _read_dotenv_database_url(dotenv_path: Path) -> str | None:
    """Read only DATABASE_URL from a local dotenv file without logging it."""
    if not dotenv_path.is_file():
        return None
    try:
        lines = dotenv_path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise HarvestDatabaseError(
            f"Unable to read {dotenv_path} while looking for DATABASE_URL: {error}"
        ) from error

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw_value = stripped.split("=", 1)
        if key.strip() != "DATABASE_URL":
            continue
        value = raw_value.strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        return value
    return None


def database_url_from_environment(*, cwd: Path | None = None) -> str:
    """Return DATABASE_URL from the process environment or local ``.env``."""
    env_value = os.environ.get("DATABASE_URL")
    if env_value:
        return env_value

    search_root = cwd or Path.cwd()
    dotenv_value = _read_dotenv_database_url(search_root / ".env")
    if dotenv_value:
        return dotenv_value

    raise HarvestDatabaseError(
        "DATABASE_URL is not set. Export DATABASE_URL or add it to .env before "
        "running `uv run python -m prism_calibration.cli harvest`."
    )


def _existing_schema_columns(connection: ConnectionLike) -> set[tuple[str, str]]:
    """Return existing public traces/validations columns from information_schema."""
    with connection.cursor() as cursor:
        cursor.execute(_COLUMN_PREFLIGHT_SQL)
        rows = cursor.fetchall()
    return {(str(row[0]), str(row[1])) for row in rows}


def _checked_columns(existing_columns: set[tuple[str, str]]) -> list[CheckedHarvestColumn]:
    """Return preflight checks in required-column order."""
    checked: list[CheckedHarvestColumn] = []
    for required in REQUIRED_HARVEST_COLUMNS:
        present = (required.table, required.column) in existing_columns
        checked.append(
            CheckedHarvestColumn(
                table=required.table,
                column=required.column,
                qualified_name=required.qualified_name,
                expected_type=required.migration_type,
                present=present,
            )
        )
    return checked


def _format_schema_error(checked_columns: list[CheckedHarvestColumn]) -> str:
    """Format a migration-style schema preflight error."""
    missing = [column for column in checked_columns if not column.present]
    missing_names = ", ".join(column.qualified_name for column in missing)
    migration_lines = [
        f"ALTER TABLE {column.table} ADD COLUMN {column.column} {column.expected_type};"
        for column in missing
    ]
    checked_lines = [
        f"- {column.qualified_name} ({column.expected_type}): "
        f"{'present' if column.present else 'missing'}"
        for column in checked_columns
    ]
    return "\n".join(
        [
            "Neon schema preflight failed. Missing required harvest columns: "
            f"{missing_names}",
            "Apply a Neon migration before harvesting, for example:",
            *migration_lines,
            "Checked columns:",
            *checked_lines,
        ]
    )


def run_schema_preflight(connection: ConnectionLike) -> HarvestPreflight:
    """Verify required Neon harvest columns exist before reading trace rows."""
    existing_columns = _existing_schema_columns(connection)
    checked_columns = _checked_columns(existing_columns)
    if any(not column.present for column in checked_columns):
        raise HarvestSchemaError(_format_schema_error(checked_columns))
    return HarvestPreflight(checked_columns=checked_columns)


def _selection_policy(selection: HarvestSelectionName, *, limit: int) -> HarvestSelectionPolicy:
    """Return the deterministic trace selection policy for a CLI request."""
    if limit < 1:
        raise HarvestSelectionError("--limit must be at least 1 for harvest selection")
    order_by = _RECENT_ORDER_BY if selection == "recent" else _OLDEST_ORDER_BY
    return HarvestSelectionPolicy(name=selection, limit=limit, order_by=order_by)


def _selection_sql(selection: HarvestSelectionName) -> str:
    """Return deterministic SQL for trace selection."""
    order_by = _SELECTION_SQL_ORDER_BY[selection]
    return f"""
SELECT t.trace_id::text, t.created_at
FROM public.traces AS t
ORDER BY {order_by}
LIMIT %s
"""


def _coerce_datetime(value: object, *, field_name: str) -> datetime:
    """Coerce a DB timestamp value into a timezone-aware datetime."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as error:
            raise HarvestSelectionError(
                f"Unable to parse {field_name} timestamp '{value}' from Neon"
            ) from error
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed
    raise HarvestSelectionError(
        f"Unable to parse {field_name} timestamp from Neon value of type "
        f"{type(value).__name__}"
    )


def select_traces(
    connection: ConnectionLike,
    *,
    limit: int,
    selection: HarvestSelectionName,
) -> tuple[SelectedTrace, ...]:
    """Select an ordered trace set from Neon using a deterministic policy."""
    with connection.cursor() as cursor:
        cursor.execute(_selection_sql(selection), (limit,))
        rows = cursor.fetchall()

    selected: list[SelectedTrace] = []
    for row in rows:
        if len(row) < 2:
            raise HarvestSelectionError(
                "Trace selection query returned fewer columns than expected"
            )
        selected.append(
            SelectedTrace(
                trace_id=str(row[0]),
                created_at=_coerce_datetime(row[1], field_name="traces.created_at"),
            )
        )
    return tuple(selected)


def _manifest_identity_payload(
    *,
    preflight: HarvestPreflight,
    selection_policy: HarvestSelectionPolicy,
    selected_traces: tuple[SelectedTrace, ...],
) -> dict[str, object]:
    """Return stable manifest identity payload excluding manifest_id."""
    return {
        "kind": HARVEST_MANIFEST_KIND,
        "schema_version": HARVEST_SCHEMA_VERSION,
        "preflight": preflight.model_dump(mode="json"),
        "selection_policy": selection_policy.model_dump(mode="json"),
        "row_count": len(selected_traces),
        "selected_trace_ids": [trace.trace_id for trace in selected_traces],
        "selected_traces": [
            trace.model_dump(mode="json") for trace in selected_traces
        ],
    }


def build_harvest_manifest(
    *,
    preflight: HarvestPreflight,
    selection_policy: HarvestSelectionPolicy,
    selected_traces: tuple[SelectedTrace, ...],
) -> HarvestSelectionManifest:
    """Build a deterministic harvest selection manifest."""
    payload = _manifest_identity_payload(
        preflight=preflight,
        selection_policy=selection_policy,
        selected_traces=selected_traces,
    )
    manifest_id = _sha256_hex(_canonical_json(payload))
    return HarvestSelectionManifest(
        manifest_id=manifest_id,
        preflight=preflight,
        selection_policy=selection_policy,
        row_count=len(selected_traces),
        selected_trace_ids=[trace.trace_id for trace in selected_traces],
        selected_traces=list(selected_traces),
    )


def _manifest_bytes(manifest: HarvestSelectionManifest) -> bytes:
    """Return deterministic, human-readable harvest manifest JSON bytes."""
    payload = manifest.model_dump(mode="json")
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_harvest_manifest(root: Path, manifest: HarvestSelectionManifest) -> Path:
    """Write a harvest selection manifest and return its path."""
    manifest_dir = root / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"harvest-selection-{manifest.manifest_id}.json"
    manifest_path.write_bytes(_manifest_bytes(manifest))
    return manifest_path


def run_harvest(
    *,
    root: Path,
    connection: ConnectionLike,
    limit: int,
    selection: HarvestSelectionName,
    preflight_only: bool,
) -> HarvestRunResult:
    """Run harvest schema preflight and optionally deterministic trace selection."""
    layout = bootstrap_corpus_root(root)
    preflight = run_schema_preflight(connection)
    if preflight_only:
        return HarvestRunResult(
            root=layout.root,
            status="preflight_passed",
            preflight=preflight,
        )

    selection_policy = _selection_policy(selection, limit=limit)
    selected_traces = select_traces(connection, limit=limit, selection=selection)
    manifest = build_harvest_manifest(
        preflight=preflight,
        selection_policy=selection_policy,
        selected_traces=selected_traces,
    )
    manifest_path = write_harvest_manifest(layout.root, manifest)
    return HarvestRunResult(
        root=layout.root,
        status="selected",
        preflight=preflight,
        manifest=manifest,
        manifest_path=manifest_path,
    )


def run_harvest_from_environment(
    *,
    root: Path,
    limit: int,
    selection: HarvestSelectionName,
    preflight_only: bool,
) -> HarvestRunResult:
    """Run harvest against Neon using DATABASE_URL from env or local dotenv."""
    dsn = database_url_from_environment()
    try:
        import psycopg
    except ImportError as error:
        raise HarvestDatabaseError(
            "psycopg is required for Neon harvest; run `uv sync --all-packages`."
        ) from error

    try:
        with psycopg.connect(dsn) as connection:
            return run_harvest(
                root=root,
                connection=cast(ConnectionLike, connection),
                limit=limit,
                selection=selection,
                preflight_only=preflight_only,
            )
    except psycopg.Error as error:
        raise HarvestDatabaseError(
            f"Unable to read Neon for harvest preflight/selection: {error}"
        ) from error


def harvest_summary(result: HarvestRunResult) -> dict[str, object]:
    """Return machine-readable CLI output for a harvest run."""
    payload: dict[str, object] = {
        "authority": "local",
        "preflight": result.preflight.model_dump(mode="json"),
        "root": str(result.root),
        "status": result.status,
    }
    if result.manifest is not None and result.manifest_path is not None:
        payload.update(
            {
                "manifest_id": result.manifest.manifest_id,
                "manifest_path": str(result.manifest_path),
                "row_count": result.manifest.row_count,
                "selected_trace_ids": result.manifest.selected_trace_ids,
                "selection_policy": result.manifest.selection_policy.model_dump(
                    mode="json"
                ),
            }
        )
    return payload


def parse_selection(value: str) -> HarvestSelectionName:
    """Parse a harvest selection value from argparse."""
    if value in ("recent", "oldest"):
        return cast(HarvestSelectionName, value)
    raise HarvestSelectionError(
        f"Unknown harvest selection '{value}'. Expected one of: recent, oldest"
    )
