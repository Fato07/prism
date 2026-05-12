/** Market data fetching from Polymarket CLOB V2 API with TTL cache.

Phase 0: Read-only access to public market data.
Caches responses with 30-60s TTL to avoid hammering the API.
*/

import pino from "pino";

import { getEnv } from "./env.js";

const logger = pino({ name: "prism.markets" });

interface MarketOutcome {
  outcome: string;
  price: number;
}

interface MarketData {
  conditionId: string;
  question: string;
  outcomes: MarketOutcome[];
  endDate: string | null;
  active: boolean;
}

interface CacheEntry {
  data: MarketData[];
  fetchedAt: number;
}

let cache: CacheEntry | null = null;

const CLOB_API_BASE = "https://clob.polymarket.com";

/** Fetch markets from Polymarket CLOB API (or return cached data).

Caches the response for the configured TTL (default 45s).
Two calls within TTL → 1 outbound request.
Call after TTL → fresh fetch.

@returns Array of market data objects
*/
export async function fetchMarkets(): Promise<MarketData[]> {
  const env = getEnv();
  const ttlMs = env.MARKET_CACHE_TTL_SECONDS * 1000;

  if (cache && Date.now() - cache.fetchedAt < ttlMs) {
    logger.debug("Returning cached market data");
    return cache.data;
  }

  logger.info("Fetching fresh market data from Polymarket CLOB");

  try {
    const url = `${CLOB_API_BASE}/markets?limit=20&active=true`;
    const response = await fetch(url);

    if (!response.ok) {
      logger.warn(
        { status: response.status },
        "Polymarket CLOB API returned non-200",
      );
      // Return stale cache if available, otherwise empty
      return cache?.data ?? [];
    }

    const raw = (await response.json()) as
      | Array<Record<string, unknown>>
      | Record<string, unknown>;
    const items = Array.isArray(raw) ? raw : (raw.data as Array<Record<string, unknown>> | undefined) ?? [];
    const markets: MarketData[] = items.map((m) => ({
      conditionId: String(m.condition_id ?? m.conditionId ?? ""),
      question: String(m.question ?? ""),
      outcomes: parseOutcomes(m),
      endDate: m.end_date_iso ? String(m.end_date_iso) : null,
      active: Boolean(m.active ?? true),
    }));

    cache = { data: markets, fetchedAt: Date.now() };
    return markets;
  } catch (err) {
    logger.error({ err }, "Failed to fetch market data");
    return cache?.data ?? [];
  }
}

/** Invalidate the market data cache. Useful for testing. */
export function invalidateMarketCache(): void {
  cache = null;
}

/** Parse outcomes from raw market data. */
function parseOutcomes(m: Record<string, unknown>): MarketOutcome[] {
  const outcomes: MarketOutcome[] = [];
  const tokens = m.tokens as Array<Record<string, unknown>> | undefined;
  if (Array.isArray(tokens)) {
    for (const token of tokens) {
      outcomes.push({
        outcome: String(token.outcome ?? ""),
        price: Number(token.price ?? 0),
      });
    }
  }
  return outcomes;
}
