import { describe, expect, it, vi } from "vitest";

import {
  buildSmokeToolArguments,
  countEvidenceItems,
  extractMcpResultBody,
  runMcpConnectorSmoke,
} from "@/lib/connector-smoke";
import type { ToolConnectorRow } from "@/lib/schemas";

const baseConnector = {
  id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  owner_scope: "workspace",
  connector_kind: "evidence",
  name: "Demo MCP evidence",
  transport: "mcp_http",
  provider: "mcp",
  server_url: "https://mcp.example.com",
  tool_name: "search",
  input_mapper: "query_limit",
  result_mapper: "generic_search",
  allowed_tools: ["search"],
  timeout_seconds: "20.000",
  max_results: 5,
  max_usdc: "0.050000",
  auth_secret_ciphertext: "v1:not-a-real-token",
  auth_secret_hint: "…1234",
  smoke_status: "not_run",
  smoke_receipt: null,
  armed: false,
  fail_closed: true,
  created_at: "2026-05-17T00:00:00Z",
  updated_at: "2026-05-17T00:00:00Z",
} satisfies ToolConnectorRow;

function jsonResponse(payload: unknown, ok = true, headers = new Headers({ "content-type": "application/json" })): Response {
  return {
    ok,
    headers,
    json: async () => payload,
    text: async () => `data: ${JSON.stringify(payload)}\n\n`,
  } as Response;
}

describe("connector smoke helpers", () => {
  it("builds smoke arguments for strict query/limit MCP tools", () => {
    expect(buildSmokeToolArguments(baseConnector)).toMatchObject({
      query: expect.stringContaining("Prism connector smoke test"),
      limit: 5,
    });
  });

  it("extracts MCP structuredContent and counts evidence results", () => {
    const body = extractMcpResultBody({ structuredContent: { results: [{ title: "A" }] } });
    expect(countEvidenceItems(body)).toBe(1);
  });

  it("passes when tools/list includes the tool and tools/call returns mapped results", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(
          { jsonrpc: "2.0", id: "init", result: {} },
          true,
          new Headers({ "content-type": "application/json", "mcp-session-id": "session-1" })
        )
      )
      .mockResolvedValueOnce(jsonResponse({ jsonrpc: "2.0", id: "initialized", result: {} }))
      .mockResolvedValueOnce(
        jsonResponse({
          jsonrpc: "2.0",
          id: "list",
          result: { tools: [{ name: "search", inputSchema: { type: "object" } }] },
        })
      )
      .mockResolvedValueOnce(
        jsonResponse({
          jsonrpc: "2.0",
          id: "call",
          result: { structuredContent: { results: [{ title: "Smoke", url: "https://example.com" }] } },
        })
      );

    const receipt = await runMcpConnectorSmoke({ row: baseConnector, bearerToken: "token", fetchImpl });

    expect(receipt.status).toBe("passed");
    expect(receipt.evidence_count).toBe(1);
    expect(fetchImpl).toHaveBeenCalledWith(
      "https://mcp.example.com",
      expect.objectContaining({
        headers: expect.objectContaining({ authorization: "Bearer token" }),
      })
    );
    expect(fetchImpl).toHaveBeenCalledWith(
      "https://mcp.example.com",
      expect.objectContaining({
        headers: expect.objectContaining({ "mcp-session-id": "session-1" }),
      })
    );
    expect(JSON.stringify(receipt)).not.toContain("token");
  });

  it("fails closed when MCP output cannot be mapped to evidence", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ jsonrpc: "2.0", id: "init", result: {} }))
      .mockResolvedValueOnce(
        jsonResponse({ jsonrpc: "2.0", id: "list", result: { tools: [{ name: "search" }] } })
      )
      .mockResolvedValueOnce(
        jsonResponse({ jsonrpc: "2.0", id: "call", result: { structuredContent: { unexpected: true } } })
      );

    const receipt = await runMcpConnectorSmoke({ row: baseConnector, fetchImpl });

    expect(receipt.status).toBe("failed");
    expect(receipt.error_code).toBe("mapper_no_results");
    expect(receipt.fail_closed_ok).toBe(true);
  });
});
