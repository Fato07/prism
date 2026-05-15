/**
 * x402 client-side signing utilities.
 *
 * Constructs EIP-3009 transferWithAuthorization typed data for USDC
 * and packages the signature into a base64-encoded x402 v2 payment
 * payload suitable for the X-PAYMENT header.
 *
 * The sentinel's x402 middleware decodes the base64 payload and forwards
 * it to the facilitator at x402.org which verifies the signature on-chain
 * and settles the USDC transfer.
 *
 * VAL-SUBMIT-004: Visitor signs x402 0.01 USDC payment on Base Sepolia.
 * VAL-SUBMIT-007: Payment payload is NOT silently re-used (new nonce per attempt).
 */

import type { WalletClient } from "viem";
import { bytesToHex } from "viem";

/* ─────────────── Network config ─────────────── */

/** USDC contract addresses and EIP-712 domain info per network. */
export const X402_NETWORKS = {
  "base-sepolia": {
    chainId: 84532,
    usdcAddress: "0x036CbD53842c5426634e7929541eC2318f3dCF7e" as const,
    domainName: "USDC",
    domainVersion: "2",
  },
  base: {
    chainId: 8453,
    usdcAddress: "0x833589fCD6eDb6E08f4c7C32D4f71b54bda02913" as const,
    domainName: "USD Coin",
    domainVersion: "2",
  },
  "arc-testnet": {
    chainId: 5042002,
    usdcAddress: "0x3600000000000000000000000000000000000000" as const,
    domainName: "USDC",
    domainVersion: "2",
  },
} as const;

export type X402NetworkId = keyof typeof X402_NETWORKS;

/** Default network for x402 payments (matches sentinel default). */
export const DEFAULT_X402_NETWORK: X402NetworkId = "base-sepolia";

/* ─────────────── Payment requirements (from sentinel 402 response) ── */

export interface PaymentRequirements {
  amount: string;
  asset: string;
  scheme: string;
  network: string;
  recipient: string;
  facilitator?: string;
}

/* ─────────────── EIP-3009 typed data construction ─────────────── */

/**
 * Build the EIP-712 typed data for USDC's transferWithAuthorization.
 *
 * This is the same typed data structure that the x402 Python SDK
 * constructs when calling `client.create_payment_payload()`.
 * The facilitator at x402.org reconstructs this hash to verify
 * the signature.
 */
function buildTransferWithAuthorizationTypedData(
  from: `0x${string}`,
  to: `0x${string}`,
  value: bigint,
  validAfter: bigint,
  validBefore: bigint,
  nonce: `0x${string}`,
  chainNetId: X402NetworkId,
) {
  const net = X402_NETWORKS[chainNetId];

  const domain = {
    name: net.domainName,
    version: net.domainVersion,
    chainId: net.chainId,
    verifyingContract: net.usdcAddress,
  } as const;

  const types = {
    TransferWithAuthorization: [
      { name: "from", type: "address" },
      { name: "to", type: "address" },
      { name: "value", type: "uint256" },
      { name: "validAfter", type: "uint256" },
      { name: "validBefore", type: "uint256" },
      { name: "nonce", type: "bytes32" },
    ],
  } as const;

  const message = {
    from,
    to,
    value,
    validAfter,
    validBefore,
    nonce,
  };

  return { domain, types, message };
}

/* ─────────────── x402 v2 payment payload ─────────────── */

export interface TransferAuthData {
  from: string;
  to: string;
  value: string;
  validAfter: string;
  validBefore: string;
  nonce: string;
}

export interface X402AcceptedRequirements {
  scheme: string;
  network: string;
  asset: string;
  amount: string;
  payTo: string;
  maxTimeoutSeconds: number;
  extra: {
    name: string;
    version: string;
  };
}

export interface X402PaymentPayload {
  x402Version: 2;
  payload: {
    authorization: TransferAuthData;
    signature: string;
  };
  accepted: X402AcceptedRequirements;
  resource: null;
  extensions: null;
}

/**
 * Sign an EIP-3009 transferWithAuthorization via the visitor's wallet
 * and construct the x402 v2 payment payload.
 *
 * Each invocation generates a fresh nonce so the payment token is
 * never re-used (VAL-SUBMIT-007: replay-safe).
 *
 * @returns base64-encoded x402 v2 payment payload for the X-PAYMENT header
 */
export async function signX402Payment(
  walletClient: WalletClient,
  visitorAddress: `0x${string}`,
  requirements: PaymentRequirements,
  chainNetId: X402NetworkId = DEFAULT_X402_NETWORK,
): Promise<string> {
  const net = X402_NETWORKS[chainNetId];

  // Convert price (e.g., "0.01") to smallest unit (6 decimals for USDC)
  const amountSmallest = BigInt(Math.round(parseFloat(requirements.amount) * 1_000_000));

  // Fresh nonce per attempt (prevents replay — VAL-SUBMIT-007)
  const nonceBytes = new Uint8Array(32);
  crypto.getRandomValues(nonceBytes);
  const nonce: `0x${string}` = bytesToHex(nonceBytes);

  // Valid window: now → 10 minutes from now. Match the x402 Python SDK
  // shape closely: validAfter is the current timestamp, not zero.
  const nowSec = BigInt(Math.floor(Date.now() / 1000));
  const validAfter = nowSec;
  const validBefore = nowSec + BigInt(600); // 10 minutes

  const typedData = buildTransferWithAuthorizationTypedData(
    visitorAddress,
    requirements.recipient as `0x${string}`,
    amountSmallest,
    validAfter,
    validBefore,
    nonce,
    chainNetId,
  );

  // Sign via MetaMask / wallet provider
  const signature = await walletClient.signTypedData({
    account: visitorAddress,
    domain: typedData.domain,
    types: typedData.types,
    primaryType: "TransferWithAuthorization",
    message: typedData.message,
  });

  // Construct the full x402 v2 PaymentPayload shape emitted by the
  // official Python SDK's `create_payment_payload(...).model_dump_json(by_alias=True)`.
  // The public facilitator rejects minimal authorization-only objects with
  // `No facilitator registered for x402 version: undefined`.
  const accepted: X402AcceptedRequirements = {
    scheme: requirements.scheme,
    network: `eip155:${net.chainId}`,
    asset: net.usdcAddress,
    amount: amountSmallest.toString(),
    payTo: requirements.recipient,
    maxTimeoutSeconds: 120,
    extra: {
      name: net.domainName,
      version: net.domainVersion,
    },
  };

  const payload: X402PaymentPayload = {
    x402Version: 2,
    payload: {
      authorization: {
        from: visitorAddress,
        to: requirements.recipient,
        value: amountSmallest.toString(),
        validAfter: validAfter.toString(),
        validBefore: validBefore.toString(),
        nonce,
      },
      signature,
    },
    accepted,
    resource: null,
    extensions: null,
  };

  // Base64-encode for X-PAYMENT header
  const payloadJson = JSON.stringify(payload);
  const payloadBytes = new TextEncoder().encode(payloadJson);
  const base64 = btoa(String.fromCharCode(...payloadBytes));

  return base64;
}

/* ─────────────── CID regex validation ─────────────── */

/**
 * IPFS CID format regex — matches both CIDv0 (Qm...) and CIDv1 (bafy.../bafk...).
 *
 * VAL-SUBMIT-002: Rejects malformed inputs before network call.
 */
export const IPFS_CID_REGEX = /^(Qm[1-9A-HJ-NP-Za-km-z]{44}|baf[yaikh][a-z2-7]{40,})$/;

/**
 * Validate an IPFS CID string.
 * Returns an error message if invalid, or null if valid.
 */
export function validateCid(input: string): string | null {
  const trimmed = input.trim();
  if (!trimmed) {
    return "Please enter an IPFS CID";
  }
  if (!IPFS_CID_REGEX.test(trimmed)) {
    return "That does not look like a valid IPFS CID";
  }
  return null;
}

/* ─────────────── Trace hash derivation ─────────────── */

/**
 * Compute a deterministic trace_hash from a CID.
 * Uses a simple SHA-256 derivation: sha256("prism-submit:" + CID)
 * This ensures self-serve validations produce unique request hashes
 * distinct from the internal trader pipeline's content hashes.
 */
export async function computeTraceHash(cid: string): Promise<string> {
  const data = new TextEncoder().encode(`prism-submit:${cid}`);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  const hashHex = hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
  return `0x${hashHex}`;
}
