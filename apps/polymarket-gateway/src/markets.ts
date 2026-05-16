/** Market data fetching and deterministic token resolution from Polymarket CLOB.

Product rules:
- Default public market surfaces exclude stale markets whose endDate is in the past.
- Recommended markets must be binary Yes/No markets with explicit token IDs.
- Live orders must receive an explicit tokenId; resolution is exposed separately
  so routing is auditable instead of silent fuzzy fallback.
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

interface TokenResolution {
  status: "resolved" | "unresolved";
  tokenId: string | null;
  conditionId: string | null;
  confidence: number;
  source:
    | "clob_tokens"
    | "explicit_token_id"
    | "condition_id_exact"
    | "question_fuzzy"
    | "internal_id_heuristic"
    | "none";
  matchedQuestion?: string;
  reason?: string;
}

interface MarketData {
  conditionId: string;
  question: string;
  outcomes: MarketOutcome[];
  /** Convenience: the "Yes" outcome's ERC-1155 token ID. Null if no Yes token found. */
  yesTokenId: string | null;
  /** Convenience: the "No" outcome's ERC-1155 token ID. Null if no No token found. */
  noTokenId: string | null;
  endDate: string | null;
  active: boolean;
  acceptingOrders: boolean;
  tokenResolution: TokenResolution;
  surfaceReason: string;
  surfaceScore: number;
}

interface MarketFetchOptions {
  limit?: number;
  fresh?: boolean;
  binary?: boolean;
  resolved?: boolean;
}

interface CacheEntry {
  data: MarketData[];
  fetchedAt: number;
}

let cache: CacheEntry | null = null;

const CLOB_API_BASE = "https://clob.polymarket.com";
const GAMMA_API_BASE = "https://gamma-api.polymarket.com";

/** Fetch filtered markets from Polymarket CLOB API (or return cached data).

Defaults are product-safe: future-or-undated, binary Yes/No, token-resolved,
limited to 20. This prevents stale historical markets from becoming the default
surface for users and autonomous runs.
*/
export async function fetchMarkets(
  options: MarketFetchOptions = {},
): Promise<MarketData[]> {
  const all = await fetchAllMarkets();
  return filterAndRankMarkets(all, options);
}

/** Recommended markets are the same filtered set with an explicit product name. */
export async function fetchRecommendedMarkets(limit = 20): Promise<MarketData[]> {
  return fetchMarkets({ limit, fresh: true, binary: true, resolved: true });
}

/** Resolve an auditable live-trade token ID from explicit token, condition ID, or question. */
export async function resolveMarketToken(
  marketIdOrQuery: string,
  marketQuestion?: string,
): Promise<TokenResolution> {
  const raw = marketIdOrQuery.trim();
  if (!raw) {
    return unresolved("empty query", "none");
  }

  if (isTokenId(raw)) {
    return {
      status: "resolved",
      tokenId: raw,
      conditionId: null,
      confidence: 1,
      source: "explicit_token_id",
      reason: "input already looks like a Polymarket ERC-1155 token ID",
    };
  }

  const markets = await fetchMarkets({ limit: 1000, fresh: true, binary: true, resolved: true });

  if (isConditionId(raw)) {
    const exact = markets.find((m) => m.conditionId.toLowerCase() === raw.toLowerCase());
    if (exact?.yesTokenId) {
      return {
        status: "resolved",
        tokenId: exact.yesTokenId,
        conditionId: exact.conditionId,
        confidence: 1,
        source: "condition_id_exact",
        matchedQuestion: exact.question,
        reason: "matched conditionId to CLOB market and selected Yes token",
      };
    }
    return unresolved("conditionId was not found in fresh binary CLOB markets", "condition_id_exact");
  }

  const queryText = marketQuestion?.trim() || raw;
  const fuzzy = resolveByQuestion(markets, queryText);
  if (fuzzy) return fuzzy;

  const heuristic = resolveByInternalId(markets, raw);
  if (heuristic) return heuristic;

  return unresolved("no fresh binary market matched query", "none");
}

/** Backwards-compatible helper: returns only the resolved Yes token ID. */
export async function resolveTokenId(
  marketId: string,
  marketQuestion?: string,
): Promise<string | null> {
  const resolution = await resolveMarketToken(marketId, marketQuestion);
  return resolution.tokenId;
}

/** Invalidate the market data cache. Useful for testing. */
export function invalidateMarketCache(): void {
  cache = null;
}

/** Check whether a string looks like a real 66-char hex condition ID (0x + 64 hex digits). */
export function isConditionId(value: string): boolean {
  return /^0x[0-9a-f]{64}$/i.test(value);
}

/** Check whether a string looks like a Polymarket ERC-1155 token ID. */
export function isTokenId(value: string): boolean {
  return /^\d{20,}$/.test(value);
}

async function fetchAllMarkets(): Promise<MarketData[]> {
  const env = getEnv();
  const ttlMs = env.MARKET_CACHE_TTL_SECONDS * 1000;

  if (cache && Date.now() - cache.fetchedAt < ttlMs) {
    logger.debug("Returning cached market data");
    return cache.data;
  }

  logger.info("Fetching fresh market data from Polymarket CLOB");

  try {
    const gammaMarkets = await fetchGammaMarkets();
    const markets = gammaMarkets.length > 0 ? gammaMarkets : await fetchClobMarkets();

    cache = { data: markets, fetchedAt: Date.now() };
    return markets;
  } catch (err) {
    logger.error({ err }, "Failed to fetch market data");
    return cache?.data ?? [];
  }
}

async function fetchGammaMarkets(): Promise<MarketData[]> {
  const url = `${GAMMA_API_BASE}/markets?active=true&closed=false&archived=false&limit=500&order=volume&ascending=false`;
  const response = await fetch(url);

  if (!response.ok) {
    logger.warn({ status: response.status }, "Polymarket Gamma API returned non-200");
    return [];
  }

  const raw = (await response.json()) as
    | Array<Record<string, unknown>>
    | Record<string, unknown>;
  const items = Array.isArray(raw)
    ? raw
    : (raw.data as Array<Record<string, unknown>> | undefined) ?? [];
  return items.map(normalizeMarket).filter((m) => m.conditionId && m.question);
}

async function fetchClobMarkets(): Promise<MarketData[]> {
  const url = `${CLOB_API_BASE}/markets?limit=1000&active=true`;
  const response = await fetch(url);

  if (!response.ok) {
    logger.warn({ status: response.status }, "Polymarket CLOB API returned non-200");
    return [];
  }

  const raw = (await response.json()) as
    | Array<Record<string, unknown>>
    | Record<string, unknown>;
  const items = Array.isArray(raw)
    ? raw
    : (raw.data as Array<Record<string, unknown>> | undefined) ?? [];
  return items.map(normalizeMarket).filter((m) => m.conditionId && m.question);
}

function normalizeMarket(m: Record<string, unknown>): MarketData {
  const outcomes = parseOutcomes(m);
  const yesTokenId = extractOutcomeTokenId(outcomes, "yes");
  const noTokenId = extractOutcomeTokenId(outcomes, "no");
  const active = Boolean(m.active ?? true) && !Boolean(m.closed ?? false);
  const acceptingOrders = Boolean(m.accepting_orders ?? m.acceptingOrders ?? active);
  const endDate = parseEndDate(m);
  const tokenResolution = buildTokenResolution(m, yesTokenId, noTokenId);
  const surfaceReason = buildSurfaceReason({ active, acceptingOrders, endDate, outcomes, yesTokenId });

  return {
    conditionId: String(m.condition_id ?? m.conditionId ?? ""),
    question: String(m.question ?? ""),
    outcomes,
    yesTokenId,
    noTokenId,
    endDate,
    active,
    acceptingOrders,
    tokenResolution,
    surfaceReason,
    surfaceScore: scoreMarket({ active, acceptingOrders, endDate, outcomes, yesTokenId }),
  };
}

function filterAndRankMarkets(
  markets: MarketData[],
  options: MarketFetchOptions,
): MarketData[] {
  const limit = Math.max(1, Math.min(options.limit ?? 20, 1000));
  const fresh = options.fresh ?? true;
  const binary = options.binary ?? true;
  const resolved = options.resolved ?? true;

  return markets
    .filter((m) => m.active)
    .filter((m) => m.acceptingOrders)
    .filter((m) => (fresh ? isFreshOrUndated(m.endDate) : true))
    .filter((m) => (binary ? isBinaryYesNoMarket(m) : true))
    .filter((m) => (resolved ? m.tokenResolution.status === "resolved" : true))
    .sort((a, b) => b.surfaceScore - a.surfaceScore || compareEndDate(a.endDate, b.endDate))
    .slice(0, limit);
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
        tokenId: String(token.token_id ?? token.tokenId ?? ""),
      });
    }
    return outcomes;
  }

  const gammaOutcomes = parseMaybeJsonArray(m.outcomes);
  const gammaPrices = parseMaybeJsonArray(m.outcomePrices);
  const gammaTokenIds = parseMaybeJsonArray(m.clobTokenIds);
  for (let i = 0; i < gammaOutcomes.length; i += 1) {
    outcomes.push({
      outcome: String(gammaOutcomes[i] ?? ""),
      price: Number(gammaPrices[i] ?? 0),
      tokenId: String(gammaTokenIds[i] ?? ""),
    });
  }
  return outcomes;
}

function parseMaybeJsonArray(value: unknown): unknown[] {
  if (Array.isArray(value)) return value;
  if (typeof value !== "string") return [];
  try {
    const parsed = JSON.parse(value) as unknown;
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function extractOutcomeTokenId(outcomes: MarketOutcome[], outcome: "yes" | "no"): string | null {
  const match = outcomes.find((o) => o.outcome.toLowerCase() === outcome);
  return match?.tokenId || null;
}

function parseEndDate(m: Record<string, unknown>): string | null {
  const raw = m.end_date_iso ?? m.endDateIso ?? m.end_date ?? m.endDate;
  return raw ? String(raw) : null;
}

function buildTokenResolution(
  m: Record<string, unknown>,
  yesTokenId: string | null,
  noTokenId: string | null,
): TokenResolution {
  const conditionId = String(m.condition_id ?? m.conditionId ?? "") || null;
  if (yesTokenId && noTokenId) {
    return {
      status: "resolved",
      tokenId: yesTokenId,
      conditionId,
      confidence: 1,
      source: "clob_tokens",
      reason: "CLOB market exposes Yes/No token IDs",
    };
  }
  return {
    status: "unresolved",
    tokenId: null,
    conditionId,
    confidence: 0,
    source: "none",
    reason: "market does not expose both Yes and No token IDs",
  };
}

function buildSurfaceReason(input: {
  active: boolean;
  acceptingOrders: boolean;
  endDate: string | null;
  outcomes: MarketOutcome[];
  yesTokenId: string | null;
}): string {
  const reasons: string[] = [];
  reasons.push(input.active ? "active" : "inactive");
  reasons.push(input.acceptingOrders ? "accepting orders" : "not accepting orders");
  reasons.push(isFreshOrUndated(input.endDate) ? "fresh or undated" : "ended");
  reasons.push(isBinaryYesNoOutcomeSet(input.outcomes) ? "binary Yes/No" : "not binary Yes/No");
  reasons.push(input.yesTokenId ? "Yes token resolved" : "Yes token missing");
  return reasons.join(" · ");
}

function scoreMarket(input: {
  active: boolean;
  acceptingOrders: boolean;
  endDate: string | null;
  outcomes: MarketOutcome[];
  yesTokenId: string | null;
}): number {
  let score = 0;
  if (input.active) score += 25;
  if (input.acceptingOrders) score += 20;
  if (isFreshOrUndated(input.endDate)) score += 20;
  if (isBinaryYesNoOutcomeSet(input.outcomes)) score += 20;
  if (input.yesTokenId) score += 10;
  if (hasNonTerminalPrices(input.outcomes)) score += 5;
  return score;
}

function isBinaryYesNoMarket(m: MarketData): boolean {
  return isBinaryYesNoOutcomeSet(m.outcomes) && Boolean(m.yesTokenId && m.noTokenId);
}

function isBinaryYesNoOutcomeSet(outcomes: MarketOutcome[]): boolean {
  const labels = new Set(outcomes.map((o) => o.outcome.toLowerCase()));
  return outcomes.length === 2 && labels.has("yes") && labels.has("no");
}

function hasNonTerminalPrices(outcomes: MarketOutcome[]): boolean {
  return outcomes.some((o) => o.price > 0.001 && o.price < 0.999);
}

function isFreshOrUndated(endDate: string | null): boolean {
  if (!endDate) return true;
  const timestamp = Date.parse(endDate);
  if (!Number.isFinite(timestamp)) return true;
  return timestamp > Date.now();
}

function compareEndDate(a: string | null, b: string | null): number {
  const ta = a ? Date.parse(a) : Number.POSITIVE_INFINITY;
  const tb = b ? Date.parse(b) : Number.POSITIVE_INFINITY;
  return ta - tb;
}

function resolveByQuestion(markets: MarketData[], question: string): TokenResolution | null {
  const queryTerms = extractSignificantTerms(question);
  if (queryTerms.length === 0) return null;

  let bestMatch: MarketData | null = null;
  let bestScore = 0;

  for (const m of markets) {
    const marketTerms = extractSignificantTerms(m.question);
    const overlap = queryTerms.filter((qt) =>
      marketTerms.some((mt) => significantTermMatches(qt, mt)),
    ).length;
    if (overlap > bestScore) {
      bestScore = overlap;
      bestMatch = m;
    }
  }

  const confidence = queryTerms.length ? bestScore / queryTerms.length : 0;
  if (bestMatch?.yesTokenId && bestScore >= 2 && confidence >= 0.34) {
    return {
      status: "resolved",
      tokenId: bestMatch.yesTokenId,
      conditionId: bestMatch.conditionId,
      confidence: round2(confidence),
      source: "question_fuzzy",
      matchedQuestion: bestMatch.question,
      reason: "matched significant question terms to a fresh binary CLOB market",
    };
  }
  return null;
}

function resolveByInternalId(markets: MarketData[], internalId: string): TokenResolution | null {
  for (const m of markets) {
    if (m.yesTokenId && internalIdMatchesMarket(internalId, m.question)) {
      return {
        status: "resolved",
        tokenId: m.yesTokenId,
        conditionId: m.conditionId,
        confidence: 0.5,
        source: "internal_id_heuristic",
        matchedQuestion: m.question,
        reason: "matched internal alias keywords to a fresh binary CLOB market",
      };
    }
  }
  return null;
}

function significantTermMatches(queryTerm: string, marketTerm: string): boolean {
  if (/^\d+$/.test(queryTerm) || /^\d+$/.test(marketTerm)) {
    return queryTerm === marketTerm;
  }
  return marketTerm.includes(queryTerm) || queryTerm.includes(marketTerm);
}

function unresolved(reason: string, source: TokenResolution["source"]): TokenResolution {
  return {
    status: "unresolved",
    tokenId: null,
    conditionId: null,
    confidence: 0,
    source,
    reason,
  };
}

/** Strip stop words and return significant lowercase terms from a question string. */
function extractSignificantTerms(question: string): string[] {
  const stopWords = new Set([
    "will",
    "the",
    "a",
    "an",
    "by",
    "in",
    "of",
    "at",
    "to",
    "for",
    "before",
    "after",
    "end",
    "is",
    "are",
    "be",
    "it",
    "or",
    "and",
    "this",
    "that",
    "with",
    "from",
    "than",
    "more",
    "less",
    "most",
    "exceed",
    "top",
    "does",
    "do",
    "can",
    "has",
    "have",
    "been",
  ]);
  return question
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter((w) => w.length >= 3 && !stopWords.has(w));
}

/** Heuristic: check if an internal marketId like "0xbtc_150k_2026" matches keywords. */
function internalIdMatchesMarket(internalId: string, question: string): boolean {
  const idLower = internalId.toLowerCase();
  const qLower = question.toLowerCase();

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

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

export type { MarketData, MarketFetchOptions, MarketOutcome, TokenResolution };
