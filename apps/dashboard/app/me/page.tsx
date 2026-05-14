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
import { GlobalNav } from "@/components/global-nav";
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
      <GlobalNav currentPage="me" />

      <main className="mx-auto max-w-5xl px-6 pb-16 pt-8">
        <MeWalletPanel />
      </main>
    </div>
  );
}

