# Post-hackathon mission — product-grade Prism trust runtime

**Status:** Parked / do not start until after hackathon submission.
**Priority before submission:** Low, unless a reliability issue blocks the demo or public receipts.
**Resume trigger:** After the final Agora/Canteen submission is complete and demo assets are archived.

## Why this exists

Prism started as a hackathon build, but the stronger long-term product is a trust layer for autonomous agents that need to justify actions before moving money.

The post-hackathon goal is to turn the current demo-grade pipeline into a production-grade runtime that real builders can operate, audit, and pay for.

## Product thesis

> Prism is a trust runtime for autonomous agents: before an agent moves money, Prism verifies the reasoning, evidence, provenance, and policy gates behind the action.

Prediction-market trading remains the wedge, but the broader platform can serve:

- prediction-market agents;
- DeFi and treasury automation;
- DAO trading bots;
- MCP/x402 tool providers;
- agent marketplaces that need receipt-backed action quality.

## Non-goals for hackathon week

Do **not** let this mission distract from winning the hackathon. Before submission, only pull work from this file when it directly supports:

- demo reliability;
- judge-facing clarity;
- prevention of bad live autonomous behavior;
- public API/report correctness;
- safety around payments, connector secrets, or capital movement.

## Workstreams

### 1. Operator control plane

Build a production-grade admin surface for autonomous pipeline operation.

Tasks:

- Show `paused`, `paper`, and `live` mode clearly.
- Show scheduler state: running/stopped, last run, next run, interval, last error.
- Add explicit start/stop controls for the trader pipeline.
- Display validation, gas, and evidence-provider spend per period.
- Require authenticated admin access for all controls.

Success criteria:

- An operator can safely pause/restart the agent without shell access.
- A stopped auto loop cannot continue in the background.
- The UI makes capital-moving state impossible to misunderstand.

### 2. Evidence as infrastructure, not prompt prose

Trader evidence must come from approved tools or explicit data limitations, not model-invented citations.

Tasks:

- Add tool-first market/evidence retrieval before trace generation.
- Represent evidence as structured receipts with source URL, content hash, timestamp, provider, and extractor.
- Force `HOLD` when current market-specific evidence is unavailable.
- Keep stale evidence as a valid concern, not something to paper over with fake timestamps.

Success criteria:

- BUY/SELL traces have current structured evidence.
- Missing, stale, malformed, or fabricated evidence fails closed into HOLD or Sentinel blockers.
- Public reports can explain exactly which evidence supported or failed a trade.

### 3. Validation budget, queueing, and provider reliability

Sentinel evidence retrieval should be budgeted and reliable under autonomous load.

Tasks:

- Add provider budgets and max spend/requests per period.
- Cache evidence by market/query/source URL.
- Add backoff and circuit breakers for `429` / provider failures.
- Queue validation jobs instead of letting every auto tick trigger repeated external calls.
- Log skipped evidence calls as receipts/reasons, not silent omissions.

Success criteria:

- Exa/Tavily/Brave/MCP providers cannot be spammed by the auto loop.
- Paid external validations keep high-quality evidence resolution.
- Internal unpaid validations use a conservative, quota-safe path by default.

### 4. Raw score, capped score, and capital gate clarity

Make the trust outcome explainable to builders and judges.

Tasks:

- Persist and expose raw Sentinel score separately from issue-ledger capped score.
- Expose cap reason and unresolved blocker/material counts.
- Show capital gate state separately from model verdict.
- Update dashboard/report/API copy to frame blocked trades as safety wins.

Success criteria:

- A user can tell whether a `WARN` came from model judgment or policy caps.
- Public receipts explain why capital was blocked or allowed.
- The dashboard reinforces Prism's value: bad or under-supported actions do not move money.

### 5. Connector security and enterprise readiness

Harden Connector Passport into a trustworthy integration surface.

Tasks:

- Replace token-only admin control with real authenticated admin roles.
- Add audit logs for connector creation, arming, secret rotation, smoke tests, and failures.
- Track connector health and historical smoke receipts.
- Add secret rotation and revocation flows.
- Keep private/local/HTTP URL blocking as the default safety posture.

Success criteria:

- Connector changes are attributable and replayable.
- Secrets never leak to logs, receipts, UI, public APIs, or pinned artifacts.
- A builder can understand which provider was used without seeing connector secrets/config.

### 6. Commercial wedge validation

Increase business confidence with real external signal.

Tasks:

- Talk to 5-10 prediction-market or agent builders.
- Ask whether they would use Prism as a pre-trade validation layer.
- Test pricing: per validation, per agent/month, or enterprise runtime fee.
- Capture objections and missing trust requirements.
- Convert strongest feedback into a private-beta plan.

Success criteria:

- At least 3 credible builders say they want to try Prism in an agent workflow.
- At least 1 external workflow is integrated or committed to a pilot.
- Pricing and buyer persona become sharper than the current hackathon wedge.

## First post-hackathon sprint proposal

1. Deploy all hackathon fixes to a stable production baseline.
2. Add operator control plane + authenticated scheduler controls.
3. Add evidence-provider budget/cache/circuit breaker.
4. Add raw-vs-capped score fields to DB/API/dashboard.
5. Convert trader evidence generation to tool-first or HOLD.
6. Start private-beta outreach using the demo receipts as proof.

## Confidence target

Current confidence estimate: ~7.5/10 that Prism is worth continuing seriously.

Target after this mission:

- technical/product confidence: 8.5/10;
- business confidence: improved only if external builders validate the need.

The confidence should increase through evidence, not optimism.
