# Prism Protocol — v0

Protocol artifacts for `prism.report.v0` — the portable, receipt-backed adversarial validation report format.

## Artifacts

| File | Description |
|------|-------------|
| [`prism-protocol-v0.md`](./prism-protocol-v0.md) | Human-readable protocol specification |
| [`prism-report-v0.schema.json`](./prism-report-v0.schema.json) | JSON Schema Draft 2020-12 definition |
| [`receipt-verification-v0.md`](./receipt-verification-v0.md) | Step-by-step receipt verification walkthrough |
| [`fixtures/`](./fixtures/) | PASS and fail-closed conformance test fixtures |
| [`oracle-review.md`](./oracle-review.md) | Mission-oracle review findings and resolutions |

## Quick smoke checks

These Python one-liners check that schema and fixture files are well-formed JSON. They are **smoke / convenience checks** — not the canonical test gate.

```bash
# Smoke: schema parses as valid JSON
python -m json.tool docs/protocol/prism-report-v0.schema.json > /dev/null

# Smoke: PASS fixture parses as valid JSON
python -m json.tool docs/protocol/fixtures/pass-report.json > /dev/null

# Smoke: fail-closed fixture parses as valid JSON
python -m json.tool docs/protocol/fixtures/fail-closed-report.json > /dev/null
```

## Canonical test gate

The **canonical, authoritative test gate** is:

```bash
pnpm --dir apps/docs test
```

This runs the full vitest suite — schema compilation with ajv 2020-12 + ajv-formats, fixture validation, tampered-fixture rejection, cross-receipt consistency, banned-phrase enforcement, and all structural assertions on every protocol artifact. The Python smoke commands above are convenience checks only; they do not replace the vitest gate.

## Live-vs-v0 drift canary (operator smoke, not CI)

The live dashboard API may drift from the v0 protocol envelope over time. Run this canary to compare core identifiers between the live public PASS report and the canonical fixture:

```bash
curl -sS https://prism-dashboard-production-e6e3.up.railway.app/api/public/traces/d6cdd60f-f5e0-43ab-ba2d-7dcab76a8e24/report \
  | jq '{trace_id: .trace.trace_id, ipfs_cid: .trace.ipfs_cid, verdict_score: .validation.verdict_score, capital_gate_status: .capital_gate.status}'
```

Compare the `trace_id`, `ipfs_cid`, `verdict_score`, and `capital_gate_status` against the corresponding fields in `fixtures/pass-report.json`. Mismatches indicate live-envelope drift that requires attention.

**This is an operator smoke check, not a CI gate.** It depends on a live HTTP endpoint and should be run manually when protocol changes are proposed.

## Reserved action_intent literals

The `action_intent` envelope is a discriminated union on `type`. Three literals are reserved for future versions:

| Literal | Status | Description |
|---------|--------|-------------|
| `prediction_market` | **Implemented** | Polymarket trade intent (strict branch) |
| `payment_batch` | **Reserved — future** | Batch payment processing |
| `defi_rebalance` | **Reserved — future** | DeFi portfolio rebalancing |
| `treasury_move` | **Reserved — future** | Treasury / DAO fund movement |

The reserved types (`payment_batch`, `defi_rebalance`, `treasury_move`) require only `type` and are defined under `$defs` in the schema. Richer reserved-branch semantics require a new `schema_version` (e.g., `prism.report.v1`).

## Payment receipt protocols

The `payment_receipts` array is a discriminated union on `protocol`. Three protocol identifiers are defined:

| Protocol | Status | Description |
|----------|--------|-------------|
| `x402` | **Implemented** | x402 micropayment on Base Sepolia (strict branch) |
| `mpp` | **Reserved — future** | Multiparty Payment Protocol |
| `ap2` | **Reserved — future** | Agent Payment Protocol v2 |

`x402` requires `protocol`, `tx_hash`, `amount_usdc`, and `network` with full receipt shape. `mpp` and `ap2` are reserved adapter-only slots — they require only `protocol` and provide a `receipt_header_hash` placeholder. Full MPP and AP2 receipt shapes require a new `schema_version`.

## See also

- [Prism verification guarantees](/docs/verification-guarantees) — public-facing summary
- [Receipts](/docs/receipts) — how to verify every receipt type Prism produces
