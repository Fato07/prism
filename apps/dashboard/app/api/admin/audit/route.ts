import { NextRequest, NextResponse } from "next/server";

import { isOperatorAdminRequest } from "@/lib/operator-auth";
import { getPool } from "@/lib/db";

export const dynamic = "force-dynamic";

/** Default number of events returned when no limit is specified. */
const DEFAULT_LIMIT = 50;

/** Maximum number of events that may be requested. */
const MAX_LIMIT = 200;

/**
 * GET /api/admin/audit
 *
 * Returns recent audit events from the operator_events table, ordered by
 * timestamp DESC (newest first).  Requires a valid OPERATOR_ADMIN_TOKEN.
 *
 * Query parameters:
 *   - `limit` (optional): number of events to return (1–200, default 50).
 *
 * Response: `{ events: OperatorEventRow[] }`
 */
export async function GET(request: NextRequest): Promise<NextResponse> {
  // --- Auth gate ---
  if (!isOperatorAdminRequest(request)) {
    return NextResponse.json(
      { error: "operator_admin_required" },
      { status: 401, headers: { "Cache-Control": "no-store" } },
    );
  }

  // --- Parse and clamp limit ---
  const url = new URL(request.url);
  const rawLimit = url.searchParams.get("limit");
  let limit = DEFAULT_LIMIT;
  if (rawLimit !== null) {
    const parsed = Number.parseInt(rawLimit, 10);
    if (!Number.isNaN(parsed)) {
      limit = Math.max(1, Math.min(MAX_LIMIT, parsed));
    }
  }

  // --- Query operator_events ---
  try {
    const pool = getPool();
    const result = await pool.query(
      `SELECT id::text AS id,
              actor,
              action,
              old_state,
              new_state,
              timestamp::text AS timestamp,
              result,
              error
         FROM operator_events
        ORDER BY timestamp DESC
        LIMIT $1`,
      [limit],
    );

    return NextResponse.json(
      { events: result.rows },
      {
        status: 200,
        headers: { "Cache-Control": "no-store" },
      },
    );
  } catch (err) {
    // Return empty events on DB error — operator page degrades gracefully
    console.error("[audit] Failed to query operator_events:", err);
    return NextResponse.json(
      { events: [] },
      {
        status: 200,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }
}
