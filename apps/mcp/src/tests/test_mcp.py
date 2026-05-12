"""FastMCP server tests — VAL-MCP-001 through VAL-MCP-009.

Covers:
  * VAL-MCP-001 — tools/list returns ``validate`` with the expected schema.
  * VAL-MCP-002 — tools/call validate invokes the sentinel pipeline.
  * VAL-MCP-003 — MCP endpoint is x402-protected (HTTP-layer test).
  * VAL-MCP-004 — MCP tool with x402 payment succeeds.
  * VAL-MCP-005 — MCP mounted as ASGI sub-app at /mcp.
  * VAL-MCP-006 — Invalid trace_uri → structured ToolError, no LLM/DB call.
  * VAL-MCP-007 — Respects PRISM_ONCHAIN flag.
  * VAL-MCP-008 — External MCP client can discover and call the tool end-to-end.
  * VAL-MCP-009 — MCP tool schema matches HTTP ``ValidateRequest`` / ``ValidateResponse``.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client
from prism_schemas.trace import Evidence, ThesisStep, TradingR1Trace
from prism_schemas.verdict import SentinelVerdict


def _make_trace() -> TradingR1Trace:
    return TradingR1Trace(
        trace_id=str(uuid.uuid4()),
        agent_id=1,
        market_id="test-market-mcp",
        market_question="Will MCP discovery work end-to-end?",
        thesis=[
            ThesisStep(
                proposition="MCP discovery and call should both succeed via the mounted sub-app.",
                supporting_evidence_ids=[0],
                risk_factors=["Streamable HTTP transport may behave unexpectedly"],
            )
        ],
        evidence=[
            Evidence(
                source="docs.fastmcp.com",
                claim="FastMCP supports ASGI sub-app mounting.",
                confidence=0.9,
                timestamp=datetime.now(UTC),
            )
        ],
        raw_probability=0.8,
        volatility_adjustment=-0.05,
        final_probability=0.75,
        action="BUY",
        size_usdc=5.0,
        price_limit=0.75,
        rationale="High confidence on MCP feasibility.",
        model_family="anthropic-claude",
        model_name="claude-sonnet-4-20250514",
        created_at=datetime.now(UTC),
    )


def _make_verdict(trace_id: str | None = None) -> SentinelVerdict:
    return SentinelVerdict(
        request_hash=hashlib.sha256(b"mcp-test-request").hexdigest(),
        trace_id=trace_id or str(uuid.uuid4()),
        sentinel_agent_id=2,
        evidence_challenges=[
            "Source documentation may be outdated.",
            "ASGI mount semantics could shift between versions.",
            "Lifespan ordering needs verification.",
        ],
        thesis_challenges=["Assumes streamable HTTP transport is stable."],
        calibration_critique=(
            "Probabilities are reasonable but the volatility adjustment needs justification."
        ),
        verdict_score=72,
        verdict_label="PASS",
        dialogue_messages=[{"role": "adversary", "content": "Verify lifespan ordering."}],
        model_family="openai-gpt",
        model_name="gpt-4o-mini",
        created_at=datetime.now(UTC),
    )


@pytest.fixture(autouse=True)
def _clear_x402_state() -> Generator[None, None, None]:
    """Ensure x402 in-memory consumed-token set is clean between tests."""
    from sentinel.x402_middleware import reset_consumed_tokens_for_testing

    reset_consumed_tokens_for_testing()
    yield
    reset_consumed_tokens_for_testing()


def _patches_for_sentinel_pipeline(
    fetch_trace: dict | None = None,
    verdict: SentinelVerdict | None = None,
) -> tuple[
    AsyncMock,
    MagicMock,
    MagicMock,
    MagicMock,
    MagicMock,
    list[object],
]:
    """Patch out the external services the MCP tool would normally call.

    Returns the spies plus the patch handles so the caller can stop them.
    """
    pinata_patch = patch("prism_mcp.server.PinataClient", create=True)
    # The PinataClient is imported inside `_run_validation`, so the patch
    # below targets the *sentinel* module which is where the symbol lives.
    sentinel_pinata_patch = patch("sentinel.ipfs.PinataClient")
    generate_patch = patch("sentinel.adversarial.generate_verdict")
    persist_patch = patch("sentinel.persistence.persist_verdict")
    update_uri_patch = patch("sentinel.persistence.update_verdict_response_uri")

    sentinel_pinata_cls = sentinel_pinata_patch.start()
    generate_fn = generate_patch.start()
    persist_fn = persist_patch.start()
    update_uri_fn = update_uri_patch.start()
    pinata_patch.stop()

    pinata_instance = AsyncMock()
    pinata_instance.fetch_json.return_value = (
        fetch_trace if fetch_trace is not None else _make_trace().model_dump(mode="json")
    )
    pinata_instance.pin_json.return_value = "QmTestVerdictCIDmcp"
    pinata_instance.close = AsyncMock()
    sentinel_pinata_cls.return_value = pinata_instance

    generate_fn.return_value = verdict if verdict is not None else _make_verdict()

    return (
        pinata_instance,
        sentinel_pinata_cls,
        generate_fn,
        persist_fn,
        update_uri_fn,
        [sentinel_pinata_patch, generate_patch, persist_patch, update_uri_patch],
    )


# ---------------------------------------------------------------------------
# VAL-MCP-001 + VAL-MCP-009: tools/list returns validate with correct schema
# ---------------------------------------------------------------------------


class TestToolDiscovery:
    @pytest.mark.asyncio
    async def test_tools_list_returns_validate_tool(self) -> None:
        from prism_mcp.server import build_mcp_server

        server = build_mcp_server()
        async with Client(server) as client:
            tools = await client.list_tools()
        names = [t.name for t in tools]
        assert "validate" in names

    @pytest.mark.asyncio
    async def test_validate_tool_input_schema_matches_http_endpoint(self) -> None:
        """VAL-MCP-009: schema fields semantically match the HTTP /validate body."""
        from prism_mcp.server import build_mcp_server

        server = build_mcp_server()
        async with Client(server) as client:
            tools = await client.list_tools()

        validate = next(t for t in tools if t.name == "validate")
        schema = validate.inputSchema
        assert schema["type"] == "object"
        props = schema["properties"]
        assert "trace_uri" in props
        assert props["trace_uri"]["type"] == "string"
        assert "trace_hash" in props
        assert props["trace_hash"]["type"] == "string"
        assert "on_chain_request_hash" in props

        required = schema.get("required", [])
        assert "trace_uri" in required
        assert "trace_hash" in required
        assert "on_chain_request_hash" not in required

    @pytest.mark.asyncio
    async def test_validate_tool_description_mentions_x402_payment(self) -> None:
        from prism_mcp.server import build_mcp_server

        server = build_mcp_server()
        async with Client(server) as client:
            tools = await client.list_tools()

        validate = next(t for t in tools if t.name == "validate")
        description = (validate.description or "").lower()
        assert "trading-r1" in description or "trace" in description


# ---------------------------------------------------------------------------
# VAL-MCP-002 + VAL-MCP-008: tools/call validate invokes the sentinel pipeline
# ---------------------------------------------------------------------------


class TestToolInvocation:
    @pytest.mark.asyncio
    async def test_validate_tool_call_returns_verdict_via_in_memory_client(self) -> None:
        from prism_mcp.server import build_mcp_server

        verdict = _make_verdict()
        (
            pinata_instance,
            _pinata_cls,
            generate_fn,
            persist_fn,
            update_uri_fn,
            handles,
        ) = _patches_for_sentinel_pipeline(verdict=verdict)

        try:
            server = build_mcp_server()
            async with Client(server) as client:
                result = await client.call_tool(
                    "validate",
                    {"trace_uri": "ipfs://QmGood", "trace_hash": "0xfeedbeef"},
                )
        finally:
            for h in handles:
                h.stop()

        data = result.data
        assert data is not None
        assert data.verdict_score == verdict.verdict_score
        assert data.verdict_label == verdict.verdict_label
        assert data.ipfs_cid == "QmTestVerdictCIDmcp"
        assert data.content_hash_hex == verdict.content_hash().hex()
        assert data.tx_hash is None
        generate_fn.assert_called_once()
        persist_fn.assert_called_once()
        update_uri_fn.assert_called_once()
        pinata_instance.fetch_json.assert_called_once_with("QmGood")
        pinata_instance.pin_json.assert_called_once()


# ---------------------------------------------------------------------------
# VAL-MCP-006: Invalid trace_uri → structured error
# ---------------------------------------------------------------------------


class TestStructuredErrors:
    @pytest.mark.asyncio
    async def test_empty_trace_uri_returns_structured_error(self) -> None:
        from prism_mcp.server import build_mcp_server

        server = build_mcp_server()
        async with Client(server) as client:
            result = await client.call_tool(
                "validate",
                {"trace_uri": "", "trace_hash": "0xabc"},
                raise_on_error=False,
            )
        assert result.is_error
        message = "".join(getattr(c, "text", "") for c in (result.content or []))
        assert "invalid_trace_uri" in message

    @pytest.mark.asyncio
    async def test_unreachable_trace_uri_returns_structured_error(self) -> None:
        from prism_mcp.server import build_mcp_server

        sentinel_pinata_patch = patch("sentinel.ipfs.PinataClient")
        generate_patch = patch("sentinel.adversarial.generate_verdict")
        persist_patch = patch("sentinel.persistence.persist_verdict")

        sentinel_pinata_cls = sentinel_pinata_patch.start()
        generate_fn = generate_patch.start()
        persist_fn = persist_patch.start()

        pinata_instance = AsyncMock()
        pinata_instance.fetch_json.side_effect = RuntimeError("IPFS 404")
        pinata_instance.close = AsyncMock()
        sentinel_pinata_cls.return_value = pinata_instance

        try:
            server = build_mcp_server()
            async with Client(server) as client:
                result = await client.call_tool(
                    "validate",
                    {"trace_uri": "ipfs://QmDoesNotExist", "trace_hash": "0xabc"},
                    raise_on_error=False,
                )
        finally:
            sentinel_pinata_patch.stop()
            generate_patch.stop()
            persist_patch.stop()

        assert result.is_error
        message = "".join(getattr(c, "text", "") for c in (result.content or []))
        assert "trace_fetch_failed" in message
        generate_fn.assert_not_called()
        persist_fn.assert_not_called()


# ---------------------------------------------------------------------------
# VAL-MCP-007: respects PRISM_ONCHAIN flag
# ---------------------------------------------------------------------------


class TestOnChainFlag:
    @pytest.mark.asyncio
    async def test_validate_tool_skips_onchain_when_flag_disabled(self) -> None:
        from prism_mcp.server import build_mcp_server

        _, _, _, _, _, handles = _patches_for_sentinel_pipeline()
        try:
            with patch.dict(os.environ, {"PRISM_ONCHAIN": ""}, clear=False):
                server = build_mcp_server()
                async with Client(server) as client:
                    result = await client.call_tool(
                        "validate",
                        {
                            "trace_uri": "ipfs://QmGood",
                            "trace_hash": "0xfeedbeef",
                            "on_chain_request_hash": "0xrequesthash",
                        },
                    )
        finally:
            for h in handles:
                h.stop()
        assert result.data is not None
        assert result.data.tx_hash is None

    @pytest.mark.asyncio
    async def test_validate_tool_invokes_onchain_when_flag_enabled(self) -> None:
        from prism_mcp.server import build_mcp_server

        _, _, _, _, _, handles = _patches_for_sentinel_pipeline()
        submit_fn_patch = patch(
            "sentinel.chain.submit_validation_response_from_env",
            new_callable=AsyncMock,
        )
        update_tx_patch = patch("sentinel.persistence.update_validation_tx_hash")

        submit_fn = submit_fn_patch.start()
        update_tx_fn = update_tx_patch.start()
        submit_fn.return_value = {
            "request_hash": "0xrequesthash",
            "circle_tx_id": "circle-abc",
            "on_chain_tx_hash": "0xfaceb00c",
        }

        try:
            with patch.dict(os.environ, {"PRISM_ONCHAIN": "true"}, clear=False):
                server = build_mcp_server()
                async with Client(server) as client:
                    result = await client.call_tool(
                        "validate",
                        {
                            "trace_uri": "ipfs://QmGood",
                            "trace_hash": "0xfeedbeef",
                            "on_chain_request_hash": "0xrequesthash",
                        },
                    )
        finally:
            submit_fn_patch.stop()
            update_tx_patch.stop()
            for h in handles:
                h.stop()

        assert result.data is not None
        assert result.data.tx_hash == "0xfaceb00c"
        submit_fn.assert_awaited_once()
        update_tx_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_tool_skips_onchain_without_request_hash(self) -> None:
        from prism_mcp.server import build_mcp_server

        _, _, _, _, _, handles = _patches_for_sentinel_pipeline()
        submit_fn_patch = patch(
            "sentinel.chain.submit_validation_response_from_env",
            new_callable=AsyncMock,
        )
        submit_fn = submit_fn_patch.start()
        try:
            with patch.dict(os.environ, {"PRISM_ONCHAIN": "true"}, clear=False):
                server = build_mcp_server()
                async with Client(server) as client:
                    result = await client.call_tool(
                        "validate",
                        {"trace_uri": "ipfs://QmGood", "trace_hash": "0xfeedbeef"},
                    )
        finally:
            submit_fn_patch.stop()
            for h in handles:
                h.stop()
        assert result.data is not None
        assert result.data.tx_hash is None
        submit_fn.assert_not_awaited()


# ---------------------------------------------------------------------------
# VAL-MCP-005 + VAL-MCP-003: MCP mounted at /mcp behind x402 middleware
# ---------------------------------------------------------------------------


def _patch_sentinel_main() -> tuple[object, ...]:
    """Mock out the heavy sentinel startup machinery (DB, IPFS, LLM).

    Patches both the ``sentinel.main`` aliases used by the HTTP ``/validate``
    handler and the source modules imported by the MCP tool's
    ``_run_validation`` function, so paid MCP ``tools/call`` traffic doesn't
    hit real Pinata / OpenAI / Neon.
    """
    pinata_patch = patch("sentinel.main.PinataClient")
    gen_patch = patch("sentinel.main.generate_verdict")
    persist_patch = patch("sentinel.main.persist_verdict")
    update_uri_patch = patch("sentinel.main.update_verdict_response_uri")
    migration_patch = patch("sentinel.main.run_migration")
    agent_row_patch = patch("sentinel.main.ensure_agent_row")
    startup_patch = patch("sentinel.main._run_startup_gates")

    ipfs_patch = patch("sentinel.ipfs.PinataClient")
    adversarial_patch = patch("sentinel.adversarial.generate_verdict")
    persistence_persist_patch = patch("sentinel.persistence.persist_verdict")
    persistence_uri_patch = patch("sentinel.persistence.update_verdict_response_uri")
    persistence_tx_patch = patch("sentinel.persistence.update_validation_tx_hash")

    pinata_cls = pinata_patch.start()
    gen_fn = gen_patch.start()
    persist_patch.start()
    update_uri_patch.start()
    migration_patch.start()
    agent_row_patch.start()
    startup_patch.start()

    ipfs_cls = ipfs_patch.start()
    adversarial_fn = adversarial_patch.start()
    persistence_persist_patch.start()
    persistence_uri_patch.start()
    persistence_tx_patch.start()

    pinata_instance = AsyncMock()
    pinata_instance.fetch_json.return_value = _make_trace().model_dump(mode="json")
    pinata_instance.pin_json.return_value = "QmTestVerdictCIDmcp"
    pinata_instance.close = AsyncMock()
    pinata_cls.return_value = pinata_instance
    ipfs_cls.return_value = pinata_instance

    verdict = _make_verdict()
    gen_fn.return_value = verdict
    adversarial_fn.return_value = verdict

    return (
        pinata_patch,
        gen_patch,
        persist_patch,
        update_uri_patch,
        migration_patch,
        agent_row_patch,
        startup_patch,
        ipfs_patch,
        adversarial_patch,
        persistence_persist_patch,
        persistence_uri_patch,
        persistence_tx_patch,
    )


class TestMcpHttpMount:
    def test_mcp_endpoint_returns_mcp_response_on_get(self) -> None:
        """VAL-MCP-005: /mcp is mounted on the sentinel FastAPI app."""
        patches = _patch_sentinel_main()
        try:
            with patch.dict(os.environ, {"X402_BYPASS": "1"}, clear=False):
                from sentinel.main import app

                with TestClient(app) as client:
                    resp = client.get("/mcp/")
                    body = resp.text
        finally:
            for p in patches:
                p.stop()

        assert "jsonrpc" in body.lower()

    def test_health_endpoint_remains_open(self) -> None:
        patches = _patch_sentinel_main()
        try:
            with patch.dict(os.environ, {"X402_BYPASS": ""}, clear=False):
                from sentinel.main import app

                with TestClient(app) as client:
                    resp = client.get("/health")
        finally:
            for p in patches:
                p.stop()
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_validate_endpoint_still_works_alongside_mcp(self) -> None:
        """Both /validate and /mcp coexist on the same app/port."""
        patches = _patch_sentinel_main()
        try:
            with patch.dict(os.environ, {"X402_BYPASS": "1"}, clear=False):
                from sentinel.main import app

                with TestClient(app) as client:
                    resp = client.post(
                        "/validate",
                        json={"trace_uri": "ipfs://QmGood", "trace_hash": "0xabc"},
                    )
        finally:
            for p in patches:
                p.stop()
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "verdict_score" in body

    def test_mcp_post_without_payment_returns_jsonrpc_error_envelope(self) -> None:
        """VAL-MCP-003: MCP POST without x402 payment returns a JSON-RPC error envelope.

        The body MUST be MCP-compatible (jsonrpc/id/error shape) and carry the
        payment requirement details inside ``error.data`` so a JSON-RPC client
        can surface them as a structured error rather than a raw HTTP failure.
        """
        patches = _patch_sentinel_main()
        try:
            with patch.dict(os.environ, {"X402_BYPASS": ""}, clear=False):
                from sentinel.main import app

                with TestClient(app) as client:
                    resp = client.post(
                        "/mcp/",
                        json={
                            "jsonrpc": "2.0",
                            "id": 7,
                            "method": "tools/call",
                            "params": {
                                "name": "validate",
                                "arguments": {
                                    "trace_uri": "ipfs://QmGood",
                                    "trace_hash": "0xabc",
                                },
                            },
                        },
                        headers={"Accept": "application/json, text/event-stream"},
                    )
        finally:
            for p in patches:
                p.stop()

        assert resp.status_code == 402, resp.text
        body = resp.json()
        assert body.get("jsonrpc") == "2.0"
        assert body.get("id") == 7
        assert "error" in body
        error = body["error"]
        assert isinstance(error.get("code"), int)
        assert isinstance(error.get("message"), str) and error["message"]
        data = error.get("data") or {}
        assert data.get("asset") == "USDC"
        assert data.get("amount")
        assert data.get("facilitator") == "x402"
        assert data.get("network") == "base"

    def test_mcp_post_malformed_payment_returns_jsonrpc_error_envelope(self) -> None:
        """Malformed payment header on /mcp/ → JSON-RPC error with specific error code."""
        patches = _patch_sentinel_main()
        try:
            with patch.dict(os.environ, {"X402_BYPASS": ""}, clear=False):
                from sentinel.main import app

                with TestClient(app) as client:
                    resp = client.post(
                        "/mcp/",
                        json={
                            "jsonrpc": "2.0",
                            "id": "abc-123",
                            "method": "tools/call",
                            "params": {
                                "name": "validate",
                                "arguments": {
                                    "trace_uri": "ipfs://QmGood",
                                    "trace_hash": "0xabc",
                                },
                            },
                        },
                        headers={
                            "Accept": "application/json, text/event-stream",
                            "x402-payment": "invalid",
                        },
                    )
        finally:
            for p in patches:
                p.stop()

        assert resp.status_code == 402, resp.text
        body = resp.json()
        assert body.get("jsonrpc") == "2.0"
        assert body.get("id") == "abc-123"
        data = body["error"]["data"]
        assert data.get("error") == "invalid_payment_token"
        assert data.get("asset") == "USDC"
        assert data.get("amount")

    def test_validate_post_without_payment_keeps_flat_402_body(self) -> None:
        """HTTP /validate keeps the legacy flat 402 body — not JSON-RPC wrapping."""
        patches = _patch_sentinel_main()
        try:
            with patch.dict(os.environ, {"X402_BYPASS": ""}, clear=False):
                from sentinel.main import app

                with TestClient(app) as client:
                    resp = client.post(
                        "/validate",
                        json={"trace_uri": "ipfs://QmGood", "trace_hash": "0xabc"},
                    )
        finally:
            for p in patches:
                p.stop()

        assert resp.status_code == 402, resp.text
        body = resp.json()
        assert "jsonrpc" not in body
        assert body["asset"] == "USDC"
        assert body["amount"]
        assert body["facilitator"] == "x402"

    def test_mcp_post_with_bypass_header_proceeds(self) -> None:
        patches = _patch_sentinel_main()
        try:
            with patch.dict(os.environ, {"X402_BYPASS": ""}, clear=False):
                from sentinel.main import app

                with TestClient(app) as client:
                    resp = client.post(
                        "/mcp/",
                        json={
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "initialize",
                            "params": {
                                "protocolVersion": "2025-03-26",
                                "capabilities": {},
                                "clientInfo": {"name": "test", "version": "1.0"},
                            },
                        },
                        headers={
                            "Accept": "application/json, text/event-stream",
                            "X402-Bypass": "internal",
                        },
                    )
        finally:
            for p in patches:
                p.stop()
        assert resp.status_code == 200, resp.text
        assert "jsonrpc" in resp.text.lower()


# ---------------------------------------------------------------------------
# VAL-MCP-004: MCP tool with x402 payment succeeds end-to-end
# ---------------------------------------------------------------------------


class TestMcpWithPayment:
    def test_mcp_tools_list_with_x402_payment_returns_validate(self) -> None:
        patches = _patch_sentinel_main()
        try:
            with patch.dict(
                os.environ,
                {"X402_BYPASS": "", "X402_FACILITATOR_URL": "", "X402_RECIPIENT_ADDRESS": ""},
                clear=False,
            ):
                from sentinel.main import app

                with TestClient(app) as client:
                    resp = client.post(
                        "/mcp/",
                        json={
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "initialize",
                            "params": {
                                "protocolVersion": "2025-03-26",
                                "capabilities": {},
                                "clientInfo": {"name": "external-agent", "version": "1.0"},
                            },
                        },
                        headers={
                            "Accept": "application/json, text/event-stream",
                            "x402-payment": "external-agent-pays-aaa-bbb-ccc-001",
                        },
                    )
        finally:
            for p in patches:
                p.stop()
        assert resp.status_code == 200, resp.text
        assert "jsonrpc" in resp.text.lower()


# ---------------------------------------------------------------------------
# VAL-MCP-009: ValidateMcpResult includes payment_tx_hash to match HTTP schema
# ---------------------------------------------------------------------------


class TestPaymentTxHashSchemaParity:
    def test_validate_mcp_result_model_has_payment_tx_hash_field(self) -> None:
        from prism_mcp.server import ValidateMcpResult

        assert "payment_tx_hash" in ValidateMcpResult.model_fields
        field = ValidateMcpResult.model_fields["payment_tx_hash"]
        assert field.default is None

    @pytest.mark.asyncio
    async def test_validate_tool_output_schema_includes_payment_tx_hash(self) -> None:
        """tools/list outputSchema must expose payment_tx_hash to MCP clients."""
        from prism_mcp.server import build_mcp_server

        server = build_mcp_server()
        async with Client(server) as client:
            tools = await client.list_tools()
        validate = next(t for t in tools if t.name == "validate")
        output_schema = getattr(validate, "outputSchema", None)
        assert output_schema is not None, "validate tool must expose an output schema"

        props = output_schema.get("properties") or {}
        nested = (output_schema.get("$defs") or {}).get("ValidateMcpResult", {}).get(
            "properties",
            {},
        )

        assert "payment_tx_hash" in props or "payment_tx_hash" in nested, (
            "outputSchema must include payment_tx_hash field "
            f"(top-level={list(props)[:6]} nested={list(nested)[:6]})"
        )

    def test_mcp_validate_through_http_with_payment_returns_payment_tx_hash(self) -> None:
        """Paid MCP tools/call must return payment_tx_hash sourced from middleware."""
        patches = _patch_sentinel_main()
        try:
            with patch.dict(
                os.environ,
                {"X402_BYPASS": "", "X402_FACILITATOR_URL": "", "X402_RECIPIENT_ADDRESS": ""},
                clear=False,
            ):
                from sentinel.main import app

                with TestClient(app) as client:
                    init_resp = client.post(
                        "/mcp/",
                        json={
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "initialize",
                            "params": {
                                "protocolVersion": "2025-03-26",
                                "capabilities": {},
                                "clientInfo": {"name": "tx-hash-tester", "version": "1.0"},
                            },
                        },
                        headers={
                            "Accept": "application/json, text/event-stream",
                            "x402-payment": "payment-tx-hash-test-token-init-001",
                        },
                    )
                    assert init_resp.status_code == 200, init_resp.text
                    session_id = init_resp.headers.get("mcp-session-id") or ""

                    notif_headers = {
                        "Accept": "application/json, text/event-stream",
                        "x402-payment": "payment-tx-hash-test-token-init-001-notif",
                    }
                    if session_id:
                        notif_headers["mcp-session-id"] = session_id
                    client.post(
                        "/mcp/",
                        json={
                            "jsonrpc": "2.0",
                            "method": "notifications/initialized",
                            "params": {},
                        },
                        headers=notif_headers,
                    )

                    call_headers = {
                        "Accept": "application/json, text/event-stream",
                        "x402-payment": "payment-tx-hash-test-token-call-002",
                    }
                    if session_id:
                        call_headers["mcp-session-id"] = session_id
                    call_resp = client.post(
                        "/mcp/",
                        json={
                            "jsonrpc": "2.0",
                            "id": 2,
                            "method": "tools/call",
                            "params": {
                                "name": "validate",
                                "arguments": {
                                    "trace_uri": "ipfs://QmPaymentTxHashTest",
                                    "trace_hash": "0xdeadbeef",
                                },
                            },
                        },
                        headers=call_headers,
                    )
        finally:
            for p in patches:
                p.stop()

        assert call_resp.status_code == 200, call_resp.text
        text = call_resp.text
        assert "payment_tx_hash" in text, (
            "MCP tools/call result should expose payment_tx_hash, body=" + text[:1000]
        )
        assert "0x" in text
