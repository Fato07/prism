"""x402 payment middleware for the sentinel /validate endpoint.

The sentinel exposes a paid `validate` resource. Callers must include a
valid x402 payment header that authorizes $0.01 USDC settlement via
the configured facilitator.

Design notes:
  - **Dual facilitator mode** controlled by ``X402_FACILITATOR_MODE``:
      * ``public`` (default): x402.org public facilitator on Base Sepolia.
      * ``circle``: Circle facilitator targeting Arc Testnet USDC.
    Both modes coexist; the env var is read at request time so toggling
    requires only a restart, not a code change.
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
  X402_RECIPIENT_ADDRESS     — Base address that receives USDC (public mode)
  X402_ARC_RECIPIENT_ADDRESS — Arc Testnet address that receives USDC (circle mode)
  X402_NETWORK               — x402 network identifier (default `"base-sepolia"`)
  X402_FACILITATOR_MODE      — `"public"` (default) or `"circle"`
  X402_FACILITATOR_URL       — public facilitator base URL (default `"https://x402.org/facilitator"`)
  X402_CIRCLE_FACILITATOR_URL — Circle facilitator base URL (circle mode, optional)
  X402_FACILITATOR_NAME      — facilitator identifier reported in 402 body (default `"x402"`)
  X402_SETTLEMENT_TIMEOUT_S  — settlement timeout seconds (default `10`)
  RAILWAY_ENVIRONMENT        — `"production"` → bypass mode is refused at startup

Circle facilitator on Arc Testnet — gap note (VAL-X402-CIRCLE-006):
  As of 2026-05-15 the Circle facilitator endpoint for Arc Testnet USDC
  settlement is **not publicly documented** with a stable URL or API
  contract. The public x402 path therefore defaults to Base Sepolia.
  When ``X402_FACILITATOR_MODE=circle`` and
  ``X402_CIRCLE_FACILITATOR_URL`` is unset, the middleware logs a clear
  warning and falls back to mock settlement (same as dev mode). Do NOT
  stub fake on-chain transactions — resolve this once Circle publishes
  the Arc Testnet facilitator endpoint.
"""

from __future__ import annotations

import asyncio
import base64
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
X402_DEFAULT_NETWORK = "base-sepolia"
X402_DEFAULT_FACILITATOR_MODE = "public"
X402_DEFAULT_FACILITATOR_NAME = "x402"
X402_DEFAULT_SETTLEMENT_TIMEOUT_S = 10.0

# Network identifiers — friendly slug → CAIP-2 → USDC contract address.
# x402.org's public facilitator currently supports Base Sepolia (84532) only;
# Base mainnet (8453) requires the Coinbase CDP-hosted facilitator (auth req'd).
# USDC EIP-712 domain `name` differs by network (verified by calling name()
# on each contract): Sepolia uses "USDC", mainnet uses "USD Coin". The
# facilitator reconstructs the EIP-712 typed-data hash from these fields when
# verifying the client's signature — a mismatch yields invalid_exact_evm_signature.
X402_NETWORK_MAP: dict[str, dict[str, str]] = {
    "base-sepolia": {
        "caip2": "eip155:84532",
        "usdc_address": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        "usdc_domain_name": "USDC",
        "usdc_domain_version": "2",
    },
    "base": {
        "caip2": "eip155:8453",
        "usdc_address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bda02913",
        "usdc_domain_name": "USD Coin",
        "usdc_domain_version": "2",
    },
    "eip155:84532": {
        "caip2": "eip155:84532",
        "usdc_address": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        "usdc_domain_name": "USDC",
        "usdc_domain_version": "2",
    },
    "eip155:8453": {
        "caip2": "eip155:8453",
        "usdc_address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bda02913",
        "usdc_domain_name": "USD Coin",
        "usdc_domain_version": "2",
    },
    # Arc Testnet — chain ID 5042002, native USDC at 0x3600… (6 decimals).
    # USDC is the native gas token on Arc, so the EIP-712 domain name
    # may differ from standard ERC-20 USDC. Using "USDC" / "2" as the
    # default; operator must verify via contract name() call once the
    # Circle facilitator endpoint is documented for Arc Testnet.
    "arc-testnet": {
        "caip2": "eip155:5042002",
        "usdc_address": "0x3600000000000000000000000000000000000000",
        "usdc_domain_name": "USDC",
        "usdc_domain_version": "2",
    },
    "eip155:5042002": {
        "caip2": "eip155:5042002",
        "usdc_address": "0x3600000000000000000000000000000000000000",
        "usdc_domain_name": "USDC",
        "usdc_domain_version": "2",
    },
}


def _resolve_network() -> dict[str, str]:
    """Return the CAIP-2 id and USDC contract address for the active network.

    When ``X402_FACILITATOR_MODE=circle``, the network is forced to
    Arc Testnet regardless of the ``X402_NETWORK`` env var. Otherwise
    the network is resolved from ``X402_NETWORK`` (default: base-sepolia).
    """
    mode = get_x402_facilitator_mode()
    if mode == "circle":
        info = X402_NETWORK_MAP.get("arc-testnet")
        if info is None:
            # Should never happen — arc-testnet is hardcoded above.
            logger.warning("x402_arc_testnet_missing_from_network_map")
            info = X402_NETWORK_MAP["base-sepolia"]
        return info

    raw = os.environ.get("X402_NETWORK", X402_DEFAULT_NETWORK).strip().lower()
    info = X402_NETWORK_MAP.get(raw)
    if info is None:
        logger.warning("x402_unknown_network", configured=raw, defaulting_to="base-sepolia")
        info = X402_NETWORK_MAP["base-sepolia"]
    return info

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
    """Receiving address for x402 USDC payments, mode-aware.

    When ``X402_FACILITATOR_MODE=circle``, reads ``X402_ARC_RECIPIENT_ADDRESS``.
    Otherwise reads ``X402_RECIPIENT_ADDRESS`` (Base Sepolia).
    """
    mode = get_x402_facilitator_mode()
    if mode == "circle":
        addr = os.environ.get("X402_ARC_RECIPIENT_ADDRESS", "").strip() or None
        if addr is None:
            logger.warning(
                "x402_arc_recipient_missing",
                message=(
                    "X402_ARC_RECIPIENT_ADDRESS is not set but "
                    "X402_FACILITATOR_MODE=circle. Settlement will fall back "
                    "to mock mode."
                ),
            )
        return addr
    return os.environ.get("X402_RECIPIENT_ADDRESS", "").strip() or None


def get_x402_network() -> str:
    """x402 network identifier for the active mode.

    When ``X402_FACILITATOR_MODE=circle``, returns ``"arc-testnet"``.
    Otherwise returns the ``X402_NETWORK`` env var (default: base-sepolia).
    """
    mode = get_x402_facilitator_mode()
    if mode == "circle":
        return "arc-testnet"
    return os.environ.get("X402_NETWORK", X402_DEFAULT_NETWORK).strip() or X402_DEFAULT_NETWORK


def get_x402_facilitator_mode() -> str:
    """Facilitator routing mode: ``"public"`` (default) or ``"circle"``.

    Both modes coexist; the env var is read at request time so toggling
    requires only a restart, not a code change.
    """
    raw = os.environ.get("X402_FACILITATOR_MODE", "").strip().lower()
    if raw == "circle":
        return "circle"
    # Any value other than "circle" (including empty, "public", or
    # unrecognized) defaults to the public Base Sepolia path.
    return "public"


def get_x402_facilitator_url() -> str | None:
    """Facilitator base URL for the active mode.

    When ``X402_FACILITATOR_MODE=circle``, returns ``X402_CIRCLE_FACILITATOR_URL``
    (if set) or None (gap — Circle facilitator on Arc Testnet is not yet
    documented). When ``public``, returns ``X402_FACILITATOR_URL``.
    """
    mode = get_x402_facilitator_mode()
    if mode == "circle":
        url = os.environ.get("X402_CIRCLE_FACILITATOR_URL", "").strip() or None
        if url is None:
            logger.warning(
                "x402_circle_facilitator_url_missing",
                message=(
                    "X402_CIRCLE_FACILITATOR_URL is not set. "
                    "Circle facilitator on Arc Testnet is not yet documented. "
                    "Falling back to mock settlement."
                ),
            )
        return url
    return os.environ.get("X402_FACILITATOR_URL", "").strip() or None


def get_x402_facilitator_name() -> str:
    """Facilitator identifier reported in 402 response body.

    When ``X402_FACILITATOR_MODE=circle``, returns ``"circle"`` unless
    ``X402_FACILITATOR_NAME`` is explicitly set.
    """
    mode = get_x402_facilitator_mode()
    explicit = os.environ.get("X402_FACILITATOR_NAME", "").strip()
    if explicit:
        return explicit
    if mode == "circle":
        return "circle"
    return X402_DEFAULT_FACILITATOR_NAME


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
        "facilitator_mode": get_x402_facilitator_mode(),
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
) -> tuple[bool, str | None, str | None, str | None]:
    """Settle the payment on Base via the configured x402 facilitator.

    Returns (success, tx_hash, error_code, payer).

    The ``payer`` is the on-chain address that funded the settlement,
    extracted from the facilitator's success response.  It is ``None``
    in mock / error paths.

    Falls back to a deterministic mock tx hash when no facilitator URL or
    recipient address is configured. The mock path is intentional for
    development and unit tests so the downstream pipeline can still record
    a non-null `payment_tx_hash` without touching the chain.

    When ``X402_FACILITATOR_MODE=circle`` and the Circle facilitator URL
    is not configured (Arc Testnet gap), the mock path is also used and a
    clear warning is logged. See module docstring for the gap note.
    """
    facilitator_url = get_x402_facilitator_url()
    recipient = get_x402_recipient()

    if not facilitator_url or not recipient:
        mock_hash = (
            "0x" + hashlib.sha256(f"x402-mock-settlement:{payment_token}".encode()).hexdigest()
        )
        logger.info(
            "x402_settled_mock",
            tx_hash=mock_hash,
            facilitator_mode=get_x402_facilitator_mode(),
            **request_context,
        )
        return True, mock_hash, None, None

    # The X-PAYMENT header value is base64-encoded JSON of an x402 v2
    # PaymentPayload. The facilitator's /settle endpoint expects the *decoded*
    # object under the key `paymentPayload` (not the raw base64 string under
    # `payment` — that was a pre-v2 shape and the public facilitator now rejects
    # it with `errorReason: missing_parameters`).
    try:
        decoded_bytes = base64.b64decode(payment_token, validate=False)
        payment_payload_obj = json.loads(decoded_bytes)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning(
            "x402_payment_decode_failed",
            error=str(exc),
            **request_context,
        )
        return False, None, "invalid_payment_token", None

    net = _resolve_network()
    # USDC has 6 decimals on every EVM chain; convert decimal string to smallest unit.
    try:
        amount_smallest = str(int(float(get_x402_price_usdc()) * 1_000_000))
    except (ValueError, TypeError):
        amount_smallest = "10000"  # 0.01 USDC fallback

    payload = {
        "x402Version": 2,
        "paymentPayload": payment_payload_obj,
        "paymentRequirements": {
            "scheme": "exact",
            "network": net["caip2"],
            "asset": net["usdc_address"],
            "amount": amount_smallest,
            "payTo": recipient,
            "maxTimeoutSeconds": 120,
            "extra": {
                "name": net["usdc_domain_name"],
                "version": net["usdc_domain_version"],
            },
        },
    }

    settle_url = f"{facilitator_url.rstrip('/')}/settle"
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(8.0),
            follow_redirects=True,
        ) as client:
            resp = await client.post(settle_url, json=payload)
            if resp.status_code != 200:
                logger.warning(
                    "x402_facilitator_non_200",
                    status=resp.status_code,
                    body=resp.text[:400],
                    **request_context,
                )
                return False, None, "settlement_failed", None
            data = resp.json()
            if not data.get("success"):
                # Log the structured error so we can debug rejection reasons
                # (invalid_exact_evm_signature, insufficient_funds, etc).
                logger.warning(
                    "x402_settlement_rejected",
                    error_reason=data.get("errorReason"),
                    error_message=data.get("errorMessage"),
                    payer=data.get("payer"),
                    facilitator_network=data.get("network"),
                    **request_context,
                )
                return False, None, "settlement_failed", None
            tx_hash = (
                data.get("transaction") or data.get("txHash") or data.get("hash")
            )
            payer = data.get("payer")
            logger.info(
                "x402_settlement_succeeded",
                tx_hash=tx_hash,
                payer=payer,
                facilitator_mode=get_x402_facilitator_mode(),
                **request_context,
            )
            return True, tx_hash, None, payer
    except httpx.TimeoutException:
        return False, None, "payment_settlement_timeout", None
    except httpx.HTTPError as exc:
        logger.error("x402_settlement_http_error", error=str(exc))
        return False, None, "settlement_failed", None


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


# MCP JSON-RPC methods that are gratis (the protocol's free metadata layer):
# clients need them to discover tools / set up the session, and charging for
# them creates a chicken-and-egg with the session handshake. Only the
# `tools/call` method actually invokes a paid resource.
MCP_FREE_METHODS: frozenset[str] = frozenset(
    {
        "initialize",
        "notifications/initialized",
        "notifications/cancelled",
        "ping",
        "tools/list",
        "resources/list",
        "prompts/list",
    }
)


async def _read_mcp_method(request: Request) -> str | None:
    """Best-effort: extract the JSON-RPC method name from an MCP request body.

    Reads the body once via ``await request.body()`` which Starlette caches
    internally, so downstream FastMCP can re-read the same bytes without
    the stream being exhausted. Returns ``None`` on any parse failure so the
    middleware falls through to the default paywall path.
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
        m = payload.get("method")
        if isinstance(m, str):
            return m
    return None


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

    # MCP setup methods (initialize, tools/list, etc.) pass through without
    # payment so clients can complete the JSON-RPC handshake. Only paid
    # actions (``tools/call``) actually hit the paywall below.
    if _is_mcp_path(request.url.path):
        method = await _read_mcp_method(request)
        if method in MCP_FREE_METHODS:
            logger.info(
                "x402_mcp_free_method",
                path=request.url.path,
                method=method,
            )
            return await call_next(request)

    if is_x402_bypass_enabled():
        request.state.x402_payment_tx_hash = None
        request.state.x402_payer_address = None
        return await call_next(request)

    if _bypass_via_header(request):
        logger.info("x402_internal_bypass", path=request.url.path)
        request.state.x402_payment_tx_hash = None
        request.state.x402_payer_address = None
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
        success, tx_hash, settle_error, payer = await asyncio.wait_for(
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
    request.state.x402_payer_address = payer
    logger.info(
        "x402_payment_accepted",
        path=request.url.path,
        tx_hash=tx_hash,
        payer=payer,
        facilitator_mode=get_x402_facilitator_mode(),
    )
    return await call_next(request)
