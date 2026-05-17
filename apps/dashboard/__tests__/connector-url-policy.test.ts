import { describe, expect, it } from "vitest";

import { isSafeConnectorUrl, redactConnectorUrl } from "@/lib/connector-url-policy";

describe("connector URL policy", () => {
  it("allows HTTPS public connector URLs", () => {
    expect(isSafeConnectorUrl("https://mcp.example.com/mcp/")).toBe(true);
  });

  it("blocks local and private-network URLs by default", () => {
    expect(isSafeConnectorUrl("http://127.0.0.1:8000/mcp/")).toBe(false);
    expect(isSafeConnectorUrl("https://10.0.0.5/mcp/")).toBe(false);
    expect(isSafeConnectorUrl("https://metadata.internal/mcp/")).toBe(false);
  });

  it("does not expose connector hostnames in redacted passports", () => {
    expect(redactConnectorUrl("https://private-mcp.example.com/mcp/")).toBe("https://configured-host");
  });
});
