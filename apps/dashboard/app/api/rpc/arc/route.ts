/**
 * POST /api/rpc/arc — Server-side proxy for Arc Testnet RPC.
 *
 * The Arc Testnet RPC endpoint does not support CORS (returns 405 on
 * OPTIONS, no Access-Control-Allow-Origin). This proxy lets the
 * browser-side wagmi client call the RPC through a same-origin route,
 * bypassing CORS entirely.
 *
 * The RPC URL is read from the server-side ARC_RPC_URL env var
 * (preferred) or falls back to NEXT_PUBLIC_ARC_RPC_URL.
 */

import { NextRequest, NextResponse } from "next/server";

const ARC_RPC_URL =
  process.env.ARC_RPC_URL ?? process.env.NEXT_PUBLIC_ARC_RPC_URL!;

export async function POST(req: NextRequest): Promise<NextResponse> {
  const body = await req.json();
  const response = await fetch(ARC_RPC_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  return NextResponse.json(data);
}
