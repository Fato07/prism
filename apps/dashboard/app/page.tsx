/**
 * Prism Landing Page — Root route (/)
 *
 * Waitlist landing page with pitch section, email signup, waitlist count,
 * and link to live dashboard. Mobile-responsive. SEO meta tags in layout.
 */

import type { Metadata } from "next";
import { getWaitlistCount, ensureWaitlistTable } from "@/lib/db";
import { WaitlistSignupForm } from "@/components/waitlist-form";

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

const BENEFITS = [
  {
    icon: "🛡️",
    title: "Adversarial Validation",
    description:
      "Two-agent adversarial validation catches flawed AI reasoning before it moves markets",
  },
  {
    icon: "⛓️",
    title: "On-Chain Proof",
    description:
      "On-chain proof on Arc — every verdict is immutable, verifiable, and gasless",
  },
  {
    icon: "💸",
    title: "Sentinel-as-a-Service",
    description:
      "Sentinel-as-a-service: other agents pay per validation via x402 nanopayments",
  },
] as const;

export default async function LandingPage() {
  // Ensure table exists and get count
  let waitlistCount = 0;
  try {
    await ensureWaitlistTable();
    waitlistCount = await getWaitlistCount();
  } catch {
    // DB not available — show page anyway with count 0
  }

  const countDisplay =
    waitlistCount > 0
      ? `Join ${waitlistCount} other${waitlistCount !== 1 ? "s" : ""} on the waitlist`
      : "Be the first to join the waitlist";

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex flex-col">
      {/* Nav */}
      <nav className="border-b border-gray-800/50 bg-gray-950/80 px-6 py-4 backdrop-blur-sm sticky top-0 z-50">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <a href="/" className="text-xl font-bold tracking-tight">
            <span className="text-blue-400">Prism</span>
          </a>
          <a
            href="/dashboard"
            className="rounded-lg border border-gray-700 px-4 py-2 text-sm font-medium text-gray-300 transition-colors hover:border-gray-500 hover:text-white"
          >
            Live Dashboard
          </a>
        </div>
      </nav>

      {/* Hero */}
      <main className="flex-1 flex flex-col items-center justify-center px-6 py-16 sm:py-24">
        <div className="mx-auto max-w-3xl text-center">
          {/* Tagline */}
          <p className="mb-4 text-sm font-medium uppercase tracking-widest text-blue-400">
            The first adversarial AI validator on ERC-8004
          </p>

          {/* Main headline */}
          <h1 className="mb-6 text-4xl font-extrabold tracking-tight sm:text-5xl lg:text-6xl">
            See through the{" "}
            <span className="bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
              reasoning
            </span>
          </h1>

          {/* Subtitle */}
          <p className="mb-10 text-lg text-gray-400 sm:text-xl max-w-2xl mx-auto">
            AI agents trade on prediction markets. But who checks their reasoning?
            Prism pits a sentinel against every trade — catching flaws before capital
            moves. On-chain. Gasless. Verifiable.
          </p>

          {/* Waitlist signup */}
          <div className="mb-6">
            <p className="mb-4 text-sm text-gray-500">{countDisplay}</p>
            <div className="mx-auto max-w-md relative">
              <WaitlistSignupForm />
            </div>
          </div>
        </div>

        {/* Benefits */}
        <div className="mx-auto mt-16 max-w-4xl w-full">
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
            {BENEFITS.map((benefit) => (
              <div
                key={benefit.title}
                className="rounded-xl border border-gray-800 bg-gray-900/50 p-6 transition-colors hover:border-gray-700"
              >
                <div className="mb-3 text-2xl">{benefit.icon}</div>
                <h3 className="mb-2 text-base font-semibold text-gray-100">
                  {benefit.title}
                </h3>
                <p className="text-sm text-gray-400 leading-relaxed">
                  {benefit.description}
                </p>
              </div>
            ))}
          </div>
        </div>

        {/* Tech stack badges */}
        <div className="mt-16 flex flex-wrap items-center justify-center gap-3 text-xs text-gray-500">
          <span className="rounded-full bg-gray-900 px-3 py-1 border border-gray-800">Arc</span>
          <span className="rounded-full bg-gray-900 px-3 py-1 border border-gray-800">ERC-8004</span>
          <span className="rounded-full bg-gray-900 px-3 py-1 border border-gray-800">Circle Wallets</span>
          <span className="rounded-full bg-gray-900 px-3 py-1 border border-gray-800">x402</span>
          <span className="rounded-full bg-gray-900 px-3 py-1 border border-gray-800">Polymarket</span>
          <span className="rounded-full bg-gray-900 px-3 py-1 border border-gray-800">Neon</span>
        </div>

        {/* CTA to dashboard */}
        <div className="mt-12">
          <a
            href="/dashboard"
            className="inline-flex items-center gap-2 rounded-lg bg-gray-900 border border-gray-700 px-6 py-3 text-sm font-medium text-gray-300 transition-colors hover:bg-gray-800 hover:text-white"
          >
            View Live Dashboard
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
            </svg>
          </a>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-800 px-6 py-6">
        <div className="mx-auto max-w-5xl flex flex-col items-center gap-2 sm:flex-row sm:justify-between">
          <p className="text-xs text-gray-600">
            The first adversarial AI validator on ERC-8004 · Powered by Arc &amp; Circle
          </p>
          <div className="flex items-center gap-4 text-xs text-gray-600">
            <a href="/dashboard" className="hover:text-gray-400 transition-colors">
              Dashboard
            </a>
            <span>·</span>
            <a
              href="https://github.com/Fato07/prism"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-gray-400 transition-colors"
            >
              GitHub
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
