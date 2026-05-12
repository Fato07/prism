"""x402 payment middleware tests — VAL-X402-001 through VAL-X402-010.

These tests cover the rigorous Phase 1 middleware in
`sentinel.x402_middleware`. They mock the IPFS / DSPy / DB layer so they
exercise only the payment gating + settlement glue.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from prism_schemas.trace import Evidence, ThesisStep, TradingR1Trace
from prism_schemas.verdict import SentinelVerdict

from sentinel.x402_middleware import (
    X402_DEFAULT_PRICE_USDC,
    _malformed_reason,
    assert_bypass_safe_at_startup,
    is_production,
    is_x402_bypass_enabled,
    reset_consumed_tokens_for_testing,
)


@pytest.fixture(autouse=True)
def _clear_consumed_tokens() -> Generator[None, None, None]:
    """Reset the in-memory consumed payment-token set before every test."""
    reset_consumed_tokens_for_testing()
    yield
    reset_consumed_tokens_for_testing()


def _make_trace() -> TradingR1Trace:
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


def _build_client():
    """Return a FastAPI TestClient with all downstream services mocked."""
    pinata_patch = patch("sentinel.main.PinataClient")
    gen_patch = patch("sentinel.main.generate_verdict")
    persist_patch = patch("sentinel.main.persist_verdict")
    update_uri_patch = patch("sentinel.main.update_verdict_response_uri")
    migration_patch = patch("sentinel.main.run_migration")
    agent_row_patch = patch("sentinel.main.ensure_agent_row")
    startup_patch = patch("sentinel.main._run_startup_gates")

    pinata_cls = pinata_patch.start()
    gen_fn = gen_patch.start()
    persist_patch.start()
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

    def stop_all() -> None:
        pinata_patch.stop()
        gen_patch.stop()
        persist_patch.stop()
        update_uri_patch.stop()
        migration_patch.stop()
        agent_row_patch.stop()
        startup_patch.stop()

    return client, stop_all


# ---------------------------------------------------------------------------
# VAL-X402-001: Unpaid request returns HTTP 402 with payment details
# ---------------------------------------------------------------------------


class TestUnpaidReturns402:
    def test_unpaid_validate_returns_402_with_payment_details(self) -> None:
        with patch.dict(os.environ, {"X402_BYPASS": ""}, clear=False):
            client, stop = _build_client()
            try:
                resp = client.post(
                    "/validate",
                    json={"trace_uri": "ipfs://QmTestCID", "trace_hash": "0xabc"},
                )
            finally:
                stop()

            assert resp.status_code == 402
            body = resp.json()
            assert body["detail"]
            assert body["amount"] == "0.01"
            assert body["asset"] == "USDC"
            assert body["facilitator"] == "x402"
            assert body["network"] == "base"

    def test_402_body_includes_recipient_when_configured(self) -> None:
        recipient = "0x000000000000000000000000000000000000dEaD"
        with patch.dict(
            os.environ,
            {
                "X402_BYPASS": "",
                "X402_RECIPIENT_ADDRESS": recipient,
            },
            clear=False,
        ):
            client, stop = _build_client()
            try:
                resp = client.post(
                    "/validate",
                    json={"trace_uri": "ipfs://QmTestCID", "trace_hash": "0xabc"},
                )
            finally:
                stop()

            assert resp.status_code == 402
            assert resp.json()["recipient"] == recipient


# ---------------------------------------------------------------------------
# VAL-X402-002: Malformed payment header returns HTTP 402
# ---------------------------------------------------------------------------


class TestMalformedPayment:
    def test_malformed_reason_detects_invalid(self) -> None:
        assert _malformed_reason("invalid") == "invalid_payment_token"
        assert _malformed_reason("corrupted") == "invalid_payment_token"
        assert _malformed_reason("") == "invalid_payment_token"
        assert _malformed_reason("abc") == "invalid_payment_token"

    def test_malformed_reason_detects_expired(self) -> None:
        assert _malformed_reason("expired") == "payment_expired"
        assert _malformed_reason("some-token:expired") == "payment_expired"

    def test_malformed_reason_accepts_valid_looking_token(self) -> None:
        assert _malformed_reason("valid-payment-token-001") is None
        assert _malformed_reason("0x" + "a" * 200) is None

    def test_invalid_payment_token_returns_402_with_error(self) -> None:
        with patch.dict(os.environ, {"X402_BYPASS": ""}, clear=False):
            client, stop = _build_client()
            try:
                resp = client.post(
                    "/validate",
                    json={"trace_uri": "ipfs://QmTestCID", "trace_hash": "0xabc"},
                    headers={"x402-payment": "invalid"},
                )
            finally:
                stop()

            assert resp.status_code == 402
            body = resp.json()
            assert body["error"] == "invalid_payment_token"

    def test_expired_payment_token_returns_402_with_error(self) -> None:
        with patch.dict(os.environ, {"X402_BYPASS": ""}, clear=False):
            client, stop = _build_client()
            try:
                resp = client.post(
                    "/validate",
                    json={"trace_uri": "ipfs://QmTestCID", "trace_hash": "0xabc"},
                    headers={"x402-payment": "some-token:expired"},
                )
            finally:
                stop()

            assert resp.status_code == 402
            assert resp.json()["error"] == "payment_expired"


# ---------------------------------------------------------------------------
# VAL-X402-003 + VAL-X402-005: Valid payment proceeds and exposes tx hash
# ---------------------------------------------------------------------------


class TestSuccessfulPayment:
    def test_valid_payment_returns_200_with_verdict_and_payment_tx_hash(self) -> None:
        with patch.dict(os.environ, {"X402_BYPASS": ""}, clear=False):
            client, stop = _build_client()
            try:
                resp = client.post(
                    "/validate",
                    json={"trace_uri": "ipfs://QmTestCID", "trace_hash": "0xabc"},
                    headers={"x402-payment": "deadbeef-payment-token-12345"},
                )
            finally:
                stop()

            assert resp.status_code == 200
            body = resp.json()
            assert "verdict_score" in body
            assert "verdict_label" in body
            assert "ipfs_cid" in body
            assert body["payment_tx_hash"], "payment_tx_hash must be populated after settlement"
            assert body["payment_tx_hash"].startswith("0x")

    def test_payment_tx_hash_is_deterministic_for_same_token(self) -> None:
        token = "stable-payment-token-aaa"
        with patch.dict(os.environ, {"X402_BYPASS": ""}, clear=False):
            client, stop = _build_client()
            try:
                resp1 = client.post(
                    "/validate",
                    json={"trace_uri": "ipfs://Qm1", "trace_hash": "0x1"},
                    headers={"x402-payment": token},
                )
                reset_consumed_tokens_for_testing()
                resp2 = client.post(
                    "/validate",
                    json={"trace_uri": "ipfs://Qm1", "trace_hash": "0x1"},
                    headers={"x402-payment": token},
                )
            finally:
                stop()

            assert resp1.status_code == 200
            assert resp2.status_code == 200
            assert resp1.json()["payment_tx_hash"] == resp2.json()["payment_tx_hash"]

    def test_valid_payment_accepted_via_x_payment_header(self) -> None:
        with patch.dict(os.environ, {"X402_BYPASS": ""}, clear=False):
            client, stop = _build_client()
            try:
                resp = client.post(
                    "/validate",
                    json={"trace_uri": "ipfs://QmTestCID", "trace_hash": "0xabc"},
                    headers={"x-payment": "standard-x402-payment-token-xyz"},
                )
            finally:
                stop()

            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# VAL-X402-004: Payment amount matches configured price
# ---------------------------------------------------------------------------


class TestConfiguredPrice:
    def test_default_price_is_one_cent(self) -> None:
        with patch.dict(os.environ, {"X402_PRICE_USDC": ""}, clear=False):
            client, stop = _build_client()
            try:
                resp = client.post(
                    "/validate",
                    json={"trace_uri": "ipfs://QmTestCID", "trace_hash": "0xabc"},
                )
            finally:
                stop()

            assert resp.status_code == 402
            assert resp.json()["amount"] == X402_DEFAULT_PRICE_USDC == "0.01"

    def test_custom_price_env_var_reflected_in_402_body(self) -> None:
        with patch.dict(
            os.environ,
            {"X402_BYPASS": "", "X402_PRICE_USDC": "0.05"},
            clear=False,
        ):
            client, stop = _build_client()
            try:
                resp = client.post(
                    "/validate",
                    json={"trace_uri": "ipfs://QmTestCID", "trace_hash": "0xabc"},
                )
            finally:
                stop()

            assert resp.status_code == 402
            assert resp.json()["amount"] == "0.05"


# ---------------------------------------------------------------------------
# VAL-X402-006: Double-spend rejected
# ---------------------------------------------------------------------------


class TestDoubleSpend:
    def test_same_payment_token_used_twice_returns_402(self) -> None:
        token = "TEST_TOKEN_PLACEHOLDER_NOT_A_SECRET_xx"
        with patch.dict(os.environ, {"X402_BYPASS": ""}, clear=False):
            client, stop = _build_client()
            try:
                first = client.post(
                    "/validate",
                    json={"trace_uri": "ipfs://Qm1", "trace_hash": "0x1"},
                    headers={"x402-payment": token},
                )
                second = client.post(
                    "/validate",
                    json={"trace_uri": "ipfs://Qm2", "trace_hash": "0x2"},
                    headers={"x402-payment": token},
                )
            finally:
                stop()

            assert first.status_code == 200
            assert second.status_code == 402
            assert second.json()["error"] == "payment_already_consumed"


# ---------------------------------------------------------------------------
# VAL-X402-007: Bypass mode (and production refusal)
# ---------------------------------------------------------------------------


class TestBypass:
    def test_env_var_bypass_skips_payment_check(self) -> None:
        with patch.dict(os.environ, {"X402_BYPASS": "1"}, clear=False):
            assert is_x402_bypass_enabled()
            client, stop = _build_client()
            try:
                resp = client.post(
                    "/validate",
                    json={"trace_uri": "ipfs://QmTestCID", "trace_hash": "0xabc"},
                )
            finally:
                stop()

            assert resp.status_code == 200

    def test_internal_bypass_header_skips_payment_check(self) -> None:
        with patch.dict(os.environ, {"X402_BYPASS": ""}, clear=False):
            client, stop = _build_client()
            try:
                resp = client.post(
                    "/validate",
                    json={"trace_uri": "ipfs://QmTestCID", "trace_hash": "0xabc"},
                    headers={"X402-Bypass": "internal-trader-call"},
                )
            finally:
                stop()

            assert resp.status_code == 200

    def test_internal_bypass_header_requires_token_when_configured(self) -> None:
        with patch.dict(
            os.environ,
            {"X402_BYPASS": "", "X402_INTERNAL_BYPASS_TOKEN": "secret-token-abc"},
            clear=False,
        ):
            client, stop = _build_client()
            try:
                wrong = client.post(
                    "/validate",
                    json={"trace_uri": "ipfs://QmTestCID", "trace_hash": "0xabc"},
                    headers={"X402-Bypass": "wrong-token"},
                )
                right = client.post(
                    "/validate",
                    json={"trace_uri": "ipfs://QmTestCID", "trace_hash": "0xabc"},
                    headers={"X402-Bypass": "secret-token-abc"},
                )
            finally:
                stop()

            assert wrong.status_code == 402
            assert right.status_code == 200

    def test_production_refuses_to_start_with_bypass(self) -> None:
        with patch.dict(
            os.environ,
            {"RAILWAY_ENVIRONMENT": "production", "X402_BYPASS": "1"},
            clear=False,
        ):
            assert is_production()
            assert is_x402_bypass_enabled()
            with pytest.raises(SystemExit):
                assert_bypass_safe_at_startup()

    def test_production_without_bypass_starts_normally(self) -> None:
        with patch.dict(
            os.environ,
            {"RAILWAY_ENVIRONMENT": "production", "X402_BYPASS": ""},
            clear=False,
        ):
            assert is_production()
            assert not is_x402_bypass_enabled()
            assert_bypass_safe_at_startup()

    def test_non_production_with_bypass_starts_normally(self) -> None:
        with patch.dict(
            os.environ,
            {"RAILWAY_ENVIRONMENT": "preview", "X402_BYPASS": "1"},
            clear=False,
        ):
            assert not is_production()
            assert is_x402_bypass_enabled()
            assert_bypass_safe_at_startup()


# ---------------------------------------------------------------------------
# VAL-X402-008: Settlement on Base (config-level assertion)
# ---------------------------------------------------------------------------


class TestSettlementOnBase:
    def test_default_network_is_base(self) -> None:
        with patch.dict(os.environ, {"X402_BYPASS": "", "X402_NETWORK": ""}, clear=False):
            client, stop = _build_client()
            try:
                resp = client.post(
                    "/validate",
                    json={"trace_uri": "ipfs://QmTestCID", "trace_hash": "0xabc"},
                )
            finally:
                stop()

            assert resp.status_code == 402
            assert resp.json()["network"] == "base"


# ---------------------------------------------------------------------------
# VAL-X402-009: Payment timeout returns 504
# ---------------------------------------------------------------------------


class TestSettlementTimeout:
    def test_settlement_timeout_returns_504(self) -> None:
        async def slow_settle(token, *, request_context):
            import asyncio

            await asyncio.sleep(5)
            return True, "0xnope", None

        env = {"X402_BYPASS": "", "X402_SETTLEMENT_TIMEOUT_S": "0.1"}
        with (
            patch.dict(os.environ, env, clear=False),
            patch("sentinel.x402_middleware._settle_payment", side_effect=slow_settle),
        ):
            client, stop = _build_client()
            try:
                resp = client.post(
                    "/validate",
                    json={"trace_uri": "ipfs://QmTestCID", "trace_hash": "0xabc"},
                    headers={"x402-payment": "slow-settling-payment-token"},
                )
            finally:
                stop()

            assert resp.status_code == 504
            assert resp.json()["error"] == "payment_settlement_timeout"


# ---------------------------------------------------------------------------
# VAL-X402-010: /health is not x402-protected
# ---------------------------------------------------------------------------


class TestHealthOpen:
    def test_health_returns_200_without_payment(self) -> None:
        with patch.dict(os.environ, {"X402_BYPASS": ""}, clear=False):
            client, stop = _build_client()
            try:
                resp = client.get("/health")
            finally:
                stop()

            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Facilitator integration (production path) — mocked HTTP
# ---------------------------------------------------------------------------


class TestFacilitatorSettlement:
    def test_facilitator_success_returns_tx_hash_from_body(self) -> None:
        import httpx

        async def fake_post(self, url, json=None, **kwargs):
            request = httpx.Request("POST", url, json=json)
            return httpx.Response(
                status_code=200,
                json={
                    "success": True,
                    "txHash": "0xfacilitatortx0000000000000000000000000000000000000000000000000001",
                },
                request=request,
            )

        env = {
            "X402_BYPASS": "",
            "X402_RECIPIENT_ADDRESS": "0x0000000000000000000000000000000000000DeaD",
            "X402_FACILITATOR_URL": "https://facilitator.example.com",
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("httpx.AsyncClient.post", new=fake_post),
        ):
            client, stop = _build_client()
            try:
                resp = client.post(
                    "/validate",
                    json={"trace_uri": "ipfs://QmTestCID", "trace_hash": "0xabc"},
                    headers={"x402-payment": "facilitator-payment-token-001"},
                )
            finally:
                stop()

            assert resp.status_code == 200
            assert resp.json()["payment_tx_hash"].startswith("0xfacilitatortx")

    def test_facilitator_non_success_returns_402(self) -> None:
        import httpx

        async def fake_post(self, url, json=None, **kwargs):
            request = httpx.Request("POST", url, json=json)
            return httpx.Response(
                status_code=200,
                json={"success": False, "error": "invalid"},
                request=request,
            )

        env = {
            "X402_BYPASS": "",
            "X402_RECIPIENT_ADDRESS": "0x0000000000000000000000000000000000000DeaD",
            "X402_FACILITATOR_URL": "https://facilitator.example.com",
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("httpx.AsyncClient.post", new=fake_post),
        ):
            client, stop = _build_client()
            try:
                resp = client.post(
                    "/validate",
                    json={"trace_uri": "ipfs://QmTestCID", "trace_hash": "0xabc"},
                    headers={"x402-payment": "facilitator-rejected-token-aaa"},
                )
            finally:
                stop()

            assert resp.status_code == 402
            assert resp.json()["error"] == "settlement_failed"

    def test_facilitator_http_error_returns_402(self) -> None:
        import httpx

        async def fake_post(self, url, json=None, **kwargs):
            raise httpx.ConnectError("facilitator unreachable")

        env = {
            "X402_BYPASS": "",
            "X402_RECIPIENT_ADDRESS": "0x0000000000000000000000000000000000000DeaD",
            "X402_FACILITATOR_URL": "https://facilitator.example.com",
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("httpx.AsyncClient.post", new=fake_post),
        ):
            client, stop = _build_client()
            try:
                resp = client.post(
                    "/validate",
                    json={"trace_uri": "ipfs://QmTestCID", "trace_hash": "0xabc"},
                    headers={"x402-payment": "facilitator-error-token-aaa"},
                )
            finally:
                stop()

            assert resp.status_code == 402
            assert resp.json()["error"] == "settlement_failed"
