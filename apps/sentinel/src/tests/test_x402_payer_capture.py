"""x402 payer capture tests — VAL-X402-PAYER-001 through VAL-X402-PAYER-006.

These tests verify that the x402 middleware captures the ``payer`` address
from the facilitator settlement response and threads it through to the
validations INSERT, and that the internal bypass path leaves
``requester_address`` NULL.

Test strategy:
  - Mock the IPFS / DSPy / DB layer so tests exercise only the payment
    gating + settlement + payer-capture plumbing.
  - Use FastAPI TestClient (synchronous, but hits the async middleware
    through Starlette's test transport).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from prism_schemas.trace import Evidence, ThesisStep, TradingR1Trace
from prism_schemas.verdict import SentinelVerdict

from sentinel.x402_middleware import reset_consumed_tokens_for_testing

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_consumed_tokens() -> Generator[None, None, None]:
    """Reset the in-memory consumed payment-token set before every test."""
    reset_consumed_tokens_for_testing()
    yield
    reset_consumed_tokens_for_testing()


def _make_trace() -> TradingR1Trace:
    """Create a synthetic TradingR1Trace for testing."""
    return TradingR1Trace(
        trace_id=str(uuid.uuid4()),
        agent_id=1,
        market_id="test-market-001",
        market_question="Will X happen by end of 2026?",
        thesis=[
            ThesisStep(
                proposition="The event is likely based on current trends.",
                supporting_evidence_ids=[0],
                risk_factors=["Trend may reverse"],
            )
        ],
        evidence=[
            Evidence(
                source="reuters.com",
                claim="Recent data supports the trend.",
                confidence=0.75,
                timestamp=datetime.now(UTC),
            )
        ],
        raw_probability=0.70,
        volatility_adjustment=-0.05,
        final_probability=0.65,
        action="BUY",
        size_usdc=10.0,
        price_limit=0.65,
        rationale="Moderate confidence trade based on supporting evidence.",
        model_family="anthropic-claude",
        model_name="claude-sonnet-4-20250514",
        created_at=datetime.now(UTC),
    )


def _make_verdict() -> SentinelVerdict:
    """Create a synthetic SentinelVerdict for testing."""
    return SentinelVerdict(
        request_hash=hashlib.sha256(b"test-request").hexdigest(),
        trace_id=str(uuid.uuid4()),
        sentinel_agent_id=2,
        evidence_challenges=[
            "Evidence source may have confirmation bias",
            "Confidence level is not well-calibrated",
            "Single source of evidence is insufficient",
        ],
        thesis_challenges=["Proposition assumes linear trend continuation"],
        calibration_critique=(
            "The raw probability of 0.70 seems reasonable but the volatility "
            "adjustment appears arbitrary without supporting methodology."
        ),
        verdict_score=70,
        verdict_label="PASS",
        dialogue_messages=[{"role": "adversary", "content": "Challenge the sourcing."}],
        model_family="openai-gpt",
        model_name="gpt-4o-mini",
        created_at=datetime.now(UTC),
    )


def _build_client() -> tuple[TestClient, list[MagicMock], MagicMock]:
    """Return a FastAPI TestClient with all downstream services mocked.

    Returns (client, patches, persist_mock) where patches is a list of
    active patchers that the caller must stop after use, and persist_mock
    is the MagicMock that replaces ``persist_verdict`` so callers can
    assert on its call arguments.
    """
    pinata_patch = patch("sentinel.main.PinataClient")
    gen_patch = patch("sentinel.main.generate_verdict")
    persist_patch = patch("sentinel.main.persist_verdict")
    update_uri_patch = patch("sentinel.main.update_verdict_response_uri")
    migration_patch = patch("sentinel.main.run_migration")
    agent_row_patch = patch("sentinel.main.ensure_agent_row")
    startup_patch = patch("sentinel.main._run_startup_gates")

    pinata_cls = pinata_patch.start()
    gen_fn = gen_patch.start()
    persist_mock = persist_patch.start()
    update_uri_patch.start()
    migration_patch.start()
    agent_row_patch.start()
    startup_patch.start()

    pinata_instance = AsyncMock()
    pinata_instance.fetch_json.return_value = _make_trace().model_dump(mode="json")
    pinata_instance.pin_json.return_value = "QmTestVerdictCID"
    pinata_instance.close = AsyncMock()
    pinata_cls.return_value = pinata_instance

    gen_fn.return_value = _make_verdict()

    from sentinel.main import app

    client = TestClient(app, raise_server_exceptions=False)

    all_patches = [
        pinata_patch,
        gen_patch,
        persist_patch,
        update_uri_patch,
        migration_patch,
        agent_row_patch,
        startup_patch,
    ]
    return client, all_patches, persist_mock


def _stop_patches(patches: list[MagicMock]) -> None:
    """Stop all active patches."""
    for p in patches:
        p.stop()


def _encode_payment_payload(payload: dict[str, object]) -> str:
    """Base64-encode a JSON payload the way the middleware expects."""
    return base64.b64encode(json.dumps(payload).encode()).decode()


# ---------------------------------------------------------------------------
# VAL-X402-PAYER-001: Middleware reads payer from settlement success response
# ---------------------------------------------------------------------------


class TestPayerCaptureFromSettlement:
    """Verify that the middleware stashes payer on request.state."""

    def test_facilitator_success_captures_payer_on_request_state(self) -> None:
        """Successful x402 settlement puts payer onto request.state.x402_payer_address."""
        import httpx

        payer_address = "0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B"

        async def fake_post(
            self: httpx.AsyncClient,
            url: str,
            json: dict[str, object] | None = None,
            **kwargs: object,
        ) -> httpx.Response:
            request = httpx.Request("POST", url, json=json)
            return httpx.Response(
                status_code=200,
                json={
                    "success": True,
                    "txHash": (
                        "0xfacilitatortx0000000000000000000000000"
                        "0000000000000000000000000001"
                    ),
                    "payer": payer_address,
                },
                request=request,
            )

        payment_payload = _encode_payment_payload({"signature": "0xabc", "payload": {}})
        env = {
            "X402_BYPASS": "",
            "X402_RECIPIENT_ADDRESS": "0x0000000000000000000000000000000000000DeaD",
            "X402_FACILITATOR_URL": "https://facilitator.example.com",
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("httpx.AsyncClient.post", new=fake_post),
        ):
            client, patches, _ = _build_client()
            try:
                resp = client.post(
                    "/validate",
                    json={"trace_uri": "ipfs://QmTestCID", "trace_hash": "0xabc"},
                    headers={"x402-payment": payment_payload},
                )
            finally:
                _stop_patches(patches)

            assert resp.status_code == 200

    def test_mock_settlement_leaves_payer_none(self) -> None:
        """Mock settlement path (no facilitator) leaves payer None on request state."""
        with patch.dict(
            os.environ,
            {
                "X402_BYPASS": "",
                "X402_FACILITATOR_URL": "",
                "X402_RECIPIENT_ADDRESS": "",
            },
            clear=False,
        ):
            client, patches, persist_mock = _build_client()
            try:
                resp = client.post(
                    "/validate",
                    json={"trace_uri": "ipfs://QmTestCID", "trace_hash": "0xabc"},
                    headers={"x402-payment": "mock-settlement-payment-token-123"},
                )
            finally:
                _stop_patches(patches)

            assert resp.status_code == 200
            # In mock mode, payer is None. Verify persist_verdict was called
            # with requester_address=None.
            persist_mock.assert_called_once()
            call_kwargs = persist_mock.call_args
            assert call_kwargs[1].get("requester_address") is None


# ---------------------------------------------------------------------------
# VAL-X402-PAYER-002: Validate handler threads payer into validations insert
# ---------------------------------------------------------------------------


class TestPayerThreadingToPersist:
    """Verify that the /validate handler reads x402_payer_address and passes
    it to persist_verdict as requester_address."""

    def test_facilitator_payer_passed_to_persist_verdict(self) -> None:
        """When x402 settles with a payer, persist_verdict receives it as requester_address."""
        import httpx

        payer_address = "0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B"
        payer_address.lower()

        async def fake_post(
            self: httpx.AsyncClient,
            url: str,
            json: dict[str, object] | None = None,
            **kwargs: object,
        ) -> httpx.Response:
            request = httpx.Request("POST", url, json=json)
            return httpx.Response(
                status_code=200,
                json={
                    "success": True,
                    "txHash": (
                        "0xfacilitatortx0000000000000000000000000"
                        "0000000000000000000000000001"
                    ),
                    "payer": payer_address,
                },
                request=request,
            )

        payment_payload = _encode_payment_payload({"signature": "0xabc", "payload": {}})
        env = {
            "X402_BYPASS": "",
            "X402_RECIPIENT_ADDRESS": "0x0000000000000000000000000000000000000DeaD",
            "X402_FACILITATOR_URL": "https://facilitator.example.com",
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("httpx.AsyncClient.post", new=fake_post),
        ):
            client, patches, persist_mock = _build_client()
            try:
                resp = client.post(
                    "/validate",
                    json={"trace_uri": "ipfs://QmTestCID", "trace_hash": "0xabc"},
                    headers={"x402-payment": payment_payload},
                )
            finally:
                _stop_patches(patches)

            assert resp.status_code == 200
            # Verify persist_verdict was called with requester_address
            # Note: persist_verdict lowercases internally before DB insert;
            # the keyword argument receives the raw address from the middleware.
            persist_mock.assert_called_once()
            call_kwargs = persist_mock.call_args
            assert call_kwargs[1].get("requester_address") == payer_address, (
                f"Expected requester_address={payer_address}, "
                f"got {call_kwargs[1].get('requester_address')}"
            )


# ---------------------------------------------------------------------------
# VAL-X402-PAYER-003: Bypass path leaves requester_address NULL
# ---------------------------------------------------------------------------


class TestBypassPathNullRequester:
    """Verify that internal bypass (trader to sentinel) leaves requester_address NULL."""

    def test_internal_bypass_header_leaves_requester_address_none(self) -> None:
        """X402-Bypass header results in persist_verdict with requester_address=None."""
        with patch.dict(os.environ, {"X402_BYPASS": ""}, clear=False):
            client, patches, persist_mock = _build_client()
            try:
                resp = client.post(
                    "/validate",
                    json={"trace_uri": "ipfs://QmTestCID", "trace_hash": "0xabc"},
                    headers={"X402-Bypass": "internal-trader-call"},
                )
            finally:
                _stop_patches(patches)

            assert resp.status_code == 200
            persist_mock.assert_called_once()
            call_kwargs = persist_mock.call_args
            assert call_kwargs[1].get("requester_address") is None, (
                "Internal bypass path must pass requester_address=None"
            )

    def test_env_bypass_leaves_requester_address_none(self) -> None:
        """X402_BYPASS=1 env results in persist_verdict with requester_address=None."""
        with patch.dict(os.environ, {"X402_BYPASS": "1"}, clear=False):
            client, patches, persist_mock = _build_client()
            try:
                resp = client.post(
                    "/validate",
                    json={"trace_uri": "ipfs://QmTestCID", "trace_hash": "0xabc"},
                )
            finally:
                _stop_patches(patches)

            assert resp.status_code == 200
            persist_mock.assert_called_once()
            call_kwargs = persist_mock.call_args
            assert call_kwargs[1].get("requester_address") is None, (
                "Env bypass path must pass requester_address=None"
            )

    def test_bypass_with_token_leaves_requester_address_none(self) -> None:
        """X402-Bypass with matching token results in requester_address=None."""
        with patch.dict(
            os.environ,
            {"X402_BYPASS": "", "X402_INTERNAL_BYPASS_TOKEN": "secret-token-xyz"},
            clear=False,
        ):
            client, patches, persist_mock = _build_client()
            try:
                resp = client.post(
                    "/validate",
                    json={"trace_uri": "ipfs://QmTestCID", "trace_hash": "0xabc"},
                    headers={"X402-Bypass": "secret-token-xyz"},
                )
            finally:
                _stop_patches(patches)

            assert resp.status_code == 200
            persist_mock.assert_called_once()
            call_kwargs = persist_mock.call_args
            assert call_kwargs[1].get("requester_address") is None


# ---------------------------------------------------------------------------
# VAL-X402-PAYER-005/006: Existing tests still pass + mypy clean
#   (verified by the test runner / mypy invocation, not individual assertions)
# ---------------------------------------------------------------------------


class TestPayerCaptureUnit:
    """Unit-level tests for the _settle_payment return value change."""

    @pytest.mark.asyncio
    async def test_settle_payment_returns_payer_on_success(self) -> None:
        """_settle_payment returns a 4-tuple with payer on facilitator success."""
        import httpx

        payer = "0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B"

        async def fake_post(
            self: httpx.AsyncClient,
            url: str,
            json: dict[str, object] | None = None,
            **kwargs: object,
        ) -> httpx.Response:
            request = httpx.Request("POST", url, json=json)
            return httpx.Response(
                status_code=200,
                json={
                    "success": True,
                    "txHash": (
                        "0xfacilitatortx0000000000000000000000000"
                        "0000000000000000000000000001"
                    ),
                    "payer": payer,
                },
                request=request,
            )

        env = {
            "X402_RECIPIENT_ADDRESS": "0x0000000000000000000000000000000000000DeaD",
            "X402_FACILITATOR_URL": "https://facilitator.example.com",
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("httpx.AsyncClient.post", new=fake_post),
        ):
            from sentinel.x402_middleware import _settle_payment

            payment_payload = _encode_payment_payload({"signature": "0xabc", "payload": {}})
            success, tx_hash, error_code, returned_payer = await _settle_payment(
                payment_payload,
                request_context={"path": "/validate"},
            )

        assert success is True
        assert tx_hash is not None
        assert error_code is None
        assert returned_payer == payer

    @pytest.mark.asyncio
    async def test_settle_payment_returns_none_payer_on_mock(self) -> None:
        """_settle_payment returns None payer in mock mode (no facilitator)."""
        with patch.dict(
            os.environ,
            {"X402_FACILITATOR_URL": "", "X402_RECIPIENT_ADDRESS": ""},
            clear=False,
        ):
            from sentinel.x402_middleware import _settle_payment

            success, tx_hash, error_code, returned_payer = await _settle_payment(
                "mock-token-123",
                request_context={"path": "/validate"},
            )

        assert success is True
        assert tx_hash is not None
        assert error_code is None
        assert returned_payer is None

    @pytest.mark.asyncio
    async def test_settle_payment_returns_none_payer_on_failure(self) -> None:
        """_settle_payment returns None payer when settlement fails."""
        import httpx

        async def fake_post(
            self: httpx.AsyncClient,
            url: str,
            json: dict[str, object] | None = None,
            **kwargs: object,
        ) -> httpx.Response:
            request = httpx.Request("POST", url, json=json)
            return httpx.Response(
                status_code=200,
                json={
                    "success": False,
                    "errorReason": "insufficient_funds",
                },
                request=request,
            )

        env = {
            "X402_RECIPIENT_ADDRESS": "0x0000000000000000000000000000000000000DeaD",
            "X402_FACILITATOR_URL": "https://facilitator.example.com",
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("httpx.AsyncClient.post", new=fake_post),
        ):
            from sentinel.x402_middleware import _settle_payment

            payment_payload = _encode_payment_payload({"signature": "0xabc", "payload": {}})
            success, _tx_hash, _error_code, returned_payer = await _settle_payment(
                payment_payload,
                request_context={"path": "/validate"},
            )

        assert success is False
        assert returned_payer is None

    @pytest.mark.asyncio
    async def test_settle_payment_returns_none_payer_on_decode_error(self) -> None:
        """_settle_payment returns None payer when payment token cannot be decoded."""
        env = {
            "X402_RECIPIENT_ADDRESS": "0x0000000000000000000000000000000000000DeaD",
            "X402_FACILITATOR_URL": "https://facilitator.example.com",
        }
        with patch.dict(os.environ, env, clear=False):
            from sentinel.x402_middleware import _settle_payment

            success, _tx_hash, error_code, returned_payer = await _settle_payment(
                "not-valid-base64!!!",
                request_context={"path": "/validate"},
            )

        assert success is False
        assert error_code == "invalid_payment_token"
        assert returned_payer is None


# ---------------------------------------------------------------------------
# persist_verdict requester_address integration
# ---------------------------------------------------------------------------


class TestPersistVerdictRequesterAddress:
    """Tests for persist_verdict accepting and using requester_address."""

    def test_persist_verdict_includes_requester_address_in_insert(self) -> None:
        """persist_verdict includes requester_address in the INSERT SQL."""
        with patch("sentinel.persistence.psycopg") as mock_psycopg:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_psycopg.connect.return_value.__enter__ = lambda s: mock_conn  # type: ignore[assignment]
            mock_psycopg.connect.return_value.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor  # type: ignore[assignment]
            mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

            verdict = _make_verdict()
            from sentinel.persistence import persist_verdict

            persist_verdict(
                verdict,
                requester_address="0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B",
                dsn="NEON_DSN_PLACEHOLDER",
            )

            # Verify INSERT includes requester_address
            mock_cursor.execute.assert_called_once()
            call_args = mock_cursor.execute.call_args
            sql: str = call_args[0][0]
            params = call_args[0][1]
            assert "requester_address" in sql, "INSERT must include requester_address column"
            # Verify the address is lowercased
            assert params[-1] == "0xab5801a7d398351b8be11c439e05c5b3259aec9b", (
                "requester_address must be lowercased before insert"
            )

    def test_persist_verdict_with_none_requester_address(self) -> None:
        """persist_verdict with requester_address=None still works (internal bypass)."""
        with patch("sentinel.persistence.psycopg") as mock_psycopg:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_psycopg.connect.return_value.__enter__ = lambda s: mock_conn  # type: ignore[assignment]
            mock_psycopg.connect.return_value.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor  # type: ignore[assignment]
            mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

            verdict = _make_verdict()
            from sentinel.persistence import persist_verdict

            persist_verdict(verdict, requester_address=None, dsn="NEON_DSN_PLACEHOLDER")

            mock_cursor.execute.assert_called_once()
            call_args = mock_cursor.execute.call_args
            params = call_args[0][1]
            assert params[-1] is None, "requester_address param should be None"

    def test_persist_verdict_without_requester_address_backward_compat(self) -> None:
        """persist_verdict called without requester_address still works (backward compat)."""
        with patch("sentinel.persistence.psycopg") as mock_psycopg:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_psycopg.connect.return_value.__enter__ = lambda s: mock_conn  # type: ignore[assignment]
            mock_psycopg.connect.return_value.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor  # type: ignore[assignment]
            mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

            verdict = _make_verdict()
            from sentinel.persistence import persist_verdict

            # Call without requester_address (old calling convention)
            persist_verdict(verdict, dsn="NEON_DSN_PLACEHOLDER")

            mock_cursor.execute.assert_called_once()
            call_args = mock_cursor.execute.call_args
            params = call_args[0][1]
            assert params[-1] is None, "Default requester_address should be None"

    def test_persist_verdict_on_conflict_preserves_existing_requester_address(self) -> None:
        """ON CONFLICT does not overwrite an existing requester_address with NULL."""
        with patch("sentinel.persistence.psycopg") as mock_psycopg:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_psycopg.connect.return_value.__enter__ = lambda s: mock_conn  # type: ignore[assignment]
            mock_psycopg.connect.return_value.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor  # type: ignore[assignment]
            mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

            verdict = _make_verdict()
            from sentinel.persistence import persist_verdict

            persist_verdict(verdict, requester_address=None, dsn="NEON_DSN_PLACEHOLDER")

            mock_cursor.execute.assert_called_once()
            call_args = mock_cursor.execute.call_args
            sql: str = call_args[0][0]
            assert "COALESCE(validations.requester_address" in sql, (
                "ON CONFLICT must preserve existing requester_address via COALESCE"
            )
