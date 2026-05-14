"""Treasury module — USDC↔USYC park/unpark operations for idle yield.

Controlled by ``TRADER_YIELD_MODE`` env var:
  - ``off`` (default): no-op. Existing pipeline unchanged.
  - ``park``: after each trace, residual USDC > 5 → park into USYC.
  - ``smart``: only park when sentinel verdict is REJECT/WARN.

When ``USYC_ARC_TESTNET_ADDRESS`` is unset or empty, the module switches to
*dry-run* mode: on-chain calls are skipped, a structured log is emitted, and
the ``treasury_events`` row is still inserted with ``tx_hash = NULL``.

See ``docs/research/usyc-arc-testnet-gap.md`` for the USYC Arc Testnet
deployment status.
"""

from __future__ import annotations

import os
import uuid
from decimal import Decimal
from typing import Any, Literal

import psycopg
import structlog

from prism_schemas.treasury import TreasuryEventCreate, TreasuryEventResult

logger = structlog.get_logger("prism.trader.treasury")

# ---------------------------------------------------------------------------
# Yield mode configuration
# ---------------------------------------------------------------------------

YieldMode = Literal["off", "park", "smart"]

_PARK_THRESHOLD_USDC = Decimal("5.0")
"""Residual USDC above this threshold triggers a park in ``park`` mode."""


def resolve_yield_mode() -> YieldMode:
    """Return the effective ``TRADER_YIELD_MODE``, defaulting to ``off``."""
    raw = os.environ.get("TRADER_YIELD_MODE", "off").strip().lower()
    if raw not in ("off", "park", "smart"):
        raise ValueError(
            f"TRADER_YIELD_MODE must be one of off|park|smart, got: {raw!r}"
        )
    mode: YieldMode = raw  # type: ignore[assignment]
    return mode


def _usyc_address() -> str:
    """Return the USYC contract address on Arc Testnet, or empty string."""
    return os.environ.get("USYC_ARC_TESTNET_ADDRESS", "").strip()


def _is_dry_run() -> bool:
    """True when USYC contract address is unavailable → dry-run mode."""
    return not _usyc_address()


def _dsn() -> str:
    """Return DATABASE_URL from environment."""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise OSError("DATABASE_URL is not set in environment")
    return url


def _agent_id() -> int:
    """Return the trader agent ID from environment or default."""
    raw = os.environ.get("TRADER_AGENT_ID", "1")
    return int(raw)


def _wallet_id() -> str:
    """Return the trader Circle wallet ID from environment."""
    wid = os.environ.get("CIRCLE_WALLET_TRADER_ID", "")
    if not wid:
        raise OSError("CIRCLE_WALLET_TRADER_ID is not set in environment")
    return wid


def _wallet_address() -> str:
    """Return the trader wallet address from environment."""
    addr = os.environ.get("CIRCLE_WALLET_TRADER_ADDRESS", "0x0")
    return addr


# ---------------------------------------------------------------------------
# Result model lives in prism_schemas.treasury.TreasuryEventResult (Pydantic v2)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Typed exceptions
# ---------------------------------------------------------------------------


class InsufficientUsycBalance(Exception):
    """Raised when the wallet's USYC balance is insufficient for unpark."""


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _persist_treasury_event(
    event: TreasuryEventCreate,
    dsn: str | None = None,
) -> str:
    """Insert a treasury_events row and return the generated UUID id.

    Uses the same psycopg pattern as :mod:`trader.persistence`.
    """
    dsn = dsn or _dsn()
    row_id = str(uuid.uuid4())

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO treasury_events "
            "(id, agent_id, wallet_address, event_type, usdc_amount, "
            "usyc_amount, rationale, tx_hash) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                row_id,
                event.agent_id,
                event.wallet_address,
                event.event_type,
                event.usdc_amount,
                event.usyc_amount,
                event.rationale,
                event.tx_hash,
            ),
        )
        conn.commit()

    logger.info(
        "treasury_event_persisted",
        event_id=row_id,
        event_type=event.event_type,
        usdc_amount=str(event.usdc_amount),
        tx_hash=event.tx_hash,
    )
    return row_id


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def park_idle_usdc(
    wallet_id: str,
    usdc_amount: Decimal,
    rationale: str,
) -> TreasuryEventResult:
    """Park idle USDC into USYC on Arc Testnet.

    Flow:
    1. If ``USYC_ARC_TESTNET_ADDRESS`` is empty → dry-run: skip on-chain
       call, log structured rationale, persist row with ``tx_hash = NULL``.
    2. Otherwise, call USYC mint via Circle DCW SDK → wait for tx → persist
       row with ``tx_hash``.

    Args:
        wallet_id: Circle wallet ID for the trader.
        usdc_amount: Amount of USDC to park.
        rationale: Human-readable reason for this park operation.

    Returns:
        TreasuryEventResult with the persisted event details.
    """
    dry_run = _is_dry_run()
    usyc_addr = _usyc_address()
    agent_id = _agent_id()
    wallet_address = _wallet_address()

    if dry_run:
        logger.info(
            "treasury_park_dry_run",
            wallet_id=wallet_id,
            usdc_amount=str(usdc_amount),
            rationale=rationale,
            gap_doc="docs/research/usyc-arc-testnet-gap.md",
        )
        event = TreasuryEventCreate(
            agent_id=agent_id,
            wallet_address=wallet_address,
            event_type="park",
            usdc_amount=usdc_amount,
            usyc_amount=None,
            rationale=f"{rationale} (dry_run)",
            tx_hash=None,
        )
        event_id = _persist_treasury_event(event)
        return TreasuryEventResult(
            event_id=event_id,
            event_type="park",
            usdc_amount=usdc_amount,
            tx_hash=None,
            rationale=event.rationale,
            dry_run=True,
        )

    # Live path: call USYC mint contract via Circle SDK
    from trader.chain import CircleChain as _CircleChain

    chain = _CircleChain()

    # USYC mint: approve USDC spend + mint USYC
    # For USYC, the standard ERC-4626 deposit(mint) ABI is:
    # deposit(uint256 assets, address receiver) returns (uint256 shares)
    # Convert USDC amount to smallest unit (6 decimals)
    amount_smallest = str(int(usdc_amount * Decimal("1_000_000")))

    logger.info(
        "treasury_park_executing",
        wallet_id=wallet_id,
        usdc_amount=str(usdc_amount),
        usyc_contract=usyc_addr,
    )

    try:
        tx_id = await chain.execute_contract(
            wallet_id=wallet_id,
            contract_address=usyc_addr,
            abi_function_signature="deposit(uint256,address)",
            abi_parameters=[amount_smallest, wallet_address],
        )

        # Wait for on-chain settlement
        tx_result: dict[str, Any] = await chain.wait_for_transaction(tx_id)
        tx_hash = tx_result.get("tx_hash")
    except Exception as exc:
        logger.error("treasury_park_chain_error", error=str(exc))
        # Fall back to dry-run-like record — still persist but with no tx_hash
        event = TreasuryEventCreate(
            agent_id=agent_id,
            wallet_address=wallet_address,
            event_type="park",
            usdc_amount=usdc_amount,
            usyc_amount=None,
            rationale=f"{rationale} (chain_error: {exc})",
            tx_hash=None,
        )
        event_id = _persist_treasury_event(event)
        return TreasuryEventResult(
            event_id=event_id,
            event_type="park",
            usdc_amount=usdc_amount,
            tx_hash=None,
            rationale=event.rationale,
            dry_run=True,
        )

    logger.info(
        "treasury_park_complete",
        wallet_id=wallet_id,
        usdc_amount=str(usdc_amount),
        tx_hash=tx_hash,
    )

    event = TreasuryEventCreate(
        agent_id=agent_id,
        wallet_address=wallet_address,
        event_type="park",
        usdc_amount=usdc_amount,
        usyc_amount=None,  # Would need on-chain read to determine; populated later
        rationale=rationale,
        tx_hash=tx_hash,
    )
    event_id = _persist_treasury_event(event)

    return TreasuryEventResult(
        event_id=event_id,
        event_type="park",
        usdc_amount=usdc_amount,
        tx_hash=tx_hash,
        rationale=rationale,
        dry_run=False,
    )


async def unpark_for_trade(
    wallet_id: str,
    usdc_target: Decimal,
) -> TreasuryEventResult:
    """Unpark USYC back to USDC for a trade.

    Flow:
    1. If dry-run mode → skip on-chain, persist row with ``tx_hash = NULL``.
    2. Check wallet USYC balance is sufficient.
    3. Call USYC redeem via Circle DCW SDK → wait for tx → persist.

    Args:
        wallet_id: Circle wallet ID for the trader.
        usdc_target: Amount of USDC needed for the trade.

    Returns:
        TreasuryEventResult with the persisted event details.

    Raises:
        InsufficientUsycBalance: If the wallet's USYC balance is below
            the implied USDC target and not in dry-run mode.
    """
    dry_run = _is_dry_run()
    usyc_addr = _usyc_address()
    agent_id = _agent_id()
    wallet_address = _wallet_address()

    if dry_run:
        logger.info(
            "treasury_unpark_dry_run",
            wallet_id=wallet_id,
            usdc_target=str(usdc_target),
            gap_doc="docs/research/usyc-arc-testnet-gap.md",
        )
        event = TreasuryEventCreate(
            agent_id=agent_id,
            wallet_address=wallet_address,
            event_type="unpark",
            usdc_amount=usdc_target,
            usyc_amount=None,
            rationale=f"unpark for trade (dry_run)",
            tx_hash=None,
        )
        event_id = _persist_treasury_event(event)
        return TreasuryEventResult(
            event_id=event_id,
            event_type="unpark",
            usdc_amount=usdc_target,
            tx_hash=None,
            rationale=event.rationale,
            dry_run=True,
        )

    # Live path: check USYC balance first
    from trader.chain import CircleChain as _CircleChain

    chain = _CircleChain()

    try:
        balances = await chain.get_wallet_balance(wallet_id)
    except Exception as exc:
        logger.error("treasury_unpark_balance_check_failed", error=str(exc))
        raise InsufficientUsycBalance(
            f"Cannot check USYC balance: {exc}"
        ) from exc

    usyc_balance = Decimal(str(balances.get("USYC", 0)))
    # USYC:USDC is roughly 1:1 (yield-accruing stablecoin).
    # For simplicity, we check if USYC balance ≥ usdc_target.
    if usyc_balance < usdc_target:
        raise InsufficientUsycBalance(
            f"Wallet USYC balance ({usyc_balance}) < target USDC ({usdc_target})"
        )

    # USYC redeem: withdraw(uint256 assets, address receiver, address owner)
    # Standard ERC-4626 withdraw ABI
    amount_smallest = str(int(usdc_target * Decimal("1_000_000")))

    logger.info(
        "treasury_unpark_executing",
        wallet_id=wallet_id,
        usdc_target=str(usdc_target),
        usyc_contract=usyc_addr,
    )

    try:
        tx_id = await chain.execute_contract(
            wallet_id=wallet_id,
            contract_address=usyc_addr,
            abi_function_signature="withdraw(uint256,address,address)",
            abi_parameters=[amount_smallest, wallet_address, wallet_address],
        )

        # Wait for on-chain settlement
        tx_result: dict[str, Any] = await chain.wait_for_transaction(tx_id)
        tx_hash = tx_result.get("tx_hash")
    except Exception as exc:
        logger.error("treasury_unpark_chain_error", error=str(exc))
        raise

    logger.info(
        "treasury_unpark_complete",
        wallet_id=wallet_id,
        usdc_target=str(usdc_target),
        tx_hash=tx_hash,
    )

    event = TreasuryEventCreate(
        agent_id=agent_id,
        wallet_address=wallet_address,
        event_type="unpark",
        usdc_amount=usdc_target,
        usyc_amount=None,  # Would need on-chain read to determine
        rationale="unpark for trade",
        tx_hash=tx_hash,
    )
    event_id = _persist_treasury_event(event)

    return TreasuryEventResult(
        event_id=event_id,
        event_type="unpark",
        usdc_amount=usdc_target,
        tx_hash=tx_hash,
        rationale="unpark for trade",
        dry_run=False,
    )


# ---------------------------------------------------------------------------
# Pipeline helpers — called from main.py at the treasury hook points
# ---------------------------------------------------------------------------


def should_park_after_trace(
    yield_mode: YieldMode,
    verdict_label: str | None,
    residual_usdc: Decimal,
) -> bool:
    """Decide whether to park residual USDC after a trace is generated.

    Args:
        yield_mode: The active TRADER_YIELD_MODE.
        verdict_label: The sentinel verdict (REJECT/WARN/PASS/ENDORSE) or None
            if sentinel was unreachable.
        residual_usdc: The trader wallet's remaining USDC after trace generation.

    Returns:
        True if ``park_idle_usdc`` should be called.
    """
    if yield_mode == "off":
        return False

    if yield_mode == "park":
        # Park whenever residual > threshold, regardless of verdict
        return residual_usdc > _PARK_THRESHOLD_USDC

    if yield_mode == "smart":
        # Only park on REJECT or WARN verdicts
        if verdict_label in ("REJECT", "WARN"):
            return residual_usdc > _PARK_THRESHOLD_USDC
        return False

    return False


def should_unpark_before_trade(
    yield_mode: YieldMode,
    verdict_label: str,
) -> bool:
    """Decide whether to unpark USYC before executing a trade.

    On the PASS branch, if yield_mode is park or smart, we need to ensure
    the trader has liquid USDC. We unpark only if there was a prior park
    (i.e., mode is not ``off``).

    Args:
        yield_mode: The active TRADER_YIELD_MODE.
        verdict_label: The sentinel verdict (must be PASS to reach this point).

    Returns:
        True if ``unpark_for_trade`` should be called.
    """
    if yield_mode == "off":
        return False

    # Both park and smart modes may have parked USDC previously,
    # so on PASS we unpark to ensure liquid USDC for the trade.
    # Only unpark when verdict is PASS (we're about to trade).
    return verdict_label == "PASS"
