/** Polymarket Gateway — Hono app factory.

Separates app creation from server startup for testability.
*/

import { Hono } from "hono";
import pino from "pino";

import { fetchMarkets } from "./markets.js";
import { placePrismOrder } from "./trade.js";
import type { TradeSide } from "./trade.js";
import { persistTrade } from "./db.js";
import { getEnv } from "./env.js";

const logger = pino({ name: "prism.gateway" });

/** Create and configure the Hono app. */
export function createApp(): Hono {
  const app = new Hono();

  /** GET /health — Health check. */
  app.get("/health", (c) => {
    return c.json({
      status: "ok",
      service: "prism-polymarket-gateway",
      timestamp: new Date().toISOString(),
    });
  });

  /** GET /markets — Fetch cached market data. */
  app.get("/markets", async (c) => {
    try {
      const markets = await fetchMarkets();
      return c.json({ markets, count: markets.length });
    } catch (err) {
      logger.error({ err }, "Failed to fetch markets");
      return c.json({ error: "Failed to fetch market data" }, 500);
    }
  });

  /** POST /trade — Execute a paper trade. */
  app.post("/trade", async (c) => {
    const env = getEnv();

    if (env.PRISM_TRADE_MODE !== "paper") {
      return c.json({ error: "Only paper trading supported in Phase 0" }, 400);
    }

    let body: Record<string, unknown>;
    try {
      body = await c.req.json();
    } catch {
      return c.json({ error: "Invalid JSON body" }, 400);
    }

    // Validate required fields
    const agentId = body.agentId;
    const traceId = body.traceId;
    const marketId = body.marketId;
    const side = body.side as string;
    const sizeUsdc = body.sizeUsdc as number;

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
      const receipt = placePrismOrder({
        agentId: Number(agentId),
        traceId: String(traceId),
        marketId: String(marketId),
        side: side as TradeSide,
        sizeUsdc,
      });

      // Persist to Neon (best-effort, don't fail the response)
      const persisted = await persistTrade(receipt);
      if (!persisted) {
        logger.warn(
          { orderId: receipt.orderId },
          "Trade receipt generated but not persisted to DB",
        );
      }

      return c.json({ receipt, persisted }, 200);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Trade failed";
      const status = message.includes("exceeds") ? 422 : 500;
      return c.json({ error: message }, status);
    }
  });

  return app;
}
