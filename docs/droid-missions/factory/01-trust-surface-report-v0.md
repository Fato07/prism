# Factory Mission 01 — Trust Surface + Prism Report v0

**Status:** COMPLETE
**Date completed:** 2026-05-20
**Branch:** feat/llms-txt

## Completion summary

All three milestones shipped. Delivered artifacts:

1. `apps/docs/content/docs/verification-guarantees.mdx` — public docs page (8 guarantees, 5 NOT-guarantees, trust assumptions, fail-closed behavior)
2. `docs/protocol/prism-report-v0.schema.json` — JSON Schema Draft 2020-12 (15 required top-level fields, discriminated unions on `action_intent` and `payment_receipts`, strict object closure, oracle-hardened)
3. `docs/protocol/prism-protocol-v0.md` — human protocol spec (onchain-forbidden rules, canonicalization, fail-closed semantics, score semantics)
4. `docs/protocol/receipt-verification-v0.md` — verification walkthrough (IPFS CID, Base Sepolia x402, Arc validation tx, content-hash recomputation)
5. `docs/protocol/oracle-review.md` — mission oracle review findings (10 issues/resolutions from independent audit)
6. `docs/protocol/README.md` — protocol index (artifact links, smoke commands, canonical test gate, drift canary, reserved-type tables)
7. `docs/protocol/fixtures/pass-report.json` — canonical PASS conformance fixture from live API (trace d6cdd60f)
8. `docs/protocol/fixtures/fail-closed-report.json` — canonical fail-closed conformance fixture from BLOCK trace (50b93a7b)
9. 82 vitest tests in `apps/docs/__tests__/docs-content.test.ts` (schema structure, protocol content, fixture validation, 4 tampered-fail cases, cross-receipt consistency, score-label invariants, secrets scans)
10. `apps/docs/package.json` — added ajv@^8 and ajv-formats@^3 devDependencies

Verification: 146/146 assertions passed, 82/82 tests pass. All recorded commands exit 0. Canonical test gate: `pnpm --dir apps/docs test`.

## Goal

Turn Prism’s trust story into a concrete, portable receipt standard and public explanation.

By the end of this Mission, a builder should understand exactly what Prism guarantees, what it does not guarantee, and how a `Prism Report v0` can be verified without trusting the dashboard UI.

## Background

Prism’s post-submission thesis is:

> Prism is the validate-before-action trust layer for money-moving agents.

The strongest public question from traction was: “what guarantees the security and verification here?” This mission answers that question and defines the portable artifact Prism can eventually protocolize.

Read first:

- `AGENTS.md`
- `docs/droid-missions/2026-05-19-product-technical-roadmap.md`
- `docs/research/2026-05-19-prism-market-landscape.md`
- `docs/research/2026-05-19-prism-market-sizing-gap.md`
- existing docs under `apps/docs/content/docs/`
- public report route: `apps/dashboard/app/api/public/traces/[id]/report/route.ts`

## Non-goals

- No custom Solidity.
- No token mechanics.
- No MPP or Stripe implementation.
- No live paid calls.
- No claim that Prism proves truth, profit, or legal compliance.

## Milestone 1 — Verification Guarantees Documentation

### Features

1. Create or update a docs page explaining:
   - what Prism guarantees;
   - what Prism does not guarantee;
   - trust assumptions;
   - fail-closed behavior;
   - how source URL verification and source hashes work;
   - how x402/payment receipts and Arc/ERC-8004 references fit in.
2. Link canonical examples:
   - URL-verified PASS report;
   - fail-closed guardrail trace/report;
   - latest x402 paid validation receipt.
3. Add concise README or docs navigation link if appropriate.

### Validation

- Docs tests pass.
- Copy avoids overclaiming correctness/profit/security.
- A reader can answer “what does Prism guarantee?” in under 2 minutes.

## Milestone 2 — Prism Report v0 Schema + Protocol Draft

### Features

1. Create `docs/protocol/prism-protocol-v0.md`.
2. Create `docs/protocol/prism-report-v0.schema.json`.
3. Create `docs/protocol/receipt-verification-v0.md`.
4. Define `action_intent` as a generic envelope.
5. Define first concrete action type: `PredictionMarketAction`.
6. Reserve future action types:
   - `PaymentBatchIntent`;
   - `DeFiRebalanceIntent`;
   - `TreasuryMoveIntent`.
7. Define payment receipt references for:
   - current x402 receipts;
   - future MPP receipt headers/hashes;
   - optional AP2/mandate references if useful.
8. Define Arc/ERC-8004 reference shape.
9. Define what belongs onchain vs pinned/signed/offchain.

### Validation

- JSON schema is valid.
- Protocol docs explicitly say no raw prompts, raw scraped pages, secrets, or private chain-of-thought go onchain.
- Protocol v0 can be understood without running the dashboard.

## Milestone 3 — Conformance Fixtures

### Features

1. Add fixture: PASS report.
2. Add fixture: fail-closed report.
3. Add fixture: stale-evidence/HOLD report if feasible.
4. Add minimal tests or scripts to validate fixtures against schema.

### Validation

- Fixtures pass schema validation.
- Tampered or invalid fixture fails if a validator script/test is included.

## Suggested files

- `apps/docs/content/docs/security.mdx`
- `apps/docs/content/docs/receipts.mdx`
- `apps/docs/content/docs/public-apis.mdx`
- new: `apps/docs/content/docs/verification-guarantees.mdx`
- new: `docs/protocol/prism-protocol-v0.md`
- new: `docs/protocol/prism-report-v0.schema.json`
- new: `docs/protocol/receipt-verification-v0.md`
- new: `docs/protocol/fixtures/*.json`
- `apps/docs/__tests__/docs-content.test.ts`

## Suggested verification commands

```bash
pnpm --dir apps/docs test
pnpm --dir apps/docs lint
python -m json.tool docs/protocol/prism-report-v0.schema.json >/dev/null
python -m json.tool docs/protocol/fixtures/pass-report.json >/dev/null
python -m json.tool docs/protocol/fixtures/fail-closed-report.json >/dev/null
```

## Completion criteria

- Verification guarantees docs exist and are linked.
- Prism Report v0 draft exists with fixtures.
- Tests/validation commands are recorded in the final Mission summary.
