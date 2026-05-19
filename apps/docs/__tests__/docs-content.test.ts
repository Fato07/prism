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

  it('prism-report-v0 verdict has raw_verdict_score and capped_verdict_score both required (int 0..100)', () => {
    const schema = loadSchema();
    const properties = schema.properties as Record<string, unknown>;
    const verdict = properties['verdict'] as Record<string, unknown>;
    expect(verdict).toBeTruthy();

    const vRequired = verdict.required as string[];
    expect(vRequired).toContain('verdict_score');
    expect(vRequired).toContain('verdict_label');
    expect(vRequired).toContain('raw_verdict_score');
    expect(vRequired).toContain('capped_verdict_score');

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

  // -----------------------------------------------------------------------
  // Oracle-hardening tests (m2-schema-oracle-hardening)
  // -----------------------------------------------------------------------

  function compileValidator(): ReturnType<typeof Ajv2020.prototype.compile> {
    const schema = loadSchema();
    const ajv = new Ajv2020({ strict: true, allErrors: true });
    addFormats(ajv);
    return ajv.compile(schema);
  }

  function buildMinimalReport(overrides: Record<string, unknown> = {}): Record<string, unknown> {
    const base: Record<string, unknown> = {
      schema_version: 'prism.report.v0',
      generated_at: '2026-05-19T12:00:00Z',
      trace: {
        trace_id: 'test-trace',
        agent_id: 'test-agent',
        market_id: 'test-market',
        market_question: 'Will this test pass?',
        action: 'YES',
        raw_probability: 0.55,
        final_probability: 0.60,
        ipfs_cid: 'QmTestTestTestTestTestTestTestTestTestTest',
        dashboard_url: 'https://example.com/trace/test-trace',
      },
      action_intent: {
        type: 'prediction_market',
        market_id: 'test-market',
        side: 'YES',
        size_usdc: '5.00',
        builder_code: 'PRISM',
        raw_probability: 0.55,
        final_probability: 0.60,
        rationale: 'test rationale',
      },
      validator: {
        sentinel_agent_id: 'test-sentinel',
        model_family: 'openai-gpt',
        model_name: 'gpt-4o',
      },
      verdict: {
        verdict_score: 75,
        verdict_label: 'PASS',
        raw_verdict_score: 80,
        capped_verdict_score: 75,
      },
      reasoning_metrics: {
        evidence_count: 2,
        source_diversity: 2,
        thesis_steps: 2,
        evidence_reference_count: 2,
        evidence_coverage: 0.8,
        invalid_evidence_refs: 0,
        unsupported_thesis_steps: 0,
        risk_factor_count: 1,
        avg_evidence_confidence: 0.7,
        probability_delta: 0.05,
        has_falsification_language: true,
      },
      readiness: 'usable',
      warnings: [],
      issue_ledger: {
        summary: {
          total_issues: 0,
          resolved_count: 0,
          unresolved_blocking_count: 0,
          unresolved_material_count: 0,
          clean_pass_allowed: true,
          endorsement_allowed: true,
          active_policy_constraints: [],
          explanation: 'No issues.',
        },
        issues: [],
      },
      evidence_receipts: [
        {
          source_url: 'https://example.com/source',
          source_content_hash: '0x0000000000000000000000000000000000000000000000000000000000000001',
          retrieved_at: '2026-05-19T12:00:00Z',
          provider: 'test-provider',
          adequacy_checks: ['check-1'],
        },
      ],
      capital_gate: {
        status: 'ALLOW_PAPER',
      },
      payment_receipts: [
        {
          protocol: 'x402',
          tx_hash: '0x0000000000000000000000000000000000000000000000000000000000000002',
          amount_usdc: '0.01',
          network: 'base-sepolia',
          chain_id: 84532,
          payer: '0x0000000000000000000000000000000000000001',
          payee: '0x0000000000000000000000000000000000000002',
        },
      ],
      onchain_receipts: {
        trace_arc_tx: '0x0000000000000000000000000000000000000000000000000000000000000003',
        validation_arc_tx: '0x0000000000000000000000000000000000000000000000000000000000000004',
        erc8004_request_hash: '0x0000000000000000000000000000000000000000000000000000000000000005',
      },
      content_hashes: {
        trace_json_hash: '0x0000000000000000000000000000000000000000000000000000000000000006',
        verdict_json_hash: '0x0000000000000000000000000000000000000000000000000000000000000007',
        report_json_hash: '0x0000000000000000000000000000000000000000000000000000000000000008',
      },
    };

    // shallow merge overrides
    return { ...base, ...overrides };
  }

  it('prism-report-v0 minimal valid report passes ajv validation', () => {
    const validate = compileValidator();
    const report = buildMinimalReport();
    const valid = validate(report);
    expect(valid, `ajv errors: ${JSON.stringify(validate.errors)}`).toBe(true);
  });

  it('prism-report-v0 rejects report missing raw_verdict_score (score-field required)', () => {
    const validate = compileValidator();
    const report = buildMinimalReport();
    const verdict = report.verdict as Record<string, unknown>;
    delete (verdict as Record<string, unknown>).raw_verdict_score;
    const valid = validate(report);
    expect(valid).toBe(false);
    expect(validate.errors).toBeTruthy();
    expect(validate.errors!.some((e) => e.instancePath.includes('verdict') && e.keyword === 'required')).toBe(true);
  });

  it('prism-report-v0 rejects report missing capped_verdict_score (score-field required)', () => {
    const validate = compileValidator();
    const report = buildMinimalReport();
    const verdict = report.verdict as Record<string, unknown>;
    delete (verdict as Record<string, unknown>).capped_verdict_score;
    const valid = validate(report);
    expect(valid).toBe(false);
    expect(validate.errors).toBeTruthy();
    expect(validate.errors!.some((e) => e.instancePath.includes('verdict') && e.keyword === 'required')).toBe(true);
  });

  it('prism-report-v0 capped_verdict_score invariant is documented in schema description', () => {
    const schema = loadSchema();
    const properties = schema.properties as Record<string, unknown>;
    const verdict = properties['verdict'] as Record<string, unknown>;
    const vProps = verdict.properties as Record<string, unknown>;
    const capped = vProps['capped_verdict_score'] as Record<string, unknown>;
    expect(capped).toBeTruthy();
    const desc = String(capped.description ?? '');
    expect(desc).toMatch(/capped_verdict_score\s*<=/);
  });

  it('prism-report-v0 rejects permissive extra properties in issue_ledger nested objects (no raw_prompt smuggling)', () => {
    const validate = compileValidator();
    const report = buildMinimalReport({
      issue_ledger: {
        summary: {
          total_issues: 0, resolved_count: 0,
          unresolved_blocking_count: 0, unresolved_material_count: 0,
          clean_pass_allowed: true, endorsement_allowed: true,
          active_policy_constraints: [], explanation: 'ok',
        },
        issues: [{
          id: 'i1', type: 'factuality', severity: 'high',
          blocking_pass: true, resolution_status: 'open',
          question: 'Is this true?', required_resolution: 'verify',
          tool_status: 'fail_closed', tool_provider: 'test',
          tool_receipt: {
            source_content_hash: '0x0000000000000000000000000000000000000000000000000000000000000101',
            retrieved_at: '2026-05-19T12:00:00Z',
            provider: 'test',
          },
          resolved_by_evidence_tool: false,
          latest_resolution: {
            status: 'unresolved',
            resolved_at: '2026-05-19T12:00:00Z',
          },
          // RAW_PROMPT should be rejected by additionalProperties:false
          raw_prompt: 'should not be allowed',
        }],
      },
    });
    const valid = validate(report);
    expect(valid).toBe(false);
    expect(validate.errors).toBeTruthy();
    expect(validate.errors!.some((e) =>
      e.keyword === 'additionalProperties' || e.keyword === 'unevaluatedProperties',
    )).toBe(true);
  });

  it('prism-report-v0 rejects forbidden keys in issue_ledger.tool_receipt (secret smuggle)', () => {
    const validate = compileValidator();
    const report = buildMinimalReport({
      issue_ledger: {
        summary: {
          total_issues: 0, resolved_count: 0,
          unresolved_blocking_count: 0, unresolved_material_count: 0,
          clean_pass_allowed: true, endorsement_allowed: true,
          active_policy_constraints: [], explanation: 'ok',
        },
        issues: [{
          id: 'i2', type: 'factuality', severity: 'high',
          blocking_pass: true, resolution_status: 'open',
          question: 'Did the trader leak secrets?', required_resolution: 'redact',
          tool_status: 'fail_closed', tool_provider: 'test',
          tool_receipt: {
            source_content_hash: '0x0000000000000000000000000000000000000000000000000000000000000201',
            retrieved_at: '2026-05-19T12:00:00Z',
            provider: 'test',
            // api_key field should be rejected by additionalProperties:false
            api_key: 'sk-secret-leaked-key-should-fail',
          },
          resolved_by_evidence_tool: false,
          latest_resolution: {
            status: 'unresolved',
            resolved_at: '2026-05-19T12:00:00Z',
          },
        }],
      },
    });
    const valid = validate(report);
    expect(valid).toBe(false);
    expect(validate.errors).toBeTruthy();
    expect(validate.errors!.some((e) =>
      e.keyword === 'additionalProperties' || e.keyword === 'unevaluatedProperties',
    )).toBe(true);
  });

  it('prism-report-v0 rejects forbidden keys in issue_ledger.latest_resolution (chain-of-thought smuggle)', () => {
    const validate = compileValidator();
    const report = buildMinimalReport({
      issue_ledger: {
        summary: {
          total_issues: 0, resolved_count: 0,
          unresolved_blocking_count: 0, unresolved_material_count: 0,
          clean_pass_allowed: true, endorsement_allowed: true,
          active_policy_constraints: [], explanation: 'ok',
        },
        issues: [{
          id: 'i3', type: 'factuality', severity: 'high',
          blocking_pass: true, resolution_status: 'open',
          question: 'Does the CoT leak private reasoning?', required_resolution: 'redact',
          tool_status: 'not_recorded', tool_provider: 'none',
          tool_receipt: {
            source_content_hash: '0x0000000000000000000000000000000000000000000000000000000000000301',
            retrieved_at: '2026-05-19T12:00:00Z',
            provider: 'test',
          },
          resolved_by_evidence_tool: false,
          latest_resolution: {
            status: 'unresolved',
            resolved_at: '2026-05-19T12:00:00Z',
            // chain_of_thought should be rejected
            chain_of_thought: 'The model thought about this...',
          },
        }],
      },
    });
    const valid = validate(report);
    expect(valid).toBe(false);
    expect(validate.errors).toBeTruthy();
    expect(validate.errors!.some((e) =>
      e.keyword === 'additionalProperties' || e.keyword === 'unevaluatedProperties',
    )).toBe(true);
  });

  it('prism-report-v0 enforces scalar bounds on probability fields (rejects > 1)', () => {
    const validate = compileValidator();
    const report = buildMinimalReport();
    const trace = report.trace as Record<string, unknown>;
    trace.raw_probability = 1.5;
    const valid = validate(report);
    expect(valid).toBe(false);
    expect(validate.errors).toBeTruthy();
    expect(validate.errors!.some((e) => e.keyword === 'maximum' || e.keyword === 'minimum')).toBe(true);
  });

  it('prism-report-v0 enforces scalar bounds on avg_evidence_confidence (rejects < 0)', () => {
    const validate = compileValidator();
    const report = buildMinimalReport();
    const rm = report.reasoning_metrics as Record<string, unknown>;
    rm.avg_evidence_confidence = -0.1;
    const valid = validate(report);
    expect(valid).toBe(false);
    expect(validate.errors).toBeTruthy();
    expect(validate.errors!.some((e) => e.keyword === 'maximum' || e.keyword === 'minimum')).toBe(true);
  });

  it('prism-report-v0 enforces USDC decimal-string pattern on size_usdc (rejects empty)', () => {
    const validate = compileValidator();
    const report = buildMinimalReport();
    const ai = report.action_intent as Record<string, unknown>;
    ai.size_usdc = '';
    const valid = validate(report);
    expect(valid).toBe(false);
    expect(validate.errors).toBeTruthy();
    expect(validate.errors!.some((e) => e.keyword === 'pattern')).toBe(true);
  });

  it('prism-report-v0 enforces USDC decimal-string pattern on amount_usdc (rejects negative)', () => {
    const validate = compileValidator();
    const report = buildMinimalReport();
    const prs = report.payment_receipts as Array<Record<string, unknown>>;
    prs[0].amount_usdc = '-5.00';
    const valid = validate(report);
    expect(valid).toBe(false);
    expect(validate.errors).toBeTruthy();
    expect(validate.errors!.some((e) => e.keyword === 'pattern')).toBe(true);
  });

  it('prism-report-v0 enforces minLength:1 on warnings items (rejects empty string)', () => {
    const validate = compileValidator();
    const report = buildMinimalReport();
    report.warnings = ['ok', ''];
    const valid = validate(report);
    expect(valid).toBe(false);
    expect(validate.errors).toBeTruthy();
    expect(validate.errors!.some((e) => e.keyword === 'minLength')).toBe(true);
  });

  it('prism-report-v0 enforces minLength:1 on market_question (rejects empty string)', () => {
    const validate = compileValidator();
    const report = buildMinimalReport();
    const trace = report.trace as Record<string, unknown>;
    trace.market_question = '';
    const valid = validate(report);
    expect(valid).toBe(false);
    expect(validate.errors).toBeTruthy();
    expect(validate.errors!.some((e) => e.keyword === 'minLength')).toBe(true);
  });

  it('prism-report-v0 proof: no {} permissive subschemas remain in issue_ledger', () => {
    const schema = loadSchema();
    const il = (schema.properties as Record<string, unknown>)['issue_ledger'] as Record<string, unknown>;
    expect(il).toBeTruthy();

    // resolution_metadata must be an object with additionalProperties: false, not {}
    const rm = il.properties as Record<string, unknown>;
    const resMeta = rm['resolution_metadata'] as Record<string, unknown>;
    expect(resMeta).toBeTruthy();
    expect(resMeta.type).toBe('object');
    expect(resMeta.additionalProperties).toBe(false);

    // Check issues.items.properties for strict closures
    const issues = rm['issues'] as Record<string, unknown>;
    const items = issues.items as Record<string, unknown>;
    const itemProps = items.properties as Record<string, unknown>;

    // tool_receipt must be strict
    const tr = itemProps['tool_receipt'] as Record<string, unknown>;
    expect(tr).toBeTruthy();
    expect(tr.type).toBe('object');
    expect(tr.additionalProperties).toBe(false);
    expect(tr.required).toBeTruthy();
    expect((tr.required as string[]).length).toBeGreaterThanOrEqual(2);

    // latest_resolution must be strict
    const lr = itemProps['latest_resolution'] as Record<string, unknown>;
    expect(lr).toBeTruthy();
    expect(lr.type).toBe('object');
    expect(lr.additionalProperties).toBe(false);
    expect(lr.required).toBeTruthy();
    expect((lr.required as string[]).length).toBeGreaterThanOrEqual(2);
  });

  it('prism-report-v0 proof: no request_hash duplication in verdict (removed)', () => {
    const schema = loadSchema();
    const properties = schema.properties as Record<string, unknown>;
    const verdict = properties['verdict'] as Record<string, unknown>;
    const vProps = verdict.properties as Record<string, unknown>;

    // request_hash must NOT be present in verdict.properties
    expect(vProps['request_hash']).toBeUndefined();

    // erc8004_request_hash must be present in onchain_receipts as canonical location
    const onchain = properties['onchain_receipts'] as Record<string, unknown>;
    const orProps = onchain.properties as Record<string, unknown>;
    expect(orProps['erc8004_request_hash']).toBeTruthy();
  });

  it('prism-report-v0 proof: scalar fields have bounds, patterns, or minLength', () => {
    const schema = loadSchema();
    const properties = schema.properties as Record<string, unknown>;

    // trace probabilities bounded
    const trace = properties['trace'] as Record<string, unknown>;
    const tProps = trace.properties as Record<string, unknown>;
    expect((tProps['raw_probability'] as Record<string, unknown>).minimum).toBe(0);
    expect((tProps['raw_probability'] as Record<string, unknown>).maximum).toBe(1);
    expect((tProps['final_probability'] as Record<string, unknown>).minimum).toBe(0);
    expect((tProps['final_probability'] as Record<string, unknown>).maximum).toBe(1);
    expect((tProps['market_question'] as Record<string, unknown>).minLength).toBe(1);

    // reasoning_metrics avg_evidence_confidence bounded
    const rm = properties['reasoning_metrics'] as Record<string, unknown>;
    const rmProps = rm.properties as Record<string, unknown>;
    expect((rmProps['avg_evidence_confidence'] as Record<string, unknown>).minimum).toBe(0);
    expect((rmProps['avg_evidence_confidence'] as Record<string, unknown>).maximum).toBe(1);

    // warnings items have minLength
    const w = properties['warnings'] as Record<string, unknown>;
    const wItems = w.items as Record<string, unknown>;
    expect(wItems.minLength).toBe(1);

    // x402 def: amount_usdc has pattern, chain_id has minimum, payer/payee have EVM pattern
    const defs = schema.$defs as Record<string, unknown>;
    const x402 = defs['payment_receipt_x402'] as Record<string, unknown>;
    const x402Props = x402.properties as Record<string, unknown>;
    expect((x402Props['amount_usdc'] as Record<string, unknown>).pattern).toBeTruthy();
    expect((x402Props['chain_id'] as Record<string, unknown>).minimum).toBe(1);
    expect((x402Props['payer'] as Record<string, unknown>).pattern).toBeTruthy();
    expect((x402Props['payee'] as Record<string, unknown>).pattern).toBeTruthy();

    // prediction_market def: size_usdc has pattern, probabilities bounded
    const pm = defs['action_intent_prediction_market'] as Record<string, unknown>;
    const pmProps = pm.properties as Record<string, unknown>;
    expect((pmProps['size_usdc'] as Record<string, unknown>).pattern).toBeTruthy();
    expect((pmProps['raw_probability'] as Record<string, unknown>).minimum).toBe(0);
    expect((pmProps['raw_probability'] as Record<string, unknown>).maximum).toBe(1);
    expect((pmProps['final_probability'] as Record<string, unknown>).minimum).toBe(0);
    expect((pmProps['final_probability'] as Record<string, unknown>).maximum).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// Protocol Documentation
// ---------------------------------------------------------------------------

describe('Protocol documentation', () => {
  const protocolDocPath = '../../docs/protocol/prism-protocol-v0.md';
  const receiptVerificationPath = '../../docs/protocol/receipt-verification-v0.md';

  it('prism-protocol-v0.md contains onchain-forbidden language covering all four categories', () => {
    const body = read(protocolDocPath).toLowerCase();

    // VAL-PROTOCOL-009: onchain-forbidden section must forbid all four:
    // raw prompts, scraped pages, secrets, chain-of-thought
    expect(body).toMatch(/raw\s+prompts?/);
    expect(body).toMatch(/scraped\s+pages?/);
    expect(body).toMatch(/\bsecrets?\b/);
    expect(body).toMatch(/chain[- ]of[- ]thought/);
  });

  it('prism-protocol-v0.md marks mpp and ap2 as reserved/future payment receipt protocols', () => {
    const body = read(protocolDocPath).toLowerCase();

    // VAL-PROTOCOL-007, VAL-PROTOCOL-008: mpp and ap2 must appear near
    // reserved/future markers in payment receipt context
    expect(body).toMatch(/\bmpp\b/);
    expect(body).toMatch(/\bap2\b/);
    expect(body).toMatch(/payment\s+receipt/);
    expect(body).toMatch(/reserved|future|not\s+implemented/);
  });

  it('prism-protocol-v0.md contains zero banned overclaim phrases (shared const)', () => {
    const body = read(protocolDocPath).toLowerCase();

    // VAL-PROTOCOL-014, VAL-CROSS-009: same shared BANNED_PHRASES const from F1
    for (const phrase of BANNED_PHRASES) {
      expect(body, `protocol doc should not contain "${phrase}"`).not.toContain(phrase);
    }
  });

  it('prism-protocol-v0.md mirrors the 8 Prism guarantees from verification-guarantees.mdx', () => {
    // VAL-CROSS-004: same set, same count (8)
    const guaranteesBody = read('content/docs/verification-guarantees.mdx');
    const protocolBody = read(protocolDocPath);

    // The 8 guarantee concepts — each must appear in both files
    const guaranteeConcepts = [
      /\bprovenance\b/i,
      /\bindependent\s+adversarial\s+review\b/i,
      /\bsource\s+URL\s+verification\b/i,
      /\bsource\s+content\s+hashes\b/i,
      /\bissue[- ]?ledger\s+transparency\b/i,
      /\bx402\s+receipts\b/i,
      /\bArc\b/,
      /\bERC[- ]?8004\b/,
      /\bfail[- ]?closed\s+capital\s+gate\b/i,
    ];

    for (const concept of guaranteeConcepts) {
      expect(guaranteesBody, `guarantees page should mention: ${concept}`).toMatch(concept);
      expect(protocolBody, `protocol doc should mention: ${concept}`).toMatch(concept);
    }

    // Both files must have a "What Prism guarantees" heading
    expect(guaranteesBody).toMatch(/What Prism guarantees/i);
    expect(protocolBody).toMatch(/What Prism guarantees/i);

    // Count: each file should mention all 9 concepts (which represent 8 distinct guarantees —
    //   Arc + ERC-8004 together form one guarantee item)
    const guHits = guaranteeConcepts.filter((c) => c.test(guaranteesBody));
    const protoHits = guaranteeConcepts.filter((c) => c.test(protocolBody));
    expect(guHits).toHaveLength(9);
    expect(protoHits).toHaveLength(9);
  });

  it('prism-protocol-v0.md mirrors the 5 Prism disclaimers from verification-guarantees.mdx', () => {
    // VAL-CROSS-005: same set, same count (5)
    const guaranteesBody = read('content/docs/verification-guarantees.mdx');
    const protocolBody = read(protocolDocPath);

    // 5 NOT-guarantees: truth, profit, complete security, legal compliance,
    // PASS is not an instruction to execute real capital
    const disclaimerConcepts = [
      /\btruth\b/i,
      /\bprofit\b/i,
      /\bcomplete\s+security\b/i,
      /\blegal\s+compliance\b/i,
      /PASS.*not.*instruction.*execute|PASS.*not.*command.*execute/i,
    ];

    for (const concept of disclaimerConcepts) {
      expect(guaranteesBody, `guarantees page should mention disclaimer: ${concept}`).toMatch(concept);
      expect(protocolBody, `protocol doc should mention disclaimer: ${concept}`).toMatch(concept);
    }

    // Both files must have a "What Prism does NOT guarantee" heading
    expect(guaranteesBody).toMatch(/What Prism does NOT guarantee/i);
    expect(protocolBody).toMatch(/What Prism does NOT guarantee/i);

    // Count: all 5 disclaimer concepts must appear in both files
    const guHits = disclaimerConcepts.filter((c) => c.test(guaranteesBody));
    const protoHits = disclaimerConcepts.filter((c) => c.test(protocolBody));
    expect(guHits).toHaveLength(5);
    expect(protoHits).toHaveLength(5);
  });

  // -----------------------------------------------------------------------
  // Oracle protocol hardening (m2-protocol-oracle-hardening)
  // -----------------------------------------------------------------------

  it('prism-protocol-v0.md has normative content-hash canonicalization section (RFC 8785, UTF-8, Keccak-256, 0x prefix, self-reference, generated_at, test vector)', () => {
    const body = read(protocolDocPath);

    // Must mention RFC 8785 or JCS or canonical JSON or deterministic JSON
    expect(body).toMatch(/RFC\s*8785|JCS|canonical\s+JSON|deterministic\s+JSON/i);

    // Must mention UTF-8 encoding
    expect(body).toMatch(/UTF[- ]?8/);

    // Must mention Keccak-256 or hash algorithm
    expect(body).toMatch(/Keccak[- ]?256|hash\s+algorithm/i);

    // Must mention 0x prefix
    expect(body).toMatch(/0x[-\s]?prefixed|prefixed\s+with\s+`?0x`?|0x[- ]?prefix/i);

    // Must handle self-referential report_json_hash (omit or sentinel)
    const lower = body.toLowerCase();
    expect(lower).toMatch(/report_json_hash/);
    expect(lower).toMatch(/omitted|remov|excluded|exclud|sentinel|null.*before|before.*null/);

    // Must state whether generated_at participates in the hash
    expect(body).toMatch(/generated_at/);

    // Must contain a minimal worked example or test vector
    expect(body).toMatch(/example|test\s*vector|work(?:ed)?\s*example/);
  });

  it('prism-protocol-v0.md defines raw/capped/display verdict score semantics with capped <= raw', () => {
    const body = read(protocolDocPath);

    // Must mention all three score fields
    expect(body).toMatch(/raw_verdict_score/);
    expect(body).toMatch(/capped_verdict_score/);
    expect(body).toMatch(/verdict_score/);

    // Must state that capped <= raw
    expect(body).toMatch(/capped.*<=.*raw|capped_verdict_score\s*(?:<=|≤|must be less than or equal to|must not exceed)\s*raw_verdict_score/i);

    // Must define what verdict_score represents (display/alias/capped)
    const lower = body.toLowerCase();
    expect(lower).toMatch(/verdict_score.*display|verdict_score.*alias|verdict_score.*capped/);
  });

  it('prism-protocol-v0.md states exact fail-closed criteria and that REVIEW is not fail-closed', () => {
    const body = read(protocolDocPath);

    // Must mention BLOCK, REJECT, and unresolved_blocking_count as fail-closed criteria
    expect(body).toMatch(/\bBLOCK\b/);
    expect(body).toMatch(/\bREJECT\b/);
    expect(body).toMatch(/unresolved_blocking_count/);

    // Must state that REVIEW is NOT fail-closed
    const lower = body.toLowerCase();
    expect(lower).toMatch(/\breview\b.*not.*fail[-\s]?closed|fail[-\s]?closed.*\breview\b|review.*distinct.*state|review.*separate/);
  });

  it('prism-protocol-v0.md defines tool_receipt vs evidence_receipts[] relationship', () => {
    const body = read(protocolDocPath);

    // Must mention both tool_receipt and evidence_receipts
    expect(body).toMatch(/tool_receipt/);
    expect(body).toMatch(/evidence_receipts/);

    // Must define relationship: subset, reference, or informational
    const lower = body.toLowerCase();
    expect(lower).toMatch(/reference|subset|informational|backward|legacy|canonical|should\s+prefer/);
  });

  it('prism-protocol-v0.md defines readiness enum semantics with capital-gate correlations', () => {
    const body = read(protocolDocPath);

    // Must mention all three readiness values
    expect(body).toMatch(/usable/);
    expect(body).toMatch(/needs_review/);
    expect(body).toMatch(/not_ready/);

    // Must define correlations with capital gate
    expect(body).toMatch(/capital_gate|capital\s+gate/);
  });

  it('prism-protocol-v0.md reserved oneOf wording clarifies v0 consumers reject richer future payloads', () => {
    const body = read(protocolDocPath);

    // Must mention that richer payloads require new schema_version
    const lower = body.toLowerCase();
    expect(lower).toMatch(/schema_version/);

    // Must mention rejection behavior for v0 consumers
    expect(lower).toMatch(/reject|will\s+not\s+accept|should\s+reject|must\s+reject|intended\s+behavior/);
  });
});

// ---------------------------------------------------------------------------
// Receipt Verification — oracle hardening consistency
// ---------------------------------------------------------------------------

describe('Receipt verification — oracle hardening', () => {
  const receiptVerificationPath = '../../docs/protocol/receipt-verification-v0.md';

  it('receipt-verification-v0.md is consistent with canonicalization procedure (self-reference, generated_at)', () => {
    const body = read(receiptVerificationPath);

    // Must mention report_json_hash self-reference handling
    const lower = body.toLowerCase();
    expect(lower).toMatch(/report_json_hash/);
    expect(lower).toMatch(/omit|remov|exclude|sentinel|null\s*before|before\s*null/);

    // Must mention generated_at participation
    expect(body).toMatch(/generated_at/);
  });
});
