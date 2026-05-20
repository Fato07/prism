# Droid Factory Mission List — Prism Post-Submission

**Status:** superseded by Factory Mission briefs  
**Last updated:** May 19, 2026

This file is an index. The actual mission briefs live under:

`docs/droid-missions/factory/`

Start there:

- `docs/droid-missions/factory/README.md`
- `docs/droid-missions/factory/01-trust-surface-report-v0.md`
- `docs/droid-missions/factory/02-operator-safety-control-plane.md`
- `docs/droid-missions/factory/03-evidence-reliability-tool-first.md`
- `docs/droid-missions/factory/04-verify-integrate-beta.md`
- `docs/droid-missions/factory/05-connector-security-payment-rails.md`
- `docs/droid-missions/factory/06-release-stabilization.md`

## Why this changed

The first draft looked like ordinary subagent prompts. That is not the best fit for Factory Missions. Factory Missions are collaborative planning/orchestration workflows: you start `/missions`, provide a structured goal, refine features and milestones with Mission Control, then let the orchestration layer assign workers and run milestone validation.

The new files are therefore **mission briefs**, not “you are Droid” prompts.

## Mission status

| # | Mission | Status | Completed | Notes |
|---|---------|--------|-----------|-------|
| 01 | Trust Surface + Prism Report v0 | **COMPLETE** | 2026-05-20 | Schema, protocol docs, fixtures, 82 vitest tests, 146 assertions. Branch: feat/llms-txt. |
| 02 | Operator Safety Control Plane | **COMPLETE** | 2026-05-20 | Runtime status, authenticated start/stop, audit log, /operator page. |
| 03 | Evidence Reliability + Tool-First Trading | Pending | — | |
| 04 | Verify + Integrate Beta | Pending | — | Unblocked: Mission 01 schema now exists. |
| 05 | Connector Security + Payment Rail Abstraction | Pending | — | Depends on 01 + ideally 03. |
| 06 | Release Stabilization | Pending | — | After any major merge batch. |

## Global constraints

- Keep `AUTO_PIPELINE=false` unless explicitly approved.
- Do not deploy/restart production without explicit approval.
- Do not add custom Solidity/token mechanics for protocol v0.
- Do not run paid calls without explicit spend approval.
- Do not commit secrets/private pilot notes.
- Keep Prism focused: validate-before-action receipts for money-moving agents, with prediction-market agents as the first beta wedge.
