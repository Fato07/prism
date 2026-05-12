/**
 * Database data fetching for the Prism dashboard.
 * Server-side only — reads from Neon Postgres via pg.
 */

import pg from "pg";
import {
  TraceRowSchema,
  ValidationRowSchema,
  TradeRowSchema,
  AgentRowSchema,
  type TraceRow,
  type ValidationRow,
  type TradeRow,
  type AgentRow,
} from "@/lib/schemas";

const { Pool } = pg;

/** Global pool instance (cached across server component invocations). */
let pool: pg.Pool | null = null;

function getPool(): pg.Pool {
  if (!pool) {
    const databaseUrl = process.env.DATABASE_URL;
    if (!databaseUrl) {
      throw new Error("DATABASE_URL environment variable is not set");
    }
    pool = new Pool({
      connectionString: databaseUrl,
      max: 5,
      idleTimeoutMillis: 30_000,
      connectionTimeoutMillis: 10_000,
    });
  }
  return pool;
}

/** Fetch the most recent trace from the traces table. */
export async function getLatestTrace(): Promise<TraceRow | null> {
  const client = getPool();
  const result = await client.query(
    "SELECT trace_id, agent_id::text AS agent_id, market_id, ipfs_cid, encode(content_hash, 'hex') AS content_hash, tx_hash, created_at::text AS created_at FROM traces ORDER BY created_at DESC LIMIT 1"
  );
  if (result.rows.length === 0) return null;
  // pg returns BIGINT as string, parse to number
  const row = result.rows[0];
  return TraceRowSchema.parse({ ...row, agent_id: Number(row.agent_id) });
}

/** Fetch the most recent validation for a given trace. */
export async function getLatestValidation(
  traceId?: string
): Promise<ValidationRow | null> {
  const client = getPool();
  let query: string;
  let params: string[];

  if (traceId) {
    query =
      "SELECT encode(request_hash, 'hex') AS request_hash, trace_id, sentinel_agent_id::text AS sentinel_agent_id, verdict_score, response_uri, tx_hash, created_at::text AS created_at FROM validations WHERE trace_id = $1 ORDER BY created_at DESC LIMIT 1";
    params = [traceId];
  } else {
    query =
      "SELECT encode(request_hash, 'hex') AS request_hash, trace_id, sentinel_agent_id::text AS sentinel_agent_id, verdict_score, response_uri, tx_hash, created_at::text AS created_at FROM validations ORDER BY created_at DESC LIMIT 1";
    params = [];
  }

  const result = await client.query(query, params);
  if (result.rows.length === 0) return null;
  const row = result.rows[0];
  return ValidationRowSchema.parse({ ...row, sentinel_agent_id: Number(row.sentinel_agent_id) });
}

/** Fetch the most recent trade. */
export async function getLatestTrade(): Promise<TradeRow | null> {
  const client = getPool();
  const result = await client.query(
    "SELECT order_id, trace_id, market_id, side, size::text, builder_code, status, polymarket_tx, created_at::text AS created_at FROM trades ORDER BY created_at DESC LIMIT 1"
  );
  if (result.rows.length === 0) return null;
  return TradeRowSchema.parse(result.rows[0]);
}

/** Fetch all agents. */
export async function getAgents(): Promise<AgentRow[]> {
  const client = getPool();
  const result = await client.query(
    "SELECT agent_id::text AS agent_id, role, wallet_address, agent_card_cid, registration_tx_hash, created_at::text AS created_at FROM agents ORDER BY agent_id"
  );
  return result.rows.map((row: Record<string, unknown>) =>
    AgentRowSchema.parse({ ...row, agent_id: Number(row.agent_id) })
  );
}

/** Fetch trace content from IPFS via Pinata gateway. */
export async function fetchTraceFromIPFS(
  cid: string
): Promise<Record<string, unknown> | null> {
  try {
    const url = `https://gateway.pinata.cloud/ipfs/${cid}`;
    const res = await fetch(url, { next: { revalidate: 300 } });
    if (!res.ok) return null;
    return (await res.json()) as Record<string, unknown>;
  } catch {
    return null;
  }
}

/** Fetch verdict content from IPFS via Pinata gateway. */
export async function fetchVerdictFromIPFS(
  cid: string
): Promise<Record<string, unknown> | null> {
  try {
    const url = `https://gateway.pinata.cloud/ipfs/${cid}`;
    const res = await fetch(url, { next: { revalidate: 300 } });
    if (!res.ok) return null;
    return (await res.json()) as Record<string, unknown>;
  } catch {
    return null;
  }
}

/** Close the pool (for testing / shutdown). */
export async function closePool(): Promise<void> {
  if (pool) {
    await pool.end();
    pool = null;
  }
}
