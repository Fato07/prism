"""Trading-R1 trace generation using Mirascope + Claude.

Uses the Mirascope v2 ``@llm.call`` decorator with a Pydantic response model
to produce a structured :class:`TradingR1Trace` from a market question.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from mirascope import llm  # type: ignore[import-untyped]
from prism_schemas.trace import TradingR1Trace

from trader.prompts import TRADING_R1_SYSTEM, build_evidence_context

if TYPE_CHECKING:
    from prism_schemas.verdict import EvidenceToolReceipt
    from sentinel.evidence_tools import EvidenceSearchResult  # type: ignore[import-untyped]

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


@llm.call(_model_id(), format=TradingR1Trace)  # type: ignore[untyped-decorator]
def generate_trace(
    market_id: str,
    market_question: str,
    evidence_context: str = "",
) -> str:
    """Generate a Trading-R1 reasoning trace for a market question.

    Parameters:
        market_id: The Polymarket condition ID.
        market_question: The market question text.
        evidence_context: Optional tool-sourced evidence to inject into the
            prompt.  When provided, the LLM is instructed to use this evidence
            instead of fabricating sources.

    Returns a Mirascope Response; use ``.parse()`` to get TradingR1Trace.
    """
    now = datetime.now(UTC).isoformat()
    prompt = (
        f"SYSTEM: {TRADING_R1_SYSTEM}\n\n"
        f"USER: Current UTC time: {now}\n"
        f"Market ID: {market_id}\n"
        f"Market Question: {market_question}\n\n"
    )
    if evidence_context:
        prompt += evidence_context
    else:
        prompt += (
            "Produce a complete Trading-R1 reasoning trace for this market. "
            "Include thesis composition, evidence collection, "
            "volatility-adjusted probability, and your final decision. Use the "
            "current UTC time above when judging evidence freshness. If you lack "
            "current, market-specific evidence, choose HOLD."
        )
    return prompt


async def generate_and_post_process(
    market_id: str,
    market_question: str,
    wallet_balance: float = WALLET_BALANCE_CAP,
) -> TradingR1Trace:
    """Generate a trace and post-process (fill auto fields, clamp size, HOLD guards).

    This is the main entry point for trace generation. It:
    1. Calls evidence_search() to retrieve tool-sourced evidence from sentinel
    2. Injects retrieved evidence into the Mirascope prompt as context
    3. Maps EvidenceSearchResult → EvidenceToolReceipt for trace evidence_receipts
    4. Calls Claude via Mirascope to generate a structured trace
    5. Fills auto-generated fields (trace_id, model_family, model_name, created_at)
    6. Clamps size_usdc per the wallet balance cap
    7. Applies stale-evidence HOLD guard (independent of tool-first guard)
    8. Applies tool-first HOLD guard (empty evidence_receipts + BUY/SELL → HOLD)
    """
    logger.info("generating_trace", market_id=market_id)

    # ---------------------------------------------------------------
    # Step 1: Retrieve tool-sourced evidence from the sentinel
    # ---------------------------------------------------------------
    evidence_receipts: list[EvidenceToolReceipt] = []
    evidence_context = ""

    try:
        from trader.tools.evidence_search import evidence_search, map_result_to_receipt

        search_results: list[EvidenceSearchResult] = await evidence_search(
            market_question=market_question,
        )

        # Map EvidenceSearchResult → EvidenceToolReceipt for trace receipts.
        for result in search_results:
            evidence_receipts.append(map_result_to_receipt(result))

        # Build the evidence context section for the prompt.
        if search_results:
            evidence_context = build_evidence_context(search_results)
            logger.info(
                "evidence_injected_into_prompt",
                result_count=len(search_results),
                receipt_count=len(evidence_receipts),
            )
        else:
            logger.info("evidence_search_returned_empty", market_question=market_question[:100])
    except Exception as exc:
        logger.warning(
            "evidence_search_failed_unexpected",
            error=type(exc).__name__,
            detail=str(exc)[:200],
        )
        # Degraded mode: proceed without tool evidence.

    # ---------------------------------------------------------------
    # Step 2: Generate the trace via Mirascope + Claude
    # ---------------------------------------------------------------
    response = generate_trace(
        market_id=market_id,
        market_question=market_question,
        evidence_context=evidence_context,
    )

    # Parse the structured output into a TradingR1Trace via Mirascope's .parse().
    trace: TradingR1Trace = response.parse()

    # ---------------------------------------------------------------
    # Step 3: Post-process — clamp probabilities, size, apply guardrails
    # ---------------------------------------------------------------

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

    # Capture the original action for independent guard evaluation.
    # Both the stale-evidence guard and tool-first guard need to know
    # what the LLM originally intended before any guard overrides.
    _original_action = action

    if action == "HOLD":
        size_usdc = 0.0
        price_limit = 0.5

    # --- Guard 1: Stale-evidence guard (existing, independent) ---
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

    # --- Guard 2: Tool-first HOLD guard (independent of stale-evidence guard) ---
    # Check against the original action so both guards can fire independently.
    if _original_action in ("BUY", "SELL") and not evidence_receipts:
        logger.warning(
            "trace_action_forced_hold_no_tool_evidence",
            original_action=_original_action,
            evidence_receipts_count=0,
        )
        action = "HOLD"
        size_usdc = 0.0
        price_limit = 0.5
        clamped_raw = 0.5
        clamped_final = 0.5
        volatility_adjustment = 0.0
        rationale = (
            f"{rationale}\n\n"
            f"Prism tool-first guard: no tool-sourced evidence was retrieved "
            f"before trace generation, so the autonomous trader changed the "
            f"action from {_original_action} to HOLD. Trader must have "
            f"verifiable tool-sourced evidence before deploying capital."
        )

    # ---------------------------------------------------------------
    # Step 4: Override auto-generated fields with deterministic values
    # ---------------------------------------------------------------
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
            "evidence_receipts": evidence_receipts,
        }
    )

    logger.info(
        "trace_generated",
        trace_id=trace.trace_id,
        action=trace.action,
        size_usdc=trace.size_usdc,
        final_probability=trace.final_probability,
        evidence_receipts_count=len(trace.evidence_receipts),
    )
    return trace
