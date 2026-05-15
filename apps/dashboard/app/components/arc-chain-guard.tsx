"use client";

/**
 * ArcChainGuard — prompts the connected wallet to switch to Arc Testnet
 * after the initial connection on a different chain (e.g., Base Sepolia).
 *
 * Why this exists:
 *   MetaMask doesn't natively recognize Arc Testnet (chain 5042002).
 *   When AppKit's defaultNetwork is set to a well-known chain (Base Sepolia),
 *   the wallet connects successfully on that chain. This guard then calls
 *   wagmi's switchChain, which triggers wallet_addEthereumChain under the
 *   hood (because MetaMask doesn't know Arc Testnet). The chain definition's
 *   rpcUrls must contain the absolute public URL for this to work.
 *
 * The guard is non-blocking: if the user rejects the chain switch, the app
 * still functions on whatever chain they're on. The submit-form's own
 * switchChainAsync handles the chain switch at transaction time.
 *
 * Why switchChain is stored in a ref:
 *   useSwitchChain() returns a new function reference on every render.
 *   Putting it directly in the useEffect dependency array causes the effect
 *   to fire on every render → triggers switchChain → state update → re-render,
 *   creating an infinite loop (React #310). Storing it in a ref breaks this
 *   cycle while keeping the function reference current.
 */

import { useAccount, useSwitchChain } from "wagmi";
import { useEffect, useRef } from "react";
import { arcTestnet } from "@/config";

const ARC_CHAIN_ID = arcTestnet.id;

export function ArcChainGuard() {
  const { isConnected, chainId } = useAccount();
  const { switchChain } = useSwitchChain();
  const switchChainRef = useRef(switchChain);
  const promptedRef = useRef(false);

  // Keep the ref current so the main effect always calls the latest switchChain
  useEffect(() => {
    switchChainRef.current = switchChain;
  }, [switchChain]);

  useEffect(() => {
    // Only prompt once per connection session, and only when the
    // wallet is connected but not on Arc Testnet.
    if (!isConnected || chainId === ARC_CHAIN_ID || promptedRef.current) {
      return;
    }

    promptedRef.current = true;

    // Attempt to switch to Arc Testnet. If the user rejects or the
    // wallet can't add the chain, this fails silently — the app
    // will prompt again at transaction time (see submit-form.tsx).
    try {
      switchChainRef.current?.({ chainId: ARC_CHAIN_ID });
    } catch {
      // Silently ignore — the user can switch later from the
      // AppKit network selector or the submit form.
    }
  }, [isConnected, chainId]); // switchChain removed from deps

  // Reset the prompt flag when the wallet disconnects
  useEffect(() => {
    if (!isConnected) {
      promptedRef.current = false;
    }
  }, [isConnected]);

  return null; // No UI — this is a side-effect-only component
}
