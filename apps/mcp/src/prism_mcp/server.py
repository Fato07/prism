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
from typing import TYPE_CHECKING, Any

import structlog
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_request
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from prism_schemas.verdict import SentinelVerdict

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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


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

    from sentinel.adversarial import generate_verdict

    sentinel_agent_id = _sentinel_agent_id()
    try:
        verdict: SentinelVerdict = await generate_verdict(
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
        ipfs_cid = await pinata.pin_json(verdict.model_dump(mode="json"))
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
            "cross-family adversarial discrimination."
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

    return server


mcp: FastMCP = build_mcp_server()
