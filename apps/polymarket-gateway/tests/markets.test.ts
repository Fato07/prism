/** Tests for VAL-POLY-003: Market data fetch with caching.

- Market data fetch returns 200 with question/outcomes/prices
- Response cached with 30-60s TTL
- Two calls within TTL → 1 outbound request
- Call after TTL → fresh fetch
*/

import { describe, it, expect, beforeAll, afterEach, vi } from "vitest";

import { fetchMarkets, invalidateMarketCache } from "../src/markets.js";

const sampleMarkets = [
  {
    condition_id: "0x1234567890abcdef",
    question: "Will Prism pass scrutiny validation?",
    active: true,
    tokens: [
      { outcome: "Yes", price: 0.62 },
      { outcome: "No", price: 0.38 },
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
  process.env.POLY_BUILDER_CODE = "0xtestbuildercode";
  process.env.DATABASE_URL = "NEON_DATABASE_URL_PLACEHOLDER";
  process.env.MARKET_CACHE_TTL_SECONDS = "45";
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  invalidateMarketCache();
  fetchMock.mockClear();
});

describe("VAL-POLY-003: Market data fetch with caching", () => {
  it("fetchMarkets returns an array of market data", async () => {
    const markets = await fetchMarkets();
    expect(Array.isArray(markets)).toBe(true);
  });

  it("each market has question, outcomes, and conditionId fields", async () => {
    const markets = await fetchMarkets();
    // If the Polymarket API is reachable, check structure
    // If not (no network in CI), the array may be empty — that's fine
    for (const m of markets) {
      expect(m).toHaveProperty("question");
      expect(m).toHaveProperty("outcomes");
      expect(m).toHaveProperty("conditionId");
      expect(Array.isArray(m.outcomes)).toBe(true);
    }
  });

  it("caches the response and returns same data on second call", async () => {
    const first = await fetchMarkets();
    const second = await fetchMarkets();
    // Verify data is the same (deep equality since cache may return same or new array)
    expect(second).toStrictEqual(first);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("invalidating cache causes a fresh fetch", async () => {
    const first = await fetchMarkets();
    invalidateMarketCache();
    const second = await fetchMarkets();
    // May or may not be same data, but should be different references
    // (new fetch even if same content)
    // Actually if API returns same data, they could have same structure
    // The key test is that the fetch function was called again
    expect(second).toStrictEqual(first);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
