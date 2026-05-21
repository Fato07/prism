import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

import { GET } from "@/api/admin/runtime/route";

const VALID_TOKEN = "op-test-fixture-value-abc";
const WRONG_TOKEN = "wrong-token-456";
const TRADER_URL = "http://localhost:3201";

function adminRequest(authToken?: string): Request {
  const headers: Record<string, string> = {};
  if (authToken) {
    headers.authorization = `Bearer ${authToken}`;
  }
  return new Request("http://localhost:3200/api/admin/runtime", { headers });
}

const STATUS_FIXTURE = {
  scheduler_running: false,
  interval_minutes: 5,
  auto_pipeline_enabled: false,
  trade_mode: "paper",
  last_tick_timestamp: null,
  next_tick: null,
  last_error: null,
  service_version: "0.1.0",
};

describe("GET /api/admin/runtime", () => {
  beforeEach(() => {
    process.env.OPERATOR_ADMIN_TOKEN = VALID_TOKEN;
    process.env.TRADER_INTERNAL_URL = TRADER_URL;
    vi.restoreAllMocks();
  });

  afterEach(() => {
    delete (process.env as Record<string, string | undefined>).OPERATOR_ADMIN_TOKEN;
    delete (process.env as Record<string, string | undefined>).TRADER_INTERNAL_URL;
    delete (process.env as Record<string, string | undefined>).CONNECTOR_ADMIN_TOKEN;
  });

  it("returns 401 when no auth header is present (VAL-ADMIN-003)", async () => {
    const response = await GET(adminRequest() as never);
    expect(response.status).toBe(401);

    const body = await response.json();
    expect(body.error).toBe("operator_admin_required");
  });

  it("returns 401 for wrong token (VAL-ADMIN-004) — same body as missing", async () => {
    const missingResponse = await GET(adminRequest() as never);
    const missingBody = await missingResponse.json();

    const wrongResponse = await GET(adminRequest(WRONG_TOKEN) as never);
    const wrongBody = await wrongResponse.json();

    expect(wrongResponse.status).toBe(401);
    expect(wrongBody).toEqual(missingBody);
  });

  it("returns 401 when OPERATOR_ADMIN_TOKEN is unset (VAL-ADMIN-006)", async () => {
    delete (process.env as Record<string, string | undefined>).OPERATOR_ADMIN_TOKEN;
    const response = await GET(adminRequest(VALID_TOKEN) as never);
    expect(response.status).toBe(401);
  });

  it("returns 401 when CONNECTOR_ADMIN_TOKEN is used (VAL-ADMIN-005)", async () => {
    process.env.CONNECTOR_ADMIN_TOKEN = "connector-token";
    const response = await GET(
      (() => {
        const req = new Request("http://localhost:3200/api/admin/runtime", {
          headers: { authorization: "Bearer connector-token" },
        });
        return req as never;
      })() as never,
    );
    expect(response.status).toBe(401);
  });

  it("returns 502 when TRADER_INTERNAL_URL is not set", async () => {
    delete (process.env as Record<string, string | undefined>).TRADER_INTERNAL_URL;
    const response = await GET(adminRequest(VALID_TOKEN) as never);
    expect(response.status).toBe(502);

    const body = await response.json();
    expect(body.error).toBe("trader_unreachable");
  });

  it("proxies trader /status successfully (VAL-ADMIN-007)", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(STATUS_FIXTURE), { status: 200 }),
    );
    globalThis.fetch = mockFetch;

    const response = await GET(adminRequest(VALID_TOKEN) as never);
    expect(response.status).toBe(200);

    const body = await response.json();
    expect(body).toEqual(STATUS_FIXTURE);
    expect(mockFetch).toHaveBeenCalledWith(`${TRADER_URL}/status`, {
      method: "GET",
      headers: { Accept: "application/json" },
    });
  });

  it("returns 502 when trader is unreachable (VAL-ADMIN-008)", async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error("ECONNREFUSED"));
    globalThis.fetch = mockFetch;

    const response = await GET(adminRequest(VALID_TOKEN) as never);
    expect(response.status).toBe(502);

    const body = await response.json();
    expect(body.error).toBe("trader_unreachable");
  });

  it("returns 502 when trader returns non-2xx status", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      new Response("Internal Server Error", { status: 500 }),
    );
    globalThis.fetch = mockFetch;

    const response = await GET(adminRequest(VALID_TOKEN) as never);
    expect(response.status).toBe(502);
  });

  it("sets Cache-Control: no-store on all responses (VAL-ADMIN-014)", async () => {
    // Test unauthorized response
    const unauthResponse = await GET(adminRequest() as never);
    expect(unauthResponse.headers.get("Cache-Control")).toBe("no-store");

    // Test success response
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(STATUS_FIXTURE), { status: 200 }),
    );
    globalThis.fetch = mockFetch;

    const successResponse = await GET(adminRequest(VALID_TOKEN) as never);
    expect(successResponse.headers.get("Cache-Control")).toBe("no-store");

    // Test error response
    delete (process.env as Record<string, string | undefined>).TRADER_INTERNAL_URL;
    process.env.OPERATOR_ADMIN_TOKEN = VALID_TOKEN;
    const errorResponse = await GET(adminRequest(VALID_TOKEN) as never);
    expect(errorResponse.headers.get("Cache-Control")).toBe("no-store");
  });

  it("returns Cache-Control: no-store on 401 and 502 error responses (VAL-ADMIN-020)", async () => {
    // 401 response must include Cache-Control: no-store
    const unauthResponse = await GET(adminRequest() as never);
    expect(unauthResponse.status).toBe(401);
    expect(unauthResponse.headers.get("Cache-Control")).toBe("no-store");

    // 401 with wrong token must include Cache-Control: no-store
    const wrongTokenResponse = await GET(adminRequest(WRONG_TOKEN) as never);
    expect(wrongTokenResponse.status).toBe(401);
    expect(wrongTokenResponse.headers.get("Cache-Control")).toBe("no-store");

    // 502 when TRADER_INTERNAL_URL is not set must include Cache-Control: no-store
    delete (process.env as Record<string, string | undefined>).TRADER_INTERNAL_URL;
    process.env.OPERATOR_ADMIN_TOKEN = VALID_TOKEN;
    const noUrlResponse = await GET(adminRequest(VALID_TOKEN) as never);
    expect(noUrlResponse.status).toBe(502);
    expect(noUrlResponse.headers.get("Cache-Control")).toBe("no-store");

    // 502 when trader fetch rejects must include Cache-Control: no-store
    process.env.TRADER_INTERNAL_URL = TRADER_URL;
    const mockFetch = vi.fn().mockRejectedValue(new Error("ECONNREFUSED"));
    globalThis.fetch = mockFetch;
    const fetchErrorResponse = await GET(adminRequest(VALID_TOKEN) as never);
    expect(fetchErrorResponse.status).toBe(502);
    expect(fetchErrorResponse.headers.get("Cache-Control")).toBe("no-store");

    // 502 when trader returns non-2xx must include Cache-Control: no-store
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response("Internal Server Error", { status: 500 }),
    );
    const non2xxResponse = await GET(adminRequest(VALID_TOKEN) as never);
    expect(non2xxResponse.status).toBe(502);
    expect(non2xxResponse.headers.get("Cache-Control")).toBe("no-store");
  });

  it("does not forward OPERATOR_ADMIN_TOKEN to the trader (VAL-ADMIN-012)", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(STATUS_FIXTURE), { status: 200 }),
    );
    globalThis.fetch = mockFetch;

    await GET(adminRequest(VALID_TOKEN) as never);

    // Verify the fetch call headers do NOT include the operator token
    const fetchArgs = mockFetch.mock.calls[0];
    const fetchHeaders = fetchArgs[1]?.headers;
    expect(fetchHeaders).toBeDefined();
    expect(fetchHeaders).not.toHaveProperty("Authorization");
    expect(fetchHeaders).not.toHaveProperty("authorization");
    expect(fetchHeaders).not.toHaveProperty("X-Prism-Admin-Token");
    expect(fetchHeaders).not.toHaveProperty("x-prism-admin-token");
  });

  it("exports force-dynamic to prevent caching (VAL-ADMIN-015)", async () => {
    // The `dynamic` export is a compile-time constant. We verify it exists.
    // This is verified by the module-level `export const dynamic = "force-dynamic"`.
    const routeModule = await import("@/api/admin/runtime/route");
    expect(routeModule.dynamic).toBe("force-dynamic");
  });
});
