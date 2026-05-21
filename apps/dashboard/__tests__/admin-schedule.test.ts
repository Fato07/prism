/**
 * Admin schedule route tests — VAL-ADMIN-009..013, VAL-AUDIT-004..008,010,012
 *
 * Tests POST /api/admin/schedule/start and POST /api/admin/schedule/stop
 * with auth, proxy, and audit-event writing.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

const VALID_TOKEN = "op-test-fixture-value-abc";
const WRONG_TOKEN = "wrong-token-xyz";
const TRADER_URL = "http://localhost:3201";

/** Module-level mock pool.  query() records calls so tests can inspect them. */
const mockPoolQuery = vi.fn().mockResolvedValue({ rows: [], rowCount: 0 });

vi.mock("@/lib/db", () => ({
  getPool: () => ({ query: mockPoolQuery }),
}));

function adminRequest(
  path: string,
  authToken?: string,
  body?: Record<string, unknown>,
): Request {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (authToken) {
    headers.authorization = `Bearer ${authToken}`;
  }
  return new Request(`http://localhost:3200${path}`, {
    method: "POST",
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
}

const STATUS_STOPPED = {
  scheduler_running: false,
  interval_minutes: 5,
  auto_pipeline_enabled: false,
  trade_mode: "paper",
  last_tick_timestamp: null,
  next_tick: null,
  last_error: null,
  service_version: "0.1.0",
};

const STATUS_RUNNING = {
  scheduler_running: true,
  interval_minutes: 5,
  auto_pipeline_enabled: false,
  trade_mode: "paper",
  last_tick_timestamp: "2026-05-20T10:00:00Z",
  next_tick: "2026-05-20T10:05:00Z",
  last_error: null,
  service_version: "0.1.0",
};

/** Return only the INSERT INTO operator_events calls from the mock pool. */
function auditInsertCalls() {
  return mockPoolQuery.mock.calls.filter(
    (call: unknown[]) =>
      typeof call[0] === "string" &&
      (call[0] as string).includes("INSERT INTO operator_events"),
  );
}

describe("POST /api/admin/schedule/start", () => {
  beforeEach(() => {
    process.env.OPERATOR_ADMIN_TOKEN = VALID_TOKEN;
    process.env.TRADER_INTERNAL_URL = TRADER_URL;
    mockPoolQuery.mockClear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    delete (process.env as Record<string, string | undefined>).OPERATOR_ADMIN_TOKEN;
    delete (process.env as Record<string, string | undefined>).TRADER_INTERNAL_URL;
  });

  it("returns 401 when no auth header is present", async () => {
    const { POST } = await import("@/api/admin/schedule/start/route");
    const response = await POST(adminRequest("/api/admin/schedule/start") as never);
    expect(response.status).toBe(401);

    const body = await response.json();
    expect(body.error).toBe("operator_admin_required");
  });

  it("returns 401 for wrong token — same body as missing", async () => {
    const { POST } = await import("@/api/admin/schedule/start/route");

    const missingResponse = await POST(
      adminRequest("/api/admin/schedule/start") as never,
    );
    const missingBody = await missingResponse.json();

    const wrongResponse = await POST(
      adminRequest("/api/admin/schedule/start", WRONG_TOKEN) as never,
    );
    const wrongBody = await wrongResponse.json();

    expect(wrongResponse.status).toBe(401);
    expect(wrongBody).toEqual(missingBody);
  });

  it("writes audit event on unauthorized attempt (VAL-AUDIT-007)", async () => {
    const { POST } = await import("@/api/admin/schedule/start/route");
    await POST(adminRequest("/api/admin/schedule/start") as never);

    const insertCalls = auditInsertCalls();
    expect(insertCalls.length).toBe(1);

    const params: unknown[] = insertCalls[0][1] as unknown[];
    // params order: actor ($1), action ($2), old_state ($3), new_state ($4), result ($5), error ($6)
    expect(params[0]).toBe("unknown"); // actor
    expect(params[1]).toBe("start_scheduler"); // action
    expect(params[4]).toBe("unauthorized"); // result
    // actor should never contain the token value
    expect(JSON.stringify(params)).not.toContain(VALID_TOKEN);
  });

  it("proxies to trader POST /schedule successfully (VAL-ADMIN-009)", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(STATUS_STOPPED), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: "started" }), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(STATUS_RUNNING), { status: 200 }),
      );
    globalThis.fetch = mockFetch;

    const { POST } = await import("@/api/admin/schedule/start/route");
    const response = await POST(
      adminRequest("/api/admin/schedule/start", VALID_TOKEN) as never,
    );
    expect(response.status).toBe(200);

    const body = await response.json();
    expect(body.status).toBe("started");

    // Verify proxy call to trader POST /schedule
    const scheduleCall = mockFetch.mock.calls.find(
      (call: unknown[]) =>
        typeof call[0] === "string" &&
        (call[0] as string).endsWith("/schedule") &&
        (call[1] as Record<string, unknown> | undefined)?.method === "POST",
    );
    expect(scheduleCall).toBeDefined();
    expect(scheduleCall![0]).toBe(`${TRADER_URL}/schedule`);
  });

  it("writes audit event on successful start (VAL-AUDIT-004)", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_STOPPED), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "started" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_RUNNING), { status: 200 }));
    globalThis.fetch = mockFetch;

    const { POST } = await import("@/api/admin/schedule/start/route");
    await POST(adminRequest("/api/admin/schedule/start", VALID_TOKEN) as never);

    const insertCalls = auditInsertCalls();
    expect(insertCalls.length).toBe(1);

    const params: unknown[] = insertCalls[0][1] as unknown[];
    // params order: actor ($1), action ($2), old_state ($3), new_state ($4), result ($5), error ($6)
    expect(params[0]).toBe("operator_admin"); // actor
    expect(params[1]).toBe("start_scheduler"); // action
    expect(params[4]).toBe("success"); // result

    // old_state should show stopped
    let oldState = params[2];
    if (typeof oldState === "string") oldState = JSON.parse(oldState);
    expect((oldState as Record<string, unknown>).scheduler_running).toBe(false);

    // new_state should show running
    let newState = params[3];
    if (typeof newState === "string") newState = JSON.parse(newState);
    expect((newState as Record<string, unknown>).scheduler_running).toBe(true);

    // error should be null
    expect(params[5]).toBeNull();
  });

  it("writes audit event on failure when trader returns non-2xx (VAL-AUDIT-006)", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_STOPPED), { status: 200 }))
      .mockResolvedValueOnce(new Response("Internal Server Error", { status: 500 }));
    globalThis.fetch = mockFetch;

    const { POST } = await import("@/api/admin/schedule/start/route");
    const response = await POST(
      adminRequest("/api/admin/schedule/start", VALID_TOKEN) as never,
    );
    expect(response.status).toBe(502);

    const insertCalls = auditInsertCalls();
    expect(insertCalls.length).toBe(1);

    const params: unknown[] = insertCalls[0][1] as unknown[];
    expect(params[1]).toBe("start_scheduler"); // action
    expect(params[4]).toBe("failure"); // result

    // error should be populated
    expect(params[5]).toBeTruthy();
  });

  it("writes audit event on failure when trader is unreachable (VAL-AUDIT-006)", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_STOPPED), { status: 200 }))
      .mockRejectedValueOnce(new Error("ECONNREFUSED"));
    globalThis.fetch = mockFetch;

    const { POST } = await import("@/api/admin/schedule/start/route");
    const response = await POST(
      adminRequest("/api/admin/schedule/start", VALID_TOKEN) as never,
    );
    expect(response.status).toBe(502);

    const insertCalls = auditInsertCalls();
    expect(insertCalls.length).toBe(1);

    const params: unknown[] = insertCalls[0][1] as unknown[];
    expect(params[5]).toBeTruthy(); // error populated
  });

  it("does not accept or forward trade_mode parameter (VAL-ADMIN-011)", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_STOPPED), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "started" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_RUNNING), { status: 200 }));
    globalThis.fetch = mockFetch;

    const { POST } = await import("@/api/admin/schedule/start/route");
    // Send a body with trade_mode — it should be ignored
    await POST(
      adminRequest("/api/admin/schedule/start", VALID_TOKEN, {
        trade_mode: "live",
      }) as never,
    );

    // Verify the POST to trader /schedule does NOT contain trade_mode
    const scheduleCall = mockFetch.mock.calls.find(
      (call: unknown[]) =>
        typeof call[0] === "string" &&
        (call[0] as string).endsWith("/schedule") &&
        (call[1] as Record<string, unknown> | undefined)?.method === "POST",
    );
    expect(scheduleCall).toBeDefined();
    const fetchBody = (scheduleCall![1] as Record<string, unknown> | undefined)?.body;
    if (fetchBody) {
      expect(fetchBody).not.toContain("trade_mode");
      expect(fetchBody).not.toContain("live");
    }
  });

  it("does not forward interval_minutes to trader (VAL-ADMIN-018)", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_STOPPED), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "started" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_RUNNING), { status: 200 }));
    globalThis.fetch = mockFetch;

    const { POST } = await import("@/api/admin/schedule/start/route");
    // Send a body with interval_minutes — it should NOT be forwarded to the trader
    await POST(
      adminRequest("/api/admin/schedule/start", VALID_TOKEN, {
        interval_minutes: 123,
      }) as never,
    );

    // Verify the POST to trader /schedule does NOT contain interval_minutes
    const scheduleCall = mockFetch.mock.calls.find(
      (call: unknown[]) =>
        typeof call[0] === "string" &&
        (call[0] as string).endsWith("/schedule") &&
        (call[1] as Record<string, unknown> | undefined)?.method === "POST",
    );
    expect(scheduleCall).toBeDefined();

    // Verify no body was sent to the trader — the route sends an empty body
    const fetchOptions = scheduleCall![1] as Record<string, unknown>;
    expect(fetchOptions.body).toBeUndefined();

    // Double-check: JSON.stringify of the call args should not contain interval_minutes
    const callStr = JSON.stringify(scheduleCall);
    expect(callStr).not.toContain("interval_minutes");
  });

  it("does not forward OPERATOR_ADMIN_TOKEN to trader (VAL-ADMIN-012)", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_STOPPED), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "started" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_RUNNING), { status: 200 }));
    globalThis.fetch = mockFetch;

    const { POST } = await import("@/api/admin/schedule/start/route");
    await POST(adminRequest("/api/admin/schedule/start", VALID_TOKEN) as never);

    // Check all fetch calls — none should include the operator token
    for (const call of mockFetch.mock.calls) {
      const headers = call[1]?.headers;
      if (headers) {
        expect(headers).not.toHaveProperty("Authorization");
        expect(headers).not.toHaveProperty("authorization");
        expect(headers).not.toHaveProperty("X-Prism-Admin-Token");
        expect(headers).not.toHaveProperty("x-prism-admin-token");
      }
    }
  });

  it("accepts empty POST body (VAL-ADMIN-013)", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_STOPPED), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "started" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_RUNNING), { status: 200 }));
    globalThis.fetch = mockFetch;

    const { POST } = await import("@/api/admin/schedule/start/route");
    const headers: Record<string, string> = {
      authorization: `Bearer ${VALID_TOKEN}`,
    };
    const request = new Request(
      "http://localhost:3200/api/admin/schedule/start",
      { method: "POST", headers },
    );
    const response = await POST(request as never);
    expect(response.status).toBe(200);
    expect((await response.json()).status).toBe("started");
  });

  it("returns 401 when OPERATOR_ADMIN_TOKEN is unset", async () => {
    delete (process.env as Record<string, string | undefined>).OPERATOR_ADMIN_TOKEN;
    const { POST } = await import("@/api/admin/schedule/start/route");
    const response = await POST(
      adminRequest("/api/admin/schedule/start", VALID_TOKEN) as never,
    );
    expect(response.status).toBe(401);
  });

  it("returns 502 when trader returns non-2xx response", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_STOPPED), { status: 200 }))
      .mockResolvedValueOnce(new Response("error", { status: 500 }));
    globalThis.fetch = mockFetch;

    const { POST } = await import("@/api/admin/schedule/start/route");
    const response = await POST(
      adminRequest("/api/admin/schedule/start", VALID_TOKEN) as never,
    );
    expect(response.status).toBe(502);

    const body = await response.json();
    expect(body.error).toBe("trader_unreachable");
  });

  it("returns 502 when TRADER_INTERNAL_URL is not set", async () => {
    delete (process.env as Record<string, string | undefined>).TRADER_INTERNAL_URL;
    const { POST } = await import("@/api/admin/schedule/start/route");
    const response = await POST(
      adminRequest("/api/admin/schedule/start", VALID_TOKEN) as never,
    );
    expect(response.status).toBe(502);
  });

  it("sets Cache-Control: no-store on all responses (VAL-ADMIN-014)", async () => {
    // Unauthorized
    const { POST } = await import("@/api/admin/schedule/start/route");
    const unauthResponse = await POST(
      adminRequest("/api/admin/schedule/start") as never,
    );
    expect(unauthResponse.headers.get("Cache-Control")).toBe("no-store");

    // Success
    process.env.TRADER_INTERNAL_URL = TRADER_URL;
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_STOPPED), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "started" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_RUNNING), { status: 200 }));
    globalThis.fetch = mockFetch;
    const successResponse = await POST(
      adminRequest("/api/admin/schedule/start", VALID_TOKEN) as never,
    );
    expect(successResponse.headers.get("Cache-Control")).toBe("no-store");
  });

  it("old_state and new_state are well-formed JSONB objects (VAL-AUDIT-008)", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_STOPPED), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "started" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_RUNNING), { status: 200 }));
    globalThis.fetch = mockFetch;

    const { POST } = await import("@/api/admin/schedule/start/route");
    await POST(adminRequest("/api/admin/schedule/start", VALID_TOKEN) as never);

    const insertCalls = auditInsertCalls();
    expect(insertCalls.length).toBe(1);
    const params: unknown[] = insertCalls[0][1] as unknown[];

    // old_state (index 2) and new_state (index 3) should be objects
    let oldState = params[2];
    let newState = params[3];

    if (typeof oldState === "string") oldState = JSON.parse(oldState);
    if (typeof newState === "string") newState = JSON.parse(newState);

    expect(typeof oldState).toBe("object");
    expect(oldState).not.toBeNull();
    expect(typeof newState).toBe("object");
    expect(newState).not.toBeNull();

    // old_state indicates stopped
    expect((oldState as Record<string, unknown>).scheduler_running).toBe(false);
    // new_state indicates running
    expect((newState as Record<string, unknown>).scheduler_running).toBe(true);
  });

  it("exports force-dynamic", async () => {
    const routeModule = await import("@/api/admin/schedule/start/route");
    expect(routeModule.dynamic).toBe("force-dynamic");
  });
});

describe("POST /api/admin/schedule/stop", () => {
  beforeEach(() => {
    process.env.OPERATOR_ADMIN_TOKEN = VALID_TOKEN;
    process.env.TRADER_INTERNAL_URL = TRADER_URL;
    mockPoolQuery.mockClear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    delete (process.env as Record<string, string | undefined>).OPERATOR_ADMIN_TOKEN;
    delete (process.env as Record<string, string | undefined>).TRADER_INTERNAL_URL;
  });

  it("returns 401 when no auth header is present", async () => {
    const { POST } = await import("@/api/admin/schedule/stop/route");
    const response = await POST(adminRequest("/api/admin/schedule/stop") as never);
    expect(response.status).toBe(401);
  });

  it("proxies to trader DELETE /schedule successfully (VAL-ADMIN-010)", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(STATUS_RUNNING), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: "stopped" }), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(STATUS_STOPPED), { status: 200 }),
      );
    globalThis.fetch = mockFetch;

    const { POST } = await import("@/api/admin/schedule/stop/route");
    const response = await POST(
      adminRequest("/api/admin/schedule/stop", VALID_TOKEN) as never,
    );
    expect(response.status).toBe(200);

    const body = await response.json();
    expect(body.status).toBe("stopped");

    // Verify proxy call to trader DELETE /schedule
    const scheduleCall = mockFetch.mock.calls.find(
      (call: unknown[]) =>
        typeof call[0] === "string" &&
        (call[0] as string).endsWith("/schedule") &&
        (call[1] as Record<string, unknown> | undefined)?.method === "DELETE",
    );
    expect(scheduleCall).toBeDefined();
    expect(scheduleCall![0]).toBe(`${TRADER_URL}/schedule`);
  });

  it("writes audit event on successful stop (VAL-AUDIT-005)", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_RUNNING), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "stopped" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_STOPPED), { status: 200 }));
    globalThis.fetch = mockFetch;

    const { POST } = await import("@/api/admin/schedule/stop/route");
    await POST(adminRequest("/api/admin/schedule/stop", VALID_TOKEN) as never);

    const insertCalls = auditInsertCalls();
    expect(insertCalls.length).toBe(1);

    const params: unknown[] = insertCalls[0][1] as unknown[];
    // params order: actor ($1), action ($2), old_state ($3), new_state ($4), result ($5), error ($6)
    expect(params[0]).toBe("operator_admin"); // actor
    expect(params[1]).toBe("stop_scheduler"); // action
    expect(params[4]).toBe("success"); // result

    let oldState = params[2];
    let newState = params[3];
    if (typeof oldState === "string") oldState = JSON.parse(oldState);
    if (typeof newState === "string") newState = JSON.parse(newState);

    expect((oldState as Record<string, unknown>).scheduler_running).toBe(true);
    expect((newState as Record<string, unknown>).scheduler_running).toBe(false);
  });

  it("writes audit event on unauthorized stop attempt (VAL-AUDIT-007)", async () => {
    const { POST } = await import("@/api/admin/schedule/stop/route");
    await POST(adminRequest("/api/admin/schedule/stop") as never);

    const insertCalls = auditInsertCalls();
    expect(insertCalls.length).toBe(1);

    const params: unknown[] = insertCalls[0][1] as unknown[];
    expect(params[0]).toBe("unknown"); // actor = unknown
    expect(JSON.stringify(params)).not.toContain(VALID_TOKEN);
  });

  it("does not forward OPERATOR_ADMIN_TOKEN to trader (VAL-ADMIN-012)", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_RUNNING), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "stopped" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_STOPPED), { status: 200 }));
    globalThis.fetch = mockFetch;

    const { POST } = await import("@/api/admin/schedule/stop/route");
    await POST(adminRequest("/api/admin/schedule/stop", VALID_TOKEN) as never);

    for (const call of mockFetch.mock.calls) {
      const headers = call[1]?.headers;
      if (headers) {
        expect(headers).not.toHaveProperty("Authorization");
        expect(headers).not.toHaveProperty("authorization");
        expect(headers).not.toHaveProperty("X-Prism-Admin-Token");
        expect(headers).not.toHaveProperty("x-prism-admin-token");
      }
    }
  });

  it("accepts empty POST body (VAL-ADMIN-013)", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_RUNNING), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "stopped" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_STOPPED), { status: 200 }));
    globalThis.fetch = mockFetch;

    const { POST } = await import("@/api/admin/schedule/stop/route");
    const headers: Record<string, string> = {
      authorization: `Bearer ${VALID_TOKEN}`,
    };
    const request = new Request("http://localhost:3200/api/admin/schedule/stop", {
      method: "POST",
      headers,
    });
    const response = await POST(request as never);
    expect(response.status).toBe(200);
    expect((await response.json()).status).toBe("stopped");
  });

  it("returns 502 when trader is unreachable", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_RUNNING), { status: 200 }))
      .mockRejectedValueOnce(new Error("ECONNREFUSED"));
    globalThis.fetch = mockFetch;

    const { POST } = await import("@/api/admin/schedule/stop/route");
    const response = await POST(
      adminRequest("/api/admin/schedule/stop", VALID_TOKEN) as never,
    );
    expect(response.status).toBe(502);

    // Audit event should be written
    const insertCalls = auditInsertCalls();
    expect(insertCalls.length).toBe(1);

    const params: unknown[] = insertCalls[0][1] as unknown[];
    expect(params[5]).toBeTruthy(); // error populated
  });

  it("exports force-dynamic", async () => {
    const routeModule = await import("@/api/admin/schedule/stop/route");
    expect(routeModule.dynamic).toBe("force-dynamic");
  });
});

// ---------------------------------------------------------------------------
// VAL-AUDIT-006: Actor field populated correctly
// ---------------------------------------------------------------------------
describe("VAL-AUDIT-006: Actor field populated correctly", () => {
  beforeEach(() => {
    process.env.OPERATOR_ADMIN_TOKEN = VALID_TOKEN;
    process.env.TRADER_INTERNAL_URL = TRADER_URL;
    mockPoolQuery.mockClear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    delete (process.env as Record<string, string | undefined>).OPERATOR_ADMIN_TOKEN;
    delete (process.env as Record<string, string | undefined>).TRADER_INTERNAL_URL;
  });

  it("actor is 'operator_admin' for authenticated requests, never the token value", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_STOPPED), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "started" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_RUNNING), { status: 200 }));
    globalThis.fetch = mockFetch;

    // Also import stop to test both operations
    const { POST: startPost } = await import("@/api/admin/schedule/start/route");
    const { POST: stopPost } = await import("@/api/admin/schedule/stop/route");
    await startPost(adminRequest("/api/admin/schedule/start", VALID_TOKEN) as never);

    // Check start audit
    const startCalls = auditInsertCalls();
    const startParams = startCalls[startCalls.length - 1][1] as unknown[];
    expect(startParams[0]).toBe("operator_admin");
    expect(startParams[0]).not.toContain(VALID_TOKEN);
    expect(typeof startParams[0]).toBe("string");
    expect((startParams[0] as string).length).toBeGreaterThan(0);

    // Reset mocks for stop test
    mockPoolQuery.mockClear();
    mockFetch.mockClear();
    mockFetch
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_RUNNING), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "stopped" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_STOPPED), { status: 200 }));

    await stopPost(adminRequest("/api/admin/schedule/stop", VALID_TOKEN) as never);

    const stopCalls = auditInsertCalls();
    const stopParams = stopCalls[stopCalls.length - 1][1] as unknown[];
    expect(stopParams[0]).toBe("operator_admin");
    expect(stopParams[0]).not.toContain(VALID_TOKEN);
  });

  it("actor is 'unknown' for unauthorized requests, never the attempted token", async () => {
    const { POST } = await import("@/api/admin/schedule/start/route");
    // Send request with a specific wrong token
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      authorization: `Bearer ${WRONG_TOKEN}`,
    };
    const request = new Request(
      "http://localhost:3200/api/admin/schedule/start",
      { method: "POST", headers },
    );
    await POST(request as never);

    const insertCalls = auditInsertCalls();
    expect(insertCalls.length).toBe(1);
    const params = insertCalls[0][1] as unknown[];
    expect(params[0]).toBe("unknown");
    // Actor field must NEVER contain the token value
    expect(params[0]).not.toBe(WRONG_TOKEN);
    expect(JSON.stringify(params)).not.toContain(WRONG_TOKEN);
  });

  it("actor never contains any env var ending with _TOKEN, _KEY, or _SECRET", async () => {
    process.env.OPERATOR_ADMIN_TOKEN = "op-test-value-for-audit-check";
    process.env.CONNECTOR_ADMIN_TOKEN = "conn-test-value-for-audit-check";
    process.env.SOME_API_KEY = "sk-test-dummy-key-for-audit-check";

    const { POST } = await import("@/api/admin/schedule/start/route");
    // Unauthorized request
    await POST(adminRequest("/api/admin/schedule/start") as never);

    const insertCalls = auditInsertCalls();
    const params = insertCalls[0][1] as unknown[];
    const serialized = JSON.stringify(params);
    expect(serialized).not.toContain("op-test-value-for-audit-check");
    expect(serialized).not.toContain("conn-test-value-for-audit-check");
    expect(serialized).not.toContain("sk-test-dummy-key-for-audit-check");

    delete (process.env as Record<string, string | undefined>).CONNECTOR_ADMIN_TOKEN;
    delete (process.env as Record<string, string | undefined>).SOME_API_KEY;
  });
});

// ---------------------------------------------------------------------------
// VAL-AUDIT-007: Action field matches operation type
// ---------------------------------------------------------------------------
describe("VAL-AUDIT-007: Action field matches operation type", () => {
  beforeEach(() => {
    process.env.OPERATOR_ADMIN_TOKEN = VALID_TOKEN;
    process.env.TRADER_INTERNAL_URL = TRADER_URL;
    mockPoolQuery.mockClear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    delete (process.env as Record<string, string | undefined>).OPERATOR_ADMIN_TOKEN;
    delete (process.env as Record<string, string | undefined>).TRADER_INTERNAL_URL;
  });

  it("action is 'start_scheduler' for start operations", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_STOPPED), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "started" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_RUNNING), { status: 200 }));
    globalThis.fetch = mockFetch;

    const { POST } = await import("@/api/admin/schedule/start/route");
    await POST(adminRequest("/api/admin/schedule/start", VALID_TOKEN) as never);

    const insertCalls = auditInsertCalls();
    expect(insertCalls.length).toBe(1);
    const params = insertCalls[0][1] as unknown[];
    expect(params[1]).toBe("start_scheduler");
    expect(params[1]).not.toBe("stop_scheduler");
    expect(params[1]).not.toBe("update_interval");
  });

  it("action is 'stop_scheduler' for stop operations", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_RUNNING), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "stopped" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_STOPPED), { status: 200 }));
    globalThis.fetch = mockFetch;

    const { POST } = await import("@/api/admin/schedule/stop/route");
    await POST(adminRequest("/api/admin/schedule/stop", VALID_TOKEN) as never);

    const insertCalls = auditInsertCalls();
    expect(insertCalls.length).toBe(1);
    const params = insertCalls[0][1] as unknown[];
    expect(params[1]).toBe("stop_scheduler");
    expect(params[1]).not.toBe("start_scheduler");
    expect(params[1]).not.toBe("update_interval");
  });

  it("action is 'start_scheduler' even on unauthorized start attempt", async () => {
    const { POST } = await import("@/api/admin/schedule/start/route");
    await POST(adminRequest("/api/admin/schedule/start") as never);

    const insertCalls = auditInsertCalls();
    expect(insertCalls.length).toBe(1);
    const params = insertCalls[0][1] as unknown[];
    expect(params[1]).toBe("start_scheduler");
  });

  it("action is 'stop_scheduler' even on unauthorized stop attempt", async () => {
    const { POST } = await import("@/api/admin/schedule/stop/route");
    await POST(adminRequest("/api/admin/schedule/stop") as never);

    const insertCalls = auditInsertCalls();
    expect(insertCalls.length).toBe(1);
    const params = insertCalls[0][1] as unknown[];
    expect(params[1]).toBe("stop_scheduler");
  });
});

// ---------------------------------------------------------------------------
// VAL-AUDIT-008: Result field values are constrained
// ---------------------------------------------------------------------------
describe("VAL-AUDIT-008: Result field values constrained", () => {
  const VALID_RESULTS = new Set(["success", "failure", "unauthorized"]);

  beforeEach(() => {
    process.env.OPERATOR_ADMIN_TOKEN = VALID_TOKEN;
    process.env.TRADER_INTERNAL_URL = TRADER_URL;
    mockPoolQuery.mockClear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    delete (process.env as Record<string, string | undefined>).OPERATOR_ADMIN_TOKEN;
    delete (process.env as Record<string, string | undefined>).TRADER_INTERNAL_URL;
  });

  it("result is 'success' on successful start", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_STOPPED), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "started" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_RUNNING), { status: 200 }));
    globalThis.fetch = mockFetch;

    const { POST } = await import("@/api/admin/schedule/start/route");
    await POST(adminRequest("/api/admin/schedule/start", VALID_TOKEN) as never);

    const insertCalls = auditInsertCalls();
    expect(insertCalls.length).toBe(1);
    const params = insertCalls[0][1] as unknown[];
    expect(params[4]).toBe("success");
    expect(VALID_RESULTS.has(params[4] as string)).toBe(true);
  });

  it("result is 'success' on successful stop", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_RUNNING), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "stopped" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_STOPPED), { status: 200 }));
    globalThis.fetch = mockFetch;

    const { POST } = await import("@/api/admin/schedule/stop/route");
    await POST(adminRequest("/api/admin/schedule/stop", VALID_TOKEN) as never);

    const insertCalls = auditInsertCalls();
    expect(insertCalls.length).toBe(1);
    const params = insertCalls[0][1] as unknown[];
    expect(params[4]).toBe("success");
    expect(VALID_RESULTS.has(params[4] as string)).toBe(true);
  });

  it("result is 'failure' when trader unreachable", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_STOPPED), { status: 200 }))
      .mockRejectedValueOnce(new Error("ECONNREFUSED"));
    globalThis.fetch = mockFetch;

    const { POST } = await import("@/api/admin/schedule/start/route");
    await POST(adminRequest("/api/admin/schedule/start", VALID_TOKEN) as never);

    const insertCalls = auditInsertCalls();
    expect(insertCalls.length).toBe(1);
    const params = insertCalls[0][1] as unknown[];
    expect(params[4]).toBe("failure");
    expect(VALID_RESULTS.has(params[4] as string)).toBe(true);
  });

  it("result is 'unauthorized' when no token provided", async () => {
    const { POST } = await import("@/api/admin/schedule/start/route");
    await POST(adminRequest("/api/admin/schedule/start") as never);

    const insertCalls = auditInsertCalls();
    expect(insertCalls.length).toBe(1);
    const params = insertCalls[0][1] as unknown[];
    expect(params[4]).toBe("unauthorized");
    expect(VALID_RESULTS.has(params[4] as string)).toBe(true);
  });

  it("result is never a value outside {success, failure, unauthorized}", async () => {
    // Test unauthorized (start)
    let { POST } = await import("@/api/admin/schedule/start/route");
    await POST(adminRequest("/api/admin/schedule/start") as never);

    // Test unauthorized (stop)
    mockPoolQuery.mockClear();
    const { POST: stopPost } = await import("@/api/admin/schedule/stop/route");
    await stopPost(adminRequest("/api/admin/schedule/stop") as never);

    // Test failure (no TRADER_INTERNAL_URL)
    mockPoolQuery.mockClear();
    delete (process.env as Record<string, string | undefined>).TRADER_INTERNAL_URL;
    const { POST: startPost2 } = await import("@/api/admin/schedule/start/route");
    await startPost2(adminRequest("/api/admin/schedule/start", VALID_TOKEN) as never);

    // Collect all result values across all audit inserts
    const allCalls = auditInsertCalls();
    for (const call of allCalls) {
      const params = call[1] as unknown[];
      const result = params[4] as string;
      expect(VALID_RESULTS.has(result)).toBe(true);
    }
  });
});

// ---------------------------------------------------------------------------
// VAL-AUDIT-009: Error field populated on failure, null on success
// ---------------------------------------------------------------------------
describe("VAL-AUDIT-009: Error field behavior", () => {
  beforeEach(() => {
    process.env.OPERATOR_ADMIN_TOKEN = VALID_TOKEN;
    process.env.TRADER_INTERNAL_URL = TRADER_URL;
    mockPoolQuery.mockClear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    delete (process.env as Record<string, string | undefined>).OPERATOR_ADMIN_TOKEN;
    delete (process.env as Record<string, string | undefined>).TRADER_INTERNAL_URL;
  });

  it("error is null on successful start", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_STOPPED), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "started" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_RUNNING), { status: 200 }));
    globalThis.fetch = mockFetch;

    const { POST } = await import("@/api/admin/schedule/start/route");
    await POST(adminRequest("/api/admin/schedule/start", VALID_TOKEN) as never);

    const insertCalls = auditInsertCalls();
    expect(insertCalls.length).toBe(1);
    const params = insertCalls[0][1] as unknown[];
    expect(params[5]).toBeNull();
  });

  it("error is null on successful stop", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_RUNNING), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "stopped" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_STOPPED), { status: 200 }));
    globalThis.fetch = mockFetch;

    const { POST } = await import("@/api/admin/schedule/stop/route");
    await POST(adminRequest("/api/admin/schedule/stop", VALID_TOKEN) as never);

    const insertCalls = auditInsertCalls();
    expect(insertCalls.length).toBe(1);
    const params = insertCalls[0][1] as unknown[];
    expect(params[5]).toBeNull();
  });

  it("error is non-null string on trader fetch failure", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_STOPPED), { status: 200 }))
      .mockRejectedValueOnce(new Error("ECONNREFUSED"));
    globalThis.fetch = mockFetch;

    const { POST } = await import("@/api/admin/schedule/start/route");
    await POST(adminRequest("/api/admin/schedule/start", VALID_TOKEN) as never);

    const insertCalls = auditInsertCalls();
    expect(insertCalls.length).toBe(1);
    const params = insertCalls[0][1] as unknown[];
    expect(params[4]).toBe("failure");
    expect(params[5]).toBeTruthy();
    expect(typeof params[5]).toBe("string");
    expect((params[5] as string).length).toBeGreaterThan(0);
  });

  it("error is non-null string on trader non-2xx response", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_STOPPED), { status: 200 }))
      .mockResolvedValueOnce(new Response("Internal error", { status: 500 }));
    globalThis.fetch = mockFetch;

    const { POST } = await import("@/api/admin/schedule/start/route");
    await POST(adminRequest("/api/admin/schedule/start", VALID_TOKEN) as never);

    const insertCalls = auditInsertCalls();
    expect(insertCalls.length).toBe(1);
    const params = insertCalls[0][1] as unknown[];
    expect(params[4]).toBe("failure");
    expect(params[5]).toBeTruthy();
    expect(typeof params[5]).toBe("string");
    expect((params[5] as string).length).toBeGreaterThan(0);
    expect(params[5]).toContain("500");
  });

  it("error is non-null string on unauthorized attempt", async () => {
    const { POST } = await import("@/api/admin/schedule/start/route");
    await POST(adminRequest("/api/admin/schedule/start") as never);

    const insertCalls = auditInsertCalls();
    expect(insertCalls.length).toBe(1);
    const params = insertCalls[0][1] as unknown[];
    expect(params[4]).toBe("unauthorized");
    expect(params[5]).toBeTruthy();
    expect(typeof params[5]).toBe("string");
  });

  it("error field never contains secrets or tokens", async () => {
    process.env.OPERATOR_ADMIN_TOKEN = "op-test-value-for-error-check";

    const { POST } = await import("@/api/admin/schedule/start/route");
    await POST(adminRequest("/api/admin/schedule/start") as never);

    const insertCalls = auditInsertCalls();
    const params = insertCalls[0][1] as unknown[];
    const errorValue = params[5] as string;
    expect(errorValue).toBeTruthy();
    expect(errorValue).not.toContain("op-test-value-for-error-check");
    expect(errorValue).not.toContain("Bearer");
    expect(errorValue).not.toContain("sk-");
  });
});

// ---------------------------------------------------------------------------
// VAL-AUDIT-014: Audit log is append-only
// ---------------------------------------------------------------------------
describe("VAL-AUDIT-014: Audit log is append-only", () => {
  it("route source files contain no UPDATE or DELETE on operator_events", async () => {
    // Read the actual source files to verify no UPDATE/DELETE operations
    const fs = await import("node:fs");
    const path = await import("node:path");

    const routeDir = path.resolve(__dirname, "../app/api/admin/schedule");
    const files = [
      path.join(routeDir, "start", "route.ts"),
      path.join(routeDir, "stop", "route.ts"),
    ];

    for (const file of files) {
      const content = fs.readFileSync(file, "utf-8");
      // SQL UPDATE or DELETE on operator_events must not appear
      expect(content).not.toMatch(/UPDATE\s+operator_events/i);
      expect(content).not.toMatch(/DELETE\s+FROM\s+operator_events/i);
      // Only INSERT should appear when operator_events is mentioned
      if (content.includes("operator_events")) {
        // Use dotAll pattern for multi-line template literals
        expect(content).toMatch(/INSERT\s+INTO\s+operator_events/im);
      }
    }
  });

  it("running the same mutation twice creates two distinct audit rows", async () => {
    process.env.OPERATOR_ADMIN_TOKEN = VALID_TOKEN;
    process.env.TRADER_INTERNAL_URL = TRADER_URL;

    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_STOPPED), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "started" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_RUNNING), { status: 200 }))
      // Second call: already running scenario
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_RUNNING), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "already_running", interval_minutes: 5 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_RUNNING), { status: 200 }));
    globalThis.fetch = mockFetch;

    // First start — creates one audit row
    mockPoolQuery.mockClear();
    const { POST } = await import("@/api/admin/schedule/start/route");
    await POST(adminRequest("/api/admin/schedule/start", VALID_TOKEN) as never);
    const firstCallCount = auditInsertCalls().length;
    expect(firstCallCount).toBe(1);

    // Second start (simulating a separate operator action) — creates another row
    // Re-import to get fresh module state
    vi.resetModules();
    mockPoolQuery.mockClear();
    const { POST: POST2 } = await import("@/api/admin/schedule/start/route");
    await POST2(adminRequest("/api/admin/schedule/start", VALID_TOKEN) as never);
    const secondCallCount = auditInsertCalls().length;
    expect(secondCallCount).toBe(1);

    // Each mutation writes exactly one INSERT row — no updates
    expect(firstCallCount + secondCallCount).toBe(2);

    delete (process.env as Record<string, string | undefined>).OPERATOR_ADMIN_TOKEN;
    delete (process.env as Record<string, string | undefined>).TRADER_INTERNAL_URL;
  });
});

// ---------------------------------------------------------------------------
// VAL-AUDIT-016: Already-running start has old_state == new_state
// ---------------------------------------------------------------------------
describe("VAL-AUDIT-016: Already-running start writes audit with old_state == new_state", () => {
  beforeEach(() => {
    process.env.OPERATOR_ADMIN_TOKEN = VALID_TOKEN;
    process.env.TRADER_INTERNAL_URL = TRADER_URL;
    mockPoolQuery.mockClear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    delete (process.env as Record<string, string | undefined>).OPERATOR_ADMIN_TOKEN;
    delete (process.env as Record<string, string | undefined>).TRADER_INTERNAL_URL;
  });

  it("when trader returns 'already_running', old_state equals new_state", async () => {
    // Simulate scheduler already running:
    // 1. oldStatus → STATUS_RUNNING (scheduler_running: true)
    // 2. Trader returns 200 with status: "already_running"
    // 3. newStatus → STATUS_RUNNING (scheduler_running: true)
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_RUNNING), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "already_running", interval_minutes: 5 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_RUNNING), { status: 200 }));
    globalThis.fetch = mockFetch;

    const { POST } = await import("@/api/admin/schedule/start/route");
    const response = await POST(
      adminRequest("/api/admin/schedule/start", VALID_TOKEN) as never,
    );
    // Trader returns 200 for already_running — dashboard treats as success
    expect(response.status).toBe(200);

    const insertCalls = auditInsertCalls();
    expect(insertCalls.length).toBe(1);
    const params = insertCalls[0][1] as unknown[];

    // Result should be success (trader returned 200)
    expect(params[4]).toBe("success");
    // Error should be null (it's a success case)
    expect(params[5]).toBeNull();

    // old_state and new_state should both reflect running
    let oldState = params[2];
    let newState = params[3];
    if (typeof oldState === "string") oldState = JSON.parse(oldState);
    if (typeof newState === "string") newState = JSON.parse(newState);

    expect((oldState as Record<string, unknown>).scheduler_running).toBe(true);
    expect((newState as Record<string, unknown>).scheduler_running).toBe(true);

    // old_state equals new_state — no state transition occurred
    expect(JSON.stringify(oldState)).toBe(JSON.stringify(newState));
  });

  it("old_state and new_state differ on actual state transition (start)", async () => {
    // Normal start from stopped to running
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_STOPPED), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "started", interval_minutes: 5 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_RUNNING), { status: 200 }));
    globalThis.fetch = mockFetch;

    const { POST } = await import("@/api/admin/schedule/start/route");
    await POST(adminRequest("/api/admin/schedule/start", VALID_TOKEN) as never);

    const insertCalls = auditInsertCalls();
    const params = insertCalls[0][1] as unknown[];

    let oldState = params[2];
    let newState = params[3];
    if (typeof oldState === "string") oldState = JSON.parse(oldState);
    if (typeof newState === "string") newState = JSON.parse(newState);

    expect((oldState as Record<string, unknown>).scheduler_running).toBe(false);
    expect((newState as Record<string, unknown>).scheduler_running).toBe(true);
    // States should differ on actual transition
    expect(JSON.stringify(oldState)).not.toBe(JSON.stringify(newState));
  });

  it("old_state and new_state differ on actual state transition (stop)", async () => {
    // Normal stop from running to stopped
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_RUNNING), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "stopped", interval_minutes: 5 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_STOPPED), { status: 200 }));
    globalThis.fetch = mockFetch;

    const { POST } = await import("@/api/admin/schedule/stop/route");
    await POST(adminRequest("/api/admin/schedule/stop", VALID_TOKEN) as never);

    const insertCalls = auditInsertCalls();
    const params = insertCalls[0][1] as unknown[];

    let oldState = params[2];
    let newState = params[3];
    if (typeof oldState === "string") oldState = JSON.parse(oldState);
    if (typeof newState === "string") newState = JSON.parse(newState);

    expect((oldState as Record<string, unknown>).scheduler_running).toBe(true);
    expect((newState as Record<string, unknown>).scheduler_running).toBe(false);
    expect(JSON.stringify(oldState)).not.toBe(JSON.stringify(newState));
  });
});

// VAL-AUDIT-012: actor field always populated
describe("VAL-AUDIT-012: actor field is always populated", () => {
  beforeEach(() => {
    process.env.OPERATOR_ADMIN_TOKEN = VALID_TOKEN;
    process.env.TRADER_INTERNAL_URL = TRADER_URL;
    mockPoolQuery.mockClear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    delete (process.env as Record<string, string | undefined>).OPERATOR_ADMIN_TOKEN;
    delete (process.env as Record<string, string | undefined>).TRADER_INTERNAL_URL;
  });

  it("actor is 'operator_admin' for authenticated success", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_STOPPED), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "started" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(STATUS_RUNNING), { status: 200 }));
    globalThis.fetch = mockFetch;

    const { POST } = await import("@/api/admin/schedule/start/route");
    await POST(adminRequest("/api/admin/schedule/start", VALID_TOKEN) as never);

    const insertCalls = auditInsertCalls();
    expect(insertCalls.length).toBe(1);
    const params = insertCalls[0][1] as unknown[];
    expect(params[0]).toBe("operator_admin");
    expect(params[0]).toBeTruthy();
    expect(params[0]).not.toBe("");
  });

  it("actor is 'unknown' for unauthorized", async () => {
    const { POST } = await import("@/api/admin/schedule/start/route");
    await POST(adminRequest("/api/admin/schedule/start") as never);

    const insertCalls = auditInsertCalls();
    expect(insertCalls.length).toBe(1);
    const params = insertCalls[0][1] as unknown[];
    expect(params[0]).toBe("unknown");
    expect(params[0]).toBeTruthy();
  });
});
