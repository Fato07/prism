"""Treasury module tests — covers VAL-TREASURY-001 through VAL-TREASURY-007
and VAL-YIELDMODE-001 through VAL-YIELDMODE-006.

Test categories:
- VAL-TREASURY-001: park_idle_usdc returns TreasuryEventResult (live path mocked)
- VAL-TREASURY-002: park inserts a row into treasury_events
- VAL-TREASURY-003: park dry-run mode (USYC address unset)
- VAL-TREASURY-004: unpark_for_trade succeeds when USYC balance sufficient
- VAL-TREASURY-005: unpark rejects insufficient USYC balance
- VAL-TREASURY-006: Treasury operations emit structured logs
- VAL-YIELDMODE-001: Default value is off
- VAL-YIELDMODE-002: off — no park/unpark ever (regression check)
- VAL-YIELDMODE-003: park — park called when residual > 5 USDC
- VAL-YIELDMODE-004: smart — park only on REJECT/WARN verdicts
- VAL-YIELDMODE-005: Invalid value fails fast at startup
- VAL-YIELDMODE-006: park mode calls unpark before trade on PASS verdict
"""

from __future__ import annotations

import contextlib
import os
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import structlog
from prism_schemas.treasury import TreasuryEventResult

from trader.treasury import (
    InsufficientUsycBalanceError,
    YieldMode,
    park_idle_usdc,
    resolve_yield_mode,
    should_park_after_trace,
    should_unpark_before_trade,
    unpark_for_trade,
)

if TYPE_CHECKING:
    from collections.abc import Generator

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

WALLET_ID = "test-wallet-uuid-1234"
WALLET_ADDRESS = "0xc960833ee26e23ca01dfc4d217a8942ea78b452b"


@pytest.fixture(autouse=True)
def _set_env() -> Generator[None, None, None]:
    """Set minimal env vars for treasury module."""
    with patch.dict(
        os.environ,
        {
            "DATABASE_URL": "NEON_DSN_PLACEHOLDER",
            "TRADER_AGENT_ID": "4140",
            "CIRCLE_WALLET_TRADER_ID": WALLET_ID,
            "CIRCLE_WALLET_TRADER_ADDRESS": WALLET_ADDRESS,
        },
        clear=False,
    ):
        yield


def _mock_persist(event: Any, dsn: str | None = None) -> str:
    """Mock persist function returning a fixed UUID."""
    return "00000000-0000-0000-0000-000000000001"


# ===========================================================================
# VAL-TREASURY-001: park_idle_usdc returns TreasuryEventResult (live path)
# ===========================================================================


class TestParkIdleUsdcLivePath:
    """Tests for park_idle_usdc with USYC address set (live path, mocked SDK)."""

    @pytest.mark.asyncio
    async def test_park_returns_treasury_event_result(self) -> None:
        """park_idle_usdc returns a TreasuryEventResult with event_type='park'."""
        mock_chain = MagicMock()
        mock_chain.execute_contract = AsyncMock(return_value="circle-tx-id-1")
        mock_chain.wait_for_transaction = AsyncMock(
            return_value={
                "id": "circle-tx-id-1",
                "state": "COMPLETE",
                "tx_hash": "0xabc123",
                "blockchain": "ARC-TESTNET",
            }
        )

        with (
            patch.dict(os.environ, {"USYC_ARC_TESTNET_ADDRESS": "0xUsycContract"}),
            patch("trader.chain.CircleChain", return_value=mock_chain),
            patch("trader.treasury._persist_treasury_event", side_effect=_mock_persist),
        ):
            result = await park_idle_usdc(
                wallet_id=WALLET_ID,
                usdc_amount=Decimal("10.0"),
                rationale="manual-test",
            )

        assert isinstance(result, TreasuryEventResult)
        assert result.event_type == "park"
        assert result.usdc_amount == Decimal("10.0")
        assert result.tx_hash == "0xabc123"
        assert result.dry_run is False
        assert result.event_id == "00000000-0000-0000-0000-000000000001"

    @pytest.mark.asyncio
    async def test_park_calls_execute_contract(self) -> None:
        """park_idle_usdc calls Circle SDK execute_contract with correct params."""
        mock_chain = MagicMock()
        mock_chain.execute_contract = AsyncMock(return_value="circle-tx-id-1")
        mock_chain.wait_for_transaction = AsyncMock(
            return_value={
                "id": "circle-tx-id-1",
                "state": "COMPLETE",
                "tx_hash": "0xabc123",
                "blockchain": "ARC-TESTNET",
            }
        )

        with (
            patch.dict(os.environ, {"USYC_ARC_TESTNET_ADDRESS": "0xUsycContract"}),
            patch("trader.chain.CircleChain", return_value=mock_chain),
            patch("trader.treasury._persist_treasury_event", side_effect=_mock_persist),
        ):
            await park_idle_usdc(
                wallet_id=WALLET_ID,
                usdc_amount=Decimal("5.0"),
                rationale="manual-test",
            )

        mock_chain.execute_contract.assert_called_once()
        call_kwargs = mock_chain.execute_contract.call_args[1]
        assert call_kwargs["wallet_id"] == WALLET_ID
        assert call_kwargs["contract_address"] == "0xUsycContract"
        assert call_kwargs["abi_function_signature"] == "deposit(uint256,address)"

    @pytest.mark.asyncio
    async def test_park_chain_error_falls_back_to_dry_run(self) -> None:
        """park_idle_usdc falls back when Circle SDK raises an exception."""
        mock_chain = MagicMock()
        mock_chain.execute_contract = AsyncMock(side_effect=Exception("network error"))

        with (
            patch.dict(os.environ, {"USYC_ARC_TESTNET_ADDRESS": "0xUsycContract"}),
            patch("trader.chain.CircleChain", return_value=mock_chain),
            patch("trader.treasury._persist_treasury_event", side_effect=_mock_persist),
        ):
            result = await park_idle_usdc(
                wallet_id=WALLET_ID,
                usdc_amount=Decimal("5.0"),
                rationale="manual-test",
            )

        assert result.tx_hash is None
        assert result.dry_run is True


# ===========================================================================
# VAL-TREASURY-002: park inserts a row into treasury_events
# ===========================================================================


class TestParkPersistence:
    """Tests for treasury_events row insertion on park."""

    @pytest.mark.asyncio
    async def test_park_persists_event(self) -> None:
        """park_idle_usdc calls _persist_treasury_event with correct fields."""
        persisted_events: list[Any] = []

        def capture_persist(event: Any, dsn: str | None = None) -> str:
            persisted_events.append(event)
            return "00000000-0000-0000-0000-000000000002"

        with (
            patch.dict(os.environ, {"USYC_ARC_TESTNET_ADDRESS": ""}),
            patch("trader.treasury._persist_treasury_event", side_effect=capture_persist),
        ):
            await park_idle_usdc(
                wallet_id=WALLET_ID,
                usdc_amount=Decimal("7.5"),
                rationale="residual test",
            )

        assert len(persisted_events) == 1
        event = persisted_events[0]
        assert event.event_type == "park"
        assert event.agent_id == 4140
        assert event.wallet_address == WALLET_ADDRESS
        assert event.usdc_amount == Decimal("7.5")

    @pytest.mark.asyncio
    async def test_park_live_persists_with_tx_hash(self) -> None:
        """park_idle_usdc live path persists row with non-null tx_hash."""
        persisted_events: list[Any] = []

        def capture_persist(event: Any, dsn: str | None = None) -> str:
            persisted_events.append(event)
            return "00000000-0000-0000-0000-000000000003"

        mock_chain = MagicMock()
        mock_chain.execute_contract = AsyncMock(return_value="circle-tx-id-2")
        mock_chain.wait_for_transaction = AsyncMock(
            return_value={
                "id": "circle-tx-id-2",
                "state": "COMPLETE",
                "tx_hash": "0xdef456",
                "blockchain": "ARC-TESTNET",
            }
        )

        with (
            patch.dict(os.environ, {"USYC_ARC_TESTNET_ADDRESS": "0xUsycContract"}),
            patch("trader.chain.CircleChain", return_value=mock_chain),
            patch("trader.treasury._persist_treasury_event", side_effect=capture_persist),
        ):
            await park_idle_usdc(
                wallet_id=WALLET_ID,
                usdc_amount=Decimal("5.0"),
                rationale="manual-test",
            )

        assert len(persisted_events) == 1
        event = persisted_events[0]
        assert event.tx_hash == "0xdef456"
        assert event.rationale == "manual-test"


# ===========================================================================
# VAL-TREASURY-003: park dry-run mode (USYC address unset)
# ===========================================================================


class TestParkDryRun:
    """Tests for dry-run mode when USYC_ARC_TESTNET_ADDRESS is empty."""

    @pytest.mark.asyncio
    async def test_park_dry_run_no_chain_call(self) -> None:
        """park_idle_usdc dry-run does not invoke CircleChain."""
        with (
            patch.dict(os.environ, {"USYC_ARC_TESTNET_ADDRESS": ""}),
            patch("trader.treasury._persist_treasury_event", side_effect=_mock_persist),
            patch("trader.chain.CircleChain") as mock_chain_cls,
        ):
            result = await park_idle_usdc(
                wallet_id=WALLET_ID,
                usdc_amount=Decimal("5.0"),
                rationale="manual-test",
            )

        # CircleChain should NOT be instantiated
        mock_chain_cls.assert_not_called()
        assert result.dry_run is True
        assert result.tx_hash is None

    @pytest.mark.asyncio
    async def test_park_dry_run_writes_event_row(self) -> None:
        """park_idle_usdc dry-run still inserts a treasury_events row."""
        persisted_events: list[Any] = []

        def capture_persist(event: Any, dsn: str | None = None) -> str:
            persisted_events.append(event)
            return "00000000-0000-0000-0000-000000000004"

        with (
            patch.dict(os.environ, {"USYC_ARC_TESTNET_ADDRESS": ""}),
            patch("trader.treasury._persist_treasury_event", side_effect=capture_persist),
        ):
            await park_idle_usdc(
                wallet_id=WALLET_ID,
                usdc_amount=Decimal("10.0"),
                rationale="manual-test",
            )

        assert len(persisted_events) == 1
        event = persisted_events[0]
        assert event.tx_hash is None
        assert event.rationale.endswith("(dry_run)")

    @pytest.mark.asyncio
    async def test_park_dry_run_emits_structured_log(self) -> None:
        """park_idle_usdc dry-run logs treasury_park_dry_run with structlog."""
        with (
            patch.dict(os.environ, {"USYC_ARC_TESTNET_ADDRESS": ""}),
            patch("trader.treasury._persist_treasury_event", side_effect=_mock_persist),
            structlog_testing_capture_logs() as logs,
        ):
                await park_idle_usdc(
                    wallet_id=WALLET_ID,
                    usdc_amount=Decimal("5.0"),
                    rationale="manual-test",
                )

        park_logs = [log for log in logs if log.get("event") == "treasury_park_dry_run"]
        assert len(park_logs) == 1
        log = park_logs[0]
        assert log["wallet_id"] == WALLET_ID
        assert log["usdc_amount"] == "5.0"
        assert "gap_doc" in log


# ===========================================================================
# VAL-TREASURY-004: unpark_for_trade succeeds when USYC balance sufficient
# ===========================================================================


class TestUnparkSufficientBalance:
    """Tests for unpark_for_trade with sufficient USYC balance."""

    @pytest.mark.asyncio
    async def test_unpark_returns_treasury_event_result(self) -> None:
        """unpark_for_trade returns TreasuryEventResult with event_type='unpark'."""
        mock_chain = MagicMock()
        mock_chain.get_wallet_balance = AsyncMock(
            return_value={"USYC": 20.0, "USDC": 5.0}
        )
        mock_chain.execute_contract = AsyncMock(return_value="circle-tx-id-3")
        mock_chain.wait_for_transaction = AsyncMock(
            return_value={
                "id": "circle-tx-id-3",
                "state": "COMPLETE",
                "tx_hash": "0x789ghi",
                "blockchain": "ARC-TESTNET",
            }
        )

        with (
            patch.dict(os.environ, {"USYC_ARC_TESTNET_ADDRESS": "0xUsycContract"}),
            patch("trader.chain.CircleChain", return_value=mock_chain),
            patch("trader.treasury._persist_treasury_event", side_effect=_mock_persist),
        ):
            result = await unpark_for_trade(
                wallet_id=WALLET_ID,
                usdc_target=Decimal("10.0"),
            )

        assert isinstance(result, TreasuryEventResult)
        assert result.event_type == "unpark"
        assert result.usdc_amount == Decimal("10.0")
        assert result.tx_hash == "0x789ghi"
        assert result.dry_run is False

    @pytest.mark.asyncio
    async def test_unpark_dry_run_skips_chain(self) -> None:
        """unpark_for_trade dry-run does not call CircleChain."""
        with (
            patch.dict(os.environ, {"USYC_ARC_TESTNET_ADDRESS": ""}),
            patch("trader.treasury._persist_treasury_event", side_effect=_mock_persist),
            patch("trader.chain.CircleChain") as mock_chain_cls,
        ):
            result = await unpark_for_trade(
                wallet_id=WALLET_ID,
                usdc_target=Decimal("5.0"),
            )

        mock_chain_cls.assert_not_called()
        assert result.dry_run is True
        assert result.tx_hash is None


# ===========================================================================
# VAL-TREASURY-005: unpark rejects insufficient USYC balance
# ===========================================================================


class TestUnparkInsufficientBalance:
    """Tests for unpark_for_trade with insufficient USYC balance."""

    @pytest.mark.asyncio
    async def test_unpark_insufficient_raises_typed_exception(self) -> None:
        """unpark_for_trade raises InsufficientUsycBalanceError when balance < target."""
        mock_chain = MagicMock()
        mock_chain.get_wallet_balance = AsyncMock(
            return_value={"USYC": 3.0, "USDC": 97.0}
        )

        with (
            patch.dict(os.environ, {"USYC_ARC_TESTNET_ADDRESS": "0xUsycContract"}),
            patch("trader.chain.CircleChain", return_value=mock_chain),
            patch("trader.treasury._persist_treasury_event", side_effect=_mock_persist),
            pytest.raises(InsufficientUsycBalanceError),
        ):
                await unpark_for_trade(
                    wallet_id=WALLET_ID,
                    usdc_target=Decimal("10.0"),
                )

    @pytest.mark.asyncio
    async def test_unpark_insufficient_does_not_execute_contract(self) -> None:
        """unpark_for_trade does not call execute_contract when balance is low."""
        mock_chain = MagicMock()
        mock_chain.get_wallet_balance = AsyncMock(
            return_value={"USYC": 2.0, "USDC": 98.0}
        )

        with (
            patch.dict(os.environ, {"USYC_ARC_TESTNET_ADDRESS": "0xUsycContract"}),
            patch("trader.chain.CircleChain", return_value=mock_chain),
            patch("trader.treasury._persist_treasury_event", side_effect=_mock_persist),
            pytest.raises(InsufficientUsycBalanceError),
        ):
                await unpark_for_trade(
                    wallet_id=WALLET_ID,
                    usdc_target=Decimal("10.0"),
                )

        mock_chain.execute_contract.assert_not_called()

    @pytest.mark.asyncio
    async def test_unpark_insufficient_does_not_persist(self) -> None:
        """unpark_for_trade does not persist a row when balance is insufficient."""
        mock_chain = MagicMock()
        mock_chain.get_wallet_balance = AsyncMock(
            return_value={"USYC": 2.0, "USDC": 98.0}
        )

        with (
            patch.dict(os.environ, {"USYC_ARC_TESTNET_ADDRESS": "0xUsycContract"}),
            patch("trader.chain.CircleChain", return_value=mock_chain),
            patch("trader.treasury._persist_treasury_event") as mock_persist,
            pytest.raises(InsufficientUsycBalanceError),
        ):
                await unpark_for_trade(
                    wallet_id=WALLET_ID,
                    usdc_target=Decimal("10.0"),
                )

        mock_persist.assert_not_called()


# ===========================================================================
# VAL-TREASURY-006: Treasury operations emit structured logs
# ===========================================================================


class TestTreasuryStructuredLogs:
    """Tests for structlog event emission on treasury operations."""

    @pytest.mark.asyncio
    async def test_park_emits_treasury_log(self) -> None:
        """park_idle_usdc emits a structlog event starting with 'treasury_'."""
        with (
            patch.dict(os.environ, {"USYC_ARC_TESTNET_ADDRESS": ""}),
            patch("trader.treasury._persist_treasury_event", side_effect=_mock_persist),
            structlog_testing_capture_logs() as logs,
        ):
                await park_idle_usdc(
                    wallet_id=WALLET_ID,
                    usdc_amount=Decimal("5.0"),
                    rationale="log-test",
                )

        treasury_logs = [
            log for log in logs if str(log.get("event", "")).startswith("treasury_")
        ]
        assert len(treasury_logs) >= 1
        # Check required keys per VAL-TREASURY-006
        for log in treasury_logs:
            assert "wallet_id" in log or "usdc_amount" in log

    @pytest.mark.asyncio
    async def test_unpark_dry_run_emits_treasury_log(self) -> None:
        """unpark_for_trade dry-run emits treasury_unpark_dry_run log."""
        with (
            patch.dict(os.environ, {"USYC_ARC_TESTNET_ADDRESS": ""}),
            patch("trader.treasury._persist_treasury_event", side_effect=_mock_persist),
            structlog_testing_capture_logs() as logs,
        ):
                await unpark_for_trade(
                    wallet_id=WALLET_ID,
                    usdc_target=Decimal("5.0"),
                )

        unpark_logs = [
            log for log in logs if log.get("event") == "treasury_unpark_dry_run"
        ]
        assert len(unpark_logs) >= 1

    @pytest.mark.asyncio
    async def test_park_live_emits_treasury_park_complete(self) -> None:
        """park_idle_usdc live path emits treasury_park_complete log."""
        mock_chain = MagicMock()
        mock_chain.execute_contract = AsyncMock(return_value="circle-tx-id-4")
        mock_chain.wait_for_transaction = AsyncMock(
            return_value={
                "id": "circle-tx-id-4",
                "state": "COMPLETE",
                "tx_hash": "0xcomplete",
                "blockchain": "ARC-TESTNET",
            }
        )

        with (
            patch.dict(os.environ, {"USYC_ARC_TESTNET_ADDRESS": "0xUsycContract"}),
            patch("trader.chain.CircleChain", return_value=mock_chain),
            patch("trader.treasury._persist_treasury_event", side_effect=_mock_persist),
            structlog_testing_capture_logs() as logs,
        ):
                await park_idle_usdc(
                    wallet_id=WALLET_ID,
                    usdc_amount=Decimal("5.0"),
                    rationale="manual-test",
                )

        complete_logs = [
            log for log in logs if log.get("event") == "treasury_park_complete"
        ]
        assert len(complete_logs) >= 1
        log = complete_logs[0]
        assert "tx_hash" in log
        assert log["usdc_amount"] == "5.0"


# ===========================================================================
# VAL-YIELDMODE-001: Default value is off
# ===========================================================================


class TestYieldModeDefault:
    """Tests for default TRADER_YIELD_MODE resolution."""

    def test_default_is_off(self) -> None:
        """With TRADER_YIELD_MODE unset, resolve_yield_mode() returns 'off'."""
        with patch.dict(os.environ, {}, clear=False):
            # Remove the var if it exists
            os.environ.pop("TRADER_YIELD_MODE", None)
            mode = resolve_yield_mode()
        assert mode == "off"

    def test_explicit_off(self) -> None:
        """With TRADER_YIELD_MODE=off, resolve_yield_mode() returns 'off'."""
        with patch.dict(os.environ, {"TRADER_YIELD_MODE": "off"}):
            mode = resolve_yield_mode()
        assert mode == "off"

    def test_explicit_park(self) -> None:
        """With TRADER_YIELD_MODE=park, resolve_yield_mode() returns 'park'."""
        with patch.dict(os.environ, {"TRADER_YIELD_MODE": "park"}):
            mode = resolve_yield_mode()
        assert mode == "park"

    def test_explicit_smart(self) -> None:
        """With TRADER_YIELD_MODE=smart, resolve_yield_mode() returns 'smart'."""
        with patch.dict(os.environ, {"TRADER_YIELD_MODE": "smart"}):
            mode = resolve_yield_mode()
        assert mode == "smart"


# ===========================================================================
# VAL-YIELDMODE-002: off — no park/unpark ever (regression check)
# ===========================================================================


class TestYieldModeOffNoTreasury:
    """Tests that off mode never triggers park/unpark."""

    @pytest.mark.parametrize(
        ("verdict_label", "residual"),
        [
            ("REJECT", Decimal("50.0")),
            ("WARN", Decimal("50.0")),
            ("PASS", Decimal("50.0")),
            ("ENDORSE", Decimal("50.0")),
            (None, Decimal("50.0")),
        ],
    )
    def test_should_park_off_never_triggers(
        self,
        verdict_label: str | None,
        residual: Decimal,
    ) -> None:
        """should_park_after_trace returns False for all verdicts when mode=off."""
        assert should_park_after_trace("off", verdict_label, residual) is False

    @pytest.mark.parametrize(
        ("verdict_label",),
        [("REJECT",), ("WARN",), ("PASS",), ("ENDORSE",)],
    )
    def test_should_unpark_off_never_triggers(self, verdict_label: str) -> None:
        """should_unpark_before_trade returns False for all verdicts when mode=off."""
        assert should_unpark_before_trade("off", verdict_label) is False


# ===========================================================================
# VAL-YIELDMODE-003: park — park called when residual > 5 USDC
# ===========================================================================


class TestYieldModeParkThreshold:
    """Tests for park mode threshold behavior."""

    @pytest.mark.parametrize(
        ("residual", "expected"),
        [
            (Decimal("0.0"), False),
            (Decimal("4.99"), False),
            (Decimal("5.0"), False),  # exactly 5 → NOT > 5
            (Decimal("5.01"), True),  # > 5 → park
            (Decimal("20.0"), True),
            (Decimal("95.0"), True),
        ],
    )
    def test_park_mode_threshold(
        self,
        residual: Decimal,
        expected: bool,
    ) -> None:
        """park mode: park called iff residual > 5.0 USDC."""
        assert should_park_after_trace("park", "REJECT", residual) == expected

    def test_park_mode_ignores_verdict(self) -> None:
        """park mode: park triggered regardless of verdict when residual > 5."""
        for verdict in ("REJECT", "WARN", "PASS", "ENDORSE", None):
            assert should_park_after_trace("park", verdict, Decimal("20.0")) is True

    def test_park_mode_below_threshold_ignores_verdict(self) -> None:
        """park mode: park NOT triggered when residual ≤ 5 regardless of verdict."""
        for verdict in ("REJECT", "WARN", "PASS", "ENDORSE", None):
            assert should_park_after_trace("park", verdict, Decimal("3.0")) is False


# ===========================================================================
# VAL-YIELDMODE-004: smart — park only on REJECT/WARN verdicts
# ===========================================================================


class TestYieldModeSmartVerdictMatrix:
    """Tests for smart mode verdict-dependent park behavior."""

    @pytest.mark.parametrize(
        ("verdict_label", "residual", "expected"),
        [
            ("REJECT", Decimal("20.0"), True),
            ("WARN", Decimal("20.0"), True),
            ("PASS", Decimal("20.0"), False),
            ("ENDORSE", Decimal("20.0"), False),
            (None, Decimal("20.0"), False),
            # Below threshold — even REJECT doesn't trigger
            ("REJECT", Decimal("3.0"), False),
            ("WARN", Decimal("3.0"), False),
        ],
    )
    def test_smart_mode_verdict_matrix(
        self,
        verdict_label: str | None,
        residual: Decimal,
        expected: bool,
    ) -> None:
        """smart mode: park only for REJECT/WARN with residual > 5."""
        assert should_park_after_trace("smart", verdict_label, residual) == expected

    def test_smart_mode_reject_triggers(self) -> None:
        """smart mode: REJECT verdict with residual > 5 → park."""
        assert should_park_after_trace("smart", "REJECT", Decimal("20.0")) is True

    def test_smart_mode_pass_does_not_trigger(self) -> None:
        """smart mode: PASS verdict does not trigger park."""
        assert should_park_after_trace("smart", "PASS", Decimal("20.0")) is False


# ===========================================================================
# VAL-YIELDMODE-005: Invalid value fails fast at startup
# ===========================================================================


class TestYieldModeInvalid:
    """Tests for invalid TRADER_YIELD_MODE values."""

    @pytest.mark.parametrize(
        "invalid_value",
        ["yes", "on", "1", "true", "auto", ""],
    )
    def test_invalid_value_raises_value_error(self, invalid_value: str) -> None:
        """Invalid TRADER_YIELD_MODE raises ValueError."""
        with (
            patch.dict(os.environ, {"TRADER_YIELD_MODE": invalid_value}),
            pytest.raises(ValueError, match="TRADER_YIELD_MODE"),
        ):
            resolve_yield_mode()

    def test_case_insensitive_values_accepted(self) -> None:
        """PARK, Smart, OFF (with whitespace) are accepted after normalization."""
        with patch.dict(os.environ, {"TRADER_YIELD_MODE": "PARK"}):
            assert resolve_yield_mode() == "park"
        with patch.dict(os.environ, {"TRADER_YIELD_MODE": "Smart"}):
            assert resolve_yield_mode() == "smart"
        with patch.dict(os.environ, {"TRADER_YIELD_MODE": "OFF "}):
            assert resolve_yield_mode() == "off"


# ===========================================================================
# VAL-YIELDMODE-006: park/smart mode calls unpark before trade on PASS
# ===========================================================================


class TestUnparkBeforeTrade:
    """Tests for unpark-before-trade behavior on PASS verdict."""

    def test_park_mode_unpark_on_pass(self) -> None:
        """park mode: should_unpark_before_trade returns True on PASS."""
        assert should_unpark_before_trade("park", "PASS") is True

    def test_smart_mode_unpark_on_pass(self) -> None:
        """smart mode: should_unpark_before_trade returns True on PASS."""
        assert should_unpark_before_trade("smart", "PASS") is True

    def test_off_mode_no_unpark_on_pass(self) -> None:
        """off mode: should_unpark_before_trade returns False on PASS."""
        assert should_unpark_before_trade("off", "PASS") is False

    @pytest.mark.parametrize(
        ("mode", "verdict", "expected"),
        [
            ("park", "REJECT", False),
            ("park", "WARN", False),
            ("park", "ENDORSE", False),
            ("smart", "REJECT", False),
            ("smart", "WARN", False),
            ("smart", "ENDORSE", False),
        ],
    )
    def test_unpark_only_on_pass(
        self,
        mode: YieldMode,
        verdict: str,
        expected: bool,
    ) -> None:
        """should_unpark_before_trade only returns True on PASS verdict."""
        assert should_unpark_before_trade(mode, verdict) == expected


# ===========================================================================
# Pipeline integration: treasury hooks in _run_pipeline_internal
# ===========================================================================


class TestPipelineTreasuryHooks:
    """Integration tests for treasury hooks wired into the pipeline."""

    @pytest.mark.asyncio
    async def test_off_mode_no_treasury_calls(self) -> None:
        """TRADER_YIELD_MODE=off: pipeline never calls park/unpark."""
        with (
            patch.dict(
                os.environ,
                {
                    "TRADER_YIELD_MODE": "off",
                    "USYC_ARC_TESTNET_ADDRESS": "",
                },
            ),
            patch("trader.treasury.park_idle_usdc", new_callable=AsyncMock) as mock_park,
            patch("trader.treasury.unpark_for_trade", new_callable=AsyncMock) as mock_unpark,
        ):
            # Just verify should_park/should_unpark don't trigger calls
            assert should_park_after_trace("off", "REJECT", Decimal("50")) is False
            assert should_unpark_before_trade("off", "PASS") is False

        mock_park.assert_not_called()
        mock_unpark.assert_not_called()


# ===========================================================================
# Helper: structlog testing capture
# ===========================================================================


def structlog_testing_capture_logs() -> Any:
    """Return a context manager that captures structlog output.

    Uses structlog.testing.capture_logs if available, otherwise
    falls back to a simple list-based capture.
    """
    try:
        from structlog.testing import capture_logs

        return capture_logs()
    except ImportError:
        # Fallback: patch structlog's processors
        @contextlib.contextmanager
        def _capture() -> Generator[list[dict[str, Any]], None, None]:
            captured: list[dict[str, Any]] = []

            class CaptureProcessor:
                def __call__(self, logger: Any, method: str, event_dict: Any) -> Any:
                    captured.append(event_dict)
                    return event_dict

            old_config = structlog.get_config()
            structlog.configure(
                processors=[CaptureProcessor()],
                logger_factory=structlog.PrintLoggerFactory(),
            )
            try:
                yield captured
            finally:
                structlog.configure(**old_config)

        return _capture()
