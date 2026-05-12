"""Prism Trader — FastAPI service on port 3201.

Endpoints:
  GET  /health   — liveness check
  POST /trigger  — generate a Trading-R1 trace for a market question

Startup gates (all must pass before the service accepts requests):
  1. Environment variable validation
  2. LLM family validation (must be anthropic-claude)
  3. Geofencing check (locale must not be in Polymarket restricted list)

When PRISM_ONCHAIN=true, /trigger also submits the validation request
on-chain and persists the tx_hash.
"""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator

import structlog
from fastapi import FastAPI, HTTPException
from prism_schemas.db import run_migration
from prism_schemas.trace import TradingR1Trace
from pydantic import BaseModel, Field

from trader.config import check_geofence, startup_check
from trader.ipfs import PinataClient
from trader.persistence import (
    ensure_agent_row,
    persist_trace,
    update_trace_ipfs_cid,
    update_trace_tx_hash,
)
from trader.trading_r1 import WALLET_BALANCE_CAP, generate_and_post_process

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)

logger = structlog.get_logger("prism.trader")


def _is_onchain() -> bool:
    """Check if on-chain steps are enabled."""
    return os.environ.get("PRISM_ONCHAIN", "").strip().lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Startup gates
# ---------------------------------------------------------------------------


def _run_startup_gates() -> None:
    """Execute all startup validation gates. Exits on failure."""
    # Gate 1: Environment variables
    startup_check("trader")

    # Gate 2: LLM family is validated inside startup_check

    # Gate 3: Geofencing
    locale = os.environ.get("LOCALE", "")
    if not check_geofence(locale):
        logger.error("geofence_check_failed", locale=locale)
        print(
            f"FATAL: Locale '{locale}' is in Polymarket's restricted list. Service cannot start.",
            file=sys.stderr,
        )
        sys.exit(1)

    logger.info("startup_gates_passed")


async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Execute startup gates and DB setup when the app starts (not at import time)."""
    _run_startup_gates()

    _dsn = os.environ.get("DATABASE_URL", "")
    if _dsn:
        try:
            run_migration(_dsn)
            ensure_agent_row(_dsn)
        except Exception as exc:
            logger.error("db_setup_failed", error=str(exc))
    yield


app = FastAPI(title="Prism Trader", version="0.1.0", lifespan=_lifespan)


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class TriggerRequest(BaseModel):
    """Request body for POST /trigger."""

    market_id: str = Field(..., min_length=1, description="Polymarket condition ID")
    market_question: str = Field(..., min_length=1, description="The market question text")


class TriggerResponse(BaseModel):
    """Response body for POST /trigger."""

    trace_id: str
    ipfs_cid: str
    content_hash_hex: str
    action: str
    size_usdc: float
    final_probability: float
    tx_hash: str | None = None
    on_chain_request_hash: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness check."""
    return {"status": "ok", "service": "prism-trader"}


@app.post("/trigger", response_model=TriggerResponse)
async def trigger(request: TriggerRequest) -> TriggerResponse:
    """Generate a Trading-R1 trace for a market question.

    Flow: Claude call → IPFS pin → DB persist → (on-chain validationRequest
    if PRISM_ONCHAIN=true) → return trace metadata.
    """
    logger.info("trigger_received", market_id=request.market_id)

    # Determine wallet balance (default to cap for now; real balance query
    # can be wired in Phase 1 via CircleChain.get_wallet_balance).
    wallet_balance = WALLET_BALANCE_CAP

    # Generate trace via Mirascope + Claude
    try:
        trace: TradingR1Trace = await generate_and_post_process(
            market_id=request.market_id,
            market_question=request.market_question,
            wallet_balance=wallet_balance,
        )
    except Exception as exc:
        logger.error("trace_generation_failed", error=str(exc))
        raise HTTPException(status_code=502, detail=f"LLM call failed: {exc}") from exc

    # Validate trace against schema (double-check)
    TradingR1Trace.model_validate(trace.model_dump())

    # Pin to IPFS via Pinata
    ipfs_cid: str
    try:
        pinata = PinataClient()
        ipfs_cid = await pinata.pin_json(trace.model_dump(mode="json"))
        await pinata.close()
    except Exception as exc:
        logger.error("ipfs_pin_failed", error=str(exc))
        raise HTTPException(status_code=502, detail=f"IPFS pin failed: {exc}") from exc

    # Persist to Neon DB (only after successful IPFS pin per VAL-TRADER-003)
    try:
        persist_trace(trace)
        update_trace_ipfs_cid(trace.trace_id, ipfs_cid)
    except Exception as exc:
        logger.error("db_persist_failed", error=str(exc))
        raise HTTPException(status_code=502, detail=f"DB persist failed: {exc}") from exc

    content_hash_hex = trace.content_hash().hex()

    # On-chain validation request (optional, controlled by PRISM_ONCHAIN env var)
    tx_hash: str | None = None
    on_chain_request_hash: str | None = None

    if _is_onchain():
        try:
            from trader.validation import submit_validation_request_from_env

            trace_uri = f"ipfs://{ipfs_cid}"
            result = await submit_validation_request_from_env(
                trace_uri=trace_uri,
                trace_hash=f"0x{content_hash_hex}",
            )
            tx_hash = result.get("on_chain_tx_hash")
            on_chain_request_hash = result.get("request_hash")

            # Persist tx_hash to DB
            if tx_hash:
                update_trace_tx_hash(trace.trace_id, tx_hash)

            logger.info(
                "on_chain_validation_request_submitted",
                trace_id=trace.trace_id,
                tx_hash=tx_hash,
                request_hash=on_chain_request_hash,
            )
        except Exception as exc:
            # On-chain step failed — trace is still valid, just no tx_hash
            logger.error(
                "on_chain_validation_request_failed",
                trace_id=trace.trace_id,
                error=str(exc),
            )

    logger.info(
        "trigger_complete",
        trace_id=trace.trace_id,
        ipfs_cid=ipfs_cid,
        action=trace.action,
        size_usdc=trace.size_usdc,
        tx_hash=tx_hash,
    )

    return TriggerResponse(
        trace_id=trace.trace_id,
        ipfs_cid=ipfs_cid,
        content_hash_hex=content_hash_hex,
        action=trace.action,
        size_usdc=trace.size_usdc,
        final_probability=trace.final_probability,
        tx_hash=tx_hash,
        on_chain_request_hash=on_chain_request_hash,
    )
