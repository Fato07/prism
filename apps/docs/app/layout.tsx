import './globals.css';

import type { Metadata } from 'next';
import { RootProvider } from 'fumadocs-ui/provider/next';
import { GeistMono } from 'geist/font/mono';
import { GeistSans } from 'geist/font/sans';
import type { ReactNode } from 'react';

export const metadata: Metadata = {
  title: {
    default: 'Prism Docs',
    template: '%s | Prism Docs',
  },
  description:
    'Developer documentation for Prism: adversarial AI validation, x402 payments, MCP, CLI reports, and receipt verification.',
  metadataBase: new URL('https://prism-docs-production.up.railway.app'),
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${GeistSans.variable} ${GeistMono.variable} flex min-h-screen flex-col`}>
        <RootProvider>{children}</RootProvider>
      </body>
    </html>
  );
}
