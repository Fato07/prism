import { NextResponse } from "next/server";
import { getStatsData } from "@/lib/stats";

export const dynamic = "force-dynamic";

export async function GET(): Promise<NextResponse> {
  const stats = await getStatsData();
  return NextResponse.json({
    generated_at: new Date().toISOString(),
    stats,
  });
}
