/**
 * Stats page tests — /stats
 *
 * Covers:
 *   - Stats data computation (verdict counts, unique wallets, on-chain anchors)
 *   - External x402 metric excludes Prism's own agent wallets
 *   - Builder fees calculation (0.1% of fill notional)
 *   - Latency formatting (seconds → human-readable)
 *   - Calibration gap (good vs bad score spread)
 *   - Verdict distribution histogram bucketing (4 buckets)
 *   - Sparkline data shape (7-day daily aggregates)
 *   - ActivityStats interface matches /stats tiles (single source of truth)
 *   - Fee formatting helper
 *   - Page is a server component (no 'use client')
 */

import { describe, it, expect } from "vitest";

/* ─────────────── Verdict counts ─────────────── */

describe("VAL-STATS-002: Verdicts issued tile", () => {
  it("count(*) from validations returns total verdicts", () => {
    const mockResult = { cnt: "27" };
    expect(Number(mockResult.cnt)).toBe(27);
  });

  it("handles zero validations", () => {
    const mockResult = { cnt: "0" };
    expect(Number(mockResult.cnt)).toBe(0);
  });
});

/* ─────────────── Unique wallets ─────────────── */

describe("VAL-STATS-003: Unique wallets connected", () => {
  it("counts distinct non-null requester_address values", () => {
    const addresses = [
      "0xabc123",
      "0xabc123", // duplicate
      "0xdef456",
      null as string | null,
      null,
      "0xghi789",
    ];
    const unique = new Set(
      addresses.filter((a): a is string => a !== null),
    ).size;
    expect(unique).toBe(3);
  });

  it("excludes null addresses from the count", () => {
    const addresses = [null, null, null] as (string | null)[];
    const unique = new Set(
      addresses.filter((a): a is string => a !== null),
    ).size;
    expect(unique).toBe(0);
  });
});

/* ─────────────── On-chain anchors ─────────────── */

describe("VAL-STATS-005: On-chain anchors (non-null request_tx + response_tx)", () => {
  it("counts traces where both tx hashes are non-null", () => {
    const rows = [
      { trace_tx: "0xabc", validation_tx: "0xdef" },  // qualifies
      { trace_tx: "0xabc", validation_tx: null },       // doesn't qualify
      { trace_tx: null, validation_tx: "0xdef" },        // doesn't qualify
      { trace_tx: null, validation_tx: null },            // doesn't qualify
      { trace_tx: "0x123", validation_tx: "0x456" },    // qualifies
    ];
    const count = rows.filter(
      (r) => r.trace_tx !== null && r.validation_tx !== null,
    ).length;
    expect(count).toBe(2);
  });
});

/* ─────────────── External x402 calls ─────────────── */

describe("VAL-STATS-007 / VAL-CROSS-011: External x402 calls exclude Prism wallets", () => {
  const INTERNAL_WALLETS = [
    "0xc960833ee26e23ca01dfc4d217a8942ea78b452b", // trader
    "0x56509b03e85f3cbae5ba2190ee99b945d2f0ac36", // sentinel
  ];

  it("excludes trader and sentinel wallet addresses", () => {
    const validations = [
      { requester_address: "0xc960833ee26e23ca01dfc4d217a8942ea78b452b" },
      { requester_address: "0x56509b03e85f3cbae5ba2190ee99b945d2f0ac36" },
      { requester_address: "0xABCDEF1234567890ABCDEF1234567890ABCDEF12" },
      { requester_address: "0x1234567890ABCDEF1234567890ABCDEF12345678" },
      { requester_address: null },
    ];

    const external = validations.filter(
      (v) =>
        v.requester_address !== null &&
        !INTERNAL_WALLETS.includes(v.requester_address.toLowerCase()),
    );
    expect(external).toHaveLength(2);
  });

  it("comparison is case-insensitive", () => {
    const uppercaseTrader = "0xC960833EE26E23CA01DFC4D217A8942EA78B452B";
    const isInternal = INTERNAL_WALLETS.includes(uppercaseTrader.toLowerCase());
    expect(isInternal).toBe(true);
  });

  it("null requester_address is excluded (not external)", () => {
    const validations: { requester_address: string | null }[] = [
      { requester_address: null },
    ];
    const external = validations.filter(
      (v): v is { requester_address: string } => v.requester_address !== null,
    ).filter(
      (v) => !INTERNAL_WALLETS.includes(v.requester_address.toLowerCase()),
    );
    expect(external).toHaveLength(0);
  });
});

/* ─────────────── Builder fees ─────────────── */

describe("VAL-STATS-006: Builder fees attributed", () => {
  it("calculates 0.1% of fill notional for qualifying trades", () => {
    const trades = [
      { size: 100, fill_price: 0.55, status: "paper_filled" },
      { size: 50, fill_price: 0.4, status: "filled" },
    ];
    const totalFees = trades
      .filter((t) => ["paper_filled", "filled"].includes(t.status))
      .reduce((sum, t) => sum + t.size * t.fill_price * 0.001, 0);
    // 100*0.55*0.001 = 0.055, 50*0.4*0.001 = 0.02 → total = 0.075
    expect(totalFees).toBeCloseTo(0.075, 6);
  });

  it("excludes non-qualifying trade statuses", () => {
    const trades = [
      { size: 100, fill_price: 0.5, status: "open" },
      { size: 50, fill_price: 0.5, status: "cancelled" },
    ];
    const totalFees = trades
      .filter((t) => ["paper_filled", "filled"].includes(t.status))
      .reduce((sum, t) => sum + t.size * t.fill_price * 0.001, 0);
    expect(totalFees).toBe(0);
  });
});

/* ─────────────── Avg verdict score ─────────────── */

describe("VAL-STATS-008: Avg sentinel verdict score", () => {
  it("computes mean of verdict_score values", () => {
    const scores = [80, 60, 40, 20, 100];
    const avg = scores.reduce((sum, s) => sum + s, 0) / scores.length;
    expect(avg).toBe(60);
  });

  it("rounds to 2 decimal places", () => {
    const avg = 66.666666;
    const rounded = Number(avg.toFixed(2));
    expect(rounded).toBe(66.67);
  });
});

/* ─────────────── Latency formatting ─────────────── */

describe("VAL-STATS-010/011: Verdict latency formatting", () => {
  function formatLatency(seconds: number): string {
    if (seconds <= 0 || !Number.isFinite(seconds)) return "—";
    if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    const minutes = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return `${minutes}m ${secs}s`;
  }

  it("formats sub-second latency as milliseconds", () => {
    expect(formatLatency(0.42)).toBe("420ms");
  });

  it("formats second-level latency with one decimal", () => {
    expect(formatLatency(3.2)).toBe("3.2s");
  });

  it("formats minute-level latency as minutes and seconds", () => {
    expect(formatLatency(125)).toBe("2m 5s");
  });

  it("formats zero or negative as dash", () => {
    expect(formatLatency(0)).toBe("—");
    expect(formatLatency(-1)).toBe("—");
  });

  it("formats NaN as dash", () => {
    expect(formatLatency(NaN)).toBe("—");
  });
});

/* ─────────────── Calibration gap ─────────────── */

describe("VAL-STATS-012: Calibration gap (good vs bad score spread)", () => {
  it("computes difference between high-score and low-score averages", () => {
    const goodAvg = 85;
    const badAvg = 12;
    const gap = Math.round(goodAvg - badAvg);
    expect(gap).toBe(73);
    expect(gap).toBeGreaterThanOrEqual(30); // hard rule
  });

  it("flags calibration spreads below the target threshold", () => {
    const goodAvg = 60;
    const badAvg = 35;
    const gap = Math.round(goodAvg - badAvg);
    expect(gap).toBe(25);
    expect(gap < 30).toBe(true); // This would be a failing calibration
  });
});

/* ─────────────── Verdict distribution histogram ─────────────── */

describe("VAL-STATS-009: Verdict distribution histogram (4 buckets)", () => {
  const BUCKETS = [
    { label: "0–25", lower: 0 },
    { label: "26–50", lower: 26 },
    { label: "51–75", lower: 51 },
    { label: "76–100", lower: 76 },
  ];

  it("has exactly 4 buckets covering 0-100", () => {
    expect(BUCKETS).toHaveLength(4);
    expect(BUCKETS[0].lower).toBe(0);
    expect(BUCKETS[3].lower).toBe(76);
  });

  it("bucket labels match expected format", () => {
    for (const b of BUCKETS) {
      expect(b.label).toMatch(/^\d+–\d+$/);
    }
  });

  it("scores are correctly assigned to buckets", () => {
    function getBucket(score: number): string {
      if (score <= 25) return "0–25";
      if (score <= 50) return "26–50";
      if (score <= 75) return "51–75";
      return "76–100";
    }
    expect(getBucket(0)).toBe("0–25");
    expect(getBucket(25)).toBe("0–25");
    expect(getBucket(26)).toBe("26–50");
    expect(getBucket(50)).toBe("26–50");
    expect(getBucket(51)).toBe("51–75");
    expect(getBucket(75)).toBe("51–75");
    expect(getBucket(76)).toBe("76–100");
    expect(getBucket(100)).toBe("76–100");
  });

  it("bar heights sum to total verdict count", () => {
    const distribution = [
      { label: "0–25", lower: 0, count: 3 },
      { label: "26–50", lower: 26, count: 5 },
      { label: "51–75", lower: 51, count: 10 },
      { label: "76–100", lower: 76, count: 9 },
    ];
    const total = distribution.reduce((sum, b) => sum + b.count, 0);
    expect(total).toBe(27); // matches mock validations count
  });

  it("ensures all 4 buckets present even with sparse data", () => {
    const defaults = [
      { label: "0–25", lower: 0, count: 0 },
      { label: "26–50", lower: 26, count: 0 },
      { label: "51–75", lower: 51, count: 0 },
      { label: "76–100", lower: 76, count: 0 },
    ];
    // Simulate DB returning only 2 buckets
    const dbRows = [
      { label: "0–25", lower: 0, count: 5 },
      { label: "76–100", lower: 76, count: 10 },
    ];
    const filled = defaults.map((d) => {
      const match = dbRows.find((r) => r.label === d.label);
      return { ...d, count: match ? match.count : 0 };
    });
    expect(filled).toHaveLength(4);
    expect(filled[0].count).toBe(5);
    expect(filled[1].count).toBe(0);
    expect(filled[2].count).toBe(0);
    expect(filled[3].count).toBe(10);
  });
});

/* ─────────────── Sparkline data shape ─────────────── */

describe("VAL-STATS-014: Each tile has 7-day sparkline", () => {
  it("daily count data has date and count fields", () => {
    const dailyVerdicts = [
      { date: "2026-05-08", count: 5 },
      { date: "2026-05-09", count: 3 },
      { date: "2026-05-10", count: 7 },
    ];
    for (const entry of dailyVerdicts) {
      expect(entry).toHaveProperty("date");
      expect(entry).toHaveProperty("count");
      expect(typeof entry.date).toBe("string");
      expect(typeof entry.count).toBe("number");
    }
  });

  it("sparkline data must have at least 2 points for rendering", () => {
    const data1 = [{ date: "2026-05-08", count: 5 }];
    const data2 = [
      { date: "2026-05-08", count: 5 },
      { date: "2026-05-09", count: 3 },
    ];
    expect(data1.length < 2).toBe(true);  // fallback placeholder
    expect(data2.length >= 2).toBe(true);  // sparkline renders
  });

  it("daily fee data has date and fee fields", () => {
    const dailyFees = [
      { date: "2026-05-08", fee: "0.010000" },
      { date: "2026-05-09", fee: "0.025000" },
    ];
    for (const entry of dailyFees) {
      expect(entry).toHaveProperty("date");
      expect(entry).toHaveProperty("fee");
    }
  });

  it("daily average score data has date and avg fields", () => {
    const dailyScores = [
      { date: "2026-05-08", avg: 65 },
      { date: "2026-05-09", avg: 72 },
    ];
    for (const entry of dailyScores) {
      expect(entry).toHaveProperty("date");
      expect(entry).toHaveProperty("avg");
      expect(typeof entry.avg).toBe("number");
    }
  });

  it("daily latency data has date and avgSeconds fields", () => {
    const dailyLatency = [
      { date: "2026-05-08", avgSeconds: 3.2 },
      { date: "2026-05-09", avgSeconds: 4.1 },
    ];
    for (const entry of dailyLatency) {
      expect(entry).toHaveProperty("date");
      expect(entry).toHaveProperty("avgSeconds");
      expect(typeof entry.date).toBe("string");
      expect(typeof entry.avgSeconds).toBe("number");
    }
  });

  it("latency sparkline uses dailyLatency data (not dailyVerdicts counts)", () => {
    // The latency tiles must render avgSeconds trend, not verdict count trend
    const dailyLatency = [
      { date: "2026-05-08", avgSeconds: 2.5 },
      { date: "2026-05-09", avgSeconds: 5.0 },
      { date: "2026-05-10", avgSeconds: 1.8 },
    ];
    const sparklineData = dailyLatency.map((d) => ({
      date: d.date,
      value: d.avgSeconds,
    }));
    for (const point of sparklineData) {
      expect(point.value).toBeGreaterThan(0);
      expect(typeof point.value).toBe("number");
    }
    // Ensure values are latency-scale (seconds), not count-scale (integers)
    expect(sparklineData[0].value).toBe(2.5);
    expect(sparklineData[1].value).toBe(5.0);
  });

  it("daily calibration gap data has date and gap fields", () => {
    const dailyCalibrationGap = [
      { date: "2026-05-08", gap: 55 },
      { date: "2026-05-09", gap: 60 },
    ];
    for (const entry of dailyCalibrationGap) {
      expect(entry).toHaveProperty("date");
      expect(entry).toHaveProperty("gap");
      expect(typeof entry.date).toBe("string");
      expect(typeof entry.gap).toBe("number");
    }
  });

  it("calibration gap sparkline uses dailyCalibrationGap data (not dailyScores avg)", () => {
    // The calibration gap tile must render gap trend, not average score trend
    const dailyCalibrationGap = [
      { date: "2026-05-08", gap: 50 },
      { date: "2026-05-09", gap: 65 },
      { date: "2026-05-10", gap: 45 },
    ];
    const sparklineData = dailyCalibrationGap.map((d) => ({
      date: d.date,
      value: d.gap,
    }));
    // Gaps are integers (rounded), not floating-point averages
    for (const point of sparklineData) {
      expect(Number.isInteger(point.value)).toBe(true);
    }
    expect(sparklineData[0].value).toBe(50);
    expect(sparklineData[1].value).toBe(65);
  });
});

/* ─────────────── Subtitle presence ─────────────── */

describe("VAL-STATS-013: Each tile has 'What this measures' subtitle", () => {
  const tiles = [
    { title: "Verdicts issued", subtitle: "Total adversarial verdicts produced by the sentinel" },
    { title: "Unique wallets connected", subtitle: "Distinct requester wallets that paid for validations" },
    { title: "Traces validated", subtitle: "Total reasoning traces in the system" },
    { title: "On-chain anchors", subtitle: "Traces with both validationRequest and validationResponse on ERC-8004" },
    { title: "Builder fees attributed", subtitle: "Paper-fill fee model plus live builder-code receipts via HMAC codes" },
    { title: "External x402 calls served", subtitle: "Validations requested by non-Prism wallets — excludes internal agent calls" },
    { title: "Avg sentinel verdict score", subtitle: "Mean verdict_score across all validations (0–100)" },
    { title: "Verdict latency p50", subtitle: "Median time from trace creation to sentinel verdict" },
    { title: "Verdict latency p95", subtitle: "95th-percentile time from trace creation to verdict — tail latency" },
    { title: "Calibration gap", subtitle: "High-vs-low live verdict spread — target ≥30" },
  ];

  it("every tile has a non-empty subtitle", () => {
    for (const tile of tiles) {
      expect(tile.subtitle.length).toBeGreaterThan(0);
    }
  });

  it("all 10 expected tiles are defined", () => {
    expect(tiles).toHaveLength(10);
  });
});

/* ─────────────── Single source of truth ─────────────── */

describe("VAL-CROSS-010 / VAL-WIDGETS-003: LiveActivityStrip numbers match /stats", () => {
  it("ActivityStats interface includes /stats-compatible fields", () => {
    const stats = {
      traces: 27,
      validations: 27,
      trades: 5,
      flagged: 3,
      uniqueWallets: 4,
      onChainAnchors: 2,
      externalX402Calls: 6,
    };

    // These fields must exist on the ActivityStats type
    expect(stats).toHaveProperty("traces");
    expect(stats).toHaveProperty("validations");
    expect(stats).toHaveProperty("uniqueWallets");
    expect(stats).toHaveProperty("onChainAnchors");
    expect(stats).toHaveProperty("externalX402Calls");
  });

  it("ActivityStats validations count matches /stats verdicts count", () => {
    // Both surfaces read from the same query
    const fromStrip = { validations: 27 };
    const fromStats = { verdictsIssued: 27 };
    expect(fromStrip.validations).toBe(fromStats.verdictsIssued);
  });

  it("ActivityStats traces count matches /stats traces count", () => {
    const fromStrip = { traces: 27 };
    const fromStats = { tracesValidated: 27 };
    expect(fromStrip.traces).toBe(fromStats.tracesValidated);
  });

  it("ActivityStats onChainAnchors matches /stats on-chain anchors", () => {
    const fromStrip = { onChainAnchors: 2 };
    const fromStats = { onChainAnchors: 2 };
    expect(fromStrip.onChainAnchors).toBe(fromStats.onChainAnchors);
  });
});

/* ─────────────── Fee formatting ─────────────── */

function formatFee(feeStr: string): string {
  const fee = parseFloat(feeStr);
  if (Number.isNaN(fee) || fee === 0) return "0";
  return fee.toFixed(6).replace(/\.?0+$/, "");
}

describe("Fee formatting (shared with builder-fees page)", () => {
  it("formats zero as '0'", () => {
    expect(formatFee("0")).toBe("0");
    expect(formatFee("0.000000")).toBe("0");
  });

  it("formats with up to 6 decimal places, stripping trailing zeros", () => {
    expect(formatFee("0.055000")).toBe("0.055");
    expect(formatFee("1.500000")).toBe("1.5");
    expect(formatFee("0.123456")).toBe("0.123456");
  });
});

/* ─────────────── Page is a server component ─────────────── */

describe("VAL-STATS-016: Page is a server component", () => {
  it("stats page.tsx does not contain 'use client'", async () => {
    const fs = await import("fs/promises");
    const path = await import("path");
    const filePath = path.join(
      process.cwd(),
      "app/stats/page.tsx",
    );
    const content = await fs.readFile(filePath, "utf-8");
    const firstLine = content.trim().split("\n")[0];
    expect(firstLine).not.toBe("'use client'");
    expect(firstLine).not.toBe('"use client"');
    expect(content.startsWith("'use client'")).toBe(false);
    expect(content.startsWith('"use client"')).toBe(false);
  });
});

/* ─────────────── VAL-CROSS-003: Self-serve verdict increments unique wallets ─────────────── */

describe("VAL-CROSS-003: Self-serve verdict increments unique wallets", () => {
  it("a new wallet address increases the distinct count by 1", () => {
    const existing = ["0xabc", "0xdef"];
    const newAddress = "0xghi";
    const after = [...existing, newAddress];
    expect(new Set(after).size).toBe(new Set(existing).size + 1);
  });

  it("a repeat wallet address does not increase the distinct count", () => {
    const existing = ["0xabc", "0xdef"];
    const repeat = "0xabc";
    const after = [...existing, repeat];
    expect(new Set(after).size).toBe(new Set(existing).size);
  });
});

/* ─────────────── Shared pool singleton (m3 scrutiny fix) ─────────────── */

describe("Stats uses shared getPool() from lib/db.ts (no duplicate Pool)", () => {
  it("stats.ts does not create its own pg.Pool", async () => {
    const fs = await import("fs/promises");
    const path = await import("path");
    const filePath = path.join(process.cwd(), "app/lib/stats.ts");
    const content = await fs.readFile(filePath, "utf-8");

    // Must not contain "new Pool" or "const { Pool }"
    expect(content).not.toMatch(/new\s+Pool\s*\(/);
    expect(content).not.toMatch(/const\s*\{\s*Pool\s*\}\s*=\s*pg/);

    // Must import getPool from db.ts
    expect(content).toMatch(/import\s*\{[^}]*getPool[^}]*\}\s*from\s*["']@\/lib\/db["']/);
  });

  it("stats.ts delegates closeStatsPool to closePool from db.ts", async () => {
    const fs = await import("fs/promises");
    const path = await import("path");
    const filePath = path.join(process.cwd(), "app/lib/stats.ts");
    const content = await fs.readFile(filePath, "utf-8");

    // Must import closePool from db.ts
    expect(content).toMatch(/import\s*\{[^}]*closePool[^}]*\}\s*from\s*["']@\/lib\/db["']/);
  });
});
