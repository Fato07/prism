/** Tests for the Hono API routes (health, markets, trade).

Integration-level tests using Hono's test utilities.
*/

import { describe, it, expect, beforeAll, vi } from "vitest";

// Mock @neondatabase/serverless before any imports that use it
vi.mock("@neondatabase/serverless", () => ({
  neon: vi.fn(() => vi.fn().mockResolvedValue([])),
}));

beforeAll(() => {
  process.env.PRISM_TRADE_MODE = "paper";
  process.env.POLY_BUILDER_CODE = "0xtestbuildercode";
  process.env.DATABASE_URL = "NEON_DATABASE_URL_PLACEHOLDER";
  process.env.BUILDER_HMAC_SECRET = "test-hmac-secret";
  process.env.WALLET_BALANCE_CAP_USDC = "100";
  process.env.PORT = "3203";
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      new Response(
        JSON.stringify([
          {
            condition_id: "0x1234567890abcdef",
            question: "Will Prism pass scrutiny validation?",
            active: true,
            end_date_iso: "2099-12-31T00:00:00Z",
            tokens: [
              { outcome: "Yes", price: 0.62, token_id: "1112223334445556667778889990001112223334445556667778889990001111" },
              { outcome: "No", price: 0.38, token_id: "9998887776665554443332221110009998887776665554443332221110009999" },
            ],
          },
        ]),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    ),
  );
});

import { Hono } from "hono";
import { createApp } from "../src/app.js";

describe("API Routes", () => {
  let app: Hono;

  beforeAll(() => {
    app = createApp();
  });

  describe("GET /health", () => {
    it("returns 200 with status ok", async () => {
      const res = await app.request("/health");
      expect(res.status).toBe(200);
      const body = await res.json();
      expect(body.status).toBe("ok");
      expect(body.service).toBe("prism-polymarket-gateway");
      expect(body).toHaveProperty("timestamp");
    });
  });

  describe("GET /markets", () => {
    it("returns 200 with markets array", async () => {
      const res = await app.request("/markets");
      expect(res.status).toBe(200);
      const body = await res.json();
      expect(body).toHaveProperty("markets");
      expect(body).toHaveProperty("count");
      expect(Array.isArray(body.markets)).toBe(true);
      expect(body.markets[0].tokenResolution.status).toBe("resolved");
    });

    it("GET /markets/recommended returns surfaced markets", async () => {
      const res = await app.request("/markets/recommended?limit=1");
      expect(res.status).toBe(200);
      const body = await res.json();
      expect(body.count).toBe(1);
      expect(body.markets[0].surfaceReason).toContain("binary Yes/No");
    });

    it("GET /markets/resolve resolves a query without placing a trade", async () => {
      const res = await app.request(
        "/markets/resolve?query=Will%20Prism%20pass%20scrutiny%20validation%3F",
      );
      expect(res.status).toBe(200);
      const body = await res.json();
      expect(body.resolution.status).toBe("resolved");
      expect(body.resolution.source).toBe("question_fuzzy");
    });
  });

  describe("POST /trade", () => {
    it("returns 200 with paper receipt for valid params", async () => {
      const res = await app.request("/trade", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agentId: 1,
          traceId: "550e8400-e29b-41d4-a716-446655440000",
          marketId: "0x1234567890abcdef",
          side: "BUY",
          sizeUsdc: 10,
        }),
      });
      expect(res.status).toBe(200);
      const body = await res.json();
      expect(body.receipt).toHaveProperty("orderId");
      expect(body.receipt.status).toBe("paper_filled");
      expect(body.receipt.builderCode).toMatch(/^0x[0-9a-f]{64}$/);
    });

    it("returns 422 for missing required fields", async () => {
      const res = await app.request("/trade", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agentId: 1 }),
      });
      expect(res.status).toBe(422);
    });

    it("returns 422 for invalid side", async () => {
      const res = await app.request("/trade", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agentId: 1,
          traceId: "test",
          marketId: "test",
          side: "HOLD",
          sizeUsdc: 10,
        }),
      });
      expect(res.status).toBe(422);
    });

    it("returns 422 for oversized trade", async () => {
      const res = await app.request("/trade", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agentId: 1,
          traceId: "test",
          marketId: "test",
          side: "BUY",
          sizeUsdc: 26, // Exceeds 25% of 100 USDC cap
        }),
      });
      expect(res.status).toBe(422);
      const body = await res.json();
      expect(body.error).toContain("exceeds");
    });

    it("returns 400 for invalid JSON body", async () => {
      const res = await app.request("/trade", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "not-json",
      });
      expect(res.status).toBe(400);
    });
  });
});
