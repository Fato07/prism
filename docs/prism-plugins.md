# Prism Tool Connectors

Prism Tool Connectors are the MCP-first integration layer for Prism's adversarial trust
runtime. They let agent builders bring their own tools, MCP servers, x402 services,
internal APIs, action systems, and policies while Prism keeps one consistent trust
contract: tool outputs become auditable artifacts, the sentinel challenges those
artifacts, unresolved issues are gated by policy, and final decisions become receipts.

This replaces the earlier mental model of "Prism has a native adapter for every data
provider." Native adapters can exist, but they are not the center of the product.

> Bring your own tools. Prism turns their outputs into adversarially audited reasoning
> receipts.

## Product hypothesis

Agent builders already organize capabilities as tools: MCP servers, x402-paid APIs,
custom internal endpoints, wallets, chain clients, search providers, and domain APIs.
Firecrawl, Exa, Tavily, and many similar services increasingly expose MCP tools of their
own. Prism should not duplicate every provider as a bespoke wrapper.

Prism's job is higher-level:

1. receive an agent trace or action claim;
2. identify trust issues in an issue ledger;
3. call the relevant tools only when a challenge needs resolution;
4. normalize tool outputs into evidence/action/verification artifacts;
5. adjudicate whether the issue is resolved, conceded, or still blocking;
6. emit a verdict and receipt other agents can query.

## Two MCP roles

Prism has two complementary MCP roles.

### 1. Prism as an MCP server

External agents call Prism to validate traces and query the trust state Prism currently
exposes. The x402-protected FastMCP endpoint mounted at `/mcp/` already exists;
read-only receipt inspection now includes redacted connector capabilities and issue ledgers.

Current MCP trust surface:

| Tool | Inputs | Output | Mode |
| --- | --- | --- | --- |
| `validate` | `trace_uri`, `trace_hash`, optional `on_chain_request_hash` | `ValidateMcpResult` with verdict score/label, IPFS CID, content hash, payment tx, optional Arc tx | Mutating: runs validation, pins/persists receipt, optionally anchors on Arc |
| `get_price` | none | x402 validation price, currency, settlement network | Read-only |
| `get_stats` | optional `hours` lookback | aggregate validation counts, score distribution, latency, on-chain anchors | Read-only |
| `get_calibration` | none | latest sentinel calibration gap and synthetic trace scores | Read-only |
| `get_tool_manifest` | none | redacted Prism MCP tools and connector capability flags | Read-only |
| `get_issue_ledger` | `trace_id` or `request_hash` | structured challenges, resolution attempts, rounds, metadata, unresolved counts | Read-only |
| `verify_receipt` | `response_uri`/`cid` or `trace_id`/`request_hash`, optional `content_hash_hex` | receipt verification checks against schema, content hash, and/or DB identity | Read-only |
| `explain_verdict` | `trace_id` or `request_hash` | deterministic verdict summary, active issue-ledger policy gates, latest resolution attempt per issue | Read-only |

Pricing policy for Prism's own MCP surface:

- free discovery/trust tools: `initialize`, `tools/list`, `get_price`, `get_stats`,
  `get_calibration`, `get_tool_manifest`, `get_issue_ledger`, `verify_receipt`, and
  `explain_verdict`;
- paid mutating tool: `validate`;
- future expensive read tools may become rate-limited or x402-priced, but receipt
  verification should stay free enough for other agents to trust Prism outputs.

HTTP smoke coverage for Prism's own MCP server starts a real local FastMCP HTTP
server and calls read-only trust tools over the network transport:

```bash
uv run pytest \
  apps/mcp/src/tests/test_mcp.py::TestHttpTrustToolSmoke::test_read_only_trust_tools_work_through_real_http_fastmcp_server \
  -q
```

Future tools should include:

- `submit_issue_response` or `propose_resolution`.

External callers should never be able to mark issues resolved directly. They can submit
responses or proposed resolutions; the sentinel remains responsible for adjudication.

### 2. Prism as an MCP client

Inside the adversarial resolution loop, Prism should call external tools exposed by MCP
servers: Firecrawl MCP, Exa MCP, Tavily MCP, internal research MCP servers, market data MCP
servers, chain verification tools, and company-specific tools.

```text
External agent → Prism MCP validate
                     ↓
              Sentinel issue ledger
                     ↓
         Prism calls external MCP tools
                     ↓
           normalized Prism artifacts
                     ↓
        resolution loop + policy gates
                     ↓
             verdict + receipt
```

This is the strategic plugin architecture.

## Non-goal

Prism is not Zapier for agents. A connector belongs in Prism only if it helps answer at
least one trust question:

1. What evidence did the agent rely on?
2. What action did the agent take?
3. Can the claim/action be verified independently?
4. What policy decides whether capital is allowed to move?

If a tool does not affect evidence, action receipts, verification, or policy, it should not
be a core Prism connector.

## Connector categories

### Evidence connectors

Evidence connectors provide source-linked context for open issues in the adversarial
resolution loop. Prism does not treat “any result returned” as resolution: normalized
evidence must pass an adequacy gate for the challenge type and required resolution before
an issue can move to `resolved`; otherwise the issue remains fail-closed.

Preferred form:

- MCP tools exposed by providers or internal systems.

Examples:

- Firecrawl MCP search/scrape tools;
- Exa MCP search tools;
- Tavily MCP search/research tools;
- Brave/Search MCP tools;
- Polymarket market metadata tools;
- sports/news/macro domain MCP tools;
- internal research/data warehouse MCP tools;
- x402-paid evidence APIs;
- custom webhook bridge when MCP is not available;
- direct native adapters as fallback/reference implementations.

### Action connectors

Action connectors capture what the agent did and produce action receipts.

Examples:

- Polymarket order placement or paper-trade receipt;
- Circle wallet transfer;
- Arc contract call;
- x402 payment;
- treasury park/unpark action;
- future off-chain action receipts such as Discord/X posts.

### Verification connectors

Verification connectors independently check whether evidence/action claims are true.

Examples:

- Arc / viem chain reads;
- Polymarket builder-trade reconciliation;
- IPFS CID resolution;
- x402 settlement verification;
- Circle transaction lookup;
- third-party market resolution status.

### Policy connectors

Policy connectors decide whether unresolved issues should block a verdict or trade.

Examples:

- `unresolved_blocker: reject`;
- `require_source_urls: true`;
- `sports_market_requires_current_injury_status: true`;
- `max_trade_size_fraction: 0.25`;
- `min_independent_sources: 2`;
- `allowed_tool_domains: [...]`.

## Runtime model

```text
Trader trace
→ Sentinel issue ledger
→ Tool selector chooses relevant connector only for unresolved issues
→ MCP/x402/webhook/direct tool call
→ Normalizer maps tool output into Prism artifact
→ Trader/system response resolves, revises, or concedes
→ Sentinel adjudicates final status
→ Policy gates score/label
→ Verdict + issue ledger + receipts are pinned/anchored/queryable
```

The core loop is always Prism-owned. Tool execution is pluggable.

## Connector Passport v1

Hosted Connector Passport v1 is now the concrete product shape behind the Tool
Connection Studio. It is not a broad marketplace; it is a controlled registry for
trust-relevant evidence connectors.

Current behavior:

1. Dashboard stores connector passports in `tool_connectors`.
2. Bearer tokens are encrypted server-side with `CONNECTOR_SECRETS_KEY` and are never
   returned through UI/API JSON, MCP tools, receipts, logs, or pinned artifacts.
3. `/dashboard` shows the active evidence route next to Sentinel reasoning, so connector
   state is part of the trust workspace rather than a standalone product marketplace.
4. `/connectors` is a compact workspace tools/settings route where an operator saves an
   MCP HTTP connector, chooses explicit input/result mappers, runs smoke, and arms the
   connector.
5. Smoke receipts record redacted checks: transport, tool reachability, schema, mapper,
   fail-closed behavior, cost cap, and parsed evidence count.
6. A connector can be armed only after smoke passes. A partial unique index enforces one
   armed evidence connector at a time.
7. During resolution, the sentinel reads the armed DB connector first. If none is armed,
   it falls back to `PRISM_EVIDENCE_PROVIDER`. If an armed connector is broken or its
   token cannot be decrypted, Prism fails closed instead of silently using a different
   evidence path.

Deployment env for hosted connector passports:

```bash
PRISM_EVIDENCE_DB_CONNECTORS=1
CONNECTOR_SECRETS_KEY=$(openssl rand -base64 32)
CONNECTOR_ADMIN_TOKEN=<operator-only connector admin token>
```

Hosted deployments should keep `CONNECTOR_ALLOW_PRIVATE_URLS=0` and
`CONNECTOR_ALLOW_HTTP_CONNECTORS=0` so smoke tests cannot SSRF private infrastructure.

Self-hosted/env-only mode remains available with `PRISM_EVIDENCE_DB_CONNECTORS=0`.

For live demo evidence without a third-party research provider, sentinel mounts
`/market-evidence-mcp/`, a free read-only FastMCP server with tool `search`. Configure it
with input mapper `prism_evidence_request` and result mapper `generic_search`. It calls the
Prism Polymarket gateway and only returns evidence for market-structure or explicit
market-status temporal challenges; source-quality, logic, generic stale-evidence, and other
unsupported issue types return no evidence and stay fail-closed.

For transport smoke only, sentinel also mounts `/demo-evidence-mcp/`. It returns one
`generic_search`-compatible artifact for Connector Passport smoke queries and otherwise
returns no evidence unless `PRISM_DEMO_EVIDENCE_ALLOW_RESOLUTION=1` is explicitly enabled.
Replace these hosted demo connectors with a production MCP research provider before relying
on broad evidence-tool resolution for capital movement.

## Connector priority

Use this priority order when integrating a new capability:

1. **MCP connector** — preferred. The provider or user already exposes a tool contract.
2. **x402 connector** — when the capability is paid per use and returns HTTP artifacts.
3. **Custom webhook connector** — when the user has an internal tool that is not MCP yet.
4. **Direct native adapter** — fallback for demos, simple self-hosting, or reference mappers.

Direct adapters are useful, but they should not become the main product surface.

## Plugin manifest direction

The future manifest should describe trust-relevant tools, not provider-specific code.

```yaml
tools:
  evidence:
    - id: firecrawl-search
      kind: evidence
      transport: mcp_http
      server_url_env: FIRECRAWL_MCP_URL
      tool_name: search
      result_mapper: firecrawl_search
      input_mapper: query_limit
      timeout_seconds: 30
      max_results: 5

    - id: internal-research
      kind: evidence
      transport: mcp_http
      server_url_env: INTERNAL_RESEARCH_MCP_URL
      tool_name: search_market_context
      result_mapper: generic_search
      input_mapper: query
      timeout_seconds: 20

    - id: parallel-paid-search
      kind: evidence
      transport: x402_http
      endpoint_env: PARALLEL_X402_SEARCH_URL
      result_mapper: parallel_search
      max_usdc: 0.02

    - id: fallback-brave
      kind: evidence
      transport: direct_adapter
      adapter: brave_search
      api_key_env: BRAVE_SEARCH_API_KEY

  verification:
    - id: arc-validation-registry
      kind: verification
      transport: direct_adapter
      adapter: viem_arc_validation_registry

policy:
  max_resolution_rounds: 2
  unresolved_blocker: reject
  unresolved_material: warn
  require_source_urls: true
```

Important: `result_mapper` is explicit. Prism should not guess arbitrary tool output shapes.

## Normalized artifacts

Prism should normalize all connector outputs before they enter the trust loop.

MVP artifact already exists:

```json
{
  "title": "Current source title",
  "url": "https://example.com/source",
  "snippet": "Quoted or extracted evidence snippet.",
  "provider": "firecrawl_mcp.search",
  "published_at": "2026-05-16T00:00:00Z",
  "retrieved_at": "2026-05-16T12:00:00Z",
  "confidence": 0.91
}
```

Longer-term artifacts:

- `EvidencePacket` — source, claim, quote/snippet, retrieval time, provider/tool provenance;
- `ActionReceipt` — action kind, actor, target, amount, tx/order ID, status;
- `VerificationReceipt` — independent check result and method;
- `PolicyDecision` — allowed/blocked/warned with rule IDs.

## Hosted vs self-hosted

### Self-hosted Prism

Self-hosted teams bring their own MCP servers, keys, wallets, and endpoints.

```yaml
tools:
  evidence:
    - id: firecrawl
      transport: mcp_http
      server_url_env: FIRECRAWL_MCP_URL
      tool_name: search
      result_mapper: firecrawl_search

    - id: company-market-data
      transport: mcp_http
      server_url_env: COMPANY_MARKET_DATA_MCP_URL
      tool_name: get_market_context
      result_mapper: generic_search
```

### Hosted Prism

Hosted Prism can manage selected connectors internally and charge via x402 per validation or
per evidence-resolution round.

```yaml
tools:
  evidence:
    - id: prism-managed-research
      transport: hosted_managed
      result_mapper: generic_search

billing:
  mode: x402
  price_per_validation_usdc: 0.01
  price_per_evidence_round_usdc: 0.002
```

## Current implementation status

The current implementation lives in `apps/sentinel/src/sentinel/evidence_tools.py`.
It now includes the MCP-first seam while preserving the earlier direct adapters as
fallback/reference implementations.

Current pieces:

- `tool_connectors` migration — Connector Passport v1 registry with one armed
  evidence connector per workspace.
- `/api/connectors` plus `/api/connectors/[id]/smoke` and `/arm` — redacted
  dashboard control plane for save → smoke → arm.
- `/market-evidence-mcp/` — read-only Polymarket gateway evidence MCP server for resolving
  market-structure/status issues without pretending to answer broader research questions.
- `/demo-evidence-mcp/` — smoke-only demo MCP evidence server mounted on sentinel for
  proving Connector Passport wiring before a production provider is available.
- Dashboard `Evidence tool route` card — shows active connector state beside Sentinel
  reasoning without exposing secrets.
- `/connectors` workspace tools/settings route — operator control plane for current
  passports, smoke receipts, auth configured state, and fail-closed armability.
- `evidence_provider_from_runtime()` — sentinel loader that prefers the armed DB
  connector and falls back to env-only providers when no DB connector is armed.
- `NoopEvidenceProvider` — safe default, no network calls.
- `StaticEvidenceProvider` — deterministic tests.
- `McpEvidenceProvider` — preferred MCP client connector for external tools.
- `EvidenceConnectorConfig` / `ToolConnectorManifest` — small Pydantic manifest models.
- explicit result mapper registry — `generic_search`, `firecrawl_search`, `exa_search`,
  `tavily_search`, `parallel_search`, `brave_search`, `custom_webhook`.
- `CustomWebhookEvidenceProvider` — BYO bridge; useful for wrapping MCP/internal tools.
- `ParallelSearchEvidenceProvider` — direct adapter fallback/reference mapper.
- `TavilySearchEvidenceProvider` — direct adapter fallback/reference mapper.
- `ExaSearchEvidenceProvider` — direct adapter fallback/reference mapper.
- `FirecrawlSearchEvidenceProvider` — direct adapter fallback/reference mapper.
- `BraveSearchEvidenceProvider` — direct adapter fallback/reference mapper.

These are not wasted work. They provide:

1. demo-ready fallback when an MCP server is not configured;
2. examples of normalizing provider output into Prism artifacts;
3. hosted-mode shortcuts;
4. test fixtures for result mappers.

Direct adapter env blocks remain available, but new integrations should prefer MCP first.

MCP evidence connector environment:

```bash
PRISM_EVIDENCE_PROVIDER=mcp
PRISM_EVIDENCE_MCP_URL=https://example.com/mcp/
PRISM_EVIDENCE_MCP_TOOL=search
PRISM_EVIDENCE_RESULT_MAPPER=generic_search
PRISM_EVIDENCE_MCP_INPUT_MAPPER=query
PRISM_EVIDENCE_MCP_AUTH_TOKEN=optional-bearer-token
PRISM_EVIDENCE_MCP_ALLOWED_TOOLS=search
PRISM_EVIDENCE_MCP_TIMEOUT_SECONDS=20
ADVERSARIAL_RESOLUTION_MAX_ROUNDS=2
```

Local HTTP smoke coverage starts a real FastMCP HTTP server and connects through
`McpEvidenceProvider(server_url=...)`, not the in-process test transport:

```bash
uv run pytest \
  apps/sentinel/src/tests/test_evidence_tools.py::test_mcp_evidence_provider_calls_real_http_fastmcp_server \
  -q
```

## Ralph implementation roadmap

### Phase 1 — Docs and strategy

- Reframe Prism Plugins as MCP-first Tool Connectors.
- Update architecture docs to show Prism as both MCP server and MCP client.
- Mark native adapters as fallback/reference, not the strategic center.

### Phase 2 — Manifest and MCP evidence provider

- Define a small manifest/config schema for connector declarations.
- Add `McpEvidenceProvider`:
  - `server_url_env`;
  - `tool_name`;
  - `result_mapper`;
  - `input_mapper` (`query`, `query_limit`, `query_max_results`, `q_count`,
    `prism_evidence_request`);
  - auth headers or token env refs;
  - timeout/budget fields;
  - explicit tool allowlist;
  - no secrets in logs, receipts, or pinned artifacts;
  - fail-closed behavior.
- Test against a fake in-process FastMCP server and a local HTTP FastMCP server.

### Phase 3 — Result mappers

- Extract mapper functions from the direct adapters:
  - `generic_search`;
  - `firecrawl_search`;
  - `exa_search`;
  - `tavily_search`;
  - `parallel_search`;
  - `brave_search`.
- Keep direct adapters as wrappers around those mappers where practical.

### Phase 4 — Resolution-loop integration

- Add env/config support for `PRISM_EVIDENCE_PROVIDER=mcp`.
- Ensure unresolved blockers still fail closed if the MCP tool errors or returns unusable
  output.
- Add integration coverage proving MCP evidence can resolve a blocker and MCP failure
  leaves it unresolved.

### Phase 5 — Queryable Prism surface

Extend Prism's own MCP server with more agent-readable trust tools:

- `submit_issue_response` / `propose_resolution`.

Already implemented in this phase:

- `get_tool_manifest`;
- `get_issue_ledger`;
- `verify_receipt`;
- `explain_verdict`.

## Decision

Proceed with an MCP-first architecture:

```text
Prism Core = adversarial trust semantics
Tool Connectors = MCP/x402/webhook/direct ways to gather evidence/actions/verifications
Normalizers = explicit mappers from tool output to Prism artifacts
Receipts = queryable proof for agents and humans
```

Confidence: **9/10** for the strategic pivot, **9.3/10** for the hybrid plan of
MCP-first plus native fallback/reference adapters.
