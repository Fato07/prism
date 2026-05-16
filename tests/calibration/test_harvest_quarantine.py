"""Harvest quarantine and failure-summary tests."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prism_calibration.harvest import REQUIRED_HARVEST_COLUMNS, harvest_summary, run_harvest
from prism_schemas.trace import Evidence, ThesisStep, TradingR1Trace


class QuarantineCursor:
    """Cursor fake for quarantine harvest tests."""

    def __init__(self, connection: QuarantineConnection) -> None:
        self.connection = connection
        self._rows: list[tuple[object, ...]] = []

    def __enter__(self) -> QuarantineCursor:
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


class QuarantineConnection:
    """Connection fake exposing the harvest DB protocol."""

    def __init__(self, selection_rows: list[tuple[object, ...]]) -> None:
        self.schema_rows = {
            (required.table, required.column) for required in REQUIRED_HARVEST_COLUMNS
        }
        self.selection_rows = selection_rows

    def cursor(self) -> QuarantineCursor:
        """Return a context-manageable fake cursor."""
        return QuarantineCursor(self)


class MixedIpfsFetcher:
    """IPFS fetcher fake that can return payloads or raise per CID."""

    def __init__(self, payloads: Mapping[str, dict[str, Any] | OSError]) -> None:
        self.payloads = dict(payloads)
        self.fetched: list[str] = []

    def fetch_json(self, cid: str) -> dict[str, Any]:
        """Return payloads or raise configured failures."""
        self.fetched.append(cid)
        payload = self.payloads[cid]
        if isinstance(payload, OSError):
            raise payload
        return payload


def _trace_payload(trace_id: str, *, market_id: str = "polymarket-real-002") -> dict[str, Any]:
    """Return a valid Trading-R1 trace payload."""
    created_at = datetime(2026, 5, 15, 13, 0, tzinfo=UTC)
    trace = TradingR1Trace(
        trace_id=trace_id,
        agent_id=4140,
        market_id=market_id,
        market_question=f"Will quarantined trace {trace_id} continue processing?",
        thesis=[
            ThesisStep(
                proposition="Bad rows should not stop good rows from harvesting.",
                supporting_evidence_ids=[0],
                risk_factors=["A single malformed trace may abort the run."],
            )
        ],
        evidence=[
            Evidence(
                source="fixture",
                claim="Quarantine captures reason-coded failures.",
                confidence=0.84,
                timestamp=created_at,
            )
        ],
        raw_probability=0.52,
        volatility_adjustment=0.01,
        final_probability=0.53,
        action="HOLD",
        size_usdc=0.0,
        price_limit=0.5,
        rationale="The harvest should continue through mixed-quality input.",
        model_family="anthropic-claude",
        model_name="claude-opus-4-7",
        created_at=created_at,
    )
    return trace.model_dump(mode="json")


def _selection_row(
    payload: dict[str, Any],
    *,
    cid: str | None,
    db_hash: bytes | None = None,
) -> tuple[object, ...]:
    """Return a fake DB row matching harvest SQL."""
    trace = TradingR1Trace.model_validate(payload)
    return (
        trace.trace_id,
        trace.agent_id,
        trace.market_id,
        cid or "",
        db_hash or trace.content_hash(),
        None,
        datetime(2026, 5, 15, 13, 5, tzinfo=UTC),
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )


def test_harvest_quarantines_bad_rows_and_continues(tmp_path: Path) -> None:
    """Missing CIDs, IPFS errors, bad schemas, and hash mismatches quarantine."""
    good = _trace_payload("00000000-0000-4000-8000-000000000010")
    missing_cid = _trace_payload("00000000-0000-4000-8000-000000000011")
    unreachable = _trace_payload("00000000-0000-4000-8000-000000000012")
    malformed = _trace_payload("00000000-0000-4000-8000-000000000013")
    malformed.pop("market_question")
    hash_mismatch = _trace_payload("00000000-0000-4000-8000-000000000014")

    root = tmp_path / "calibration"
    result = run_harvest(
        root=root,
        connection=QuarantineConnection(
            [
                _selection_row(good, cid="QmGood"),
                _selection_row(missing_cid, cid=None),
                _selection_row(unreachable, cid="QmUnreachable"),
                _selection_row(
                    _trace_payload("00000000-0000-4000-8000-000000000013"),
                    cid="QmMalformed",
                ),
                _selection_row(hash_mismatch, cid="QmMismatch", db_hash=bytes.fromhex("ff" * 32)),
            ]
        ),
        limit=10,
        selection="recent",
        preflight_only=False,
        fetcher=MixedIpfsFetcher(
            {
                "QmGood": good,
                "QmUnreachable": OSError("gateway timeout"),
                "QmMalformed": malformed,
                "QmMismatch": hash_mismatch,
            }
        ),
    )

    summary = harvest_summary(result)
    assert summary["exit_status"] == "partial"
    assert summary["counts"] == {"quarantined": 4, "selected": 5, "succeeded": 1}
    assert summary["reason_counts"] == {
        "hash_mismatch": 1,
        "ipfs_unreachable": 1,
        "malformed_schema": 1,
        "missing_cid": 1,
    }
    assert len(summary["row_paths"]) == 1
    assert len(summary["quarantine_paths"]) == 4

    quarantine_payloads = [
        json.loads(Path(path).read_text(encoding="utf-8"))
        for path in summary["quarantine_paths"]
    ]
    reasons = {payload["trace_id"]: payload["reason_code"] for payload in quarantine_payloads}
    assert reasons == {
        "00000000-0000-4000-8000-000000000011": "missing_cid",
        "00000000-0000-4000-8000-000000000012": "ipfs_unreachable",
        "00000000-0000-4000-8000-000000000013": "malformed_schema",
        "00000000-0000-4000-8000-000000000014": "hash_mismatch",
    }
    for payload in quarantine_payloads:
        assert payload["run_id"].startswith("harvest-")
        assert payload["source_table"] == "traces"
        assert "details" in payload
        assert "cid" in payload
