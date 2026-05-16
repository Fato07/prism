/** Polymarket Gateway — Hono app factory.

Separates app creation from server startup for testability.
*/

import { Hono } from "hono";
import pino from "pino";

import { persistTrade } from "./db.js";
import { getEnv } from "./env.js";
import { checkGeofence } from "./geofence.js";
import { fetchMarkets, fetchRecommendedMarkets, resolveMarketToken } from "./markets.js";
import { placePrismOrder } from "./trade.js";
import type { TradeSide } from "./trade.js";

const logger = pino({ name: "prism.gateway" });

export function createApp(): Hono {
  const app = new Hono();

  app.get("/health", (c) => {
    const env = getEnv();
    return c.json({
      status: "ok",
      service: "prism-polymarket-gateway",
      mode: env.PRISM_TRADE_MODE,
      timestamp: new Date().toISOString(),
    });
  });

  app.get("/markets", async (c) => {
    try {
      const limit = parseLimit(c.req.query("limit"));
      const markets = await fetchMarkets({
        limit,
        fresh: parseBooleanQuery(c.req.query("fresh"), true),
        binary: parseBooleanQuery(c.req.query("binary"), true),
        resolved: parseBooleanQuery(c.req.query("resolved"), true),
      });
      return c.json({ markets, count: markets.length, filters: { limit } });
    } catch (err) {
      logger.error({ err }, "Failed to fetch markets");
      return c.json({ error: "Failed to fetch market data" }, 500);
    }
  });

  app.get("/markets/recommended", async (c) => {
    try {
      const limit = parseLimit(c.req.query("limit"));
      const markets = await fetchRecommendedMarkets(limit);
      return c.json({ markets, count: markets.length, filters: { limit } });
    } catch (err) {
      logger.error({ err }, "Failed to fetch recommended markets");
      return c.json({ error: "Failed to fetch recommended market data" }, 500);
    }
  });

  app.get("/markets/resolve", async (c) => {
    const query = c.req.query("query") ?? c.req.query("q") ?? "";
    const marketQuestion = c.req.query("marketQuestion") ?? c.req.query("question");
    if (!query.trim()) {
      return c.json({ error: "Missing required query parameter: query" }, 422);
    }

    try {
      const resolution = await resolveMarketToken(query, marketQuestion);
      return c.json({ query, marketQuestion: marketQuestion ?? null, resolution });
    } catch (err) {
      logger.error({ err, query }, "Failed to resolve market token");
      return c.json({ error: "Failed to resolve market token" }, 500);
    }
  });

  app.post("/trade", async (c) => {
    const env = getEnv();

    if (env.PRISM_TRADE_MODE === "live") {
      const geo = checkGeofence(env.LOCALE);
      if (!geo.allowed) {
        return c.json(
          { error: geo.reason ?? "geofence_restricted", locale: geo.locale },
          403,
        );
      }
    }

    let body: Record<string, unknown>;
    try {
      body = await c.req.json();
    } catch {
      return c.json({ error: "Invalid JSON body" }, 400);
    }

    const agentId = body.agentId;
    const traceId = body.traceId;
    const marketId = body.marketId;
    const side = body.side as string;
    const sizeUsdc = body.sizeUsdc as number;
    const tokenId = body.tokenId as string | undefined;
    const priceLimit = body.priceLimit as number | undefined;
    const marketQuestion = body.marketQuestion as string | undefined;

    if (!agentId || !traceId || !marketId || !side || sizeUsdc === undefined) {
      return c.json(
        {
          error:
            "Missing required fields: agentId, traceId, marketId, side, sizeUsdc",
        },
        422,
      );
    }

    if (side !== "BUY" && side !== "SELL") {
      return c.json({ error: "side must be BUY or SELL" }, 422);
    }

    if (typeof sizeUsdc !== "number" || sizeUsdc <= 0) {
      return c.json({ error: "sizeUsdc must be a positive number" }, 422);
    }

    try {
      if (env.PRISM_TRADE_MODE === "live" && !tokenId) {
        const resolution = await resolveMarketToken(
          String(marketId),
          marketQuestion ? String(marketQuestion) : undefined,
        );
        return c.json(
          {
            error:
              "tokenId is required for live trades. Call GET /markets/resolve first, " +
              "then resubmit with the explicit tokenId.",
            resolution,
          },
          422,
        );
      }

      const receipt = await placePrismOrder({
        agentId: Number(agentId),
        traceId: String(traceId),
        marketId: String(marketId),
        side: side as TradeSide,
        sizeUsdc,
        tokenId: tokenId ?? undefined,
        priceLimit,
      });

      const persisted = await persistTrade(receipt);
      if (!persisted) {
        logger.warn(
          { orderId: receipt.orderId },
          "Trade receipt generated but not persisted to DB",
        );
      }

      const httpStatus = receipt.status === "failed" ? 502 : 200;
      return c.json({ receipt, persisted }, httpStatus);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Trade failed";
      let status: 422 | 403 | 500 = 500;
      if (message.includes("exceeds") || message.includes("below")) status = 422;
      else if (message.includes("geofence")) status = 403;
      return c.json({ error: message }, status);
    }
  });

  return app;
}

function parseLimit(raw: string | undefined): number {
  const parsed = Number(raw ?? 20);
  if (!Number.isFinite(parsed)) return 20;
  return Math.max(1, Math.min(Math.floor(parsed), 100));
}

function parseBooleanQuery(raw: string | undefined, defaultValue: boolean): boolean {
  if (raw === undefined) return defaultValue;
  const normalised = raw.trim().toLowerCase();
  if (["1", "true", "yes"].includes(normalised)) return true;
  if (["0", "false", "no"].includes(normalised)) return false;
  return defaultValue;
}
