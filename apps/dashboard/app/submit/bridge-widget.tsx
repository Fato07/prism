"use client";

/**
 * BridgeWidget — conditionally renders a Circle App Kit bridge UI when
 * the connected wallet has insufficient USDC on the target x402 payment chain.
 *
 * VAL-BRIDGE-002: Widget renders ONLY when USDC < 0.01 on target chain.
 * VAL-BRIDGE-003: Destination defaults to Base Sepolia (or Arc Testnet
 *   when X402_FACILITATOR_MODE=circle).
 * VAL-BRIDGE-004: No layout shift when hidden — returns null, no placeholder.
 * VAL-BRIDGE-005: Styled to match shadcn dark theme.
 *
 * The bridge uses Circle's App Kit (`@circle-fin/app-kit`) with the
 * viem adapter (`@circle-fin/adapter-viem-v2`) to perform CCTPv2
 * cross-chain USDC transfers via the connected browser wallet.
 */

import { useCallback, useState } from "react";
import { useAccount, useWalletClient, useReadContract } from "wagmi";
import { AppKit, BridgeChain } from "@circle-fin/app-kit";
import { createAdapterFromProvider } from "@circle-fin/adapter-viem-v2";
import { Card, CardContent } from "@/components/ui/card";
import { ArrowRightLeft, Loader2, CheckCircle2, AlertTriangle } from "lucide-react";
import { X402_NETWORKS, DEFAULT_X402_NETWORK } from "./lib/x402-client";

/* ─────────────── Constants ─────────────── */

/** Minimum USDC balance required on the target chain (0.01 USDC = 10_000 in 6-decimal units). */
const MIN_USDC_UNITS = BigInt(10000);

/** USDC ERC-20 ABI — only the `balanceOf` function is needed. */
const USDC_ABI = [
  {
    inputs: [{ name: "account", type: "address" }],
    name: "balanceOf",
    outputs: [{ name: "", type: "uint256" }],
    stateMutability: "view",
    type: "function",
  },
] as const;

/**
 * Determine the destination chain for bridging based on the x402 facilitator mode.
 *
 * When X402_FACILITATOR_MODE=circle and Gateway supports it, destination is Arc Testnet.
 * Otherwise, default to Base Sepolia (the standard x402 settlement chain).
 */
function getDestinationChain(): BridgeChain {
  const mode = process.env.NEXT_PUBLIC_X402_FACILITATOR_MODE ?? "public";
  if (mode === "circle") {
    return BridgeChain.Arc_Testnet;
  }
  return BridgeChain.Base_Sepolia;
}

/**
 * Get the destination chain ID (for useReadContract).
 * Matches the x402 network config.
 */
function getDestinationChainId(): number {
  const mode = process.env.NEXT_PUBLIC_X402_FACILITATOR_MODE ?? "public";
  if (mode === "circle") {
    return 5042002; // Arc Testnet
  }
  return X402_NETWORKS[DEFAULT_X402_NETWORK].chainId; // Base Sepolia (84532)
}

/**
 * Get the USDC contract address for the destination chain.
 */
function getDestinationUsdcAddress(): `0x${string}` {
  const mode = process.env.NEXT_PUBLIC_X402_FACILITATOR_MODE ?? "public";
  if (mode === "circle") {
    // Arc Testnet USDC native gas token address
    return "0x3600000000000000000000000000000000000000" as const;
  }
  return X402_NETWORKS[DEFAULT_X402_NETWORK].usdcAddress;
}

/** Bridge amount: 0.05 USDC (gives some buffer above the 0.01 minimum). */
const BRIDGE_AMOUNT = "0.05";

/* ─────────────── Types ─────────────── */

type BridgePhase = "idle" | "bridging" | "success" | "error";

type BridgeSourceStatus =
  | { kind: "supported"; sourceChain: BridgeChain; sourceChainName: string }
  | { kind: "same-destination"; sourceChainName: string }
  | { kind: "unsupported"; sourceChainName: string };

/** Map an EVM chain ID to Circle App Kit's BridgeChain enum. */
export function chainIdToBridgeChain(chainId: number | undefined): BridgeChain | null {
  switch (chainId) {
    case 84532:
      return BridgeChain.Base_Sepolia;
    case 8453:
      return BridgeChain.Base;
    case 5042002:
      return BridgeChain.Arc_Testnet;
    case 11155111:
      return BridgeChain.Ethereum_Sepolia;
    case 421614:
      return BridgeChain.Arbitrum_Sepolia;
    case 43113:
      return BridgeChain.Avalanche_Fuji;
    case 11155420:
      return BridgeChain.Optimism_Sepolia;
    default:
      return null;
  }
}

/** Human-readable name for supported source/destination chains. */
function bridgeChainName(chain: BridgeChain | null): string {
  switch (chain) {
    case BridgeChain.Base_Sepolia:
      return "Base Sepolia";
    case BridgeChain.Base:
      return "Base";
    case BridgeChain.Arc_Testnet:
      return "Arc Testnet";
    case BridgeChain.Ethereum_Sepolia:
      return "Ethereum Sepolia";
    case BridgeChain.Arbitrum_Sepolia:
      return "Arbitrum Sepolia";
    case BridgeChain.Avalanche_Fuji:
      return "Avalanche Fuji";
    case BridgeChain.Optimism_Sepolia:
      return "Optimism Sepolia";
    default:
      return "this network";
  }
}

/** True for testnet bridge routes that can plausibly fund testnet x402. */
function isTestnetBridgeSource(chain: BridgeChain): boolean {
  return [
    BridgeChain.Arc_Testnet,
    BridgeChain.Base_Sepolia,
    BridgeChain.Ethereum_Sepolia,
    BridgeChain.Arbitrum_Sepolia,
    BridgeChain.Avalanche_Fuji,
    BridgeChain.Optimism_Sepolia,
  ].includes(chain);
}

/**
 * Decide whether the current wallet network can be used as a source for
 * the destination x402 payment chain.
 *
 * Critical UX guard: never call Circle App Kit with from === to. Circle
 * correctly rejects Base Sepolia → Base Sepolia with "route not supported";
 * in that case the right action is funding the destination chain directly.
 */
export function getBridgeSourceStatus(
  sourceChainId: number | undefined,
  destinationChain: BridgeChain,
): BridgeSourceStatus {
  const sourceChain = chainIdToBridgeChain(sourceChainId);
  const sourceChainName = bridgeChainName(sourceChain);

  if (!sourceChain) {
    return { kind: "unsupported", sourceChainName };
  }

  if (sourceChain === destinationChain) {
    return { kind: "same-destination", sourceChainName };
  }

  // Public x402 settles on Base Sepolia today. Do not suggest mainnet→testnet
  // bridging (e.g. Base → Base Sepolia); Circle/AppKit won't support that and
  // it confuses users who simply need testnet USDC from a faucet.
  if (destinationChain === BridgeChain.Base_Sepolia && !isTestnetBridgeSource(sourceChain)) {
    return { kind: "unsupported", sourceChainName };
  }

  return { kind: "supported", sourceChain, sourceChainName };
}

/* ─────────────── Component ─────────────── */

export function BridgeWidget() {
  const { address, isConnected, chainId } = useAccount();
  const { data: walletClient } = useWalletClient();

  const destinationChainId = getDestinationChainId();
  const destinationUsdcAddress = getDestinationUsdcAddress();

  // Read USDC balance on the destination chain
  const { data: usdcBalance, refetch } = useReadContract({
    address: destinationUsdcAddress,
    abi: USDC_ABI,
    functionName: "balanceOf",
    args: address ? [address] : undefined,
    chainId: destinationChainId,
    query: {
      enabled: isConnected && !!address,
    },
  });

  const [phase, setPhase] = useState<BridgePhase>("idle");
  const [bridgeError, setBridgeError] = useState<string | null>(null);

  /* ── Bridge handler ────────────────────────────────────────── */

  const handleBridge = useCallback(async () => {
    if (!walletClient || !address) return;

    setPhase("bridging");
    setBridgeError(null);

    try {
      // Get the EIP-1193 provider from the wallet
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- window.ethereum is untyped
      const provider = (window as any).ethereum;
      if (!provider) {
        throw new Error("No browser wallet provider found. Please use a Web3-compatible browser.");
      }

      // Create viem adapter from the browser provider
      const adapter = await createAdapterFromProvider({ provider });

      // Initialize App Kit
      const kit = new AppKit();

      const destinationChain = getDestinationChain();
      // Source chain = whatever chain the wallet is currently on. Prefer
      // wagmi's reactive account chainId; walletClient.chain can be undefined
      // for WalletConnect/Reown sessions and previously fell back to Base
      // Sepolia, causing invalid Base Sepolia → Base Sepolia bridge attempts.
      const sourceStatus = getBridgeSourceStatus(chainId ?? walletClient.chain?.id, destinationChain);
      if (sourceStatus.kind !== "supported") {
        throw new Error(
          sourceStatus.kind === "same-destination"
            ? `You're already on ${bridgeChainName(destinationChain)}. Add testnet USDC directly instead of bridging.`
            : `${sourceStatus.sourceChainName} cannot bridge into ${bridgeChainName(destinationChain)} for this testnet payment flow.`,
        );
      }
      const sourceChain = sourceStatus.sourceChain;

      const result = await kit.bridge({
        from: { adapter, chain: sourceChain },
        to: { adapter, chain: destinationChain },
        amount: BRIDGE_AMOUNT,
        token: "USDC",
      });

      if (result.state === "error") {
        const failedStep = result.steps.find((s) => s.error);
        const errorMsg = failedStep?.error;
        throw new Error(
          (errorMsg && typeof errorMsg === "object" && "message" in errorMsg
            ? (errorMsg as { message: string }).message
            : undefined) ?? "Bridge operation failed",
        );
      }

      setPhase("success");
      // Refresh the balance after a short delay to reflect the bridge
      setTimeout(() => {
        void refetch();
      }, 5000);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Bridge operation failed unexpectedly";
      setBridgeError(message);
      setPhase("error");
    }
  }, [walletClient, address, chainId, refetch]);

  /* ── Determine visibility ───────────────────────────────────── */

  const hasSufficientBalance = usdcBalance !== undefined && usdcBalance >= MIN_USDC_UNITS;

  // Hide when: wallet disconnected, balance sufficient, or balance still loading
  // but wallet IS connected and we have a definitive insufficient balance → show
  if (!isConnected || !address || hasSufficientBalance) {
    // VAL-BRIDGE-004: Return null (no placeholder) to avoid CLS
    return null;
  }

  // If balance is still loading (undefined) but wallet is connected and we know
  // it's not sufficient (undefined means not loaded yet), don't show either —
  // wait for the query to resolve. This prevents flash-of-widget.
  if (usdcBalance === undefined) {
    return null;
  }

  /* ── Derive display names ─────────────────────────────────────── */

  const destinationChain = getDestinationChain();
  const destinationChainName = bridgeChainName(destinationChain);
  const sourceStatus = getBridgeSourceStatus(chainId ?? walletClient?.chain?.id, destinationChain);
  const canBridge = sourceStatus.kind === "supported";

  /* ── Render ─────────────────────────────────────────────────── */

  return (
    <div className="mb-4">
      <Card tone="default">
        <CardContent className="flex flex-col gap-3 py-4">
          {/* Header */}
          <div className="flex items-center gap-3">
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-[var(--color-trader)]/10">
              <ArrowRightLeft className="h-3.5 w-3.5 text-[var(--color-trader)]" strokeWidth={2} />
            </div>
            <div>
              <h3 className="text-xs font-semibold text-fg">
                Insufficient USDC on {destinationChainName}
              </h3>
              <p className="text-xs text-fg-faint">
                {canBridge
                  ? `Bridge ${BRIDGE_AMOUNT} USDC to proceed with validation`
                  : sourceStatus.kind === "same-destination"
                    ? "You are already on the payment chain. Add testnet USDC directly, then refresh."
                    : `${sourceStatus.sourceChainName} cannot fund this testnet payment route. Switch to a supported testnet source or use the faucet.`}
              </p>
            </div>
          </div>

          {/* Bridge button / same-chain funding guidance */}
          {phase === "idle" && canBridge && (
            <button
              type="button"
              onClick={handleBridge}
              className={`
                flex items-center justify-center gap-2 rounded-lg px-3 py-2
                text-xs font-medium transition-colors
                focus:outline-none focus:ring-2 focus:ring-[var(--color-trader)]/40
                min-h-[44px] /* VAL-SUBMIT-009: 44px hit target */
                bg-[var(--color-trader)] text-canvas hover:bg-[var(--color-trader)]/90
              `}
            >
              <ArrowRightLeft className="h-3.5 w-3.5" strokeWidth={2} />
              Bridge {BRIDGE_AMOUNT} USDC from {sourceStatus.sourceChainName} to {destinationChainName}
            </button>
          )}

          {phase === "idle" && !canBridge && (
            <div className="flex flex-col gap-2 rounded-lg border border-[var(--border)] bg-elevated/40 px-3 py-2">
              <p className="text-xs text-fg-muted">
                {sourceStatus.kind === "same-destination"
                  ? `Because your wallet is already on ${destinationChainName}, there is no cross-chain route to run. Fund ${destinationChainName} USDC directly, then refresh this balance check.`
                  : `This payment flow settles on ${destinationChainName}. ${sourceStatus.sourceChainName} is not a supported source for that testnet route.`}
              </p>
              <div className="flex flex-wrap gap-2">
                <a
                  href="https://faucet.circle.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex min-h-[36px] items-center justify-center rounded-lg bg-[var(--color-trader)] px-3 text-xs font-medium text-canvas hover:bg-[var(--color-trader)]/90"
                >
                  Open Circle faucet
                </a>
                <button
                  type="button"
                  onClick={() => void refetch()}
                  className="inline-flex min-h-[36px] items-center justify-center rounded-lg border border-[var(--border)] px-3 text-xs font-medium text-fg-muted transition-colors hover:text-fg"
                >
                  Refresh balance
                </button>
              </div>
            </div>
          )}

          {/* Bridging in progress */}
          {phase === "bridging" && (
            <div className="flex items-center gap-2 rounded-lg border border-[var(--color-trader)]/30 bg-[var(--color-trader)]/5 px-3 py-2">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-[var(--color-trader)]" strokeWidth={2} />
              <span className="text-xs text-[var(--color-trader)]">
                Bridging USDC... Check your wallet for signature requests.
              </span>
            </div>
          )}

          {/* Success */}
          {phase === "success" && (
            <div className="flex items-center gap-2 rounded-lg border border-[var(--color-success)]/30 bg-[var(--color-success)]/5 px-3 py-2">
              <CheckCircle2 className="h-3.5 w-3.5 text-[var(--color-success)]" strokeWidth={2} />
              <span className="text-xs text-[var(--color-success)]">
                Bridge initiated! Balance will update shortly. You may need to switch networks.
              </span>
            </div>
          )}

          {/* Error */}
          {phase === "error" && bridgeError && (
            <div className="flex flex-col gap-2">
              <div
                role="alert"
                className="flex items-start gap-2 rounded-lg border border-[var(--color-danger)]/30 bg-[var(--color-danger)]/5 px-3 py-2"
              >
                <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-[var(--color-danger)] mt-0.5" strokeWidth={2} />
                <span className="text-xs text-[var(--color-danger)]">{bridgeError}</span>
              </div>
              <button
                type="button"
                onClick={() => {
                  setPhase("idle");
                  setBridgeError(null);
                }}
                className="text-xs text-fg-faint underline decoration-fg-faint/30 hover:decoration-fg-faint transition-colors"
              >
                Try again
              </button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
