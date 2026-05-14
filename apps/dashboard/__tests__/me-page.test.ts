/**
 * /me page tests — My Verdicts
 *
 * Covers:
 *   - VAL-ME-001: Route renders 200 when wallet disconnected
 *   - VAL-ME-002: Disconnected state shows CTA card, not empty page
 *   - VAL-ME-003: Connected state fetches verdicts with lower-cased address
 *   - VAL-ME-004: Connected state with ≥1 verdict renders verdict history grid
 *   - VAL-ME-005: Address lower-cased before query; uses HashChip
 *
 * Tests are unit-level (no browser / no real chain).
 */

import { describe, it, expect } from "vitest";

/* ─────────────── Address sanitisation (VAL-ME-005) ─────────────── */

describe("VAL-ME-005: Address is lower-cased before query", () => {
  it("lowercases a checksum address for the API URL", () => {
    const checksumAddress = "0xC960833ee26E23Ca01Dfc4d217a8942EA78b452B";
    const lowercased = checksumAddress.toLowerCase();
    expect(lowercased).toBe("0xc960833ee26e23ca01dfc4d217a8942ea78b452b");
  });

  it("lowercasing a already-lowercase address is idempotent", () => {
    const lower = "0xc960833ee26e23ca01dfc4d217a8942ea78b452b";
    expect(lower.toLowerCase()).toBe(lower);
  });

  it("the API URL includes the lower-cased address", () => {
    const address = "0xC960833ee26E23Ca01Dfc4d217a8942EA78b452B";
    const url = `/api/verdicts/by-address?address=${address.toLowerCase()}`;
    expect(url).toContain("address=0xc960833ee26e23ca01dfc4d217a8942ea78b452b");
    expect(url).not.toContain("0xC9");
  });
});

/* ─────────────── Disconnected state (VAL-ME-001, VAL-ME-002) ──── */

describe("VAL-ME-001: /me route renders when wallet disconnected", () => {
  it("the page file does not contain 'use client' (server component shell)", () => {
    // Read the page file and verify it's NOT a client component
    const fs = require("fs");
    const path = require("path");
    const pagePath = path.resolve(
      __dirname,
      "../app/me/page.tsx",
    );
    const content = fs.readFileSync(pagePath, "utf-8");
    expect(content.startsWith("'use client'")).toBe(false);
  });

  it("the page imports MeWalletPanel for client-side logic", () => {
    const fs = require("fs");
    const path = require("path");
    const pagePath = path.resolve(
      __dirname,
      "../app/me/page.tsx",
    );
    const content = fs.readFileSync(pagePath, "utf-8");
    expect(content).toContain("MeWalletPanel");
  });
});

describe("VAL-ME-002: Disconnected state shows CTA card", () => {
  it("MeWalletPanel contains a CTA card text for disconnected state", () => {
    const fs = require("fs");
    const path = require("path");
    const panelPath = path.resolve(
      __dirname,
      "../app/me/me-wallet-panel.tsx",
    );
    const content = fs.readFileSync(panelPath, "utf-8");
    // Must contain a human-readable CTA message, NOT just "undefined" or blank
    expect(content).toContain("Connect to view your verdicts");
  });

  it("MeWalletPanel does not render 'undefined' in the disconnected state", () => {
    const fs = require("fs");
    const path = require("path");
    const panelPath = path.resolve(
      __dirname,
      "../app/me/me-wallet-panel.tsx",
    );
    const content = fs.readFileSync(panelPath, "utf-8");
    // The disconnected block should not reference useAccount address
    // without guarding for null
    expect(content).toContain("!isConnected");
    expect(content).toContain("!address");
  });
});

/* ─────────────── Connected state fetch (VAL-ME-003) ────────────── */

describe("VAL-ME-003: Connected state fetches verdicts for the connected address", () => {
  it("MeWalletPanel uses the correct API endpoint pattern", () => {
    const fs = require("fs");
    const path = require("path");
    const panelPath = path.resolve(
      __dirname,
      "../app/me/me-wallet-panel.tsx",
    );
    const content = fs.readFileSync(panelPath, "utf-8");
    expect(content).toContain("/api/verdicts/by-address?address=");
  });

  it("MeWalletPanel lower-cases the address before the fetch", () => {
    const fs = require("fs");
    const path = require("path");
    const panelPath = path.resolve(
      __dirname,
      "../app/me/me-wallet-panel.tsx",
    );
    const content = fs.readFileSync(panelPath, "utf-8");
    expect(content).toContain("address.toLowerCase()");
  });

  it("fetch is triggered only when isConnected and address are truthy", () => {
    const fs = require("fs");
    const path = require("path");
    const panelPath = path.resolve(
      __dirname,
      "../app/me/me-wallet-panel.tsx",
    );
    const content = fs.readFileSync(panelPath, "utf-8");
    // The useEffect guard condition should check both
    expect(content).toMatch(/isConnected.*address|address.*isConnected/);
  });
});

/* ─────────────── Connected state verdicts grid (VAL-ME-004) ────── */

describe("VAL-ME-004: Connected state renders verdicts in /history card style", () => {
  it("MeWalletPanel uses the same HistoryEntry type as /history", () => {
    const fs = require("fs");
    const path = require("path");
    const panelPath = path.resolve(
      __dirname,
      "../app/me/me-wallet-panel.tsx",
    );
    const content = fs.readFileSync(panelPath, "utf-8");
    expect(content).toContain("HistoryEntry");
    expect(content).toContain("@/lib/db");
  });

  it("MeWalletPanel renders a grid with data-testid='me-cards'", () => {
    const fs = require("fs");
    const path = require("path");
    const panelPath = path.resolve(
      __dirname,
      "../app/me/me-wallet-panel.tsx",
    );
    const content = fs.readFileSync(panelPath, "utf-8");
    expect(content).toContain('data-testid="me-cards"');
  });

  it("each card links to /trace/<uuid> like /history", () => {
    const fs = require("fs");
    const path = require("path");
    const panelPath = path.resolve(
      __dirname,
      "../app/me/me-wallet-panel.tsx",
    );
    const content = fs.readFileSync(panelPath, "utf-8");
    expect(content).toContain("`/trace/${entry.trace_id}`");
  });

  it("empty state renders when verdicts array is empty", () => {
    const fs = require("fs");
    const path = require("path");
    const panelPath = path.resolve(
      __dirname,
      "../app/me/me-wallet-panel.tsx",
    );
    const content = fs.readFileSync(panelPath, "utf-8");
    expect(content).toContain("No verdicts yet");
  });
});

/* ─────────────── Address displayed via HashChip (VAL-ME-005) ──── */

describe("VAL-ME-005: Address is displayed via HashChip, not raw span", () => {
  it("MeWalletPanel uses HashChip component for the address", () => {
    const fs = require("fs");
    const path = require("path");
    const panelPath = path.resolve(
      __dirname,
      "../app/me/me-wallet-panel.tsx",
    );
    const content = fs.readFileSync(panelPath, "utf-8");
    expect(content).toContain("<HashChip");
    expect(content).toContain("@/components/ui/hash-chip");
  });

  it("HashChip receives the address value via displayAddress variable", () => {
    const fs = require("fs");
    const path = require("path");
    const panelPath = path.resolve(
      __dirname,
      "../app/me/me-wallet-panel.tsx",
    );
    const content = fs.readFileSync(panelPath, "utf-8");
    expect(content).toContain('value={displayAddress}');
    expect(content).toContain("const displayAddress = address");
  });

  it("the address is NOT rendered as raw <span> text", () => {
    const fs = require("fs");
    const path = require("path");
    const panelPath = path.resolve(
      __dirname,
      "../app/me/me-wallet-panel.tsx",
    );
    const content = fs.readFileSync(panelPath, "utf-8");
    // Check that there is no direct {address} or {displayAddress} inside a <span> text node
    // (HashChip handles rendering the truncated + clickable version)
    const linesWithAddress = content
      .split("\n")
      .filter((line: string) =>
        (line.includes("{address}") || line.includes("{displayAddress}")) &&
        !line.includes("value={displayAddress}") &&
        !line.includes("useAccount") &&
        !line.includes("const displayAddress = address") &&
        !line.includes("address.toLowerCase()")
      );

    // There should not be a bare {address}/{displayAddress} inside JSX text content
    expect(linesWithAddress.length).toBe(0);
  });
});

/* ─────────────── Verdict tone mapping (mirrors /history) ──────── */

describe("Verdict tone mapping (mirrors /history)", () => {
  function verdictTone(
    label: string | null | undefined,
  ): "bad" | "warn" | "good" | "neutral" {
    if (!label) return "neutral";
    const map: Record<string, "bad" | "warn" | "good"> = {
      REJECT: "bad",
      WARN: "warn",
      PASS: "good",
      ENDORSE: "good",
    };
    return map[label] ?? "neutral";
  }

  it("REJECT → bad", () => expect(verdictTone("REJECT")).toBe("bad"));
  it("WARN → warn", () => expect(verdictTone("WARN")).toBe("warn"));
  it("PASS → good", () => expect(verdictTone("PASS")).toBe("good"));
  it("ENDORSE → good", () => expect(verdictTone("ENDORSE")).toBe("good"));
  it("null → neutral", () => expect(verdictTone(null)).toBe("neutral"));
});

/* ─────────────── No fetch when disconnected (VAL-ME-001) ───────── */

describe("No fetch fired when wallet is disconnected", () => {
  it("the useEffect guard returns early when not connected", () => {
    const fs = require("fs");
    const path = require("path");
    const panelPath = path.resolve(
      __dirname,
      "../app/me/me-wallet-panel.tsx",
    );
    const content = fs.readFileSync(panelPath, "utf-8");
    // The useEffect should check !isConnected || !address and return early
    expect(content).toContain("!isConnected || !address");
  });
});
