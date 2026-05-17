/** Tests for VAL-POLY-004: Paper trade persisted to Neon trades table.

After paper trade execution, result written to trades table:
- order_id, trace_id, market_id, side, size, builder_code, status
- polymarket_tx is null for paper trades
- fill_price is recorded for paper fills so builder fee totals are not silently zero
- SELECT by order_id returns 1 matching row

Note: These tests require a real DATABASE_URL to a Neon instance with
the trades table. In unit test mode, we mock the DB layer.
*/

import { describe, it, expect, beforeAll, vi } from "vitest";

import { TradeReceipt } from "../src/trade.js";

beforeAll(() => {
  process.env.PRISM_TRADE_MODE = "paper";
  process.env.POLY_BUILDER_CODE = "0xtestbuildercode";
  process.env.DATABASE_URL = "NEON_DATABASE_URL_PLACEHOLDER";
  process.env.BUILDER_HMAC_SECRET = "test-hmac-secret";
  process.env.WALLET_BALANCE_CAP_USDC = "100";
});

// Mock the neon function from @neondatabase/serverless
vi.mock("@neondatabase/serverless", () => ({
  neon: vi.fn(() => {
    // Return a mock SQL function
    return vi.fn(async (strings: TemplateStringsArray, ...values: unknown[]) => {
      // Mock INSERT returns empty array (success)
      if (strings[0]?.includes("INSERT")) {
        return [];
      }
      // Mock SELECT returns a matching row
      if (strings[0]?.includes("SELECT")) {
        return [
          {
            order_id: "test-order-id",
            trace_id: "test-trace-id",
            market_id: "test-market-id",
            side: "BUY",
            size: "10",
            builder_code: "0xabcdef",
            status: "paper_filled",
            polymarket_tx: null,
            fill_price: "0.5",
            created_at: new Date().toISOString(),
          },
        ];
      }
      return [];
    });
  }),
}));

import { persistTrade, getTrade } from "../src/db.js";

describe("VAL-POLY-004: Paper trade persisted to Neon", () => {
  const mockReceipt: TradeReceipt = {
    orderId: "test-order-id",
    traceId: "test-trace-id",
    marketId: "test-market-id",
    side: "BUY",
    size: 10,
    builderCode: "0xabcdef",
    status: "paper_filled",
    timestamp: new Date().toISOString(),
    fillPrice: 0.5,
  };

  it("persistTrade returns true on success", async () => {
    const result = await persistTrade(mockReceipt);
    expect(result).toBe(true);
  });

  it("getTrade returns a row with polymarket_tx null for paper trades", async () => {
    const row = await getTrade("test-order-id");
    expect(row).not.toBeNull();
    expect(row?.polymarket_tx).toBeNull();
    expect(row?.status).toBe("paper_filled");
    expect(row?.fill_price).toBe("0.5");
  });

  it("persisted trade has all required fields", async () => {
    const row = await getTrade("test-order-id");
    expect(row).toHaveProperty("order_id");
    expect(row).toHaveProperty("trace_id");
    expect(row).toHaveProperty("market_id");
    expect(row).toHaveProperty("side");
    expect(row).toHaveProperty("size");
    expect(row).toHaveProperty("builder_code");
    expect(row).toHaveProperty("status");
    expect(row).toHaveProperty("polymarket_tx");
    expect(row).toHaveProperty("fill_price");
  });

  it("getTrade returns null for non-existent order", async () => {
    // Override the mock for this test to return empty array
    const { neon } = await import("@neondatabase/serverless");
    const mockNeon = vi.mocked(neon);
    const mockSql = vi.fn().mockResolvedValue([]);
    mockNeon.mockReturnValue(mockSql);

    const row = await getTrade("nonexistent");
    expect(row).toBeNull();

    // Restore
    vi.restoreAllMocks();
  });
});
