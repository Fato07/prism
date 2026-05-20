import { NextRequest, NextResponse } from "next/server";

import { isOperatorAdminRequest } from "@/lib/operator-auth";

export const dynamic = "force-dynamic";

/**
 * GET /api/admin/runtime
 *
 * Proxies the trader's `GET /status` endpoint.  Requires a valid
 * OPERATOR_ADMIN_TOKEN (via `Authorization: Bearer` or `X-Prism-Admin-Token`
 * header).  Returns the full 8‑field status object on success, HTTP 401 when
 * the token is missing or wrong, and HTTP 502 when the trader is unreachable.
 *
 * This route has **zero side effects** — it never starts or stops the
 * scheduler and never mutates any state.
 */
export async function GET(request: NextRequest): Promise<NextResponse> {
  if (!isOperatorAdminRequest(request)) {
    return NextResponse.json(
      { error: "operator_admin_required" },
      {
        status: 401,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }

  const traderUrl = process.env.TRADER_INTERNAL_URL;
  if (!traderUrl) {
    return NextResponse.json(
      { error: "trader_unreachable" },
      {
        status: 502,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }

  try {
    const response = await fetch(`${traderUrl}/status`, {
      method: "GET",
      headers: { Accept: "application/json" },
    });

    if (!response.ok) {
      return NextResponse.json(
        { error: "trader_unreachable" },
        {
          status: 502,
          headers: { "Cache-Control": "no-store" },
        },
      );
    }

    const body = await response.json();
    return NextResponse.json(body, {
      status: 200,
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return NextResponse.json(
      { error: "trader_unreachable" },
      {
        status: 502,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }
}
