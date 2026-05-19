import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';
import Ajv2020 from 'ajv/dist/2020';
import addFormats from 'ajv-formats';

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

// ---------------------------------------------------------------------------
// Prism Report v0 Schema
// ---------------------------------------------------------------------------

const FORBIDDEN_SCHEMA_SUBSTRINGS = [
  'raw_prompt',
  'prompt_text',
  'chain_of_thought',
  'chain-of-thought',
  'scratchpad',
  'scraped_page',
  'raw_html',
  'page_html',
  'api_key',
  'apikey',
  'private_key',
  'bearer_token',
  'authorization_header',
  'cookie_jar',
];

const TOP_LEVEL_REQUIRED = [
  'schema_version',
  'generated_at',
  'trace',
  'action_intent',
  'validator',
  'verdict',
  'reasoning_metrics',
  'readiness',
  'warnings',
  'issue_ledger',
  'evidence_receipts',
  'capital_gate',
  'payment_receipts',
  'onchain_receipts',
  'content_hashes',
];

function resolveRef(schema: Record<string, unknown>, ref: string): Record<string, unknown> | null {
  if (!ref.startsWith('#/')) return null;
  const parts = ref.replace('#/', '').split('/');
  let current: unknown = schema;
  for (const part of parts) {
    if (current && typeof current === 'object') {
      current = (current as Record<string, unknown>)[part];
    } else {
      return null;
    }
  }
  return (current && typeof current === 'object') ? current as Record<string, unknown> : null;
}

describe('Prism Report v0 Schema', () => {
  const schemaPath = '../../docs/protocol/prism-report-v0.schema.json';

  function loadSchema(): Record<string, unknown> {
    return JSON.parse(read(schemaPath)) as Record<string, unknown>;
  }

  it('prism-report-v0 schema file exists at docs/protocol/', () => {
    expect(() => read(schemaPath)).not.toThrow();
  });

  it('prism-report-v0 schema declares Draft 2020-12 dialect', () => {
    const schema = loadSchema();
    expect(schema.$schema).toBe('https://json-schema.org/draft/2020-12/schema');
  });

  it('prism-report-v0 schema has stable $id containing prism-report-v0', () => {
    const schema = loadSchema();
    const id = schema.$id;
    expect(id).toBeTruthy();
    expect(String(id)).toMatch(/prism-report-v0/);
  });

  it('prism-report-v0 schema compiles cleanly with ajv 2020 + ajv-formats', () => {
    const schema = loadSchema();
    const ajv = new Ajv2020({ strict: true, allErrors: true });
    addFormats(ajv);
    const validate = ajv.compile(schema);
    expect(typeof validate).toBe('function');
  });

  it('prism-report-v0 schema requires 15 top-level fields', () => {
    const schema = loadSchema();
    expect(schema.type).toBe('object');
    const required = schema.required as string[];
    expect(Array.isArray(required)).toBe(true);

    for (const field of TOP_LEVEL_REQUIRED) {
      expect(required).toContain(field);
    }
  });

  it('prism-report-v0 schema declares additionalProperties:false at top level and in major subschemas', () => {
    const schema = loadSchema();

    // Top-level closure
    expect(schema.additionalProperties).toBe(false);

    const properties = schema.properties as Record<string, unknown>;
    const subschemaKeys = ['trace', 'validator', 'verdict', 'capital_gate', 'onchain_receipts', 'content_hashes'];

    for (const key of subschemaKeys) {
      const subschema = properties[key] as Record<string, unknown> | undefined;
      expect(subschema, `subschema "${key}" should exist`).toBeTruthy();
      expect(
        subschema!.additionalProperties,
        `subschema "${key}" should have additionalProperties: false`,
      ).toBe(false);
    }

    // issue_ledger items
    const issueLedger = properties['issue_ledger'] as Record<string, unknown>;
    expect(issueLedger).toBeTruthy();
    const ilItems = issueLedger.items as Record<string, unknown> | undefined;
    if (ilItems) {
      expect(ilItems.additionalProperties).toBe(false);
    }
  });

  it('prism-report-v0 schema does NOT have a top-level validation property', () => {
    const schema = loadSchema();
    const properties = schema.properties as Record<string, unknown>;
    expect(properties.validation).toBeUndefined();

    const required = schema.required as string[];
    expect(required.includes('validation')).toBe(false);
  });

  it('prism-report-v0 action_intent.oneOf has 4 branches matching reserved + implemented types', () => {
    const schema = loadSchema();
    const properties = schema.properties as Record<string, unknown>;
    const actionIntent = properties['action_intent'] as Record<string, unknown>;
    expect(actionIntent).toBeTruthy();

    const oneOf = actionIntent.oneOf as Array<Record<string, unknown>>;
    expect(Array.isArray(oneOf)).toBe(true);
    expect(oneOf.length).toBeGreaterThanOrEqual(4);

    const expectedTypes = new Set(['prediction_market', 'payment_batch', 'defi_rebalance', 'treasury_move']);
    const foundTypes = new Set<string>();

    for (const branch of oneOf) {
      // Resolve $ref if present
      const resolved = branch.$ref
        ? resolveRef(schema, String(branch.$ref))
        : branch;
      expect(resolved, `branch $ref ${branch.$ref ?? '(inline)'} should resolve`).toBeTruthy();

      const props = resolved!.properties as Record<string, unknown> | undefined;
      expect(props, 'resolved branch should have properties').toBeTruthy();

      const typeProp = props!['type'] as Record<string, unknown> | undefined;
      expect(typeProp, 'resolved branch should have a "type" property').toBeTruthy();

      const constVal = typeProp!.const as string;
      expect(constVal).toBeTruthy();
      foundTypes.add(constVal);

      const branchRequired = resolved!.required as string[] | undefined;
      expect(branchRequired, `branch "${constVal}" should have required`).toBeTruthy();
      expect(branchRequired!.includes('type'), `branch "${constVal}" should require type`).toBe(true);

      if (constVal === 'prediction_market') {
        // STRICT branch
        expect(branchRequired!.length).toBeGreaterThanOrEqual(3); // type + at least 2 more
      } else {
        // RESERVED branches — only "type" is required
        expect(branchRequired!.length).toBe(1);
      }
    }

    expect(foundTypes).toEqual(expectedTypes);
  });

  it('prism-report-v0 payment_receipts.items.oneOf has 3 branches matching x402+mpp+ap2', () => {
    const schema = loadSchema();
    const properties = schema.properties as Record<string, unknown>;
    const paymentReceipts = properties['payment_receipts'] as Record<string, unknown>;
    expect(paymentReceipts).toBeTruthy();
    expect(paymentReceipts.type).toBe('array');

    const items = paymentReceipts.items as Record<string, unknown>;
    expect(items).toBeTruthy();

    const oneOf = items.oneOf as Array<Record<string, unknown>>;
    expect(Array.isArray(oneOf)).toBe(true);
    expect(oneOf.length).toBeGreaterThanOrEqual(3);

    const expectedProtocols = new Set(['x402', 'mpp', 'ap2']);
    const foundProtocols = new Set<string>();

    for (const branch of oneOf) {
      const resolved = branch.$ref
        ? resolveRef(schema, String(branch.$ref))
        : branch;
      expect(resolved, `branch $ref ${branch.$ref ?? '(inline)'} should resolve`).toBeTruthy();

      const props = resolved!.properties as Record<string, unknown> | undefined;
      expect(props, 'resolved branch should have properties').toBeTruthy();

      const protocolProp = props!['protocol'] as Record<string, unknown> | undefined;
      expect(protocolProp, 'resolved branch should have a "protocol" property').toBeTruthy();

      const constVal = protocolProp!.const as string;
      expect(constVal).toBeTruthy();
      foundProtocols.add(constVal);

      const branchRequired = resolved!.required as string[] | undefined;
      expect(branchRequired, `branch "${constVal}" should have required`).toBeTruthy();
      expect(branchRequired!.includes('protocol'), `branch "${constVal}" should require protocol`).toBe(true);

      if (constVal === 'x402') {
        // STRICT branch
        expect(branchRequired!.length).toBeGreaterThanOrEqual(4); // protocol + at least 3 more
      }
      // mpp, ap2 — reserved, only protocol required here (may have receipt_header_hash optional)
    }

    expect(foundProtocols).toEqual(expectedProtocols);
  });

  it('prism-report-v0 capital_gate.status enum matches dashboard exactly', () => {
    const schema = loadSchema();
    const properties = schema.properties as Record<string, unknown>;
    const capitalGate = properties['capital_gate'] as Record<string, unknown>;
    expect(capitalGate).toBeTruthy();

    const cgRequired = capitalGate.required as string[];
    expect(cgRequired).toContain('status');

    const cgProps = capitalGate.properties as Record<string, unknown>;
    const statusProp = cgProps['status'] as Record<string, unknown>;
    expect(statusProp).toBeTruthy();

    const statusEnum = statusProp.enum as string[];
    const expected = ['PENDING_VALIDATION', 'BLOCK', 'REVIEW', 'ALLOW_PAPER', 'ENDORSE'];
    expect(new Set(statusEnum)).toEqual(new Set(expected));
  });

  it('prism-report-v0 verdict.verdict_label enum is REJECT|WARN|PASS|ENDORSE', () => {
    const schema = loadSchema();
    const properties = schema.properties as Record<string, unknown>;
    const verdict = properties['verdict'] as Record<string, unknown>;
    expect(verdict).toBeTruthy();

    const vProps = verdict.properties as Record<string, unknown>;
    const labelProp = vProps['verdict_label'] as Record<string, unknown>;
    expect(labelProp).toBeTruthy();

    const labelEnum = labelProp.enum as string[];
    const expected = ['REJECT', 'WARN', 'PASS', 'ENDORSE'];
    expect(new Set(labelEnum)).toEqual(new Set(expected));
  });

  it('prism-report-v0 verdict has raw_verdict_score and capped_verdict_score (int 0..100)', () => {
    const schema = loadSchema();
    const properties = schema.properties as Record<string, unknown>;
    const verdict = properties['verdict'] as Record<string, unknown>;
    expect(verdict).toBeTruthy();

    const vRequired = verdict.required as string[];
    expect(vRequired).toContain('verdict_score');
    expect(vRequired).toContain('verdict_label');

    const vProps = verdict.properties as Record<string, unknown>;

    // verdict_score is integer 0..100
    const scoreProp = vProps['verdict_score'] as Record<string, unknown>;
    expect(scoreProp).toBeTruthy();
    expect(scoreProp.type).toBe('integer');
    expect(scoreProp.minimum).toBe(0);
    expect(scoreProp.maximum).toBe(100);

    // raw_verdict_score
    const rawScore = vProps['raw_verdict_score'] as Record<string, unknown>;
    expect(rawScore).toBeTruthy();
    expect(rawScore.type).toBe('integer');
    expect(rawScore.minimum).toBe(0);
    expect(rawScore.maximum).toBe(100);

    // capped_verdict_score
    const cappedScore = vProps['capped_verdict_score'] as Record<string, unknown>;
    expect(cappedScore).toBeTruthy();
    expect(cappedScore.type).toBe('integer');
    expect(cappedScore.minimum).toBe(0);
    expect(cappedScore.maximum).toBe(100);
  });

  it('prism-report-v0 canonical field names are present with correct patterns', () => {
    const schema = loadSchema();
    const properties = schema.properties as Record<string, unknown>;

    // evidence_receipts items: source_url (format uri), source_content_hash (0x pattern)
    const evidenceReceipts = properties['evidence_receipts'] as Record<string, unknown>;
    expect(evidenceReceipts).toBeTruthy();
    const erItems = evidenceReceipts.items as Record<string, unknown>;
    const erRequired = erItems.required as string[];
    expect(new Set(erRequired)).toEqual(new Set([
      'source_url', 'source_content_hash', 'retrieved_at', 'provider', 'adequacy_checks',
    ]));

    const erProps = erItems.properties as Record<string, unknown>;
    const sourceUrl = erProps['source_url'] as Record<string, unknown>;
    expect(sourceUrl.format).toBe('uri');

    const sourceContentHash = erProps['source_content_hash'] as Record<string, unknown>;
    expect(sourceContentHash.pattern).toBe('^0x[0-9a-fA-F]{64}$');

    // onchain_receipts
    const onchainReceipts = properties['onchain_receipts'] as Record<string, unknown>;
    expect(onchainReceipts).toBeTruthy();
    const orRequired = onchainReceipts.required as string[];
    expect(new Set(orRequired)).toEqual(new Set([
      'trace_arc_tx', 'validation_arc_tx', 'erc8004_request_hash',
    ]));

    const orProps = onchainReceipts.properties as Record<string, unknown>;
    const hexPattern = '^0x[0-9a-fA-F]{64}$';
    expect((orProps['trace_arc_tx'] as Record<string, unknown>).pattern).toBe(hexPattern);
    expect((orProps['validation_arc_tx'] as Record<string, unknown>).pattern).toBe(hexPattern);
    expect((orProps['erc8004_request_hash'] as Record<string, unknown>).pattern).toBe(hexPattern);

    // content_hashes
    const contentHashes = properties['content_hashes'] as Record<string, unknown>;
    expect(contentHashes).toBeTruthy();
    const chRequired = contentHashes.required as string[];
    expect(new Set(chRequired)).toEqual(new Set([
      'trace_json_hash', 'verdict_json_hash', 'report_json_hash',
    ]));

    const chProps = contentHashes.properties as Record<string, unknown>;
    expect((chProps['trace_json_hash'] as Record<string, unknown>).pattern).toBe(hexPattern);
    expect((chProps['verdict_json_hash'] as Record<string, unknown>).pattern).toBe(hexPattern);
    expect((chProps['report_json_hash'] as Record<string, unknown>).pattern).toBe(hexPattern);
  });

  it('prism-report-v0 schema text contains zero forbidden substrings', () => {
    const schemaText = read(schemaPath).toLowerCase();

    for (const phrase of FORBIDDEN_SCHEMA_SUBSTRINGS) {
      expect(schemaText, `schema should not contain "${phrase}"`).not.toContain(phrase);
    }
  });
});
