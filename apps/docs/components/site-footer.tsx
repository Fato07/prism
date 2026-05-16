import Link from 'next/link';
import type { ReactNode } from 'react';

import { PrismWordmark } from '@/components/prism-wordmark';

const footerGroups = [
  {
    title: 'Build',
    links: [
      { label: 'Quickstart', href: '/docs/quickstart' },
      { label: 'CLI', href: '/docs/cli' },
      { label: 'x402 + MCP', href: '/docs/x402-mcp-validation' },
    ],
  },
  {
    title: 'Verify',
    links: [
      { label: 'Receipts', href: '/docs/receipts' },
      { label: 'Public APIs', href: '/docs/public-apis' },
      { label: 'Security', href: '/docs/security' },
    ],
  },
  {
    title: 'Product',
    links: [
      { label: 'Dashboard', href: 'https://prism-dashboard-production-e6e3.up.railway.app' },
      { label: 'GitHub', href: 'https://github.com/Fato07/prism' },
      { label: 'Troubleshooting', href: '/docs/troubleshooting' },
    ],
  },
] as const;

export function SiteFooter() {
  return (
    <footer className="mt-20 border-t border-border/70 bg-canvas-sunken/55">
      <div className="mx-auto grid w-full max-w-6xl gap-10 px-6 py-10 md:grid-cols-[1.2fr_1.8fr]">
        <div>
          <PrismWordmark />
          <p className="mt-4 max-w-sm text-sm leading-6 text-fg-muted">
            Developer documentation for receipt-backed adversarial validation: dashboard,
            MCP/x402, CLI, and public reporting APIs.
          </p>
        </div>
        <div className="grid gap-8 sm:grid-cols-3">
          {footerGroups.map((group) => (
            <div key={group.title}>
              <h2 className="text-xs font-semibold uppercase tracking-[0.22em] text-fg-subtle">
                {group.title}
              </h2>
              <ul className="mt-4 space-y-3 text-sm text-fg-muted">
                {group.links.map((link) => (
                  <li key={link.href}>
                    <FooterLink href={link.href}>{link.label}</FooterLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </footer>
  );
}

function FooterLink({ children, href }: { children: ReactNode; href: string }) {
  if (href.startsWith('http')) {
    return (
      <a className="hover:text-fg" href={href} rel="noreferrer" target="_blank">
        {children}
      </a>
    );
  }

  return (
    <Link className="hover:text-fg" href={href}>
      {children}
    </Link>
  );
}
