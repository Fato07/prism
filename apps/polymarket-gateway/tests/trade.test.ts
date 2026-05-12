/** Tests for VAL-POLY-002: Paper trade returns simulated fill with builder code.

When PRISM_TRADE_MODE=paper:
- placePrismOrder does NOT send HTTP to Polymarket CLOB
- Returns simulated receipt with: orderId, traceId, marketId, side, size, builderCode, status:'paper_filled'
- builderCode matches mapAgentIdToBuilderCode(agentId)
- Works without POLYMARKET_API_KEY
*/

import { describe, it, expect, beforeAll } from "vitest";

import { mapAgentIdToBuilderCode } from "../src/builder.js";
import { placePrismOrder, validateTradeSize } from "../src/trade.js";
import type { PrismOrderParams } from "../src/trade.js";

beforeAll(() => {
  process.env.PRISM_TRADE_MODE = "paper";
  process.env.POLY_BUILDER_CODE = "0xtestbuildercode";
  process.env.DATABASE_URL = "NEON_DATABASE_URL_PLACEHOLDER";
  process.env.BUILDER_HMAC_SECRET = "test-hmac-secret";
  process.env.WALLET_BALANCE_CAP_USDC = "100";
});

describe("VAL-POLY-002: Paper trade returns simulated receipt", () => {
  const validParams: PrismOrderParams = {
    agentId: 1,
    traceId: "550e8400-e29b-41d4-a716-446655440000",
    marketId: "0x1234567890abcdef",
    side: "BUY",
    sizeUsdc: 10,
  };

  it("returns a receipt with all required fields", async () => {
    const receipt = await placePrismOrder(validParams);

    expect(receipt).toHaveProperty("orderId");
    expect(receipt).toHaveProperty("traceId", validParams.traceId);
    expect(receipt).toHaveProperty("marketId", validParams.marketId);
    expect(receipt).toHaveProperty("side", validParams.side);
    expect(receipt).toHaveProperty("size", validParams.sizeUsdc);
    expect(receipt).toHaveProperty("builderCode");
    expect(receipt).toHaveProperty("status", "paper_filled");
    expect(receipt).toHaveProperty("timestamp");
  });

  it("orderId is a valid UUID", async () => {
    const receipt = await placePrismOrder(validParams);
    const uuidRegex =
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
    expect(receipt.orderId).toMatch(uuidRegex);
  });

  it("builderCode matches HMAC derivation from agentId", async () => {
    const receipt = await placePrismOrder(validParams);
    const expectedCode = mapAgentIdToBuilderCode(validParams.agentId);
    expect(receipt.builderCode).toBe(expectedCode);
  });

  it("timestamp is a valid ISO 8601 string", async () => {
    const receipt = await placePrismOrder(validParams);
    expect(new Date(receipt.timestamp).toISOString()).toBe(receipt.timestamp);
  });

  it("two trades produce different orderIds", async () => {
    const receipt1 = await placePrismOrder(validParams);
    const receipt2 = await placePrismOrder(validParams);
    expect(receipt1.orderId).not.toBe(receipt2.orderId);
  });

  it("works without POLYMARKET_API_KEY (no live credentials needed)", async () => {
    delete process.env.POLYMARKET_API_KEY;
    const receipt = await placePrismOrder(validParams);
    expect(receipt.status).toBe("paper_filled");
  });

  it("SELL side works correctly", async () => {
    const sellParams: PrismOrderParams = {
      ...validParams,
      side: "SELL",
    };
    const receipt = await placePrismOrder(sellParams);
    expect(receipt.side).toBe("SELL");
    expect(receipt.status).toBe("paper_filled");
  });

  it("polymarketTx is null for paper receipts", async () => {
    const receipt = await placePrismOrder(validParams);
    expect(receipt.polymarketTx).toBeNull();
  });
});
