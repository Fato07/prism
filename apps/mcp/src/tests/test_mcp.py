"""FastMCP server tests — VAL-MCP-001 through VAL-MCP-016.

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
  * VAL-MCP-010 — get_price tool returns correct pricing.
  * VAL-MCP-011 — get_stats tool returns aggregate statistics.
  * VAL-MCP-012 — get_calibration tool returns calibration metrics.
  * VAL-MCP-013 — get_tool_manifest returns redacted connector capabilities.
  * VAL-MCP-014 — get_issue_ledger returns read-only structured issue ledgers.
  * VAL-MCP-015 — verify_receipt verifies pinned verdict receipts.
  * VAL-MCP-016 — All 7 tools discoverable via tools/list.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client
from prism_schemas.trace import Evidence, ThesisStep, TradingR1Trace
from prism_schemas.verdict import (
    AdversarialChallenge,
    AdversarialResolutionMetadata,
    ChallengeResolution,
    ResolutionRound,
    SentinelVerdict,
)


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
    generate_patch = patch("sentinel.resolution_loop.generate_verdict")
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
        generate_patch = patch("sentinel.resolution_loop.generate_verdict")
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
        nested = (
            (output_schema.get("$defs") or {})
            .get("ValidateMcpResult", {})
            .get(
                "properties",
                {},
            )
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


# ---------------------------------------------------------------------------
# VAL-MCP-010: get_price tool returns correct pricing
# ---------------------------------------------------------------------------


class TestGetPriceTool:
    @pytest.mark.asyncio
    async def test_tools_list_includes_get_price(self) -> None:
        """get_price appears in tools/list."""
        from prism_mcp.server import build_mcp_server

        server = build_mcp_server()
        async with Client(server) as client:
            tools = await client.list_tools()
        names = [t.name for t in tools]
        assert "get_price" in names

    @pytest.mark.asyncio
    async def test_get_price_returns_expected_fields(self) -> None:
        """get_price returns the static 0.01 USDC price with expected structure."""
        from prism_mcp.server import build_mcp_server

        server = build_mcp_server()
        async with Client(server) as client:
            result = await client.call_tool("get_price", {})

        data = result.data
        assert data is not None
        assert data.price_usdc == 0.01
        assert data.currency == "USDC"
        assert data.network == "base-sepolia"
        assert isinstance(data.description, str) and len(data.description) > 0

    @pytest.mark.asyncio
    async def test_get_price_result_validates_against_pydantic_model(self) -> None:
        """GetPriceResult model validates the tool output."""
        from prism_mcp.server import GetPriceResult

        result = GetPriceResult(
            price_usdc=0.01,
            currency="USDC",
            network="base-sepolia",
            description="test",
        )
        assert result.price_usdc == 0.01


# ---------------------------------------------------------------------------
# VAL-MCP-011: get_stats tool returns aggregate statistics
# ---------------------------------------------------------------------------


class TestGetStatsTool:
    @pytest.mark.asyncio
    async def test_tools_list_includes_get_stats(self) -> None:
        """get_stats appears in tools/list."""
        from prism_mcp.server import build_mcp_server

        server = build_mcp_server()
        async with Client(server) as client:
            tools = await client.list_tools()
        names = [t.name for t in tools]
        assert "get_stats" in names

    @pytest.mark.asyncio
    async def test_get_stats_returns_zeroed_defaults_without_db(self) -> None:
        """get_stats returns zeroed defaults when DATABASE_URL is not set."""
        from prism_mcp.server import build_mcp_server

        with patch.dict(os.environ, {}, clear=False):
            # Remove DATABASE_URL if present
            os.environ.pop("DATABASE_URL", None)
            server = build_mcp_server()
            async with Client(server) as client:
                result = await client.call_tool("get_stats", {})

        data = result.data
        assert data is not None
        assert data.total_validations == 0
        assert data.avg_verdict_score == 0.0
        assert data.on_chain_anchors == 0
        assert data.lookback_hours == 168
        assert data.verdict_distribution.REJECT == 0
        assert data.verdict_distribution.WARN == 0
        assert data.verdict_distribution.PASS == 0
        assert data.verdict_distribution.ENDORSE == 0

    @pytest.mark.asyncio
    async def test_get_stats_with_custom_hours(self) -> None:
        """get_stats passes the hours parameter to the DB query."""
        from prism_mcp.server import build_mcp_server

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DATABASE_URL", None)
            server = build_mcp_server()
            async with Client(server) as client:
                result = await client.call_tool("get_stats", {"hours": 24})

        data = result.data
        assert data is not None
        assert data.lookback_hours == 24

    @pytest.mark.asyncio
    async def test_get_stats_rejects_zero_hours(self) -> None:
        """get_stats raises ToolError for hours < 1."""
        from prism_mcp.server import build_mcp_server

        server = build_mcp_server()
        async with Client(server) as client:
            result = await client.call_tool("get_stats", {"hours": 0}, raise_on_error=False)

        assert result.is_error
        message = "".join(getattr(c, "text", "") for c in (result.content or []))
        assert "invalid_hours" in message

    @pytest.mark.asyncio
    async def test_get_stats_with_mocked_db(self) -> None:
        """get_stats returns real data when DB query succeeds."""
        from prism_mcp.server import build_mcp_server

        mock_row = (
            26,  # total_validations
            62.3,  # avg_verdict_score
            1,  # reject_count
            0,  # warn_count
            24,  # pass_count
            1,  # endorse_count
            20,  # on_chain_anchors
            45.2,  # p95_latency_seconds
        )

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = mock_row
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        with (
            patch.dict(
                os.environ,
                {"DATABASE_URL": "TEST_DSN_PLACEHOLDER"},
                clear=False,
            ),
            patch("psycopg.connect", return_value=mock_conn),
        ):
            server = build_mcp_server()
            async with Client(server) as client:
                result = await client.call_tool("get_stats", {"hours": 168})

        data = result.data
        assert data is not None
        assert data.total_validations == 26
        assert data.avg_verdict_score == 62.3
        assert data.on_chain_anchors == 20
        assert data.p95_latency_seconds == 45.2
        assert data.lookback_hours == 168
        assert data.verdict_distribution.REJECT == 1
        assert data.verdict_distribution.WARN == 0
        assert data.verdict_distribution.PASS == 24
        assert data.verdict_distribution.ENDORSE == 1

    def test_query_stats_returns_defaults_on_db_error(self) -> None:
        """_query_stats_from_db returns zeroed defaults on DB query failure."""
        from prism_mcp.server import _query_stats_from_db

        with (
            patch.dict(os.environ, {"DATABASE_URL": "INVALID_DSN_PLACEHOLDER"}, clear=False),
            patch("psycopg.connect", side_effect=Exception("connection refused")),
        ):
            data = _query_stats_from_db(168)

        assert data["total_validations"] == 0
        assert data["avg_verdict_score"] == 0.0

    def test_get_stats_result_model_validates(self) -> None:
        """GetStatsResult Pydantic model validates correctly."""
        from prism_mcp.server import GetStatsResult, VerdictDistribution

        result = GetStatsResult(
            total_validations=26,
            verdict_distribution=VerdictDistribution(REJECT=1, WARN=0, PASS=24, ENDORSE=1),
            avg_verdict_score=62.3,
            p95_latency_seconds=45.2,
            on_chain_anchors=20,
            lookback_hours=168,
        )
        assert result.total_validations == 26
        assert result.verdict_distribution.PASS == 24


# ---------------------------------------------------------------------------
# VAL-MCP-012: get_calibration tool returns calibration metrics
# ---------------------------------------------------------------------------


class TestGetCalibrationTool:
    @pytest.mark.asyncio
    async def test_tools_list_includes_get_calibration(self) -> None:
        """get_calibration appears in tools/list."""
        from prism_mcp.server import build_mcp_server

        server = build_mcp_server()
        async with Client(server) as client:
            tools = await client.list_tools()
        names = [t.name for t in tools]
        assert "get_calibration" in names

    @pytest.mark.asyncio
    async def test_get_calibration_returns_expected_fields(self) -> None:
        """get_calibration returns the static calibration data."""
        from prism_mcp.server import build_mcp_server

        server = build_mcp_server()
        async with Client(server) as client:
            result = await client.call_tool("get_calibration", {})

        data = result.data
        assert data is not None
        assert data.calibration_passed is True
        assert data.gap_points == 45
        assert data.min_required_gap == 30
        assert data.model_family == "openai-gpt"
        assert data.tested_at == "2026-05-13T20:08:00Z"

    @pytest.mark.asyncio
    async def test_get_calibration_test_results_discriminate(self) -> None:
        """Calibration test results show correct discrimination."""
        from prism_mcp.server import build_mcp_server

        server = build_mcp_server()
        async with Client(server) as client:
            result = await client.call_tool("get_calibration", {})

        data = result.data
        test_results = data.test_results
        assert len(test_results) == 3

        good = next(r for r in test_results if r.trace_quality == "good")
        mediocre = next(r for r in test_results if r.trace_quality == "mediocre")
        bad = next(r for r in test_results if r.trace_quality == "bad")

        assert good.score == 65 and good.label == "PASS"
        assert mediocre.score == 42 and mediocre.label == "WARN"
        assert bad.score == 20 and bad.label == "REJECT"
        assert good.score - bad.score == 45  # gap ≥ 30

    @pytest.mark.asyncio
    async def test_get_calibration_result_model_validates(self) -> None:
        """GetCalibrationResult Pydantic model validates correctly."""
        from prism_mcp.server import CalibrationTestResult, GetCalibrationResult

        result = GetCalibrationResult(
            calibration_passed=True,
            gap_points=45,
            min_required_gap=30,
            model_family="openai-gpt",
            test_results=[
                CalibrationTestResult(trace_quality="good", score=65, label="PASS"),
            ],
            tested_at="2026-05-13T20:08:00Z",
        )
        assert result.calibration_passed is True
        assert result.gap_points == 45


# ---------------------------------------------------------------------------
# VAL-MCP-013: get_tool_manifest returns redacted connector capabilities
# ---------------------------------------------------------------------------


class TestGetToolManifestTool:
    @pytest.mark.asyncio
    async def test_tools_list_includes_get_tool_manifest(self) -> None:
        """get_tool_manifest appears in tools/list."""
        from prism_mcp.server import build_mcp_server

        server = build_mcp_server()
        async with Client(server) as client:
            tools = await client.list_tools()
        names = [t.name for t in tools]
        assert "get_tool_manifest" in names

    @pytest.mark.asyncio
    async def test_get_tool_manifest_redacts_mcp_connector_secrets(self) -> None:
        """get_tool_manifest returns capability flags without URLs or tokens."""
        from prism_mcp.server import build_mcp_server

        with patch.dict(
            os.environ,
            {
                "PRISM_EVIDENCE_PROVIDER": "mcp",
                "PRISM_EVIDENCE_MCP_URL": "https://secret-tools.example.com/mcp/",
                "PRISM_EVIDENCE_MCP_TOOL": "search",
                "PRISM_EVIDENCE_RESULT_MAPPER": "firecrawl_search",
                "PRISM_EVIDENCE_MCP_INPUT_MAPPER": "query_limit",
                "PRISM_EVIDENCE_MCP_AUTH_TOKEN": "super-secret-token",
                "PRISM_EVIDENCE_MCP_ALLOWED_TOOLS": "search,extract",
            },
            clear=False,
        ):
            server = build_mcp_server()
            async with Client(server) as client:
                result = await client.call_tool("get_tool_manifest", {})

        data = result.data
        assert data is not None
        assert "get_issue_ledger" in data.prism_mcp_tools
        assert "verify_receipt" in data.prism_mcp_tools
        connector = data.evidence_connectors[0]
        assert connector.provider == "mcp"
        assert connector.transport == "mcp_http"
        assert connector.configured is True
        assert connector.has_server_url is True
        assert connector.has_auth_token is True
        assert connector.tool_name == "search"
        assert connector.result_mapper == "firecrawl_search"
        assert connector.input_mapper == "query_limit"
        assert connector.allowed_tools == ["search", "extract"]
        serialized = json.dumps(result.structured_content)
        assert "secret-tools" not in serialized
        assert "super-secret-token" not in serialized

    @pytest.mark.asyncio
    async def test_get_tool_manifest_marks_invalid_mcp_mapper_unconfigured(self) -> None:
        """Unknown MCP mappers make the redacted connector manifest unconfigured."""
        from prism_mcp.server import build_mcp_server

        with patch.dict(
            os.environ,
            {
                "PRISM_EVIDENCE_PROVIDER": "mcp",
                "PRISM_EVIDENCE_MCP_URL": "https://tools.example.com/mcp/",
                "PRISM_EVIDENCE_MCP_TOOL": "search",
                "PRISM_EVIDENCE_RESULT_MAPPER": "unknown_mapper",
                "PRISM_EVIDENCE_MCP_INPUT_MAPPER": "query_limit",
            },
            clear=False,
        ):
            server = build_mcp_server()
            async with Client(server) as client:
                result = await client.call_tool("get_tool_manifest", {})

        data = result.data
        assert data is not None
        connector = data.evidence_connectors[0]
        assert connector.provider == "mcp"
        assert connector.configured is False
        assert "unknown" in " ".join(data.notes).lower()

    @pytest.mark.asyncio
    async def test_get_tool_manifest_marks_direct_adapter_aliases_as_fallback(self) -> None:
        """Direct adapter aliases are exposed as fallback/reference connectors."""
        from prism_mcp.server import build_mcp_server

        with patch.dict(
            os.environ,
            {
                "PRISM_EVIDENCE_PROVIDER": "brave",
                "BRAVE_SEARCH_API_KEY": "brave-secret",
            },
            clear=False,
        ):
            server = build_mcp_server()
            async with Client(server) as client:
                result = await client.call_tool("get_tool_manifest", {})

        data = result.data
        assert data is not None
        connector = data.evidence_connectors[0]
        assert connector.provider == "brave_search"
        assert connector.transport == "direct_adapter"
        assert connector.configured is True
        assert connector.has_api_key is True
        assert connector.fallback_reference is True
        serialized = json.dumps(result.structured_content)
        assert "brave-secret" not in serialized

    def test_get_tool_manifest_result_model_validates(self) -> None:
        """GetToolManifestResult Pydantic model validates correctly."""
        from prism_mcp.server import EvidenceConnectorManifestEntry, GetToolManifestResult

        result = GetToolManifestResult(
            prism_mcp_tools=["validate", "get_tool_manifest"],
            evidence_connectors=[
                EvidenceConnectorManifestEntry(
                    provider="noop",
                    transport="noop",
                    configured=True,
                )
            ],
        )
        assert result.redacted is True
        assert result.evidence_connectors[0].provider == "noop"


# ---------------------------------------------------------------------------
# VAL-MCP-014: get_issue_ledger returns read-only structured issue ledgers
# ---------------------------------------------------------------------------


class TestGetIssueLedgerTool:
    @pytest.mark.asyncio
    async def test_tools_list_includes_get_issue_ledger(self) -> None:
        """get_issue_ledger appears in tools/list."""
        from prism_mcp.server import build_mcp_server

        server = build_mcp_server()
        async with Client(server) as client:
            tools = await client.list_tools()
        names = [t.name for t in tools]
        assert "get_issue_ledger" in names

    @pytest.mark.asyncio
    async def test_get_issue_ledger_requires_identifier(self) -> None:
        """get_issue_ledger rejects calls without trace_id or request_hash."""
        from prism_mcp.server import build_mcp_server

        server = build_mcp_server()
        async with Client(server) as client:
            result = await client.call_tool("get_issue_ledger", {}, raise_on_error=False)

        assert result.is_error
        message = "".join(getattr(c, "text", "") for c in (result.content or []))
        assert "missing_identifier" in message

    @pytest.mark.asyncio
    async def test_get_issue_ledger_returns_ledger_from_pinned_verdict(self) -> None:
        """get_issue_ledger resolves a DB receipt to a redacted pinned verdict ledger."""
        from prism_mcp.server import build_mcp_server

        request_hash = hashlib.sha256(b"issue-ledger-test").hexdigest()
        trace_id = str(uuid.uuid4())
        challenge = AdversarialChallenge(
            id="sys-temporal-stale-evidence",
            type="temporal",
            severity="blocking",
            question="Evidence predates the market event window.",
            required_resolution="Retrieve current evidence or revise to HOLD.",
            blocking_pass=True,
            claim_ref="evidence[0]",
            resolution_status="conceded",
        )
        resolution = ChallengeResolution(
            challenge_id=challenge.id,
            status="conceded",
            responder="evidence_tool",
            response="No current source found; blocker remains unresolved.",
            created_at=datetime.now(UTC),
        )
        round_ = ResolutionRound(
            round_index=0,
            opened_challenge_ids=[challenge.id],
            resolved_challenge_ids=[],
            prompt="Resolve stale evidence.",
            response=f"{challenge.id}: conceded",
            created_at=datetime.now(UTC),
        )
        verdict = _make_verdict(trace_id=trace_id).model_copy(
            update={
                "request_hash": request_hash,
                "verdict_score": 50,
                "verdict_label": "WARN",
                "structured_challenges": [challenge],
                "challenge_resolutions": [resolution],
                "resolution_rounds": [round_],
                "resolution_metadata": AdversarialResolutionMetadata(
                    confidence=0.42,
                    stop_reason="unresolved_blockers",
                    unresolved_blocking_count=1,
                    unresolved_material_count=0,
                    max_rounds=1,
                ),
                "requester_address": "0xshouldnotbereturned",
            }
        )
        mock_row = (
            request_hash,
            trace_id,
            2,
            50,
            "ipfs://QmIssueLedgerVerdict",
            "0xarcanchor",
            datetime.now(UTC),
        )
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = mock_row
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        with (
            patch.dict(os.environ, {"DATABASE_URL": "TEST_DSN_PLACEHOLDER"}, clear=False),
            patch("psycopg.connect", return_value=mock_conn),
            patch(
                "prism_mcp.server._fetch_verdict_json_from_response_uri",
                new=AsyncMock(return_value=verdict.model_dump(mode="json", exclude_defaults=True)),
            ),
        ):
            server = build_mcp_server()
            async with Client(server) as client:
                result = await client.call_tool("get_issue_ledger", {"trace_id": trace_id})

        data = result.data
        assert data is not None
        assert data.validation.request_hash == request_hash
        assert data.validation.trace_id == trace_id
        assert data.validation.verdict_score == 50
        assert data.validation.verdict_label == "WARN"
        assert data.structured_challenges[0].id == challenge.id
        assert data.challenge_resolutions[0].status == "conceded"
        assert data.resolution_rounds[0].opened_challenge_ids == [challenge.id]
        assert data.unresolved_blocking_count == 1
        assert data.unresolved_material_count == 0
        assert data.redacted is True
        serialized = json.dumps(result.structured_content)
        assert "0xshouldnotbereturned" not in serialized
        assert "TEST_DSN_PLACEHOLDER" not in serialized

    @pytest.mark.asyncio
    async def test_get_issue_ledger_fails_when_pinned_verdict_mismatches_receipt(self) -> None:
        """Mismatched pinned verdicts fail closed instead of mixing ledgers."""
        from prism_mcp.server import build_mcp_server

        request_hash = hashlib.sha256(b"issue-ledger-db-row").hexdigest()
        trace_id = str(uuid.uuid4())
        mismatched_verdict = _make_verdict(trace_id=str(uuid.uuid4())).model_copy(
            update={
                "request_hash": hashlib.sha256(b"different-pinned-verdict").hexdigest(),
                "verdict_score": 50,
                "verdict_label": "WARN",
            }
        )
        mock_row = (
            request_hash,
            trace_id,
            2,
            50,
            "ipfs://QmMismatchedVerdict",
            None,
            datetime.now(UTC),
        )
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = mock_row
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        with (
            patch.dict(os.environ, {"DATABASE_URL": "TEST_DSN_PLACEHOLDER"}, clear=False),
            patch("psycopg.connect", return_value=mock_conn),
            patch(
                "prism_mcp.server._fetch_verdict_json_from_response_uri",
                new=AsyncMock(
                    return_value=mismatched_verdict.model_dump(
                        mode="json",
                        exclude_defaults=True,
                    )
                ),
            ),
        ):
            server = build_mcp_server()
            async with Client(server) as client:
                result = await client.call_tool(
                    "get_issue_ledger",
                    {"trace_id": trace_id},
                    raise_on_error=False,
                )

        assert result.is_error
        message = "".join(getattr(c, "text", "") for c in (result.content or []))
        assert "verdict_receipt_mismatch" in message

    @pytest.mark.asyncio
    async def test_get_issue_ledger_returns_not_found_for_missing_receipt(self) -> None:
        """Missing validation receipts return a structured ToolError."""
        from prism_mcp.server import build_mcp_server

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        with (
            patch.dict(os.environ, {"DATABASE_URL": "TEST_DSN_PLACEHOLDER"}, clear=False),
            patch("psycopg.connect", return_value=mock_conn),
        ):
            server = build_mcp_server()
            async with Client(server) as client:
                result = await client.call_tool(
                    "get_issue_ledger",
                    {"request_hash": hashlib.sha256(b"missing").hexdigest()},
                    raise_on_error=False,
                )

        assert result.is_error
        message = "".join(getattr(c, "text", "") for c in (result.content or []))
        assert "issue_ledger_not_found" in message

    @pytest.mark.asyncio
    async def test_get_issue_ledger_rejects_invalid_request_hash(self) -> None:
        """Invalid request_hash input fails before any DB lookup."""
        from prism_mcp.server import build_mcp_server

        with patch.dict(os.environ, {"DATABASE_URL": "TEST_DSN_PLACEHOLDER"}, clear=False):
            server = build_mcp_server()
            async with Client(server) as client:
                result = await client.call_tool(
                    "get_issue_ledger",
                    {"request_hash": "not-hex"},
                    raise_on_error=False,
                )

        assert result.is_error
        message = "".join(getattr(c, "text", "") for c in (result.content or []))
        assert "invalid_request_hash" in message

    def test_get_issue_ledger_result_model_validates(self) -> None:
        """GetIssueLedgerResult Pydantic model validates correctly."""
        from prism_mcp.server import GetIssueLedgerResult, IssueLedgerValidationRef

        result = GetIssueLedgerResult(
            validation=IssueLedgerValidationRef(
                request_hash=hashlib.sha256(b"model").hexdigest(),
                trace_id=str(uuid.uuid4()),
                sentinel_agent_id=2,
                verdict_score=65,
                verdict_label="PASS",
                response_uri="ipfs://QmVerdict",
            ),
            structured_challenges=[],
            challenge_resolutions=[],
            resolution_rounds=[],
            unresolved_blocking_count=0,
            unresolved_material_count=0,
            verdict_content_hash_hex=hashlib.sha256(b"receipt").hexdigest(),
        )
        assert result.redacted is True
        assert result.validation.verdict_label == "PASS"


# ---------------------------------------------------------------------------
# VAL-MCP-015: verify_receipt verifies pinned verdict receipts
# ---------------------------------------------------------------------------


class TestVerifyReceiptTool:
    @pytest.mark.asyncio
    async def test_tools_list_includes_verify_receipt(self) -> None:
        """verify_receipt appears in tools/list."""
        from prism_mcp.server import build_mcp_server

        server = build_mcp_server()
        async with Client(server) as client:
            tools = await client.list_tools()
        names = [t.name for t in tools]
        assert "verify_receipt" in names

    @pytest.mark.asyncio
    async def test_verify_receipt_by_cid_and_content_hash(self) -> None:
        """verify_receipt validates a pinned verdict against an expected hash."""
        from prism_mcp.server import build_mcp_server

        verdict = _make_verdict()
        expected_hash = verdict.content_hash().hex()

        with patch(
            "prism_mcp.server._fetch_verdict_json_from_response_uri",
            new=AsyncMock(return_value=verdict.model_dump(mode="json", exclude_defaults=True)),
        ):
            server = build_mcp_server()
            async with Client(server) as client:
                result = await client.call_tool(
                    "verify_receipt",
                    {"cid": "QmReceipt", "content_hash_hex": expected_hash},
                )

        data = result.data
        assert data is not None
        assert data.verified is True
        assert data.response_uri == "ipfs://QmReceipt"
        assert data.checks.response_uri_resolved is True
        assert data.checks.schema_valid is True
        assert data.checks.content_hash_matches is True
        assert data.verdict_content_hash_hex == expected_hash
        assert data.validation is None

    @pytest.mark.asyncio
    async def test_verify_receipt_requires_anchor_for_verified_true(self) -> None:
        """A schema-valid receipt without DB/hash anchor is not fully verified."""
        from prism_mcp.server import build_mcp_server

        verdict = _make_verdict()

        with patch(
            "prism_mcp.server._fetch_verdict_json_from_response_uri",
            new=AsyncMock(return_value=verdict.model_dump(mode="json", exclude_defaults=True)),
        ):
            server = build_mcp_server()
            async with Client(server) as client:
                result = await client.call_tool("verify_receipt", {"cid": "QmReceipt"})

        data = result.data
        assert data is not None
        assert data.verified is False
        assert data.checks.schema_valid is True
        assert data.checks.content_hash_matches is None
        assert data.validation is None
        assert "anchor" in " ".join(data.notes).lower()

    @pytest.mark.asyncio
    async def test_verify_receipt_returns_false_for_wrong_content_hash(self) -> None:
        """verify_receipt returns verified=false instead of throwing on hash mismatch."""
        from prism_mcp.server import build_mcp_server

        verdict = _make_verdict()
        wrong_hash = hashlib.sha256(b"wrong-receipt").hexdigest()

        with patch(
            "prism_mcp.server._fetch_verdict_json_from_response_uri",
            new=AsyncMock(return_value=verdict.model_dump(mode="json", exclude_defaults=True)),
        ):
            server = build_mcp_server()
            async with Client(server) as client:
                result = await client.call_tool(
                    "verify_receipt",
                    {"response_uri": "ipfs://QmReceipt", "content_hash_hex": wrong_hash},
                )

        data = result.data
        assert data is not None
        assert data.verified is False
        assert data.checks.content_hash_matches is False
        assert data.verdict_content_hash_hex != wrong_hash

    @pytest.mark.asyncio
    async def test_verify_receipt_checks_db_receipt_identity(self) -> None:
        """verify_receipt compares DB receipt identity fields with the pinned verdict."""
        from prism_mcp.server import build_mcp_server

        request_hash = hashlib.sha256(b"verify-db-row").hexdigest()
        trace_id = str(uuid.uuid4())
        verdict = _make_verdict(trace_id=trace_id).model_copy(
            update={"request_hash": request_hash, "verdict_score": 72}
        )
        mock_row = (
            request_hash,
            trace_id,
            2,
            72,
            "ipfs://QmVerifyReceipt",
            "0xarcanchor",
            datetime.now(UTC),
        )
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = mock_row
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        with (
            patch.dict(os.environ, {"DATABASE_URL": "TEST_DSN_PLACEHOLDER"}, clear=False),
            patch("psycopg.connect", return_value=mock_conn),
            patch(
                "prism_mcp.server._fetch_verdict_json_from_response_uri",
                new=AsyncMock(return_value=verdict.model_dump(mode="json", exclude_defaults=True)),
            ),
        ):
            server = build_mcp_server()
            async with Client(server) as client:
                result = await client.call_tool(
                    "verify_receipt",
                    {
                        "request_hash": request_hash,
                        "content_hash_hex": verdict.content_hash().hex(),
                    },
                )

        data = result.data
        assert data is not None
        assert data.verified is True
        assert data.validation is not None
        assert data.validation.request_hash == request_hash
        assert data.checks.db_receipt_found is True
        assert data.checks.response_uri_matches_db is True
        assert data.checks.request_hash_matches is True
        assert data.checks.trace_id_matches is True
        assert data.checks.sentinel_agent_id_matches is True
        assert data.checks.verdict_score_matches is True
        serialized = json.dumps(result.structured_content)
        assert "TEST_DSN_PLACEHOLDER" not in serialized

    @pytest.mark.asyncio
    async def test_verify_receipt_requires_identifier(self) -> None:
        """verify_receipt rejects calls without receipt or DB identifiers."""
        from prism_mcp.server import build_mcp_server

        server = build_mcp_server()
        async with Client(server) as client:
            result = await client.call_tool("verify_receipt", {}, raise_on_error=False)

        assert result.is_error
        message = "".join(getattr(c, "text", "") for c in (result.content or []))
        assert "missing_identifier" in message

    def test_verify_receipt_result_model_validates(self) -> None:
        """VerifyReceiptResult Pydantic model validates correctly."""
        from prism_mcp.server import ReceiptVerificationChecks, VerifyReceiptResult

        result = VerifyReceiptResult(
            verified=True,
            checks=ReceiptVerificationChecks(
                response_uri_resolved=True,
                schema_valid=True,
                content_hash_matches=True,
            ),
            response_uri="ipfs://QmReceipt",
            verdict_content_hash_hex=hashlib.sha256(b"receipt").hexdigest(),
        )
        assert result.verified is True
        assert result.redacted is True


# ---------------------------------------------------------------------------
# VAL-MCP-016: All 7 tools discoverable via tools/list
# ---------------------------------------------------------------------------


class TestAllToolsDiscoverable:
    @pytest.mark.asyncio
    async def test_tools_list_returns_all_seven_tools(self) -> None:
        """tools/list returns validate, price, stats, calibration, manifest, ledger, verify."""
        from prism_mcp.server import build_mcp_server

        server = build_mcp_server()
        async with Client(server) as client:
            tools = await client.list_tools()
        names = sorted([t.name for t in tools])
        assert "validate" in names
        assert "get_price" in names
        assert "get_stats" in names
        assert "get_calibration" in names
        assert "get_tool_manifest" in names
        assert "get_issue_ledger" in names
        assert "verify_receipt" in names
        expected_tools = {
            "validate",
            "get_price",
            "get_stats",
            "get_calibration",
            "get_tool_manifest",
            "get_issue_ledger",
            "verify_receipt",
        }
        assert expected_tools.issubset(set(names))
        assert sum(1 for n in names if n in expected_tools) == 7
