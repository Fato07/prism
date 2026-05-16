from __future__ import annotations

import json

import httpx
import pytest

import prism_cli.client as client_module
from prism_cli.client import PrismCliError, request_validation_quote, submit_paid_validation
from prism_cli.config import CliConfig

TRACE_URI = "ipfs://QmNzqnPEEQUMn3GMbiEZANpKXZRPmTHxVwt5nNevR8iXt8"
TRACE_HASH = "0x1a750011608a7480e9cb11f1d20587e32efb7a7dd433b85820f0dbfcdee19fdb"
SENTINEL_URL = "https://sentinel.example/mcp/"


def payment_required_body() -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "error": {
            "code": -32002,
            "message": "Payment required",
            "data": {
                "detail": "Payment required",
                "amount": "0.01",
                "asset": "USDC",
                "scheme": "exact",
                "network": "base-sepolia",
                "facilitator": "x402",
                "facilitator_mode": "public",
                "recipient": "0x1453000000000000000000000000000000000000",
            },
        },
    }


def validation_result_payload(*, is_error: bool = False) -> dict:
    if is_error:
        return {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "isError": True,
                "content": [{"type": "text", "text": "trace_fetch_failed: IPFS 404"}],
            },
        }
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "structuredContent": {
                "request_hash": "request-hash",
                "trace_id": "d6cdd60f-f5e0-43ab-ba2d-7dcab76a8e24",
                "sentinel_agent_id": 2,
                "verdict_score": 65,
                "verdict_label": "PASS",
                "evidence_challenges": ["challenge"],
                "thesis_challenges": [],
                "calibration_critique": "calibrated",
                "ipfs_cid": "QmVerdict",
                "content_hash_hex": "abc123",
                "tx_hash": "0xarc",
                "payment_tx_hash": "0xbase",
            }
        },
    }


def install_mock_transport(monkeypatch, handler) -> None:
    original_async_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)

    def async_client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(client_module.httpx, "AsyncClient", async_client_factory)


@pytest.mark.anyio
async def test_quote_performs_mcp_handshake_and_parses_jsonrpc_402(monkeypatch) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        method = payload.get("method")
        calls.append(method)
        if method == "initialize":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": 0, "result": {}},
                headers={"mcp-session-id": "session-1"},
            )
        if method == "notifications/initialized":
            assert request.headers["mcp-session-id"] == "session-1"
            return httpx.Response(202)
        assert method == "tools/call"
        assert request.headers["mcp-session-id"] == "session-1"
        assert "x-payment" not in {k.lower(): v for k, v in request.headers.items()}
        return httpx.Response(402, json=payment_required_body())

    install_mock_transport(monkeypatch, handler)

    quote = await request_validation_quote(
        CliConfig(sentinel_url=SENTINEL_URL),
        TRACE_URI,
        trace_hash=TRACE_HASH,
    )

    assert calls == ["initialize", "notifications/initialized", "tools/call"]
    assert quote.amount_usdc == "0.01"
    assert quote.caip2 == "eip155:84532"
    assert quote.asset_contract == "0x036CbD53842c5426634e7929541eC2318f3dCF7e"


@pytest.mark.anyio
async def test_paid_validation_forwards_payment_and_parses_sse(monkeypatch) -> None:
    paid_seen = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal paid_seen
        payload = json.loads(request.content.decode())
        method = payload.get("method")
        if method == "initialize":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": 0, "result": {}},
                headers={"mcp-session-id": "session-1"},
            )
        if method == "notifications/initialized":
            return httpx.Response(202)
        if "x-payment" not in {k.lower(): v for k, v in request.headers.items()}:
            return httpx.Response(402, json=payment_required_body())
        paid_seen = True
        assert request.headers["x-payment"] == "signed-payload"
        body = "event: message\ndata: " + json.dumps(validation_result_payload()) + "\n\n"
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    install_mock_transport(monkeypatch, handler)

    receipt = await submit_paid_validation(
        CliConfig(sentinel_url=SENTINEL_URL),
        TRACE_URI,
        x_payment_header="signed-payload",
        trace_hash=TRACE_HASH,
    )

    assert paid_seen
    assert receipt.result.verdict_score == 65
    assert receipt.result.payment_tx_hash == "0xbase"


@pytest.mark.anyio
async def test_paid_validation_raises_clean_error_for_mcp_tool_failure(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        method = payload.get("method")
        if method == "initialize":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": 0, "result": {}},
                headers={"mcp-session-id": "session-1"},
            )
        if method == "notifications/initialized":
            return httpx.Response(202)
        if "x-payment" not in {k.lower(): v for k, v in request.headers.items()}:
            return httpx.Response(402, json=payment_required_body())
        return httpx.Response(200, json=validation_result_payload(is_error=True))

    install_mock_transport(monkeypatch, handler)

    with pytest.raises(PrismCliError, match="trace_fetch_failed"):
        await submit_paid_validation(
            CliConfig(sentinel_url=SENTINEL_URL),
            TRACE_URI,
            x_payment_header="signed-payload",
            trace_hash=TRACE_HASH,
        )
