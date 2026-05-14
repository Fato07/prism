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

# Wallet balance cap (hard rule from AGENTS.md).
WALLET_BALANCE_CAP = 100.0  # USDC
# Per-trade hard cap sized to hackathon-scale Polymarket deposits (~$8 USDC).
# The 25 % wallet-balance rule still applies on top of this cap.
MAX_TRADE_SIZE = 2.0  # USDC

# Probability clamping bounds — Polymarket CLOB rejects prices outside
# [0.001, 0.999]; we use [0.01, 0.99] to leave margin and avoid
# edge-case rejections from the exchange.
_PROB_MIN = 0.01
_PROB_MAX = 0.99


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

    Rules (from AGENTS.md §Security guardrails):
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


@llm.call(_model_id(), format=TradingR1Trace)
def generate_trace(market_id: str, market_question: str) -> str:
    """Generate a Trading-R1 reasoning trace for a market question.

    Returns a Mirascope Response; use ``.parse()`` to get TradingR1Trace.
    """
    return (
        f"SYSTEM: {TRADING_R1_SYSTEM}\n\n"
        f"USER: Market ID: {market_id}\n"
        f"Market Question: {market_question}\n\n"
        "Produce a complete Trading-R1 reasoning trace for this market. "
        "Include thesis composition, evidence collection, "
        "volatility-adjusted probability, and your final decision."
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

    # Override auto-generated fields with deterministic values.
    trace = trace.model_copy(
        update={
            "trace_id": str(uuid.uuid4()),
            "market_id": market_id,
            "market_question": market_question,
            "model_family": "anthropic-claude",
            "model_name": _model_name_short(),
            "created_at": datetime.now(UTC),
            "size_usdc": clamp_size(trace.size_usdc, wallet_balance),
            "raw_probability": clamped_raw,
            "final_probability": clamped_final,
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
