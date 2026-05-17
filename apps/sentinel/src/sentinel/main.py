"""Prism Sentinel — FastAPI service on port 3202.

Endpoints:
  GET  /health    — liveness check
  POST /validate          — adversarially validate a trader's reasoning trace
  ALL  /mcp/*               — FastMCP ASGI sub-app exposing ``validate`` as an MCP tool
  ALL  /demo-evidence-mcp/* — free demo MCP evidence server for connector smoke tests
  ALL  /market-evidence-mcp/* — free read-only Polymarket evidence MCP server

Startup gates (all must pass before the service accepts requests):
  1. Environment variable validation
  2. LLM family validation (must be openai-gpt)
  3. x402 bypass production safety gate

x402 middleware:
  Both ``POST /validate`` and ``/mcp/*`` are paywalled — callers must
  include a valid x402 payment header authorizing $0.01 USDC settlement
  on Base via the configured x402 facilitator (Circle Gateway). See
  ``sentinel.x402_middleware`` for the full pipeline.

When PRISM_ONCHAIN=true and on_chain_request_hash is provided,
/validate (and the MCP ``validate`` tool) also submit the validation
response on-chain and persist the tx_hash.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException, Request
from prism_mcp.server import build_mcp_server
from prism_schemas.db import run_migration
from prism_schemas.startup import startup_check
from prism_schemas.verdict import SentinelVerdict
from pydantic import BaseModel, Field

from sentinel.demo_evidence_mcp import build_demo_evidence_mcp_server
from sentinel.ipfs import PinataClient
from sentinel.market_evidence_mcp import build_market_evidence_mcp_server
from sentinel.persistence import (
    ensure_agent_row,
    persist_verdict,
    update_validation_tx_hash,
    update_verdict_response_uri,
)
from sentinel.resolution_loop import generate_verdict_with_resolution as generate_verdict
from sentinel.x402_middleware import (
    assert_bypass_safe_at_startup,
    is_x402_bypass_enabled,
    x402_middleware,
)

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)

logger = structlog.get_logger("prism.sentinel")


def _is_onchain() -> bool:
    """Check if on-chain steps are enabled."""
    return os.environ.get("PRISM_ONCHAIN", "").strip().lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# x402 Payment Middleware (configuration retained at module level)
# ---------------------------------------------------------------------------


def _is_x402_bypass() -> bool:
    """Back-compat shim used by existing tests.

    Real bypass logic lives in `sentinel.x402_middleware`. Keep this for
    tests that import `_is_x402_bypass` directly.
    """
    return is_x402_bypass_enabled()


# ---------------------------------------------------------------------------
# Startup gates
# ---------------------------------------------------------------------------


def _run_startup_gates() -> None:
    """Execute all startup validation gates. Exits on failure."""
    # Gate 1: Environment variables + LLM family validation
    startup_check("sentinel")

    # Gate 2: x402 bypass safety (refuse to start with bypass in production)
    assert_bypass_safe_at_startup()

    logger.info("startup_gates_passed")


# Run gates at module import time (uvicorn loads this module on start).
_run_startup_gates()

# Run DB migration and ensure agent row after gates pass.
_dsn = os.environ.get("DATABASE_URL", "")
if _dsn:
    try:
        run_migration(_dsn)
        ensure_agent_row(_dsn)
    except Exception as exc:
        logger.error("db_setup_failed", error=str(exc))

_mcp_server = build_mcp_server()
_mcp_app = _mcp_server.http_app(path="/")
_demo_evidence_mcp_server = build_demo_evidence_mcp_server()
_demo_evidence_mcp_app = _demo_evidence_mcp_server.http_app(path="/")
_market_evidence_mcp_server = build_market_evidence_mcp_server()
_market_evidence_mcp_app = _market_evidence_mcp_server.http_app(path="/")


@asynccontextmanager
async def _combined_mcp_lifespan(fastapi_app: FastAPI) -> AsyncIterator[None]:
    """Start both mounted FastMCP ASGI apps under the sentinel lifespan."""
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(_mcp_app.lifespan(fastapi_app))
        await stack.enter_async_context(_demo_evidence_mcp_app.lifespan(fastapi_app))
        await stack.enter_async_context(_market_evidence_mcp_app.lifespan(fastapi_app))
        yield


app = FastAPI(title="Prism Sentinel", version="0.1.0", lifespan=_combined_mcp_lifespan)
app.middleware("http")(x402_middleware)
app.mount("/mcp", _mcp_app)
app.mount("/demo-evidence-mcp", _demo_evidence_mcp_app)
app.mount("/market-evidence-mcp", _market_evidence_mcp_app)


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class ValidateRequest(BaseModel):
    """Request body for POST /validate."""

    trace_uri: str = Field(..., min_length=1, description="IPFS URI of the trace to validate")
    trace_hash: str = Field(..., min_length=1, description="Hex hash of the trace content")
    on_chain_request_hash: str | None = Field(
        None,
        description=(
            "On-chain request hash from validationRequest (for on-chain response submission)"
        ),
    )


class ValidateResponse(BaseModel):
    """Response body for POST /validate."""

    request_hash: str
    trace_id: str
    sentinel_agent_id: int
    verdict_score: int
    verdict_label: str
    evidence_challenges: list[str]
    thesis_challenges: list[str]
    calibration_critique: str
    ipfs_cid: str
    content_hash_hex: str
    tx_hash: str | None = None
    payment_tx_hash: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness check."""
    return {"status": "ok", "service": "prism-sentinel"}


@app.post("/validate", response_model=ValidateResponse)
async def validate(body: ValidateRequest, http_request: Request) -> ValidateResponse:
    """Adversarially validate a trader's reasoning trace.

    Flow: Fetch trace from IPFS → DSPy adversarial validation → IPFS pin →
    DB persist → (on-chain validationResponse if PRISM_ONCHAIN=true and
    on_chain_request_hash provided) → return verdict metadata.
    """
    logger.info("validate_received", trace_uri=body.trace_uri)

    # Pull the x402 settlement tx hash and payer address that the middleware
    # stashed on state.  Both are None when the request bypassed payment
    # (internal trader→sentinel channel).
    payment_tx_hash: str | None = getattr(http_request.state, "x402_payment_tx_hash", None)
    requester_address: str | None = getattr(http_request.state, "x402_payer_address", None)

    # Compute request_hash from the trace_uri and trace_hash
    request_hash = hashlib.sha256(f"{body.trace_uri}:{body.trace_hash}".encode()).hexdigest()

    # Extract CID from trace_uri (ipfs://CID format)
    trace_cid = body.trace_uri
    if trace_cid.startswith("ipfs://"):
        trace_cid = trace_cid[7:]

    # Fetch the trace from IPFS to get the actual trace JSON
    trace_json_str: str
    trace_id: str = ""
    try:
        pinata = PinataClient()
        trace_data = await pinata.fetch_json(trace_cid)
        # Use the fetched data directly as JSON string
        import json

        trace_json_str = json.dumps(trace_data)
        trace_id = trace_data.get("trace_id", "")
        await pinata.close()
    except Exception as exc:
        logger.error("trace_fetch_failed", trace_uri=body.trace_uri, error=str(exc))
        raise HTTPException(
            status_code=400,
            detail=f"Cannot fetch trace from IPFS: {exc}",
        ) from exc

    # Generate adversarial verdict via DSPy + GPT
    sentinel_agent_id = int(os.environ.get("SENTINEL_AGENT_ID", "2"))
    try:
        verdict: SentinelVerdict = await generate_verdict(
            trace_json=trace_json_str,
            request_hash=request_hash,
            trace_id=trace_id,
            sentinel_agent_id=sentinel_agent_id,
        )
    except Exception as exc:
        logger.error("verdict_generation_failed", error=str(exc))
        raise HTTPException(status_code=502, detail=f"LLM call failed: {exc}") from exc

    # Validate verdict against schema (double-check)
    SentinelVerdict.model_validate(verdict.model_dump())

    # Pin verdict to IPFS via Pinata
    ipfs_cid: str
    try:
        pinata = PinataClient()
        ipfs_cid = await pinata.pin_json(verdict.model_dump(mode="json", exclude_defaults=True))
        await pinata.close()
    except Exception as exc:
        logger.error("ipfs_pin_failed", error=str(exc))
        raise HTTPException(status_code=502, detail=f"IPFS pin failed: {exc}") from exc

    # Persist to Neon DB (only after successful IPFS pin per VAL-SENTINEL-004)
    try:
        persist_verdict(verdict, requester_address=requester_address)
        update_verdict_response_uri(request_hash, f"ipfs://{ipfs_cid}")
    except Exception as exc:
        logger.error("db_persist_failed", error=str(exc))
        raise HTTPException(status_code=502, detail=f"DB persist failed: {exc}") from exc

    content_hash_hex = verdict.content_hash().hex()

    # On-chain validation response (optional, controlled by PRISM_ONCHAIN env var)
    tx_hash: str | None = None

    if _is_onchain() and body.on_chain_request_hash:
        try:
            from sentinel.chain import submit_validation_response_from_env

            verdict_uri = f"ipfs://{ipfs_cid}"
            result = await submit_validation_response_from_env(
                request_hash=body.on_chain_request_hash,
                verdict_score=verdict.verdict_score,
                verdict_uri=verdict_uri,
                verdict_hash=f"0x{content_hash_hex}",
            )
            tx_hash = result.get("on_chain_tx_hash")

            # Persist tx_hash to DB
            if tx_hash:
                update_validation_tx_hash(request_hash, tx_hash)

            logger.info(
                "on_chain_validation_response_submitted",
                trace_id=verdict.trace_id,
                tx_hash=tx_hash,
                request_hash=body.on_chain_request_hash,
            )
        except Exception as exc:
            # On-chain step failed — verdict is still valid, just no tx_hash
            logger.error(
                "on_chain_validation_response_failed",
                trace_id=verdict.trace_id,
                error=str(exc),
            )

    logger.info(
        "validate_complete",
        trace_id=verdict.trace_id,
        verdict_score=verdict.verdict_score,
        verdict_label=verdict.verdict_label,
        ipfs_cid=ipfs_cid,
        tx_hash=tx_hash,
        payment_tx_hash=payment_tx_hash,
    )

    return ValidateResponse(
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
