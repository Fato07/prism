import { NextRequest, NextResponse } from "next/server";

import { isOperatorAdminRequest } from "@/lib/operator-auth";
import { getPool } from "@/lib/db";

export const dynamic = "force-dynamic";

/**
 * Helper: fetch the trader's /status endpoint and return the parsed JSON
 * object, or null when the trader is unreachable.
 */
async function fetchTraderStatus(traderUrl: string): Promise<Record<string, unknown> | null> {
  try {
    const response = await fetch(`${traderUrl}/status`, {
      method: "GET",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) return null;
    return (await response.json()) as Record<string, unknown>;
  } catch {
    return null;
  }
}

/**
 * Write an audit event to the operator_events table using the singleton
 * Postgres pool (getPool).  Every mutation attempt — success, failure, or
 * unauthorized — writes one row.
 */
async function writeAuditEvent(params: {
  actor: string;
  action: string;
  oldState: Record<string, unknown> | null;
  newState: Record<string, unknown> | null;
  result: "success" | "failure" | "unauthorized";
  error: string | null;
}): Promise<void> {
  try {
    const pool = getPool();
    await pool.query(
      `INSERT INTO operator_events
         (actor, action, old_state, new_state, result, error)
       VALUES ($1, $2, $3, $4, $5, $6)`,
      [
        params.actor,
        params.action,
        params.oldState ? JSON.stringify(params.oldState) : null,
        params.newState ? JSON.stringify(params.newState) : null,
        params.result,
        params.error,
      ],
    );
  } catch {
    // Audit write failure must never block the HTTP response.
  }
}

/**
 * POST /api/admin/schedule/stop
 *
 * Proxies the trader's `DELETE /schedule` endpoint.  Requires a valid
 * OPERATOR_ADMIN_TOKEN.  Writes an audit event to operator_events on every
 * attempt — success, failure, or unauthorized.
 *
 * The operator token is NEVER forwarded to the trader (VAL-ADMIN-012).
 * The POST body may be empty (VAL-ADMIN-013).
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  // --- Auth gate ---
  if (!isOperatorAdminRequest(request)) {
    await writeAuditEvent({
      actor: "unknown",
      action: "stop_scheduler",
      oldState: null,
      newState: null,
      result: "unauthorized",
      error: "Missing or invalid operator token",
    });

    return NextResponse.json(
      { error: "operator_admin_required" },
      { status: 401, headers: { "Cache-Control": "no-store" } },
    );
  }

  const traderUrl = process.env.TRADER_INTERNAL_URL;
  if (!traderUrl) {
    await writeAuditEvent({
      actor: "operator_admin",
      action: "stop_scheduler",
      oldState: null,
      newState: null,
      result: "failure",
      error: "TRADER_INTERNAL_URL not configured",
    });

    return NextResponse.json(
      { error: "trader_unreachable" },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }

  // --- Capture old state before mutation ---
  const oldStatus = await fetchTraderStatus(traderUrl);
  const oldState: Record<string, unknown> | null = oldStatus
    ? { scheduler_running: oldStatus.scheduler_running }
    : null;

  // --- Proxy to trader DELETE /schedule ---
  let traderResponse: Response;
  try {
    traderResponse = await fetch(`${traderUrl}/schedule`, {
      method: "DELETE",
      headers: { Accept: "application/json" },
    });
  } catch (err) {
    const errorMessage = err instanceof Error ? err.message : "Unknown fetch error";
    await writeAuditEvent({
      actor: "operator_admin",
      action: "stop_scheduler",
      oldState,
      newState: null,
      result: "failure",
      error: errorMessage,
    });

    return NextResponse.json(
      { error: "trader_unreachable" },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }

  if (!traderResponse.ok) {
    const errorText = await traderResponse.text().catch(() => "Unknown error");
    await writeAuditEvent({
      actor: "operator_admin",
      action: "stop_scheduler",
      oldState,
      newState: null,
      result: "failure",
      error: `Trader returned HTTP ${traderResponse.status}: ${errorText}`,
    });

    return NextResponse.json(
      { error: "trader_unreachable" },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }

  // --- Capture new state after mutation ---
  const newStatus = await fetchTraderStatus(traderUrl);
  const newState: Record<string, unknown> | null = newStatus
    ? { scheduler_running: newStatus.scheduler_running }
    : null;

  // --- Write success audit event ---
  await writeAuditEvent({
    actor: "operator_admin",
    action: "stop_scheduler",
    oldState,
    newState,
    result: "success",
    error: null,
  });

  // --- Return trader response ---
  const body = await traderResponse.json();
  return NextResponse.json(body, {
    status: 200,
    headers: { "Cache-Control": "no-store" },
  });
}
