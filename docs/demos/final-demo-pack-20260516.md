# Prism final demo pack — 2026-05-16

This is the judge-facing recording pack for Prism's final demo. It uses only receipt-backed claims.

## Primary links

| Surface | Link |
| --- | --- |
| Dashboard | <https://prism-dashboard-production-e6e3.up.railway.app> |
| Docs | <https://prism-docs-production.up.railway.app> |
| Quickstart | <https://prism-docs-production.up.railway.app/docs/quickstart> |
| Receipts guide | <https://prism-docs-production.up.railway.app/docs/receipts> |
| Canonical trace | <https://prism-dashboard-production-e6e3.up.railway.app/trace/d6cdd60f-f5e0-43ab-ba2d-7dcab76a8e24> |
| Stats | <https://prism-dashboard-production-e6e3.up.railway.app/stats> |
| Self-serve submit | <https://prism-dashboard-production-e6e3.up.railway.app/submit> |
| Sentinel MCP | `https://prism-sentinel-production.up.railway.app/mcp/` |
| GitHub | <https://github.com/Fato07/prism> |

Keep the sentinel MCP trailing slash: `/mcp/`.

## Receipt links

| Proof | Link |
| --- | --- |
| First dashboard self-serve receipt | [`self-serve-submit-20260515T101946Z.md`](./self-serve-submit-20260515T101946Z.md) |
| Dashboard x402 payment tx | <https://sepolia.basescan.org/tx/0x63bf70941e8890b2b92459addfa18ecb57dd06bba7ea715391f00322faf58d68> |
| First CLI paid validation receipt | [`cli-paid-validation-20260516T214837Z.md`](./cli-paid-validation-20260516T214837Z.md) |
| CLI x402 payment tx | <https://sepolia.basescan.org/tx/0xd6ab0cbba99dfa1162ab24ccf35c9e9544c1bb64a550a0e349e8033ebd4f43e1> |
| CLI verdict IPFS | <https://gateway.pinata.cloud/ipfs/QmUQpQEaggjuZqGAJpxoDXg4ghJ3ReufWM546g856KqUnk> |
| CLI wallet deployment preflight tx | <https://sepolia.basescan.org/tx/0x3b68fc432bb7b052352851b962728905e01818d1c88940ab2e97da29bea21d89> |

## Current stats snapshot

Snapshot from `GET /api/public/stats` at `2026-05-16T21:58:15.969Z`:

| Metric | Value |
| --- | ---: |
| Verdicts issued | 598 |
| Traces validated | 787 |
| On-chain anchors | 571 |
| External x402 calls | 2 |
| Unique wallets | 2 |
| Average verdict score | 62.87 |
| P50 latency | 20.7s |
| P95 latency | 26.1s |
| Calibration gap | 57 |

## 120-second demo script

### 0:00–0:15 — Hook

> I'm Fathin, building Prism solo from Tallinn. Trading agents can sound confident while reasoning badly. Prism is the second agent that checks the first one before capital moves.

Show dashboard home or `/stats`.

### 0:15–0:35 — What Prism is

> A Claude-family trader creates a structured Trading-R1 trace. A separate GPT-family sentinel attacks the evidence, thesis, and calibration. The output is a Prism Report: verdict, reasoning metrics, IPFS content, and receipts.

Show canonical trace page:

```txt
https://prism-dashboard-production-e6e3.up.railway.app/trace/d6cdd60f-f5e0-43ab-ba2d-7dcab76a8e24
```

### 0:35–0:55 — Human self-serve path

> The dashboard is self-serve: paste an IPFS CID, pay 0.01 USDC via x402 on Base Sepolia, and get a verdict permalink. This payment settled at 0x63bf7094… and produced a 65 PASS verdict.

Show `/submit`, then the BaseScan tx and self-serve receipt.

### 0:55–1:20 — Agent/developer path

> Prism is also callable by agents and developers. The sentinel is an x402-protected MCP service, and the CLI wraps the flow safely: quote first, then explicit capped payment.

Show docs quickstart, then terminal command:

```bash
uvx --from "prism-cli @ git+https://github.com/Fato07/prism.git#subdirectory=apps/cli" prism demo
```

Then show paid receipt:

```txt
docs/demos/cli-paid-validation-20260516T214837Z.md
```

### 1:20–1:40 — Receipts

> This is the live CLI paid receipt: 0.01 USDC, Base Sepolia tx 0xd6ab0cbb…, verdict CID on IPFS, and `prism doctor` green. Prism never reads private keys; Circle CLI signs typed data at the wallet boundary.

Show BaseScan tx, IPFS verdict, and docs `/docs/receipts`.

### 1:40–2:00 — Why Arc / close

> The long-term point is agents validating agents before markets move. Arc gives the identity and validation registry layer; x402 gives paid access; Prism turns reasoning into a receipt-backed object. Today it has 598 verdicts, 787 traces, 571 on-chain anchors, and two external x402 payments. If you build a trading agent, Prism is the adversarial validator you call before you trade.

End on docs or dashboard stats.

## Screen recording checklist

Open these tabs before recording:

1. Dashboard stats: <https://prism-dashboard-production-e6e3.up.railway.app/stats>
2. Canonical trace: <https://prism-dashboard-production-e6e3.up.railway.app/trace/d6cdd60f-f5e0-43ab-ba2d-7dcab76a8e24>
3. Submit page: <https://prism-dashboard-production-e6e3.up.railway.app/submit>
4. Docs quickstart: <https://prism-docs-production.up.railway.app/docs/quickstart>
5. Docs receipts: <https://prism-docs-production.up.railway.app/docs/receipts>
6. CLI payment tx: <https://sepolia.basescan.org/tx/0xd6ab0cbba99dfa1162ab24ccf35c9e9544c1bb64a550a0e349e8033ebd4f43e1>
7. CLI verdict IPFS: <https://gateway.pinata.cloud/ipfs/QmUQpQEaggjuZqGAJpxoDXg4ghJ3ReufWM546g856KqUnk>

Terminal prep:

```bash
cd apps/cli
uv run prism doctor
uv run prism demo
```

Only run paid commands live if you intentionally want another 0.01 USDC payment:

```bash
uv run prism demo --pay \
  --circle-address 0x229d65c16eb0386ac9a759625836e7d2b9831c3e \
  --max-amount-usdc 0.01
```

## Hard claim guardrails

Do not claim:

- gasless payments
- SCA/Gas Station sponsorship
- CCTP or Unified Balance production usage
- custom Solidity contracts
- live Polymarket orders unless showing an actual live-fill receipt
- that the CLI paid validation produced an Arc tx; it produced x402 payment + IPFS verdict receipts, while other Prism validation flows anchor on Arc

Safe claims:

- dashboard self-serve x402 payment settled on Base Sepolia
- CLI x402 payment settled on Base Sepolia
- verdict content is pinned to IPFS
- Arc/ERC-8004 registries are used for identity/validation receipts where tx hashes are present
- Prism CLI never reads private keys
- paid flows are explicit and capped

## Submission one-liner

Prism is an adversarial validation layer for trading agents: a different-family sentinel challenges a trader's reasoning, then returns a receipt-backed verdict through dashboard, MCP, and CLI surfaces.

## Submission paragraph

Prism validates trading-agent reasoning before capital moves. A Claude-family trader generates a Trading-R1 trace; a separate GPT/DSPy sentinel adversarially challenges the evidence, thesis, risk factors, and calibration. The output is a Prism Report with deterministic metrics, verdict, IPFS content, x402 payment receipts, and Arc/ERC-8004 validation receipts where anchored. The product is live as a dashboard, x402-protected MCP endpoint, developer CLI, and documentation site. Two external x402 validations have settled on Base Sepolia, including a live CLI paid validation with a public payment transaction and verdict CID.
