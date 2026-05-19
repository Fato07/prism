const DASHBOARD_ORIGIN = 'https://prism-dashboard-production-e6e3.up.railway.app';
const DOCS_ORIGIN = 'https://prism-docs-production.up.railway.app';

export const dynamic = 'force-static';

const BODY = `# Prism

> Validate-before-action receipts for money-moving AI agents. Prism currently focuses on prediction-market/trading-agent validation: a trader proposes an action, a different-family Sentinel challenges the reasoning and evidence, and a public Prism Report explains the verdict and capital gate.

Prism does not guarantee truth, profit, legal compliance, or perfect security. It provides provenance, independent adversarial review, evidence/source checks, public receipts, and fail-closed policy outcomes.

## Core links

- [Live dashboard](${DASHBOARD_ORIGIN}): public product surface.
- [Developer docs](${DOCS_ORIGIN}): quickstart, CLI, x402/MCP validation, public APIs, receipts, security model, and architecture.
- [Docs llms.txt](${DOCS_ORIGIN}/llms.txt): full LLM-oriented documentation index.
- [GitHub repository](https://github.com/Fato07/prism): source code and checked-in receipt fixtures.
- [Official demo](https://youtu.be/6gjfT9GchYo): founder-led Agora Agents submission video.
- [Companion showcase](https://youtu.be/ZmSStvqNgIo): visual explainer, not the official proof video.

## Public product routes

- [Stats](${DASHBOARD_ORIGIN}/stats): receipt-linked activity stats.
- [History](${DASHBOARD_ORIGIN}/history): public validation history.
- [Trust workspace](${DASHBOARD_ORIGIN}/dashboard): trader/sentinel trust surface.
- [Connector Passport](${DASHBOARD_ORIGIN}/connectors): MCP-first evidence source setup and smoke status.
- [Self-serve validation](${DASHBOARD_ORIGIN}/submit): x402 validation flow.
- [Calibration](${DASHBOARD_ORIGIN}/calibration): sentinel discrimination evidence.

## Public APIs

- [Stats API](${DASHBOARD_ORIGIN}/api/public/stats)
- [History API](${DASHBOARD_ORIGIN}/api/public/history)
- [Canonical URL-verified report](${DASHBOARD_ORIGIN}/api/public/traces/85d58b9c-f45f-4aa1-8b8a-7a4b1c1c8fea/report)
- [Canonical fail-closed report](${DASHBOARD_ORIGIN}/api/public/traces/74cead4a-5def-4cec-8cb2-b5294d739acb/report)

## Agent surface

- [Sentinel MCP endpoint](https://prism-sentinel-production.up.railway.app/mcp/): x402-protected MCP service. Keep the trailing slash.

For implementation details, prefer the docs site and its llms.txt index.
`;

export function GET(): Response {
  return new Response(BODY, {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
      'Cache-Control': 'public, max-age=3600, stale-while-revalidate=86400',
    },
  });
}
