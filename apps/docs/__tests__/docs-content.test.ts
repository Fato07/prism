import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

const root = process.cwd();

function read(relativePath: string): string {
  return readFileSync(join(root, relativePath), 'utf8');
}

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
    expect(meta.pages).toContain('security');
    expect(meta.pages).not.toContain('api-reference');
  });

  it('renders Prism brand and footer links across docs surfaces', () => {
    const layout = read('lib/layout.shared.tsx');
    const docsPage = read('app/docs/[[...slug]]/page.tsx');
    const footer = read('components/site-footer.tsx');
    const home = read('app/page.tsx');

    expect(layout).toContain('<PrismWordmark />');
    expect(docsPage).toContain('aria-label="Prism documentation home"');
    expect(docsPage).toContain('<PrismWordmark />');
    expect(footer).toContain('Quickstart');
    expect(footer).toContain('Public APIs');
    expect(home).toContain('<SiteFooter />');
  });

  it('does not publish personal Circle login details', () => {
    const quickstart = read('content/docs/quickstart.mdx');
    const troubleshooting = read('content/docs/troubleshooting.mdx');

    const combined = `${quickstart}\n${troubleshooting}`;

    expect(combined).not.toMatch(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i);
    expect(combined).toContain('YOUR_CIRCLE_EMAIL');
  });

  it('documents the canonical MCP endpoint with trailing slash', () => {
    const page = read('content/docs/x402-mcp-validation.mdx');

    expect(page).toContain('https://prism-sentinel-production.up.railway.app/mcp/');
    expect(page).toContain('trailing slash');
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
  });

  it('ships an OpenAPI source for public dashboard APIs only', () => {
    const openapi = read('openapi/prism-public-api.yaml');

    expect(openapi).toContain('/api/public/stats');
    expect(openapi).toContain('/api/public/history');
    expect(openapi).toContain('/api/public/traces/{id}/report');
    expect(openapi).not.toContain('/mcp/');
  });
});
