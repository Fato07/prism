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

Recommended hosted broad-research Connector Passport preset:

```text
name: Exa hosted MCP evidence
transport: mcp_http
server_url: https://mcp.exa.ai/mcp
tool_name: web_search_exa
input_mapper: query_max_results
result_mapper: exa_mcp_text
allowed_tools: web_search_exa
max_results: 5
max_usdc: null
fail_closed: true
```

Recommended URL-extraction env for production Sentinel:

```bash
PRISM_EVIDENCE_EXTRACTOR=mcp
PRISM_EVIDENCE_EXTRACTOR_MCP_URL=https://mcp.exa.ai/mcp
PRISM_EVIDENCE_EXTRACTOR_MCP_TOOL=web_fetch_exa
PRISM_EVIDENCE_EXTRACTOR_INPUT_MAPPER=exa_web_fetch
PRISM_EVIDENCE_EXTRACTOR_RESULT_MAPPER=exa_extract
PRISM_EVIDENCE_EXTRACTOR_TIMEOUT_SECONDS=30
PRISM_EVIDENCE_EXTRACTION_REQUIRED=1
```

Smoke should pass with non-zero evidence count before arming. Sentinel still applies issue
adequacy gates, so Exa output only resolves an issue when it is recent enough, topic-matched,
and satisfies the challenge type. When extraction is required, the selected source URL must
also fetch successfully and produce issue-supporting readable content; otherwise the issue
stays fail-closed.

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

1. Open `/connectors`.
2. Enter the connector admin token.
3. Save or inspect the Exa MCP HTTP connector passport.
4. Run smoke.
5. Confirm the smoke receipt shows transport/schema/mapper/fail-closed checks.
6. Arm the connector.
7. Return to `/dashboard` and confirm provider badges appear inline in Sentinel/tool reasoning rather than as a standalone Evidence Route card.
8. Run one validation with `ADVERSARIAL_RESOLUTION_MAX_ROUNDS=2` and `PRISM_EVIDENCE_EXTRACTION_REQUIRED=1`.
9. For Exa hosted MCP, confirm supported issue types move to `resolved` only when public report tool outcomes show provider `exa_mcp`, search tool `web_search_exa`, extractor provider `exa_contents`, extractor tool `web_fetch_exa`, non-null `source_content_hash`, and a redacted `source_excerpt`. If the verdict remains WARN, the capital gate may still require review even after blocking evidence gates clear.
10. For fail-closed mode, use the canonical guardrail trace or re-arm the market-only connector/malformed connector and confirm unsupported blockers remain unresolved if the connector fails or returns non-matching output.

## Public API smoke

```bash
curl -s -H "Authorization: Bearer $CONNECTOR_ADMIN_TOKEN" "$DASHBOARD_URL/api/connectors" | jq '.connectors[] | {id,name,armed,smoke_status,auth_configured,status_label}'
curl -s "$DASHBOARD_URL/api/public/stats" | jq .
curl -s "$DASHBOARD_URL/api/public/traces/$TRACE_ID/report" | jq '{trace_id, issue_ledger, receipt_verification}'
```

The connector response must not include bearer tokens or `auth_secret_ciphertext`.
