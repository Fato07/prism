/** Tests for @prism/builder-codes: deterministic HMAC builder code derivation.

mapAgentIdToBuilderCode(agentId, secret) uses HMAC-SHA256 to derive a builder code.
- Same agentId + secret → same code (deterministic)
- Different agentIds → different codes (no collisions across ≥3 test IDs)
- Different secrets → different codes for same agentId
*/

import { describe, it, expect } from "vitest";

import {
  mapAgentIdToBuilderCode,
  verifyBuilderCode,
} from "../src/index.js";

const SECRET = "test-hmac-secret";

describe("mapAgentIdToBuilderCode", () => {
  it("same agentId + secret produces same builder code (deterministic)", () => {
    const code1 = mapAgentIdToBuilderCode(1, SECRET);
    const code2 = mapAgentIdToBuilderCode(1, SECRET);
    expect(code1).toBe(code2);
  });

  it("different agentIds produce different codes", () => {
    const code1 = mapAgentIdToBuilderCode(1, SECRET);
    const code2 = mapAgentIdToBuilderCode(2, SECRET);
    const code3 = mapAgentIdToBuilderCode(3, SECRET);
    expect(code1).not.toBe(code2);
    expect(code2).not.toBe(code3);
    expect(code1).not.toBe(code3);
  });

  it("returns a valid hex string starting with 0x", () => {
    const code = mapAgentIdToBuilderCode(42, SECRET);
    expect(code).toMatch(/^0x[0-9a-f]{64}$/);
  });

  it("works with string agentIds", () => {
    const code = mapAgentIdToBuilderCode("agent-trader-001", SECRET);
    expect(code).toMatch(/^0x[0-9a-f]{64}$/);
    // Same string → same code
    expect(code).toBe(mapAgentIdToBuilderCode("agent-trader-001", SECRET));
  });

  it("string and number of same value produce same code (both converted to string '1')", () => {
    const numCode = mapAgentIdToBuilderCode(1, SECRET);
    const strCode = mapAgentIdToBuilderCode("1", SECRET);
    // Both String(1) and String("1") yield "1", so HMAC input is identical
    expect(numCode).toBe(strCode);
  });

  it("different secrets produce different codes for the same agentId", () => {
    const code1 = mapAgentIdToBuilderCode(1, "secret-a");
    const code2 = mapAgentIdToBuilderCode(1, "secret-b");
    expect(code1).not.toBe(code2);
  });

  it("verifyBuilderCode correctly validates derived codes", () => {
    const agentId = 5;
    const code = mapAgentIdToBuilderCode(agentId, SECRET);
    expect(verifyBuilderCode(agentId, code, SECRET)).toBe(true);
    expect(verifyBuilderCode(agentId, "0xwrong", SECRET)).toBe(false);
    expect(verifyBuilderCode(999, code, SECRET)).toBe(false);
  });

  it("verifyBuilderCode rejects code derived with wrong secret", () => {
    const code = mapAgentIdToBuilderCode(1, "secret-a");
    expect(verifyBuilderCode(1, code, "secret-b")).toBe(false);
  });

  it("no collisions across 100 agentIds", () => {
    const codes = new Set<string>();
    for (let i = 1; i <= 100; i++) {
      const code = mapAgentIdToBuilderCode(i, SECRET);
      codes.add(code);
    }
    expect(codes.size).toBe(100);
  });
});
