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
import {
  ensureWaitlistTable,
  getWaitlistCount,
  getActivityStats,
} from "@/lib/db";
import { Hero } from "@/components/landing/hero";
import { HowItWorks } from "@/components/landing/how-it-works";
import { WhyPrism } from "@/components/landing/why-prism";
import { LiveActivityStrip } from "@/components/landing/live-activity-strip";
import { Pill } from "@/components/ui/pill";
import { Separator } from "@/components/ui/separator";
import { ArrowUpRight } from "lucide-react";
import { BrandMark } from "@/components/brands/brand-mark";

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
  let stats = { traces: 0, validations: 0, trades: 0, flagged: 0 };
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
      <GlassNav />

      <main>
        <Hero waitlistCount={waitlistCount} />

        <HowItWorks />

        <WhyPrism />

        <LiveActivityStrip stats={stats} waitlistCount={waitlistCount} />

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

function GlassNav() {
  return (
    <nav className="sticky top-0 z-50 border-b border-[var(--color-border)] bg-[var(--color-canvas)]/70 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3.5">
        <a
          href="/"
          className="group inline-flex items-center gap-2 text-base font-semibold tracking-[var(--tracking-tight)] text-fg"
        >
          <Wordmark />
          <span>Prism</span>
        </a>
        <div className="flex items-center gap-2">
          <a
            href="https://github.com/Fato07/prism"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="GitHub"
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--color-border)] text-fg-muted transition-colors hover:border-[var(--color-border-strong)] hover:text-fg focus-ring"
          >
            <GithubMark className="h-4 w-4" />
          </a>
          <a
            href="/dashboard"
            className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border-strong)] bg-[var(--color-canvas-raised)] px-3.5 py-1.5 text-sm font-medium text-fg transition-colors hover:bg-[var(--color-panel)] focus-ring"
          >
            Live dashboard
            <ArrowUpRight className="h-3.5 w-3.5" strokeWidth={2} />
          </a>
        </div>
      </div>
    </nav>
  );
}

function GithubMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="currentColor"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.339-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.02 10.02 0 0022 12.017C22 6.484 17.522 2 12 2z"
      />
    </svg>
  );
}

function Wordmark() {
  // Tiny prism mark — three diverging rays, mono-color, abstract.
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 20 20"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M4 17L10 3L16 17Z"
        stroke="url(#prism-gradient)"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
      <defs>
        <linearGradient
          id="prism-gradient"
          x1="3"
          y1="3"
          x2="17"
          y2="17"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="var(--color-trader)" />
          <stop offset="0.6" stopColor="var(--color-sentinel)" />
          <stop offset="1" stopColor="var(--color-verdict-good)" />
        </linearGradient>
      </defs>
    </svg>
  );
}



function Footer() {
  return (
    <footer className="px-6 py-10">
      <div className="mx-auto flex max-w-6xl flex-col items-start gap-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3 text-sm text-fg-muted">
          <Wordmark />
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
          <a
            href="/dashboard"
            className="text-fg-muted transition-colors hover:text-fg"
          >
            Dashboard
          </a>
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
