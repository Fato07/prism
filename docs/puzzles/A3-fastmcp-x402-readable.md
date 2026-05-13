# Puzzle A3 — FastMCP mounted on x402-protected FastAPI

> **Readable version for review.** The JSON payload to paste into
> `arc-canteen submit-puzzle` lives in `A3-fastmcp-x402.json`.

---

## prompt

I'm exposing a paid tool via FastMCP. I mount it as an ASGI sub-app on a FastAPI
service at `/mcp` (streamable-HTTP transport), and I want to gate it with
x402-style USDC payments using `x402-fastapi`. My existing REST endpoint
`POST /validate` already returns the standard flat 402 body
`{detail, amount, asset, facilitator, network, scheme, recipient}` and REST
clients depend on that shape.

The problem: when an MCP client (Claude Desktop, `fastmcp.Client`, etc.) hits
`/mcp` without a payment header, the raw HTTP 402 response with that flat body
breaks the client — it just sees "protocol error" or hangs. MCP traffic is
JSON-RPC 2.0 over HTTP, so the client expects a JSON-RPC error envelope, not an
HTTP-shaped body, and it needs to correlate the failure with the originating
`tools/call` `id`.

Write a single FastAPI middleware function `x402_middleware(request, call_next)`
that:

1. Protects `POST /validate` AND every method under `/mcp` (FastMCP's
   streamable-HTTP transport uses `POST` for `tools/call` and `GET` with SSE
   headers for the stream — both must be gated).
2. For `/validate` failures, returns the legacy flat 402 body so existing REST
   clients keep working.
3. For `/mcp` failures, returns a JSON-RPC 2.0 error envelope
   `{"jsonrpc":"2.0","id":<echoed>,"error":{"code","message","data"}}` with the
   payment details under `error.data`, and the original `id` from the request
   body echoed back so the JSON-RPC client can correlate. The envelope must
   still come over HTTP 402 (or 504 on timeout) so HTTP-aware proxies/loggers
   see the right status.
4. Distinguishes payment-required (use JSON-RPC code `-32002`) from
   settlement-timeout (use `-32004`).
5. On successful settlement, makes the on-chain settlement tx hash available
   to the downstream MCP tool implementation so the tool can include
   `payment_tx_hash` in its tool result.
6. Does **not** break MCP clients by consuming the request body before
   FastMCP sees it — reading `await request.body()` inside middleware
   exhausts the ASGI receive stream and FastMCP will hang or 400.

Assume `async def _settle_payment(token) -> tuple[bool, str | None, str | None]`
exists and returns `(success, tx_hash, error_code)`. Recipient address,
network, facilitator name, price are read from env.

---

## ground_truth

```python
import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse

X402_PAYMENT_HEADER = "x402-payment"
X402_STANDARD_PAYMENT_HEADER = "x-payment"
MCP_PROTECTED_PREFIX = "/mcp"
JSONRPC_PAYMENT_REQUIRED_CODE = -32002
JSONRPC_PAYMENT_TIMEOUT_CODE = -32004


def _is_protected(path: str, method: str) -> bool:
    if path == "/validate" and method == "POST":
        return True
    # Gate ALL methods under /mcp — POST for tools/call, GET for SSE stream.
    return path == MCP_PROTECTED_PREFIX or path.startswith(MCP_PROTECTED_PREFIX + "/")


def _is_mcp(path: str) -> bool:
    return path == MCP_PROTECTED_PREFIX or path.startswith(MCP_PROTECTED_PREFIX + "/")


def _flat_402_body(detail: str, error: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "detail": detail,
        "amount": os.environ.get("X402_PRICE_USDC", "0.01"),
        "asset": "USDC",
        "facilitator": os.environ.get("X402_FACILITATOR_NAME", "x402"),
        "network": os.environ.get("X402_NETWORK", "base"),
        "scheme": "exact",
    }
    if recipient := os.environ.get("X402_RECIPIENT_ADDRESS", "").strip():
        body["recipient"] = recipient
    if error:
        body["error"] = error
    return body


async def _read_rpc_id(request: Request) -> Any:
    """Safely peek at the JSON-RPC `id` WITHOUT exhausting the ASGI stream.

    Only called on the error path, where we are about to short-circuit and
    NOT forward to downstream FastMCP — so consuming the body here is safe.
    On the success path the body is left untouched for FastMCP to read.
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
        if isinstance(rpc_id, (str, int)) or rpc_id is None:
            return rpc_id
    return None  # batched or malformed — null id is still valid JSON-RPC


async def _reject(
    request: Request,
    *,
    status_code: int,
    detail: str,
    error: str | None = None,
) -> JSONResponse:
    flat = _flat_402_body(detail, error)
    if not _is_mcp(request.url.path):
        # /validate keeps the legacy flat body for REST clients.
        return JSONResponse(status_code=status_code, content=flat)

    rpc_code = (
        JSONRPC_PAYMENT_TIMEOUT_CODE
        if error == "payment_settlement_timeout"
        else JSONRPC_PAYMENT_REQUIRED_CODE
    )
    envelope = {
        "jsonrpc": "2.0",
        "id": await _read_rpc_id(request),
        "error": {"code": rpc_code, "message": detail, "data": flat},
    }
    # HTTP status is preserved (402 / 504) so proxies and logs stay correct;
    # the JSON-RPC client reads error.data for the payment requirements.
    return JSONResponse(status_code=status_code, content=envelope)


async def x402_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    if not _is_protected(request.url.path, request.method):
        return await call_next(request)

    token = (
        request.headers.get(X402_PAYMENT_HEADER, "").strip()
        or request.headers.get(X402_STANDARD_PAYMENT_HEADER, "").strip()
    )
    if not token:
        return await _reject(request, status_code=402, detail="Payment required")

    timeout_s = float(os.environ.get("X402_SETTLEMENT_TIMEOUT_S", "10"))
    try:
        success, tx_hash, settle_error = await asyncio.wait_for(
            _settle_payment(token), timeout=timeout_s
        )
    except asyncio.TimeoutError:
        return await _reject(
            request,
            status_code=504,
            detail="Payment settlement timeout",
            error="payment_settlement_timeout",
        )

    if not success:
        return await _reject(
            request,
            status_code=402,
            detail="Settlement failed",
            error=settle_error or "settlement_failed",
        )

    # Stash settlement tx hash on request.state so the downstream MCP tool
    # can surface it as `payment_tx_hash` in its tool result via
    # fastmcp.server.dependencies.get_http_request().state.x402_payment_tx_hash.
    request.state.x402_payment_tx_hash = tx_hash
    return await call_next(request)
```

---

## model

Factory Droid mission ensemble — orchestrator: Droid Core (GLM-5.1); worker: Claude Opus 4.7; validator: GPT-5.5. All three roles, spanning three independent model families (Zhipu GLM, Anthropic, OpenAI), failed on this prompt. Circle skills (`use-developer-controlled-wallets`, x402) and the ARC coding context were loaded.

---

## explanation

This composition is the load-bearing piece of "sentinel-as-a-service" in our
build. Every layer of our Factory Droid mission ensemble — the GLM-5.1
orchestrator (Droid Core), the Claude Opus 4.7 worker, AND the GPT-5.5
validator — failed it in distinct ways even with Circle's x402 skill and the
ARC coding context enabled. Three model families (Zhipu GLM, Anthropic,
OpenAI) failing on the same prompt rules out single-model quirks and
suggests the gap is in the shared corpus across families. The reason: each
piece (x402, FastMCP, FastAPI middleware) is documented in isolation, but
their composition is not, and the failure modes are silent at runtime.

Specific knowledge gaps (note: an earlier version of this submission with a less precise model attribution was submitted to this CLI minutes earlier — this is the corrected canonical version. Please disregard the prior one):

1. **JSON-RPC error code selection for payment.** There is no official
   JSON-RPC code for "payment required." The spec reserves `-32000..-32099`
   for server errors and `-32600..-32603` for protocol errors. The agent
   typically picks `-32600` ("invalid request") or `-32000` (generic server
   error), both of which mislead MCP clients into thinking the request was
   malformed rather than unpaid. Correct answer: pick from the reserved
   server range and pin a code per payment failure mode (`-32002` for
   payment required, `-32004` for timeout) so clients can switch on it.
   Verified against early x402+MCP demos by Coinbase/Anthropic.

2. **ASGI body-stream exhaustion.** `await request.body()` reads the
   ASGI receive stream once. If middleware does this on the success path,
   downstream FastMCP gets an empty body and either hangs (SSE) or 400s
   (POST). Most agents reach for `request.body()` unconditionally to
   inspect the JSON-RPC `id`, which silently breaks the happy path. Correct
   answer: only read the body when issuing the error response (we are about
   to short-circuit and NOT forward), and leave it untouched on the
   success path. Alternative is caching the body via a custom ASGI receive
   wrapper, which is significantly more code.

3. **HTTP status code preservation under JSON-RPC envelope.** It is
   tempting to "wrap everything in 200 OK with JSON-RPC error" because
   that is what some pure JSON-RPC servers do. That breaks HTTP-aware
   x402 facilitators, proxies, and loggers that expect 402/504 to mean
   "payment required / settlement timeout." Correct answer: preserve the
   HTTP status (402 or 504) AND return the JSON-RPC envelope. MCP clients
   parse the body regardless of status; HTTP infra still sees the right
   code.

4. **GET-under-/mcp must also be gated.** FastMCP's streamable-HTTP
   transport uses `GET` with `Accept: text/event-stream` for the SSE
   listener channel and `POST` for `tools/call`. Agents that gate only
   `POST /mcp` create a paywall bypass: an attacker can open the SSE
   stream for free and observe server-initiated activity. Correct answer:
   gate every method under the `/mcp` prefix.

5. **Surfacing the settlement tx hash to the tool.** The MCP tool needs
   to return `payment_tx_hash` to the caller as part of the tool result,
   but the settlement happens in HTTP middleware, two abstraction layers
   above the tool function. Agents reach for ContextVars, global state,
   or threadlocals — all wrong under asyncio. Correct answer: stash on
   `request.state.x402_payment_tx_hash` (Starlette idiom, lifetime is
   the single request), then pull from the tool via
   `fastmcp.server.dependencies.get_http_request().state.x402_payment_tx_hash`.
   This is the only path that survives concurrent in-flight requests and
   in-process `fastmcp.Client` callers (which have no HTTP context and
   should get `None`).

6. **Dual-shape body (flat for REST, envelope for /mcp).** Agents
   collapse both routes to the JSON-RPC shape "for consistency," which
   breaks pre-existing REST clients that depend on top-level `amount` /
   `asset` keys. Correct answer: branch on path inside the rejection
   helper; REST keeps flat, `/mcp` gets the envelope wrapping the same
   flat body under `error.data`.

How I derived the ground truth: this code is from the Prism sentinel service
(commit `083eb62`, `fix(mcp): wrap unpaid /mcp 402s in JSON-RPC error and
surface payment_tx_hash`). Verified end-to-end against the real
`x402.org/facilitator` settling on Base testnet, against `fastmcp.Client`
in-process (no HTTP context — `payment_tx_hash=None`), and against an MCP
JSON-RPC client over the streamable-HTTP transport. Test coverage in
`apps/mcp/src/tests/test_mcp.py` (226 lines added in the same commit) pins
the envelope shape, the request-id echo, the differentiated error codes, the
tx-hash propagation, and the body-stream-not-exhausted invariant.
