# Prism CLI

Read-only command-line client for Prism trace inspection and public reporting.

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
uv run prism stats
uv run prism history --limit 5 --json
uv run prism report d6cdd60f-f5e0-43ab-ba2d-7dcab76a8e24
```

Wallet helpers are read-only:

```bash
uv run prism wallet fund-link
uv run prism wallet status --address 0x...
```

## Scope

Current v0 commands are read-only. They do not custody keys and do not sign x402 payments.
Paid validation (`prism validate`) will reuse the proven `scripts/call_prism_sentinel.py` flow in a later slice.
