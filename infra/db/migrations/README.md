# Database migrations

Forward-only SQL migrations for the Neon Postgres database that backs Prism.

## Conventions

- Files live in this directory, named `NNN_short_description.sql` (e.g. `001_validations_requester_address.sql`).
- `NNN` is a zero-padded three-digit sequence number, monotonically increasing. Start at `001`. Do not reuse or renumber.
- Each migration is **additive only**. Allowed: `CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`. Forbidden in this mission: `DROP`, destructive `ALTER COLUMN`, `TRUNCATE`.
- Every migration must be idempotent — applying it twice must be a no-op.
- Update the cross-language schemas in the same commit:
  - `packages/schemas-python/` — Pydantic v2 model field.
  - `packages/schemas-typescript/` — Zod schema field.

## Applying a migration

Migrations are applied by a worker (or operator) from a local environment with `psql` on PATH and the pooled `DATABASE_URL` exported:

```bash
psql "$DATABASE_URL" -f infra/db/migrations/NNN_short_description.sql
```

After applying, verify the change against the live schema and paste the relevant `\d+` block into the worker handoff:

```bash
psql "$DATABASE_URL" -c '\d+ <table_name>'
```

## Rollback

There is no automated rollback. To revert a change, author a new forward-only migration with a higher sequence number that re-states the desired schema. Never edit a previously committed migration file.

## Connection string

Always use the pooled connection URL (with the `-pooler` suffix) — see `.env.example` `DATABASE_URL`. The non-pooled URL (`DATABASE_URL_UNPOOLED`) is reserved for ad-hoc administrative work and must never be hardcoded in service code.
