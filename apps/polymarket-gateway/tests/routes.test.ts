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
            tokens: [
              { outcome: "Yes", price: 0.62 },
              { outcome: "No", price: 0.38 },
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
