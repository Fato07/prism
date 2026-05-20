# Factory Mission 02 — Operator Safety Control Plane

**Status:** ✅ COMPLETE (2026-05-20)

## Goal

Make Prism’s autonomous runtime observable and safely controllable before any future autonomous trading is re-enabled.

This Mission turns “keep AUTO_PIPELINE=false” from an operator memory rule into product infrastructure: runtime status, authenticated controls, and audit logs.

## Background

Prism currently has safety fixes that keep the auto pipeline disabled and stoppable, but a production operator still needs a clear control plane:

- Is the trader scheduler running?
- Is the system in paper or live mode?
- When was the last tick?
- What was the last error?
- Who started/stopped the pipeline?

Read first:

- `AGENTS.md`
- `docs/droid-missions/2026-05-19-product-technical-roadmap.md`
- `docs/droid-missions/2026-05-18-post-hackathon-product-hardening.md`
- `apps/trader/src/trader/main.py`
- `apps/trader/src/tests/test_trader.py`
- relevant dashboard API/page conventions

## Non-goals

- Do not re-enable `AUTO_PIPELINE`.
- Do not deploy or restart production.
- Do not add live trading controls beyond clearly guarded paper/live display unless explicitly approved.
- Do not expose secrets or private env values.

## Milestone 1 — Read-only Runtime Status

### Features

1. Add or formalize a trader runtime status endpoint:
   - scheduler running/stopped;
   - configured interval;
   - auto-pipeline enabled flag;
   - trade mode;
   - last tick timestamp;
   - next tick if known;
   - last error if any;
   - service/deployment version if available.
2. Ensure the endpoint has no side effects.
3. Add tests for stopped state and no auto-start behavior.
4. Add a dashboard admin/operator page that displays read-only state.

### Validation

- Reading status never starts the scheduler.
- Tests pass.
- UI cannot be confused with a mutation surface.

## Milestone 2 — Authenticated Mutations

### Features

1. Add authenticated admin routes for:
   - start scheduler;
   - stop scheduler;
   - optionally update interval with safe bounds.
2. Require explicit confirmation in UI for any start action.
3. Show current state before mutation.
4. Do not enable live trading by default.

### Validation

- Unauthorized mutation returns 401/403.
- Authorized local/test mutation works.
- Stop action cancels any background task.
- Start action cannot accidentally switch from paper to live.

## Milestone 3 — Operator Audit Log

### Features

1. Add migration for operator events if needed:
   - actor;
   - action;
   - old state;
   - new state;
   - timestamp;
   - result;
   - error if any.
2. Write audit event for every mutation attempt.
3. Surface recent audit events in admin page if feasible.

### Validation

- Tests cover audit event writing or mocked event writer.
- Failed/unauthorized attempts are either logged safely or explicitly documented.

## Suggested files

- `apps/trader/src/trader/main.py`
- `apps/trader/src/tests/test_trader.py`
- `apps/dashboard/app/admin/page.tsx` or `apps/dashboard/app/operator/page.tsx`
- `apps/dashboard/app/api/admin/runtime/route.ts`
- `apps/dashboard/app/api/admin/schedule/route.ts`
- `apps/dashboard/app/lib/admin-auth.ts`
- `apps/dashboard/__tests__/admin*.test.ts`
- `infra/db/migrations/005_operator_events.sql`

## Suggested verification commands

```bash
uv run pytest apps/trader/src/tests/test_trader.py -q
pnpm --dir apps/dashboard test
pnpm --dir apps/dashboard lint
```

## Completion criteria

- Operator can see runtime status without shell access.
- Operator can stop/start safely in local/test environment with auth.
- Audit path exists for control-plane mutations.
- `AUTO_PIPELINE=false` remains the safe default.
