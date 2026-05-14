/**
 * /me Page — Connected wallet's verdict history
 *
 * Server component shell that renders a header (nav + ConnectWalletButton)
 * and delegates to the client-side <MeWalletPanel> for wallet-aware logic.
 *
 * VAL-ME-001: Returns 200 even when no wallet connected.
 * VAL-ME-002: Disconnected state shows CTA card, not empty page.
 * VAL-ME-003: Connected state fetches verdicts for the connected address.
 * VAL-ME-004: Connected state with verdicts renders the same card grid as /history.
 * VAL-ME-005: Address is lower-cased before query and rendered via <HashChip>.
 */

import type { Metadata } from "next";
import { ConnectWalletButton } from "@/components/connect-wallet-button";
import { Separator } from "@/components/ui/separator";
import { ArrowLeft } from "lucide-react";
import { MeWalletPanel } from "./me-wallet-panel";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "My Verdicts",
  description:
    "View your adversarial validation verdict history on Prism. Connect your wallet to see verdicts you requested.",
};

export default function MePage() {
  return (
    <div className="min-h-screen bg-canvas text-fg">
      <MeHeader />

      <main className="mx-auto max-w-5xl px-6 pb-16 pt-8">
        <MeWalletPanel />
      </main>
    </div>
  );
}

/* ─────────────── Header ─────────────── */

function MeHeader() {
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
          My Verdicts
        </h1>
      </div>
    </header>
  );
}
