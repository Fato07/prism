"""Trading-R1 trace generation using Mirascope + Claude.

Uses the Mirascope v2 ``@llm.call`` decorator with a Pydantic response model
to produce a structured :class:`TradingR1Trace` from a market question.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import structlog
from mirascope import llm
from prism_schemas.trace import TradingR1Trace

from trader.prompts import TRADING_R1_SYSTEM

logger = structlog.get_logger("prism.trader.trading_r1")

# Default model — overridden by TRADER_MODEL env var.
DEFAULT_MODEL = "anthropic/claude-sonnet-4-20250514"

# Wallet balance cap.
WALLET_BALANCE_CAP = 100.0  # USDC
# Per-trade hard cap sized to hackathon-scale Polymarket deposits (~$8 USDC).
# The 25 % wallet-balance rule still applies on top of this cap.
MAX_TRADE_SIZE = 2.0  # USDC

# Probability clamping bounds — Polymarket CLOB rejects prices outside
# [0.001, 0.999]; we use [0.01, 0.99] to leave margin and avoid
# edge-case rejections from the exchange.
_PROB_MIN = 0.01
_PROB_MAX = 0.99
_STALE_EVIDENCE_DAYS = 365


def _model_id() -> str:
    """Return the Mirascope model ID for the configured Claude model."""
    raw = os.environ.get("TRADER_MODEL", "claude-sonnet-4-20250514")
    # If the user already prefixed with "anthropic/", use as-is.
    if raw.startswith("anthropic/"):
        return raw
    return f"anthropic/{raw}"


def _model_name_short() -> str:
    """Return the short model name (without provider prefix) for the trace."""
    raw = os.environ.get("TRADER_MODEL", "claude-sonnet-4-20250514")
    return raw.split("/")[-1] if "/" in raw else raw


def clamp_size(size_usdc: float, wallet_balance: float = WALLET_BALANCE_CAP) -> float:
    """Clamp the trade size to 25 % of wallet balance, capped at 2 USDC.

    Safety rules:
    - wallet_balance_cap = 100 USDC
    - max_trade = min(2, 0.25 * wallet_balance)
    - If wallet_balance > 100, still cap at 2 USDC
    """
    effective_balance = min(wallet_balance, WALLET_BALANCE_CAP)
    max_allowed = min(MAX_TRADE_SIZE, 0.25 * effective_balance)
    clamped = min(size_usdc, max_allowed)
    if size_usdc > max_allowed:
        logger.warning(
            "trade_size_clamped",
            original=size_usdc,
            clamped=clamped,
            wallet_balance=wallet_balance,
        )
    return clamped


def _as_utc(dt: datetime) -> datetime:
    """Return a timezone-aware UTC datetime for evidence age checks."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def evidence_all_stale(
    trace: TradingR1Trace,
    *,
    created_at: datetime,
    stale_days: int = _STALE_EVIDENCE_DAYS,
) -> bool:
    """Return true when every evidence item is older than the stale threshold."""
    if not trace.evidence:
        return False
    created = _as_utc(created_at)
    return all((created - _as_utc(item.timestamp)).days > stale_days for item in trace.evidence)


@llm.call(_model_id(), format=TradingR1Trace)
def generate_trace(market_id: str, market_question: str) -> str:
    """Generate a Trading-R1 reasoning trace for a market question.

    Returns a Mirascope Response; use ``.parse()`` to get TradingR1Trace.
    """
    now = datetime.now(UTC).isoformat()
    return (
        f"SYSTEM: {TRADING_R1_SYSTEM}\n\n"
        f"USER: Current UTC time: {now}\n"
        f"Market ID: {market_id}\n"
        f"Market Question: {market_question}\n\n"
        "Produce a complete Trading-R1 reasoning trace for this market. "
        "Include thesis composition, evidence collection, "
        "volatility-adjusted probability, and your final decision. Use the "
        "current UTC time above when judging evidence freshness. If you lack "
        "current, market-specific evidence, choose HOLD."
    )


async def generate_and_post_process(
    market_id: str,
    market_question: str,
    wallet_balance: float = WALLET_BALANCE_CAP,
) -> TradingR1Trace:
    """Generate a trace and post-process (fill auto fields, clamp size).

    This is the main entry point for trace generation. It:
    1. Calls Claude via Mirascope to generate a structured trace
    2. Fills auto-generated fields (trace_id, model_family, model_name, created_at)
    3. Clamps size_usdc per the wallet balance cap
    """
    logger.info("generating_trace", market_id=market_id)

    response = generate_trace(market_id=market_id, market_question=market_question)

    # Parse the structured output into a TradingR1Trace via Mirascope's .parse().
    trace: TradingR1Trace = response.parse()

    # Clamp probabilities to valid trading range.
    # Polymarket CLOB rejects prices outside [0.001, 0.999]; we use
    # [0.01, 0.99] to leave margin and avoid edge-case rejections.
    clamped_raw = max(_PROB_MIN, min(_PROB_MAX, trace.raw_probability))
    clamped_final = max(_PROB_MIN, min(_PROB_MAX, trace.final_probability))

    if trace.raw_probability != clamped_raw or trace.final_probability != clamped_final:
        logger.warning(
            "probability_clamped",
            raw_original=trace.raw_probability,
            raw_clamped=clamped_raw,
            final_original=trace.final_probability,
            final_clamped=clamped_final,
        )

    created_at = datetime.now(UTC)
    action = trace.action
    size_usdc = clamp_size(trace.size_usdc, wallet_balance)
    price_limit = trace.price_limit
    rationale = trace.rationale
    volatility_adjustment = trace.volatility_adjustment

    if action == "HOLD":
        size_usdc = 0.0
        price_limit = 0.5

    if action != "HOLD" and evidence_all_stale(trace, created_at=created_at):
        logger.warning(
            "trace_action_forced_hold_stale_evidence",
            original_action=action,
            evidence_count=len(trace.evidence),
            stale_days=_STALE_EVIDENCE_DAYS,
        )
        action = "HOLD"
        size_usdc = 0.0
        price_limit = 0.5
        clamped_raw = 0.5
        clamped_final = 0.5
        volatility_adjustment = 0.0
        rationale = (
            f"{rationale}\n\n"
            "Prism post-process guard: all cited evidence is stale relative to "
            "trace creation, so the autonomous trader changed the action to HOLD "
            "instead of routing BUY/SELL capital."
        )

    # Override auto-generated fields with deterministic values.
    trace = trace.model_copy(
        update={
            "trace_id": str(uuid.uuid4()),
            "market_id": market_id,
            "market_question": market_question,
            "model_family": "anthropic-claude",
            "model_name": _model_name_short(),
            "created_at": created_at,
            "size_usdc": size_usdc,
            "raw_probability": clamped_raw,
            "volatility_adjustment": volatility_adjustment,
            "final_probability": clamped_final,
            "action": action,
            "price_limit": price_limit,
            "rationale": rationale,
        }
    )

    logger.info(
        "trace_generated",
        trace_id=trace.trace_id,
        action=trace.action,
        size_usdc=trace.size_usdc,
        final_probability=trace.final_probability,
    )
    return trace
