import { NextRequest, NextResponse } from "next/server";
import { clampPublicLimit, getPublicHistoryEntries } from "@/lib/public-api";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<NextResponse> {
  const limit = clampPublicLimit(request.nextUrl.searchParams.get("limit"));
  const entries = await getPublicHistoryEntries(limit);
  return NextResponse.json({
    generated_at: new Date().toISOString(),
    limit,
    entries,
  });
}
