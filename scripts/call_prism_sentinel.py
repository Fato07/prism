# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "httpx>=0.28",
#   "eth-account>=0.13",
#   "x402[evm]>=2.10",
# ]
# ///
"""
Call Prism's sentinel from an *external* agent — x402 + MCP demo client.

This script is the public integration example for Prism's sentinel-as-a-service.
Fork it, change the trace input, point it at your own wallet — and you have
agent-to-agent payments working in ~200 lines of Python.

What it does
============

1. Loads (or generates and persists) an ephemeral Ethereum keypair to
   `.local/prism-client.key`. This wallet is YOUR external agent's identity.
2. Checks the wallet's USDC balance on Base mainnet.
3. If empty → prints funding instructions and exits cleanly.
4. If funded → executes the full x402 + MCP dance:
     a. POST {SENTINEL_MCP_URL} with a tools/call request, no payment
     b. Sentinel returns HTTP 402 with payment requirements in a JSON-RPC
        error envelope (Prism's custom shape — see the parse helper below)
     c. Sign an EIP-3009 transferWithAuthorization via the x402 SDK
     d. Re-POST with the signed payment in the X-PAYMENT header
     e. Sentinel forwards the payment to the x402.org facilitator → 0.01
        USDC settles on Base mainnet → sentinel runs adversarial validation
        → returns the verdict as MCP structuredContent
5. Saves a Markdown receipt to `docs/demos/external-call-<timestamp>.md`
   containing every hash + a tweet-ready narrative at the bottom.

The wallet only ever needs USDC. EIP-3009 transfers are gasless for the
signer — the facilitator pays the Base gas. So one MetaMask transfer of
0.05 USDC gets you ~5 demo runs.

Usage
=====

    uv run scripts/call_prism_sentinel.py
    uv run scripts/call_prism_sentinel.py --trace-uri ipfs://... --trace-hash 0x...

Fork notes
==========

- The `.local/prism-client.key` is gitignored. Don't commit your private key.
- The `DEFAULT_TRACE_URI` / `DEFAULT_TRACE_HASH` constants below point at a
  real, on-chain anchored trace from Prism's production DB. Override on the
  CLI to validate your own reasoning trace (must be JSON pinned to IPFS).
- The sentinel currently returns a custom 402 body wrapped in a JSON-RPC
  error envelope. A future Prism release will emit the standard x402 v2
  `PaymentRequired` schema so any vanilla x402 client SDK works without
  the custom parse step in `parse_jsonrpc_402_body`.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from eth_account import Account

# x402 SDK imports — kept here so the failure message is friendly if missing
try:
    from x402 import x402Client
    from x402.mechanisms.evm.exact import register_exact_evm_client
    from x402.mechanisms.evm.signers import EthAccountSigner
    from x402.schemas import (
        Network,
        PaymentRequired,
        PaymentRequirements,
    )
except ImportError as exc:  # pragma: no cover
    sys.stderr.write(
        "FATAL: missing x402[evm]. Install with `uv run --with x402[evm]` "
        "or run this script via `uv run scripts/call_prism_sentinel.py` "
        f"(PEP 723 metadata handles deps).\n  Underlying: {exc}\n"
    )
    sys.exit(2)


# ───────────────────────── Configuration ─────────────────────────

# Note the trailing slash — the sentinel mounts FastMCP at `/mcp/` and a
# request to `/mcp` (no slash) receives a 307 redirect. httpx (and most HTTP
# clients) strip custom headers like X-PAYMENT across 3xx redirects for
# security, so hitting the canonical URL directly avoids losing the payment.
SENTINEL_MCP_URL = "https://prism-sentinel-production.up.railway.app/mcp/"

# Network config — the public x402.org facilitator currently supports Base
# Sepolia only. Base mainnet x402 requires the Coinbase CDP facilitator (auth).
# Override via the `PRISM_X402_NETWORK` env var if you wire up a mainnet
# facilitator on your sentinel.
NETWORK = os.environ.get("PRISM_X402_NETWORK", "base-sepolia").lower()

# Per-network USDC domain config. The EIP-712 domain `name` differs between
# Sepolia ("USDC") and mainnet ("USD Coin") — if we sign with the wrong
# domain name, the facilitator rejects with `invalid_exact_evm_signature`.
# Verified by calling name()/version() on each contract on 2026-05-13.
_NETWORK_CONFIG: dict[str, dict[str, Any]] = {
    "base-sepolia": {
        "chain_id": 84532,
        "caip2": "eip155:84532",
        "usdc_address": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        "usdc_domain_name": "USDC",
        "usdc_domain_version": "2",
        "rpc_url": "https://sepolia.base.org",
        "explorer": "https://sepolia.basescan.org",
    },
    "base": {
        "chain_id": 8453,
        "caip2": "eip155:8453",
        "usdc_address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bda02913",
        "usdc_domain_name": "USD Coin",
        "usdc_domain_version": "2",
        "rpc_url": "https://mainnet.base.org",
        "explorer": "https://basescan.org",
    },
}
if NETWORK not in _NETWORK_CONFIG:
    raise SystemExit(
        f"unknown PRISM_X402_NETWORK={NETWORK!r}; expected one of {list(_NETWORK_CONFIG)}"
    )
CFG = _NETWORK_CONFIG[NETWORK]

USDC_CONTRACT = CFG["usdc_address"]
BASE_RPC = CFG["rpc_url"]
BASE_CHAIN_ID = CFG["chain_id"]
CAIP2_BASE = CFG["caip2"]
EXPLORER = CFG["explorer"]

# Latest anchored validated trace from production DB (May 13, 2026).
# Override via --trace-uri / --trace-hash CLI args.
DEFAULT_TRACE_URI = (
    "ipfs://QmNzqnPEEQUMn3GMbiEZANpKXZRPmTHxVwt5nNevR8iXt8"
)
DEFAULT_TRACE_HASH = (
    "0x1a750011608a7480e9cb11f1d20587e32efb7a7dd433b85820f0dbfcdee19fdb"
)

REPO_ROOT = Path(__file__).resolve().parents[1]
KEY_PATH = REPO_ROOT / ".local" / "prism-client.key"
RECEIPTS_DIR = REPO_ROOT / "docs" / "demos"


# ───────────────────────── Wallet management ─────────────────────────


def load_or_create_wallet() -> Any:
    """Load the persisted client wallet or generate a new one."""
    if KEY_PATH.exists():
        pk = KEY_PATH.read_text().strip()
        return Account.from_key(pk), False
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    acct = Account.create()
    KEY_PATH.write_text(acct.key.hex())
    os.chmod(KEY_PATH, 0o600)
    return acct, True


def usdc_balance(address: str) -> float:
    """Query USDC balance on Base mainnet via JSON-RPC eth_call."""
    selector = "0x70a08231"  # keccak256("balanceOf(address)")[:4]
    padded = address.lower().replace("0x", "").zfill(64)
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_call",
        "params": [{"to": USDC_CONTRACT, "data": selector + padded}, "latest"],
    }
    with httpx.Client(timeout=10.0) as c:
        resp = c.post(BASE_RPC, json=body)
    hex_bal = resp.json().get("result", "0x0")
    return int(hex_bal, 16) / 1_000_000  # USDC has 6 decimals


# ───────────────────────── MCP/x402 dance ─────────────────────────


def make_mcp_initialize_body() -> dict[str, Any]:
    """Build the JSON-RPC body for the MCP initialize handshake.

    Required as the first call — the server returns a session ID in the
    ``mcp-session-id`` header that subsequent calls must echo back.
    """
    return {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {"experimental": {}, "sampling": {}},
            "clientInfo": {
                "name": "prism-external-x402-demo",
                "version": "0.1.0",
            },
        },
    }


def make_mcp_initialized_notification() -> dict[str, Any]:
    """The required notification after initialize completes."""
    return {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
    }


def make_mcp_body(trace_uri: str, trace_hash: str) -> dict[str, Any]:
    """Build the JSON-RPC body for the MCP tools/call request."""
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "validate",
            "arguments": {
                "trace_uri": trace_uri,
                "trace_hash": trace_hash,
            },
        },
    }


def base_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        # MCP streamable-HTTP transport accepts either content type.
        "Accept": "application/json, text/event-stream",
    }


async def call_unpaid(client: httpx.AsyncClient, body: dict[str, Any]) -> httpx.Response:
    return await client.post(SENTINEL_MCP_URL, json=body, headers=base_headers())


async def call_paid(
    client: httpx.AsyncClient,
    body: dict[str, Any],
    payment_b64: str,
    session_id: str | None,
) -> httpx.Response:
    headers = {**base_headers(), "X-PAYMENT": payment_b64}
    if session_id:
        headers["mcp-session-id"] = session_id
    return await client.post(SENTINEL_MCP_URL, json=body, headers=headers)


async def mcp_handshake(client: httpx.AsyncClient) -> str:
    """Complete the MCP initialize + notifications/initialized handshake.

    Returns the ``mcp-session-id`` issued by the server.
    Raises if the server doesn't issue one or returns non-200.
    """
    init_body = make_mcp_initialize_body()
    init_resp = await client.post(
        SENTINEL_MCP_URL, json=init_body, headers=base_headers()
    )
    if init_resp.status_code != 200:
        raise RuntimeError(
            f"MCP initialize failed: {init_resp.status_code} {init_resp.text[:200]}"
        )
    session_id = init_resp.headers.get("mcp-session-id")
    if not session_id:
        raise RuntimeError(
            "MCP server did not issue an mcp-session-id header on initialize"
        )
    # Required notifications/initialized so the server transitions from
    # handshake to operational state. Server replies 202 Accepted.
    notif_body = make_mcp_initialized_notification()
    notif_resp = await client.post(
        SENTINEL_MCP_URL,
        json=notif_body,
        headers={**base_headers(), "mcp-session-id": session_id},
    )
    if notif_resp.status_code not in (200, 202):
        raise RuntimeError(
            f"MCP notifications/initialized rejected: {notif_resp.status_code} "
            f"{notif_resp.text[:200]}"
        )
    return session_id


def parse_jsonrpc_402_body(parsed: dict[str, Any]) -> dict[str, Any]:
    """Extract Prism's custom payment requirements from the JSON-RPC error envelope.

    The sentinel currently emits this shape on 402::

        {"jsonrpc": "2.0", "id": <echoed>,
         "error": {"code": -32002, "message": "Payment required",
                   "data": {"detail": "...", "amount": "0.01", "asset": "USDC",
                            "scheme": "exact", "network": "base",
                            "facilitator": "x402", "recipient": "0x1453..."}}}

    We normalize that into a dict suitable for building a v2 PaymentRequirements.
    """
    err = parsed.get("error", {})
    data = err.get("data", {}) or {}
    return {
        "amount_usdc_decimal": str(data["amount"]),
        "asset": data["asset"],
        "scheme": data["scheme"],
        "network_raw": data["network"],  # "base" — needs CAIP-2 mapping
        "recipient": data["recipient"],
        "facilitator": data.get("facilitator"),
    }


def to_v2_payment_requirements(req: dict[str, Any]) -> PaymentRequirements:
    """Lift Prism's custom 402 dict into a standard x402 v2 PaymentRequirements."""
    expected_networks = {"base-sepolia", "base", CAIP2_BASE}
    if req["network_raw"].lower() not in expected_networks:
        raise ValueError(
            f"Sentinel announced network {req['network_raw']!r}, but this client is "
            f"configured for {NETWORK!r} ({CAIP2_BASE}). Set PRISM_X402_NETWORK to match."
        )
    amount_smallest = str(int(float(req["amount_usdc_decimal"]) * 1_000_000))
    return PaymentRequirements(
        scheme=req["scheme"],
        network=Network(CAIP2_BASE),
        asset=USDC_CONTRACT,
        amount=amount_smallest,
        pay_to=req["recipient"],
        max_timeout_seconds=120,
        extra={
            # Must match the on-chain USDC contract's EIP-712 domain name/
            # version. Sepolia: name="USDC". Mainnet: name="USD Coin".
            "name": CFG["usdc_domain_name"],
            "version": CFG["usdc_domain_version"],
        },
    )


async def build_x_payment_header(
    account: Any, requirements: PaymentRequirements
) -> str:
    """Sign EIP-3009 transferWithAuthorization and return the base64 X-PAYMENT value."""
    signer = EthAccountSigner(account)
    client = x402Client()
    register_exact_evm_client(client, signer)
    payment_required = PaymentRequired(accepts=[requirements])
    payload = await client.create_payment_payload(payment_required)
    payload_json = payload.model_dump_json(by_alias=True)
    return base64.b64encode(payload_json.encode("utf-8")).decode("ascii")


# ───────────────────────── Receipt rendering ─────────────────────────


def render_markdown_receipt(d: dict[str, Any]) -> str:
    score = d.get("verdict_score")
    label = d.get("verdict_label", "?")
    score_disp = f"**{score}** ({label})" if score is not None else "—"
    tx_arc = d.get("tx_hash_arc")
    tx_arc_link = (
        f"[`{tx_arc[:18]}…`](https://testnet.arcscan.app/tx/{tx_arc})"
        if tx_arc
        else "_(not anchored)_"
    )
    tx_base = d.get("payment_tx_hash")
    tx_base_link = (
        f"[`{tx_base[:18]}…`](https://basescan.org/tx/{tx_base})"
        if tx_base
        else "_(unknown)_"
    )

    cid = d.get("verdict_ipfs_cid") or "_(none)_"
    cid_link = (
        f"[`{cid[:18]}…`](https://ipfs.io/ipfs/{cid})"
        if cid and cid != "_(none)_"
        else "_(none)_"
    )

    return f"""# Prism sentinel — external x402 + MCP call receipt

**When:** {d['timestamp']}
**External client wallet:** [`{d['client_wallet']}`](https://basescan.org/address/{d['client_wallet']})
**Prism sentinel endpoint:** `{SENTINEL_MCP_URL}`

## Input

- **Trace URI:** [`{d['trace_uri']}`](https://ipfs.io/ipfs/{d['trace_uri'].replace('ipfs://','')})
- **Trace hash:** `{d['trace_hash']}`

## Payment

- **Amount:** {d['amount_paid']} USDC
- **Recipient:** [`{d['recipient']}`](https://basescan.org/address/{d['recipient']})
- **Network:** Base mainnet (chain {BASE_CHAIN_ID})
- **Settlement tx (Base):** {tx_base_link}

## Verdict

- **Score:** {score_disp} / 100
- **Verdict IPFS:** {cid_link}
- **Anchor on Arc (ValidationRegistry.validationResponse):** {tx_arc_link}

## Narrative

At **{d['timestamp']}**, a previously-unknown external wallet
([`{d['client_wallet'][:18]}…`](https://basescan.org/address/{d['client_wallet']}))
paid {d['amount_paid']} USDC over x402 to Prism's sentinel-as-a-service. The
sentinel pulled the trader's reasoning trace from IPFS, ran an adversarial
verdict in a different model family from the original trader, and returned a
score of **{score} ({label})** along with the structured critique. The whole
exchange is verifiable on-chain: the USDC settlement on Base
({tx_base_link}) and the verdict anchor on Arc ({tx_arc_link}).

This is what _sentinel-as-a-service_ on ERC-8004 looks like in practice — one
agent paying another agent for an adversarial check, settled in stablecoins,
anchored on a public ledger. No API keys exchanged, no off-chain trust
required.

---

<details>
<summary>Full MCP <code>tools/call validate</code> response</summary>

```json
{json.dumps(d['structured_content'], indent=2)}
```

</details>
"""


def save_receipt(data: dict[str, Any]) -> Path:
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = data["timestamp"].replace(":", "").replace("-", "")
    path = RECEIPTS_DIR / f"external-call-{ts}.md"
    path.write_text(render_markdown_receipt(data))
    return path


# ───────────────────────── Main flow ─────────────────────────


def banner(s: str, *, status: str = "•") -> None:
    print(f"  {status} {s}")


async def amain(trace_uri: str, trace_hash: str) -> int:
    print()
    print("Prism — external x402 + MCP demo client")
    print("=" * 56)
    print()

    # Step 0: wallet
    account, freshly_minted = load_or_create_wallet()
    addr = account.address
    if freshly_minted:
        banner(f"Generated fresh client wallet at {KEY_PATH.relative_to(REPO_ROOT)}", status="+")
    else:
        banner(f"Loaded client wallet from {KEY_PATH.relative_to(REPO_ROOT)}")
    banner(f"Client address: {addr}")

    balance = usdc_balance(addr)
    banner(f"USDC balance on {NETWORK}: {balance:.4f} USDC")

    if balance < 0.011:
        print()
        print("─" * 56)
        print("  Insufficient balance for one demo call (need ≥ 0.011 USDC).")
        print()
        print(f"  Send 0.05 USDC on {NETWORK} to:")
        print()
        print(f"      {addr}")
        print()
        print("  Then re-run this script.")
        print("─" * 56)
        return 1

    body = make_mcp_body(trace_uri, trace_hash)

    async with httpx.AsyncClient(
        follow_redirects=True, timeout=httpx.Timeout(180.0)
    ) as client:
        # Step 0: MCP handshake — initialize + notifications/initialized.
        # Free per the sentinel's middleware (paid actions are only tools/call).
        print()
        banner("[0/4] MCP handshake — initialize …", status=">")
        try:
            session_id = await mcp_handshake(client)
        except RuntimeError as exc:
            banner(str(exc), status="!")
            return 1
        banner(f"Session: {session_id[:24]}…", status="✓")

        # Step 1: unpaid call → expect 402
        banner("[1/4] Calling sentinel /mcp with session but no payment …", status=">")
        r1 = await client.post(
            SENTINEL_MCP_URL,
            json=body,
            headers={**base_headers(), "mcp-session-id": session_id},
        )
        if r1.status_code != 402:
            banner(f"Unexpected status {r1.status_code}: {r1.text[:200]}", status="!")
            return 1
        req = parse_jsonrpc_402_body(r1.json())
        banner(
            f"402 received · {req['amount_usdc_decimal']} {req['asset']} "
            f"to {req['recipient'][:10]}… on {req['network_raw']}",
            status="✓",
        )

        # Step 2: sign payment
        banner("[2/4] Signing EIP-3009 transferWithAuthorization …", status=">")
        requirements = to_v2_payment_requirements(req)
        payment_b64 = await build_x_payment_header(account, requirements)
        banner(f"Payment payload ready ({len(payment_b64)} char base64)", status="✓")

        # Step 3: paid call
        banner("[3/4] Re-calling /mcp with X-PAYMENT header …", status=">")
        r2 = await call_paid(client, body, payment_b64, session_id)
        if r2.status_code != 200:
            banner(f"Paid call returned {r2.status_code}: {r2.text[:300]}", status="!")
            return 1
        banner(f"200 OK · response {len(r2.content)} bytes", status="✓")

        # Step 4: parse + save receipt
        banner("[4/4] Parsing verdict + saving receipt …", status=">")
        # MCP streamable-HTTP may respond as either application/json or
        # text/event-stream. SSE responses look like ``event: message\ndata:
        # {...}\n\n`` — we extract the first ``data:`` line as JSON.
        ctype = r2.headers.get("content-type", "")
        raw_text = r2.text
        if "text/event-stream" in ctype.lower():
            data_line = next(
                (
                    line[len("data:") :].strip()
                    for line in raw_text.splitlines()
                    if line.startswith("data:")
                ),
                None,
            )
            if not data_line:
                banner(
                    f"SSE response had no data: line. First 200 chars: {raw_text[:200]!r}",
                    status="!",
                )
                return 1
            parsed = json.loads(data_line)
        else:
            parsed = r2.json()
        result = parsed.get("result", {})
        structured = result.get("structuredContent", {}) or {}
        verdict_score = structured.get("verdict_score")
        verdict_label = structured.get("verdict_label")
        tx_hash_arc = structured.get("tx_hash")
        payment_tx_hash = structured.get("payment_tx_hash")
        verdict_ipfs_cid = structured.get("ipfs_cid")

        receipt_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "client_wallet": addr,
            "trace_uri": trace_uri,
            "trace_hash": trace_hash,
            "amount_paid": req["amount_usdc_decimal"],
            "recipient": req["recipient"],
            "verdict_score": verdict_score,
            "verdict_label": verdict_label,
            "verdict_ipfs_cid": verdict_ipfs_cid,
            "tx_hash_arc": tx_hash_arc,
            "payment_tx_hash": payment_tx_hash,
            "structured_content": structured,
        }
        receipt_path = save_receipt(receipt_data)
        banner(f"Receipt: {receipt_path.relative_to(REPO_ROOT)}", status="✓")

        print()
        print("─" * 56)
        print(f"  Verdict: {verdict_label} (score {verdict_score}/100)")
        if payment_tx_hash:
            print(f"  Settlement: https://basescan.org/tx/{payment_tx_hash}")
        if tx_hash_arc:
            print(f"  Anchor on Arc: https://testnet.arcscan.app/tx/{tx_hash_arc}")
        print()
        new_balance = usdc_balance(addr)
        print(f"  Wallet balance now: {new_balance:.4f} USDC "
              f"(spent {balance - new_balance:.4f} USDC on this call)")
        print("─" * 56)
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Call Prism's sentinel from an external agent via x402 + MCP."
    )
    p.add_argument(
        "--trace-uri",
        default=DEFAULT_TRACE_URI,
        help="IPFS URI of the reasoning trace to validate (default: a real "
        "on-chain anchored trace from Prism's production DB).",
    )
    p.add_argument(
        "--trace-hash",
        default=DEFAULT_TRACE_HASH,
        help="bytes32 hex content hash of the trace (default: matches the "
        "default --trace-uri).",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    return asyncio.run(amain(args.trace_uri, args.trace_hash))


if __name__ == "__main__":
    sys.exit(main())
