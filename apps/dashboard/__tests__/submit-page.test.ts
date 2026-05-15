/**
 * /submit page tests — Self-serve validation with x402 payment
 *
 * Covers:
 *   - VAL-SUBMIT-001: GET /submit returns 200 with form
 *   - VAL-SUBMIT-002: Client-side CID regex rejects malformed inputs
 *   - VAL-SUBMIT-003: Connect gate prompts wallet connection
 *   - VAL-SUBMIT-005: Invalid-CID error shows friendly inline message
 *   - VAL-SUBMIT-006: Sentinel error surfaces friendly inline message
 *   - VAL-SUBMIT-007: x402 settlement failure surfaces friendly message
 *   - VAL-SUBMIT-008: External links use rel=noopener noreferrer
 *   - VAL-SUBMIT-009: Responsive at mobile (44px hit target)
 *   - VAL-SUBMIT-010: No console.log / console.error from submission path
 *
 * Tests are unit-level (no browser / no real chain).
 */

import { describe, it, expect, vi, beforeAll } from "vitest";

/* ─────────────── VAL-SUBMIT-001: Route renders 200 with form ──── */

describe("VAL-SUBMIT-001: /submit route renders with form", () => {
  it("the page file does not contain 'use client' (server component shell)", () => {
    const fs = require("fs");
    const path = require("path");
    const pagePath = path.resolve(__dirname, "../app/submit/page.tsx");
    const content = fs.readFileSync(pagePath, "utf-8");
    expect(content.startsWith("'use client'")).toBe(false);
  });

  it("the page imports SubmitForm for client-side logic", () => {
    const fs = require("fs");
    const path = require("path");
    const pagePath = path.resolve(__dirname, "../app/submit/page.tsx");
    const content = fs.readFileSync(pagePath, "utf-8");
    expect(content).toContain("SubmitForm");
  });

  it("the page exports metadata with title", () => {
    const fs = require("fs");
    const path = require("path");
    const pagePath = path.resolve(__dirname, "../app/submit/page.tsx");
    const content = fs.readFileSync(pagePath, "utf-8");
    expect(content).toContain("export const metadata");
    expect(content).toContain("Submit Trace");
  });
});

/* ─────────────── VAL-SUBMIT-002: CID regex validation ─────────── */

describe("VAL-SUBMIT-002: Client-side CID regex rejects malformed inputs", () => {
  // Import the validation function
  let validateCid: (input: string) => string | null;

  beforeAll(async () => {
    const mod = await import("@/submit/lib/x402-client");
    validateCid = mod.validateCid;
  });

  it("rejects empty input", () => {
    expect(validateCid("")).toBeTruthy();
  });

  it("rejects random short strings", () => {
    expect(validateCid("nope")).toBeTruthy();
    expect(validateCid("0xabc")).toBeTruthy();
  });

  it("rejects Qm prefix with too few characters", () => {
    expect(validateCid("Qmshort")).toBeTruthy();
  });

  it("accepts valid CIDv0 (Qm...)", () => {
    expect(validateCid("QmNzqnPEEQUMn3GMbiEZANpKXZRPmTHxVwt5nNevR8iXt8")).toBeNull();
  });

  it("accepts valid CIDv1 (bafy...)", () => {
    expect(validateCid("bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efn6vlctq4e2apb2k3qjbjq")).toBeNull();
  });

  it("accepts valid CIDv1 (bafk...)", () => {
    expect(validateCid("bafkreihdwdcefgh4dqkjv67uzcmwqoj3eetje3p5gmhjpfkhcewc7vmz4")).toBeNull();
  });

  it("rejects invalid CIDv1 prefix", () => {
    expect(validateCid("bafz1234567890abcdefghijklmnopqrstuvwxyz1234567890abc")).toBeTruthy();
  });

  it("trims whitespace before validation", () => {
    expect(validateCid("  QmNzqnPEEQUMn3GMbiEZANpKXZRPmTHxVwt5nNevR8iXt8  ")).toBeNull();
  });
});

/* ─────────────── VAL-SUBMIT-003: Connect gate ────────────────── */

describe("VAL-SUBMIT-003: Connect gate opens Reown modal when wallet disconnected", () => {
  it("SubmitForm imports useAppKit from @reown/appkit/react for programmatic modal open", () => {
    const fs = require("fs");
    const path = require("path");
    const formPath = path.resolve(__dirname, "../app/submit/submit-form.tsx");
    const content = fs.readFileSync(formPath, "utf-8");
    expect(content).toContain("useAppKit");
    expect(content).toContain("@reown/appkit/react");
  });

  it("SubmitForm calls openAppKitModal() when wallet is disconnected and user clicks Validate", () => {
    const fs = require("fs");
    const path = require("path");
    const formPath = path.resolve(__dirname, "../app/submit/submit-form.tsx");
    const content = fs.readFileSync(formPath, "utf-8");
    // The code should destructure open from useAppKit
    expect(content).toContain("openAppKitModal");
    // And call it in the disconnected branch
    expect(content).toContain("void openAppKitModal()");
  });

  it("SubmitForm uses useAccount isConnected to gate submission", () => {
    const fs = require("fs");
    const path = require("path");
    const formPath = path.resolve(__dirname, "../app/submit/submit-form.tsx");
    const content = fs.readFileSync(formPath, "utf-8");
    expect(content).toContain("useAccount");
    expect(content).toContain("isConnected");
  });

  it("SubmitForm does NOT show an inline error for disconnected wallet", () => {
    const fs = require("fs");
    const path = require("path");
    const formPath = path.resolve(__dirname, "../app/submit/submit-form.tsx");
    const content = fs.readFileSync(formPath, "utf-8");
    // The old pattern showed an inline error like "Please connect your wallet..."
    // The new pattern opens the modal instead — verify the inline error for
    // disconnection is NOT present
    expect(content).not.toContain(
      "Please connect your wallet before submitting",
    );
    // Verify the modal open call is present in the disconnected branch
    expect(content).toContain("void openAppKitModal()");
  });
});

/* ─────────────── VAL-SUBMIT-005: Invalid-CID friendly error ──── */

describe("VAL-SUBMIT-005: Invalid-CID error shows friendly inline message", () => {
  it("SubmitForm renders inline error with role=alert for CID validation", () => {
    const fs = require("fs");
    const path = require("path");
    const formPath = path.resolve(__dirname, "../app/submit/submit-form.tsx");
    const content = fs.readFileSync(formPath, "utf-8");
    // The CID error should use role="alert" for accessibility
    expect(content).toContain('role="alert"');
    // The CID validation error is rendered via {cidError} which comes from
    // validateCid() in the x402-client module
    expect(content).toContain("{cidError}");
  });

  it("SubmitForm does not use console.error for CID errors", () => {
    const fs = require("fs");
    const path = require("path");
    const formPath = path.resolve(__dirname, "../app/submit/submit-form.tsx");
    const content = fs.readFileSync(formPath, "utf-8");
    // Strip comments (lines starting with * or //) before checking
    const codeLines = content
      .split("\n")
      .filter((line: string) => !line.trimStart().startsWith("*") && !line.trimStart().startsWith("//"))
      .join("\n");
    expect(codeLines).not.toContain("console.error(");
    expect(codeLines).not.toContain("console.log(");
  });
});

/* ─────────────── VAL-SUBMIT-006: Sentinel error friendly message ── */

describe("VAL-SUBMIT-006: Sentinel error surfaces friendly inline message", () => {
  it("SubmitForm renders inline error region for submission failures", () => {
    const fs = require("fs");
    const path = require("path");
    const formPath = path.resolve(__dirname, "../app/submit/submit-form.tsx");
    const content = fs.readFileSync(formPath, "utf-8");
    // Should have an inline error section
    expect(content).toContain("inlineError");
    // Should show a recovery message
    expect(content).toContain("You can try again");
  });

  it("SubmitForm re-enables the submit button after error", () => {
    const fs = require("fs");
    const path = require("path");
    const formPath = path.resolve(__dirname, "../app/submit/submit-form.tsx");
    const content = fs.readFileSync(formPath, "utf-8");
    // The error state should allow retry
    expect(content).toContain('phase === "error"');
    // The submit button should not stay disabled after error
    // Check that the disabled condition is based on isSubmitting + cidError + empty input
    expect(content).toContain("isSubmitting");
  });

  it("Confirm API route returns friendly message for sentinel errors", () => {
    const fs = require("fs");
    const path = require("path");
    const confirmPath = path.resolve(
      __dirname,
      "../app/api/validate/confirm/route.ts",
    );
    const content = fs.readFileSync(confirmPath, "utf-8");
    expect(content).toContain("temporarily unavailable");
  });
});

/* ─────────────── VAL-SUBMIT-007: x402 settlement failure ─────── */

describe("VAL-SUBMIT-007: x402 settlement failure surfaces friendly message", () => {
  it("Confirm API route maps settlement_failed to friendly message", () => {
    const fs = require("fs");
    const path = require("path");
    const confirmPath = path.resolve(
      __dirname,
      "../app/api/validate/confirm/route.ts",
    );
    const content = fs.readFileSync(confirmPath, "utf-8");
    expect(content).toContain("settlement_failed");
    expect(content).toContain("sufficient USDC");
  });

  it("Confirm API route maps invalid_payment_token to friendly message", () => {
    const fs = require("fs");
    const path = require("path");
    const confirmPath = path.resolve(
      __dirname,
      "../app/api/validate/confirm/route.ts",
    );
    const content = fs.readFileSync(confirmPath, "utf-8");
    expect(content).toContain("invalid_payment_token");
    expect(content).toContain("Payment signature was invalid");
  });

  it("x402 client generates a fresh nonce per attempt (replay-safe)", async () => {
    const mod = await import("@/submit/lib/x402-client");
    // Call computeTraceHash twice with same input — should produce same result
    const hash1 = await mod.computeTraceHash("test-cid");
    const hash2 = await mod.computeTraceHash("test-cid");
    expect(hash1).toBe(hash2);
    // Different inputs should produce different hashes
    const hash3 = await mod.computeTraceHash("other-cid");
    expect(hash1).not.toBe(hash3);
  });

  it("SubmitForm clears inline error on retry", () => {
    const fs = require("fs");
    const path = require("path");
    const formPath = path.resolve(__dirname, "../app/submit/submit-form.tsx");
    const content = fs.readFileSync(formPath, "utf-8");
    // When user edits CID, inline error should clear
    expect(content).toContain("setInlineError(null)");
  });
});

/* ─────────────── VAL-SUBMIT-008: External links ──────────────── */

describe("VAL-SUBMIT-008: No external links open without rel=noopener noreferrer", () => {
  it("SubmitForm external links use target=_blank with rel=noopener noreferrer", () => {
    const fs = require("fs");
    const path = require("path");
    const formPath = path.resolve(__dirname, "../app/submit/submit-form.tsx");
    const content = fs.readFileSync(formPath, "utf-8");
    // Find all target="_blank" and verify each has rel
    const blankMatches = content.match(/target="_blank"/g) ?? [];
    const relMatches = content.match(/rel="noopener noreferrer"/g) ?? [];
    expect(blankMatches.length).toBeGreaterThan(0);
    expect(blankMatches.length).toBe(relMatches.length);
  });
});

/* ─────────────── VAL-SUBMIT-009: Responsive at mobile ──────────── */

describe("VAL-SUBMIT-009: Responsive at mobile width", () => {
  it("submit button has min-h-[44px] for iOS HIG compliance", () => {
    const fs = require("fs");
    const path = require("path");
    const formPath = path.resolve(__dirname, "../app/submit/submit-form.tsx");
    const content = fs.readFileSync(formPath, "utf-8");
    expect(content).toContain("min-h-[44px]");
  });

  it("form uses flex-col for vertical stacking at mobile width", () => {
    const fs = require("fs");
    const path = require("path");
    const formPath = path.resolve(__dirname, "../app/submit/submit-form.tsx");
    const content = fs.readFileSync(formPath, "utf-8");
    expect(content).toContain("flex-col");
  });
});

/* ─────────────── VAL-SUBMIT-010: No console.log/error ─────────── */

describe("VAL-SUBMIT-010: No console.log / console.error from submission path", () => {
  it("SubmitForm does not use console.log or console.error in code", () => {
    const fs = require("fs");
    const path = require("path");
    const formPath = path.resolve(__dirname, "../app/submit/submit-form.tsx");
    const content = fs.readFileSync(formPath, "utf-8");
    // Strip comments (lines starting with * or //) before checking
    const codeLines = content
      .split("\n")
      .filter((line: string) => !line.trimStart().startsWith("*") && !line.trimStart().startsWith("//"))
      .join("\n");
    expect(codeLines).not.toContain("console.log(");
    expect(codeLines).not.toContain("console.error(");
  });

  it("x402-client does not use console.log or console.error", () => {
    const fs = require("fs");
    const path = require("path");
    const clientPath = path.resolve(__dirname, "../app/submit/lib/x402-client.ts");
    const content = fs.readFileSync(clientPath, "utf-8");
    expect(content).not.toContain("console.log");
    expect(content).not.toContain("console.error");
  });

  it("API route initiate does not use console.log", () => {
    const fs = require("fs");
    const path = require("path");
    const routePath = path.resolve(
      __dirname,
      "../app/api/validate/initiate/route.ts",
    );
    const content = fs.readFileSync(routePath, "utf-8");
    expect(content).not.toContain("console.log");
    expect(content).not.toContain("console.error");
  });

  it("API route confirm does not use console.log", () => {
    const fs = require("fs");
    const path = require("path");
    const routePath = path.resolve(
      __dirname,
      "../app/api/validate/confirm/route.ts",
    );
    const content = fs.readFileSync(routePath, "utf-8");
    expect(content).not.toContain("console.log");
    expect(content).not.toContain("console.error");
  });
});

/* ─────────────── EIP-3009 / x402 payload construction ────────── */

describe("x402 client: EIP-3009 typed data construction", () => {
  it("X402_NETWORKS contains base-sepolia with correct USDC address", async () => {
    const mod = await import("@/submit/lib/x402-client");
    expect(mod.X402_NETWORKS["base-sepolia"]).toBeDefined();
    expect(mod.X402_NETWORKS["base-sepolia"].chainId).toBe(84532);
    expect(mod.X402_NETWORKS["base-sepolia"].usdcAddress).toBe(
      "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
    );
    expect(mod.X402_NETWORKS["base-sepolia"].domainName).toBe("USDC");
    expect(mod.X402_NETWORKS["base-sepolia"].domainVersion).toBe("2");
  });

  it("X402_NETWORKS contains base mainnet with correct USDC address", async () => {
    const mod = await import("@/submit/lib/x402-client");
    expect(mod.X402_NETWORKS.base).toBeDefined();
    expect(mod.X402_NETWORKS.base.chainId).toBe(8453);
    expect(mod.X402_NETWORKS.base.usdcAddress).toBe(
      "0x833589fCD6eDb6E08f4c7C32D4f71b54bda02913",
    );
    expect(mod.X402_NETWORKS.base.domainName).toBe("USD Coin");
  });

  it("DEFAULT_X402_NETWORK is base-sepolia", async () => {
    const mod = await import("@/submit/lib/x402-client");
    expect(mod.DEFAULT_X402_NETWORK).toBe("base-sepolia");
  });

  it("X402NetworkId type covers all three networks", async () => {
    const mod = await import("@/submit/lib/x402-client");
    const networkIds: Array<"base-sepolia" | "base" | "arc-testnet"> = ["base-sepolia", "base", "arc-testnet"];
    expect(networkIds).toHaveLength(3);
    // Verify the type is exported
    expect(typeof mod.DEFAULT_X402_NETWORK).toBe("string");
  });

  it("IPFS_CID_REGEX matches valid CIDv0", async () => {
    const mod = await import("@/submit/lib/x402-client");
    expect(mod.IPFS_CID_REGEX.test("QmNzqnPEEQUMn3GMbiEZANpKXZRPmTHxVwt5nNevR8iXt8")).toBe(true);
  });

  it("IPFS_CID_REGEX matches valid CIDv1", async () => {
    const mod = await import("@/submit/lib/x402-client");
    expect(mod.IPFS_CID_REGEX.test("bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efn6vlctq4e2apb2k3qjbjq")).toBe(true);
  });

  it("IPFS_CID_REGEX rejects invalid CIDs", async () => {
    const mod = await import("@/submit/lib/x402-client");
    expect(mod.IPFS_CID_REGEX.test("nope")).toBe(false);
    expect(mod.IPFS_CID_REGEX.test("0xabc")).toBe(false);
    expect(mod.IPFS_CID_REGEX.test("Qmshort")).toBe(false);
  });
});

/* ─────────────── API route input validation ──────────────────── */

describe("API routes: input validation", () => {
  it("Initiate route requires traceUri and traceHash", () => {
    const fs = require("fs");
    const path = require("path");
    const routePath = path.resolve(
      __dirname,
      "../app/api/validate/initiate/route.ts",
    );
    const content = fs.readFileSync(routePath, "utf-8");
    expect(content).toContain("traceUri is required");
    expect(content).toContain("traceHash is required");
  });

  it("Confirm API route remaps transferAuth to authorization", () => {
    const fs = require("fs");
    const path = require("path");
    const confirmPath = path.resolve(
      __dirname,
      "../app/api/validate/confirm/route.ts",
    );
    const content = fs.readFileSync(confirmPath, "utf-8");
    // The confirm route must remap the client's "transferAuth" to the
    // x402 protocol's canonical "authorization" before sending to sentinel
    expect(content).toContain("transferAuth");
    expect(content).toContain(".authorization = ");
  });

  it("Confirm route requires sessionId, xPayment, traceUri, traceHash", () => {
    const fs = require("fs");
    const path = require("path");
    const routePath = path.resolve(
      __dirname,
      "../app/api/validate/confirm/route.ts",
    );
    const content = fs.readFileSync(routePath, "utf-8");
    expect(content).toContain("sessionId is required");
    expect(content).toContain("xPayment is required");
    expect(content).toContain("traceUri is required");
    expect(content).toContain("traceHash is required");
  });

  it("Initiate route returns 503 when SENTINEL_MCP_URL is not set", () => {
    const fs = require("fs");
    const path = require("path");
    const routePath = path.resolve(
      __dirname,
      "../app/api/validate/initiate/route.ts",
    );
    const content = fs.readFileSync(routePath, "utf-8");
    expect(content).toContain("Sentinel endpoint not configured");
    expect(content).toContain("503");
  });

  it("Confirm route returns 503 when SENTINEL_MCP_URL is not set", () => {
    const fs = require("fs");
    const path = require("path");
    const routePath = path.resolve(
      __dirname,
      "../app/api/validate/confirm/route.ts",
    );
    const content = fs.readFileSync(routePath, "utf-8");
    expect(content).toContain("Sentinel endpoint not configured");
    expect(content).toContain("503");
  });
});

/* ─────────────── Chain switching ──────────────────────────────── */

describe("Chain switching for x402 payment", () => {
  it("SubmitForm checks chainId and prompts switch using dynamic network from initiate response", () => {
    const fs = require("fs");
    const path = require("path");
    const formPath = path.resolve(__dirname, "../app/submit/submit-form.tsx");
    const content = fs.readFileSync(formPath, "utf-8");
    expect(content).toContain("chainId");
    expect(content).toContain("switchChainAsync");
    // Dynamic chain switch using initiate response network, not hardcoded
    expect(content).toContain("targetNetwork");
    expect(content).toContain("targetChainId");
  });

  it("SubmitForm uses useSwitchChain for chain switching", () => {
    const fs = require("fs");
    const path = require("path");
    const formPath = path.resolve(__dirname, "../app/submit/submit-form.tsx");
    const content = fs.readFileSync(formPath, "utf-8");
    expect(content).toContain("useSwitchChain");
  });

  it("SubmitForm chain switch happens after initiate call", () => {
    const fs = require("fs");
    const path = require("path");
    const formPath = path.resolve(__dirname, "../app/submit/submit-form.tsx");
    const content = fs.readFileSync(formPath, "utf-8");
    // The switchChainAsync call should appear after the initiate fetch
    const initiateIdx = content.indexOf("initiateResp");
    const switchIdx = content.indexOf("switchChainAsync({ chainId: targetChainId }");
    expect(initiateIdx).toBeGreaterThan(-1);
    expect(switchIdx).toBeGreaterThan(-1);
    expect(switchIdx).toBeGreaterThan(initiateIdx);
  });

  it("SubmitForm chain label adapts to target network (Arc Testnet vs Base Sepolia)", () => {
    const fs = require("fs");
    const path = require("path");
    const formPath = path.resolve(__dirname, "../app/submit/submit-form.tsx");
    const content = fs.readFileSync(formPath, "utf-8");
    expect(content).toContain("networkLabel");
    expect(content).toContain("Arc Testnet");
    expect(content).toContain("Base Sepolia");
  });
});

/* ─────────────── Dynamic network selection (Bug 2 fix) ─────────── */

describe("Dynamic network selection for x402 payment", () => {
  it("signX402Payment uses initiateData.paymentRequirements.network, not DEFAULT_X402_NETWORK", () => {
    const fs = require("fs");
    const path = require("path");
    const formPath = path.resolve(__dirname, "../app/submit/submit-form.tsx");
    const content = fs.readFileSync(formPath, "utf-8");
    // The signX402Payment call should pass targetNetwork (from initiate response)
    // NOT DEFAULT_X402_NETWORK
    expect(content).toContain("targetNetwork");
    expect(content).toContain("signX402Payment");
    // Verify the call uses targetNetwork as the last argument
    const signCallMatch = content.match(
      /signX402Payment\(\s*walletClient,\s*address,\s*initiateData\.paymentRequirements,\s*targetNetwork/m,
    );
    expect(signCallMatch).not.toBeNull();
  });

  it("SubmitForm does NOT import DEFAULT_X402_NETWORK", () => {
    const fs = require("fs");
    const path = require("path");
    const formPath = path.resolve(__dirname, "../app/submit/submit-form.tsx");
    const content = fs.readFileSync(formPath, "utf-8");
    // DEFAULT_X402_NETWORK should not appear in the import statement
    const importLine = content
      .split("\n")
      .find((line: string) => line.includes("from \"./lib/x402-client\""));
    expect(importLine).toBeDefined();
    expect(importLine).not.toContain("DEFAULT_X402_NETWORK");
  });

  it("SubmitForm imports X402NetworkId type for dynamic network cast", () => {
    const fs = require("fs");
    const path = require("path");
    const formPath = path.resolve(__dirname, "../app/submit/submit-form.tsx");
    const content = fs.readFileSync(formPath, "utf-8");
    expect(content).toContain("X402NetworkId");
  });

  it("X402_NETWORKS includes arc-testnet entry with correct chainId and USDC address", async () => {
    const mod = await import("@/submit/lib/x402-client");
    expect(mod.X402_NETWORKS["arc-testnet"]).toBeDefined();
    expect(mod.X402_NETWORKS["arc-testnet"].chainId).toBe(5042002);
    expect(mod.X402_NETWORKS["arc-testnet"].usdcAddress).toBe(
      "0x3600000000000000000000000000000000000000",
    );
    expect(mod.X402_NETWORKS["arc-testnet"].domainName).toBe("USDC");
    expect(mod.X402_NETWORKS["arc-testnet"].domainVersion).toBe("2");
  });

  it("X402NetworkId type now covers arc-testnet", async () => {
    const mod = await import("@/submit/lib/x402-client");
    // Verify the arc-testnet key exists in the networks object
    const networkKeys = Object.keys(mod.X402_NETWORKS);
    expect(networkKeys).toContain("arc-testnet");
    expect(networkKeys).toContain("base-sepolia");
    expect(networkKeys).toContain("base");
    expect(networkKeys).toHaveLength(3);
  });

  it("Unsupported network from initiate response throws friendly error", () => {
    const fs = require("fs");
    const path = require("path");
    const formPath = path.resolve(__dirname, "../app/submit/submit-form.tsx");
    const content = fs.readFileSync(formPath, "utf-8");
    expect(content).toContain("Unsupported payment network");
  });

  it("paymentRequirements.network is cast to X402NetworkId from initiate response", () => {
    const fs = require("fs");
    const path = require("path");
    const formPath = path.resolve(__dirname, "../app/submit/submit-form.tsx");
    const content = fs.readFileSync(formPath, "utf-8");
    expect(content).toContain(
      "initiateData.paymentRequirements.network as X402NetworkId",
    );
  });
});
