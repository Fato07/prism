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
 * Absolute Arc Testnet RPC URL.
 *
 * This MUST be an absolute, publicly accessible HTTPS URL because
 * MetaMask uses it when calling wallet_addEthereumChain for custom
 * chains. A relative URL like /api/rpc/arc is NOT resolvable by
 * MetaMask's extension background process and causes silent chain-
 * addition failures (the root cause of the MetaMask auth bug).
 *
 * Server and client both use the absolute URL in the chain definition.
 * CORS is handled separately: wagmi's HTTP transport uses the same-
 * origin proxy (/api/rpc/arc) to bypass CORS, while MetaMask calls
 * the RPC from its own background context (no CORS restriction).
 */
const arcPublicRpcUrl =
  process.env.ARC_RPC_URL ?? process.env.NEXT_PUBLIC_ARC_RPC_URL!;

/**
 * Same-origin proxy URL for wagmi's browser-side HTTP transport.
 * Bypasses CORS restrictions on the Arc Testnet RPC endpoint.
 * Only used in the WagmiAdapter transports config, NOT in the
 * chain definition's rpcUrls (which MetaMask reads).
 */
const arcProxyRpcUrl =
  typeof window === "undefined" ? arcPublicRpcUrl : "/api/rpc/arc";

export const arcTestnet = defineChain({
  ...arcTestnetBase,
  rpcUrls: {
    default: { http: [arcPublicRpcUrl] },
  },
  // Defensive fallback: arcTestnetBase already defines blockExplorers, but
  // if it's ever missing, this prevents Reown AppKit web components from
  // rendering SVGs with empty width/height attributes (which crashes the
  // /submit page on the deployed dashboard).
  blockExplorers: arcTestnetBase.blockExplorers ?? {
    default: {
      name: "Arc Scan",
      url: "https://explorer.arc-testnet.thecanteenapp.com",
    },
  },
  // Reown AppKit uses assets.imageUrl to render chain icons in its web
  // components. Without it, custom chains get an <svg width="" height="">
  // which throws in strict rendering. Arc's icon is served from /public.
  assets: {
    imageId: undefined,
    imageUrl: "/icon.svg",
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
    // Arc Testnet uses the CORS-bypassing proxy on the browser,
    // or the direct URL on the server. MetaMask's wallet_addEthereumChain
    // reads rpcUrls from the chain definition (absolute URL), NOT this transport.
    [arcTestnet.id]: http(arcProxyRpcUrl),
  },
});

/** Typed wagmi config — re-exported for convenience. */
export const config = wagmiAdapter.wagmiConfig;
