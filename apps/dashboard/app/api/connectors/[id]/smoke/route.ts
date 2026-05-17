import { NextResponse } from "next/server";

import { isConnectorAdminRequest } from "@/lib/connector-auth";
import { ConnectorStoreError, smokeConnector } from "@/lib/connector-store";

export const dynamic = "force-dynamic";

interface RouteContext {
  params: Promise<{ id: string }>;
}

export async function POST(request: Request, context: RouteContext): Promise<NextResponse> {
  if (!isConnectorAdminRequest(request)) {
    return NextResponse.json({ error: "connector_admin_required" }, { status: 401 });
  }
  const { id } = await context.params;
  try {
    const connector = await smokeConnector(id);
    return NextResponse.json({ connector }, { status: 200 });
  } catch (error) {
    if (error instanceof ConnectorStoreError && error.code === "connector_not_found") {
      return NextResponse.json({ error: "connector_not_found" }, { status: 404 });
    }
    return NextResponse.json({ error: "connector_smoke_failed" }, { status: 500 });
  }
}
