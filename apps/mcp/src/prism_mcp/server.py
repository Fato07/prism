"""FastMCP server exposing the sentinel adversarial validator as an MCP tool.

The MCP server is designed to be mounted as an ASGI sub-app on the sentinel
FastAPI service at the ``/mcp`` path, behind the same x402 PaymentMiddleware
that protects ``POST /validate``. External agents discover the ``validate``
tool via ``tools/list`` and invoke it through ``tools/call``.

Tools exposed:

  ``validate`` — Adversarially validate a Trading-R1 trace pinned to IPFS.
  ``get_price`` — Return the current x402 validation price.
  ``get_stats`` — Return aggregate sentinel statistics from Neon.
  ``get_calibration`` — Return the latest sentinel calibration metrics.
  ``get_tool_manifest`` — Return a redacted connector/tool capability manifest.
  ``get_issue_ledger`` — Return a read-only issue ledger for a validation receipt.

The ``validate`` tool runs the same pipeline as ``POST /validate``:

  1. Fetch trace JSON from IPFS via Pinata gateway.
  2. Generate the adversarial verdict via DSPy + GPT.
  3. Pin verdict JSON to IPFS via Pinata.
  4. Persist verdict to the Neon ``validations`` table.
  5. If ``PRISM_ONCHAIN`` is enabled and ``on_chain_request_hash`` is
     provided, submit ``validationResponse`` on Arc via the Circle SDK.

The tool's input schema mirrors ``ValidateRequest`` from the sentinel and
the output mirrors ``ValidateResponse`` (minus ``payment_tx_hash`` which is
controlled at the HTTP middleware layer).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import datetime
from typing import Any

import structlog
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_request
from prism_schemas.verdict import (
    AdversarialChallenge,
    AdversarialResolutionMetadata,
    ChallengeResolution,
    ResolutionRound,
    SentinelVerdict,
)
from pydantic import BaseModel, Field

logger = structlog.get_logger("prism.mcp")

MCP_SERVER_NAME = "prism-sentinel"


def _http_state_string(name: str) -> str | None:
    """Return a string value stashed on the current FastMCP HTTP request state.

    Returns ``None`` for in-process MCP clients (e.g. unit tests using
    ``fastmcp.Client(server)``) where no HTTP request exists.
    """
    try:
        req = get_http_request()
    except RuntimeError:
        return None
    value = getattr(req.state, name, None)
    return value if isinstance(value, str) else None


def _payment_tx_hash_from_http_context() -> str | None:
    """Return the x402 settlement tx hash stashed on the current HTTP request.

    The sentinel ``x402_middleware`` stores the settled Base tx hash on
    ``request.state.x402_payment_tx_hash`` before dispatching to the MCP
    sub-app. We surface it on the tool result so MCP callers receive the
    same ``payment_tx_hash`` field the HTTP ``/validate`` endpoint emits.
    """
    return _http_state_string("x402_payment_tx_hash")


def _payer_address_from_http_context() -> str | None:
    """Return the x402 payer address stashed on the current HTTP request."""
    return _http_state_string("x402_payer_address")


class ValidateMcpResult(BaseModel):
    """Output schema for the MCP ``validate`` tool.

    Mirrors the sentinel ``ValidateResponse`` so external agents see the
    same surface whether they call the HTTP endpoint or the MCP tool.
    ``payment_tx_hash`` is populated by the x402 middleware on the
    underlying HTTP request and is ``None`` for in-process invocations
    that bypass the HTTP layer.
    """

    request_hash: str
    trace_id: str
    sentinel_agent_id: int
    verdict_score: int = Field(ge=0, le=100)
    verdict_label: str
    evidence_challenges: list[str]
    thesis_challenges: list[str]
    calibration_critique: str
    ipfs_cid: str
    content_hash_hex: str
    tx_hash: str | None = None
    payment_tx_hash: str | None = None


# ---------------------------------------------------------------------------
# Pricing constant
# ---------------------------------------------------------------------------

VALIDATION_PRICE_USDC: float = 0.01
VALIDATION_CURRENCY: str = "USDC"
VALIDATION_NETWORK: str = "base-sepolia"
VALIDATION_PRICE_DESCRIPTION: str = "Price per adversarial validation of a reasoning trace"

# ---------------------------------------------------------------------------
# Calibration constant (May 13 2026 run, gap ≥ 30 points required)
# ---------------------------------------------------------------------------

CALIBRATION_RESULT: dict[str, Any] = {
    "calibration_passed": True,
    "gap_points": 45,
    "min_required_gap": 30,
    "model_family": "openai-gpt",
    "test_results": [
        {"trace_quality": "good", "score": 65, "label": "PASS"},
        {"trace_quality": "mediocre", "score": 42, "label": "WARN"},
        {"trace_quality": "bad", "score": 20, "label": "REJECT"},
    ],
    "tested_at": "2026-05-13T20:08:00Z",
}


# ---------------------------------------------------------------------------
# Response models for the new tools
# ---------------------------------------------------------------------------


class GetPriceResult(BaseModel):
    """Output schema for the MCP ``get_price`` tool."""

    price_usdc: float
    currency: str
    network: str
    description: str


class VerdictDistribution(BaseModel):
    """Verdict label distribution counts."""

    REJECT: int = 0
    WARN: int = 0
    PASS: int = 0
    ENDORSE: int = 0


class GetStatsResult(BaseModel):
    """Output schema for the MCP ``get_stats`` tool."""

    total_validations: int
    verdict_distribution: VerdictDistribution
    avg_verdict_score: float
    p95_latency_seconds: float | None
    on_chain_anchors: int
    lookback_hours: int


class CalibrationTestResult(BaseModel):
    """Single calibration test result."""

    trace_quality: str
    score: int
    label: str


class GetCalibrationResult(BaseModel):
    """Output schema for the MCP ``get_calibration`` tool."""

    calibration_passed: bool
    gap_points: int
    min_required_gap: int
    model_family: str
    test_results: list[CalibrationTestResult]
    tested_at: str


class EvidenceConnectorManifestEntry(BaseModel):
    """Redacted evidence connector configuration exposed to external agents."""

    provider: str
    transport: str
    configured: bool
    result_mapper: str | None = None
    input_mapper: str | None = None
    tool_name: str | None = None
    allowed_tools: list[str] = Field(default_factory=list)
    has_server_url: bool = False
    has_auth_token: bool = False
    has_api_key: bool = False
    fallback_reference: bool = False


class GetToolManifestResult(BaseModel):
    """Output schema for the MCP ``get_tool_manifest`` tool."""

    prism_mcp_tools: list[str]
    evidence_connectors: list[EvidenceConnectorManifestEntry]
    redacted: bool = True
    notes: list[str] = Field(default_factory=list)


class IssueLedgerValidationRef(BaseModel):
    """Minimal validation receipt reference for issue-ledger lookups."""

    request_hash: str
    trace_id: str
    sentinel_agent_id: int
    verdict_score: int = Field(ge=0, le=100)
    verdict_label: str
    response_uri: str
    tx_hash: str | None = None
    created_at: str | None = None


class GetIssueLedgerResult(BaseModel):
    """Output schema for the read-only MCP ``get_issue_ledger`` tool."""

    validation: IssueLedgerValidationRef
    structured_challenges: list[AdversarialChallenge]
    challenge_resolutions: list[ChallengeResolution]
    resolution_rounds: list[ResolutionRound]
    resolution_metadata: AdversarialResolutionMetadata | None = None
    unresolved_blocking_count: int = Field(ge=0)
    unresolved_material_count: int = Field(ge=0)
    verdict_content_hash_hex: str
    redacted: bool = True
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _csv_env(name: str) -> list[str]:
    """Return a comma-separated env var as stripped non-empty values."""
    raw_value = os.environ.get(name, "")
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def _tool_manifest_from_env() -> GetToolManifestResult:
    """Return a redacted MCP/tool connector manifest.

    This intentionally exposes booleans and connector semantics, not API keys,
    bearer tokens, or private server URLs.
    """
    provider = _canonical_evidence_provider(
        os.environ.get("PRISM_EVIDENCE_PROVIDER", "noop"),
    )
    direct_adapter_api_key_envs = {
        "parallel_search": "PARALLEL_API_KEY",
        "tavily_search": "TAVILY_API_KEY",
        "exa_search": "EXA_API_KEY",
        "firecrawl_search": "FIRECRAWL_API_KEY",
        "brave_search": "BRAVE_SEARCH_API_KEY",
    }
    notes = [
        "Connector secrets and server URLs are redacted.",
        "Direct adapters are fallback/reference implementations; MCP is preferred.",
    ]

    if provider in {"mcp", "mcp_http"}:
        result_mapper = os.environ.get("PRISM_EVIDENCE_RESULT_MAPPER", "generic_search")
        input_mapper = os.environ.get("PRISM_EVIDENCE_MCP_INPUT_MAPPER", "query")
        valid_result_mapper = _is_known_evidence_result_mapper(result_mapper)
        valid_input_mapper = _is_known_evidence_input_mapper(input_mapper)
        if not valid_result_mapper:
            notes.append("Configured MCP evidence result mapper is unknown.")
        if not valid_input_mapper:
            notes.append("Configured MCP evidence input mapper is unknown.")
        connector = EvidenceConnectorManifestEntry(
            provider="mcp",
            transport="mcp_http",
            configured=bool(
                os.environ.get("PRISM_EVIDENCE_MCP_URL")
                and os.environ.get("PRISM_EVIDENCE_MCP_TOOL")
                and valid_result_mapper
                and valid_input_mapper
            ),
            result_mapper=result_mapper,
            input_mapper=input_mapper,
            tool_name=os.environ.get("PRISM_EVIDENCE_MCP_TOOL"),
            allowed_tools=_csv_env("PRISM_EVIDENCE_MCP_ALLOWED_TOOLS"),
            has_server_url=bool(os.environ.get("PRISM_EVIDENCE_MCP_URL")),
            has_auth_token=bool(os.environ.get("PRISM_EVIDENCE_MCP_AUTH_TOKEN")),
        )
    elif provider in direct_adapter_api_key_envs:
        api_key_env = direct_adapter_api_key_envs[provider]
        connector = EvidenceConnectorManifestEntry(
            provider=provider,
            transport="direct_adapter",
            configured=bool(os.environ.get(api_key_env)),
            result_mapper=provider,
            has_api_key=bool(os.environ.get(api_key_env)),
            fallback_reference=True,
        )
    elif provider == "custom_webhook":
        connector = EvidenceConnectorManifestEntry(
            provider="custom_webhook",
            transport="custom_webhook",
            configured=bool(os.environ.get("PRISM_EVIDENCE_WEBHOOK_URL")),
            result_mapper="custom_webhook",
            has_server_url=bool(os.environ.get("PRISM_EVIDENCE_WEBHOOK_URL")),
            has_auth_token=bool(os.environ.get("PRISM_EVIDENCE_WEBHOOK_BEARER_TOKEN")),
            fallback_reference=True,
        )
    else:
        connector = EvidenceConnectorManifestEntry(
            provider=provider,
            transport="noop",
            configured=provider == "noop",
        )

    return GetToolManifestResult(
        prism_mcp_tools=[
            "validate",
            "get_price",
            "get_stats",
            "get_calibration",
            "get_tool_manifest",
            "get_issue_ledger",
        ],
        evidence_connectors=[connector],
        notes=notes,
    )


def _canonical_evidence_provider(provider: str) -> str:
    """Normalize evidence provider aliases used by the sentinel service."""
    normalized = provider.strip().lower() or "noop"
    return {
        "parallel": "parallel_search",
        "tavily": "tavily_search",
        "exa": "exa_search",
        "firecrawl": "firecrawl_search",
        "brave": "brave_search",
    }.get(normalized, normalized)


def _is_known_evidence_result_mapper(mapper_name: str) -> bool:
    """Return whether a result mapper is supported by the sentinel connector layer."""
    return mapper_name.strip().lower() in {
        "generic_search",
        "custom_webhook",
        "firecrawl_search",
        "exa_search",
        "parallel_search",
        "tavily_search",
        "brave_search",
    }


def _is_known_evidence_input_mapper(mapper_name: str) -> bool:
    """Return whether an MCP input mapper is supported by the sentinel connector layer."""
    return mapper_name.strip().lower() in {
        "query",
        "query_limit",
        "query_max_results",
        "q_count",
        "prism_evidence_request",
    }


def _request_hash_bytes(request_hash: str) -> bytes:
    """Decode a public bytes32 request hash string for DB lookup."""
    normalized = request_hash.strip().removeprefix("0x")
    if len(normalized) != 64:
        raise ToolError("invalid_request_hash: request_hash must be 32-byte hex")
    try:
        return bytes.fromhex(normalized)
    except ValueError as exc:
        raise ToolError("invalid_request_hash: request_hash must be 32-byte hex") from exc


def _isoformat_db_value(value: object) -> str | None:
    """Return a stable string for DB timestamp values."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _query_issue_ledger_validation(
    *,
    trace_id: str | None,
    request_hash: str | None,
) -> dict[str, Any] | None:
    """Query the latest validation receipt row for an issue-ledger lookup."""
    dsn = os.environ.get("DATABASE_URL", "")
    if not dsn:
        raise ToolError("database_unavailable: DATABASE_URL is not configured")

    try:
        import psycopg
    except ImportError as exc:
        raise ToolError("database_unavailable: psycopg is not installed") from exc

    clauses: list[str] = []
    params: list[object] = []
    if trace_id:
        clauses.append("trace_id = %s")
        params.append(trace_id)
    if request_hash:
        clauses.append("request_hash = %s")
        params.append(_request_hash_bytes(request_hash))
    if not clauses:
        raise ToolError("missing_identifier: provide trace_id or request_hash")

    sql = """
        SELECT
            encode(request_hash, 'hex') AS request_hash,
            trace_id,
            sentinel_agent_id,
            verdict_score,
            response_uri,
            tx_hash,
            created_at
        FROM validations
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT 1
    """.format(where_clause=" AND ".join(clauses))

    try:
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            row = cur.fetchone()
    except Exception as exc:
        logger.error("get_issue_ledger_db_query_failed", error_type=type(exc).__name__)
        raise ToolError("database_query_failed: cannot query validation receipt") from exc

    if row is None:
        return None

    return {
        "request_hash": str(row[0]),
        "trace_id": str(row[1]),
        "sentinel_agent_id": int(row[2]),
        "verdict_score": int(row[3]),
        "response_uri": str(row[4] or ""),
        "tx_hash": str(row[5]) if row[5] is not None else None,
        "created_at": _isoformat_db_value(row[6]),
    }


async def _fetch_verdict_json_from_response_uri(response_uri: str) -> dict[str, Any]:
    """Fetch a pinned verdict JSON receipt from its response URI."""
    if not response_uri or not response_uri.strip():
        raise ToolError("missing_response_uri: validation receipt has no response_uri")

    from sentinel.ipfs import PinataClient

    cid = _strip_ipfs_scheme(response_uri.strip())
    pinata = PinataClient()
    try:
        verdict_json = await pinata.fetch_json(cid)
    except Exception as exc:
        logger.error("get_issue_ledger_verdict_fetch_failed", error_type=type(exc).__name__)
        raise ToolError("verdict_fetch_failed: cannot resolve validation response_uri") from exc
    finally:
        await pinata.close()

    if not isinstance(verdict_json, dict):
        raise ToolError("invalid_verdict_receipt: pinned verdict must be a JSON object")
    return verdict_json


def _validate_verdict_matches_receipt(
    *,
    row: dict[str, Any],
    verdict: SentinelVerdict,
) -> None:
    """Fail closed if the pinned verdict does not match the DB receipt row."""
    verdict_hash = verdict.request_hash.strip().removeprefix("0x").lower()
    row_hash = str(row["request_hash"]).strip().removeprefix("0x").lower()
    if verdict_hash != row_hash:
        raise ToolError("verdict_receipt_mismatch: pinned verdict request_hash mismatch")
    if verdict.trace_id != row["trace_id"]:
        raise ToolError("verdict_receipt_mismatch: pinned verdict trace_id mismatch")
    if verdict.sentinel_agent_id != row["sentinel_agent_id"]:
        raise ToolError("verdict_receipt_mismatch: pinned verdict sentinel_agent_id mismatch")
    if verdict.verdict_score != row["verdict_score"]:
        raise ToolError("verdict_receipt_mismatch: pinned verdict verdict_score mismatch")


def _issue_ledger_from_verdict_row(
    *,
    row: dict[str, Any],
    verdict: SentinelVerdict,
) -> GetIssueLedgerResult:
    """Build a redacted issue-ledger response from DB and pinned verdict data."""
    unresolved_statuses = {"open", "answered", "conceded"}
    unresolved_blocking_count = sum(
        1
        for challenge in verdict.structured_challenges
        if challenge.blocking_pass and challenge.resolution_status in unresolved_statuses
    )
    unresolved_material_count = sum(
        1
        for challenge in verdict.structured_challenges
        if challenge.severity == "material" and challenge.resolution_status in unresolved_statuses
    )

    return GetIssueLedgerResult(
        validation=IssueLedgerValidationRef(
            request_hash=row["request_hash"],
            trace_id=row["trace_id"],
            sentinel_agent_id=row["sentinel_agent_id"],
            verdict_score=row["verdict_score"],
            verdict_label=verdict.verdict_label,
            response_uri=row["response_uri"],
            tx_hash=row["tx_hash"],
            created_at=row["created_at"],
        ),
        structured_challenges=verdict.structured_challenges,
        challenge_resolutions=verdict.challenge_resolutions,
        resolution_rounds=verdict.resolution_rounds,
        resolution_metadata=verdict.resolution_metadata,
        unresolved_blocking_count=unresolved_blocking_count,
        unresolved_material_count=unresolved_material_count,
        verdict_content_hash_hex=verdict.content_hash().hex(),
        notes=[
            "Read-only issue ledger; callers cannot mark issues resolved through this tool.",
            "Requester wallet addresses and connector secrets are not returned.",
        ],
    )


async def _get_issue_ledger(
    *,
    trace_id: str | None,
    request_hash: str | None,
) -> GetIssueLedgerResult:
    """Return the issue ledger for a persisted validation receipt."""
    cleaned_trace_id = trace_id.strip() if trace_id else None
    cleaned_request_hash = request_hash.strip() if request_hash else None
    if not cleaned_trace_id and not cleaned_request_hash:
        raise ToolError("missing_identifier: provide trace_id or request_hash")

    row = await asyncio.to_thread(
        _query_issue_ledger_validation,
        trace_id=cleaned_trace_id,
        request_hash=cleaned_request_hash,
    )
    if row is None:
        raise ToolError("issue_ledger_not_found: no validation receipt matched the identifier")

    verdict_json = await _fetch_verdict_json_from_response_uri(row["response_uri"])
    try:
        verdict = SentinelVerdict.model_validate(verdict_json)
    except Exception as exc:
        logger.error("get_issue_ledger_invalid_verdict", error_type=type(exc).__name__)
        raise ToolError("invalid_verdict_receipt: pinned verdict does not match schema") from exc

    _validate_verdict_matches_receipt(row=row, verdict=verdict)
    return _issue_ledger_from_verdict_row(row=row, verdict=verdict)


def _query_stats_from_db(hours: int = 168) -> dict[str, Any]:
    """Query Neon for aggregate validation statistics.

    Returns a dict matching ``GetStatsResult`` fields.  If ``DATABASE_URL``
    is unset or the query fails, returns zeroed-out defaults.
    """
    dsn = os.environ.get("DATABASE_URL", "")
    if not dsn:
        logger.warning("get_stats_no_database_url")
        return {
            "total_validations": 0,
            "verdict_distribution": {"REJECT": 0, "WARN": 0, "PASS": 0, "ENDORSE": 0},
            "avg_verdict_score": 0.0,
            "p95_latency_seconds": None,
            "on_chain_anchors": 0,
            "lookback_hours": hours,
        }

    try:
        import psycopg
    except ImportError:
        logger.error("get_stats_psycopg_not_available")
        return {
            "total_validations": 0,
            "verdict_distribution": {"REJECT": 0, "WARN": 0, "PASS": 0, "ENDORSE": 0},
            "avg_verdict_score": 0.0,
            "p95_latency_seconds": None,
            "on_chain_anchors": 0,
            "lookback_hours": hours,
        }

    try:
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) AS total_validations,
                    COALESCE(AVG(v.verdict_score), 0) AS avg_verdict_score,
                    COUNT(*) FILTER (WHERE v.verdict_score <= 25) AS reject_count,
                    COUNT(*) FILTER (WHERE v.verdict_score BETWEEN 26 AND 50) AS warn_count,
                    COUNT(*) FILTER (WHERE v.verdict_score BETWEEN 51 AND 75) AS pass_count,
                    COUNT(*) FILTER (WHERE v.verdict_score >= 76) AS endorse_count,
                    COUNT(*) FILTER (WHERE v.tx_hash IS NOT NULL) AS on_chain_anchors,
                    PERCENTILE_CONT(0.95) WITHIN GROUP (
                        ORDER BY EXTRACT(EPOCH FROM (v.created_at - t.created_at))
                    ) AS p95_latency_seconds
                FROM validations v
                JOIN traces t ON v.trace_id = t.trace_id
                WHERE v.created_at >= NOW() - make_interval(secs => %s * 3600)
                """,
                (hours,),
            )
            row = cur.fetchone()
    except Exception as exc:
        logger.error("get_stats_db_query_failed", error=str(exc))
        return {
            "total_validations": 0,
            "verdict_distribution": {"REJECT": 0, "WARN": 0, "PASS": 0, "ENDORSE": 0},
            "avg_verdict_score": 0.0,
            "p95_latency_seconds": None,
            "on_chain_anchors": 0,
            "lookback_hours": hours,
        }

    if row is None:
        return {
            "total_validations": 0,
            "verdict_distribution": {"REJECT": 0, "WARN": 0, "PASS": 0, "ENDORSE": 0},
            "avg_verdict_score": 0.0,
            "p95_latency_seconds": None,
            "on_chain_anchors": 0,
            "lookback_hours": hours,
        }

    return {
        "total_validations": int(row[0]),
        "verdict_distribution": {
            "REJECT": int(row[2]),
            "WARN": int(row[3]),
            "PASS": int(row[4]),
            "ENDORSE": int(row[5]),
        },
        "avg_verdict_score": round(float(row[1]), 1),
        "p95_latency_seconds": round(float(row[7]), 1) if row[7] is not None else None,
        "on_chain_anchors": int(row[6]),
        "lookback_hours": hours,
    }


def _is_onchain_enabled() -> bool:
    """Whether on-chain validationResponse submission is enabled."""
    return os.environ.get("PRISM_ONCHAIN", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _sentinel_agent_id() -> int:
    return int(os.environ.get("SENTINEL_AGENT_ID", "2"))


def _strip_ipfs_scheme(trace_uri: str) -> str:
    """Return the bare CID from an ``ipfs://CID`` URI (or the input as-is)."""
    return trace_uri[7:] if trace_uri.startswith("ipfs://") else trace_uri


def _compute_request_hash(trace_uri: str, trace_hash: str) -> str:
    """Deterministic request hash for the MCP tool — matches HTTP /validate."""
    return hashlib.sha256(f"{trace_uri}:{trace_hash}".encode()).hexdigest()


async def _run_validation(
    trace_uri: str,
    trace_hash: str,
    on_chain_request_hash: str | None,
) -> ValidateMcpResult:
    """Run the sentinel pipeline and return the structured verdict.

    Raises ``ToolError`` on recoverable failures so the MCP client receives
    a structured error rather than an unhandled exception.
    """
    from sentinel.ipfs import PinataClient
    from sentinel.persistence import (
        persist_verdict,
        update_validation_tx_hash,
        update_verdict_response_uri,
    )

    request_hash = _compute_request_hash(trace_uri, trace_hash)
    trace_cid = _strip_ipfs_scheme(trace_uri)

    logger.info(
        "mcp_validate_invoked",
        trace_uri=trace_uri,
        request_hash=request_hash,
        onchain=on_chain_request_hash is not None and _is_onchain_enabled(),
    )

    try:
        pinata = PinataClient()
        trace_data = await pinata.fetch_json(trace_cid)
        await pinata.close()
    except Exception as exc:
        logger.error("mcp_trace_fetch_failed", trace_uri=trace_uri, error=str(exc))
        raise ToolError(f"trace_fetch_failed: cannot resolve {trace_uri} ({exc})") from exc

    trace_id = str(trace_data.get("trace_id", "")) if isinstance(trace_data, dict) else ""
    trace_json_str = json.dumps(trace_data)

    from sentinel.resolution_loop import generate_verdict_with_resolution

    sentinel_agent_id = _sentinel_agent_id()
    try:
        verdict: SentinelVerdict = await generate_verdict_with_resolution(
            trace_json=trace_json_str,
            request_hash=request_hash,
            trace_id=trace_id,
            sentinel_agent_id=sentinel_agent_id,
        )
    except Exception as exc:
        logger.error("mcp_verdict_generation_failed", error=str(exc))
        raise ToolError(f"verdict_generation_failed: {exc}") from exc

    try:
        pinata = PinataClient()
        ipfs_cid = await pinata.pin_json(verdict.model_dump(mode="json", exclude_defaults=True))
        await pinata.close()
    except Exception as exc:
        logger.error("mcp_ipfs_pin_failed", error=str(exc))
        raise ToolError(f"ipfs_pin_failed: {exc}") from exc

    requester_address = _payer_address_from_http_context()

    try:
        persist_verdict(verdict, requester_address=requester_address)
        update_verdict_response_uri(request_hash, f"ipfs://{ipfs_cid}")
    except Exception as exc:
        logger.error("mcp_db_persist_failed", error=str(exc))
        raise ToolError(f"db_persist_failed: {exc}") from exc

    content_hash_hex = verdict.content_hash().hex()

    tx_hash: str | None = None
    if _is_onchain_enabled() and on_chain_request_hash:
        try:
            from sentinel.chain import submit_validation_response_from_env

            result = await submit_validation_response_from_env(
                request_hash=on_chain_request_hash,
                verdict_score=verdict.verdict_score,
                verdict_uri=f"ipfs://{ipfs_cid}",
                verdict_hash=f"0x{content_hash_hex}",
            )
            tx_hash = result.get("on_chain_tx_hash")
            if tx_hash:
                update_validation_tx_hash(request_hash, tx_hash)
            logger.info(
                "mcp_onchain_response_submitted",
                trace_id=verdict.trace_id,
                tx_hash=tx_hash,
            )
        except Exception as exc:
            logger.error(
                "mcp_onchain_response_failed",
                trace_id=verdict.trace_id,
                error=str(exc),
            )

    payment_tx_hash = _payment_tx_hash_from_http_context()

    logger.info(
        "mcp_validate_complete",
        trace_id=verdict.trace_id,
        verdict_score=verdict.verdict_score,
        verdict_label=verdict.verdict_label,
        ipfs_cid=ipfs_cid,
        tx_hash=tx_hash,
        payment_tx_hash=payment_tx_hash,
        requester_address=requester_address,
    )

    return ValidateMcpResult(
        request_hash=request_hash,
        trace_id=verdict.trace_id,
        sentinel_agent_id=verdict.sentinel_agent_id,
        verdict_score=verdict.verdict_score,
        verdict_label=verdict.verdict_label,
        evidence_challenges=verdict.evidence_challenges,
        thesis_challenges=verdict.thesis_challenges,
        calibration_critique=verdict.calibration_critique,
        ipfs_cid=ipfs_cid,
        content_hash_hex=content_hash_hex,
        tx_hash=tx_hash,
        payment_tx_hash=payment_tx_hash,
    )


def build_mcp_server() -> FastMCP:
    """Construct and return the Prism FastMCP server with the ``validate`` tool."""
    server: FastMCP = FastMCP(
        name=MCP_SERVER_NAME,
        instructions=(
            "Prism sentinel-as-a-service. Tools: "
            "validate — obtain an adversarial verdict on a Trading-R1 reasoning "
            "trace pinned to IPFS (requires x402 USDC nanopayment on Base); "
            "get_price — check the current validation price; "
            "get_stats — view aggregate sentinel statistics; "
            "get_calibration — inspect the latest calibration metrics proving "
            "cross-family adversarial discrimination; "
            "get_tool_manifest — inspect redacted connector capabilities; "
            "get_issue_ledger — inspect read-only structured issue ledgers."
        ),
    )

    @server.tool(
        name="validate",
        description=(
            "Adversarially validate a Trading-R1 reasoning trace pinned to IPFS. "
            "Returns a structured SentinelVerdict (score 0-100, label, evidence "
            "challenges, thesis challenges, calibration critique) and the IPFS CID "
            "of the pinned verdict JSON. If on_chain_request_hash is provided and "
            "PRISM_ONCHAIN is enabled, the verdict is also anchored on Arc via "
            "ERC-8004 ValidationRegistry.validationResponse and the on-chain "
            "tx_hash is returned."
        ),
    )
    async def validate(
        trace_uri: str,
        trace_hash: str,
        on_chain_request_hash: str | None = None,
    ) -> ValidateMcpResult:
        if not trace_uri or not trace_uri.strip():
            raise ToolError("invalid_trace_uri: trace_uri must be a non-empty string")
        if not trace_hash or not trace_hash.strip():
            raise ToolError("invalid_trace_hash: trace_hash must be a non-empty string")

        return await _run_validation(
            trace_uri=trace_uri.strip(),
            trace_hash=trace_hash.strip(),
            on_chain_request_hash=on_chain_request_hash,
        )

    # ------------------------------------------------------------------
    # get_price — return the current x402 validation price
    # ------------------------------------------------------------------

    @server.tool(
        name="get_price",
        description=(
            "Get the current x402 price for a sentinel validation call. "
            "Returns the price in USDC, the settlement network, and a "
            "human-readable description. Static for now (0.01 USDC) but "
            "structured for future pricing tiers."
        ),
    )
    async def get_price() -> GetPriceResult:
        logger.info("mcp_get_price_invoked")
        return GetPriceResult(
            price_usdc=VALIDATION_PRICE_USDC,
            currency=VALIDATION_CURRENCY,
            network=VALIDATION_NETWORK,
            description=VALIDATION_PRICE_DESCRIPTION,
        )

    # ------------------------------------------------------------------
    # get_stats — return aggregate sentinel statistics from Neon
    # ------------------------------------------------------------------

    @server.tool(
        name="get_stats",
        description=(
            "Get aggregate sentinel statistics from Neon Postgres. Returns "
            "total validations, verdict distribution (REJECT/WARN/PASS/"
            "ENDORSE), average verdict score, p95 latency, and on-chain "
            "anchor count for the given lookback window (default 7 days)."
        ),
    )
    async def get_stats(hours: int = 168) -> GetStatsResult:
        logger.info("mcp_get_stats_invoked", hours=hours)
        if hours < 1:
            raise ToolError("invalid_hours: hours must be a positive integer")
        data = await asyncio.to_thread(_query_stats_from_db, hours)
        return GetStatsResult(
            total_validations=data["total_validations"],
            verdict_distribution=VerdictDistribution(**data["verdict_distribution"]),
            avg_verdict_score=data["avg_verdict_score"],
            p95_latency_seconds=data["p95_latency_seconds"],
            on_chain_anchors=data["on_chain_anchors"],
            lookback_hours=data["lookback_hours"],
        )

    # ------------------------------------------------------------------
    # get_calibration — return the latest sentinel calibration metrics
    # ------------------------------------------------------------------

    @server.tool(
        name="get_calibration",
        description=(
            "Get the latest sentinel calibration metrics. Returns the "
            "calibration test results that prove the cross-family adversarial "
            "validation discriminates correctly between good, mediocre, and "
            "bad reasoning traces. The gap between good and bad scores must "
            "be ≥ 30 points."
        ),
    )
    async def get_calibration() -> GetCalibrationResult:
        logger.info("mcp_get_calibration_invoked")
        cal = CALIBRATION_RESULT
        return GetCalibrationResult(
            calibration_passed=cal["calibration_passed"],
            gap_points=cal["gap_points"],
            min_required_gap=cal["min_required_gap"],
            model_family=cal["model_family"],
            test_results=[CalibrationTestResult(**r) for r in cal["test_results"]],
            tested_at=cal["tested_at"],
        )

    # ------------------------------------------------------------------
    # get_tool_manifest — return redacted connector/tool capabilities
    # ------------------------------------------------------------------

    @server.tool(
        name="get_tool_manifest",
        description=(
            "Get a redacted manifest of Prism MCP tools and configured evidence "
            "connectors. Secrets, API keys, bearer tokens, and private server URLs "
            "are never returned. Useful for agents deciding what Prism can verify "
            "or retrieve during adversarial resolution."
        ),
    )
    async def get_tool_manifest() -> GetToolManifestResult:
        logger.info("mcp_get_tool_manifest_invoked")
        return _tool_manifest_from_env()

    # ------------------------------------------------------------------
    # get_issue_ledger — return a read-only structured issue ledger
    # ------------------------------------------------------------------

    @server.tool(
        name="get_issue_ledger",
        description=(
            "Get the structured issue ledger for a persisted validation receipt. "
            "Provide either trace_id or request_hash. Returns only read-only "
            "sentinel-adjudicated challenges, resolution attempts, rounds, and "
            "metadata from the pinned verdict receipt; callers cannot mark issues "
            "resolved through this tool."
        ),
    )
    async def get_issue_ledger(
        trace_id: str | None = None,
        request_hash: str | None = None,
    ) -> GetIssueLedgerResult:
        logger.info(
            "mcp_get_issue_ledger_invoked",
            has_trace_id=bool(trace_id),
            has_request_hash=bool(request_hash),
        )
        return await _get_issue_ledger(trace_id=trace_id, request_hash=request_hash)

    return server


mcp: FastMCP = build_mcp_server()
