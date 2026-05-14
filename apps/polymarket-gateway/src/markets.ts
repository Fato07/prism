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
  /** ERC-1155 conditional token ID on Polygon (from the CLOB API `tokens[].token_id`). */
  tokenId: string;
}

interface MarketData {
  conditionId: string;
  question: string;
  outcomes: MarketOutcome[];
  /** Convenience: the "Yes" outcome's ERC-1155 token ID. Null if no Yes token found. */
  yesTokenId: string | null;
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
    const markets: MarketData[] = items.map((m) => {
      const outcomes = parseOutcomes(m);
      return {
        conditionId: String(m.condition_id ?? m.conditionId ?? ""),
        question: String(m.question ?? ""),
        outcomes,
        yesTokenId: extractYesTokenId(outcomes),
        endDate: m.end_date_iso ? String(m.end_date_iso) : null,
        active: Boolean(m.active ?? true),
      };
    });

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

/** Parse outcomes from raw market data, including ERC-1155 token IDs. */
function parseOutcomes(m: Record<string, unknown>): MarketOutcome[] {
  const outcomes: MarketOutcome[] = [];
  const tokens = m.tokens as Array<Record<string, unknown>> | undefined;
  if (Array.isArray(tokens)) {
    for (const token of tokens) {
      outcomes.push({
        outcome: String(token.outcome ?? ""),
        price: Number(token.price ?? 0),
        tokenId: String(token.token_id ?? ""),
      });
    }
  }
  return outcomes;
}

/** Extract the "Yes" outcome token ID from parsed outcomes. */
function extractYesTokenId(outcomes: MarketOutcome[]): string | null {
  const yesOutcome = outcomes.find(
    (o) => o.outcome.toLowerCase() === "yes",
  );
  return yesOutcome?.tokenId ?? null;
}

/** Check whether a string looks like a real 66-char hex condition ID (0x + 64 hex digits). */
export function isConditionId(value: string): boolean {
  return /^0x[0-9a-f]{64}$/i.test(value);
}

/** Resolve a real Polymarket token ID from an internal marketId and optional question text.

Resolution priority:
1. If `marketId` is already a real 66-char hex condition ID, return it as-is
2. If `marketQuestion` is provided, fuzzy-match against cached market data
3. If neither matches, return null (caller should handle gracefully)

Fuzzy matching: checks if any cached market's question contains key terms
from the provided `marketQuestion`. Strips common stop words and matches
on the longest 2-3 significant words.
*/
export async function resolveTokenId(
  marketId: string,
  marketQuestion?: string,
): Promise<string | null> {
  // 1. Already a real condition ID
  if (isConditionId(marketId)) {
    return marketId;
  }

  // 2. Need to look up from market data
  const markets = await fetchMarkets();

  if (marketQuestion) {
    // Fuzzy match: find the market whose question has the highest overlap
    // of significant words with the provided marketQuestion.
    const queryTerms = extractSignificantTerms(marketQuestion);

    let bestMatch: MarketData | null = null;
    let bestScore = 0;

    for (const m of markets) {
      const marketTerms = extractSignificantTerms(m.question);
      // Count how many query terms appear in the market terms
      const overlap = queryTerms.filter((qt) =>
        marketTerms.some((mt) => mt.includes(qt) || qt.includes(mt)),
      ).length;
      if (overlap > bestScore) {
        bestScore = overlap;
        bestMatch = m;
      }
    }

    // Require at least 2 significant term overlaps to avoid false matches
    if (bestMatch && bestScore >= 2 && bestMatch.yesTokenId) {
      logger.info(
        {
          marketId,
          matchedQuestion: bestMatch.question,
          yesTokenId: bestMatch.yesTokenId,
          score: bestScore,
        },
        "Resolved tokenId via fuzzy market question match",
      );
      return bestMatch.yesTokenId;
    }

    logger.warn(
      {
        marketId,
        marketQuestion,
        bestScore,
        bestMatchQuestion: bestMatch?.question ?? null,
      },
      "Could not resolve tokenId via fuzzy match (score too low or no yesTokenId)",
    );
  }

  // 3. Last resort: try matching by internal ID pattern in the question
  //    (e.g. "0xbtc_150k_2026" → look for "Bitcoin" or "BTC" in market questions)
  for (const m of markets) {
    if (m.yesTokenId && internalIdMatchesMarket(marketId, m.question)) {
      logger.info(
        { marketId, matchedQuestion: m.question, yesTokenId: m.yesTokenId },
        "Resolved tokenId via internal ID heuristics",
      );
      return m.yesTokenId;
    }
  }

  return null;
}

/** Strip stop words and return the most significant lowercase terms from a question string. */
function extractSignificantTerms(question: string): string[] {
  const stopWords = new Set([
    "will", "the", "a", "an", "by", "in", "of", "at", "to", "for",
    "before", "after", "end", "is", "are", "be", "it", "or", "and",
    "this", "that", "with", "from", "than", "more", "less", "most",
    "exceed", "top", "does", "do", "can", "has", "have", "been",
  ]);
  return question
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter((w) => w.length >= 3 && !stopWords.has(w));
}

/** Heuristic: check if an internal marketId like "0xbtc_150k_2026" matches
 *  key terms in a Polymarket question (e.g. "Bitcoin" → btc). */
function internalIdMatchesMarket(
  internalId: string,
  question: string,
): boolean {
  const idLower = internalId.toLowerCase();
  const qLower = question.toLowerCase();

  // Map of internal ID fragments to question keywords
  const heuristics: Array<[RegExp, string[]]> = [
    [/btc|bitcoin/, ["bitcoin", "btc"]],
    [/fed|fomc|interest.?rate/, ["fed", "fomc", "interest rate", "federal reserve"]],
    [/eu|ai.?act|regulation/, ["eu", "ai act", "regulation", "enforcement"]],
    [/ai.?agent/, ["ai agent", "agent"]],
    [/open.?source|lmsys|leaderboard/, ["open-source", "open source", "lmsys", "leaderboard"]],
    [/arc|tvl/, ["arc", "tvl"]],
    [/polymarket|volume/, ["polymarket", "volume"]],
    [/usdc|supply/, ["usdc", "supply"]],
  ];

  for (const [idPattern, keywords] of heuristics) {
    if (idPattern.test(idLower)) {
      return keywords.some((kw) => qLower.includes(kw));
    }
  }
  return false;
}

// Re-export MarketData type for use in other modules
export type { MarketData, MarketOutcome };
