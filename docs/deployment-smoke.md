# Deployment smoke checklist

Use this before a Railway deploy or demo reset.

## Local verification

```bash
uv run pytest apps/mcp/src/tests apps/sentinel/src/tests/test_evidence_tools.py apps/sentinel/src/tests/test_resolution_loop.py -q
pnpm --filter prism-dashboard test
pnpm --filter prism-dashboard build
```

## Database migration

Apply the additive Connector Passport v1 migration with the pooled Neon URL:

```bash
psql "$DATABASE_URL" -f infra/db/migrations/004_tool_connectors.sql
psql "$DATABASE_URL" -c '\d+ tool_connectors'
```

Expected safety checks:

- `tool_connectors_one_armed_per_kind_idx` exists.
- `auth_secret_ciphertext` exists but is never selected by public/dashboard redacted APIs.
- `smoke_receipt` is JSONB and contains only redacted smoke metadata.

## Railway env sanity

Required for hosted connector passports:

```bash
PRISM_EVIDENCE_DB_CONNECTORS=1
CONNECTOR_SECRETS_KEY=<32-byte base64 key from `openssl rand -base64 32`>
CONNECTOR_ADMIN_TOKEN=<operator-only connector admin token>
DATABASE_URL=<Neon pooled URL>
```

Optional env-only fallback:

```bash
PRISM_EVIDENCE_PROVIDER=mcp
PRISM_EVIDENCE_MCP_URL=https://your-tool-server.example/mcp/
PRISM_EVIDENCE_MCP_TOOL=search
PRISM_EVIDENCE_RESULT_MAPPER=generic_search
PRISM_EVIDENCE_MCP_INPUT_MAPPER=query_limit
PRISM_EVIDENCE_MCP_ALLOWED_TOOLS=search
```

Set `PRISM_EVIDENCE_DB_CONNECTORS=0` only when intentionally bypassing the DB connector registry.

For live demo evidence without a third-party research provider, sentinel exposes a free
read-only market evidence MCP server at:

```text
$SENTINEL_PUBLIC_URL/market-evidence-mcp/
```

Use tool `search`, input mapper `prism_evidence_request`, and result mapper
`generic_search`. It calls the Prism Polymarket gateway and only returns evidence for
market-structure or explicit market-status temporal challenges; unsupported issue types
return no evidence and stay fail-closed. The sentinel also applies an evidence adequacy
gate, so a non-empty connector response cannot resolve an issue unless it matches the
challenge type and required resolution.

Sentinel also exposes a smoke-only demo MCP server at:

```text
$SENTINEL_PUBLIC_URL/demo-evidence-mcp/
```

Use tool `search`, input mapper `query_limit`, and result mapper `generic_search`. The demo
server returns one evidence-shaped result for Connector Passport smoke tests and returns no
evidence for ordinary issue-resolution queries unless `PRISM_DEMO_EVIDENCE_ALLOW_RESOLUTION=1`
is explicitly enabled.

## Runtime smoke

1. Open `/dashboard` and confirm the `Evidence tool route` card is visible near Sentinel reasoning.
2. Open `/connectors`.
3. Enter the connector admin token.
4. Save an MCP HTTP connector passport.
5. Run smoke.
6. Confirm the smoke receipt shows transport/schema/mapper/fail-closed checks.
7. Arm the connector.
8. Return to `/dashboard` and confirm the active route shows as armed.
9. Run one validation with `ADVERSARIAL_RESOLUTION_MAX_ROUNDS=2`.
10. Confirm unresolved blockers remain unresolved if the connector fails or returns malformed output.

## Public API smoke

```bash
curl -s -H "Authorization: Bearer $CONNECTOR_ADMIN_TOKEN" "$DASHBOARD_URL/api/connectors" | jq '.connectors[] | {id,name,armed,smoke_status,auth_configured,status_label}'
curl -s "$DASHBOARD_URL/api/public/stats" | jq .
curl -s "$DASHBOARD_URL/api/public/traces/$TRACE_ID/report" | jq '{trace_id, issue_ledger, receipt_verification}'
```

The connector response must not include bearer tokens or `auth_secret_ciphertext`.
