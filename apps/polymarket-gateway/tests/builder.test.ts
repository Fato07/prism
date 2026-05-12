/** Tests for VAL-POLY-001: Builder code deterministically derived from agentId.

mapAgentIdToBuilderCode(agentId) uses HMAC to derive a builder code.
- Same agentId → same code (deterministic)
- Different agentIds → different codes (no collisions across ≥3 test IDs)
*/

import { describe, it, expect, beforeAll } from "vitest";

import { mapAgentIdToBuilderCode, verifyBuilderCode } from "../src/builder.js";

// Set env vars before importing env module
beforeAll(() => {
  process.env.POLY_BUILDER_CODE = "0xtestbuildercode";
  process.env.DATABASE_URL = "NEON_DATABASE_URL_PLACEHOLDER";
  process.env.BUILDER_HMAC_SECRET = "test-hmac-secret";
});

describe("VAL-POLY-001: mapAgentIdToBuilderCode", () => {
  it("same agentId produces same builder code (deterministic)", () => {
    const code1 = mapAgentIdToBuilderCode(1);
    const code2 = mapAgentIdToBuilderCode(1);
    expect(code1).toBe(code2);
  });

  it("different agentIds produce different codes", () => {
    const code1 = mapAgentIdToBuilderCode(1);
    const code2 = mapAgentIdToBuilderCode(2);
    const code3 = mapAgentIdToBuilderCode(3);
    expect(code1).not.toBe(code2);
    expect(code2).not.toBe(code3);
    expect(code1).not.toBe(code3);
  });

  it("returns a valid hex string starting with 0x", () => {
    const code = mapAgentIdToBuilderCode(42);
    expect(code).toMatch(/^0x[0-9a-f]{64}$/);
  });

  it("works with string agentIds", () => {
    const code = mapAgentIdToBuilderCode("agent-trader-001");
    expect(code).toMatch(/^0x[0-9a-f]{64}$/);
    // Same string → same code
    expect(code).toBe(mapAgentIdToBuilderCode("agent-trader-001"));
  });

  it("string and number of same value produce same code (both converted to string '1')", () => {
    const numCode = mapAgentIdToBuilderCode(1);
    const strCode = mapAgentIdToBuilderCode("1");
    // Both String(1) and String("1") yield "1", so HMAC input is identical
    expect(numCode).toBe(strCode);
  });

  it("verifyBuilderCode correctly validates derived codes", () => {
    const agentId = 5;
    const code = mapAgentIdToBuilderCode(agentId);
    expect(verifyBuilderCode(agentId, code)).toBe(true);
    expect(verifyBuilderCode(agentId, "0xwrong")).toBe(false);
    expect(verifyBuilderCode(999, code)).toBe(false);
  });

  it("no collisions across 100 agentIds", () => {
    const codes = new Set<string>();
    for (let i = 1; i <= 100; i++) {
      const code = mapAgentIdToBuilderCode(i);
      codes.add(code);
    }
    expect(codes.size).toBe(100);
  });
});
