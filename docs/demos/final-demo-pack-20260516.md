# Prism final demo pack — 2026-05-17 update

This is the judge-facing recording pack for Prism's final demo. It uses only receipt-backed claims.

## Primary links

| Surface | Link |
| --- | --- |
| Dashboard | <https://prism-dashboard-production-e6e3.up.railway.app> |
| Docs | <https://prism-docs-production.up.railway.app> |
| Quickstart | <https://prism-docs-production.up.railway.app/docs/quickstart> |
| Receipts guide | <https://prism-docs-production.up.railway.app/docs/receipts> |
| Public APIs | <https://prism-docs-production.up.railway.app/docs/public-apis> |
| Calibration docs | <https://prism-docs-production.up.railway.app/docs/calibration> |
| URL-verified Exa evidence trace | <https://prism-dashboard-production-e6e3.up.railway.app/trace/85d58b9c-f45f-4aa1-8b8a-7a4b1c1c8fea> |
| URL-verified Exa public report | <https://prism-dashboard-production-e6e3.up.railway.app/api/public/traces/85d58b9c-f45f-4aa1-8b8a-7a4b1c1c8fea/report> |
| Fail-closed guardrail trace | <https://prism-dashboard-production-e6e3.up.railway.app/trace/74cead4a-5def-4cec-8cb2-b5294d739acb> |
| Legacy self-serve canonical trace | <https://prism-dashboard-production-e6e3.up.railway.app/trace/d6cdd60f-f5e0-43ab-ba2d-7dcab76a8e24> |
| Stats | <https://prism-dashboard-production-e6e3.up.railway.app/stats> |
| Connector Passport | <https://prism-dashboard-production-e6e3.up.railway.app/connectors> |
| Calibration | <https://prism-dashboard-production-e6e3.up.railway.app/calibration> |
| Self-serve submit | <https://prism-dashboard-production-e6e3.up.railway.app/submit> |
| Sentinel MCP | `https://prism-sentinel-production.up.railway.app/mcp/` |
| GitHub | <https://github.com/Fato07/prism> |

Keep the sentinel MCP trailing slash: `/mcp/`.

## Receipt links

| Proof | Link |
| --- | --- |
| URL-verified Exa paid validation receipt | [`external-call-20260517T203104+0000.md`](./external-call-20260517T203104+0000.md) |
| URL-verified Exa x402 payment tx | <https://sepolia.basescan.org/tx/0x8d5d7a46bd88b2ffba5b6e6c6d70221598ee041d4206377ca5991e90f5c12421> |
| URL-verified Exa verdict IPFS | <https://gateway.pinata.cloud/ipfs/QmYmfMRuHxRWJXHswWhRjbQkbqvKmpDaHxuwyR63bFk7AR> |
| Canonical demo trace list | [`canonical-traces-20260517.md`](./canonical-traces-20260517.md) |
| First dashboard self-serve receipt | [`self-serve-submit-20260515T101946Z.md`](./self-serve-submit-20260515T101946Z.md) |
| Dashboard x402 payment tx | <https://sepolia.basescan.org/tx/0x63bf70941e8890b2b92459addfa18ecb57dd06bba7ea715391f00322faf58d68> |
| Canonical trace Arc validation request | <https://testnet.arcscan.app/tx/0x5adb156fa8de6c1cf7e0d50c2197d8315eb9a501da2c00ffbf52996d2407d786> |
| First CLI paid validation receipt | [`cli-paid-validation-20260516T214837Z.md`](./cli-paid-validation-20260516T214837Z.md) |
| CLI x402 payment tx | <https://sepolia.basescan.org/tx/0xd6ab0cbba99dfa1162ab24ccf35c9e9544c1bb64a550a0e349e8033ebd4f43e1> |
| CLI verdict IPFS | <https://gateway.pinata.cloud/ipfs/QmUQpQEaggjuZqGAJpxoDXg4ghJ3ReufWM546g856KqUnk> |
| CLI wallet deployment preflight tx | <https://sepolia.basescan.org/tx/0x3b68fc432bb7b052352851b962728905e01818d1c88940ab2e97da29bea21d89> |

## Current stats snapshot

Snapshot from `GET /api/public/stats` after the Exa URL-verification paid validation:

| Metric | Value |
| --- | ---: |
| Verdicts issued | 815 |
| Traces validated | 1,005 |
| On-chain anchors | 786 |
| Builder-attributed trades | 404 |
| Builder fees with fill-price receipts | `0.013186` USDC |
| External x402 calls | 3 |
| Unique wallets | 3 |
| Live verdict score spread | 57 |

## Demo modes

### URL-verified Exa evidence resolution — current default

Active connector: `Exa hosted MCP evidence` (`mcp_http`, search tool `web_search_exa`, mapper `exa_mcp_text`). Production Sentinel also requires extraction through Exa `web_fetch_exa` (`PRISM_EVIDENCE_EXTRACTION_REQUIRED=1`).

Use this to show the mature path:

1. Trader submits a reasoning trace.
2. Sentinel raises source-quality, temporal, market-structure, logic, or calibration issues.
3. Connector Passport routes targeted evidence requests to Exa hosted MCP.
4. Sentinel accepts only issue-matched, readable, recent/source-adequate search results.
5. Sentinel fetches the selected source URL through Exa `web_fetch_exa`.
6. The public issue ledger records `resolved`, `fail_closed`, or `not_recorded` tool outcomes plus structured `tool_receipt` fields: provider, tool, extractor provider/tool, source URL, source content hash, and excerpt.
7. Clean PASS / ENDORSE still depends on unresolved issue gates; a PASS score can remain non-endorseable if material issues are still open.

Canonical URL-verified trace:

```txt
https://prism-dashboard-production-e6e3.up.railway.app/trace/85d58b9c-f45f-4aa1-8b8a-7a4b1c1c8fea
```

Public report API:

```txt
https://prism-dashboard-production-e6e3.up.railway.app/api/public/traces/85d58b9c-f45f-4aa1-8b8a-7a4b1c1c8fea/report
```

### Fail-closed guardrail — current demo trace

Use this trace to demonstrate failure safety without reconfiguring production connectors:

```txt
https://prism-dashboard-production-e6e3.up.railway.app/trace/74cead4a-5def-4cec-8cb2-b5294d739acb
```

The report shows material source-quality issues that stayed `open` with `tool_status=fail_closed`. Do not claim connector output automatically resolves issues. Sentinel adjudicates every resolution through adequacy and extraction gates.

## 150-second demo script

### 0:00–0:15 — Hook

> I'm Fathin, building Prism solo from Tallinn. Trading agents can sound confident while reasoning badly. Prism is the second agent that checks the first one before capital moves.

Show dashboard home or `/stats`.

### 0:15–0:40 — What Prism is

> A Claude-family trader creates a structured Trading-R1 trace. A separate GPT-family sentinel attacks the evidence, thesis, and calibration. Connector Passport arms external evidence tools, but the sentinel does not trust tool output blindly: evidence must pass adequacy gates and URL extraction checks before issues resolve. The output is a Prism Report: verdict, reasoning metrics, an issue ledger, a capital gate, IPFS content, evidence provenance receipts, and execution attribution when a paper or live trade carries a builder code.

Show the URL-verified Exa evidence trace page:

```txt
https://prism-dashboard-production-e6e3.up.railway.app/trace/85d58b9c-f45f-4aa1-8b8a-7a4b1c1c8fea
```

Narrative checkpoint: this trace demonstrates the full MCP evidence loop. Sentinel raised issues, Exa hosted MCP returned source-linked evidence, Sentinel fetched selected source URLs with `web_fetch_exa`, and adequacy gates accepted only issue-matched results. The public report exposes provider/tool/extractor identity, source URLs, source excerpts, and SHA-256 source content hashes.

### 0:40–1:00 — Capital gate

> Prism is not commentary. It is an execution gate: the trader proposes, the sentinel challenges, and Prism decides whether capital may continue. REJECT or unresolved blocking issues block capital; WARN, material issues, or legacy receipts without a structured issue ledger require review; clean PASS with a structured ledger can continue in paper mode; ENDORSE is the high-confidence path. If a connector fails, returns malformed data, or returns evidence that does not match the issue, Prism stays fail-closed.

Show the trace page `What happened here?` panel, capital-gate card, Sentinel issue-ledger summary, and execution-attribution page if time permits. The URL-verified trace should show per-issue `resolved` tool outcomes from `exa_mcp` with extractor fields; the fail-closed guardrail trace should show material issues left open when adequate evidence was not found.

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

> This is the newest paid MCP receipt: 0.01 USDC, Base Sepolia tx `0x8d5d7a46bd88b2ffba5b6e6c6d70221598ee041d4206377ca5991e90f5c12421`, a verdict CID on IPFS, and a public report with URL-verified evidence receipts. The receipt bundle also links the dashboard payment, CLI payment, canonical traces, Arc validation request where present, and verdict CIDs. Prism never reads private keys; paid flows are explicit and capped.

Show the full BaseScan tx URL, public report API, IPFS verdict, and docs `/docs/receipts`.

### 2:10–2:30 — Calibration / close

> The sentinel has to prove it discriminates. Prism's startup gate separates good, mediocre, and bad synthetic traces by 45 points, and the private calibration corpus now summarizes 60 rows: real harvested traces, synthetic seeds, mutations, and human-reviewed labels. The long-term point is agents validating agents before markets move. Today Prism has 815 verdicts, 1,005 traces, 786 on-chain anchors, 404 builder-attributed trade receipts, URL-verified Exa MCP evidence receipts, and three external x402 payments.

End on `/calibration`, docs, or dashboard stats.

## Screen recording checklist

Open these tabs before recording:

1. Dashboard stats: <https://prism-dashboard-production-e6e3.up.railway.app/stats>
2. Dashboard trust workspace: <https://prism-dashboard-production-e6e3.up.railway.app/dashboard>
3. Workspace Tools / Connector Passport: <https://prism-dashboard-production-e6e3.up.railway.app/connectors>
4. Execution attribution: <https://prism-dashboard-production-e6e3.up.railway.app/builder-fees>
5. URL-verified Exa evidence trace: <https://prism-dashboard-production-e6e3.up.railway.app/trace/85d58b9c-f45f-4aa1-8b8a-7a4b1c1c8fea>
6. URL-verified public report API example: <https://prism-dashboard-production-e6e3.up.railway.app/api/public/traces/85d58b9c-f45f-4aa1-8b8a-7a4b1c1c8fea/report>
7. Fail-closed guardrail trace: <https://prism-dashboard-production-e6e3.up.railway.app/trace/74cead4a-5def-4cec-8cb2-b5294d739acb>
8. Submit page: <https://prism-dashboard-production-e6e3.up.railway.app/submit>
9. Docs quickstart: <https://prism-docs-production.up.railway.app/docs/quickstart>
10. Docs receipts: <https://prism-docs-production.up.railway.app/docs/receipts>
11. Calibration: <https://prism-dashboard-production-e6e3.up.railway.app/calibration>
12. CLI payment tx: <https://sepolia.basescan.org/tx/0xd6ab0cbba99dfa1162ab24ccf35c9e9544c1bb64a550a0e349e8033ebd4f43e1>
13. CLI verdict IPFS: <https://gateway.pinata.cloud/ipfs/QmUQpQEaggjuZqGAJpxoDXg4ghJ3ReufWM546g856KqUnk>
14. URL-verified x402 payment tx: <https://sepolia.basescan.org/tx/0x8d5d7a46bd88b2ffba5b6e6c6d70221598ee041d4206377ca5991e90f5c12421>
15. URL-verified verdict IPFS: <https://gateway.pinata.cloud/ipfs/QmYmfMRuHxRWJXHswWhRjbQkbqvKmpDaHxuwyR63bFk7AR>

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
- URL-verified evidence receipts include Exa `web_search_exa`, Exa `web_fetch_exa`, source URL, source excerpt, and source content hash where adequate
- execution attribution links paper/live trades to builder codes; fee totals are shown only when fill-price data exists
- unresolved blockers gate clean PASS even when a connector is armed

## Submission one-liner

Prism is an adversarial validation layer for trading agents: a different-family sentinel challenges a trader's reasoning, then returns a receipt-backed verdict through dashboard, MCP, and CLI surfaces.

## Submission paragraph

Prism validates trading-agent reasoning before capital moves. A Claude-family trader generates a Trading-R1 trace; a separate GPT/DSPy sentinel adversarially challenges the evidence, thesis, risk factors, and calibration. Connector Passport arms MCP-first evidence tools; Sentinel searches with Exa `web_search_exa`, verifies selected source URLs with Exa `web_fetch_exa`, and only resolves issues when evidence passes adequacy and extraction gates. The output is a Prism Report with deterministic metrics, a verdict, structured issue ledger, capital gate, per-issue tool outcomes, evidence provenance receipts, IPFS content, x402 payment receipts, and Arc/ERC-8004 validation receipts where anchored. The product is live as a dashboard, x402-protected MCP trust endpoint, developer CLI, and documentation site. Three external x402 validations have settled on Base Sepolia, including a fresh paid MCP validation with URL-verified Exa evidence receipts.
