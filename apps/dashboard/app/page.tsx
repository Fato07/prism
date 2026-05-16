/**
 * Prism Landing Page — Root route (/)
 *
 * Composition (top to bottom):
 *   1. Glass nav (sticky)
 *   2. Hero — paper-design MeshGradient shader + headline + waitlist form
 *   3. How it works — three-step chromatic mechanism explainer
 *   4. Why it matters — asymmetric feature cards (no emojis, lucide icons)
 *   5. Live activity — real numbers from Neon
 *   6. Tech stack — pills with gradient borders for primary tech
 *   7. Footer
 *
 * All data fetching is server-side; the hero + how-it-works carry `'use client'`
 * for the shader + motion. Everything else is a server component.
 */

import type { Metadata } from "next";
import Link from "next/link";
import {
  ensureWaitlistTable,
  getWaitlistCount,
} from "@/lib/db";
import { getActivityStats } from "@/lib/stats";
import { Hero } from "@/components/landing/hero";
import { HowItWorks } from "@/components/landing/how-it-works";
import { WhyPrism } from "@/components/landing/why-prism";
import { LiveActivityStrip } from "@/components/landing/live-activity-strip";
import { GlobalNav } from "@/components/global-nav";
import { Pill } from "@/components/ui/pill";
import { Separator } from "@/components/ui/separator";
import { BrandMark } from "@/components/brands/brand-mark";
import { BuilderFeesStrip } from "@/components/landing/builder-fees-strip";
import { TreasuryStrip } from "@/components/landing/treasury-strip";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Prism — The First Adversarial AI Validator on ERC-8004",
  description:
    "Prism is the first adversarial AI validator on ERC-8004. Two agents — a trader and a sentinel — challenge each other's reasoning with on-chain proof on Arc. Join the waitlist.",
  openGraph: {
    title: "Prism — Adversarial AI Validator on ERC-8004",
    description:
      "Two agents challenge each other's reasoning. On-chain proof on Arc. Join the waitlist for early access.",
    type: "website",
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
        alt: "Prism — Adversarial AI Validator on ERC-8004",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Prism — Adversarial AI Validator on ERC-8004",
    description:
      "Two agents challenge each other's reasoning. On-chain proof on Arc.",
    images: ["/og-image.png"],
  },
};

// Brand-mark name (when applicable) for each tech in the stack section.
type TechItem = {
  label: string;
  brand?:
    | "arc"
    | "circle"
    | "canteen"
    | "polymarket"
    | "coinbase"
    | "neon"
    | "ipfs"
    | "ethereum";
};

const PRIMARY_TECH: TechItem[] = [
  { label: "Arc", brand: "arc" },
  { label: "ERC-8004", brand: "ethereum" },
  { label: "Circle Wallets", brand: "circle" },
  { label: "Canteen", brand: "canteen" },
];
const SECONDARY_TECH: TechItem[] = [
  { label: "x402", brand: "coinbase" },
  { label: "Polymarket V2", brand: "polymarket" },
  { label: "Neon Postgres", brand: "neon" },
  { label: "IPFS", brand: "ipfs" },
  { label: "DSPy" },
  { label: "Mirascope" },
];

export default async function LandingPage() {
  // Best-effort data fetch — landing must render even if Neon is down.
  let waitlistCount = 0;
  let stats = { traces: 0, validations: 0, trades: 0, flagged: 0, uniqueWallets: 0, onChainAnchors: 0, externalX402Calls: 0 };
  try {
    await ensureWaitlistTable();
    [waitlistCount, stats] = await Promise.all([
      getWaitlistCount(),
      getActivityStats(),
    ]);
  } catch {
    /* keep zeros */
  }

  return (
    <div className="min-h-screen bg-canvas text-fg">
      <GlobalNav currentPage="home" />

      <main>
        <Hero waitlistCount={waitlistCount} />

        <HowItWorks />

        <WhyPrism />

        <LiveActivityStrip stats={stats} waitlistCount={waitlistCount} />

        <BuilderFeesStrip />

        <TreasuryStrip />

        {/* Tech stack */}
        <section
          className="border-b border-[var(--color-border)]"
          aria-labelledby="tech"
        >
          <div className="mx-auto max-w-6xl px-6 py-20">
            <div className="mb-10">
              <p className="text-mono text-xs font-medium uppercase tracking-[var(--tracking-wide)] text-fg-faint">
                Built on
              </p>
              <h2
                id="tech"
                className="mt-2 max-w-2xl text-balance text-2xl font-semibold tracking-[var(--tracking-tight)] text-fg sm:text-3xl"
              >
                A stack chosen for adversarial honesty.
              </h2>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {PRIMARY_TECH.map((t) => (
                <span
                  key={t.label}
                  className="ring-spectrum relative inline-flex items-center gap-2 rounded-lg bg-[var(--color-canvas-raised)] px-3.5 py-1.5 text-sm font-medium text-fg"
                >
                  {t.brand && (
                    <BrandMark name={t.brand} size={16} aria-label={t.label} />
                  )}
                  {t.label}
                </span>
              ))}
              <Separator orientation="vertical" className="mx-2 h-6" />
              {SECONDARY_TECH.map((t) => (
                <Pill key={t.label} tone="neutral" emphasis="outline" size="md">
                  {t.brand && (
                    <BrandMark
                      name={t.brand}
                      size={12}
                      aria-label={t.label}
                      className="text-fg-muted"
                    />
                  )}
                  <span className="text-mono text-xs">{t.label}</span>
                </Pill>
              ))}
            </div>
          </div>
        </section>
      </main>

      <Footer />
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */

function Footer() {
  return (
    <footer className="px-6 py-10">
      <div className="mx-auto flex max-w-6xl flex-col items-start gap-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3 text-sm text-fg-muted">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <path d="M4 17L10 3L16 17Z" stroke="url(#footer-prism-gradient)" strokeWidth="1.4" strokeLinejoin="round" />
            <defs><linearGradient id="footer-prism-gradient" x1="3" y1="3" x2="17" y2="17" gradientUnits="userSpaceOnUse">
              <stop stopColor="var(--color-trader)" /><stop offset="0.6" stopColor="var(--color-sentinel)" /><stop offset="1" stopColor="var(--color-verdict-good)" />
            </linearGradient></defs>
          </svg>
          <span className="text-mono text-xs">
            First adversarial AI validator on ERC-8004
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-fg-faint">
          <span className="inline-flex items-center gap-1.5">
            <BrandMark name="arc" size={14} aria-label="Arc" />
            <span className="text-mono">Arc Testnet</span>
          </span>
          <span className="inline-flex items-center gap-1.5">
            <BrandMark name="circle" size={14} aria-label="Circle" />
            <span className="text-mono">Circle Wallets</span>
          </span>
          <span className="inline-flex items-center gap-1.5">
            <BrandMark name="canteen" size={14} aria-label="Canteen" />
            <span className="text-mono">Built on Canteen</span>
          </span>
          <Link
            href="/dashboard"
            prefetch
            className="text-fg-muted transition-colors hover:text-fg"
          >
            Dashboard
          </Link>
          <a
            href="https://github.com/Fato07/prism"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-fg-muted transition-colors hover:text-fg"
          >
            <BrandMark name="github" size={12} aria-label="GitHub" />
            GitHub
          </a>
        </div>
      </div>
    </footer>
  );
}
