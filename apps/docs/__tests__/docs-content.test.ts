import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

const root = process.cwd();

function read(relativePath: string): string {
  return readFileSync(join(root, relativePath), 'utf8');
}

// Shared banned-phrase set (VAL-CROSS-009). Each bigram is checked
// case-insensitively. The phrases are crafted so that disclaimers like
// "Prism does not guarantee complete security" are still permitted.
const BANNED_PHRASES = [
  'guarantees truth',
  'guarantees profit',
  'guarantees security',
  'guarantees complete security',
  'guarantees legal compliance',
  'guarantees perfect security',
  'proves correctness',
  'always safe',
  'legally compliant',
];

describe('Prism docs content', () => {
  it('keeps sidebar navigation focused and grouped', () => {
    const meta = JSON.parse(read('content/docs/meta.json')) as { pages: string[] };

    expect(meta.pages).toContain('---Start---');
    expect(meta.pages).toContain('---Use Prism---');
    expect(meta.pages).toContain('---Verify---');
    expect(meta.pages).toContain('quickstart');
    expect(meta.pages).toContain('cli');
    expect(meta.pages).toContain('x402-mcp-validation');
    expect(meta.pages).toContain('receipts');
    expect(meta.pages).toContain('calibration');
    expect(meta.pages).toContain('security');
    expect(meta.pages).not.toContain('api-reference');
  });

  it('renders Prism brand without a docs footer', () => {
    const layout = read('lib/layout.shared.tsx');
    const docsPage = read('app/docs/[[...slug]]/page.tsx');
    const docsLayout = read('app/docs/layout.tsx');
    const home = read('app/page.tsx');

    expect(layout).toContain('<PrismWordmark />');
    expect(docsPage).toContain('aria-label="Prism documentation home"');
    expect(docsPage).toContain('<PrismWordmark />');
    expect(docsLayout).not.toContain('SiteFooter');
    expect(home).not.toContain('SiteFooter');
  });

  it('does not publish personal Circle login details', () => {
    const quickstart = read('content/docs/quickstart.mdx');
    const troubleshooting = read('content/docs/troubleshooting.mdx');

    const combined = `${quickstart}\n${troubleshooting}`;

    expect(combined).not.toMatch(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i);
    expect(combined).toContain('YOUR_CIRCLE_EMAIL');
  });

  it('documents the canonical MCP endpoint with trailing slash and trust tools', () => {
    const page = read('content/docs/x402-mcp-validation.mdx');

    expect(page).toContain('https://prism-sentinel-production.up.railway.app/mcp/');
    expect(page).toContain('trailing slash');
    expect(page).toContain('validate');
    expect(page).toContain('verify_receipt');
    expect(page).toContain('get_issue_ledger');
    expect(page).toContain('explain_verdict');
    expect(page).toContain('get_tool_manifest');
  });

  it('serves an llms.txt route with public Prism context', () => {
    const route = read('app/llms.txt/route.ts');
    const layout = read('app/layout.tsx');

    expect(route).toContain("fumadocs-core/source/llms");
    expect(route).toContain('https://prism-docs-production.up.railway.app');
    expect(route).toContain('https://prism-dashboard-production-e6e3.up.railway.app');
    expect(route).toContain('https://prism-sentinel-production.up.railway.app/mcp/');
    expect(route).toContain('Prism does not guarantee truth, profit, legal compliance, or perfect security');
    expect(route).toContain('Canonical URL-verified report');
    expect(route).not.toContain('X-PAYMENT');
    expect(layout).toContain("metadataBase: new URL('https://prism-docs-production.up.railway.app')");
  });

  it('keeps paid validation explicit and capped', () => {
    const cli = read('content/docs/cli.mdx');
    const security = read('content/docs/security.mdx');

    expect(cli).toContain('--max-amount-usdc 0.01');
    expect(security.toLowerCase()).toContain('raw private keys');
    expect(security).toContain('Dry-run commands are default');
  });

  it('documents the canonical paid CLI receipt without payment header leakage', () => {
    const receipt = read('../../docs/demos/cli-paid-validation-20260516T214837Z.json');
    const receiptDocs = read('content/docs/receipts.mdx');

    expect(receipt).toContain('"mode": "paid"');
    expect(receipt).toContain('"payment_tx_hash"');
    expect(receipt).not.toContain('X-PAYMENT');
    expect(receiptDocs).toContain('cli-paid-validation-20260516T214837Z');
    expect(receiptDocs).toContain('Canonical judge receipt bundle');
    expect(receiptDocs).toContain('0xd6ab0cbba99dfa1162ab24ccf35c9e9544c1bb64a550a0e349e8033ebd4f43e1');
    expect(receiptDocs).toContain('Prism CLI never reads private keys');
  });

  it('documents calibration evidence without overclaiming a production gold set', () => {
    const calibration = read('content/docs/calibration.mdx');

    expect(calibration).toContain('45');
    expect(calibration).toContain('60');
    expect(calibration).toContain('Real harvested Trading-R1 traces');
    expect(calibration).toContain('Raw calibration rows are not committed');
    expect(calibration).toContain('What it does not claim yet');
    expect(calibration).toContain('production-grade LLM-as-judge agreement');
    expect(calibration).toContain('https://prism-dashboard-production-e6e3.up.railway.app/calibration');
  });

  it('ships an OpenAPI source for public dashboard APIs only', () => {
    const openapi = read('openapi/prism-public-api.yaml');

    expect(openapi).toContain('/api/public/stats');
    expect(openapi).toContain('/api/public/history');
    expect(openapi).toContain('/api/public/traces/{id}/report');
    expect(openapi).not.toContain('/mcp/');
  });
});

describe('Verification guarantees page', () => {
  it('verification-guarantees page is registered in meta.json under Verify group', () => {
    const meta = JSON.parse(read('content/docs/meta.json')) as { pages: string[] };

    expect(meta.pages).toContain('verification-guarantees');

    const verifyIdx = meta.pages.indexOf('---Verify---');
    const guIdx = meta.pages.indexOf('verification-guarantees');
    const refIdx = meta.pages.indexOf('---Reference---');

    expect(verifyIdx).not.toBe(-1);
    expect(guIdx).not.toBe(-1);
    expect(guIdx).toBeGreaterThan(verifyIdx);
    if (refIdx !== -1) {
      expect(guIdx).toBeLessThan(refIdx);
    }
  });

  it('verification-guarantees.mdx contains both required headings in correct order', () => {
    const body = read('content/docs/verification-guarantees.mdx');

    expect(body).toMatch(/##\s+What Prism guarantees/i);
    expect(body).toMatch(/##\s+What Prism does NOT guarantee/i);

    const guIdx = body.indexOf('What Prism guarantees');
    const notIdx = body.indexOf('What Prism does NOT guarantee');

    expect(guIdx).toBeGreaterThan(-1);
    expect(notIdx).toBeGreaterThan(-1);
    expect(guIdx).toBeLessThan(notIdx);
  });

  it('verification-guarantees.mdx enumerates all eight Prism guarantees', () => {
    const body = read('content/docs/verification-guarantees.mdx');

    // 8 guarantees per VAL-GUARANTEES-005
    expect(body).toMatch(/provenance/i);
    expect(body).toMatch(/independent adversarial review/i);
    expect(body).toMatch(/source\s+URL\s+verification/i);
    expect(body).toMatch(/source\s+content\s+hashes/i);
    expect(body).toMatch(/issue\s*[- ]?ledger\s+transparency/i);
    expect(body).toMatch(/x402\s+receipts/i);
    expect(body).toMatch(/\bArc\b/);
    expect(body).toMatch(/ERC[-\s]?8004/);
    expect(body).toMatch(/fail[-\s]?closed\s+capital\s+gate/i);
  });

  it('verification-guarantees.mdx enumerates all five NOT-guarantees', () => {
    const body = read('content/docs/verification-guarantees.mdx');

    // 5 NOT-guarantees per VAL-GUARANTEES-007 — each as a distinct disclaimer
    expect(body).toMatch(/\bTruth\b/);
    expect(body).toMatch(/\bProfit\b/);
    expect(body).toMatch(/complete\s+security/i);
    expect(body).toMatch(/legal\s+compliance/i);
    expect(body).toMatch(/PASS.*not.*instruction.*execute/i);
  });

  it('verification-guarantees.mdx links to canonical examples', () => {
    const body = read('content/docs/verification-guarantees.mdx');

    // Canonical PASS trace URL
    expect(body).toContain('/trace/d6cdd60f-f5e0-43ab-ba2d-7dcab76a8e24');
    // Canonical CLI x402 receipt
    expect(body).toContain('cli-paid-validation-20260516T214837Z');
    // Cross-links to security and receipts pages
    expect(body).toMatch(/\/docs\/security/);
    expect(body).toMatch(/\/docs\/receipts/);
  });

  it('verification-guarantees.mdx contains zero banned overclaim phrases', () => {
    const body = read('content/docs/verification-guarantees.mdx').toLowerCase();

    for (const phrase of BANNED_PHRASES) {
      expect(body).not.toContain(phrase);
    }
  });
});
