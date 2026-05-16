/** Tests for VAL-POLY-003: Market data fetch with caching.

- Market data fetch returns 200 with question/outcomes/prices
- Response cached with 30-60s TTL
- Two calls within TTL → 1 outbound request
- Call after TTL → fresh fetch
- tokenId and yesTokenId are extracted from the raw API tokens array
- resolveTokenId resolves internal market IDs via fuzzy matching
*/

import { describe, it, expect, beforeAll, afterEach, vi } from "vitest";

import {
  fetchMarkets,
  invalidateMarketCache,
  fetchRecommendedMarkets,
  resolveMarketToken,
  resolveTokenId,
  isConditionId,
  isTokenId,
} from "../src/markets.js";

const sampleMarkets = [
  {
    condition_id: "0x1111111111111111111111111111111111111111111111111111111111111111",
    question: "Will Prism pass scrutiny validation?",
    active: true,
    end_date_iso: "2099-12-31T00:00:00Z",
    tokens: [
      { outcome: "Yes", price: 0.62, token_id: "21724971184084130220463928751225911389088428869686229328700041198682962586890" },
      { outcome: "No", price: 0.38, token_id: "48331043329952076881274542254071239369484953430501484932375043687602679054079" },
    ],
  },
  {
    condition_id: "0x2222222222222222222222222222222222222222222222222222222222222222",
    question: "Will Bitcoin exceed $150,000 before the end of 2026?",
    active: true,
    end_date_iso: "2099-12-31T00:00:00Z",
    tokens: [
      { outcome: "Yes", price: 0.45, token_id: "71321045978252263464351242973717930750633671251979332203087170846869688064221" },
      { outcome: "No", price: 0.55, token_id: "29132820984415231366458791876233988279296549034696091698989893586871598072999" },
    ],
  },
  {
    condition_id: "0x3333333333333333333333333333333333333333333333333333333333333333",
    question: "Will a stale 2023 market be filtered out?",
    active: true,
    end_date_iso: "2023-03-15T00:00:00Z",
    tokens: [
      { outcome: "Yes", price: 1, token_id: "11111111111111111111111111111111111111111111111111111111111111111111" },
      { outcome: "No", price: 0, token_id: "22222222222222222222222222222222222222222222222222222222222222222222" },
    ],
  },
  {
    condition_id: "0x4444444444444444444444444444444444444444444444444444444444444444",
    question: "NCAAB: Team A vs Team B 2026-03-15",
    active: true,
    end_date_iso: "2099-12-31T00:00:00Z",
    tokens: [
      { outcome: "Team A", price: 0.5, token_id: "33333333333333333333333333333333333333333333333333333333333333333333" },
      { outcome: "Team B", price: 0.5, token_id: "44444444444444444444444444444444444444444444444444444444444444444444" },
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
    expect(second).toStrictEqual(first);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("invalidating cache causes a fresh fetch", async () => {
    const first = await fetchMarkets();
    invalidateMarketCache();
    const second = await fetchMarkets();
    expect(second).toStrictEqual(first);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe("Market token ID extraction", () => {
  it("each outcome has a tokenId field", async () => {
    const markets = await fetchMarkets();
    for (const m of markets) {
      for (const o of m.outcomes) {
        expect(o).toHaveProperty("tokenId");
        expect(typeof o.tokenId).toBe("string");
        expect(o.tokenId.length).toBeGreaterThan(0);
      }
    }
  });

  it("yesTokenId is extracted from the Yes outcome", async () => {
    const markets = await fetchMarkets();
    expect(markets[0].yesTokenId).toBe(
      "21724971184084130220463928751225911389088428869686229328700041198682962586890",
    );
    expect(markets[1].yesTokenId).toBe(
      "71321045978252263464351242973717930750633671251979332203087170846869688064221",
    );
  });

  it("recommended markets exclude stale and non-Yes/No markets", async () => {
    const markets = await fetchRecommendedMarkets(20);
    expect(markets.map((m) => m.question)).not.toContain(
      "Will a stale 2023 market be filtered out?",
    );
    expect(markets.map((m) => m.question)).not.toContain("NCAAB: Team A vs Team B 2026-03-15");
    expect(markets).toHaveLength(2);
    for (const market of markets) {
      expect(market.tokenResolution.status).toBe("resolved");
      expect(market.surfaceReason).toContain("binary Yes/No");
    }
  });
});

describe("ID classifiers", () => {
  it("isConditionId returns true for 66-char hex strings", () => {
    expect(
      isConditionId("0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"),
    ).toBe(true);
  });

  it("isConditionId returns false for internal IDs", () => {
    expect(isConditionId("0xbtc_150k_2026")).toBe(false);
  });

  it("isConditionId returns false for short hex strings", () => {
    expect(isConditionId("0x1234")).toBe(false);
  });

  it("isConditionId returns false for non-hex strings", () => {
    expect(isConditionId("not-a-hex-id")).toBe(false);
  });

  it("isTokenId returns true for decimal ERC-1155 token IDs", () => {
    expect(
      isTokenId("71321045978252263464351242973717930750633671251979332203087170846869688064221"),
    ).toBe(true);
  });
});

describe("resolveTokenId", () => {
  it("resolves a condition ID to the market's Yes token ID, not the condition ID", async () => {
    const conditionId =
      "0x2222222222222222222222222222222222222222222222222222222222222222";
    const result = await resolveTokenId(conditionId);
    expect(result).toBe(
      "71321045978252263464351242973717930750633671251979332203087170846869688064221",
    );
    expect(result).not.toBe(conditionId);
  });

  it("resolves via fuzzy question match when marketQuestion is provided", async () => {
    const result = await resolveTokenId(
      "0xbtc_150k_2026",
      "Will Bitcoin exceed $150,000 before the end of 2026?",
    );
    expect(result).toBe(
      "71321045978252263464351242973717930750633671251979332203087170846869688064221",
    );
  });

  it("resolves via internal ID heuristics when no marketQuestion", async () => {
    const result = await resolveTokenId("0xbtc_150k_2026");
    expect(result).toBe(
      "71321045978252263464351242973717930750633671251979332203087170846869688064221",
    );
  });

  it("returns null when no match found", async () => {
    const result = await resolveTokenId(
      "0xnonexistent_market_id",
      "Will something that does not exist happen?",
    );
    expect(result).toBeNull();
  });

  it("resolveMarketToken exposes confidence and source", async () => {
    const resolution = await resolveMarketToken(
      "0xbtc_150k_2026",
      "Will Bitcoin exceed $150,000 before the end of 2026?",
    );
    expect(resolution.status).toBe("resolved");
    expect(resolution.source).toBe("question_fuzzy");
    expect(resolution.confidence).toBeGreaterThan(0);
    expect(resolution.matchedQuestion).toContain("Bitcoin");
  });
});
