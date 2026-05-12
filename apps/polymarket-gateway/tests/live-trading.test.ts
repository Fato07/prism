/** Tests for live Polymarket trading (PRISM_TRADE_MODE=live).

Covers VAL-TRADE-001, 002, 004, 005, 006, 007, 009, 010.
The Polymarket V2 CLOB client is mocked via vi.mock("../src/clob.js", ...).
*/

import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@neondatabase/serverless", () => ({
  neon: vi.fn(() => vi.fn().mockResolvedValue([])),
}));

const submitLiveOrderMock = vi.fn();
const fetchBuilderTradesMock = vi.fn();

vi.mock("../src/clob.js", () => ({
  submitLiveOrder: submitLiveOrderMock,
  fetchBuilderTrades: fetchBuilderTradesMock,
  getClobClient: vi.fn(),
  resetClobClient: vi.fn(),
}));

beforeAll(() => {
  process.env.PRISM_TRADE_MODE = "live";
  process.env.POLY_BUILDER_CODE = "0xtestbuildercode";
  process.env.DATABASE_URL = "NEON_DATABASE_URL_PLACEHOLDER";
  process.env.BUILDER_HMAC_SECRET = "test-hmac-secret";
  process.env.WALLET_BALANCE_CAP_USDC = "100";
  process.env.LOCALE = "EE";
  process.env.LIVE_TRADE_MIN_USDC = "5";
  process.env.LIVE_TRADE_MAX_USDC = "10";
});

beforeEach(async () => {
  submitLiveOrderMock.mockReset();
  fetchBuilderTradesMock.mockReset();
  const { resetEnv } = await import("../src/env.js");
  resetEnv();
});

const { placePrismOrder } = await import("../src/trade.js");

describe("VAL-TRADE-001: Live mode executes real Polymarket CLOB order", () => {
  it("submits an order and returns the real Polymarket orderID", async () => {
    submitLiveOrderMock.mockResolvedValueOnce({
      success: true,
      orderID: "real-polymarket-order-id-12345",
      status: "matched",
      transactionsHashes: [
        "0xaabbccddeeff00112233445566778899aabbccddeeff00112233445566778899",
      ],
    });

    const receipt = await placePrismOrder({
      agentId: 1,
      traceId: "trace-xyz",
      marketId: "0xmarket1",
      tokenId: "12345",
      side: "BUY",
      sizeUsdc: 7,
    });

    expect(submitLiveOrderMock).toHaveBeenCalledOnce();
    const call = submitLiveOrderMock.mock.calls[0][0];
    expect(call.tokenId).toBe("12345");
    expect(call.builderCode).toMatch(/^0x[0-9a-f]{64}$/);
    expect(call.side).toBe("BUY");
    expect(call.sizeUsdc).toBe(7);

    expect(receipt.orderId).toBe("real-polymarket-order-id-12345");
    expect(receipt.orderId).not.toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
    );
  });
});

describe("VAL-TRADE-002 / VAL-TRADE-010: Live trade carries polymarket_tx + all fields", () => {
  it("populates polymarketTx with the Polygon tx hash and status filled when sync-filled", async () => {
    submitLiveOrderMock.mockResolvedValueOnce({
      success: true,
      orderID: "ord-001",
      status: "matched",
      transactionsHashes: [
        "0x9999999999999999999999999999999999999999999999999999999999999999",
      ],
    });
    const receipt = await placePrismOrder({
      agentId: 1,
      traceId: "trace-1",
      marketId: "0xmarket",
      tokenId: "token-1",
      side: "BUY",
      sizeUsdc: 8,
    });
    expect(receipt.polymarketTx).toMatch(/^0x[0-9a-f]{64}$/i);
    expect(receipt.status).toBe("filled");
    expect(receipt.builderCode).toMatch(/^0x[0-9a-f]{64}$/);
    expect(receipt.size).toBe(8);
    expect(receipt.side).toBe("BUY");
  });

  it("marks status open and polymarketTx null when no tx returned (resting order)", async () => {
    submitLiveOrderMock.mockResolvedValueOnce({
      success: true,
      orderID: "ord-resting",
      status: "live",
    });
    const receipt = await placePrismOrder({
      agentId: 1,
      traceId: "trace-2",
      marketId: "0xmarket",
      tokenId: "token-1",
      side: "BUY",
      sizeUsdc: 5,
    });
    expect(receipt.status).toBe("open");
    expect(receipt.polymarketTx).toBeNull();
  });
});

describe("VAL-TRADE-004: Live trade size constrained to 5-10 USDC", () => {
  it("5 USDC passes", async () => {
    submitLiveOrderMock.mockResolvedValueOnce({
      success: true,
      orderID: "ok",
      status: "live",
    });
    const r = await placePrismOrder({
      agentId: 1,
      traceId: "t",
      marketId: "m",
      tokenId: "tk",
      side: "BUY",
      sizeUsdc: 5,
    });
    expect(r.status).not.toBe("failed");
  });

  it("4.99 USDC rejected", async () => {
    await expect(
      placePrismOrder({
        agentId: 1,
        traceId: "t",
        marketId: "m",
        tokenId: "tk",
        side: "BUY",
        sizeUsdc: 4.99,
      }),
    ).rejects.toThrow(/below minimum/);
    expect(submitLiveOrderMock).not.toHaveBeenCalled();
  });

  it("10 USDC passes", async () => {
    submitLiveOrderMock.mockResolvedValueOnce({
      success: true,
      orderID: "ok",
      status: "live",
    });
    const r = await placePrismOrder({
      agentId: 1,
      traceId: "t",
      marketId: "m",
      tokenId: "tk",
      side: "BUY",
      sizeUsdc: 10,
    });
    expect(r.status).not.toBe("failed");
  });

  it("10.01 USDC rejected (exceeds live cap)", async () => {
    await expect(
      placePrismOrder({
        agentId: 1,
        traceId: "t",
        marketId: "m",
        tokenId: "tk",
        side: "BUY",
        sizeUsdc: 10.01,
      }),
    ).rejects.toThrow(/exceeds live cap/);
    expect(submitLiveOrderMock).not.toHaveBeenCalled();
  });

  it("25 USDC rejected even when within 25% balance cap", async () => {
    await expect(
      placePrismOrder({
        agentId: 1,
        traceId: "t",
        marketId: "m",
        tokenId: "tk",
        side: "BUY",
        sizeUsdc: 25,
      }),
    ).rejects.toThrow(/exceeds/);
  });
});

describe("VAL-TRADE-005: Paper mode still works as fallback", () => {
  it("PRISM_TRADE_MODE=paper returns paper_filled and never calls SDK", async () => {
    process.env.PRISM_TRADE_MODE = "paper";
    const { resetEnv } = await import("../src/env.js");
    resetEnv();
    const receipt = await placePrismOrder({
      agentId: 1,
      traceId: "trace-1",
      marketId: "m",
      side: "BUY",
      sizeUsdc: 10,
    });
    expect(receipt.status).toBe("paper_filled");
    expect(receipt.polymarketTx).toBeNull();
    expect(submitLiveOrderMock).not.toHaveBeenCalled();

    process.env.PRISM_TRADE_MODE = "live";
    resetEnv();
  });
});

describe("VAL-TRADE-006: Geofencing gate enforced for live mode", () => {
  it("Restricted locale (US) → throws geofence_restricted", async () => {
    process.env.LOCALE = "US";
    const { resetEnv } = await import("../src/env.js");
    resetEnv();

    await expect(
      placePrismOrder({
        agentId: 1,
        traceId: "t",
        marketId: "m",
        tokenId: "tk",
        side: "BUY",
        sizeUsdc: 7,
      }),
    ).rejects.toThrow(/geofence_restricted/);
    expect(submitLiveOrderMock).not.toHaveBeenCalled();

    process.env.LOCALE = "EE";
    resetEnv();
  });
});

describe("VAL-TRADE-009: Order submission failure handled gracefully", () => {
  it("SDK throws → returns failed receipt, no crash", async () => {
    submitLiveOrderMock.mockRejectedValueOnce(new Error("rate limited"));
    const receipt = await placePrismOrder({
      agentId: 1,
      traceId: "trace-fail",
      marketId: "m",
      tokenId: "tk",
      side: "BUY",
      sizeUsdc: 7,
    });
    expect(receipt.status).toBe("failed");
    expect(receipt.errorMsg).toMatch(/rate limited/);
    expect(receipt.polymarketTx).toBeNull();
  });

  it("SDK returns error response (success: false) → failed receipt", async () => {
    submitLiveOrderMock.mockResolvedValueOnce({
      success: false,
      orderID: "",
      errorMsg: "insufficient balance",
      status: "rejected",
    });
    const receipt = await placePrismOrder({
      agentId: 1,
      traceId: "trace-rej",
      marketId: "m",
      tokenId: "tk",
      side: "BUY",
      sizeUsdc: 7,
    });
    expect(receipt.status).toBe("failed");
    expect(receipt.errorMsg).toMatch(/insufficient balance/);
  });
});

describe("VAL-TRADE-007: V2 SDK from GitHub-style install", () => {
  it("the package is referenced and importable", async () => {
    const sdk = await import("@polymarket/clob-client-v2");
    expect(sdk.ClobClient).toBeDefined();
    expect(sdk.Side).toBeDefined();
    expect(sdk.OrderType).toBeDefined();
    expect(sdk.Chain).toBeDefined();
  });

  it("package.json references the V2 SDK", async () => {
    const pkg = await import("../package.json", { assert: { type: "json" } });
    expect(pkg.default.dependencies["@polymarket/clob-client-v2"]).toBeDefined();
  });
});
