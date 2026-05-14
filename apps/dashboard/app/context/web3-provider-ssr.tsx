"use client";

/**
 * Client-side wrapper that dynamically imports Web3Provider with SSR disabled.
 *
 * Reown AppKit's `createAppKit()` calls React hooks internally, which crashes
 * during server-side rendering with "Cannot read properties of null (reading
 * 'useRef')". This wrapper uses `next/dynamic` with `ssr: false` so the
 * module (and its module-level `createAppKit()` side-effect) only executes
 * client-side.
 *
 * The `cookies` prop is still passed for client-side hydration but the SSR
 * path renders only children (no wallet context on server).
 */

import dynamic from "next/dynamic";
import type { ReactNode } from "react";

const Web3Provider = dynamic(
  () => import("@/context/web3-provider").then((mod) => mod.default),
  {
    ssr: false,
  }
);

interface Web3ProviderSSRProps {
  children: ReactNode;
  /** Cookie string — ignored on server, used for client hydration. */
  cookies: string | null;
}

export default function Web3ProviderDynamic({
  children,
  cookies,
}: Web3ProviderSSRProps) {
  return <Web3Provider cookies={cookies}>{children}</Web3Provider>;
}
