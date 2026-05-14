/**
 * /submit Page — Self-serve validation with x402 payment
 *
 * Server component shell that renders a header (nav + ConnectWalletButton)
 * and delegates to the client-side <SubmitForm> for wallet-aware logic.
 *
 * VAL-SUBMIT-001: Returns 200 with form even when no wallet connected.
 * VAL-SUBMIT-003: Submit triggers connect flow when wallet not yet connected.
 * VAL-SUBMIT-009: Responsive at mobile width (375 × 812).
 */

import type { Metadata } from "next";
import { ConnectWalletButton } from "@/components/connect-wallet-button";
import { Separator } from "@/components/ui/separator";
import { ArrowLeft } from "lucide-react";
import { SubmitForm } from "./submit-form";
import { BridgeWidget } from "./bridge-widget";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Submit Trace",
  description:
    "Submit a reasoning trace for adversarial validation. Paste an IPFS CID, connect your wallet, and pay 0.01 USDC via x402 for a sentinel verdict.",
};

export default function SubmitPage() {
  return (
    <div className="min-h-screen bg-canvas text-fg">
      <SubmitHeader />

      <main className="mx-auto max-w-5xl px-6 pb-16 pt-8">
        <BridgeWidget />
        <SubmitForm />
      </main>
    </div>
  );
}

/* ─────────────── Header ─────────────── */

function SubmitHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-[var(--color-border)] bg-[var(--color-canvas)]/80 backdrop-blur-md">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-4 gap-y-2 px-6 py-3">
        <ConnectWalletButton />
        <a
          href="/dashboard"
          className="inline-flex items-center gap-1.5 text-sm text-fg-muted transition-colors hover:text-fg"
        >
          <ArrowLeft className="h-4 w-4" strokeWidth={2} />
          Dashboard
        </a>
        <Separator orientation="vertical" className="h-4" />
        <a
          href="/history"
          className="inline-flex items-center gap-1 text-sm text-fg-muted transition-colors hover:text-fg"
        >
          History
        </a>
        <Separator orientation="vertical" className="h-4" />
        <h1 className="text-base font-semibold tracking-[var(--tracking-tight)] text-fg">
          Submit Trace
        </h1>
      </div>
    </header>
  );
}
