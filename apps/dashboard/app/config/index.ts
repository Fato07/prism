/**
 * Wagmi + Reown AppKit configuration (shared between server and client).
 *
 * This file MUST NOT have a 'use client' directive because it is imported
 * by both the server-side layout (to derive cookie initialState) and the
 * client-side Web3Provider context.
 *
 * Pattern: https://docs.reown.com/appkit/next/core/installation
 */

import { cookieStorage, createStorage } from "@wagmi/core";
import { WagmiAdapter } from "@reown/appkit-adapter-wagmi";
import { baseSepolia, base } from "@reown/appkit/networks";
import { arcTestnet } from "@prism/arc-contracts";

/** Reown project ID — public-safe, no secret. Guaranteed string after guard. */
const _rawProjectId = process.env.NEXT_PUBLIC_REOWN_PROJECT_ID;
if (!_rawProjectId) {
  throw new Error(
    "NEXT_PUBLIC_REOWN_PROJECT_ID is not set. " +
      "Obtain one from https://dashboard.reown.com and add it to your .env.local"
  );
}
export const projectId: string = _rawProjectId;

/** Networks available in the AppKit modal. */
const networks = [arcTestnet, baseSepolia, base];

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
});

/** Typed wagmi config — re-exported for convenience. */
export const config = wagmiAdapter.wagmiConfig;
