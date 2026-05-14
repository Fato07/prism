/** Tests for live trade token ID resolution via the /trade route.

When PRISM_TRADE_MODE=live and tokenId is not provided in the request:
- If marketId is a 66-char hex condition ID, it's used as-is
- If marketQuestion is provided, fuzzy-matched against cached market data
- If no match, returns 422 with an explanatory error
- Paper mode is unaffected (no resolution needed)
*/

import { beforeAll, beforeEach, afterEach, describe, expect, it, vi } from "vitest";

// Mock @neondatabase/serverless before any imports that use it
vi.mock("@neondatabase/serverless", () => ({
  neon: vi.fn(() => vi.fn().mockResolvedValue([])),
}));

const submitLiveOrderMock = vi.fn();

vi.mock("../src/clob.js", () => ({
  submitLiveOrder: submitLiveOrderMock,
  fetchBuilderTrades: vi.fn(),
  getClobClient: vi.fn(),
  resetClobClient: vi.fn(),
}));

const sampleMarkets = [
  {
    condition_id: "0xaaa1112223334445556667778889990001112223334445556667778889990001",
    question: "Will Bitcoin exceed $150,000 before the end of 2026?",
    active: true,
    tokens: [
      { outcome: "Yes", price: 0.45, token_id: "71321045978252263464351242973717930750633671251979332203087170846869688064221" },
      { outcome: "No", price: 0.55, token_id: "29132820984415231366458791876233988279296549034696091698989893586871598072999" },
    ],
  },
  {
    condition_id: "0xbbb2223334445556667778889990001112223334445556667778889990001112",
    question: "Will the Federal Reserve cut interest rates at the June 2026 FOMC meeting?",
    active: true,
    tokens: [
      { outcome: "Yes", price: 0.3, token_id: "12345678901234567890123456789012345678901234567890123456789012345678901234567" },
      { outcome: "No", price: 0.7, token_id: "98765432109876543210987654321098765432109876543210987654321098765432109876543" },
    ],
  },
];

const fetchMock = vi.fn(async () =>
  new Response(JSON.stringify(sampleMarkets), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  }),
);

beforeAll(() => {
  vi.stubGlobal("fetch", fetchMock);
});

beforeEach(async () => {
  submitLiveOrderMock.mockReset();
  const { resetEnv } = await import("../src/env.js");
  resetEnv();
  const { invalidateMarketCache } = await import("../src/markets.js");
  invalidateMarketCache();
  fetchMock.mockClear();
});

afterEach(async () => {
  const { invalidateMarketCache } = await import("../src/markets.js");
  invalidateMarketCache();
});

describe("Live trade token ID resolution via /trade", () => {
  async function setupLiveApp() {
    process.env.PRISM_TRADE_MODE = "live";
    process.env.POLY_BUILDER_CODE = "0xtestbuildercode";
    process.env.DATABASE_URL = "NEON_DATABASE_URL_PLACEHOLDER";
    process.env.BUILDER_HMAC_SECRET = "test-hmac-secret";
    process.env.WALLET_BALANCE_CAP_USDC = "100";
    process.env.LOCALE = "EE";
    process.env.LIVE_TRADE_MIN_USDC = "5";
    process.env.LIVE_TRADE_MAX_USDC = "25";
    const { resetEnv } = await import("../src/env.js");
    resetEnv();
    const { createApp } = await import("../src/app.js");
    return createApp();
  }

  it("resolves tokenId via fuzzy match when marketQuestion is provided", async () => {
    const app = await setupLiveApp();

    submitLiveOrderMock.mockResolvedValueOnce({
      success: true,
      orderID: "ord-resolved-token",
      status: "live",
    });

    const res = await app.request("/trade", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        agentId: 1,
        traceId: "trace-token-resolve",
        marketId: "0xbtc_150k_2026",
        marketQuestion: "Will Bitcoin exceed $150,000 before the end of 2026?",
        side: "BUY",
        sizeUsdc: 7,
      }),
    });

    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.receipt.status).not.toBe("failed");

    // Verify the SDK was called with the resolved token ID (not the internal ID)
    expect(submitLiveOrderMock).toHaveBeenCalledOnce();
    const callArgs = submitLiveOrderMock.mock.calls[0][0];
    expect(callArgs.tokenId).toBe(
      "71321045978252263464351242973717930750633671251979332203087170846869688064221",
    );
    expect(callArgs.tokenId).not.toBe("0xbtc_150k_2026");
  });

  it("uses provided tokenId as-is when explicitly given", async () => {
    const app = await setupLiveApp();

    submitLiveOrderMock.mockResolvedValueOnce({
      success: true,
      orderID: "ord-explicit-token",
      status: "live",
    });

    const explicitTokenId =
      "5554443332221110009998887776665554443332221110009998887776665554444";
    const res = await app.request("/trade", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        agentId: 1,
        traceId: "trace-explicit-token",
        marketId: "0xbtc_150k_2026",
        tokenId: explicitTokenId,
        side: "BUY",
        sizeUsdc: 7,
      }),
    });

    expect(res.status).toBe(200);
    expect(submitLiveOrderMock).toHaveBeenCalledOnce();
    const callArgs = submitLiveOrderMock.mock.calls[0][0];
    expect(callArgs.tokenId).toBe(explicitTokenId);
  });

  it("returns 422 when tokenId cannot be resolved and none is provided", async () => {
    const app = await setupLiveApp();

    const res = await app.request("/trade", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        agentId: 1,
        traceId: "trace-no-resolve",
        marketId: "0xcompletely_unknown_market",
        marketQuestion: "Will something totally unrelated happen?",
        side: "BUY",
        sizeUsdc: 7,
      }),
    });

    expect(res.status).toBe(422);
    const body = await res.json();
    expect(body.error).toContain("Cannot resolve Polymarket token ID");
  });

  it("paper mode does not require tokenId resolution", async () => {
    process.env.PRISM_TRADE_MODE = "paper";
    process.env.POLY_BUILDER_CODE = "0xtestbuildercode";
    process.env.DATABASE_URL = "NEON_DATABASE_URL_PLACEHOLDER";
    process.env.BUILDER_HMAC_SECRET = "test-hmac-secret";
    process.env.WALLET_BALANCE_CAP_USDC = "100";
    const { resetEnv } = await import("../src/env.js");
    resetEnv();
    const { createApp } = await import("../src/app.js");
    const app = createApp();

    const res = await app.request("/trade", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        agentId: 1,
        traceId: "trace-paper-no-token",
        marketId: "0xbtc_150k_2026",
        side: "BUY",
        sizeUsdc: 10,
      }),
    });

    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.receipt.status).toBe("paper_filled");
    expect(submitLiveOrderMock).not.toHaveBeenCalled();
  });
});
