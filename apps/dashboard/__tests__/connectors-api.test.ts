import { describe, expect, it, vi, beforeEach } from "vitest";

const mocks = vi.hoisted(() => {
  class MockConnectorStoreError extends Error {
    readonly code: string;

    constructor(code: string, message: string) {
      super(message);
      this.name = "ConnectorStoreError";
      this.code = code;
    }
  }

  return {
    ConnectorStoreError: MockConnectorStoreError,
    getConnectorManifest: vi.fn(),
    upsertMcpConnector: vi.fn(),
    smokeConnector: vi.fn(),
    armConnector: vi.fn(),
  };
});

vi.mock("@/lib/connector-store", () => mocks);

import { GET, POST } from "@/api/connectors/route";
import { POST as ARM } from "@/api/connectors/[id]/arm/route";
import { POST as SMOKE } from "@/api/connectors/[id]/smoke/route";

function adminRequest(url: string, init: RequestInit = {}): Request {
  const headers = new Headers(init.headers);
  headers.set("authorization", "Bearer admin-token");
  return new Request(url, { ...init, headers });
}

const connector = {
  id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  name: "Demo MCP evidence",
  connector_kind: "evidence",
  transport: "mcp_http",
  provider: "mcp",
  server_url: "https://mcp.example.com",
  tool_name: "search",
  input_mapper: "query_limit",
  result_mapper: "generic_search",
  allowed_tools: ["search"],
  timeout_seconds: 20,
  max_results: 5,
  max_usdc: "0.050000",
  auth_configured: true,
  auth_secret_hint: "…1234",
  smoke_status: "passed",
  smoke_receipt: null,
  armed: false,
  armable: true,
  fail_closed: true,
  status_label: "smoke_passed",
  created_at: "2026-05-17T00:00:00Z",
  updated_at: "2026-05-17T00:00:00Z",
};

describe("connectors API routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    process.env.CONNECTOR_ADMIN_TOKEN = "admin-token";
  });

  it("requires admin auth for connector manifests", async () => {
    const response = await GET(new Request("http://localhost/api/connectors") as never);

    expect(response.status).toBe(401);
    expect(mocks.getConnectorManifest).not.toHaveBeenCalled();
  });

  it("GET /api/connectors returns a redacted manifest", async () => {
    mocks.getConnectorManifest.mockResolvedValue({
      connectors: [connector],
      active_connector_id: null,
      active_transport: null,
      mcp_first: true,
      fail_closed_default: true,
    });

    const response = await GET(adminRequest("http://localhost/api/connectors") as never);
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.connectors[0].auth_configured).toBe(true);
    expect(JSON.stringify(body)).not.toContain("auth_secret_ciphertext");
  });

  it("POST /api/connectors validates and saves MCP connector config", async () => {
    mocks.upsertMcpConnector.mockResolvedValue(connector);
    const request = adminRequest("http://localhost/api/connectors", {
      method: "POST",
      body: JSON.stringify({
        name: "Demo MCP evidence",
        server_url: "https://mcp.example.com",
        tool_name: "search",
        input_mapper: "query_limit",
        result_mapper: "generic_search",
        allowed_tools: ["search"],
        timeout_seconds: 20,
        max_results: 5,
        bearer_token: "token_1234",
      }),
    });

    const response = await POST(request as never);
    const body = await response.json();

    expect(response.status).toBe(201);
    expect(body.connector.id).toBe(connector.id);
    expect(mocks.upsertMcpConnector).toHaveBeenCalledWith(expect.objectContaining({ tool_name: "search" }));
    expect(JSON.stringify(body)).not.toContain("token_1234");
  });

  it("POST /api/connectors rejects invalid connector payloads", async () => {
    const request = adminRequest("http://localhost/api/connectors", {
      method: "POST",
      body: JSON.stringify({ name: "missing url" }),
    });

    const response = await POST(request as never);

    expect(response.status).toBe(400);
  });

  it("POST smoke returns 404 for missing connectors", async () => {
    mocks.smokeConnector.mockRejectedValue(new mocks.ConnectorStoreError("connector_not_found", "missing"));

    const response = await SMOKE(adminRequest("http://localhost") as never, {
      params: Promise.resolve({ id: connector.id }),
    });

    expect(response.status).toBe(404);
  });

  it("POST arm requires a passing smoke receipt", async () => {
    mocks.armConnector.mockRejectedValue(new mocks.ConnectorStoreError("connector_smoke_required", "smoke first"));

    const response = await ARM(adminRequest("http://localhost") as never, {
      params: Promise.resolve({ id: connector.id }),
    });

    expect(response.status).toBe(409);
  });
});
