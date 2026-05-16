"""HTTP and input-loading helpers for the Prism CLI."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode, urlparse

import httpx
from pydantic import ValidationError

from prism_cli.config import CliConfig
from prism_cli.models import (
    MarketListResponse,
    MarketResolveResponse,
    PublicHistoryResponse,
    PublicStatsResponse,
    PublicTraceReport,
    SentinelValidationResult,
    TradingR1Trace,
    ValidationQuote,
    ValidationReceipt,
)

CID_RE = re.compile(r"^(Qm[1-9A-HJ-NP-Za-km-z]{44}|baf[0-9a-zA-Z]{20,})$")
TRACE_URL_RE = re.compile(r"/trace/([0-9a-fA-F-]{36})(?:$|[/?#])")
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
)

NETWORK_CONFIG: dict[str, dict[str, str]] = {
    "base-sepolia": {
        "caip2": "eip155:84532",
        "asset_contract": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
    },
    "eip155:84532": {
        "caip2": "eip155:84532",
        "asset_contract": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
    },
    "base": {
        "caip2": "eip155:8453",
        "asset_contract": "0x833589fCD6eDb6E08f4c7C32D4f71b54bda02913",
    },
    "eip155:8453": {
        "caip2": "eip155:8453",
        "asset_contract": "0x833589fCD6eDb6E08f4c7C32D4f71b54bda02913",
    },
    "arc-testnet": {
        "caip2": "eip155:5042002",
        "asset_contract": "0x3600000000000000000000000000000000000000",
    },
    "eip155:5042002": {
        "caip2": "eip155:5042002",
        "asset_contract": "0x3600000000000000000000000000000000000000",
    },
}


class PrismCliError(RuntimeError):
    """User-facing CLI error."""


def is_ipfs_cid(value: str) -> bool:
    """Return whether a string looks like an IPFS CID."""
    return bool(CID_RE.match(value.strip()))


def extract_cid(value: str) -> str | None:
    """Extract a CID from CID or ipfs://CID input."""
    raw = value.strip()
    if raw.startswith("ipfs://"):
        raw = raw.removeprefix("ipfs://")
    return raw if is_ipfs_cid(raw) else None


def extract_trace_id(value: str) -> str | None:
    """Extract a trace UUID from a raw UUID or dashboard trace URL."""
    raw = value.strip()
    if UUID_RE.match(raw):
        return raw
    match = TRACE_URL_RE.search(raw)
    return match.group(1) if match else None


async def load_trace(source: str, config: CliConfig) -> TradingR1Trace:
    """Load a Trading-R1 trace from a local JSON file or IPFS CID/URI."""
    path = Path(source)
    if path.exists():
        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise PrismCliError(f"Trace file is not valid JSON: {path}") from exc
        return _parse_trace(payload)

    cid = extract_cid(source)
    if cid:
        url = f"{config.normalized_ipfs_gateway()}/{cid}"
        async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
            response = await client.get(url)
        if response.status_code != 200:
            raise PrismCliError(f"IPFS gateway returned {response.status_code} for CID {cid}")
        return _parse_trace(response.json())

    raise PrismCliError(
        "Unsupported trace source. Provide a local JSON file, ipfs://CID, or raw IPFS CID."
    )


async def fetch_public_stats(config: CliConfig) -> PublicStatsResponse:
    """Fetch public Prism stats from the dashboard API."""
    url = f"{config.normalized_dashboard_url()}/api/public/stats"
    async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
        response = await client.get(url)
    if response.status_code != 200:
        raise PrismCliError(f"Stats API returned {response.status_code}: {response.text[:160]}")
    return PublicStatsResponse.model_validate(response.json())


async def fetch_public_history(config: CliConfig, limit: int) -> PublicHistoryResponse:
    """Fetch recent public Prism validations from the dashboard API."""
    safe_limit = max(1, min(100, limit))
    url = f"{config.normalized_dashboard_url()}/api/public/history?limit={safe_limit}"
    async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
        response = await client.get(url)
    if response.status_code != 200:
        raise PrismCliError(f"History API returned {response.status_code}: {response.text[:160]}")
    return PublicHistoryResponse.model_validate(response.json())


async def fetch_public_report(config: CliConfig, trace_source: str) -> PublicTraceReport:
    """Fetch a public report for a trace UUID or dashboard /trace URL."""
    trace_id = extract_trace_id(trace_source)
    if not trace_id:
        raise PrismCliError("Report source must be a trace UUID or dashboard /trace/<id> URL.")
    url = f"{config.normalized_dashboard_url()}/api/public/traces/{quote(trace_id)}/report"
    async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
        response = await client.get(url)
    if response.status_code == 404:
        raise PrismCliError(f"Trace not found: {trace_id}")
    if response.status_code != 200:
        raise PrismCliError(f"Report API returned {response.status_code}: {response.text[:160]}")
    return PublicTraceReport.model_validate(response.json())


async def fetch_markets(config: CliConfig, limit: int) -> MarketListResponse:
    """Fetch recommended Polymarket markets from Prism's gateway."""
    safe_limit = max(1, min(100, limit))
    url = f"{config.normalized_polymarket_gateway_url()}/markets/recommended?limit={safe_limit}"
    async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
        response = await client.get(url)
    if response.status_code != 200:
        raise PrismCliError(f"Markets API returned {response.status_code}: {response.text[:160]}")
    return MarketListResponse.model_validate(response.json())


async def resolve_market(config: CliConfig, query: str) -> MarketResolveResponse:
    """Resolve a market query to an explicit Polymarket token ID."""
    params = urlencode({"query": query})
    url = f"{config.normalized_polymarket_gateway_url()}/markets/resolve?{params}"
    async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
        response = await client.get(url)
    if response.status_code != 200:
        raise PrismCliError(
            f"Market resolve API returned {response.status_code}: {response.text[:160]}"
        )
    return MarketResolveResponse.model_validate(response.json())


async def request_validation_quote(
    config: CliConfig,
    source: str,
    trace_hash: str | None = None,
) -> ValidationQuote:
    """Request an x402 quote from the sentinel without submitting payment."""
    trace_uri, resolved_hash = await resolve_trace_uri_and_hash(source, config, trace_hash)
    body = _make_mcp_validate_body(trace_uri, resolved_hash)
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=httpx.Timeout(config.timeout_seconds),
    ) as client:
        session_id = await _mcp_handshake(client, config)
        response = await client.post(
            config.normalized_sentinel_url(),
            json=body,
            headers={**_mcp_headers(), "mcp-session-id": session_id},
        )
    if response.status_code != 402:
        raise PrismCliError(
            f"Expected sentinel quote to return 402, got {response.status_code}: "
            f"{response.text[:160]}"
        )
    payment = _parse_payment_required(response.json())
    return _quote_from_payment_requirements(trace_uri, resolved_hash, payment)


async def submit_paid_validation(
    config: CliConfig,
    source: str,
    x_payment_header: str,
    trace_hash: str | None = None,
) -> ValidationReceipt:
    """Submit a paid sentinel validation using an externally-signed X-PAYMENT header."""
    if not x_payment_header.strip():
        raise PrismCliError("Missing X-PAYMENT header value.")
    trace_uri, resolved_hash = await resolve_trace_uri_and_hash(source, config, trace_hash)
    body = _make_mcp_validate_body(trace_uri, resolved_hash)
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=httpx.Timeout(max(config.timeout_seconds, 180.0)),
    ) as client:
        session_id = await _mcp_handshake(client, config)
        quote_response = await client.post(
            config.normalized_sentinel_url(),
            json=body,
            headers={**_mcp_headers(), "mcp-session-id": session_id},
        )
        if quote_response.status_code != 402:
            raise PrismCliError(
                f"Expected sentinel quote to return 402, got {quote_response.status_code}: "
                f"{quote_response.text[:160]}"
            )
        quote = _quote_from_payment_requirements(
            trace_uri,
            resolved_hash,
            _parse_payment_required(quote_response.json()),
        )
        paid_response = await client.post(
            config.normalized_sentinel_url(),
            json=body,
            headers={
                **_mcp_headers(),
                "mcp-session-id": session_id,
                "X-PAYMENT": x_payment_header.strip(),
            },
        )
    if paid_response.status_code != 200:
        raise PrismCliError(
            f"Paid sentinel validation returned {paid_response.status_code}: "
            f"{paid_response.text[:200]}"
        )
    result_payload = _parse_mcp_result_payload(paid_response)
    structured = result_payload.get("structuredContent") or result_payload
    try:
        result = SentinelValidationResult.model_validate(structured)
    except ValidationError as exc:
        message = exc.errors()[0]["msg"]
        raise PrismCliError(f"Sentinel response was not a validation receipt: {message}") from exc
    return ValidationReceipt(quote=quote, result=result)


async def resolve_trace_uri_and_hash(
    source: str,
    config: CliConfig,
    trace_hash: str | None = None,
) -> tuple[str, str]:
    """Normalize a CID/IPFS source and resolve or validate its trace hash."""
    cid = extract_cid(source)
    if not cid:
        raise PrismCliError("Paid validation source must be an ipfs://CID or raw IPFS CID.")
    trace_uri = f"ipfs://{cid}"
    if trace_hash:
        return trace_uri, _normalize_trace_hash(trace_hash)
    trace = await load_trace(trace_uri, config)
    return trace_uri, compute_trace_hash(trace)


def compute_trace_hash(trace: TradingR1Trace) -> str:
    """Return the deterministic bytes32 hash used by Prism chain receipts."""
    canonical = json.dumps(trace.model_dump(mode="json"), sort_keys=True)
    return "0x" + hashlib.sha256(canonical.encode()).hexdigest()


async def _mcp_handshake(client: httpx.AsyncClient, config: CliConfig) -> str:
    """Complete the free MCP initialize handshake and return the session ID."""
    init_response = await client.post(
        config.normalized_sentinel_url(),
        json={
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {"experimental": {}, "sampling": {}},
                "clientInfo": {"name": "prism-cli", "version": "0.1.0"},
            },
        },
        headers=_mcp_headers(),
    )
    if init_response.status_code != 200:
        raise PrismCliError(
            f"MCP initialize failed: {init_response.status_code}: {init_response.text[:160]}"
        )
    session_id = init_response.headers.get("mcp-session-id")
    if not session_id:
        raise PrismCliError("MCP server did not return an mcp-session-id header.")
    initialized_response = await client.post(
        config.normalized_sentinel_url(),
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers={**_mcp_headers(), "mcp-session-id": session_id},
    )
    if initialized_response.status_code not in (200, 202):
        raise PrismCliError(
            "MCP notifications/initialized failed: "
            f"{initialized_response.status_code}: {initialized_response.text[:160]}"
        )
    return session_id


def _make_mcp_validate_body(trace_uri: str, trace_hash: str) -> dict[str, Any]:
    """Build the MCP tools/call request for sentinel validation."""
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "validate",
            "arguments": {"trace_uri": trace_uri, "trace_hash": trace_hash},
        },
    }


def _mcp_headers() -> dict[str, str]:
    """Headers accepted by FastMCP's streamable HTTP transport."""
    return {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }


def _parse_payment_required(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract payment requirements from Prism's JSON-RPC 402 envelope."""
    error = payload.get("error") if isinstance(payload, dict) else None
    data = error.get("data") if isinstance(error, dict) else payload
    if not isinstance(data, dict):
        raise PrismCliError("Sentinel 402 response did not include payment requirements.")
    required = ["amount", "asset", "scheme", "network"]
    missing = [key for key in required if key not in data]
    if missing:
        raise PrismCliError(f"Sentinel 402 response missing fields: {', '.join(missing)}")
    return data


def _quote_from_payment_requirements(
    trace_uri: str,
    trace_hash: str,
    payment: dict[str, Any],
) -> ValidationQuote:
    """Normalize raw sentinel payment requirements into CLI quote output."""
    network = str(payment.get("network", ""))
    network_info = NETWORK_CONFIG.get(network.lower(), {})
    amount_usdc = str(payment["amount"])
    amount_units = str(int(float(amount_usdc) * 1_000_000))
    return ValidationQuote(
        trace_uri=trace_uri,
        trace_hash=trace_hash,
        amount_usdc=amount_usdc,
        amount_units=amount_units,
        asset=str(payment["asset"]),
        asset_contract=network_info.get("asset_contract"),
        scheme=str(payment["scheme"]),
        network=network,
        caip2=network_info.get("caip2"),
        facilitator=str(payment["facilitator"]) if payment.get("facilitator") else None,
        facilitator_mode=(
            str(payment["facilitator_mode"]) if payment.get("facilitator_mode") else None
        ),
        recipient=str(payment["recipient"]) if payment.get("recipient") else None,
        raw=payment,
    )


def _parse_mcp_result_payload(response: httpx.Response) -> dict[str, Any]:
    """Parse JSON or SSE MCP response and return the result object."""
    content_type = response.headers.get("content-type", "").lower()
    if "text/event-stream" in content_type:
        data_line = next(
            (
                line.removeprefix("data:").strip()
                for line in response.text.splitlines()
                if line.startswith("data:")
            ),
            None,
        )
        if not data_line:
            raise PrismCliError("MCP SSE response had no data line.")
        payload = json.loads(data_line)
    else:
        payload = response.json()
    if not isinstance(payload, dict):
        raise PrismCliError("MCP response was not a JSON object.")
    error = payload.get("error")
    if isinstance(error, dict):
        message = str(error.get("message") or "MCP JSON-RPC error")
        raise PrismCliError(message)
    result = payload.get("result", payload)
    if not isinstance(result, dict):
        raise PrismCliError("MCP response did not include a result object.")
    if bool(result.get("isError") or result.get("is_error")):
        raise PrismCliError(f"Sentinel tool error: {_extract_mcp_error_text(result)}")
    return result


def _extract_mcp_error_text(result: dict[str, Any]) -> str:
    """Extract readable text from an MCP tool error result."""
    content = result.get("content")
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        if parts:
            return " ".join(parts)
    return "unknown MCP tool error"


def _normalize_trace_hash(value: str) -> str:
    """Normalize user-supplied trace hash to 0x-prefixed bytes32 hex."""
    raw = value.strip().lower()
    if raw.startswith("0x"):
        raw = raw[2:]
    if not re.fullmatch(r"[0-9a-f]{64}", raw):
        raise PrismCliError("Trace hash must be a 32-byte hex string.")
    return f"0x{raw}"


def dashboard_from_trace_url(value: str) -> str | None:
    """Return the origin from a dashboard trace URL if present."""
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc and TRACE_URL_RE.search(value):
        return f"{parsed.scheme}://{parsed.netloc}"
    return None


def _parse_trace(payload: Any) -> TradingR1Trace:
    """Validate raw JSON as a Trading-R1 trace."""
    try:
        return TradingR1Trace.model_validate(payload)
    except ValidationError as exc:
        message = exc.errors()[0]["msg"]
        raise PrismCliError(f"Input is not a valid Trading-R1 trace: {message}") from exc
