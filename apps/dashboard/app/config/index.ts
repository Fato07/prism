/**
 * Wagmi + Reown AppKit configuration (shared between server and client).
 *
 * This file MUST NOT have a 'use client' directive because it is imported
 * by both the server-side layout (to derive cookie initialState) and the
 * client-side Web3Provider context.
 *
 * Pattern: https://docs.reown.com/appkit/next/core/installation
 */

import { cookieStorage, createStorage, http } from "@wagmi/core";
import { WagmiAdapter } from "@reown/appkit-adapter-wagmi";
import {
  baseSepolia,
  base,
  defineChain,
  type AppKitNetwork,
} from "@reown/appkit/networks";
import { arcTestnet as arcTestnetBase } from "@prism/arc-contracts";

/** Reown project ID — public-safe, no secret. Guaranteed string after guard. */
const _rawProjectId = process.env.NEXT_PUBLIC_REOWN_PROJECT_ID;
if (!_rawProjectId) {
  throw new Error(
    "NEXT_PUBLIC_REOWN_PROJECT_ID is not set. " +
      "Obtain one from https://dashboard.reown.com and add it to your .env.local"
  );
}
export const projectId: string = _rawProjectId;

/**
 * Arc Testnet with proxy-aware RPC URL.
 *
 * Server (SSR) uses the direct Arc RPC URL — no CORS in Node.js.
 * Browser uses the same-origin proxy (/api/rpc/arc) to bypass
 * CORS restrictions on the Arc Testnet RPC endpoint.
 */
const arcRpcUrl =
  typeof window === "undefined"
    ? (process.env.ARC_RPC_URL ?? process.env.NEXT_PUBLIC_ARC_RPC_URL!)
    : "/api/rpc/arc";

export const arcTestnet = defineChain({
  ...arcTestnetBase,
  rpcUrls: {
    default: { http: [arcRpcUrl] },
  },
});

/** Networks available in the AppKit modal. */
export const networks: [AppKitNetwork, ...AppKitNetwork[]] = [
  arcTestnet,
  baseSepolia,
  base,
];

/**
 * WagmiAdapter — the bridge between wagmi and Reown AppKit.
 * `cookieStorage` + `ssr: true` enables the cookie-state SSR pattern
 * that avoids hydration mismatches between server and client renders.
 */
export const wagmiAdapter = new WagmiAdapter({
  storage: createStorage({
    storage: cookieStorage,
  }),
  ssr: true,
  projectId,
  networks,
  transports: {
    [arcTestnet.id]: http(arcRpcUrl),
  },
});

/** Typed wagmi config — re-exported for convenience. */
export const config = wagmiAdapter.wagmiConfig;
