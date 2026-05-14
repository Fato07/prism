"use client";

/**
 * Web3Provider — client component wrapping children with wagmi + react-query.
 *
 * Implements the Reown cookie-state SSR pattern:
 *   1. Server layout calls `headers().get('cookie')` and passes it as the
 *      `cookies` prop.
 *   2. On mount, `cookieToInitialState()` hydrates wagmi's store from the
 *      cookie so the client tree matches the server-rendered markup.
 *   3. `createAppKit()` is called once (module-level side effect) to
 *      register the modal and the `<w3m-button>` custom element.
 *
 * Reference: https://docs.reown.com/appkit/next/core/installation
 */

import { wagmiAdapter, projectId } from "@/config";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createAppKit } from "@reown/appkit/react";
import { baseSepolia, base } from "@reown/appkit/networks";
import { arcTestnet } from "@prism/arc-contracts";
import type { ReactNode } from "react";
import { cookieToInitialState, WagmiProvider } from "wagmi";
import type { Config } from "wagmi";

// ── Query client (singleton per client boundary) ──────────────────────
const queryClient = new QueryClient();

// ── AppKit metadata ──────────────────────────────────────────────────
const metadata = {
  name: "Prism",
  description: "The First Adversarial AI Validator on ERC-8004",
  url: process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3200",
  icons: ["/icon.svg"],
};

// ── Initialize AppKit modal (singleton side-effect) ──────────────────
// createAppKit must be called inside a client component file.
// It registers the <w3m-button> / <appkit-button> custom elements globally.
createAppKit({
  adapters: [wagmiAdapter],
  projectId,
  networks: [arcTestnet, baseSepolia, base],
  defaultNetwork: arcTestnet,
  metadata,
  features: {
    analytics: true,
    email: true,
    socials: ["google", "x", "farcaster"],
    onramp: true,
    swaps: false,
  },
});

// ── Provider component ───────────────────────────────────────────────
interface Web3ProviderProps {
  children: ReactNode;
  /** Cookie string from `headers().get('cookie')` — bridges SSR state. */
  cookies: string | null;
}

function Web3Provider({ children, cookies }: Web3ProviderProps) {
  const initialState = cookieToInitialState(
    wagmiAdapter.wagmiConfig as Config,
    cookies
  );

  return (
    <WagmiProvider
      config={wagmiAdapter.wagmiConfig as Config}
      initialState={initialState}
    >
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </WagmiProvider>
  );
}

export default Web3Provider;
