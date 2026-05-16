# Prism Plugins

Prism Plugins are the agent-first integration layer for Prism's adversarial trust loop.
They let teams bring their own tools, data providers, action systems, and policies while
Prism keeps one consistent validation contract: evidence and actions become auditable
artifacts, the sentinel turns concerns into an issue ledger, and final verdicts are
anchored as reasoning receipts.

## Product hypothesis

Agent builders do not all use the same research stack. Some use web search APIs, some use
MCP tools, some use internal data warehouses, some pay x402 services, and some need domain
APIs. Prism should not force one provider. Prism should normalize those tool outputs into
trust-relevant artifacts that can be challenged, resolved, and verified.

> Bring your own tools. Prism turns their outputs into adversarially audited reasoning
> receipts.

## Non-goal

Prism is not trying to become Zapier for agents. A plugin belongs in Prism only if it helps
answer at least one trust question:

1. What evidence did the agent rely on?
2. What action did the agent take?
3. Can the claim/action be verified independently?
4. What policy decides whether capital is allowed to move?

## Plugin categories

### Evidence plugins

Evidence plugins provide current, source-linked context for open issues in the adversarial
resolution loop.

Examples:
- `prism.parallel_search` — Parallel Search API with BYO Parallel API key.
- `prism.parallel_x402` — future x402-paid search/research via Circle-compatible services.
- `prism.brave_search` — web/news search with BYO Brave API key.
- `prism.tavily` — agent-oriented web retrieval.
- `prism.exa` — semantic/neural research search.
- `prism.firecrawl` — scrape/extract specific pages after search.
- `prism.polymarket_gamma` — market metadata, tags, end dates, resolution status.
- `custom.webhook` — user-owned HTTP endpoint wrapping MCP tools, internal APIs, or any
  provider Prism does not natively know about.

### Action plugins

Action plugins capture what the agent did and produce action receipts.

Examples:
- `prism.polymarket_order`
- `prism.circle_wallet_transfer`
- `prism.arc_contract_call`
- `prism.x402_payment`
- `prism.treasury_park_unpark`

### Verification plugins

Verification plugins check whether claims and actions are independently true.

Examples:
- Arc / viem chain reads
- Polymarket builder-trade reconciliation
- IPFS CID resolution
- x402 settlement verification
- Circle transaction lookup

### Policy plugins

Policy plugins decide whether unresolved issues should block a verdict or trade.

Examples:
- `unresolved_blocker: reject`
- `require_source_urls: true`
- `sports_market_requires_current_injury_status: true`
- `max_trade_size_fraction: 0.25`
- `min_independent_sources: 2`

## Runtime model

```text
Trader trace
→ Sentinel issue ledger
→ If an issue needs evidence/action verification:
    plugin is called
→ challenge is resolved, answered, or conceded
→ sentinel applies policy/scoring caps
→ verdict + issue ledger + receipts are pinned/anchored
```

The core loop is always Prism-owned. Provider selection is pluggable.

## Hosted vs self-hosted

### Self-hosted Prism

Self-hosted teams bring their own keys, tools, wallets, and endpoints.

```yaml
evidence:
  providers:
    - type: custom_webhook
      url_env: PRISM_EVIDENCE_WEBHOOK_URL
      bearer_token_env: PRISM_EVIDENCE_WEBHOOK_BEARER_TOKEN
    - type: parallel_search
      api_key_env: PARALLEL_API_KEY
    - type: brave_search
      api_key_env: BRAVE_SEARCH_API_KEY

policy:
  max_resolution_rounds: 2
  unresolved_blocker: reject
  unresolved_material: warn
  require_source_urls: true
```

### Hosted Prism

Hosted Prism can manage selected providers internally and charge via x402 per validation or
per evidence-resolution round.

```yaml
evidence:
  providers:
    - type: prism_managed_parallel_x402
    - type: prism_managed_brave_search

billing:
  mode: x402
  price_per_validation_usdc: 0.01
  price_per_evidence_round_usdc: 0.002
```

## Minimal evidence plugin contract

Evidence plugins receive a targeted request for one open challenge and return normalized
results.

Request:

```json
{
  "market_question": "Will LeBron break the scoring record during the Feb 7 game vs. OKC?",
  "query": "Will LeBron break the scoring record during the Feb 7 game vs. OKC? latest current evidence status date",
  "max_results": 5,
  "challenge": {
    "id": "sys-temporal-stale-evidence",
    "type": "temporal",
    "severity": "blocking",
    "question": "Evidence is stale.",
    "required_resolution": "Retrieve current evidence or revise to HOLD.",
    "blocking_pass": true,
    "claim_ref": "evidence[0]",
    "resolution_status": "open"
  }
}
```

Response:

```json
{
  "results": [
    {
      "title": "Current source title",
      "url": "https://example.com/source",
      "snippet": "Quoted or extracted evidence snippet.",
      "provider": "custom_webhook",
      "published_at": "2026-05-16T00:00:00Z",
      "retrieved_at": "2026-05-16T12:00:00Z",
      "confidence": 0.91
    }
  ]
}
```

## Current implementation

The first plugin seam lives in `apps/sentinel/src/sentinel/evidence_tools.py`:

- `NoopEvidenceProvider` — default, no network calls.
- `StaticEvidenceProvider` — deterministic tests.
- `CustomWebhookEvidenceProvider` — BYO HTTP endpoint.
- `ParallelSearchEvidenceProvider` — native Parallel Search API adapter.
- `BraveSearchEvidenceProvider` — native Brave Search Web Search API adapter.

Custom webhook environment:

```bash
PRISM_EVIDENCE_PROVIDER=custom_webhook
PRISM_EVIDENCE_WEBHOOK_URL=https://your-service.example/evidence
PRISM_EVIDENCE_WEBHOOK_BEARER_TOKEN=optional-secret
PRISM_EVIDENCE_WEBHOOK_TIMEOUT_SECONDS=20
ADVERSARIAL_RESOLUTION_MAX_ROUNDS=2
```

Parallel Search environment:

```bash
PRISM_EVIDENCE_PROVIDER=parallel_search
PARALLEL_API_KEY=your-parallel-api-key
PARALLEL_SEARCH_MODE=advanced             # optional: basic or advanced
PARALLEL_SEARCH_LOCATION=us               # optional: ISO country code
PARALLEL_SEARCH_MAX_CHARS_TOTAL=6000      # optional
PARALLEL_SEARCH_TIMEOUT_SECONDS=30        # optional
ADVERSARIAL_RESOLUTION_MAX_ROUNDS=2
```

Brave Search environment:

```bash
PRISM_EVIDENCE_PROVIDER=brave_search
BRAVE_SEARCH_API_KEY=your-brave-search-key
BRAVE_SEARCH_COUNTRY=US              # optional
BRAVE_SEARCH_LANG=en                 # optional
BRAVE_SEARCH_FRESHNESS=pm            # optional: Brave-supported freshness value
BRAVE_SEARCH_TIMEOUT_SECONDS=20      # optional
ADVERSARIAL_RESOLUTION_MAX_ROUNDS=2
```

This is intentionally small and reversible. Native adapters for Parallel x402, Tavily, Exa,
Firecrawl, and domain APIs can be added behind the same contract.
