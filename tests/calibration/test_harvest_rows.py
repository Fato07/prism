"""Harvest row normalization and provenance tests."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prism_calibration.harvest import REQUIRED_HARVEST_COLUMNS, harvest_summary, run_harvest
from prism_calibration.validation import load_row
from prism_schemas.trace import Evidence, ThesisStep, TradingR1Trace


class HarvestCursor:
    """Cursor fake that returns schema rows and selected harvest records."""

    def __init__(self, connection: HarvestConnection) -> None:
        self.connection = connection
        self._rows: list[tuple[object, ...]] = []

    def __enter__(self) -> HarvestCursor:
        """Enter the fake cursor context manager."""
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """Exit the fake cursor context manager."""

    def execute(self, query: str, params: Sequence[object] | None = None) -> object:
        """Return fake information_schema or selected trace rows."""
        self.connection.queries.append(query)
        self.connection.params.append(tuple(params or ()))
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


class HarvestConnection:
    """Connection fake exposing the harvest DB protocol."""

    def __init__(self, selection_rows: list[tuple[object, ...]]) -> None:
        self.schema_rows = {
            (required.table, required.column) for required in REQUIRED_HARVEST_COLUMNS
        }
        self.selection_rows = selection_rows
        self.queries: list[str] = []
        self.params: list[tuple[object, ...]] = []

    def cursor(self) -> HarvestCursor:
        """Return a context-manageable fake cursor."""
        return HarvestCursor(self)


class MemoryIpfsFetcher:
    """In-memory IPFS fetcher keyed by CID."""

    def __init__(self, payloads: Mapping[str, dict[str, Any]]) -> None:
        self.payloads = dict(payloads)
        self.fetched: list[str] = []

    def fetch_json(self, cid: str) -> dict[str, Any]:
        """Return a JSON payload for one CID."""
        self.fetched.append(cid)
        return self.payloads[cid]


def _trace_payload(
    trace_id: str,
    *,
    agent_id: int = 1,
    market_id: str = "polymarket-real-001",
    created_at: datetime = datetime(2026, 5, 15, 12, 0, tzinfo=UTC),
) -> dict[str, Any]:
    """Return a valid Trading-R1 trace payload."""
    trace = TradingR1Trace(
        trace_id=trace_id,
        agent_id=agent_id,
        market_id=market_id,
        market_question=f"Will trace {trace_id} validate?",
        thesis=[
            ThesisStep(
                proposition="The normalized trace should be harvestable.",
                supporting_evidence_ids=[0],
                risk_factors=["Gateway JSON key ordering may differ."],
            )
        ],
        evidence=[
            Evidence(
                source="fixture",
                claim="The payload validates through the shared schema.",
                confidence=0.88,
                timestamp=created_at,
            )
        ],
        raw_probability=0.61,
        volatility_adjustment=-0.02,
        final_probability=0.59,
        action="BUY",
        size_usdc=5.0,
        price_limit=0.6,
        rationale="A real harvested row must preserve normalized trace content.",
        model_family="anthropic-claude",
        model_name="claude-opus-4-7",
        created_at=created_at,
    )
    return trace.model_dump(mode="json")


def _selection_row(
    payload: dict[str, Any],
    *,
    cid: str,
    validation: tuple[bytes, int, int, str, str, str, datetime] | None = None,
    db_hash: bytes | None = None,
    db_agent_id: int | None = None,
    db_created_at: datetime = datetime(2026, 5, 15, 12, 5, tzinfo=UTC),
) -> tuple[object, ...]:
    """Return one fake DB selection row matching the harvest SQL shape."""
    trace = TradingR1Trace.model_validate(payload)
    if validation is None:
        validation_values: tuple[object, ...] = (None, None, None, None, None, None, None)
    else:
        validation_values = validation
    return (
        trace.trace_id,
        db_agent_id or trace.agent_id,
        trace.market_id,
        cid,
        db_hash or trace.content_hash(),
        "0xtrace",
        db_created_at,
        *validation_values,
    )


def test_harvest_writes_normalized_real_rows_with_validation_context(
    tmp_path: Path,
) -> None:
    """Valid and unvalidated real traces export as explicit local rows."""
    validated_payload = _trace_payload("00000000-0000-4000-8000-000000000001")
    unvalidated_payload = _trace_payload("00000000-0000-4000-8000-000000000002")
    validation_created_at = datetime(2026, 5, 15, 12, 6, tzinfo=UTC)
    validation = (
        bytes.fromhex("11" * 32),
        4148,
        82,
        "ipfs://QmVerdictCid",
        "0xabcDEF1234567890",
        "0xvalidation",
        validation_created_at,
    )
    root = tmp_path / "calibration"
    fetcher = MemoryIpfsFetcher(
        {
            "QmTraceValidated": validated_payload,
            "QmTraceUnvalidated": unvalidated_payload,
        }
    )
    connection = HarvestConnection(
        [
            _selection_row(
                validated_payload,
                cid="QmTraceValidated",
                validation=validation,
                db_agent_id=4140,
            ),
            _selection_row(
                unvalidated_payload,
                cid="QmTraceUnvalidated",
                db_agent_id=4140,
            ),
        ]
    )

    result = run_harvest(
        root=root,
        connection=connection,
        limit=10,
        selection="recent",
        preflight_only=False,
        fetcher=fetcher,
    )

    summary = harvest_summary(result)
    assert summary["exit_status"] == "success"
    assert summary["counts"] == {"quarantined": 0, "selected": 2, "succeeded": 2}
    assert summary["status_counts"] == {"unvalidated": 1, "validated": 1}
    assert fetcher.fetched == ["QmTraceValidated", "QmTraceUnvalidated"]

    validated_row = load_row(root / "rows" / "real-00000000-0000-4000-8000-000000000001.json")
    assert validated_row.provenance.source_type == "real"
    assert validated_row.provenance.source_ref == "neon:traces/00000000-0000-4000-8000-000000000001"
    assert validated_row.provenance.content_hash == TradingR1Trace.model_validate(
        validated_payload
    ).content_hash().hex()
    assert validated_row.provenance.harvested_trace is not None
    assert validated_row.trace.agent_id == 1
    assert validated_row.provenance.harvested_trace.agent_id == 4140
    assert validated_row.provenance.harvested_trace.ipfs_cid == "QmTraceValidated"
    assert validated_row.provenance.harvested_trace.trace_tx_hash == "0xtrace"
    assert validated_row.provenance.harvested_trace.db_created_at.isoformat().startswith(
        "2026-05-15T12:05:00"
    )
    assert validated_row.provenance.validation is not None
    assert validated_row.provenance.validation.status == "validated"
    assert validated_row.provenance.validation.request_hash == "11" * 32
    assert validated_row.provenance.validation.requester_address == "0xabcDEF1234567890"
    assert validated_row.provenance.validation.verdict_score == 82

    unvalidated_row = load_row(
        root / "rows" / "real-00000000-0000-4000-8000-000000000002.json"
    )
    assert unvalidated_row.provenance.validation is not None
    assert unvalidated_row.provenance.validation.status == "unvalidated"
    assert unvalidated_row.review.status == "unreviewed"


def test_harvest_hash_verification_uses_normalized_schema_content(tmp_path: Path) -> None:
    """Gateway JSON byte order cannot drive canonical trace hash verification."""
    payload = _trace_payload("00000000-0000-4000-8000-000000000003")
    trace = TradingR1Trace.model_validate(payload)
    raw_gateway_hash = hashlib.sha256(
        json.dumps(payload, indent=4, sort_keys=False).encode("utf-8")
    ).hexdigest()
    assert raw_gateway_hash != trace.content_hash().hex()

    root = tmp_path / "calibration"
    result = run_harvest(
        root=root,
        connection=HarvestConnection([_selection_row(payload, cid="QmNormalizedHash")]),
        limit=1,
        selection="recent",
        preflight_only=False,
        fetcher=MemoryIpfsFetcher({"QmNormalizedHash": payload}),
    )

    summary = harvest_summary(result)
    assert summary["exit_status"] == "success"
    row = load_row(root / "rows" / "real-00000000-0000-4000-8000-000000000003.json")
    assert row.provenance.content_hash == trace.content_hash().hex()
    assert row.provenance.harvested_trace is not None
    assert row.provenance.harvested_trace.normalized_content_hash == trace.content_hash().hex()
