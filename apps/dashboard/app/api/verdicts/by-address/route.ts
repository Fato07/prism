/**
 * GET /api/verdicts/by-address?address=0x...
 *
 * Returns verdicts where validations.requester_address matches the given
 * address (case-insensitive). Response shape mirrors HistoryEntry from
 * getHistoryEntries so /me can reuse the same card component as /history.
 *
 * VAL-APIVERDICTS-001..007
 */

import { NextRequest, NextResponse } from "next/server";
import { getVerdictsByAddress } from "@/lib/db";
import type { HistoryEntry } from "@/lib/db";

/** EIP-55-like hex address pattern: 0x followed by exactly 40 hex chars. */
const ADDRESS_REGEX = /^0x[a-fA-F0-9]{40}$/;

interface ErrorResponse {
  error: string;
}

export async function GET(
  request: NextRequest,
): Promise<NextResponse<HistoryEntry[] | ErrorResponse>> {
  const { searchParams } = request.nextUrl;
  const address = searchParams.get("address");

  // VAL-APIVERDICTS-003: missing address → 400
  if (!address) {
    return NextResponse.json(
      { error: "address required" },
      { status: 400 },
    );
  }

  // VAL-APIVERDICTS-003: invalid address format → 400
  if (!ADDRESS_REGEX.test(address)) {
    return NextResponse.json(
      { error: "invalid address" },
      { status: 400 },
    );
  }

  try {
    // VAL-APIVERDICTS-002 + VAL-APIVERDICTS-004: case-insensitive lookup
    const verdicts = await getVerdictsByAddress(address.toLowerCase());

    // VAL-APIVERDICTS-005: shape mirrors HistoryEntry / getRecentVerdicts
    // VAL-APIVERDICTS-006: no secrets leaked (only DB-derived fields)
    return NextResponse.json(verdicts, { status: 200 });
  } catch (err: unknown) {
    // Never expose raw pg/psycopg error details to the client
    console.error("[by-address] DB query failed:", err);
    return NextResponse.json(
      { error: "internal server error" },
      { status: 500 },
    );
  }
}
