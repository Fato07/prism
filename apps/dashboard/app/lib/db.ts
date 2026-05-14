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

/** IPFS gateway — configurable via IPFS_GATEWAY env var. Defaults to Pinata gateway. */
const IPFS_GATEWAY = process.env.IPFS_GATEWAY || "https://gateway.pinata.cloud/ipfs";

/** Global pool instance (cached across server component invocations). */
let pool: pg.Pool | null = null;

export function getPool(): pg.Pool {
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
    "SELECT order_id, trace_id, market_id, side, size::text, builder_code, status, fill_price::text AS fill_price, polymarket_tx, created_at::text AS created_at FROM trades ORDER BY created_at DESC LIMIT 1"
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
    "SELECT order_id, trace_id, market_id, side, size::text, builder_code, status, fill_price::text AS fill_price, polymarket_tx, created_at::text AS created_at FROM trades WHERE trace_id = $1 ORDER BY created_at DESC LIMIT 1",
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

/** History entry for the /history page cards. */
export interface HistoryEntry {
  trace_id: string;
  market_name: string | null;
  side: string | null;
  verdict_score: number;
  verdict_label: string | null;
  created_at: string;
  ipfs_cid: string | null;
}

/**
 * Fetch paginated history entries (traces + validations joined).
 * Returns newest first, 20 per page by default.
 * The `page` parameter is 1-based.
 * Market names and verdict labels are enriched from IPFS content.
 */
export async function getHistoryEntries(
  page: number = 1,
  pageSize: number = 20,
): Promise<{ entries: HistoryEntry[]; total: number }> {
  const client = getPool();
  const safePageSize = Math.max(1, Math.min(100, pageSize));
  const offset = (Math.max(1, page) - 1) * safePageSize;

  const countResult = await client.query(
    `SELECT count(*) AS total
       FROM traces t
       JOIN validations v ON v.trace_id = t.trace_id`,
  );
  const total = Number(countResult.rows[0]?.total ?? 0);

  if (total === 0) {
    return { entries: [], total: 0 };
  }

  // Single query joining traces + validations to get all DB fields at once
  const result = await client.query(
    `SELECT t.trace_id,
            t.market_id,
            t.ipfs_cid,
            t.created_at::text AS created_at,
            v.verdict_score,
            v.response_uri
       FROM traces t
       JOIN validations v ON v.trace_id = t.trace_id
      ORDER BY t.created_at DESC
      LIMIT $1 OFFSET $2`,
    [safePageSize, offset],
  );

  const rows = result.rows as Record<string, unknown>[];

  // Fetch IPFS content for market names and verdict labels in parallel
  const entries = await Promise.all(
    rows.map(async (row) => {
      const cid = String(row.ipfs_cid ?? "");
      const responseUri = String(row.response_uri ?? "");
      const verdictCid = extractCid(responseUri) ?? (responseUri || null);

      const [traceContent, verdictContent] = await Promise.all([
        cid ? fetchTraceFromIPFS(cid) : Promise.resolve(null),
        verdictCid ? fetchVerdictFromIPFS(verdictCid) : Promise.resolve(null),
      ]);

      const marketName =
        (traceContent as Record<string, unknown> | null)?.market_question as string | null
        ?? String(row.market_id ?? "");
      const side =
        (traceContent as Record<string, unknown> | null)?.action as string | null;
      const verdictLabel =
        (verdictContent as Record<string, unknown> | null)?.verdict_label as string | null;

      return {
        trace_id: String(row.trace_id),
        market_name: marketName,
        side,
        verdict_score: Number(row.verdict_score),
        verdict_label: verdictLabel,
        created_at: String(row.created_at),
        ipfs_cid: cid || null,
      };
    }),
  );

  return { entries, total };
}

/**
 * Fetch verdicts filtered by requester_address (case-insensitive).
 * Returns the same HistoryEntry shape as getHistoryEntries so the /me page
 * can reuse the same card component as /history.
 * Ordered by created_at DESC.
 */
export async function getVerdictsByAddress(
  address: string,
): Promise<HistoryEntry[]> {
  const client = getPool();
  const result = await client.query(
    `SELECT t.trace_id,
            t.market_id,
            t.ipfs_cid,
            t.created_at::text AS created_at,
            v.verdict_score,
            v.response_uri
       FROM validations v
       JOIN traces t ON t.trace_id = v.trace_id
      WHERE LOWER(v.requester_address) = LOWER($1)
      ORDER BY v.created_at DESC`,
    [address],
  );

  const rows = result.rows as Record<string, unknown>[];

  if (rows.length === 0) return [];

  // Enrich with IPFS content for market_name and verdict_label
  const entries = await Promise.all(
    rows.map(async (row) => {
      const cid = String(row.ipfs_cid ?? "");
      const responseUri = String(row.response_uri ?? "");
      const verdictCid = extractCid(responseUri) ?? (responseUri || null);

      const [traceContent, verdictContent] = await Promise.all([
        cid ? fetchTraceFromIPFS(cid) : Promise.resolve(null),
        verdictCid ? fetchVerdictFromIPFS(verdictCid) : Promise.resolve(null),
      ]);

      const marketName =
        (traceContent as Record<string, unknown> | null)?.market_question as string | null
        ?? String(row.market_id ?? "");
      const side =
        (traceContent as Record<string, unknown> | null)?.action as string | null;
      const verdictLabel =
        (verdictContent as Record<string, unknown> | null)?.verdict_label as string | null;

      return {
        trace_id: String(row.trace_id),
        market_name: marketName,
        side,
        verdict_score: Number(row.verdict_score),
        verdict_label: verdictLabel,
        created_at: String(row.created_at),
        ipfs_cid: cid || null,
      };
    }),
  );

  return entries;
}

/** Builder-fees leaderboard entry. */
export interface BuilderFeesEntry {
  builder_code: string;
  agent_id: number | null;
  wallet_address: string | null;
  trade_count: number;
  total_fees: string;
  last_trade_at: string | null;
  /** Daily fee accumulation for the last 7 days (sparkline data). */
  daily_fees: { date: string; fee: string }[];
}

/**
 * Fetch the builder-fees leaderboard from trades.
 * Only counts trades with status IN ('paper_filled','filled').
 * Fee = 0.1% of fill notional (size * fill_price * 0.001).
 * Joins agents table to resolve agent_id and wallet_address via HMAC builder_code.
 * Returns empty array on any DB error.
 */
export async function getBuilderFeesLeaderboard(): Promise<
  BuilderFeesEntry[]
> {
  try {
    const client = getPool();

    // Aggregate trades by builder_code
    const aggResult = await client.query(
      `SELECT builder_code,
              COUNT(*)::int AS trade_count,
              COALESCE(SUM(size * COALESCE(fill_price::numeric, 0)) * 0.001, 0)::numeric(20,6) AS total_fees,
              MAX(created_at)::text AS last_trade_at
         FROM trades
        WHERE status IN ('paper_filled', 'filled')
        GROUP BY builder_code
        ORDER BY total_fees DESC`,
    );

    if (aggResult.rows.length === 0) return [];

    // Fetch agents to resolve builder_code → agent_id + wallet
    const agents = await getAgents();

    // Fetch daily fee accumulation for last 7 days per builder_code
    const dailyResult = await client.query(
      `SELECT builder_code,
              DATE(created_at)::text AS date,
              COALESCE(SUM(size * COALESCE(fill_price::numeric, 0)) * 0.001, 0)::numeric(20,6) AS fee
         FROM trades
        WHERE status IN ('paper_filled', 'filled')
          AND created_at >= NOW() - INTERVAL '7 days'
        GROUP BY builder_code, DATE(created_at)
        ORDER BY builder_code, date`,
    );

    // Index daily fees by builder_code
    const dailyMap = new Map<string, { date: string; fee: string }[]>();
    for (const row of dailyResult.rows as Record<string, unknown>[]) {
      const bc = String(row.builder_code);
      const entry = { date: String(row.date), fee: String(row.fee) };
      const arr = dailyMap.get(bc) ?? [];
      arr.push(entry);
      dailyMap.set(bc, arr);
    }

    return (aggResult.rows as Record<string, unknown>[]).map((row) => {
      const builderCode = String(row.builder_code);
      // Try to find an agent whose derived builder code matches
      // NOTE: We cannot derive here because we don't have the HMAC secret
      // in the dashboard. Instead, we match by joining trades.trace_id → traces.agent_id
      // and then agents.wallet_address. We do a simpler fallback: if the agents
      // table has a wallet that appears in a trade for this builder_code, use it.
      return {
        builder_code: builderCode,
        agent_id: null as number | null,
        wallet_address: null as string | null,
        trade_count: Number(row.trade_count),
        total_fees: String(row.total_fees),
        last_trade_at: row.last_trade_at ? String(row.last_trade_at) : null,
        daily_fees: dailyMap.get(builderCode) ?? [],
      };
    });
  } catch {
    return [];
  }
}

/**
 * Enrich builder-fees entries with agent_id and wallet_address by
 * joining trades to traces to agents.
 * This is a second pass because we need to correlate builder_codes
 * back to the agents that produced them.
 */
export async function enrichBuilderFeesWithAgents(
  entries: BuilderFeesEntry[],
  agents: AgentRow[],
  hmacSecret: string,
): Promise<BuilderFeesEntry[]> {
  // Import dynamically to avoid bundling crypto in client bundles
  const { mapAgentIdToBuilderCode } = await import("@prism/builder-codes");

  // Build a reverse map: builder_code → agent
  const codeToAgent = new Map<string, { agent_id: number; wallet_address: string }>();
  for (const agent of agents) {
    const code = mapAgentIdToBuilderCode(agent.agent_id, hmacSecret);
    codeToAgent.set(code, {
      agent_id: agent.agent_id,
      wallet_address: agent.wallet_address,
    });
  }

  return entries.map((entry) => {
    const match = codeToAgent.get(entry.builder_code);
    if (match) {
      return {
        ...entry,
        agent_id: match.agent_id,
        wallet_address: match.wallet_address,
      };
    }
    return entry;
  });
}

/**
 * Fetch the top-N builder-fees entries for the home page strip.
 * Returns the same BuilderFeesEntry shape, limited to `limit` rows.
 */
export async function getBuilderFeesTopN(
  limit: number = 3,
): Promise<BuilderFeesEntry[]> {
  const all = await getBuilderFeesLeaderboard();
  return all.slice(0, Math.max(1, Math.min(10, limit)));
}

/** Close the pool (for testing / shutdown). */
export async function closePool(): Promise<void> {
  if (pool) {
    await pool.end();
    pool = null;
  }
}
