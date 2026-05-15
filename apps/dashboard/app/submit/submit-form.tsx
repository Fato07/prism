"use client";

/**
 * SubmitForm — client component for the /submit self-serve validation page.
 *
 * Flow:
 *   1. Visitor pastes an IPFS CID (client-side regex validation)
 *   2. If wallet not connected → clicking Validate opens Reown modal (appkit.open())
 *   3. If connected + valid CID → multi-step submit:
 *      a. Initiate: POST /api/validate/initiate → get payment requirements
 *      b. Sign: EIP-3009 transferWithAuthorization via viem walletClient
 *      c. Confirm: POST /api/validate/confirm → get trace_id
 *      d. Redirect: router.push(/trace/[traceId])
 *   4. Error states: invalid CID, sentinel error, x402 settlement failure
 *      — all render inline error messages under the form
 *
 * VAL-SUBMIT-002: CID regex rejects malformed inputs before network call.
 * VAL-SUBMIT-003: Connect gate prompts wallet connection if disconnected.
 * VAL-SUBMIT-005: Invalid-CID error shows friendly inline message.
 * VAL-SUBMIT-006: Sentinel error shows friendly inline message.
 * VAL-SUBMIT-007: x402 settlement failure shows friendly inline message.
 * VAL-SUBMIT-009: Responsive at mobile width (stack vertically at 375px).
 * VAL-SUBMIT-010: No console.log / console.error in production paths.
 */

import { useAccount, useSwitchChain, useWalletClient } from "wagmi";
import { useAppKit } from "@reown/appkit/react";
import { useRouter } from "next/navigation";
import { useState, useCallback, useId } from "react";
import {
  validateCid,
  signX402Payment,
  computeTraceHash,
  X402_NETWORKS,
  type X402NetworkId,
  type PaymentRequirements,
} from "./lib/x402-client";
import { Card, CardContent } from "@/components/ui/card";
import {
  Loader2,
  AlertTriangle,
  CheckCircle2,
  Shield,
} from "lucide-react";

/* ─────────────── Types ─────────────── */

type SubmitPhase =
  | "idle"
  | "initiating"
  | "signing"
  | "confirming"
  | "success"
  | "error";

/* ─────────────── Component ─────────────── */

export function SubmitForm() {
  const { address, isConnected, chainId } = useAccount();
  const { switchChainAsync } = useSwitchChain();
  const { data: walletClient } = useWalletClient();
  const { open: openAppKitModal } = useAppKit();
  const router = useRouter();

  const inputId = useId();

  const [cidInput, setCidInput] = useState("");
  const [cidError, setCidError] = useState<string | null>(null);
  const [phase, setPhase] = useState<SubmitPhase>("idle");
  const [inlineError, setInlineError] = useState<string | null>(null);

  /* ── CID validation on change ───────────────────────────────────── */

  const handleCidChange = useCallback(
    (value: string) => {
      setCidInput(value);
      // Only show error after user has typed something
      if (value.trim()) {
        const error = validateCid(value);
        setCidError(error);
      } else {
        setCidError(null);
      }
      // Clear inline error when user edits
      if (inlineError) setInlineError(null);
    },
    [inlineError],
  );

  /* ── Submit handler ────────────────────────────────────────────── */

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();

      // Step 0: Validate CID client-side
      const cidValidation = validateCid(cidInput);
      if (cidValidation) {
        setCidError(cidValidation);
        return; // VAL-SUBMIT-002: no network call for invalid CID
      }

      const cid = cidInput.trim();

      // Step 1: Ensure wallet connected
      if (!isConnected) {
        // VAL-SUBMIT-003: Open the Reown connect modal programmatically
        // instead of showing an inline error. The user clicked "Validate"
        // intentfully — guide them to connect rather than blocking silently.
        void openAppKitModal();
        return;
      }

      if (!walletClient || !address) {
        setInlineError("Wallet not available. Please reconnect and try again.");
        setPhase("error");
        return;
      }

      // Clear previous errors
      setInlineError(null);
      setCidError(null);

      try {
        // Compute trace_hash from CID
        const traceHash = await computeTraceHash(cid);
        const traceUri = `ipfs://${cid}`;

        // Phase 1: Initiate — get payment requirements (includes the target network)
        setPhase("initiating");

        const initiateResp = await fetch("/api/validate/initiate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ traceUri, traceHash }),
        });

        if (!initiateResp.ok) {
          const errBody = (await initiateResp.json().catch(() => ({ error: "Request failed" }))) as { error?: string; detail?: string };
          throw new Error(
            errBody.error ?? `Initiate failed (HTTP ${initiateResp.status})`,
          );
        }

        const initiateData = (await initiateResp.json()) as {
          sessionId: string;
          paymentRequirements: PaymentRequirements;
        };

        // Step 2: Ensure correct chain — use the network from the initiate response,
        // not a hardcoded default. This fixes the bug where signing against
        // base-sepolia (DEFAULT_X402_NETWORK) caused domain/chain ID mismatch
        // when the sentinel is configured for Arc Testnet.
        const targetNetwork = initiateData.paymentRequirements.network as X402NetworkId;
        const targetChainId = X402_NETWORKS[targetNetwork]?.chainId;
        if (!targetChainId) {
          throw new Error(
            `Unsupported payment network: ${initiateData.paymentRequirements.network}`,
          );
        }
        if (chainId !== targetChainId) {
          try {
            await switchChainAsync({ chainId: targetChainId });
          } catch {
            const networkLabel = targetNetwork === "arc-testnet" ? "Arc Testnet" : "Base Sepolia";
            setInlineError(
              `Please switch your wallet to ${networkLabel} to sign the payment.`,
            );
            setPhase("error");
            return;
          }
        }

        // Phase 2: Sign EIP-3009 payment via wallet using the network
        // from the initiate response — NOT the hardcoded DEFAULT_X402_NETWORK.
        setPhase("signing");

        const xPaymentBase64 = await signX402Payment(
          walletClient,
          address,
          initiateData.paymentRequirements,
          targetNetwork,
        );

        // Phase 3: Confirm — send signed payment to sentinel
        setPhase("confirming");

        const confirmResp = await fetch("/api/validate/confirm", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            sessionId: initiateData.sessionId,
            xPayment: xPaymentBase64,
            traceUri,
            traceHash,
          }),
        });

        if (!confirmResp.ok) {
          const errBody = (await confirmResp.json().catch(() => ({ error: "Request failed" }))) as { error?: string; detail?: string };
          throw new Error(
            errBody.error ?? `Confirm failed (HTTP ${confirmResp.status})`,
          );
        }

        const confirmData = (await confirmResp.json()) as {
          traceId: string;
          verdictScore: number;
          verdictLabel: string;
        };

        // Phase 4: Success — redirect to trace page
        setPhase("success");
        router.push(`/trace/${confirmData.traceId}`);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : "An unexpected error occurred";
        // VAL-SUBMIT-005/006/007: Friendly inline error
        setInlineError(message);
        setPhase("error");
      }
    },
    [cidInput, isConnected, walletClient, address, chainId, switchChainAsync, router, openAppKitModal],
  );

  /* ── Derived state ─────────────────────────────────────────────── */

  const isSubmitting = phase === "initiating" || phase === "signing" || phase === "confirming";
  const cidIsValid = cidInput.trim() && !validateCid(cidInput.trim());

  /* ── Phase labels for the loading indicator ─────────────────────── */

  const phaseLabel: Record<SubmitPhase, string> = {
    idle: "",
    initiating: "Connecting to sentinel...",
    signing: "Waiting for wallet signature...",
    confirming: "Running adversarial validation...",
    success: "Validation complete! Redirecting...",
    error: "",
  };

  /* ── Render ─────────────────────────────────────────────────────── */

  return (
    <div className="mx-auto max-w-lg">
      <Card tone="default">
        <CardContent className="flex flex-col gap-5 py-6">
          {/* Header */}
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--color-sentinel)]/10">
              <Shield className="h-4 w-4 text-[var(--color-sentinel)]" strokeWidth={2} />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-fg">Adversarial Validation</h2>
              <p className="text-xs text-fg-faint">
                Pay 0.01 USDC via x402 for a cross-model sentinel verdict
              </p>
            </div>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="flex flex-col gap-3">
            {/* CID input */}
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor={inputId}
                className="text-xs font-medium text-fg-muted"
              >
                IPFS CID
              </label>
              <input
                id={inputId}
                type="text"
                inputMode="text"
                autoComplete="off"
                placeholder="Qm... or bafy..."
                value={cidInput}
                onChange={(e) => handleCidChange(e.target.value)}
                disabled={isSubmitting}
                aria-label="IPFS CID of the reasoning trace to validate"
                aria-invalid={cidError !== null}
                aria-describedby={cidError ? `${inputId}-error` : undefined}
                className={`
                  w-full rounded-lg border bg-[var(--color-canvas-sunken)]/60 px-3 py-2.5
                  text-sm text-fg placeholder:text-fg-faint/50
                  transition-colors
                  focus:outline-none focus:ring-2 focus:ring-[var(--color-sentinel)]/40 focus:border-[var(--color-sentinel)]/60
                  disabled:opacity-50 disabled:cursor-not-allowed
                  ${cidError ? "border-[var(--color-danger)]/60" : "border-[var(--color-border)] hover:border-[var(--color-border-strong)]"}
                `}
              />
              {/* Inline CID validation error */}
              {cidError && (
                <span
                  id={`${inputId}-error`}
                  role="alert"
                  className="flex items-center gap-1 text-xs text-[var(--color-danger)]"
                >
                  <AlertTriangle className="h-3 w-3 shrink-0" strokeWidth={2} />
                  {cidError}
                </span>
              )}
            </div>

            {/* Submit button */}
            <button
              type="submit"
              disabled={isSubmitting || !!cidError || !cidInput.trim()}
              className={`
                flex items-center justify-center gap-2 rounded-lg px-4 py-2.5
                text-sm font-medium transition-colors
                focus:outline-none focus:ring-2 focus:ring-[var(--color-sentinel)]/40
                disabled:opacity-50 disabled:cursor-not-allowed
                min-h-[44px] /* VAL-SUBMIT-009: 44px hit target */
                ${
                  isSubmitting
                    ? "bg-[var(--color-sentinel)]/30 text-[var(--color-sentinel)] cursor-wait"
                    : "bg-[var(--color-sentinel)] text-canvas hover:bg-[var(--color-sentinel)]/90"
                }
              `}
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" strokeWidth={2} />
                  <span>{phaseLabel[phase]}</span>
                </>
              ) : (
                "Validate"
              )}
            </button>
          </form>

          {/* Inline error (sentinel error, x402 settlement failure, etc.) */}
          {inlineError && phase === "error" && (
            <div
              role="alert"
              className="mt-1 flex items-start gap-2 rounded-lg border border-[var(--color-danger)]/30 bg-[var(--color-danger)]/5 px-3 py-2.5"
            >
              <AlertTriangle className="h-4 w-4 shrink-0 text-[var(--color-danger)] mt-0.5" strokeWidth={2} />
              <div className="flex flex-col gap-1">
                <p className="text-sm text-[var(--color-danger)]">{inlineError}</p>
                <p className="text-xs text-fg-faint">
                  Your submission was not processed. You can try again.
                </p>
              </div>
            </div>
          )}

          {/* Success message (before redirect) */}
          {phase === "success" && (
            <div className="mt-1 flex items-center gap-2 rounded-lg border border-[var(--color-success)]/30 bg-[var(--color-success)]/5 px-3 py-2.5">
              <CheckCircle2 className="h-4 w-4 text-[var(--color-success)]" strokeWidth={2} />
              <span className="text-sm text-[var(--color-success)]">
                Validation complete! Redirecting to verdict...
              </span>
            </div>
          )}

          {/* Info text */}
          {!isSubmitting && phase !== "success" && !inlineError && (
            <p className="text-xs text-fg-faint leading-relaxed">
              {isConnected
                ? "Enter an IPFS CID and click Validate. Your wallet will sign a 0.01 USDC payment via x402."
                : "Click Validate to connect your wallet, then sign a 0.01 USDC payment via x402."}
            </p>
          )}
        </CardContent>
      </Card>

      {/* External links — VAL-SUBMIT-008: rel=noopener noreferrer */}
      <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-xs text-fg-faint">
        <a
          href="https://docs.ipfs.tech/concepts/content-addressing/"
          target="_blank"
          rel="noopener noreferrer"
          className="underline decoration-fg-faint/30 hover:decoration-fg-faint transition-colors"
        >
          What is an IPFS CID?
        </a>
        <a
          href="https://x402.org"
          target="_blank"
          rel="noopener noreferrer"
          className="underline decoration-fg-faint/30 hover:decoration-fg-faint transition-colors"
        >
          Learn about x402 payments
        </a>
      </div>
    </div>
  );
}
