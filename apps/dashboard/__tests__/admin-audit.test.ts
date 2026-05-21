/**
 * Admin audit route tests — VAL-AUDIT-011
 *
 * Tests GET /api/admin/audit route: auth, event retrieval, limit, ordering.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

const VALID_TOKEN = "op-test-fixture-value-abc";
const WRONG_TOKEN = "wrong-token-xyz";

/** Module-level mock pool.  query() returns mock rows so tests can inspect. */
const mockPoolQuery = vi.fn();

vi.mock("@/lib/db", () => ({
  getPool: () => ({ query: mockPoolQuery }),
}));

function auditRequest(authToken?: string, limit?: number): Request {
  const headers: Record<string, string> = {};
  if (authToken) {
    headers.authorization = `Bearer ${authToken}`;
  }
  const url =
    limit !== undefined
      ? `http://localhost:3200/api/admin/audit?limit=${limit}`
      : "http://localhost:3200/api/admin/audit";
  return new Request(url, { headers });
}

const MOCK_EVENTS = [
  {
    id: "uuid-1",
    actor: "operator_admin",
    action: "start_scheduler",
    old_state: { scheduler_running: false },
    new_state: { scheduler_running: true, interval_minutes: 5 },
    timestamp: "2026-05-20T10:05:00.000Z",
    result: "success",
    error: null,
  },
  {
    id: "uuid-2",
    actor: "operator_admin",
    action: "stop_scheduler",
    old_state: { scheduler_running: true },
    new_state: { scheduler_running: false },
    timestamp: "2026-05-20T10:00:00.000Z",
    result: "success",
    error: null,
  },
  {
    id: "uuid-3",
    actor: "unknown",
    action: "start_scheduler",
    old_state: null,
    new_state: null,
    timestamp: "2026-05-20T09:55:00.000Z",
    result: "unauthorized",
    error: "Missing or invalid operator token",
  },
];

/** Return only the SELECT FROM operator_events calls. */
function auditSelectCalls() {
  return mockPoolQuery.mock.calls.filter(
    (call: unknown[]) =>
      typeof call[0] === "string" &&
      (call[0] as string).includes("FROM operator_events"),
  );
}

describe("GET /api/admin/audit", () => {
  beforeEach(() => {
    process.env.OPERATOR_ADMIN_TOKEN = VALID_TOKEN;
    mockPoolQuery.mockClear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    delete (process.env as Record<string, string | undefined>).OPERATOR_ADMIN_TOKEN;
  });

  it("returns 401 when no auth header is present", async () => {
    const { GET } = await import("@/api/admin/audit/route");
    const response = await GET(auditRequest() as never);
    expect(response.status).toBe(401);

    const body = await response.json();
    expect(body.error).toBe("operator_admin_required");
  });

  it("returns 401 for wrong token", async () => {
    const { GET } = await import("@/api/admin/audit/route");
    const response = await GET(auditRequest(WRONG_TOKEN) as never);
    expect(response.status).toBe(401);
  });

  it("returns 401 when OPERATOR_ADMIN_TOKEN is unset", async () => {
    delete (process.env as Record<string, string | undefined>).OPERATOR_ADMIN_TOKEN;
    const { GET } = await import("@/api/admin/audit/route");
    const response = await GET(auditRequest(VALID_TOKEN) as never);
    expect(response.status).toBe(401);
  });

  it("returns recent events ordered newest-first (VAL-AUDIT-011)", async () => {
    mockPoolQuery.mockResolvedValueOnce({ rows: MOCK_EVENTS });

    const { GET } = await import("@/api/admin/audit/route");
    const response = await GET(auditRequest(VALID_TOKEN) as never);
    expect(response.status).toBe(200);

    const body = await response.json();
    expect(body.events).toBeDefined();
    expect(Array.isArray(body.events)).toBe(true);
    expect(body.events.length).toBe(3);

    // Verify ordering: newest first
    expect(body.events[0].timestamp).toBe("2026-05-20T10:05:00.000Z");
    expect(body.events[1].timestamp).toBe("2026-05-20T10:00:00.000Z");

    // Verify query includes ORDER BY timestamp DESC
    const selectCalls = auditSelectCalls();
    expect(selectCalls.length).toBeGreaterThanOrEqual(1);
    const sql = selectCalls[0][0] as string;
    expect(sql).toContain("ORDER BY");
    expect(sql).toContain("DESC");
  });

  it("supports limit parameter (default ≥ 50, respects custom limit)", async () => {
    mockPoolQuery.mockResolvedValueOnce({ rows: [] });

    const { GET } = await import("@/api/admin/audit/route");
    await GET(auditRequest(VALID_TOKEN, 10) as never);

    const selectCalls = auditSelectCalls();
    expect(selectCalls.length).toBeGreaterThanOrEqual(1);

    const params = selectCalls[0][1] as unknown[];
    expect(params[0]).toBe(10);
  });

  it("defaults limit when no limit param provided", async () => {
    mockPoolQuery.mockResolvedValueOnce({ rows: [] });

    const { GET } = await import("@/api/admin/audit/route");
    await GET(auditRequest(VALID_TOKEN) as never);

    const selectCalls = auditSelectCalls();
    const params = selectCalls[0][1] as unknown[];
    // Default should be 50
    expect(params[0]).toBe(50);
  });

  it("caps limit at 200", async () => {
    mockPoolQuery.mockResolvedValueOnce({ rows: [] });

    const { GET } = await import("@/api/admin/audit/route");
    await GET(auditRequest(VALID_TOKEN, 500) as never);

    const selectCalls = auditSelectCalls();
    const params = selectCalls[0][1] as unknown[];
    expect(params[0]).toBe(200);
  });

  it("rejects limit less than 1 (defaults to 1)", async () => {
    mockPoolQuery.mockResolvedValueOnce({ rows: [] });

    const { GET } = await import("@/api/admin/audit/route");
    await GET(auditRequest(VALID_TOKEN, 0) as never);

    const selectCalls = auditSelectCalls();
    const params = selectCalls[0][1] as unknown[];
    expect(params[0]).toBe(1);
  });

  it("returns empty events array when no audit events exist", async () => {
    mockPoolQuery.mockResolvedValueOnce({ rows: [] });

    const { GET } = await import("@/api/admin/audit/route");
    const response = await GET(auditRequest(VALID_TOKEN) as never);
    expect(response.status).toBe(200);

    const body = await response.json();
    expect(body.events).toEqual([]);
  });

  it("returns events with all expected fields", async () => {
    mockPoolQuery.mockResolvedValueOnce({ rows: MOCK_EVENTS });

    const { GET } = await import("@/api/admin/audit/route");
    const response = await GET(auditRequest(VALID_TOKEN) as never);
    const body = await response.json();

    const event = body.events[0];
    expect(event).toHaveProperty("id");
    expect(event).toHaveProperty("actor");
    expect(event).toHaveProperty("action");
    expect(event).toHaveProperty("old_state");
    expect(event).toHaveProperty("new_state");
    expect(event).toHaveProperty("timestamp");
    expect(event).toHaveProperty("result");
    expect(event).toHaveProperty("error");
  });

  it("sets Cache-Control: no-store on all responses", async () => {
    // Unauthorized
    const { GET } = await import("@/api/admin/audit/route");
    const unauthResponse = await GET(auditRequest() as never);
    expect(unauthResponse.headers.get("Cache-Control")).toBe("no-store");

    // Success
    mockPoolQuery.mockResolvedValueOnce({ rows: MOCK_EVENTS });
    process.env.OPERATOR_ADMIN_TOKEN = VALID_TOKEN;
    const successResponse = await GET(auditRequest(VALID_TOKEN) as never);
    expect(successResponse.headers.get("Cache-Control")).toBe("no-store");
  });

  it("exports force-dynamic", async () => {
    const routeModule = await import("@/api/admin/audit/route");
    expect(routeModule.dynamic).toBe("force-dynamic");
  });

  it("does not expose DATABASE_URL or secrets in response (VAL-AUDIT-010)", async () => {
    mockPoolQuery.mockResolvedValueOnce({ rows: MOCK_EVENTS });

    const { GET } = await import("@/api/admin/audit/route");
    const response = await GET(auditRequest(VALID_TOKEN) as never);
    const body = await response.json();
    const bodyStr = JSON.stringify(body);

    expect(bodyStr).not.toContain("sk-");
    expect(bodyStr).not.toContain("Bearer ");
    expect(bodyStr).not.toContain("_SECRET");
    expect(bodyStr).not.toContain("_KEY");
    expect(bodyStr).not.toContain(VALID_TOKEN);
  });

  it("VALID_TOKEN in env does not leak into query or response body", async () => {
    mockPoolQuery.mockResolvedValueOnce({ rows: MOCK_EVENTS });

    const { GET } = await import("@/api/admin/audit/route");
    const response = await GET(auditRequest(VALID_TOKEN) as never);
    const body = await response.json();
    expect(JSON.stringify(body)).not.toContain(VALID_TOKEN);
  });
});

// ---------------------------------------------------------------------------
// VAL-AUDIT-014: Audit log is append-only
// ---------------------------------------------------------------------------
describe("VAL-AUDIT-014: Audit log is append-only", () => {
  it("audit route source contains no UPDATE or DELETE on operator_events", async () => {
    const fs = await import("node:fs");
    const path = await import("node:path");

    const auditRoutePath = path.resolve(__dirname, "../app/api/admin/audit/route.ts");
    const content = fs.readFileSync(auditRoutePath, "utf-8");

    // No UPDATE or DELETE queries on operator_events
    expect(content).not.toMatch(/UPDATE\s+operator_events/i);
    expect(content).not.toMatch(/DELETE\s+FROM\s+operator_events/i);

    // Only SELECT should appear when operator_events is referenced
    if (content.includes("operator_events")) {
      // Use dotAll (s flag) to match across newlines in template literals
      expect(content).toMatch(/SELECT[\s\S]*FROM\s+operator_events/im);
    }
  });

  it("audit route only performs SELECT queries, never modifies rows", () => {
    // Verify through mock: GET /api/admin/audit only calls query() for SELECT
    const selectQueries = auditSelectCalls();
    for (const call of selectQueries) {
      const sql = call[0] as string;
      expect(sql).toMatch(/^SELECT/i);
      expect(sql).not.toMatch(/^UPDATE/i);
      expect(sql).not.toMatch(/^DELETE/i);
      expect(sql).not.toMatch(/^INSERT/i);
    }
  });
});

// ---------------------------------------------------------------------------
// VAL-AUDIT-017: Unauthorized reads do not produce audit events
// ---------------------------------------------------------------------------
describe("VAL-AUDIT-017: Unauthorized reads do not produce audit events", () => {
  beforeEach(() => {
    process.env.OPERATOR_ADMIN_TOKEN = VALID_TOKEN;
    mockPoolQuery.mockClear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    delete (process.env as Record<string, string | undefined>).OPERATOR_ADMIN_TOKEN;
  });

  it("GET /api/admin/runtime unauthorized does not write audit events", async () => {
    const { GET } = await import("@/api/admin/runtime/route");

    mockPoolQuery.mockClear();
    const request = new Request("http://localhost:3200/api/admin/runtime");
    const response = await GET(request as never);
    expect(response.status).toBe(401);

    // Check that no INSERT INTO operator_events was issued
    const insertCalls = mockPoolQuery.mock.calls.filter(
      (call: unknown[]) =>
        typeof call[0] === "string" &&
        (call[0] as string).toLowerCase().includes("insert"),
    );
    expect(insertCalls.length).toBe(0);
  });

  it("GET /api/admin/audit unauthorized does not write audit events", async () => {
    const { GET } = await import("@/api/admin/audit/route");

    mockPoolQuery.mockClear();
    const request = new Request("http://localhost:3200/api/admin/audit");
    const response = await GET(request as never);
    expect(response.status).toBe(401);

    // Check that no INSERT INTO operator_events was issued
    // The route returns 401 before reaching any pool query
    const insertCalls = mockPoolQuery.mock.calls.filter(
      (call: unknown[]) =>
        typeof call[0] === "string" &&
        (call[0] as string).toLowerCase().includes("insert"),
    );
    expect(insertCalls.length).toBe(0);
  });

  it("GET /api/admin/runtime source does not reference writeAuditEvent or INSERT", async () => {
    const fs = await import("node:fs");
    const path = await import("node:path");

    const runtimePath = path.resolve(__dirname, "../app/api/admin/runtime/route.ts");
    const content = fs.readFileSync(runtimePath, "utf-8");

    // Runtime route must not write audit events
    expect(content).not.toContain("writeAuditEvent");
    expect(content).not.toMatch(/INSERT\s+INTO\s+operator_events/i);
    expect(content).not.toContain("operator_events");
  });

  it("GET /api/admin/audit source does not reference writeAuditEvent or INSERT", async () => {
    const fs = await import("node:fs");
    const path = await import("node:path");

    const auditPath = path.resolve(__dirname, "../app/api/admin/audit/route.ts");
    const content = fs.readFileSync(auditPath, "utf-8");

    // Audit route must not write audit events (it's read-only)
    expect(content).not.toContain("writeAuditEvent");
    expect(content).not.toMatch(/INSERT\s+INTO\s+operator_events/i);
  });
});
