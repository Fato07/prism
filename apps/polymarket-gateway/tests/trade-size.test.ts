/** Tests for VAL-POLY-005: Trade size enforced at 25% of capped wallet balance.

Rules:
- Max trade size = 25% of wallet balance
- Wallet balance capped at 100 USDC
- So max trade with 100 USDC balance = 25 USDC
- With 40 USDC balance → max 10 USDC
- With 120 USDC balance → max still 25 USDC (cap applies)
- 25 USDC order passes with 100 USDC balance
- 26 USDC order rejected with 100 USDC balance
- 15 USDC rejected with 40 USDC balance
*/

import { describe, it, expect, beforeAll } from "vitest";

import { validateTradeSize, placePrismOrder } from "../src/trade.js";

beforeAll(() => {
  process.env.PRISM_TRADE_MODE = "paper";
  process.env.POLY_BUILDER_CODE = "0xtestbuildercode";
  process.env.DATABASE_URL = "NEON_DATABASE_URL_PLACEHOLDER";
  process.env.BUILDER_HMAC_SECRET = "test-hmac-secret";
  process.env.WALLET_BALANCE_CAP_USDC = "100";
});

describe("VAL-POLY-005: Trade size enforcement", () => {
  describe("validateTradeSize", () => {
    it("25 USDC passes with 100 USDC balance", () => {
      const result = validateTradeSize(25, 100);
      expect(result.allowed).toBe(true);
      expect(result.maxSize).toBe(25);
    });

    it("26 USDC rejected with 100 USDC balance", () => {
      const result = validateTradeSize(26, 100);
      expect(result.allowed).toBe(false);
      expect(result.maxSize).toBe(25);
      expect(result.reason).toContain("exceeds");
    });

    it("15 USDC rejected with 40 USDC balance (25% = 10)", () => {
      const result = validateTradeSize(15, 40);
      expect(result.allowed).toBe(false);
      expect(result.maxSize).toBe(10);
    });

    it("10 USDC passes with 40 USDC balance", () => {
      const result = validateTradeSize(10, 40);
      expect(result.allowed).toBe(true);
      expect(result.maxSize).toBe(10);
    });

    it("120 USDC balance still caps at 25 USDC max (balance > cap)", () => {
      const result = validateTradeSize(25, 120);
      expect(result.allowed).toBe(true);
      // effective balance is min(120, 100) = 100, so 25% = 25
      expect(result.maxSize).toBe(25);
    });

    it("26 USDC rejected even with 120 USDC balance", () => {
      const result = validateTradeSize(26, 120);
      expect(result.allowed).toBe(false);
      expect(result.maxSize).toBe(25);
    });

    it("1 USDC passes with any positive balance", () => {
      const result = validateTradeSize(1, 4);
      expect(result.allowed).toBe(true);
    });

    it("0 USDC rejected (must be positive)", () => {
      const result = validateTradeSize(0, 100);
      expect(result.allowed).toBe(false);
    });

    it("exact 25% of balance passes", () => {
      const result = validateTradeSize(12.5, 50);
      expect(result.allowed).toBe(true);
    });

    it("slightly over 25% of balance fails", () => {
      const result = validateTradeSize(12.51, 50);
      expect(result.allowed).toBe(false);
    });
  });

  describe("placePrismOrder with size enforcement", () => {
    it("25 USDC order succeeds with default (100 USDC) balance", () => {
      const receipt = placePrismOrder({
        agentId: 1,
        traceId: "test-trace-id",
        marketId: "test-market",
        side: "BUY",
        sizeUsdc: 25,
      });
      expect(receipt.status).toBe("paper_filled");
      expect(receipt.size).toBe(25);
    });

    it("26 USDC order throws with default (100 USDC) balance", () => {
      expect(() =>
        placePrismOrder({
          agentId: 1,
          traceId: "test-trace-id",
          marketId: "test-market",
          side: "BUY",
          sizeUsdc: 26,
        }),
      ).toThrow(/exceeds/);
    });

    it("10 USDC order succeeds with 40 USDC balance", () => {
      const receipt = placePrismOrder(
        {
          agentId: 1,
          traceId: "test-trace-id",
          marketId: "test-market",
          side: "BUY",
          sizeUsdc: 10,
        },
        40,
      );
      expect(receipt.status).toBe("paper_filled");
    });

    it("15 USDC order rejected with 40 USDC balance", () => {
      expect(() =>
        placePrismOrder(
          {
            agentId: 1,
            traceId: "test-trace-id",
            marketId: "test-market",
            side: "BUY",
            sizeUsdc: 15,
          },
          40,
        ),
      ).toThrow(/exceeds/);
    });
  });
});
