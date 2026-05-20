/**
 * Admin schedule route tests — VAL-ADMIN-009..013, VAL-AUDIT-004..008,010,012
 *
 * Tests POST /api/admin/schedule/start and POST /api/admin/schedule/stop
 * with auth, proxy, and audit-event writing.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

const VALID_TOKEN = "operator-secret-token-abc";
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
