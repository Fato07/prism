/**
 * POST /api/validate/initiate — Start the MCP + x402 validation flow.
 *
 * Does the MCP handshake (initialize + notifications/initialized) and
 * sends an unpaid tools/call to the sentinel. The sentinel's x402
 * middleware intercepts the request and returns HTTP 402 with payment
 * requirements. This route extracts those requirements and returns
 * them to the client along with the MCP session ID.
 *
 * The client then signs the EIP-3009 payment and calls
 * /api/validate/confirm to complete the flow.
 */

import { NextResponse } from "next/server";

/* ─────────────── Config ─────────────── */

const SENTINEL_MCP_URL = process.env.SENTINEL_MCP_URL
  || (process.env.SENTINEL_BASE_URL
    ? `${process.env.SENTINEL_BASE_URL.replace(/\/+$/, "")}/mcp/`
    : "");

if (!SENTINEL_MCP_URL) {
  // Soft warning — route will return 503 at runtime if URL is unset
}

/* ─────────────── JSON-RPC helpers ─────────────── */

function makeInitializeBody(): Record<string, unknown> {
  return {
    jsonrpc: "2.0",
    id: 0,
    method: "initialize",
    params: {
      protocolVersion: "2025-06-18",
      capabilities: { experimental: {}, sampling: {} },
      clientInfo: {
        name: "prism-dashboard-submit",
        version: "0.1.0",
      },
    },
  };
}

function makeInitializedNotification(): Record<string, unknown> {
  return {
    jsonrpc: "2.0",
    method: "notifications/initialized",
  };
}

function makeToolsCallBody(
  traceUri: string,
  traceHash: string,
): Record<string, unknown> {
  return {
    jsonrpc: "2.0",
    id: 1,
    method: "tools/call",
    params: {
      name: "validate",
      arguments: {
        trace_uri: traceUri,
        trace_hash: traceHash,
      },
    },
  };
}

const BASE_HEADERS: Record<string, string> = {
  "Content-Type": "application/json",
  Accept: "application/json, text/event-stream",
};

/* ─────────────── Response types ─────────────── */

export interface InitiateSuccessResponse {
  sessionId: string;
  paymentRequirements: {
    amount: string;
    asset: string;
    scheme: string;
    network: string;
    recipient: string;
    facilitator?: string;
  };
}

export interface InitiateErrorResponse {
  error: string;
  detail?: string;
}

/* ─────────────── POST handler ─────────────── */

export async function POST(request: Request): Promise<NextResponse> {
  if (!SENTINEL_MCP_URL) {
    return NextResponse.json<InitiateErrorResponse>(
      { error: "Sentinel endpoint not configured" },
      { status: 503 },
    );
  }

  // Parse request body
  let traceUri: string;
  let traceHash: string;

  try {
    const body = (await request.json()) as { traceUri?: string; traceHash?: string };
    if (!body.traceUri || typeof body.traceUri !== "string") {
      return NextResponse.json<InitiateErrorResponse>(
        { error: "traceUri is required" },
        { status: 400 },
      );
    }
    if (!body.traceHash || typeof body.traceHash !== "string") {
      return NextResponse.json<InitiateErrorResponse>(
        { error: "traceHash is required" },
        { status: 400 },
      );
    }
    traceUri = body.traceUri;
    traceHash = body.traceHash;
  } catch {
    return NextResponse.json<InitiateErrorResponse>(
      { error: "Invalid JSON body" },
      { status: 400 },
    );
  }

  const timeoutMs = 30_000;

  try {
    // Step 1: MCP initialize handshake
    const initResp = await fetch(SENTINEL_MCP_URL, {
      method: "POST",
      headers: BASE_HEADERS,
      body: JSON.stringify(makeInitializeBody()),
      signal: AbortSignal.timeout(timeoutMs),
    });

    if (initResp.status !== 200) {
      const text = await initResp.text().catch(() => "");
      return NextResponse.json<InitiateErrorResponse>(
        { error: "MCP handshake failed", detail: text.slice(0, 200) },
        { status: 502 },
      );
    }

    const sessionId = initResp.headers.get("mcp-session-id");
    if (!sessionId) {
      return NextResponse.json<InitiateErrorResponse>(
        { error: "MCP server did not issue a session ID" },
        { status: 502 },
      );
    }

    // Step 2: notifications/initialized
    const notifResp = await fetch(SENTINEL_MCP_URL, {
      method: "POST",
      headers: { ...BASE_HEADERS, "mcp-session-id": sessionId },
      body: JSON.stringify(makeInitializedNotification()),
      signal: AbortSignal.timeout(timeoutMs),
    });

    if (notifResp.status !== 200 && notifResp.status !== 202) {
      const text = await notifResp.text().catch(() => "");
      return NextResponse.json<InitiateErrorResponse>(
        { error: "MCP notification rejected", detail: text.slice(0, 200) },
        { status: 502 },
      );
    }

    // Step 3: Unpaid tools/call → expect 402
    const toolsResp = await fetch(SENTINEL_MCP_URL, {
      method: "POST",
      headers: { ...BASE_HEADERS, "mcp-session-id": sessionId },
      body: JSON.stringify(makeToolsCallBody(traceUri, traceHash)),
      signal: AbortSignal.timeout(timeoutMs),
    });

    if (toolsResp.status !== 402) {
      // If not 402, something unexpected happened
      const text = await toolsResp.text().catch(() => "");
      return NextResponse.json<InitiateErrorResponse>(
        {
          error: toolsResp.status === 200
            ? "Sentinel accepted without payment — unexpected"
            : `Unexpected sentinel response: ${toolsResp.status}`,
          detail: text.slice(0, 200),
        },
        { status: 502 },
      );
    }

    // Parse the 402 JSON-RPC error envelope to extract payment requirements
    const body402 = (await toolsResp.json()) as {
      error?: {
        data?: {
          amount?: string;
          asset?: string;
          scheme?: string;
          network?: string;
          recipient?: string;
          facilitator?: string;
        };
      };
    };

    const paymentData = body402?.error?.data;
    if (!paymentData?.amount || !paymentData?.recipient) {
      return NextResponse.json<InitiateErrorResponse>(
        { error: "Could not parse payment requirements from sentinel" },
        { status: 502 },
      );
    }

    return NextResponse.json<InitiateSuccessResponse>({
      sessionId,
      paymentRequirements: {
        amount: paymentData.amount,
        asset: paymentData.asset ?? "USDC",
        scheme: paymentData.scheme ?? "exact",
        network: paymentData.network ?? "base-sepolia",
        recipient: paymentData.recipient,
        facilitator: paymentData.facilitator,
      },
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Unknown error";
    if (message.includes("timeout") || message.includes("abort")) {
      return NextResponse.json<InitiateErrorResponse>(
        { error: "Sentinel is not responding. Try again in a minute." },
        { status: 504 },
      );
    }
    return NextResponse.json<InitiateErrorResponse>(
      { error: "Failed to reach sentinel", detail: message },
      { status: 502 },
    );
  }
}
