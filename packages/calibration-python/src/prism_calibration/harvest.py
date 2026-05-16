"""Neon harvest preflight and deterministic trace selection."""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from collections.abc import Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol, cast

from prism_schemas.trace import TradingR1Trace
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from prism_calibration.layout import bootstrap_corpus_root
from prism_calibration.models import (
    CalibrationRow,
    CorpusProvenance,
    HarvestedTraceProvenance,
    HarvestValidationProvenance,
    ReviewState,
    SplitMetadata,
)
from prism_calibration.splits import (
    ASSIGNED_AT,
    SPLIT_POLICY,
    split_for_lineage,
    write_row,
)

HARVEST_SCHEMA_VERSION: Literal["1.0"] = "1.0"
HARVEST_MANIFEST_KIND: Literal["prism_calibration.harvest_selection"] = (
    "prism_calibration.harvest_selection"
)
HARVEST_RUN_MANIFEST_KIND: Literal["prism_calibration.harvest_run"] = (
    "prism_calibration.harvest_run"
)
HARVEST_SELECTION_POLICY_VERSION: Literal["neon-trace-selection-v1"] = (
    "neon-trace-selection-v1"
)
HARVEST_SPLIT_SEED = 42
DEFAULT_IPFS_GATEWAY = "https://gateway.pinata.cloud/ipfs"
HarvestSelectionName = Literal["recent", "oldest"]
HarvestFailureReason = Literal[
    "missing_cid",
    "ipfs_unreachable",
    "invalid_json",
    "malformed_schema",
    "identity_mismatch",
    "hash_mismatch",
]
HarvestExitStatus = Literal["success", "partial", "failure"]


class HarvestDatabaseError(ValueError):
    """Raised when the harvest command cannot connect to or query Neon."""


class HarvestSchemaError(ValueError):
    """Raised when Neon schema preflight finds missing harvest columns."""


class HarvestSelectionError(ValueError):
    """Raised when deterministic trace selection cannot be completed."""


class HarvestIpfsError(ValueError):
    """Raised when an IPFS payload cannot be reached through the gateway."""


class HarvestInvalidPayloadError(ValueError):
    """Raised when IPFS returns content that is not a JSON object."""


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


class IpfsJsonFetcher(Protocol):
    """Synchronous JSON fetcher used to retrieve trace payloads from IPFS."""

    def fetch_json(self, cid: str) -> dict[str, Any]:
        """Fetch one JSON object by bare CID."""


class HttpIpfsFetcher:
    """IPFS JSON fetcher using the repository's httpx gateway pattern."""

    def __init__(
        self,
        *,
        gateway_base_url: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        """Initialize a public-gateway IPFS fetcher."""
        configured_gateway = gateway_base_url or os.environ.get(
            "PRISM_IPFS_GATEWAY", DEFAULT_IPFS_GATEWAY
        )
        self.gateway_base_url = configured_gateway.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def fetch_json(self, cid: str) -> dict[str, Any]:
        """Fetch one JSON object by CID from the configured IPFS gateway."""
        try:
            import httpx
        except ImportError as error:
            raise HarvestIpfsError(
                "httpx is required for IPFS harvest; run `uv sync --all-packages`."
            ) from error

        url = f"{self.gateway_base_url}/{cid}"
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise HarvestIpfsError(f"IPFS gateway request failed for CID {cid}: {error}") from error

        try:
            payload = response.json()
        except ValueError as error:
            raise HarvestInvalidPayloadError(
                f"IPFS gateway returned non-JSON payload for CID {cid}: {error}"
            ) from error
        if not isinstance(payload, dict):
            raise HarvestInvalidPayloadError(
                f"IPFS gateway returned {type(payload).__name__}, expected JSON object"
            )
        return cast(dict[str, Any], payload)


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


class HarvestValidationContext(BaseModel):
    """Latest validation metadata selected alongside one trace row."""

    model_config = ConfigDict(extra="forbid")

    request_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    sentinel_agent_id: int
    verdict_score: int = Field(ge=0, le=100)
    response_uri: str | None = None
    requester_address: str | None = None
    tx_hash: str | None = None
    created_at: datetime | None = None


class HarvestTraceRecord(BaseModel):
    """A selected Neon trace row with enough metadata to build a corpus row."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(min_length=1)
    agent_id: int
    market_id: str = Field(min_length=1)
    ipfs_cid: str | None = None
    content_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    tx_hash: str | None = None
    created_at: datetime
    validation: HarvestValidationContext | None = None


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


class HarvestWrittenRow(BaseModel):
    """Summary of one successfully written harvested row."""

    model_config = ConfigDict(extra="forbid")

    row_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    validation_status: Literal["validated", "unvalidated"]


class HarvestQuarantineRecord(BaseModel):
    """One reason-coded harvest failure record written to quarantine."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["prism_calibration.harvest_quarantine"] = (
        "prism_calibration.harvest_quarantine"
    )
    schema_version: Literal["1.0"] = HARVEST_SCHEMA_VERSION
    run_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    agent_id: int | None = None
    market_id: str | None = None
    cid: str | None = None
    db_content_hash: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    source_table: Literal["traces"] = "traces"
    reason_code: HarvestFailureReason
    details: str = Field(min_length=1)
    validation: HarvestValidationContext | None = None
    created_at: datetime


class HarvestRunCounts(BaseModel):
    """Per-run success and quarantine counts."""

    model_config = ConfigDict(extra="forbid")

    selected: int = Field(ge=0)
    succeeded: int = Field(ge=0)
    quarantined: int = Field(ge=0)


class HarvestRunManifest(BaseModel):
    """Machine-readable manifest for a completed normalization harvest."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["prism_calibration.harvest_run"] = HARVEST_RUN_MANIFEST_KIND
    schema_version: Literal["1.0"] = HARVEST_SCHEMA_VERSION
    run_id: str = Field(min_length=1)
    created_at: datetime
    exit_status: HarvestExitStatus
    preflight: HarvestPreflight
    selection_policy: HarvestSelectionPolicy
    selection_manifest_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    selected_trace_ids: list[str]
    counts: HarvestRunCounts
    status_counts: dict[str, int]
    reason_counts: dict[str, int]
    rows: list[HarvestWrittenRow]
    quarantined: list[HarvestQuarantineRecord]


@dataclass(frozen=True)
class HarvestRunResult:
    """Result returned by a harvest preflight or selection run."""

    root: Path
    status: Literal["preflight_passed", "selected", "completed"]
    preflight: HarvestPreflight
    manifest: HarvestSelectionManifest | None = None
    manifest_path: Path | None = None
    run_id: str | None = None
    run_manifest: HarvestRunManifest | None = None
    run_manifest_path: Path | None = None
    written_rows: tuple[HarvestWrittenRow, ...] = ()
    quarantine_records: tuple[HarvestQuarantineRecord, ...] = ()
    quarantine_paths: tuple[Path, ...] = ()
    exit_status: HarvestExitStatus | None = None


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


def _harvest_records_sql(selection: HarvestSelectionName) -> str:
    """Return deterministic SQL for full trace/validation harvest records."""
    order_by = _SELECTION_SQL_ORDER_BY[selection]
    return f"""
SELECT
  t.trace_id::text,
  t.agent_id,
  t.market_id,
  t.ipfs_cid,
  encode(t.content_hash, 'hex') AS content_hash,
  t.tx_hash,
  t.created_at,
  encode(v.request_hash, 'hex') AS request_hash,
  v.sentinel_agent_id,
  v.verdict_score,
  v.response_uri,
  v.requester_address,
  v.tx_hash AS validation_tx_hash,
  v.created_at AS validation_created_at
FROM public.traces AS t
LEFT JOIN LATERAL (
  SELECT
    request_hash,
    sentinel_agent_id,
    verdict_score,
    response_uri,
    requester_address,
    tx_hash,
    created_at
  FROM public.validations AS candidate
  WHERE candidate.trace_id = t.trace_id
  ORDER BY candidate.created_at DESC, candidate.request_hash ASC
  LIMIT 1
) AS v ON TRUE
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


def _coerce_optional_datetime(value: object, *, field_name: str) -> datetime | None:
    """Coerce an optional DB timestamp value into a timezone-aware datetime."""
    if value is None:
        return None
    return _coerce_datetime(value, field_name=field_name)


def _coerce_int(value: object, *, field_name: str) -> int:
    """Coerce a DB integer-like value into ``int``."""
    if isinstance(value, bool):
        raise HarvestSelectionError(f"{field_name} from Neon must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError as error:
            raise HarvestSelectionError(
                f"Unable to parse {field_name} integer '{value}' from Neon"
            ) from error
    raise HarvestSelectionError(
        f"Unable to parse {field_name} integer from Neon value of type "
        f"{type(value).__name__}"
    )


def _coerce_optional_int(value: object, *, field_name: str) -> int | None:
    """Coerce an optional DB integer-like value into ``int``."""
    if value is None:
        return None
    return _coerce_int(value, field_name=field_name)


def _coerce_optional_str(value: object) -> str | None:
    """Return a stripped string or ``None`` for DB null/empty values."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_hash_hex(value: object, *, field_name: str) -> str:
    """Coerce a DB bytea/hex value into lowercase 64-char hex."""
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, memoryview):
        return value.tobytes().hex()
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized.startswith("\\x"):
            normalized = normalized[2:]
        if normalized.startswith("0x"):
            normalized = normalized[2:]
        return normalized
    raise HarvestSelectionError(
        f"Unable to parse {field_name} hash from Neon value of type "
        f"{type(value).__name__}"
    )


def _coerce_optional_hash_hex(value: object, *, field_name: str) -> str | None:
    """Coerce an optional DB bytea/hex value into lowercase hex."""
    if value is None:
        return None
    return _coerce_hash_hex(value, field_name=field_name)


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


def _validation_context_from_row(row: Sequence[object]) -> HarvestValidationContext | None:
    """Build optional validation context from a full harvest SQL row."""
    if len(row) < 14 or row[7] is None:
        return None

    request_hash = _coerce_hash_hex(row[7], field_name="validations.request_hash")
    sentinel_agent_id = _coerce_int(row[8], field_name="validations.sentinel_agent_id")
    verdict_score = _coerce_int(row[9], field_name="validations.verdict_score")
    return HarvestValidationContext(
        request_hash=request_hash,
        sentinel_agent_id=sentinel_agent_id,
        verdict_score=verdict_score,
        response_uri=_coerce_optional_str(row[10]),
        requester_address=_coerce_optional_str(row[11]),
        tx_hash=_coerce_optional_str(row[12]),
        created_at=_coerce_optional_datetime(
            row[13], field_name="validations.created_at"
        ),
    )


def _trace_record_from_row(row: Sequence[object]) -> HarvestTraceRecord:
    """Build a full harvest trace record from one DB result row."""
    if len(row) < 7:
        raise HarvestSelectionError(
            "Harvest trace query returned fewer columns than expected"
        )
    return HarvestTraceRecord(
        trace_id=str(row[0]),
        agent_id=_coerce_int(row[1], field_name="traces.agent_id"),
        market_id=str(row[2]),
        ipfs_cid=_coerce_optional_str(row[3]),
        content_hash=_coerce_hash_hex(row[4], field_name="traces.content_hash"),
        tx_hash=_coerce_optional_str(row[5]),
        created_at=_coerce_datetime(row[6], field_name="traces.created_at"),
        validation=_validation_context_from_row(row),
    )


def select_harvest_records(
    connection: ConnectionLike,
    *,
    limit: int,
    selection: HarvestSelectionName,
) -> tuple[HarvestTraceRecord, ...]:
    """Select full Neon trace records for normalization and provenance export."""
    with connection.cursor() as cursor:
        cursor.execute(_harvest_records_sql(selection), (limit,))
        rows = cursor.fetchall()
    return tuple(_trace_record_from_row(row) for row in rows)


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


def _model_bytes(model: BaseModel) -> bytes:
    """Return deterministic, human-readable JSON bytes for a Pydantic model."""
    payload = model.model_dump(mode="json")
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _run_id_for_manifest(manifest: HarvestSelectionManifest) -> str:
    """Return a stable harvest run identifier for one selected trace set."""
    return f"harvest-{manifest.manifest_id[:16]}"


def _normalize_cid(value: str | None) -> str | None:
    """Return a bare CID from a DB CID/URI value, or ``None`` for missing CIDs."""
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.startswith("ipfs://"):
        normalized = normalized.removeprefix("ipfs://")
    if "/ipfs/" in normalized:
        normalized = normalized.rsplit("/ipfs/", maxsplit=1)[-1]
    normalized = normalized.strip("/")
    return normalized or None


def _cid_from_uri(value: str | None) -> str | None:
    """Return a CID from an IPFS URI/gateway URL when one is present."""
    return _normalize_cid(value)


def _selected_trace_from_record(record: HarvestTraceRecord) -> SelectedTrace:
    """Return selection-manifest trace metadata from a full harvest record."""
    return SelectedTrace(trace_id=record.trace_id, created_at=record.created_at)


def _validation_provenance(record: HarvestTraceRecord) -> HarvestValidationProvenance:
    """Return explicit validated/unvalidated provenance for one trace record."""
    if record.validation is None:
        return HarvestValidationProvenance(status="unvalidated")
    return HarvestValidationProvenance(
        status="validated",
        request_hash=record.validation.request_hash,
        sentinel_agent_id=record.validation.sentinel_agent_id,
        verdict_score=record.validation.verdict_score,
        response_uri=record.validation.response_uri,
        response_cid=_cid_from_uri(record.validation.response_uri),
        requester_address=record.validation.requester_address,
        tx_hash=record.validation.tx_hash,
        created_at=record.validation.created_at,
    )


def _identity_mismatch_details(trace: TradingR1Trace, record: HarvestTraceRecord) -> str | None:
    """Return mismatch details if DB and normalized payload identity diverge."""
    mismatches: list[str] = []
    if trace.trace_id != record.trace_id:
        mismatches.append(f"trace_id payload={trace.trace_id} db={record.trace_id}")
    if trace.market_id != record.market_id:
        mismatches.append(f"market_id payload={trace.market_id} db={record.market_id}")
    if not mismatches:
        return None
    return "; ".join(mismatches)


def _quarantine_record(
    *,
    run_id: str,
    record: HarvestTraceRecord,
    cid: str | None,
    reason_code: HarvestFailureReason,
    details: str,
    created_at: datetime,
) -> HarvestQuarantineRecord:
    """Build one reason-coded quarantine record for a failed trace."""
    return HarvestQuarantineRecord(
        run_id=run_id,
        trace_id=record.trace_id,
        agent_id=record.agent_id,
        market_id=record.market_id,
        cid=cid,
        db_content_hash=record.content_hash,
        reason_code=reason_code,
        details=details,
        validation=record.validation,
        created_at=created_at,
    )


def _quarantine_path(root: Path, quarantine: HarvestQuarantineRecord) -> Path:
    """Return the deterministic quarantine file path for one failed trace."""
    safe_trace_id = "".join(
        char if char.isalnum() or char in ("-", "_") else "-"
        for char in quarantine.trace_id
    )
    return (
        root
        / "quarantine"
        / f"{quarantine.run_id}-{safe_trace_id}-{quarantine.reason_code}.json"
    )


def write_quarantine_record(root: Path, quarantine: HarvestQuarantineRecord) -> Path:
    """Write a harvest quarantine record and return its path."""
    path = _quarantine_path(root, quarantine)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_model_bytes(quarantine))
    return path


def _calibration_row_from_trace(
    *,
    run_id: str,
    record: HarvestTraceRecord,
    cid: str,
    trace: TradingR1Trace,
    normalized_hash: str,
) -> CalibrationRow:
    """Build a canonical real-source calibration row from a normalized trace."""
    row_id = f"real-{trace.trace_id}"
    lineage_id = f"real-trace-{trace.trace_id}"
    validation = _validation_provenance(record)
    split_name = split_for_lineage(lineage_id, seed=HARVEST_SPLIT_SEED)
    return CalibrationRow(
        row_id=row_id,
        trace=trace,
        provenance=CorpusProvenance(
            source_type="real",
            source_ref=f"neon:traces/{record.trace_id}",
            run_id=run_id,
            lineage_id=lineage_id,
            content_hash=normalized_hash,
            created_at=record.created_at,
            harvested_trace=HarvestedTraceProvenance(
                trace_id=record.trace_id,
                agent_id=record.agent_id,
                market_id=record.market_id,
                ipfs_cid=cid,
                ipfs_uri=f"ipfs://{cid}",
                db_content_hash=record.content_hash,
                normalized_content_hash=normalized_hash,
                trace_tx_hash=record.tx_hash,
                db_created_at=record.created_at,
                payload_created_at=trace.created_at,
            ),
            validation=validation,
        ),
        review=ReviewState(
            status="unreviewed",
            rubric_version="prism-calibration-v1",
            failure_tags=[],
            notes=f"Harvested real trace with {validation.status} validation status.",
        ),
        split=SplitMetadata(
            name=split_name,
            policy=SPLIT_POLICY,
            seed=HARVEST_SPLIT_SEED,
            assigned_at=ASSIGNED_AT,
        ),
    )


def _write_harvested_row(root: Path, row: CalibrationRow) -> Path:
    """Write one harvested calibration row under the private rows directory."""
    row_path = root / "rows" / f"{row.row_id}.json"
    row_path.parent.mkdir(parents=True, exist_ok=True)
    write_row(row_path, row)
    return row_path


def _fetch_trace_payload(fetcher: IpfsJsonFetcher, cid: str) -> dict[str, Any]:
    """Fetch a trace payload and normalize fetcher exceptions to harvest errors."""
    try:
        return fetcher.fetch_json(cid)
    except HarvestInvalidPayloadError:
        raise
    except HarvestIpfsError:
        raise
    except (OSError, KeyError) as error:
        raise HarvestIpfsError(f"Unable to fetch IPFS CID {cid}: {error}") from error


def _process_harvest_record(
    *,
    root: Path,
    run_id: str,
    record: HarvestTraceRecord,
    fetcher: IpfsJsonFetcher,
    created_at: datetime,
) -> tuple[HarvestWrittenRow | None, HarvestQuarantineRecord | None, Path | None]:
    """Normalize one selected trace into a row or quarantine failure."""
    cid = _normalize_cid(record.ipfs_cid)
    if cid is None:
        return (
            None,
            _quarantine_record(
                run_id=run_id,
                record=record,
                cid=None,
                reason_code="missing_cid",
                details="traces.ipfs_cid is empty or null",
                created_at=created_at,
            ),
            None,
        )

    try:
        payload = _fetch_trace_payload(fetcher, cid)
    except HarvestInvalidPayloadError as error:
        return (
            None,
            _quarantine_record(
                run_id=run_id,
                record=record,
                cid=cid,
                reason_code="invalid_json",
                details=str(error),
                created_at=created_at,
            ),
            None,
        )
    except HarvestIpfsError as error:
        return (
            None,
            _quarantine_record(
                run_id=run_id,
                record=record,
                cid=cid,
                reason_code="ipfs_unreachable",
                details=str(error),
                created_at=created_at,
            ),
            None,
        )

    try:
        trace = TradingR1Trace.model_validate(payload)
    except ValidationError as error:
        return (
            None,
            _quarantine_record(
                run_id=run_id,
                record=record,
                cid=cid,
                reason_code="malformed_schema",
                details="; ".join(
                    f"{'.'.join(str(part) for part in detail.get('loc', ()))}: "
                    f"{detail.get('msg', 'Invalid value')}"
                    for detail in error.errors()
                ),
                created_at=created_at,
            ),
            None,
        )

    identity_details = _identity_mismatch_details(trace, record)
    if identity_details is not None:
        return (
            None,
            _quarantine_record(
                run_id=run_id,
                record=record,
                cid=cid,
                reason_code="identity_mismatch",
                details=identity_details,
                created_at=created_at,
            ),
            None,
        )

    normalized_hash = trace.content_hash().hex()
    if normalized_hash.lower() != record.content_hash.lower():
        return (
            None,
            _quarantine_record(
                run_id=run_id,
                record=record,
                cid=cid,
                reason_code="hash_mismatch",
                details=(
                    "normalized trace content hash does not match Neon content_hash: "
                    f"normalized={normalized_hash} db={record.content_hash}"
                ),
                created_at=created_at,
            ),
            None,
        )

    try:
        row = _calibration_row_from_trace(
            run_id=run_id,
            record=record,
            cid=cid,
            trace=trace,
            normalized_hash=normalized_hash,
        )
    except ValidationError as error:
        return (
            None,
            _quarantine_record(
                run_id=run_id,
                record=record,
                cid=cid,
                reason_code="malformed_schema",
                details="; ".join(
                    f"{'.'.join(str(part) for part in detail.get('loc', ()))}: "
                    f"{detail.get('msg', 'Invalid value')}"
                    for detail in error.errors()
                ),
                created_at=created_at,
            ),
            None,
        )

    row_path = _write_harvested_row(root, row)
    validation_status: Literal["validated", "unvalidated"] = (
        "validated" if record.validation is not None else "unvalidated"
    )
    return (
        HarvestWrittenRow(
            row_id=row.row_id,
            trace_id=trace.trace_id,
            path=str(row_path),
            content_hash=normalized_hash,
            validation_status=validation_status,
        ),
        None,
        row_path,
    )


def _exit_status(*, written_count: int, quarantine_count: int) -> HarvestExitStatus:
    """Return an actionable run status from success and quarantine counts."""
    if quarantine_count == 0:
        return "success"
    if written_count > 0:
        return "partial"
    return "failure"


def _run_counts(
    *,
    selected_count: int,
    written_count: int,
    quarantine_count: int,
) -> HarvestRunCounts:
    """Build run counts for manifests and summaries."""
    return HarvestRunCounts(
        selected=selected_count,
        succeeded=written_count,
        quarantined=quarantine_count,
    )


def build_harvest_run_manifest(
    *,
    run_id: str,
    created_at: datetime,
    preflight: HarvestPreflight,
    selection_manifest: HarvestSelectionManifest,
    written_rows: tuple[HarvestWrittenRow, ...],
    quarantine_records: tuple[HarvestQuarantineRecord, ...],
) -> HarvestRunManifest:
    """Build a machine-readable manifest for a completed harvest run."""
    status_counts = Counter(row.validation_status for row in written_rows)
    reason_counts = Counter(record.reason_code for record in quarantine_records)
    exit_status = _exit_status(
        written_count=len(written_rows),
        quarantine_count=len(quarantine_records),
    )
    return HarvestRunManifest(
        run_id=run_id,
        created_at=created_at,
        exit_status=exit_status,
        preflight=preflight,
        selection_policy=selection_manifest.selection_policy,
        selection_manifest_id=selection_manifest.manifest_id,
        selected_trace_ids=selection_manifest.selected_trace_ids,
        counts=_run_counts(
            selected_count=selection_manifest.row_count,
            written_count=len(written_rows),
            quarantine_count=len(quarantine_records),
        ),
        status_counts=dict(sorted(status_counts.items())),
        reason_counts=dict(sorted(reason_counts.items())),
        rows=list(written_rows),
        quarantined=list(quarantine_records),
    )


def write_harvest_run_manifest(root: Path, manifest: HarvestRunManifest) -> Path:
    """Write a completed harvest run manifest and return its path."""
    manifest_dir = root / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"harvest-run-{manifest.run_id}.json"
    manifest_path.write_bytes(_model_bytes(manifest))
    return manifest_path


def process_harvest_records(
    *,
    root: Path,
    run_id: str,
    records: tuple[HarvestTraceRecord, ...],
    fetcher: IpfsJsonFetcher,
    created_at: datetime,
) -> tuple[
    tuple[HarvestWrittenRow, ...],
    tuple[HarvestQuarantineRecord, ...],
    tuple[Path, ...],
]:
    """Process selected records, writing rows or quarantine files while continuing."""
    written_rows: list[HarvestWrittenRow] = []
    quarantine_records: list[HarvestQuarantineRecord] = []
    quarantine_paths: list[Path] = []

    for record in records:
        written, quarantine, _row_path = _process_harvest_record(
            root=root,
            run_id=run_id,
            record=record,
            fetcher=fetcher,
            created_at=created_at,
        )
        if written is not None:
            written_rows.append(written)
        if quarantine is not None:
            quarantine_records.append(quarantine)
            quarantine_paths.append(write_quarantine_record(root, quarantine))

    return (tuple(written_rows), tuple(quarantine_records), tuple(quarantine_paths))


def run_harvest(
    *,
    root: Path,
    connection: ConnectionLike,
    limit: int,
    selection: HarvestSelectionName,
    preflight_only: bool,
    fetcher: IpfsJsonFetcher | None = None,
) -> HarvestRunResult:
    """Run harvest preflight, selection, and optional IPFS normalization."""
    layout = bootstrap_corpus_root(root)
    preflight = run_schema_preflight(connection)
    if preflight_only:
        return HarvestRunResult(
            root=layout.root,
            status="preflight_passed",
            preflight=preflight,
        )

    selection_policy = _selection_policy(selection, limit=limit)
    if fetcher is None:
        selected_traces = select_traces(connection, limit=limit, selection=selection)
    else:
        records = select_harvest_records(connection, limit=limit, selection=selection)
        selected_traces = tuple(_selected_trace_from_record(record) for record in records)
    manifest = build_harvest_manifest(
        preflight=preflight,
        selection_policy=selection_policy,
        selected_traces=selected_traces,
    )
    manifest_path = write_harvest_manifest(layout.root, manifest)
    if fetcher is None:
        return HarvestRunResult(
            root=layout.root,
            status="selected",
            preflight=preflight,
            manifest=manifest,
            manifest_path=manifest_path,
            exit_status="success",
        )

    run_id = _run_id_for_manifest(manifest)
    created_at = datetime.now(tz=UTC)
    written_rows, quarantine_records, quarantine_paths = process_harvest_records(
        root=layout.root,
        run_id=run_id,
        records=records,
        fetcher=fetcher,
        created_at=created_at,
    )
    run_manifest = build_harvest_run_manifest(
        run_id=run_id,
        created_at=created_at,
        preflight=preflight,
        selection_manifest=manifest,
        written_rows=written_rows,
        quarantine_records=quarantine_records,
    )
    run_manifest_path = write_harvest_run_manifest(layout.root, run_manifest)
    return HarvestRunResult(
        root=layout.root,
        status="completed",
        preflight=preflight,
        manifest=manifest,
        manifest_path=manifest_path,
        run_id=run_id,
        run_manifest=run_manifest,
        run_manifest_path=run_manifest_path,
        written_rows=written_rows,
        quarantine_records=quarantine_records,
        quarantine_paths=quarantine_paths,
        exit_status=run_manifest.exit_status,
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
                fetcher=None if preflight_only else HttpIpfsFetcher(),
            )
    except psycopg.Error as error:
        raise HarvestDatabaseError(
            f"Unable to read Neon for harvest preflight/selection: {error}"
        ) from error


def harvest_summary(result: HarvestRunResult) -> dict[str, object]:
    """Return machine-readable CLI output for a harvest run."""
    payload: dict[str, object] = {
        "authority": "local",
        "exit_status": result.exit_status or "success",
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
    if result.run_manifest is not None and result.run_manifest_path is not None:
        payload.update(
            {
                "counts": result.run_manifest.counts.model_dump(mode="json"),
                "harvest_manifest_path": str(result.run_manifest_path),
                "quarantine_paths": [str(path) for path in result.quarantine_paths],
                "reason_counts": result.run_manifest.reason_counts,
                "row_paths": [row.path for row in result.written_rows],
                "run_id": result.run_manifest.run_id,
                "status_counts": result.run_manifest.status_counts,
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
