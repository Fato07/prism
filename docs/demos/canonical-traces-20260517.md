# Canonical Prism demo traces — 2026-05-17

These traces are frozen as demo references for the evidence-ledger / connector-passport story.
Use the dashboard URL for live walkthroughs and the public report API for machine-verifiable receipts.

## 1. Fail-closed guardrail trace

- Trace ID: `74cead4a-5def-4cec-8cb2-b5294d739acb`
- Dashboard: <https://prism-dashboard-production-e6e3.up.railway.app/trace/74cead4a-5def-4cec-8cb2-b5294d739acb>
- Public report: <https://prism-dashboard-production-e6e3.up.railway.app/api/public/traces/74cead4a-5def-4cec-8cb2-b5294d739acb/report>
- Market: `Will the lowest temperature in Shanghai be 23°C on May 19?`
- Verdict: `PASS`, score `70`
- Gate state: `clean_pass_allowed=true`, `endorsement_allowed=false`
- Guardrail proof: two material `source_quality` issues remain `open` with `tool_status=fail_closed`:
  - `ev-1`: average May temperature claim lacked adequate climate-change/anomaly support.
  - `ev-2`: urban heat island implication lacked specific local support for the threshold.

Demo line: Prism can still show a PASS score while refusing endorsement because material evidence requests failed closed.

## 2. Exa URL-verified evidence trace

- Trace ID: `85d58b9c-f45f-4aa1-8b8a-7a4b1c1c8fea`
- Dashboard: <https://prism-dashboard-production-e6e3.up.railway.app/trace/85d58b9c-f45f-4aa1-8b8a-7a4b1c1c8fea>
- Public report: <https://prism-dashboard-production-e6e3.up.railway.app/api/public/traces/85d58b9c-f45f-4aa1-8b8a-7a4b1c1c8fea/report>
- Market: `Will "Striking Distance" be the top global Netflix movie this week?`
- Verdict: `PASS`, score `65`
- Gate state: `clean_pass_allowed=true`, `endorsement_allowed=false`
- Latest paid MCP receipt: `docs/demos/external-call-20260517T203104+0000.md`
- Full x402 settlement URL: <https://sepolia.basescan.org/tx/0x8d5d7a46bd88b2ffba5b6e6c6d70221598ee041d4206377ca5991e90f5c12421>
- Paid response URI: `ipfs://QmYmfMRuHxRWJXHswWhRjbQkbqvKmpDaHxuwyR63bFk7AR`

Receipt proof in the public report:

| Issue | Provider | Search tool | Extractor | Source hash |
| --- | --- | --- | --- | --- |
| `ev-1` | `exa_mcp` | `web_search_exa` | `exa_contents` / `web_fetch_exa` | `c395474da0514f611ec7e0762fe2d3c4298af586616943a6b7b07139d4c614ae` |
| `ev-2` | `exa_mcp` | `web_search_exa` | `exa_contents` / `web_fetch_exa` | `6cbc2da1e038210bc20c4951cf0f3aa04d9f681d74b22ef84d75e4585d96da64` |
| `sys-temporal-stale-evidence` | `exa_mcp` | `web_search_exa` | `exa_contents` / `web_fetch_exa` | `6cbc2da1e038210bc20c4951cf0f3aa04d9f681d74b22ef84d75e4585d96da64` |

Demo line: Sentinel used the armed Exa MCP search connector, fetched the selected source URL through Exa `web_fetch_exa`, stored the extractor identity plus content hash, and only then marked matching evidence issues resolved.
