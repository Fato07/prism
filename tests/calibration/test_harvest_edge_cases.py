"""Harvest edge-case coverage: --limit 0, empty result set, identity_mismatch, invalid_json."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from prism_calibration.harvest import (
    REQUIRED_HARVEST_COLUMNS,
    HarvestInvalidPayloadError,
    HarvestSelectionError,
    harvest_summary,
    run_harvest,
)
from prism_schemas.trace import Evidence, ThesisStep, TradingR1Trace


# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------


class EdgeCursor:
    """Cursor fake for edge-case harvest tests."""

    def __init__(self, connection: EdgeConnection) -> None:
        self.connection = connection
        self._rows: list[tuple[object, ...]] = []

    def __enter__(self) -> EdgeCursor:
        """Enter the fake cursor context manager."""
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """Exit the fake cursor context manager."""

    def execute(self, query: str, params: Sequence[object] | None = None) -> object:
        """Return fake information_schema or selection rows."""
        if "information_schema.columns" in query:
            self._rows = sorted(self.connection.schema_rows)
        elif "FROM public.traces" in query:
            limit = int((params or (0,))[0])
            self._rows = self.connection.selection_rows[:limit]
        else:
            raise AssertionError(f"Unexpected query: {query}")
        return self

    def fetchall(self) -> list[tuple[object, ...]]:
        """Return rows for the last fake query."""
        return list(self._rows)


class EdgeConnection:
    """Connection fake exposing the harvest DB protocol."""

    def __init__(self, selection_rows: list[tuple[object, ...]] | None = None) -> None:
        self.schema_rows = {
            (required.table, required.column) for required in REQUIRED_HARVEST_COLUMNS
        }
        self.selection_rows = selection_rows or []

    def cursor(self) -> EdgeCursor:
        """Return a context-manageable fake cursor."""
        return EdgeCursor(self)


class EdgeIpfsFetcher:
    """IPFS fetcher fake that can raise HarvestInvalidPayloadError or return payloads."""

    def __init__(self, payloads: Mapping[str, dict[str, Any] | Exception]) -> None:
        self.payloads = dict(payloads)
        self.fetched: list[str] = []

    def fetch_json(self, cid: str) -> dict[str, Any]:
        """Return payloads or raise configured exceptions."""
        self.fetched.append(cid)
        payload = self.payloads[cid]
        if isinstance(payload, Exception):
            raise payload
        return payload


def _trace_payload(
    trace_id: str,
    *,
    market_id: str = "polymarket-edge-001",
    agent_id: int = 1,
    created_at: datetime = datetime(2026, 5, 15, 14, 0, tzinfo=UTC),
) -> dict[str, Any]:
    """Return a valid Trading-R1 trace payload."""
    trace = TradingR1Trace(
        trace_id=trace_id,
        agent_id=agent_id,
        market_id=market_id,
        market_question=f"Will edge-case trace {trace_id} validate?",
        thesis=[
            ThesisStep(
                proposition="Edge cases should not break the harvest pipeline.",
                supporting_evidence_ids=[0],
                risk_factors=["An unhandled edge case could abort the run."],
            )
        ],
        evidence=[
            Evidence(
                source="fixture",
                claim="The edge-case payload validates through the shared schema.",
                confidence=0.9,
                timestamp=created_at,
            )
        ],
        raw_probability=0.55,
        volatility_adjustment=0.0,
        final_probability=0.55,
        action="HOLD",
        size_usdc=0.0,
        price_limit=0.5,
        rationale="Edge case test trace.",
        model_family="anthropic-claude",
        model_name="claude-opus-4-7",
        created_at=created_at,
    )
    return trace.model_dump(mode="json")


def _selection_row(
    payload: dict[str, Any],
    *,
    cid: str | None = None,
    db_hash: bytes | None = None,
    db_agent_id: int | None = None,
    db_market_id: str | None = None,
    db_created_at: datetime = datetime(2026, 5, 15, 14, 5, tzinfo=UTC),
) -> tuple[object, ...]:
    """Return one fake DB selection row matching the harvest SQL shape."""
    trace = TradingR1Trace.model_validate(payload)
    return (
        trace.trace_id,
        db_agent_id or trace.agent_id,
        db_market_id or trace.market_id,
        cid or "",
        db_hash or trace.content_hash(),
        None,
        db_created_at,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )


# ---------------------------------------------------------------------------
# --limit 0 edge case
# ---------------------------------------------------------------------------


def test_harvest_limit_zero_raises_selection_error(tmp_path: Path) -> None:
    """A --limit of 0 raises HarvestSelectionError before any DB reads."""
    with pytest.raises(HarvestSelectionError, match="--limit must be at least 1"):
        run_harvest(
            root=tmp_path / "calibration",
            connection=EdgeConnection(),
            limit=0,
            selection="recent",
            preflight_only=False,
        )


# ---------------------------------------------------------------------------
# Empty Neon result set
# ---------------------------------------------------------------------------


def test_harvest_empty_neon_result_set_produces_zero_count_manifest(tmp_path: Path) -> None:
    """When Neon returns zero rows, harvest produces an empty manifest with success status."""
    root = tmp_path / "calibration"
    connection = EdgeConnection(selection_rows=[])

    result = run_harvest(
        root=root,
        connection=connection,
        limit=5,
        selection="recent",
        preflight_only=False,
    )

    assert result.status == "selected"
    assert result.manifest is not None
    assert result.manifest.row_count == 0
    assert result.manifest.selected_trace_ids == []
    assert result.exit_status == "success"

    summary = harvest_summary(result)
    assert summary["exit_status"] == "success"
    assert summary["row_count"] == 0
    assert summary["selected_trace_ids"] == []

    # Manifest file should be written and valid
    assert result.manifest_path is not None
    assert result.manifest_path.exists()
    manifest_payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest_payload["row_count"] == 0


# ---------------------------------------------------------------------------
# identity_mismatch quarantine reason code
# ---------------------------------------------------------------------------


def test_harvest_identity_mismatch_trace_id_quarantines_with_reason_code(
    tmp_path: Path,
) -> None:
    """When payload trace_id differs from DB trace_id, the row is quarantined with identity_mismatch."""
    # Create a valid payload with one trace_id
    payload = _trace_payload("00000000-0000-4000-8000-000000000020")
    # DB row claims a different trace_id
    trace = TradingR1Trace.model_validate(payload)

    # Build a selection row where the DB trace_id differs from the payload
    mismatch_row = (
        "00000000-0000-4000-8000-0000000000FF",  # different trace_id
        trace.agent_id,
        trace.market_id,
        "QmIdentityMismatch",
        trace.content_hash(),
        None,
        datetime(2026, 5, 15, 14, 5, tzinfo=UTC),
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )

    root = tmp_path / "calibration"
    fetcher = EdgeIpfsFetcher({"QmIdentityMismatch": payload})
    result = run_harvest(
        root=root,
        connection=EdgeConnection(selection_rows=[mismatch_row]),
        limit=5,
        selection="recent",
        preflight_only=False,
        fetcher=fetcher,
    )

    summary = harvest_summary(result)
    assert summary["exit_status"] == "failure"
    assert summary["counts"] == {"quarantined": 1, "selected": 1, "succeeded": 0}
    assert summary["reason_counts"] == {"identity_mismatch": 1}
    assert len(summary["quarantine_paths"]) == 1

    quarantine_payload = json.loads(
        Path(summary["quarantine_paths"][0]).read_text(encoding="utf-8")
    )
    assert quarantine_payload["reason_code"] == "identity_mismatch"
    assert "trace_id payload=" in quarantine_payload["details"]
    assert "db=" in quarantine_payload["details"]


def test_harvest_identity_mismatch_market_id_quarantines_with_reason_code(
    tmp_path: Path,
) -> None:
    """When payload market_id differs from DB market_id, the row is quarantined with identity_mismatch."""
    payload = _trace_payload("00000000-0000-4000-8000-000000000021", market_id="market-A")
    # DB row has a different market_id
    row = _selection_row(
        payload,
        cid="QmMarketMismatch",
        db_market_id="market-B",
    )

    root = tmp_path / "calibration"
    fetcher = EdgeIpfsFetcher({"QmMarketMismatch": payload})
    result = run_harvest(
        root=root,
        connection=EdgeConnection(selection_rows=[row]),
        limit=5,
        selection="recent",
        preflight_only=False,
        fetcher=fetcher,
    )

    summary = harvest_summary(result)
    assert summary["reason_counts"] == {"identity_mismatch": 1}

    quarantine_payload = json.loads(
        Path(summary["quarantine_paths"][0]).read_text(encoding="utf-8")
    )
    assert quarantine_payload["reason_code"] == "identity_mismatch"
    assert "market_id payload=" in quarantine_payload["details"]


# ---------------------------------------------------------------------------
# invalid_json quarantine reason code
# ---------------------------------------------------------------------------


def test_harvest_invalid_json_non_dict_payload_quarantines_with_reason_code(
    tmp_path: Path,
) -> None:
    """When IPFS returns a JSON array instead of an object, the row is quarantined with invalid_json."""
    payload = _trace_payload("00000000-0000-4000-8000-000000000030")
    row = _selection_row(payload, cid="QmInvalidJsonArray")

    root = tmp_path / "calibration"
    # fetcher raises HarvestInvalidPayloadError for non-dict JSON
    fetcher = EdgeIpfsFetcher(
        {
            "QmInvalidJsonArray": HarvestInvalidPayloadError(
                "IPFS gateway returned list, expected JSON object"
            ),
        }
    )
    result = run_harvest(
        root=root,
        connection=EdgeConnection(selection_rows=[row]),
        limit=5,
        selection="recent",
        preflight_only=False,
        fetcher=fetcher,
    )

    summary = harvest_summary(result)
    assert summary["exit_status"] == "failure"
    assert summary["counts"] == {"quarantined": 1, "selected": 1, "succeeded": 0}
    assert summary["reason_counts"] == {"invalid_json": 1}

    quarantine_payload = json.loads(
        Path(summary["quarantine_paths"][0]).read_text(encoding="utf-8")
    )
    assert quarantine_payload["reason_code"] == "invalid_json"
    assert "expected JSON object" in quarantine_payload["details"]


def test_harvest_invalid_json_non_json_payload_quarantines_with_reason_code(
    tmp_path: Path,
) -> None:
    """When IPFS returns non-JSON content, the row is quarantined with invalid_json."""
    payload = _trace_payload("00000000-0000-4000-8000-000000000031")
    row = _selection_row(payload, cid="QmNotJson")

    root = tmp_path / "calibration"
    fetcher = EdgeIpfsFetcher(
        {
            "QmNotJson": HarvestInvalidPayloadError(
                "IPFS gateway returned non-JSON payload for CID QmNotJson: "
                "Expecting value: line 1 column 1 (char 0)"
            ),
        }
    )
    result = run_harvest(
        root=root,
        connection=EdgeConnection(selection_rows=[row]),
        limit=5,
        selection="recent",
        preflight_only=False,
        fetcher=fetcher,
    )

    summary = harvest_summary(result)
    assert summary["reason_counts"] == {"invalid_json": 1}

    quarantine_payload = json.loads(
        Path(summary["quarantine_paths"][0]).read_text(encoding="utf-8")
    )
    assert quarantine_payload["reason_code"] == "invalid_json"
    assert "non-JSON" in quarantine_payload["details"]


# ---------------------------------------------------------------------------
# Combined edge-case: identity_mismatch + invalid_json in same run
# ---------------------------------------------------------------------------


def test_harvest_mixed_identity_mismatch_and_invalid_json_both_quarantine(
    tmp_path: Path,
) -> None:
    """Both identity_mismatch and invalid_json rows quarantine in the same harvest run."""
    good_payload = _trace_payload("00000000-0000-4000-8000-000000000040")
    mismatch_payload = _trace_payload("00000000-0000-4000-8000-000000000041")
    invalid_json_payload = _trace_payload("00000000-0000-4000-8000-000000000042")

    good_row = _selection_row(good_payload, cid="QmGood4")
    mismatch_row = (
        "00000000-0000-4000-8000-0000000000FE",  # different trace_id
        TradingR1Trace.model_validate(mismatch_payload).agent_id,
        TradingR1Trace.model_validate(mismatch_payload).market_id,
        "QmMismatch4",
        TradingR1Trace.model_validate(mismatch_payload).content_hash(),
        None,
        datetime(2026, 5, 15, 14, 5, tzinfo=UTC),
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    invalid_json_row = _selection_row(invalid_json_payload, cid="QmInvalid4")

    root = tmp_path / "calibration"
    fetcher = EdgeIpfsFetcher(
        {
            "QmGood4": good_payload,
            "QmMismatch4": mismatch_payload,
            "QmInvalid4": HarvestInvalidPayloadError("expected JSON object"),
        }
    )
    result = run_harvest(
        root=root,
        connection=EdgeConnection(
            selection_rows=[good_row, mismatch_row, invalid_json_row]
        ),
        limit=5,
        selection="recent",
        preflight_only=False,
        fetcher=fetcher,
    )

    summary = harvest_summary(result)
    assert summary["exit_status"] == "partial"
    assert summary["counts"] == {"quarantined": 2, "selected": 3, "succeeded": 1}
    assert summary["reason_counts"] == {
        "identity_mismatch": 1,
        "invalid_json": 1,
    }
