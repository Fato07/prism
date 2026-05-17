import { NextRequest, NextResponse } from "next/server";
import { z } from "zod/v4";

import { isConnectorAdminRequest } from "@/lib/connector-auth";
import { CreateMcpConnectorRequestSchema } from "@/lib/connectors";
import { getConnectorManifest, upsertMcpConnector } from "@/lib/connector-store";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<NextResponse> {
  if (!isConnectorAdminRequest(request)) {
    return NextResponse.json({ error: "connector_admin_required" }, { status: 401 });
  }
  try {
    return NextResponse.json(await getConnectorManifest(), { status: 200 });
  } catch {
    return NextResponse.json({ error: "connectors_unavailable" }, { status: 500 });
  }
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  if (!isConnectorAdminRequest(request)) {
    return NextResponse.json({ error: "connector_admin_required" }, { status: 401 });
  }
  try {
    const body = await request.json();
    const parsed = CreateMcpConnectorRequestSchema.parse(body);
    const connector = await upsertMcpConnector(parsed);
    return NextResponse.json({ connector }, { status: 201 });
  } catch (error) {
    if (error instanceof z.ZodError) {
      return NextResponse.json({ error: "invalid_connector_payload" }, { status: 400 });
    }
    return NextResponse.json({ error: "connector_save_failed" }, { status: 500 });
  }
}
