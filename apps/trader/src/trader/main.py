"""Prism Trader — FastAPI service on port 3201.

Endpoints:
  GET       /health    — liveness check
  POST      /trigger   — generate a Trading-R1 trace for a market question
  POST      /pipeline  — autonomous loop: generate trace → sentinel validate
  POST      /schedule  — start periodic pipeline runs every N minutes
  DELETE    /schedule  — stop the periodic pipeline

Startup gates (all must pass before the service accepts requests):
  1. Environment variable validation
  2. LLM family validation (must be anthropic-claude)
  3. Geofencing check (locale must not be in Polymarket restricted list)

When PRISM_ONCHAIN=true, /trigger also submits the validation request
on-chain and persists the tx_hash.

When AUTO_PIPELINE=true, the service starts the periodic pipeline
automatically on startup (5-minute interval by default).
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import TYPE_CHECKING

import httpx
import structlog

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from fastapi import FastAPI, HTTPException
from prism_schemas.db import run_migration
from prism_schemas.trace import TradingR1Trace
from pydantic import BaseModel, Field

from trader.config import check_geofence, startup_check
from trader.ipfs import PinataClient
from trader.markets import pick_market
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

    # Auto-start pipeline scheduler when AUTO_PIPELINE=true
    if os.environ.get("AUTO_PIPELINE", "").strip().lower() in ("1", "true", "yes"):
        interval = int(os.environ.get("PIPELINE_INTERVAL_MINUTES", "5"))
        loop = asyncio.get_event_loop()
        loop.create_task(_pipeline_loop(interval))
        logger.info("auto_pipeline_enabled", interval_minutes=interval)

    yield


app = FastAPI(title="Prism Trader", version="0.1.0", lifespan=_lifespan)  # type: ignore[arg-type]


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


class PipelineResponse(BaseModel):
    """Response body for POST /pipeline."""

    trace: TriggerResponse
    validation: dict | None = None
    validation_status: str = "pending"  # "success" | "skipped" | "error" | "pending"


class ScheduleResponse(BaseModel):
    """Response body for POST /schedule and DELETE /schedule."""

    status: str  # "started" | "stopped" | "already_running" | "not_running"
    interval_minutes: int = 5


# ---------------------------------------------------------------------------
# Sentinel URL helper
# ---------------------------------------------------------------------------


def _sentinel_url() -> str:
    """Return the sentinel base URL from env (default localhost)."""
    return os.environ.get("SENTINEL_URL", "http://localhost:3202").rstrip("/")


def _gateway_url() -> str:
    """Return the Polymarket gateway base URL from env (default localhost)."""
    return os.environ.get("GATEWAY_URL", "http://localhost:3203").rstrip("/")


# ---------------------------------------------------------------------------
# Background scheduler state
# ---------------------------------------------------------------------------

_pipeline_task: asyncio.Task | None = None


def _is_scheduling() -> bool:
    """Whether the periodic pipeline task is currently running."""
    return _pipeline_task is not None and not _pipeline_task.done()


async def _pipeline_loop(interval_minutes: int) -> None:
    """Background loop that runs the pipeline every *interval_minutes*."""
    logger.info("pipeline_loop_started", interval_minutes=interval_minutes)
    while True:
        try:
            await asyncio.sleep(interval_minutes * 60)
            logger.info("pipeline_loop_tick")
            # Reuse the same logic as /pipeline — errors are logged, not raised.
            await _run_pipeline_internal()
        except asyncio.CancelledError:
            logger.info("pipeline_loop_cancelled")
            return
        except Exception as exc:
            logger.error("pipeline_loop_error", error=str(exc))


async def _run_pipeline_internal() -> PipelineResponse:
    """Core pipeline logic — shared by /pipeline endpoint and the scheduler."""
    market = pick_market()
    market_id = market["id"]
    market_question = market["question"]

    # Step 1: Generate trace (reuse /trigger logic)
    logger.info("pipeline_generating_trace", market_id=market_id)

    trace: TradingR1Trace
    try:
        trace = await generate_and_post_process(
            market_id=market_id,
            market_question=market_question,
            wallet_balance=WALLET_BALANCE_CAP,
        )
    except Exception as exc:
        logger.error("pipeline_trace_generation_failed", error=str(exc))
        raise

    TradingR1Trace.model_validate(trace.model_dump())

    # Step 2: Pin to IPFS
    ipfs_cid: str
    try:
        pinata = PinataClient()
        ipfs_cid = await pinata.pin_json(trace.model_dump(mode="json"))
        await pinata.close()
    except Exception as exc:
        logger.error("pipeline_ipfs_pin_failed", error=str(exc))
        raise

    # Step 3: Persist to DB
    try:
        persist_trace(trace)
        update_trace_ipfs_cid(trace.trace_id, ipfs_cid)
    except Exception as exc:
        logger.error("pipeline_db_persist_failed", error=str(exc))
        raise

    content_hash_hex = trace.content_hash().hex()

    # On-chain validation request (optional)
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
            if tx_hash:
                update_trace_tx_hash(trace.trace_id, tx_hash)
        except Exception as exc:
            logger.error("pipeline_on_chain_failed", error=str(exc))

    trigger_result = TriggerResponse(
        trace_id=trace.trace_id,
        ipfs_cid=ipfs_cid,
        content_hash_hex=content_hash_hex,
        action=trace.action,
        size_usdc=trace.size_usdc,
        final_probability=trace.final_probability,
        tx_hash=tx_hash,
        on_chain_request_hash=on_chain_request_hash,
    )

    # Step 4: Call sentinel /validate
    validation: dict | None = None
    validation_status: str = "pending"

    try:
        trace_uri = f"ipfs://{ipfs_cid}"
        validate_body: dict = {
            "trace_uri": trace_uri,
            "trace_hash": f"0x{content_hash_hex}",
        }
        if on_chain_request_hash:
            validate_body["on_chain_request_hash"] = on_chain_request_hash

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{_sentinel_url()}/validate",
                json=validate_body,
                headers={
                    # The sentinel's x402 middleware authorizes internal
                    # trader→sentinel calls if X402-Bypass matches its
                    # `X402_INTERNAL_BYPASS_TOKEN` env var exactly. Both
                    # services must be configured with the same token; if
                    # neither has a token set, any non-empty value works.
                    "X402-Bypass": os.environ.get(
                        "X402_INTERNAL_BYPASS_TOKEN", "true"
                    ),
                },
            )

            if resp.status_code in (200, 202):
                validation = resp.json()
                validation_status = "success"
                logger.info(
                    "pipeline_validation_success",
                    verdict_score=validation.get("verdict_score"),
                    verdict_label=validation.get("verdict_label"),
                )
            elif resp.status_code == 402:
                validation_status = "skipped"
                logger.warning(
                    "pipeline_validation_payment_required",
                    detail="Sentinel returned 402 (x402 payment required). "
                    "Validation skipped but trace persisted.",
                )
            else:
                validation_status = "error"
                logger.warning(
                    "pipeline_validation_failed",
                    status_code=resp.status_code,
                    body=resp.text[:500],
                )
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        validation_status = "error"
        logger.warning(
            "pipeline_sentinel_unreachable",
            sentinel_url=_sentinel_url(),
            error=str(exc),
        )
    except Exception as exc:
        validation_status = "error"
        logger.error("pipeline_validation_error", error=str(exc))

    # Step 5: Trade via Polymarket gateway (only if sentinel verdict is PASS)
    if validation_status == "success" and validation and validation.get("verdict_label") == "PASS":
        try:
            agent_id = int(os.environ.get("TRADER_AGENT_ID", "1"))
            side = "BUY" if trace.action == "BUY" else "SELL"

            trade_body: dict = {
                "agentId": agent_id,
                "traceId": trace.trace_id,
                "marketId": market_id,
                "side": side,
                "sizeUsdc": trace.size_usdc,
                "priceLimit": trace.final_probability,
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                trade_resp = await client.post(
                    f"{_gateway_url()}/trade",
                    json=trade_body,
                )

                if trade_resp.status_code in (200, 202):
                    trade_data = trade_resp.json()
                    logger.info(
                        "pipeline_trade_sent",
                        trace_id=trace.trace_id,
                        market_id=market_id,
                        side=side,
                        size_usdc=trace.size_usdc,
                        price_limit=trace.final_probability,
                        order_id=trade_data.get("receipt", {}).get("orderId"),
                    )
                else:
                    logger.warning(
                        "pipeline_trade_rejected",
                        status_code=trade_resp.status_code,
                        body=trade_resp.text[:500],
                    )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            logger.warning(
                "pipeline_trade_gateway_unreachable",
                gateway_url=_gateway_url(),
                error=str(exc),
            )
        except Exception as exc:
            logger.error("pipeline_trade_error", error=str(exc))
    else:
        reason = (
            f"validation_status={validation_status}"
            if validation_status != "success"
            else f"verdict_label={validation.get('verdict_label', 'N/A') if validation else 'N/A'}"
        )
        logger.info("pipeline_trade_skipped", reason=reason, trace_id=trace.trace_id)

    # Trace is persisted regardless of sentinel outcome.
    return PipelineResponse(
        trace=trigger_result,
        validation=validation,
        validation_status=validation_status,
    )


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


@app.post("/pipeline", response_model=PipelineResponse)
async def run_pipeline() -> PipelineResponse:
    """Run the full autonomous loop: generate trace → sentinel validate.

    1. Pick a market question from a curated list
    2. Call the trader's own /trigger logic to generate a trace
    3. Call the sentinel's /validate endpoint to validate the trace
    4. Return both results

    The trace is persisted even if the sentinel is unreachable or
    returns a non-success response (e.g. HTTP 402 when x402 is active).
    """
    logger.info("pipeline_endpoint_called")

    try:
        return await _run_pipeline_internal()
    except Exception as exc:
        logger.error("pipeline_endpoint_failed", error=str(exc))
        raise HTTPException(status_code=502, detail=f"Pipeline failed: {exc}") from exc


@app.post("/schedule", response_model=ScheduleResponse)
async def start_schedule(interval_minutes: int = 5) -> ScheduleResponse:
    """Start periodic pipeline runs every N minutes.

    Uses a lightweight asyncio background task (no external scheduler).
    Only one schedule can be active at a time — call DELETE /schedule first
    to change the interval.
    """
    global _pipeline_task  # noqa: PLW0603

    if _is_scheduling():
        return ScheduleResponse(status="already_running", interval_minutes=interval_minutes)

    _pipeline_task = asyncio.create_task(_pipeline_loop(interval_minutes))
    logger.info("schedule_started", interval_minutes=interval_minutes)
    return ScheduleResponse(status="started", interval_minutes=interval_minutes)


@app.delete("/schedule", response_model=ScheduleResponse)
async def stop_schedule() -> ScheduleResponse:
    """Stop the periodic pipeline task."""
    global _pipeline_task  # noqa: PLW0603

    if not _is_scheduling():
        return ScheduleResponse(status="not_running", interval_minutes=0)

    _pipeline_task.cancel()
    try:
        await _pipeline_task
    except asyncio.CancelledError:
        pass
    _pipeline_task = None
    logger.info("schedule_stopped")
    return ScheduleResponse(status="stopped", interval_minutes=0)
