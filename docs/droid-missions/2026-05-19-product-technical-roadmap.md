# Prism Product + Technical Roadmap

**Status:** post-submission working roadmap  
**Last updated:** May 19, 2026  
**Strategic posture:** build narrow, position broad.

## Executive thesis

> Prism is the validate-before-action trust layer for money-moving agents.

Prediction-market trading agents are the first wedge because reasoning quality, evidence freshness, public auditability, and capital movement are tightly coupled. The broader category is bigger: any autonomous agent that trades, pays, reallocates, or signs needs a verifiable receipt for why the action should be allowed.

## Positioning

### Public positioning

> Verifiable reasoning for money-moving agents.

Alternative copy:

> P&L tells you what happened. Prism shows why an agent acted — and blocks it when the reasoning does not verify.

### Product category

Prism should become a **protocolized trust runtime**, not just a dashboard:

- hosted validator/API for immediate adoption;
- open Prism Report schema for portability;
- SDKs and verifier tools for integration;
- ERC-8004/x402/MPP-compatible receipts where appropriate;
- multi-validator marketplace and disputes only after real usage exists.

### Strategic constraint

Do not broaden into generic AI observability yet. Prism is not trying to replace Braintrust/LangSmith/Langfuse. Prism is for high-risk **agent actions** where money, markets, or onchain state can change.

## Wedge decision

### Primary beta wedge: prediction-market / trading agents

Reasons:

- existing Prism product already works here;
- easiest to demo and explain;
- stale evidence is objectively visible;
- public reasoning receipts matter to users;
- action has financial consequence;
- lower compliance complexity than payroll/payments;
- natural fit with Trading-R1 traces and Polymarket builder attribution.

### Secondary discovery wedge: onchain payment agents

Run discovery now, but do not build payment-specific workflows yet.

Offer a concierge test:

> Send one proposed payment batch or action intent. Prism will return a validation receipt showing what would be allowed, blocked, or require review.

Do **not** build payroll UX, invoice reconciliation, recipient KYC, or payment-specific compliance rules until a pilot demands it.

### Later expansion: DeFi rebalance / treasury agents

DeFi capital at risk is larger, but the action semantics are more complex. Enter through one narrow action type, such as pre-rebalance validation, not generic DeFi risk scoring.

---

# Product roadmap

## Phase 0 — Preserve submission baseline, immediate

Goal: preserve the demo state and record public traction.

Tasks:

- Archive Google Form confirmation screenshot/email.
- Keep production stable; do not re-enable autonomous trading.
- Capture screenshots of Arc quote-tweet and high-signal X comments.
- Add best comments to the traction log.
- Keep `AUTO_PIPELINE=false` until operator controls and budgets land.

Acceptance criteria:

- Submission proof is saved.
- Production remains stable and manually controllable.
- Public signal is captured as qualitative traction.

## Phase 1 — Trust clarity + pilot readiness, 1-2 weeks

Goal: make Prism understandable, safe, and easy to try.

Product tasks:

1. **Publish verification guarantees** *(shipped — Mission 01, 2026-05-20)*
   - Explain what Prism guarantees:
     - provenance;
     - independent adversarial review;
     - source URL verification;
     - source content hashes;
     - issue-ledger transparency;
     - x402/payment receipts;
     - Arc/ERC-8004 references where anchored;
     - fail-closed capital gate.
   - Explain what Prism does **not** guarantee:
     - perfect truth;
     - profit;
     - complete security;
     - legal/compliance approval;
     - that a PASS should always execute real capital.
   - Delivered: `apps/docs/content/docs/verification-guarantees.mdx`.

2. **Define pilot offer**
   - Prediction-market agents: “send 10 trade traces; get Prism Reports + badges.”
   - Payment agents: “send 1 payment intent; get a review receipt.”
   - DeFi agents: “send 1 rebalance intent; get a capital-gate receipt.”

3. **Start discovery**
   - 10 builder conversations:
     - 5 prediction-market / trading-agent builders;
     - 3 payment/onchain-agent builders;
     - 2 DeFi automation or MCP-tool builders.

4. **Tighten homepage copy**
   - Lead with validate-before-action.
   - Keep trading as the proof vertical.
   - Add links to canonical PASS and fail-closed reports.

Acceptance criteria:

- 10 conversations requested, 5 completed.
- 3 credible pilot interests.
- 1 external trace/action validated outside Prism's own auto pipeline.
- Security/verification question can be answered with one public docs URL.

## Phase 2 — Private beta for trading agents, 2-4 weeks

Goal: get another builder's workflow using Prism before action.

Product tasks:

1. **Prism Report v0 as the product artifact**
   - Make report URL / JSON / IPFS content the thing users share.
   - Add concise report status:
     - `ALLOW`;
     - `REVIEW`;
     - `BLOCK`;
     - `HOLD_NO_EVIDENCE`.

2. **Validate-before-trade quickstart**
   - REST example.
   - MCP example.
   - CLI example.
   - TypeScript/Python SDK examples once SDKs exist.

3. **Public/private report modes**
   - Public mode: shareable report for social/trading proof.
   - Private mode: report visible to workspace/API key only, with optional public attestation/hash.

4. **Verified Reasoning badge**
   - Agent profile or badge showing:
     - validations run;
     - latest capital gate;
     - PASS/WARN/REJECT distribution;
     - calibration status;
     - latest receipts.

5. **Pricing tests**
   - Keep `0.01 USDC` dev/basic validation.
   - Test `0.05-0.25 USDC` for URL-verified reports.
   - Test `$49-199/month` operator bundle only after repeat usage.

Acceptance criteria:

- 1 external pilot integrated or running concierge validations weekly.
- 25+ externally submitted validations.
- At least one user says the report changed trust, execution, or copy-trading behavior.

## Phase 3 — Production operator runtime, 1-2 months

Goal: make Prism safe for operators, not just demos.

Product tasks:

1. **Operator control plane** *(shipped — Mission 02, 2026-05-20)*
   - Running/stopped state. *(shipped)*
   - Paper/live mode. *(shipped — read-only, env-only switch)*
   - Last run / next run / interval. *(shipped)*
   - Last error. *(shipped)*
   - Validation, gas, and evidence-provider spend. *(pending — future)*
   - Start/stop controls. *(shipped)*
   - Authenticated admin access. *(shipped — OPERATOR_ADMIN_TOKEN + timingSafeEqual)*

2. **Policy controls**
   - Require verified source URLs.
   - Block stale evidence.
   - Block unresolved critical/material issues.
   - Max trade/payment size.
   - Max validation spend per period.
   - Max evidence-provider requests per period.

3. **Report clarity**
   - Raw Sentinel score.
   - Issue-ledger capped score.
   - Cap reason.
   - Capital gate state.
   - Why action was blocked or allowed.

Acceptance criteria:

- Operator can stop/restart pipeline without shell access.
- Autonomous loop cannot drain provider quota.
- Dashboard makes paper/live/capital-moving state impossible to misunderstand.
- Blocked actions are clearly framed as safety wins.

## Phase 4 — Protocol-shaped portability, 2-3 months

Goal: let other apps generate, verify, and consume Prism-compatible receipts.

Product tasks:

1. **Prism Protocol v0** *(partially shipped — Mission 01, 2026-05-20)*
   - Protocol spec. *(shipped: `docs/protocol/prism-protocol-v0.md`)*
   - Report schema. *(shipped: `docs/protocol/prism-report-v0.schema.json`)*
   - Evidence receipt schema. *(covered in report schema via `evidence_receipts` field)*
   - Validator manifest schema. *(pending)*
   - Capital gate schema. *(covered in report schema via `capital_gate` field)*
   - x402/MPP/payment receipt references. *(shipped: `payment_receipts` discriminated union with `x402` + reserved `mpp`/`ap2`)*
   - ERC-8004/8183 mapping. *(covered in `onchain_receipts` field)*
   - Conformance fixtures. *(shipped: PASS + fail-closed, `docs/protocol/fixtures/`)*

2. **Verifier tools**
   - `/verify` web page.
   - `prism verify report.json` CLI.
   - `verifyReport(report)` SDK helper.

3. **Conformance fixtures**
   - PASS report.
   - Fail-closed report.
   - Stale evidence report.
   - Payment/action intent report.

4. **Validator manifests**
   - Endpoint URL.
   - ERC-8004 agent ID.
   - public key.
   - model family.
   - supported tools.
   - supported domains.
   - price/payment methods.
   - privacy mode.

Acceptance criteria:

- Another app can verify a Prism Report without the dashboard.
- Prism-compatible fixtures validate in Python and TypeScript.
- A third-party agent can call Prism before action using documented API/MCP flow.

---

# Technical roadmap

## P0 — Safety, reliability, and operator control

Do this before re-enabling autonomous trading.

### 1. Operator control plane *(shipped — Mission 02, 2026-05-20)*

Files likely affected:

- `apps/trader/src/trader/main.py`
- `apps/dashboard/app/admin/page.tsx`
- `apps/dashboard/app/api/admin/*`
- `infra/db/migrations/005_operator_events.sql`

Requirements:

- `GET /runtime` or `GET /schedule` returns scheduler state, interval, last tick, last error, and trade mode.
- `POST /schedule/start` and `DELETE /schedule` require admin auth.
- Dashboard admin page shows state clearly.
- Every operator action emits audit event.

Acceptance criteria:

- Stopped loop cannot continue in background. *(shipped)*
- UI and API agree on scheduler state. *(shipped)*
- No unauthenticated admin mutations. *(shipped)*

### 2. Evidence budgets and circuit breakers

Files likely affected:

- `apps/sentinel/src/sentinel/resolution_loop.py`
- `apps/sentinel/src/sentinel/evidence_tools.py`
- `apps/sentinel/src/sentinel/main.py`
- `apps/dashboard/app/lib/connector-store.ts`

Requirements:

- Provider request caps per period.
- Evidence cache by market/query/source URL.
- 429 backoff and cooldown.
- Circuit breaker state shown in report/tool outcome.
- Budget exhaustion fails closed with explicit receipt.

Acceptance criteria:

- Internal unpaid validations cannot drain Exa/provider quota.
- Paid validations receive higher evidence budget when configured.
- Public report explains skipped evidence calls.

### 3. Tool-first trader evidence

Files likely affected:

- `apps/trader/src/trader/trading_r1.py`
- `apps/trader/src/trader/prompts.py`
- `apps/trader/src/trader/tools/*`
- `packages/schemas-python/src/prism_schemas/trace.py`

Requirements:

- Trader gathers structured evidence before BUY/SELL.
- Evidence includes URL/provider/timestamp/hash where available.
- Missing/stale evidence forces HOLD.
- Prompt forbids invented sources or timestamps.

Acceptance criteria:

- BUY/SELL traces have current structured evidence receipts.
- HOLD is non-tradeable.
- Tests cover stale/no evidence forcing HOLD.

### 4. Raw vs capped score clarity

Files likely affected:

- `packages/schemas-python/src/prism_schemas/verdict.py`
- `packages/schemas-typescript/src/verdict.ts`
- `apps/sentinel/src/sentinel/validation.py`
- `apps/dashboard/app/lib/public-api.ts`
- `apps/dashboard/app/trace/[id]/page.tsx`

Requirements:

- Persist raw model score separately from policy-capped score.
- Persist cap reason.
- Persist unresolved blocker/material issue counts.
- Expose capital gate separately from verdict label.

Acceptance criteria:

- User can tell whether WARN came from model judgment or policy cap.
- API/report/dashboard show the same explanation.

## P1 — Prism Report v0 and verifier

### 1. Report schema *(shipped — Mission 01, 2026-05-20)*

Created:

- `docs/protocol/prism-report-v0.schema.json`
- `docs/protocol/prism-protocol-v0.md`
- `docs/protocol/receipt-verification-v0.md`

Minimum fields:

```json
{
  "schema_version": "prism.report.v0",
  "trace_uri": "ipfs://...",
  "action_intent": {},
  "requester": {},
  "agent": {},
  "validator": {},
  "verdict": {},
  "issue_ledger": [],
  "evidence_receipts": [],
  "capital_gate": {},
  "payment_receipts": [],
  "onchain_receipts": [],
  "content_hashes": {}
}
```

Important design:

- Make `action_intent` generic.
- Implement `PredictionMarketAction` first.
- Leave room for `PaymentBatchIntent`, `DeFiRebalanceIntent`, and `TreasuryMoveIntent` later.

### 2. Verifier

Add:

- CLI command: `prism verify report.json`
- API route: `/api/public/reports/:id/verify`
- UI route: `/verify`

Verifier checks:

- schema validity;
- content hashes;
- source URL hashes where available;
- IPFS CID reference;
- x402/MPP payment reference shape;
- Arc/ERC-8004 reference shape;
- capital gate consistency with unresolved issues.

Acceptance criteria:

- PASS and fail-closed fixtures verify locally.
- Invalid/tampered report fails with readable error.

## P2 — SDKs and integrations

### TypeScript SDK

Create `packages/sdk-typescript/` with:

- `fetchReport(idOrUrl)`
- `verifyReport(report)`
- `validateBeforeAction(actionIntent)`
- `explainGate(report)`

### Python SDK

Create `packages/sdk-python/` with:

- Pydantic report models;
- async client;
- verification helpers;
- paid validation wrapper.

### Integration examples

Add examples for:

- prediction-market bot validates before trade;
- MCP agent validates before tool/action execution;
- payment-agent intent validation, concierge/example only;
- DeFi rebalance intent validation, example only.

Acceptance criteria:

- External developer can integrate validate-before-trade in under 30 minutes.
- SDK tests use checked-in report fixtures.

## P3 — Connector security and enterprise readiness

Requirements:

- real admin roles instead of token-only controls;
- connector audit logs;
- secret rotation/revocation;
- smoke-test history;
- provider health and budget display;
- no private/local/HTTP URLs by default;
- no connector secrets in logs, reports, pinned artifacts, UI, or public API.

Acceptance criteria:

- Connector changes are attributable and replayable.
- A builder can understand which provider/tool was used without seeing secrets.

---

# MPP / payment protocol strategy

## What MPP is

Assuming “MPP” means **Machine Payments Protocol**: MPP is a machine-to-machine payment protocol co-authored by Tempo Labs and Stripe. It standardizes HTTP `402 Payment Required` through a `WWW-Authenticate: Payment` challenge, retry with `Authorization: Payment`, and response with `Payment-Receipt`. Cloudflare’s docs describe MPP as payment-method agnostic: Tempo stablecoins, Stripe/shared payment tokens, Lightning, cards, and custom methods. Cloudflare also states MPP is backwards-compatible with x402 for core `exact` charge flows.

Relevant docs:

- Stripe MPP docs: <https://docs.stripe.com/payments/machine/mpp>
- Cloudflare MPP docs: <https://developers.cloudflare.com/agents/agentic-payments/mpp/>
- MPP protocol site: <https://mpp.dev>

## Best judgment

MPP is strategically important, but it should be a **payment adapter**, not Prism’s core protocol.

Prism’s core protocol is the validation receipt:

> action intent → adversarial review → evidence receipts → issue ledger → capital gate → payment/onchain references.

MPP/x402/AP2 are payment rails around that receipt. They answer “how does the agent pay?” Prism answers “should this agent action be trusted before it pays/trades/signs?”

## Recommended approach

### Keep x402 as the current production rail

Reasons:

- already implemented;
- already has public settlement receipts;
- aligns with Circle/Arc hackathon story;
- simple for agent-callable paid validation;
- fits Prism’s MCP endpoint today.

### Add MPP compatibility later through an adapter

Add a payment abstraction in Prism Report v0:

```json
{
  "payment_receipts": [
    {
      "protocol": "x402",
      "network": "base-sepolia",
      "tx_hash": "0x...",
      "amount": "0.01",
      "asset": "USDC"
    }
  ]
}
```

Later allow:

```json
{
  "payment_receipts": [
    {
      "protocol": "mpp",
      "method": "tempo|stripe_spt|lightning|card|custom",
      "receipt_header_hash": "...",
      "amount": "0.10",
      "asset": "USD|USDC"
    }
  ]
}
```

### Do not pivot the product around MPP

MPP expands payment reach, but it does not create Prism’s moat. The moat is:

- issue-ledger semantics;
- fail-closed capital gates;
- evidence adequacy checks;
- URL/source-content verification;
- cross-family adversarial validation;
- portable Prism Reports;
- real agent-action datasets.

## When to implement MPP

Implement MPP when one of these is true:

1. A pilot uses Cloudflare/Stripe/Tempo and asks for MPP.
2. Prism wants to sell validation to non-crypto developers who prefer cards/SPTs.
3. MPP adoption materially exceeds x402 in target channels.
4. The adapter is cheap because x402 compatibility covers the core flow.

Until then, keep MPP in the protocol schema as a supported future payment receipt type, but do not spend core engineering time on it.

## Caution

Stripe’s MPP docs currently include regional/business constraints for accepting stablecoin and SPT payments. Prism should not rely on Stripe MPP as the only payment path until legal/entity eligibility is clear. Circle/x402 remains the cleaner current path for Prism’s onchain-agent story.

---

# 30-day execution plan

## Week 1

- Publish verification guarantees page. *(done — Mission 01)*
- Create `docs/protocol/prism-protocol-v0.md` draft. *(done — Mission 01)*
- Create Prism Report v0 schema draft. *(done — Mission 01)*
- Add traction screenshots/comments to private traction log.
- Start outreach to 10 builders.

## Week 2

- Build report verifier CLI/API skeleton.
- Add operator runtime status endpoint. *(done — Mission 02)*
- Add admin dashboard read-only state view. *(done — Mission 02)*
- Add provider budget/circuit-breaker design + first tests.
- Run 5 discovery conversations.

## Week 3

- Add start/stop admin controls with audit logs. *(done — Mission 02)*
- Add raw/capped score fields to schemas/API/UI.
- Add `validate-before-trade` quickstart.
- Run first external pilot/concierge validation.

## Week 4

- Ship TypeScript SDK alpha.
- Ship Python SDK alpha or CLI-backed client.
- Add conformance fixtures.
- Decide whether first private beta remains trading-only or adds one payment-agent pilot.

---

# Metrics to track

## Product metrics

- external validations;
- unique external wallets/API keys;
- reports shared;
- validations before action;
- actions blocked by capital gate;
- pilot integrations;
- repeat validators/requesters.

## Trust metrics

- source URLs verified;
- source extraction failure rate;
- stale evidence blocks;
- unresolved critical/material issue count;
- raw-vs-capped score deltas;
- provider budget/circuit breaker events.

## Business metrics

- discovery conversations completed;
- pilots started;
- willingness-to-pay signal;
- preferred pricing model;
- public/private report preference;
- integration surface preference: MCP, REST, SDK, CLI, webhook.

---

# Avoid

- Do not restart autonomous live trading before operator controls and budgets exist.
- Do not build custom Solidity or token mechanics for protocol v0.
- Do not put raw prompts, private chain-of-thought, scraped pages, API responses, or secrets onchain.
- Do not claim Prism proves truth, profit, or legal compliance.
- Do not let payment-agent expansion derail the trading-agent beta.
- Do not compete as generic LLM observability.

# Summary

For the next 90 days:

> Own validate-before-action receipts for prediction-market agents, while designing Prism Report v0 so payment and DeFi agents can adopt the same trust layer later.
