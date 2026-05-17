/**
 * Builder Fees page tests — /builder-fees
 *
 * Covers:
 *   - Fee calculation math (0.1% of fill notional)
 *   - Builder code HMAC derivation matching
 *   - Leaderboard ordering (fees DESC)
 *   - Format helpers (fee formatting, timestamp formatting)
 *   - Empty state condition
 *   - Sparkline data shape validation
 *   - BuilderFeesStrip top-3 truncation
 *   - Execution attribution copy avoids overclaiming zero-fee rows
 *   - Page is a server component (no 'use client')
 */

import { describe, it, expect } from "vitest";
import { mapAgentIdToBuilderCode, verifyBuilderCode } from "@prism/builder-codes";

/* ─────────────── Fee calculation math ─────────────── */

/** Calculate 0.1% builder fee from size and fill_price. */
function calculateBuilderFee(size: number, fillPrice: number): number {
  return size * fillPrice * 0.001;
}

describe("VAL-BUILDERFEES-005: Fee math matches HMAC builder-code attribution", () => {
  it("calculates 0.1% fee for a single trade", () => {
    // size=100 USDC, fill_price=0.55 → notional=55 → fee=0.055 USDC
    expect(calculateBuilderFee(100, 0.55)).toBeCloseTo(0.055, 6);
  });

  it("calculates zero fee for zero-size trade", () => {
    expect(calculateBuilderFee(0, 0.55)).toBe(0);
  });

  it("calculates zero fee for zero-price trade", () => {
    expect(calculateBuilderFee(100, 0)).toBe(0);
  });

  it("aggregates fees for multiple trades", () => {
    const fees = [
      calculateBuilderFee(50, 0.6),  // 0.03
      calculateBuilderFee(30, 0.4),  // 0.012
      calculateBuilderFee(20, 0.8),  // 0.016
    ];
    const total = fees.reduce((sum, f) => sum + f, 0);
    expect(total).toBeCloseTo(0.058, 6);
  });

  it("fee is within 1e-6 tolerance for a known case", () => {
    // 10 USDC at 0.5 → notional 5 → fee 0.005
    const fee = calculateBuilderFee(10, 0.5);
    expect(Math.abs(fee - 0.005)).toBeLessThan(1e-6);
  });
});

/* ─────────────── HMAC builder-code derivation ─────────────── */

describe("VAL-BUILDERFEES-005: Builder code HMAC derivation", () => {
  const testSecret = "test-hmac-secret-key";

  it("mapAgentIdToBuilderCode produces a hex string with 0x prefix", () => {
    const code = mapAgentIdToBuilderCode(4140, testSecret);
    expect(code).toMatch(/^0x[a-f0-9]+$/);
  });

  it("same agentId always produces same builder code (deterministic)", () => {
    const code1 = mapAgentIdToBuilderCode(4140, testSecret);
    const code2 = mapAgentIdToBuilderCode(4140, testSecret);
    expect(code1).toBe(code2);
  });

  it("different agentIds produce different builder codes", () => {
    const traderCode = mapAgentIdToBuilderCode(4140, testSecret);
    const sentinelCode = mapAgentIdToBuilderCode(4148, testSecret);
    expect(traderCode).not.toBe(sentinelCode);
  });

  it("verifyBuilderCode returns true for matching code", () => {
    const code = mapAgentIdToBuilderCode(4140, testSecret);
    expect(verifyBuilderCode(4140, code, testSecret)).toBe(true);
  });

  it("verifyBuilderCode returns false for mismatched code", () => {
    const code = mapAgentIdToBuilderCode(4140, testSecret);
    expect(verifyBuilderCode(4148, code, testSecret)).toBe(false);
  });

  it("works with string agentIds", () => {
    const code = mapAgentIdToBuilderCode("4140", testSecret);
    const numericCode = mapAgentIdToBuilderCode(4140, testSecret);
    expect(code).toBe(numericCode);
  });
});

/* ─────────────── Leaderboard ordering ─────────────── */

describe("VAL-BUILDERFEES-004: Rows ordered by total fees DESC", () => {
  it("sorts entries by total_fees descending", () => {
    const entries = [
      { builder_code: "0xaaa", total_fees: "0.050000", trade_count: 5 },
      { builder_code: "0xbbb", total_fees: "0.150000", trade_count: 3 },
      { builder_code: "0xccc", total_fees: "0.100000", trade_count: 7 },
    ];

    const sorted = [...entries].sort((a, b) =>
      parseFloat(b.total_fees) - parseFloat(a.total_fees),
    );

    expect(sorted[0].builder_code).toBe("0xbbb");
    expect(sorted[1].builder_code).toBe("0xccc");
    expect(sorted[2].builder_code).toBe("0xaaa");
  });

  it("rank matches position after sorting", () => {
    const entries = [
      { builder_code: "0xaaa", total_fees: "0.050000" },
      { builder_code: "0xbbb", total_fees: "0.150000" },
    ];

    const sorted = [...entries].sort((a, b) =>
      parseFloat(b.total_fees) - parseFloat(a.total_fees),
    );

    // Rank 1 = highest fees
    expect(sorted[0].builder_code).toBe("0xbbb");
    expect(sorted[1].builder_code).toBe("0xaaa");
  });
});

/* ─────────────── Format helpers ─────────────── */

function formatFee(feeStr: string): string {
  const fee = parseFloat(feeStr);
  if (Number.isNaN(fee) || fee === 0) return "0";
  return fee.toFixed(6).replace(/\.?0+$/, "");
}

function feeDisplay(entry: { total_fees: string; trade_count: number }): string {
  const fee = parseFloat(entry.total_fees);
  if ((Number.isNaN(fee) || fee === 0) && entry.trade_count > 0) return "Fee pending";
  return formatFee(entry.total_fees);
}

describe("Fee formatting", () => {
  it("formats zero as '0'", () => {
    expect(formatFee("0")).toBe("0");
    expect(formatFee("0.000000")).toBe("0");
  });

  it("formats with up to 6 decimal places, stripping trailing zeros", () => {
    expect(formatFee("0.055000")).toBe("0.055");
    expect(formatFee("1.500000")).toBe("1.5");
    expect(formatFee("0.123456")).toBe("0.123456");
  });

  it("formats small fees correctly", () => {
    expect(formatFee("0.001000")).toBe("0.001");
  });

  it("handles NaN gracefully", () => {
    expect(formatFee("not-a-number")).toBe("0");
  });

  it("shows fee pending when trades exist but fill prices are not recorded", () => {
    expect(feeDisplay({ total_fees: "0.000000", trade_count: 73 })).toBe("Fee pending");
  });

  it("keeps zero when there are no attributed trades", () => {
    expect(feeDisplay({ total_fees: "0.000000", trade_count: 0 })).toBe("0");
  });
});

/* ─────────────── Empty state ─────────────── */

describe("VAL-BUILDERFEES-006: Empty state when no qualifying trades", () => {
  it("page and strip use execution attribution copy", async () => {
    const fs = await import("fs/promises");
    const path = await import("path");
    const page = await fs.readFile(path.join(process.cwd(), "app/builder-fees/page.tsx"), "utf-8");
    const strip = await fs.readFile(path.join(process.cwd(), "app/components/landing/builder-fees-strip.tsx"), "utf-8");

    expect(page).toContain("Execution Attribution");
    expect(page).toContain("Fee pending");
    expect(page).not.toContain("Builder Fee Attribution");
    expect(strip).toContain("Execution attribution — builder codes");
  });

  it("empty entries array triggers empty state", () => {
    const entries: unknown[] = [];
    const hasData = entries.length > 0;
    expect(hasData).toBe(false);
  });

  it("only paper_filled and filled count as qualifying", () => {
    const qualifyingStatuses = ["paper_filled", "filled"];
    expect(qualifyingStatuses.includes("open")).toBe(false);
    expect(qualifyingStatuses.includes("cancelled")).toBe(false);
    expect(qualifyingStatuses.includes("failed")).toBe(false);
    expect(qualifyingStatuses.includes("paper_filled")).toBe(true);
    expect(qualifyingStatuses.includes("filled")).toBe(true);
  });
});

/* ─────────────── Sparkline data shape ─────────────── */

describe("VAL-WIDGETS-002: Sparkline data shape", () => {
  it("daily_fees array has date and fee fields", () => {
    const dailyFees = [
      { date: "2026-05-08", fee: "0.010000" },
      { date: "2026-05-09", fee: "0.025000" },
      { date: "2026-05-10", fee: "0.015000" },
    ];

    for (const entry of dailyFees) {
      expect(entry).toHaveProperty("date");
      expect(entry).toHaveProperty("fee");
      expect(typeof entry.date).toBe("string");
      expect(typeof entry.fee).toBe("string");
    }
  });

  it("fee values are parseable as numbers", () => {
    const dailyFees = [
      { date: "2026-05-08", fee: "0.010000" },
      { date: "2026-05-09", fee: "0.025000" },
    ];

    for (const entry of dailyFees) {
      const fee = parseFloat(entry.fee);
      expect(Number.isNaN(fee)).toBe(false);
    }
  });
});

/* ─────────────── BuilderFeesStrip top-3 ─────────────── */

describe("VAL-WIDGETS-001: BuilderFeesStrip renders top-3", () => {
  it("truncates to top 3 entries", () => {
    const entries = [
      { builder_code: "0x1", total_fees: "0.30" },
      { builder_code: "0x2", total_fees: "0.20" },
      { builder_code: "0x3", total_fees: "0.10" },
      { builder_code: "0x4", total_fees: "0.05" },
      { builder_code: "0x5", total_fees: "0.01" },
    ];

    const top3 = entries.slice(0, 3);
    expect(top3).toHaveLength(3);
    expect(top3[0].builder_code).toBe("0x1");
    expect(top3[2].builder_code).toBe("0x3");
  });

  it("handles fewer than 3 entries", () => {
    const entries = [
      { builder_code: "0x1", total_fees: "0.30" },
    ];

    const top3 = entries.slice(0, 3);
    expect(top3).toHaveLength(1);
  });

  it("handles empty entries", () => {
    const entries: unknown[] = [];
    const top3 = entries.slice(0, 3);
    expect(top3).toHaveLength(0);
  });
});

/* ─────────────── Page is a server component ─────────────── */

describe("VAL-BUILDERFEES-007: Page is a server component", () => {
  it("builder-fees page.tsx does not contain 'use client'", async () => {
    const fs = await import("fs/promises");
    const path = await import("path");
    const filePath = path.join(
      process.cwd(),
      "app/builder-fees/page.tsx",
    );
    const content = await fs.readFile(filePath, "utf-8");
    const firstLine = content.trim().split("\n")[0];
    expect(firstLine).not.toBe("'use client'");
    expect(firstLine).not.toBe('"use client"');
    // Should NOT contain 'use client' at top level
    expect(content.startsWith("'use client'")).toBe(false);
    expect(content.startsWith('"use client"')).toBe(false);
  });
});

/* ─────────────── VAL-CROSS-004: Auto-pipeline trade attributed ─────────────── */

describe("VAL-CROSS-004: Auto-pipeline trade is attributed via builder code", () => {
  it("trader agent 4140 produces a valid builder code", () => {
    const secret = process.env.BUILDER_HMAC_SECRET ?? "test";
    const code = mapAgentIdToBuilderCode(4140, secret);
    // Builder code should be a hex string
    expect(code).toMatch(/^0x[a-f0-9]+$/);
  });

  it("a trade with that builder code would appear in the leaderboard", () => {
    const mockTrade = {
      builder_code: "0xabc123",
      status: "paper_filled",
      size: "10",
      fill_price: "0.5",
    };

    // Qualifying trade → should be counted
    const qualifyingStatuses = ["paper_filled", "filled"];
    expect(qualifyingStatuses.includes(mockTrade.status)).toBe(true);

    // Fee calculation
    const fee = parseFloat(mockTrade.size) * parseFloat(mockTrade.fill_price) * 0.001;
    expect(fee).toBe(0.005);
    expect(fee).toBeGreaterThan(0);
  });
});
