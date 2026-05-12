"""x402 payment middleware for the sentinel /validate endpoint.

The sentinel exposes a paid `validate` resource. Callers must include a
valid x402 payment header that authorizes $0.01 USDC settlement on Base
via Circle Gateway / an x402-compatible facilitator.

Design notes:
  - x402 settles on Base (chain 8453), NOT Arc. The sentinel service
    runs on Railway; only the payment leg touches Base.
  - The `x402[fastapi]` SDK is installed and its types are used for
    parsing payment payloads. Settlement happens against the configured
    facilitator via HTTP (the SDK's `payment_middleware_from_config`
    is intentionally not used here because we need fine-grained control
    over the 402 body shape, the legacy `x402-payment` header name, and
    the internal bypass channel for trader-to-sentinel calls).
  - In development / unit tests (no facilitator URL or recipient
    configured), settlement returns a deterministic mock tx hash so the
    downstream pipeline still has a `payment_tx_hash` to record.

Env vars:
  X402_BYPASS                — `"1"` / `"true"` → skip all payment checks (dev/test only)
  X402_INTERNAL_BYPASS_TOKEN — opaque token; matching `X402-Bypass` request header bypasses payment
  X402_PRICE_USDC            — required price (default `"0.01"`)
  X402_RECIPIENT_ADDRESS     — Base address that receives USDC
  X402_NETWORK               — x402 network identifier (default `"base"`)
  X402_FACILITATOR_URL       — facilitator base URL (e.g. `"https://x402.org/facilitator"`)
  X402_FACILITATOR_NAME      — facilitator identifier reported in 402 body (default `"x402"`)
  X402_SETTLEMENT_TIMEOUT_S  — settlement timeout seconds (default `10`)
  RAILWAY_ENVIRONMENT        — `"production"` → bypass mode is refused at startup
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse

logger = structlog.get_logger("prism.sentinel.x402")

X402_PAYMENT_HEADER = "x402-payment"
X402_STANDARD_PAYMENT_HEADER = "x-payment"
X402_BYPASS_HEADER = "x402-bypass"
X402_ASSET = "USDC"
X402_DEFAULT_PRICE_USDC = "0.01"
X402_DEFAULT_NETWORK = "base"
X402_DEFAULT_FACILITATOR_NAME = "x402"
X402_DEFAULT_SETTLEMENT_TIMEOUT_S = 10.0

MCP_PROTECTED_PREFIX = "/mcp"

JSONRPC_PAYMENT_REQUIRED_CODE = -32002
JSONRPC_PAYMENT_TIMEOUT_CODE = -32004

_consumed_payment_tokens: set[str] = set()
_consumed_lock = asyncio.Lock()


def get_x402_price_usdc() -> str:
    """Configured price per validation, in USDC."""
    return os.environ.get("X402_PRICE_USDC", X402_DEFAULT_PRICE_USDC).strip() or (
        X402_DEFAULT_PRICE_USDC
    )


def get_x402_recipient() -> str | None:
    """Base address that receives x402 USDC payments."""
    return os.environ.get("X402_RECIPIENT_ADDRESS", "").strip() or None


def get_x402_network() -> str:
    """x402 network identifier (default: `base`)."""
    return os.environ.get("X402_NETWORK", X402_DEFAULT_NETWORK).strip() or X402_DEFAULT_NETWORK


def get_x402_facilitator_url() -> str | None:
    """Facilitator base URL (e.g. `https://x402.org/facilitator`)."""
    return os.environ.get("X402_FACILITATOR_URL", "").strip() or None


def get_x402_facilitator_name() -> str:
    """Facilitator identifier reported in 402 response body."""
    return (
        os.environ.get("X402_FACILITATOR_NAME", X402_DEFAULT_FACILITATOR_NAME).strip()
        or X402_DEFAULT_FACILITATOR_NAME
    )


def get_x402_settlement_timeout_s() -> float:
    """Maximum seconds to wait for settlement before returning 504."""
    raw = os.environ.get("X402_SETTLEMENT_TIMEOUT_S", "").strip()
    if not raw:
        return X402_DEFAULT_SETTLEMENT_TIMEOUT_S
    try:
        return float(raw)
    except ValueError:
        return X402_DEFAULT_SETTLEMENT_TIMEOUT_S


def is_x402_bypass_enabled() -> bool:
    """Whether the global `X402_BYPASS` env var is on."""
    return os.environ.get("X402_BYPASS", "").strip().lower() in ("1", "true", "yes")


def is_production() -> bool:
    """Whether the service is running in a Railway production environment."""
    return os.environ.get("RAILWAY_ENVIRONMENT", "").strip().lower() in ("production", "prod")


def assert_bypass_safe_at_startup() -> None:
    """Refuse to start when bypass is enabled in production.

    VAL-X402-007 requires this hard gate so an accidental
    `X402_BYPASS=true` deploy cannot disable nanopayment economics.
    """
    if is_production() and is_x402_bypass_enabled():
        logger.error(
            "x402_bypass_enabled_in_production",
            message=(
                "X402_BYPASS must NOT be enabled in production "
                "(RAILWAY_ENVIRONMENT=production). Refusing to start."
            ),
        )
        sys.exit(1)


def reset_consumed_tokens_for_testing() -> None:
    """Clear the in-memory consumed-token set. Test-only helper."""
    _consumed_payment_tokens.clear()


def _payment_required_body(
    detail: str = "Payment required",
    *,
    error: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "detail": detail,
        "amount": get_x402_price_usdc(),
        "asset": X402_ASSET,
        "facilitator": get_x402_facilitator_name(),
        "network": get_x402_network(),
        "scheme": "exact",
    }
    recipient = get_x402_recipient()
    if recipient:
        body["recipient"] = recipient
    if error:
        body["error"] = error
    return body


def _malformed_reason(token: str) -> str | None:
    """Return a specific error code if the payment token is obviously bad."""
    stripped = token.strip()
    if not stripped:
        return "invalid_payment_token"

    lowered = stripped.lower()
    if lowered == "expired" or lowered.endswith(":expired"):
        return "payment_expired"
    if lowered in {"invalid", "corrupted", "malformed", "bad", "null", "none"}:
        return "invalid_payment_token"

    if len(stripped) < 8:
        return "invalid_payment_token"

    return None


async def _settle_payment(
    payment_token: str,
    *,
    request_context: dict[str, Any],
) -> tuple[bool, str | None, str | None]:
    """Settle the payment on Base via the configured x402 facilitator.

    Returns (success, tx_hash, error_code).

    Falls back to a deterministic mock tx hash when no facilitator URL or
    recipient address is configured. The mock path is intentional for
    development and unit tests so the downstream pipeline can still record
    a non-null `payment_tx_hash` without touching the chain.
    """
    facilitator_url = get_x402_facilitator_url()
    recipient = get_x402_recipient()

    if not facilitator_url or not recipient:
        mock_hash = (
            "0x" + hashlib.sha256(f"x402-mock-settlement:{payment_token}".encode()).hexdigest()
        )
        logger.info("x402_settled_mock", tx_hash=mock_hash, **request_context)
        return True, mock_hash, None

    payload = {
        "x402Version": 2,
        "payment": payment_token,
        "paymentRequirements": {
            "scheme": "exact",
            "network": get_x402_network(),
            "asset": X402_ASSET,
            "payTo": recipient,
            "maxAmountRequired": get_x402_price_usdc(),
        },
    }

    settle_url = f"{facilitator_url.rstrip('/')}/settle"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0)) as client:
            resp = await client.post(settle_url, json=payload)
            if resp.status_code != 200:
                logger.warning(
                    "x402_facilitator_non_200",
                    status_code=resp.status_code,
                    body=resp.text[:200],
                )
                return False, None, "settlement_failed"
            data = resp.json()
            if not data.get("success"):
                return False, None, "settlement_failed"
            tx_hash = data.get("txHash") or data.get("transaction") or data.get("hash")
            return True, tx_hash, None
    except httpx.TimeoutException:
        return False, None, "payment_settlement_timeout"
    except httpx.HTTPError as exc:
        logger.error("x402_settlement_http_error", error=str(exc))
        return False, None, "settlement_failed"


def _bypass_via_header(request: Request) -> bool:
    """Return True when the X402-Bypass request header authorizes a skip.

    If `X402_INTERNAL_BYPASS_TOKEN` is set, the header value must match it
    exactly. If the env var is absent, any non-empty header value is
    accepted (this is the trader→sentinel internal channel in dev).
    """
    header_value = request.headers.get(X402_BYPASS_HEADER, "").strip()
    if not header_value:
        return False

    expected = os.environ.get("X402_INTERNAL_BYPASS_TOKEN", "").strip()
    if expected:
        return header_value == expected
    return True


def _is_protected_path(path: str, method: str) -> bool:
    """Whether the given request targets a paywalled resource.

    The sentinel protects two surfaces:
      * ``POST /validate`` — the legacy REST adversarial validator.
      * Any request under ``/mcp`` — the FastMCP ASGI sub-app, regardless of
        method, because the MCP streamable HTTP transport uses ``POST`` for
        ``tools/call`` and ``GET`` for the SSE stream. GET requests without
        SSE headers still trigger downstream protocol activity and so are
        gated as well.
    """
    if path == "/validate" and method == "POST":
        return True
    return path == MCP_PROTECTED_PREFIX or path.startswith(MCP_PROTECTED_PREFIX + "/")


def _is_mcp_path(path: str) -> bool:
    """Whether the request targets the FastMCP ASGI sub-app at /mcp."""
    return path == MCP_PROTECTED_PREFIX or path.startswith(MCP_PROTECTED_PREFIX + "/")


async def _read_mcp_request_id(request: Request) -> Any:
    """Best-effort extraction of the JSON-RPC ``id`` from an MCP request body.

    The MCP streamable HTTP transport carries each request as a JSON-RPC 2.0
    payload in the POST body. We need the ``id`` so the 402/504 error envelope
    can echo it back, letting JSON-RPC clients correlate the failure with the
    originating call. Returns ``None`` (which renders as JSON ``null``) when
    the body is missing, non-JSON, batched, or otherwise unparseable — the
    error envelope is still valid JSON-RPC in that case.
    """
    if request.method.upper() != "POST":
        return None
    try:
        raw = await request.body()
    except Exception:
        return None
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if isinstance(payload, dict):
        rpc_id = payload.get("id")
        if isinstance(rpc_id, str | int) or rpc_id is None:
            return rpc_id
    return None


def _jsonrpc_error_envelope(
    *,
    request_id: Any,
    code: int,
    message: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 error response body.

    MCP clients parse server failures from this shape rather than the raw
    HTTP body, so the payment requirement details live under ``error.data``.
    """
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": code,
            "message": message,
            "data": data,
        },
    }


async def _payment_required_response(
    request: Request,
    *,
    status_code: int,
    detail: str,
    error: str | None = None,
    body_override: dict[str, Any] | None = None,
) -> JSONResponse:
    """Return a payment-required JSONResponse, MCP-aware.

    For ``/mcp`` requests the body is wrapped in a JSON-RPC 2.0 error envelope
    carrying the payment details under ``error.data``. For any other protected
    route (currently just ``/validate``) the body keeps the legacy flat shape
    so existing REST clients continue to read ``body["amount"]`` etc.
    """
    flat_body = body_override or _payment_required_body(detail, error=error)
    if not _is_mcp_path(request.url.path):
        return JSONResponse(status_code=status_code, content=flat_body)

    request_id = await _read_mcp_request_id(request)
    rpc_code = (
        JSONRPC_PAYMENT_TIMEOUT_CODE
        if error == "payment_settlement_timeout"
        else JSONRPC_PAYMENT_REQUIRED_CODE
    )
    envelope = _jsonrpc_error_envelope(
        request_id=request_id,
        code=rpc_code,
        message=detail,
        data=flat_body,
    )
    return JSONResponse(status_code=status_code, content=envelope)


async def x402_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Middleware that enforces x402 payment on protected sentinel routes.

    Protected routes are ``POST /validate`` and anything under ``/mcp``
    (the FastMCP ASGI sub-app). All other paths (e.g. ``/health``) pass
    through unconditionally.

    Pipeline:
      1. Not a protected path → pass through.
      2. `X402_BYPASS=1` env or trusted `X402-Bypass` header → pass through.
      3. Missing payment header → HTTP 402 with payment requirements.
      4. Malformed / expired payment token → HTTP 402 with specific error.
      5. Token already consumed → HTTP 402 with `payment_already_consumed`.
      6. Settle on Base via facilitator (timeout 10s) → HTTP 504 on timeout.
      7. Settlement failed → HTTP 402 with `settlement_failed`.
      8. Success → mark consumed, stash tx hash, pass through.
    """
    if not _is_protected_path(request.url.path, request.method):
        return await call_next(request)

    if is_x402_bypass_enabled():
        request.state.x402_payment_tx_hash = None
        return await call_next(request)

    if _bypass_via_header(request):
        logger.info("x402_internal_bypass", path=request.url.path)
        request.state.x402_payment_tx_hash = None
        return await call_next(request)

    payment_token = request.headers.get(X402_PAYMENT_HEADER, "").strip()
    if not payment_token:
        payment_token = request.headers.get(X402_STANDARD_PAYMENT_HEADER, "").strip()

    if not payment_token:
        logger.info("x402_payment_required", path=request.url.path)
        return await _payment_required_response(
            request,
            status_code=402,
            detail="Payment required",
        )

    malformed = _malformed_reason(payment_token)
    if malformed is not None:
        logger.info("x402_payment_malformed", path=request.url.path, error=malformed)
        return await _payment_required_response(
            request,
            status_code=402,
            detail="Payment invalid",
            error=malformed,
        )

    async with _consumed_lock:
        if payment_token in _consumed_payment_tokens:
            logger.info("x402_payment_already_consumed", path=request.url.path)
            return await _payment_required_response(
                request,
                status_code=402,
                detail="Payment already consumed",
                error="payment_already_consumed",
            )

    timeout_s = get_x402_settlement_timeout_s()
    try:
        success, tx_hash, settle_error = await asyncio.wait_for(
            _settle_payment(
                payment_token,
                request_context={"path": request.url.path},
            ),
            timeout=timeout_s,
        )
    except TimeoutError:
        logger.warning("x402_settlement_timeout_outer", timeout_s=timeout_s)
        return await _payment_required_response(
            request,
            status_code=504,
            detail="Payment settlement timeout",
            error="payment_settlement_timeout",
            body_override={
                "detail": "Payment settlement timeout",
                "error": "payment_settlement_timeout",
                "amount": get_x402_price_usdc(),
                "asset": X402_ASSET,
            },
        )

    if not success:
        if settle_error == "payment_settlement_timeout":
            return await _payment_required_response(
                request,
                status_code=504,
                detail="Payment settlement timeout",
                error="payment_settlement_timeout",
                body_override={
                    "detail": "Payment settlement timeout",
                    "error": "payment_settlement_timeout",
                    "amount": get_x402_price_usdc(),
                    "asset": X402_ASSET,
                },
            )
        return await _payment_required_response(
            request,
            status_code=402,
            detail="Settlement failed",
            error=settle_error or "settlement_failed",
        )

    async with _consumed_lock:
        _consumed_payment_tokens.add(payment_token)

    request.state.x402_payment_tx_hash = tx_hash
    logger.info("x402_payment_accepted", path=request.url.path, tx_hash=tx_hash)
    return await call_next(request)
