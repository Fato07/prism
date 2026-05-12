/** Tests for VAL-TRADE-008: getBuilderTrades polling persists fill status.

Mocks the CLOB SDK + Neon to verify:
- open live trades are reconciled against fetched builder trades
- transactionHash from a matched trade is written into polymarket_tx
- status flips from 'open' to 'filled'
*/

import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

const fetchBuilderTradesMock = vi.fn();

vi.mock("../src/clob.js", () => ({
  fetchBuilderTrades: fetchBuilderTradesMock,
  submitLiveOrder: vi.fn(),
  getClobClient: vi.fn(),
  resetClobClient: vi.fn(),
}));

let updateStatusCalls: Array<{ orderId: string; status: string; tx: string | null }> = [];
const openTradesRef: { value: Array<Record<string, unknown>> } = { value: [] };

vi.mock("../src/db.js", () => ({
  listOpenLiveTrades: vi.fn(async () => openTradesRef.value),
  updateTradeStatus: vi.fn(async (orderId: string, status: string, tx: string | null) => {
    updateStatusCalls.push({ orderId, status, tx });
    return true;
  }),
  persistTrade: vi.fn(async () => true),
  getTrade: vi.fn(async () => null),
}));

beforeAll(() => {
  process.env.PRISM_TRADE_MODE = "live";
  process.env.POLY_BUILDER_CODE = "0xtestbuildercode";
  process.env.DATABASE_URL = "NEON_DATABASE_URL_PLACEHOLDER";
  process.env.BUILDER_HMAC_SECRET = "test-hmac-secret";
  process.env.WALLET_BALANCE_CAP_USDC = "100";
  process.env.LOCALE = "EE";
});

beforeEach(async () => {
  fetchBuilderTradesMock.mockReset();
  updateStatusCalls = [];
  openTradesRef.value = [];
  const { resetEnv } = await import("../src/env.js");
  resetEnv();
});

const { reconcileOpenLiveTrades } = await import("../src/polling.js");

describe("VAL-TRADE-008: builder-trades polling persists fill status", () => {
  it("returns zero-result when no open trades", async () => {
    openTradesRef.value = [];
    const r = await reconcileOpenLiveTrades();
    expect(r).toEqual({ checked: 0, filled: 0, unchanged: 0 });
    expect(fetchBuilderTradesMock).not.toHaveBeenCalled();
  });

  it("matches by order_id and writes filled status with polymarket_tx", async () => {
    openTradesRef.value = [
      {
        order_id: "ord-A",
        trace_id: "t-A",
        market_id: "m1",
        side: "BUY",
        size: "7",
        builder_code: "0xcode1",
        status: "open",
        polymarket_tx: null,
        created_at: new Date().toISOString(),
      },
    ];
    fetchBuilderTradesMock.mockResolvedValueOnce([
      {
        id: "ord-A",
        transactionHash:
          "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        builderCode: "0xcode1",
        market: "m1",
        size: "7",
        sizeUsdc: "7",
        price: "0.5",
        status: "MATCHED",
      },
    ]);

    const r = await reconcileOpenLiveTrades();
    expect(r.checked).toBe(1);
    expect(r.filled).toBe(1);
    expect(updateStatusCalls).toEqual([
      {
        orderId: "ord-A",
        status: "filled",
        tx: "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
      },
    ]);
  });

  it("leaves trades unchanged when no transactionHash is available yet", async () => {
    openTradesRef.value = [
      {
        order_id: "ord-B",
        trace_id: "t-B",
        market_id: "m1",
        side: "BUY",
        size: "5",
        builder_code: "0xcode1",
        status: "open",
        polymarket_tx: null,
        created_at: new Date().toISOString(),
      },
    ];
    fetchBuilderTradesMock.mockResolvedValueOnce([
      {
        id: "ord-B",
        transactionHash: "",
        builderCode: "0xcode1",
        market: "m1",
        status: "PENDING",
      },
    ]);
    const r = await reconcileOpenLiveTrades();
    expect(r.filled).toBe(0);
    expect(r.unchanged).toBe(1);
    expect(updateStatusCalls).toEqual([]);
  });

  it("survives fetchBuilderTrades errors and reports zero filled", async () => {
    openTradesRef.value = [
      {
        order_id: "ord-C",
        trace_id: "t-C",
        market_id: "m1",
        side: "BUY",
        size: "7",
        builder_code: "0xcode1",
        status: "open",
        polymarket_tx: null,
        created_at: new Date().toISOString(),
      },
    ];
    fetchBuilderTradesMock.mockRejectedValueOnce(new Error("network blip"));
    const r = await reconcileOpenLiveTrades();
    expect(r.checked).toBe(1);
    expect(r.filled).toBe(0);
  });

  it("queries Polymarket once per distinct builderCode", async () => {
    openTradesRef.value = [
      {
        order_id: "ord-1",
        builder_code: "0xcodeA",
        status: "open",
        polymarket_tx: null,
        trace_id: "x",
        market_id: "m",
        side: "BUY",
        size: "5",
        created_at: new Date().toISOString(),
      },
      {
        order_id: "ord-2",
        builder_code: "0xcodeA",
        status: "open",
        polymarket_tx: null,
        trace_id: "y",
        market_id: "m",
        side: "BUY",
        size: "5",
        created_at: new Date().toISOString(),
      },
      {
        order_id: "ord-3",
        builder_code: "0xcodeB",
        status: "open",
        polymarket_tx: null,
        trace_id: "z",
        market_id: "m",
        side: "BUY",
        size: "5",
        created_at: new Date().toISOString(),
      },
    ];
    fetchBuilderTradesMock.mockResolvedValue([]);
    await reconcileOpenLiveTrades();
    expect(fetchBuilderTradesMock).toHaveBeenCalledTimes(2);
  });
});
