# Prism final demo pack — 2026-05-16

This is the judge-facing recording pack for Prism's final demo. It uses only receipt-backed claims.

## Primary links

| Surface | Link |
| --- | --- |
| Dashboard | <https://prism-dashboard-production-e6e3.up.railway.app> |
| Docs | <https://prism-docs-production.up.railway.app> |
| Quickstart | <https://prism-docs-production.up.railway.app/docs/quickstart> |
| Receipts guide | <https://prism-docs-production.up.railway.app/docs/receipts> |
| Calibration docs | <https://prism-docs-production.up.railway.app/docs/calibration> |
| Broad-evidence trace | <https://prism-dashboard-production-e6e3.up.railway.app/trace/f7b4f87c-568b-4bac-90ec-d4a3df1f7bd1> |
| Legacy canonical trace | <https://prism-dashboard-production-e6e3.up.railway.app/trace/d6cdd60f-f5e0-43ab-ba2d-7dcab76a8e24> |
| Stats | <https://prism-dashboard-production-e6e3.up.railway.app/stats> |
| Calibration | <https://prism-dashboard-production-e6e3.up.railway.app/calibration> |
| Self-serve submit | <https://prism-dashboard-production-e6e3.up.railway.app/submit> |
| Sentinel MCP | `https://prism-sentinel-production.up.railway.app/mcp/` |
| GitHub | <https://github.com/Fato07/prism> |

Keep the sentinel MCP trailing slash: `/mcp/`.

## Receipt links

| Proof | Link |
| --- | --- |
| First dashboard self-serve receipt | [`self-serve-submit-20260515T101946Z.md`](./self-serve-submit-20260515T101946Z.md) |
| Dashboard x402 payment tx | <https://sepolia.basescan.org/tx/0x63bf70941e8890b2b92459addfa18ecb57dd06bba7ea715391f00322faf58d68> |
| Canonical trace Arc validation request | <https://testnet.arcscan.app/tx/0x5adb156fa8de6c1cf7e0d50c2197d8315eb9a501da2c00ffbf52996d2407d786> |
| First CLI paid validation receipt | [`cli-paid-validation-20260516T214837Z.md`](./cli-paid-validation-20260516T214837Z.md) |
| CLI x402 payment tx | <https://sepolia.basescan.org/tx/0xd6ab0cbba99dfa1162ab24ccf35c9e9544c1bb64a550a0e349e8033ebd4f43e1> |
| CLI verdict IPFS | <https://gateway.pinata.cloud/ipfs/QmUQpQEaggjuZqGAJpxoDXg4ghJ3ReufWM546g856KqUnk> |
| CLI wallet deployment preflight tx | <https://sepolia.basescan.org/tx/0x3b68fc432bb7b052352851b962728905e01818d1c88940ab2e97da29bea21d89> |

## Current stats snapshot

Snapshot from `GET /api/public/stats` after the Exa hosted MCP evidence deploy:

| Metric | Value |
| --- | ---: |
| Verdicts issued | 772 |
| Traces validated | 962 |
| On-chain anchors | 744 |
| Builder-attributed trades | 368 |
| Builder fees | `0.002990` USDC |
| External x402 calls | 2 |
| Unique wallets | 2 |
| Live verdict score spread | 57 |

## Demo modes

### Broad evidence resolution — current default

Active connector: `Exa hosted MCP evidence` (`mcp_http`, tool `web_search_exa`, mapper `exa_mcp_text`).

Use this to show the mature path:

1. Trader submits a reasoning trace.
2. Sentinel raises temporal/calibration issues in the current public trace; source-quality coverage is tested separately.
3. Connector Passport routes targeted evidence requests to Exa hosted MCP.
4. Sentinel accepts only issue-matched, recent/source-adequate evidence.
5. The issue ledger records `resolved` tool outcomes and the capital gate reaches `ALLOW_PAPER`.

### Fail-closed guardrail — optional reset mode

If you need to demonstrate failure safety, re-arm the market-only connector (`Prism market evidence MCP`) or use a connector that returns malformed/non-matching output, then re-run validation. Unsupported stale/source/logic issues should remain unresolved, clean PASS should stay gated, and the public report should show `fail_closed`/`not_recorded` rather than `resolved`.

Do not claim connector output automatically resolves issues. Sentinel adjudicates every resolution through adequacy gates.

## 150-second demo script

### 0:00–0:15 — Hook

> I'm Fathin, building Prism solo from Tallinn. Trading agents can sound confident while reasoning badly. Prism is the second agent that checks the first one before capital moves.

Show dashboard home or `/stats`.

### 0:15–0:40 — What Prism is

> A Claude-family trader creates a structured Trading-R1 trace. A separate GPT-family sentinel attacks the evidence, thesis, and calibration. Connector Passport arms external evidence tools, but the sentinel does not trust tool output blindly: evidence must pass adequacy gates before issues resolve. The output is a Prism Report: verdict, reasoning metrics, an issue ledger, a capital gate, IPFS content, receipts, and execution attribution when a paper or live trade carries a builder code.

Show the broad-evidence trace page:

```txt
https://prism-dashboard-production-e6e3.up.railway.app/trace/f7b4f87c-568b-4bac-90ec-d4a3df1f7bd1
```

Narrative checkpoint: this trace now demonstrates the full MCP evidence loop. Sentinel raised issues, Exa hosted MCP returned source-linked evidence, adequacy gates accepted only issue-matched results, and the capital gate moved to paper-mode allowed.

### 0:40–1:00 — Capital gate

> Prism is not commentary. It is an execution gate: the trader proposes, the sentinel challenges, and Prism decides whether capital may continue. REJECT or unresolved blocking issues block capital; WARN, material issues, or legacy receipts without a structured issue ledger require review; clean PASS with a structured ledger can continue in paper mode; ENDORSE is the high-confidence path. If a connector fails, returns malformed data, or returns evidence that does not match the issue, Prism stays fail-closed.

Show the trace page `What happened here?` panel, capital-gate card, Sentinel issue-ledger summary, and execution-attribution page if time permits. The current broad-evidence trace should show `PASS`, `ALLOW_PAPER`, and per-issue `resolved` tool outcomes from `exa_mcp`.

### 1:00–1:20 — Human self-serve path

> The dashboard is self-serve: paste an IPFS CID, pay 0.01 USDC via x402 on Base Sepolia, and get a verdict permalink. This payment settled at 0x63bf7094… and produced a 65 PASS verdict.

Show `/submit`, then the BaseScan tx and self-serve receipt.

### 1:20–1:45 — Agent/developer path

> Prism is also callable by agents and developers. The sentinel is an x402-protected MCP trust service: agents can validate traces, inspect issue ledgers, verify receipts, explain verdict gates, and query public reports with per-issue tool outcomes: resolved, fail-closed, or not recorded. The CLI wraps the paid flow safely: quote first, then explicit capped payment.

Show docs quickstart / x402 MCP docs, then terminal command:

```bash
uvx --from "prism-cli @ git+https://github.com/Fato07/prism.git#subdirectory=apps/cli" prism demo
```

Then show paid receipt:

```txt
docs/demos/cli-paid-validation-20260516T214837Z.md
```

### 1:45–2:10 — Receipts

> This is the live CLI paid receipt: 0.01 USDC, Base Sepolia tx 0xd6ab0cbb…, verdict CID on IPFS, and `prism doctor` green. The receipt bundle also links the dashboard payment, canonical trace, Arc validation request where present, and verdict CID. Prism never reads private keys; Circle CLI signs typed data at the wallet boundary.

Show BaseScan tx, IPFS verdict, and docs `/docs/receipts`.

### 2:10–2:30 — Calibration / close

> The sentinel has to prove it discriminates. Prism's startup gate separates good, mediocre, and bad synthetic traces by 45 points, and the private calibration corpus now summarizes 60 rows: real harvested traces, synthetic seeds, mutations, and human-reviewed labels. The long-term point is agents validating agents before markets move. Today Prism has 772 verdicts, 962 traces, 744 on-chain anchors, 368 builder-attributed trades, Exa MCP evidence resolution, and two external x402 payments.

End on `/calibration`, docs, or dashboard stats.

## Screen recording checklist

Open these tabs before recording:

1. Dashboard stats: <https://prism-dashboard-production-e6e3.up.railway.app/stats>
2. Dashboard trust workspace: <https://prism-dashboard-production-e6e3.up.railway.app/dashboard>
3. Workspace Tools / Connector Passport: <https://prism-dashboard-production-e6e3.up.railway.app/connectors>
4. Execution attribution: <https://prism-dashboard-production-e6e3.up.railway.app/builder-fees>
5. Broad-evidence trace: <https://prism-dashboard-production-e6e3.up.railway.app/trace/f7b4f87c-568b-4bac-90ec-d4a3df1f7bd1>
6. Latest public report API example: <https://prism-dashboard-production-e6e3.up.railway.app/api/public/traces/f7b4f87c-568b-4bac-90ec-d4a3df1f7bd1/report>
7. Submit page: <https://prism-dashboard-production-e6e3.up.railway.app/submit>
8. Docs quickstart: <https://prism-docs-production.up.railway.app/docs/quickstart>
9. Docs receipts: <https://prism-docs-production.up.railway.app/docs/receipts>
10. Calibration: <https://prism-dashboard-production-e6e3.up.railway.app/calibration>
11. CLI payment tx: <https://sepolia.basescan.org/tx/0xd6ab0cbba99dfa1162ab24ccf35c9e9544c1bb64a550a0e349e8033ebd4f43e1>
12. CLI verdict IPFS: <https://gateway.pinata.cloud/ipfs/QmUQpQEaggjuZqGAJpxoDXg4ghJ3ReufWM546g856KqUnk>

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
- that connector output automatically resolves issues; Sentinel adjudicates and adequacy gates may keep issues fail-closed
- that the CLI paid validation produced an Arc tx; it produced x402 payment + IPFS verdict receipts, while other Prism validation flows anchor on Arc

Safe claims:

- dashboard self-serve x402 payment settled on Base Sepolia
- CLI x402 payment settled on Base Sepolia
- verdict content is pinned to IPFS
- Arc/ERC-8004 registries are used for identity/validation receipts where tx hashes are present
- Prism CLI never reads private keys
- paid flows are explicit and capped
- Connector Passport currently arms Exa hosted MCP as the active broad evidence connector and redacts connector URLs/secrets in public surfaces
- execution attribution links paper/live trades to builder codes; fee totals are shown only when fill-price data exists
- unresolved blockers gate clean PASS even when a connector is armed

## Submission one-liner

Prism is an adversarial validation layer for trading agents: a different-family sentinel challenges a trader's reasoning, then returns a receipt-backed verdict through dashboard, MCP, and CLI surfaces.

## Submission paragraph

Prism validates trading-agent reasoning before capital moves. A Claude-family trader generates a Trading-R1 trace; a separate GPT/DSPy sentinel adversarially challenges the evidence, thesis, risk factors, and calibration. Connector Passport arms MCP-first evidence tools, but Sentinel only resolves issues when normalized evidence passes adequacy gates; unresolved blockers still gate clean PASS. The output is a Prism Report with deterministic metrics, a verdict, structured issue ledger, capital gate, per-issue tool outcomes, IPFS content, x402 payment receipts, and Arc/ERC-8004 validation receipts where anchored. The product is live as a dashboard, x402-protected MCP trust endpoint, developer CLI, and documentation site. Two external x402 validations have settled on Base Sepolia, including a live CLI paid validation with a public payment transaction and verdict CID.
