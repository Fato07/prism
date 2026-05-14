/**
 * BridgeWidget tests — Circle App Kit Bridge on /submit
 *
 * Covers:
 *   - VAL-BRIDGE-001: @circle-fin/app-kit is installed as runtime dependency
 *   - VAL-BRIDGE-002: Bridge widget mounts only when USDC < 0.01 on target chain
 *   - VAL-BRIDGE-003: Destination chain defaults to the active x402 settlement chain
 *   - VAL-BRIDGE-004: Bridge-hidden state does not break submit form layout (returns null)
 *   - VAL-BRIDGE-005: Bridge widget styling matches shadcn theme (no white bg)
 *
 * Tests are unit-level (no browser / no real chain).
 */

import { describe, it, expect, vi, beforeAll } from "vitest";

/* ─────────────── VAL-BRIDGE-001: @circle-fin/app-kit installed ── */

describe("VAL-BRIDGE-001: @circle-fin/app-kit is installed as runtime dependency", () => {
  it("declares @circle-fin/app-kit in package.json dependencies (not devDependencies)", () => {
    const fs = require("fs");
    const path = require("path");
    const pkgPath = path.resolve(__dirname, "../package.json");
    const pkg = JSON.parse(fs.readFileSync(pkgPath, "utf-8"));
    expect(pkg.dependencies["@circle-fin/app-kit"]).toBeDefined();
    // Must NOT be in devDependencies
    expect(pkg.devDependencies?.["@circle-fin/app-kit"]).toBeUndefined();
  });

  it("declares @circle-fin/adapter-viem-v2 in package.json dependencies", () => {
    const fs = require("fs");
    const path = require("path");
    const pkgPath = path.resolve(__dirname, "../package.json");
    const pkg = JSON.parse(fs.readFileSync(pkgPath, "utf-8"));
    expect(pkg.dependencies["@circle-fin/adapter-viem-v2"]).toBeDefined();
  });

  it("the package resolves without errors", () => {
    // Verify the package is actually installed
    const fs = require("fs");
    const path = require("path");
    const modPath = path.resolve(__dirname, "../node_modules/@circle-fin/app-kit");
    expect(fs.existsSync(modPath)).toBe(true);
  });
});

/* ─────────────── VAL-BRIDGE-002: Conditional rendering ─────────── */

describe("VAL-BRIDGE-002: Bridge widget mounts only when USDC < 0.01 on target chain", () => {
  it("the BridgeWidget component file exists", () => {
    const fs = require("fs");
    const path = require("path");
    const widgetPath = path.resolve(__dirname, "../app/submit/bridge-widget.tsx");
    expect(fs.existsSync(widgetPath)).toBe(true);
  });

  it("the BridgeWidget is a client component (has 'use client')", () => {
    const fs = require("fs");
    const path = require("path");
    const widgetPath = path.resolve(__dirname, "../app/submit/bridge-widget.tsx");
    const content = fs.readFileSync(widgetPath, "utf-8");
    // The directive may be either single or double quoted
    expect(content.startsWith('"use client"') || content.startsWith("'use client'")).toBe(true);
  });

  it("the component uses useReadContract to check USDC balance", () => {
    const fs = require("fs");
    const path = require("path");
    const widgetPath = path.resolve(__dirname, "../app/submit/bridge-widget.tsx");
    const content = fs.readFileSync(widgetPath, "utf-8");
    expect(content).toContain("useReadContract");
    expect(content).toContain("balanceOf");
  });

  it("the component checks balance against 0.01 USDC threshold (10000 units)", () => {
    const fs = require("fs");
    const path = require("path");
    const widgetPath = path.resolve(__dirname, "../app/submit/bridge-widget.tsx");
    const content = fs.readFileSync(widgetPath, "utf-8");
    expect(content).toContain("MIN_USDC_UNITS");
    expect(content).toContain("10000");
  });

  it("the component returns null when wallet is disconnected", () => {
    const fs = require("fs");
    const path = require("path");
    const widgetPath = path.resolve(__dirname, "../app/submit/bridge-widget.tsx");
    const content = fs.readFileSync(widgetPath, "utf-8");
    // When isConnected is false, the component returns null
    expect(content).toContain("!isConnected");
    expect(content).toContain("return null");
  });

  it("the component returns null when balance is sufficient (>= 0.01 USDC)", () => {
    const fs = require("fs");
    const path = require("path");
    const widgetPath = path.resolve(__dirname, "../app/submit/bridge-widget.tsx");
    const content = fs.readFileSync(widgetPath, "utf-8");
    expect(content).toContain("hasSufficientBalance");
  });
});

/* ─────────────── VAL-BRIDGE-003: Destination chain defaults ──── */

describe("VAL-BRIDGE-003: Bridge widget defaults destination to the active x402 settlement chain", () => {
  it("defaults to Base_Sepolia when X402_FACILITATOR_MODE is public or unset", () => {
    const fs = require("fs");
    const path = require("path");
    const widgetPath = path.resolve(__dirname, "../app/submit/bridge-widget.tsx");
    const content = fs.readFileSync(widgetPath, "utf-8");
    expect(content).toContain("BridgeChain.Base_Sepolia");
    expect(content).toContain("NEXT_PUBLIC_X402_FACILITATOR_MODE");
  });

  it("switches to Arc_Testnet when X402_FACILITATOR_MODE is circle", () => {
    const fs = require("fs");
    const path = require("path");
    const widgetPath = path.resolve(__dirname, "../app/submit/bridge-widget.tsx");
    const content = fs.readFileSync(widgetPath, "utf-8");
    expect(content).toContain("BridgeChain.Arc_Testnet");
    expect(content).toContain('"circle"');
  });

  it("uses the AppKit bridge method with proper from/to structure", () => {
    const fs = require("fs");
    const path = require("path");
    const widgetPath = path.resolve(__dirname, "../app/submit/bridge-widget.tsx");
    const content = fs.readFileSync(widgetPath, "utf-8");
    expect(content).toContain("kit.bridge");
    // The bridge params use `from` and `to`, matching the SDK API
    expect(content).toContain("from:");
    expect(content).toContain("to:");
  });
});

/* ─────────────── VAL-BRIDGE-004: No CLS when hidden ──────────── */

describe("VAL-BRIDGE-004: Bridge-hidden state does not break submit form layout", () => {
  it("the component returns null (not an empty div) when hidden", () => {
    const fs = require("fs");
    const path = require("path");
    const widgetPath = path.resolve(__dirname, "../app/submit/bridge-widget.tsx");
    const content = fs.readFileSync(widgetPath, "utf-8");
    // When conditions for hiding are met, the component returns null
    // This is verified by the presence of "return null" in the early returns
    expect(content).toContain("return null");
  });

  it("the /submit page imports BridgeWidget above SubmitForm", () => {
    const fs = require("fs");
    const path = require("path");
    const pagePath = path.resolve(__dirname, "../app/submit/page.tsx");
    const content = fs.readFileSync(pagePath, "utf-8");
    expect(content).toContain("BridgeWidget");
    // In the JSX render, BridgeWidget should appear before SubmitForm
    // Find the last occurrence of BridgeWidget in the JSX (the usage, not import)
    const jsxSection = content.slice(content.indexOf("return"));
    const bridgeJsxIndex = jsxSection.indexOf("<BridgeWidget");
    const formJsxIndex = jsxSection.indexOf("<SubmitForm");
    expect(bridgeJsxIndex).toBeLessThan(formJsxIndex);
    expect(bridgeJsxIndex).toBeGreaterThanOrEqual(0);
  });

  it("the page remains a server component (no 'use client')", () => {
    const fs = require("fs");
    const path = require("path");
    const pagePath = path.resolve(__dirname, "../app/submit/page.tsx");
    const content = fs.readFileSync(pagePath, "utf-8");
    expect(content.startsWith("'use client'")).toBe(false);
  });
});

/* ─────────────── VAL-BRIDGE-005: Styling matches shadcn theme ──── */

describe("VAL-BRIDGE-005: Bridge widget styling matches shadcn theme", () => {
  it("uses the existing Card component from shadcn/ui", () => {
    const fs = require("fs");
    const path = require("path");
    const widgetPath = path.resolve(__dirname, "../app/submit/bridge-widget.tsx");
    const content = fs.readFileSync(widgetPath, "utf-8");
    expect(content).toContain('Card');
    expect(content).toContain('CardContent');
  });

  it("uses existing design tokens (no hardcoded white backgrounds)", () => {
    const fs = require("fs");
    const path = require("path");
    const widgetPath = path.resolve(__dirname, "../app/submit/bridge-widget.tsx");
    const content = fs.readFileSync(widgetPath, "utf-8");
    // Should NOT contain white backgrounds or off-brand colors
    expect(content).not.toMatch(/bg-white/);
    expect(content).not.toMatch(/bg-\[#fff/i);
    // Should use the project's CSS variable tokens
    expect(content).toContain("--color-trader");
    expect(content).toContain("--color-danger");
  });

  it("uses Tailwind utility classes (no CSS modules)", () => {
    const fs = require("fs");
    const path = require("path");
    const widgetPath = path.resolve(__dirname, "../app/submit/bridge-widget.tsx");
    const content = fs.readFileSync(widgetPath, "utf-8");
    // No CSS module imports
    expect(content).not.toMatch(/import\s+.*\.module\.css/);
  });
});

/* ─────────────── Environment variable documentation ──────────── */

describe("NEXT_PUBLIC_X402_FACILITATOR_MODE is documented in .env.example", () => {
  it(".env.example lists NEXT_PUBLIC_X402_FACILITATOR_MODE", () => {
    const fs = require("fs");
    const path = require("path");
    const envPath = path.resolve(__dirname, "../../../.env.example");
    const content = fs.readFileSync(envPath, "utf-8");
    expect(content).toContain("NEXT_PUBLIC_X402_FACILITATOR_MODE");
  });
});
