import Link from 'next/link';

import { PrismWordmark } from '@/components/prism-wordmark';
import { SiteFooter } from '@/components/site-footer';

const navLinks = [
  { label: 'Quickstart', href: '/docs/quickstart' },
  { label: 'CLI', href: '/docs/cli' },
  { label: 'Receipts', href: '/docs/receipts' },
  { label: 'Dashboard', href: 'https://prism-dashboard-production-e6e3.up.railway.app' },
] as const;

const cards = [
  {
    title: 'Run the CLI',
    href: '/docs/cli',
    body: 'Inspect traces, fetch public reports, quote x402 validation, and save receipts.',
  },
  {
    title: 'Validate with x402 + MCP',
    href: '/docs/x402-mcp-validation',
    body: 'Call the sentinel endpoint explicitly, capped, and without Prism reading private keys.',
  },
  {
    title: 'Verify receipts',
    href: '/docs/receipts',
    body: 'Understand IPFS CIDs, Base Sepolia payment txs, Arc validation txs, and report JSON.',
  },
];

export default function HomePage() {
  return (
    <>
      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col px-6 py-8 md:py-12">
        <nav className="mb-16 flex flex-wrap items-center justify-between gap-4" aria-label="Docs">
          <Link href="/" aria-label="Prism documentation home">
            <PrismWordmark />
          </Link>
          <div className="flex flex-wrap items-center gap-3 text-sm text-fg-muted">
            {navLinks.map((link) =>
              link.href.startsWith('http') ? (
                <a className="hover:text-fg" href={link.href} key={link.href}>
                  {link.label}
                </a>
              ) : (
                <Link className="hover:text-fg" href={link.href} key={link.href}>
                  {link.label}
                </Link>
              ),
            )}
          </div>
        </nav>

        <section className="grid gap-10 lg:grid-cols-[1.2fr_0.8fr] lg:items-center">
        <div>
          <p className="mb-4 text-sm font-medium uppercase tracking-[0.22em] text-trader">
            Adversarial AI validation for agentic markets
          </p>
          <h1 className="max-w-4xl text-5xl font-semibold tracking-[-0.05em] text-fg md:text-7xl">
            Docs for turning trading traces into verifiable Prism Reports.
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-fg-muted">
            Prism pairs a trader agent with an adversarial sentinel, then links the result to x402
            payment evidence, IPFS content, and Arc/ERC-8004 validation receipts.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              className="rounded-full bg-fg px-5 py-3 text-sm font-semibold text-canvas hover:bg-trader"
              href="/docs/quickstart"
            >
              Start quickstart
            </Link>
            <Link
              className="rounded-full border border-border px-5 py-3 text-sm font-semibold text-fg hover:border-trader"
              href="/docs/security"
            >
              Read safety model
            </Link>
          </div>
        </div>

        <div className="prism-card prism-spectrum-border rounded-3xl p-6">
          <p className="text-xs font-medium uppercase tracking-[0.22em] text-fg-subtle">
            Canonical demo trace
          </p>
          <dl className="mt-6 space-y-4 text-sm">
            <div>
              <dt className="text-fg-subtle">CID</dt>
              <dd className="mt-1 break-all font-mono text-fg">
                QmNzqnPEEQUMn3GMbiEZANpKXZRPmTHxVwt5nNevR8iXt8
              </dd>
            </div>
            <div>
              <dt className="text-fg-subtle">Sentinel verdict</dt>
              <dd className="mt-1 text-fg">65 PASS</dd>
            </div>
            <div>
              <dt className="text-fg-subtle">Safe first command</dt>
              <dd className="mt-1 rounded-2xl bg-canvas-sunken p-3 font-mono text-xs text-trader">
                uvx --from "prism-cli @ git+https://github.com/Fato07/prism.git#subdirectory=apps/cli" prism demo
              </dd>
            </div>
          </dl>
        </div>
      </section>

        <section className="mt-16 grid gap-4 md:grid-cols-3">
          {cards.map((card) => (
            <Link
              className="prism-card rounded-2xl p-5 transition hover:border-trader"
              href={card.href}
              key={card.href}
            >
              <h2 className="text-lg font-semibold text-fg">{card.title}</h2>
              <p className="mt-2 text-sm leading-6 text-fg-muted">{card.body}</p>
            </Link>
          ))}
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
