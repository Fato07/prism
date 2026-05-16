import { NextRequest, NextResponse } from "next/server";
import { getPublicTraceReport } from "@/lib/public-api";

export const dynamic = "force-dynamic";

interface RouteContext {
  params: Promise<{ id: string }>;
}

export async function GET(
  _request: NextRequest,
  context: RouteContext,
): Promise<NextResponse> {
  const { id } = await context.params;
  const report = await getPublicTraceReport(id);
  if (!report) {
    return NextResponse.json({ error: "trace_not_found" }, { status: 404 });
  }
  return NextResponse.json(report);
}
