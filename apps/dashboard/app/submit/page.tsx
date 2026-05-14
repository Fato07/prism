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
import { GlobalNav } from "@/components/global-nav";
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
      <GlobalNav currentPage="submit" />

      <main className="mx-auto max-w-5xl px-6 pb-16 pt-8">
        <BridgeWidget />
        <SubmitForm />
      </main>
    </div>
  );
}

