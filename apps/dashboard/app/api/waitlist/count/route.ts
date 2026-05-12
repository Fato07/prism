/**
 * GET /api/waitlist/count — Return the current waitlist sign-up count.
 *
 * Returns { count: number } — non-negative integer.
 */

import { NextResponse } from "next/server";
import { ensureWaitlistTable, getWaitlistCount } from "@/lib/db";

export async function GET(): Promise<NextResponse> {
  try {
    // Ensure table exists before querying
    await ensureWaitlistTable();

    const count = await getWaitlistCount();

    return NextResponse.json({ count }, { status: 200 });
  } catch (error: unknown) {
    console.error("Waitlist count error:", error);
    return NextResponse.json(
      { count: 0 },
      { status: 200 }
    );
  }
}
