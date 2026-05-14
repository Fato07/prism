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

/** IPFS gateway — configurable via IPFS_GATEWAY env var. Defaults to ipfs.io (Pinata public gateway is rate-limited). */
const IPFS_GATEWAY = process.env.IPFS_GATEWAY || "https://ipfs.io/ipfs";

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

/** Fetch a trace by its ID. */
export async function getTraceById(
  traceId: string
): Promise<TraceRow | null> {
  const client = getPool();
  const result = await client.query(
    "SELECT trace_id, agent_id::text AS agent_id, market_id, ipfs_cid, encode(content_hash, 'hex') AS content_hash, tx_hash, created_at::text AS created_at FROM traces WHERE trace_id = $1",
    [traceId]
  );
  if (result.rows.length === 0) return null;
  const row = result.rows[0];
  return TraceRowSchema.parse({ ...row, agent_id: Number(row.agent_id) });
}

/**
 * Fetch the latest trace that has a corresponding validation.
 * Falls back to the latest trace if no validations exist.
 */
export async function getLatestValidatedTrace(): Promise<{
  trace: TraceRow;
  validation: ValidationRow;
} | null> {
  const client = getPool();
  const result = await client.query(
    `SELECT t.trace_id, t.agent_id::text AS agent_id, t.market_id, t.ipfs_cid,
            encode(t.content_hash, 'hex') AS content_hash, t.tx_hash, t.created_at::text AS created_at,
            encode(v.request_hash, 'hex') AS v_request_hash, v.sentinel_agent_id::text AS v_sentinel_agent_id,
            v.verdict_score, v.response_uri, v.tx_hash AS v_tx_hash, v.created_at::text AS v_created_at
     FROM traces t
     JOIN validations v ON v.trace_id = t.trace_id
     ORDER BY v.created_at DESC
     LIMIT 1`
  );
  if (result.rows.length === 0) return null;
  const row = result.rows[0];
  const trace = TraceRowSchema.parse({
    trace_id: row.trace_id,
    agent_id: Number(row.agent_id),
    market_id: row.market_id,
    ipfs_cid: row.ipfs_cid,
    content_hash: row.content_hash,
    tx_hash: row.tx_hash,
    created_at: row.created_at,
  });
  const validation = ValidationRowSchema.parse({
    request_hash: row.v_request_hash,
    trace_id: row.trace_id,
    sentinel_agent_id: Number(row.v_sentinel_agent_id),
    verdict_score: row.verdict_score,
    response_uri: row.response_uri,
    tx_hash: row.v_tx_hash,
    created_at: row.v_created_at,
  });
  return { trace, validation };
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

/** Fetch trace content from IPFS via configurable gateway. */
export async function fetchTraceFromIPFS(
  cid: string
): Promise<Record<string, unknown> | null> {
  try {
    const url = `${IPFS_GATEWAY}/${cid}`;
    const res = await fetch(url, { next: { revalidate: 300 } });
    if (!res.ok) {
      console.error(`[db] fetchTraceFromIPFS: ${res.status} for CID ${cid} via ${IPFS_GATEWAY}`);
      return null;
    }
    return (await res.json()) as Record<string, unknown>;
  } catch (err) {
    console.error(`[db] fetchTraceFromIPFS: failed for CID ${cid}`, err);
    return null;
  }
}

/** Fetch verdict content from IPFS via configurable gateway. */
export async function fetchVerdictFromIPFS(
  cid: string
): Promise<Record<string, unknown> | null> {
  try {
    const url = `${IPFS_GATEWAY}/${cid}`;
    const res = await fetch(url, { next: { revalidate: 300 } });
    if (!res.ok) {
      console.error(`[db] fetchVerdictFromIPFS: ${res.status} for CID ${cid} via ${IPFS_GATEWAY}`);
      return null;
    }
    return (await res.json()) as Record<string, unknown>;
  } catch (err) {
    console.error(`[db] fetchVerdictFromIPFS: failed for CID ${cid}`, err);
    return null;
  }
}

/** Add an email to the waitlist. Returns true if newly inserted, false if already exists. */
export async function addWaitlistEmail(email: string): Promise<{ inserted: boolean }> {
  const client = getPool();
  const result = await client.query(
    `INSERT INTO waitlist (email) VALUES ($1) ON CONFLICT (email) DO NOTHING`,
    [email]
  );
  return { inserted: result.rowCount !== null && result.rowCount > 0 };
}

/** Get the current waitlist count. */
export async function getWaitlistCount(): Promise<number> {
  const client = getPool();
  const result = await client.query("SELECT count(*) AS count FROM waitlist");
  return Number(result.rows[0].count);
}

/**
 * Aggregate activity stats for the landing-page live strip.
 * All counts are pure reads; safe to call from a server component on every render.
 * Returns zeros if any table is missing or unreachable so the landing page never fails.
 */
export interface ActivityStats {
  traces: number;
  validations: number;
  trades: number;
  flagged: number; // verdict_score < 50
}

export interface VerdictHistoryEntry {
  trace_id: string;
  request_hash: string;
  verdict_score: number;
  created_at: string;
}

/**
 * Recent verdicts for the dashboard history strip.
 * Returned newest-first; defaults to 30 entries. Empty array on any DB error.
 */
export async function getRecentVerdicts(
  limit: number = 30,
): Promise<VerdictHistoryEntry[]> {
  try {
    const client = getPool();
    const result = await client.query(
      `SELECT trace_id,
              encode(request_hash, 'hex') AS request_hash,
              verdict_score,
              created_at::text AS created_at
         FROM validations
        ORDER BY created_at DESC
        LIMIT $1`,
      [Math.max(1, Math.min(100, limit))],
    );
    return result.rows.map((r: Record<string, unknown>) => ({
      trace_id: String(r.trace_id),
      request_hash: String(r.request_hash),
      verdict_score: Number(r.verdict_score),
      created_at: String(r.created_at),
    }));
  } catch {
    return [];
  }
}

export async function getActivityStats(): Promise<ActivityStats> {
  try {
    const client = getPool();
    const result = await client.query(
      `SELECT
         (SELECT count(*) FROM traces)                                          AS traces,
         (SELECT count(*) FROM validations)                                     AS validations,
         (SELECT count(*) FROM trades)                                          AS trades,
         (SELECT count(*) FROM validations WHERE verdict_score < 50)            AS flagged`
    );
    const row = result.rows[0] ?? {};
    return {
      traces: Number(row.traces ?? 0),
      validations: Number(row.validations ?? 0),
      trades: Number(row.trades ?? 0),
      flagged: Number(row.flagged ?? 0),
    };
  } catch {
    return { traces: 0, validations: 0, trades: 0, flagged: 0 };
  }
}

/** Ensure the waitlist table exists (idempotent migration). */
export async function ensureWaitlistTable(): Promise<void> {
  const client = getPool();
  await client.query(`
    CREATE TABLE IF NOT EXISTS waitlist (
      id SERIAL PRIMARY KEY,
      email TEXT NOT NULL UNIQUE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
  `);
}

/** Fetch a trade by its trace_id. */
export async function getTradeByTraceId(
  traceId: string
): Promise<TradeRow | null> {
  const client = getPool();
  const result = await client.query(
    "SELECT order_id, trace_id, market_id, side, size::text, builder_code, status, polymarket_tx, created_at::text AS created_at FROM trades WHERE trace_id = $1 ORDER BY created_at DESC LIMIT 1",
    [traceId]
  );
  if (result.rows.length === 0) return null;
  return TradeRowSchema.parse(result.rows[0]);
}

/** Comprehensive data bundle for the trace detail page. */
export interface TraceDetailData {
  trace: TraceRow;
  validation: ValidationRow | null;
  trade: TradeRow | null;
  traderAgent: AgentRow | null;
  sentinelAgent: AgentRow | null;
  /** IPFS-fetched trace content (Trading-R1 structured data). */
  traceContent: Record<string, unknown> | null;
  /** IPFS-fetched verdict content (SentinelVerdict structured data). */
  verdictContent: Record<string, unknown> | null;
}

/** Extract a CID from an ipfs:// URI. Returns the raw string otherwise. */
function extractCid(uri: string): string | null {
  if (uri.startsWith("ipfs://")) return uri.slice(7);
  if (/^(Qm[1-9A-HJ-NP-Za-km-z]{44}|baf[ya][a-z2-7]{40,})$/.test(uri))
    return uri;
  return null;
}

/**
 * Fetch all data needed for the /trace/[id] detail page in one call.
 * Returns null if the trace doesn't exist (caller should return notFound()).
 */
export async function getTraceDetailData(
  traceId: string
): Promise<TraceDetailData | null> {
  const trace = await getTraceById(traceId);
  if (!trace) return null;

  const [validation, trade, agents] = await Promise.all([
    getLatestValidation(traceId),
    getTradeByTraceId(traceId),
    getAgents(),
  ]);

  const [traceContent, verdictContent] = await Promise.all([
    trace.ipfs_cid
      ? fetchTraceFromIPFS(trace.ipfs_cid)
      : Promise.resolve(null),
    validation?.response_uri
      ? fetchVerdictFromIPFS(extractCid(validation.response_uri) ?? validation.response_uri)
      : Promise.resolve(null),
  ]);

  const traderAgent =
    agents.find((a) => a.agent_id === trace.agent_id) ?? null;
  const sentinelAgent = validation
    ? agents.find((a) => a.agent_id === validation.sentinel_agent_id) ?? null
    : null;

  return {
    trace,
    validation,
    trade,
    traderAgent,
    sentinelAgent,
    traceContent,
    verdictContent,
  };
}

/** Close the pool (for testing / shutdown). */
export async function closePool(): Promise<void> {
  if (pool) {
    await pool.end();
    pool = null;
  }
}
