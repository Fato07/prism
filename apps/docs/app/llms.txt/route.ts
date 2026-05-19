import { llms } from 'fumadocs-core/source/llms';

import { source } from '@/lib/source';

const DOCS_ORIGIN = 'https://prism-docs-production.up.railway.app';
const DASHBOARD_ORIGIN = 'https://prism-dashboard-production-e6e3.up.railway.app';

export const dynamic = 'force-static';

function absolutizeDocsLinks(markdown: string): string {
  return markdown.replace(/\]\((\/[^)]+)\)/g, `](${DOCS_ORIGIN}$1)`);
}

function buildLlmsTxt(): string {
  const docsIndex = absolutizeDocsLinks(llms(source).index());

  return `# Prism

> MCP-first adversarial validation for money-moving AI agents. A trader produces a structured reasoning trace; a different-family Sentinel challenges evidence, sources, and risk before capital moves.

Prism's current wedge is prediction-market/trading-agent validation. The broader product direction is validate-before-action receipts for money-moving agents: verifiable reasoning, issue ledgers, evidence provenance, x402 payment receipts, and Arc/ERC-8004 validation references where anchored.

Prism does not guarantee truth, profit, legal compliance, or perfect security. It provides provenance, independent adversarial review, evidence/source checks, public receipts, and fail-closed policy outcomes.

## Core surfaces

- [Live dashboard](${DASHBOARD_ORIGIN}): public product surface for traces, stats, reports, connector status, and self-serve validation.
- [Developer docs](${DOCS_ORIGIN}): quickstart, CLI, x402/MCP validation, public APIs, receipts, security model, and architecture.
- [GitHub repository](https://github.com/Fato07/prism): source code and checked-in receipt fixtures.
- [Official demo](https://youtu.be/6gjfT9GchYo): founder-led Agora Agents submission video.
- [Companion showcase](https://youtu.be/ZmSStvqNgIo): visual explainer, not the official proof video.

## Agent and API surfaces

- [Sentinel MCP endpoint](https://prism-sentinel-production.up.railway.app/mcp/): x402-protected MCP service. Keep the trailing slash.
- [Public stats API](${DASHBOARD_ORIGIN}/api/public/stats): receipt-linked aggregate activity stats.
- [Public history API](${DASHBOARD_ORIGIN}/api/public/history): recent public traces and validations.
- [Canonical URL-verified report](${DASHBOARD_ORIGIN}/api/public/traces/85d58b9c-f45f-4aa1-8b8a-7a4b1c1c8fea/report): Exa MCP search/fetch evidence receipts.
- [Canonical fail-closed report](${DASHBOARD_ORIGIN}/api/public/traces/74cead4a-5def-4cec-8cb2-b5294d739acb/report): unresolved evidence blockers remain blocked.

## MCP tools

The Sentinel MCP server exposes validation and read-only trust tools, including \`validate\`, \`verify_receipt\`, \`get_issue_ledger\`, \`explain_verdict\`, \`get_tool_manifest\`, \`get_stats\`, \`get_calibration\`, and \`get_price\`.

## Documentation index

${docsIndex}
`;
}

export function GET(): Response {
  return new Response(buildLlmsTxt(), {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
      'Cache-Control': 'public, max-age=3600, stale-while-revalidate=86400',
    },
  });
}
