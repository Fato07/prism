# Prism CLI

Command-line client for Prism trace inspection, public reporting, market resolution, and x402 validation orchestration.

This is the local product spine for builders who want to inspect agent traces and pull Prism metrics without opening the dashboard.

## Local usage

```bash
cd apps/cli
uv run prism --help
```

Inspect a local Trading-R1 trace without payment or LLM calls:

```bash
uv run prism inspect ./trace.json
uv run prism inspect ipfs://QmNzqnPEEQUMn3GMbiEZANpKXZRPmTHxVwt5nNevR8iXt8 --json
```

Read public activity from the dashboard API:

```bash
uv run prism doctor
uv run prism stats
uv run prism history --limit 5 --json
uv run prism report d6cdd60f-f5e0-43ab-ba2d-7dcab76a8e24
uv run prism markets --limit 5
uv run prism market resolve "<question from prism markets>" --json
uv run prism quote ipfs://QmNzqnPEEQUMn3GMbiEZANpKXZRPmTHxVwt5nNevR8iXt8 \
  --trace-hash 0x1a750011608a7480e9cb11f1d20587e32efb7a7dd433b85820f0dbfcdee19fdb
uv run prism validate ipfs://Qm... --trace-hash 0x... --x-payment-file ./x-payment.txt
uv run prism validate ipfs://Qm... --trace-hash 0x... \
  --circle-address 0xYourCircleWallet --circle-chain BASE-SEPOLIA --max-amount-usdc 0.01
```

Wallet helpers are read-only:

```bash
uv run prism wallet fund-link
uv run prism wallet status --address 0x...
```

## Scope

The CLI does not custody keys and never reads private keys. `prism quote` returns the exact payment requirements for the sentinel MCP endpoint. `prism validate` can either submit an externally signed `X-PAYMENT` header via `--x-payment-file`, `PRISM_X_PAYMENT`, or `--x-payment-header`, or ask Circle CLI to sign the EIP-712 authorization with `--circle-address`. The Circle signer path shells out to `circle wallet sign typed-data`; private keys remain inside the Circle wallet/CLI boundary.

Run `prism doctor` before paid demos. It checks dashboard/sentinel/gateway health, the MCP `/mcp/` handshake, Circle CLI availability, and the Base Sepolia testnet wallet session required for x402 payment.

Market commands read Prism's Polymarket gateway, which filters stale markets and returns explicit token-resolution metadata. Live trade execution still requires the caller to pass an explicit token ID.
