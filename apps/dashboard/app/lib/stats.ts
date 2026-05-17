/**
 * Shared stats data source for /stats page and <LiveActivityStrip>.
 *
 * Single source of truth — both surfaces read from the same Neon queries
 * so their numbers always reconcile (VAL-CROSS-010, VAL-WIDGETS-003).
 *
 * Uses the shared pg.Pool singleton from lib/db.ts — no duplicate connections.
 *
 * All queries are optimised with existing indexes:
 *   - validations_requester_idx on (requester_address)
 *   - traces/validations PKs on trace_id
 *   - Primary key lookups for JOINs
 */

import { getPool, closePool } from "@/lib/db";

/** Agent wallet addresses to exclude from "External x402 calls" metric. */
const INTERNAL_WALLET_ADDRESSES = [
  "0xc960833ee26e23ca01dfc4d217a8942ea78b452b", // trader
  "0x56509b03e85f3cbae5ba2190ee99b945d2f0ac36", // sentinel
] as const;

/* ─────────────── Tile data types ─────────────── */

export interface DailyCount {
  date: string;
  count: number;
}

export interface DailyFee {
  date: string;
  fee: string;
}

export interface DailyAvg {
  date: string;
  avg: number;
}

export interface DailyLatency {
  date: string;
  /** Average latency in seconds for that day. */
  avgSeconds: number;
}

export interface DailyCalibrationGap {
  date: string;
  /** Calibration gap (good_avg − bad_avg) for that day. */
  gap: number;
}

export interface VerdictBucket {
  /** Bucket label, e.g. "0–25". */
  label: string;
  /** Numeric lower bound of the bucket. */
  lower: number;
  /** Count of verdicts in this bucket. */
  count: number;
}

export interface StatsData {
  /** Total adversarial verdicts produced. */
  verdictsIssued: number;
  /** Distinct external wallets that requested validations. */
  uniqueWallets: number;
  /** Total traces in the system. */
  tracesValidated: number;
  /** Traces with both validationRequest + validationResponse anchored on-chain. */
  onChainAnchors: number;
  /** Total builder fees attributed when fill-price data is present (0.1% of fill notional). */
  builderFees: string;
  /** Qualifying paper/live trade receipts that carry builder codes. */
  builderAttributedTrades: number;
  /** x402 calls from external wallets (excluding Prism's own agent wallets). */
  externalX402Calls: number;
  /** Average sentinel verdict score (0–100). */
  avgVerdictScore: string;
  /** 50th-percentile verdict latency (trace creation → verdict creation). */
  latencyP50: string;
  /** 95th-percentile verdict latency. */
  latencyP95: string;
  /** Score spread between highest and lowest verdict categories (calibration proxy). */
  calibrationGap: number;

  /** 7-day sparkline data for each metric. */
  dailyVerdicts: DailyCount[];
  dailyWallets: DailyCount[];
  dailyTraces: DailyCount[];
  dailyAnchors: DailyCount[];
  dailyFees: DailyFee[];
  dailyX402Calls: DailyCount[];
  dailyScores: DailyAvg[];
  /** Daily average latency in seconds — used by latency p50/p95 sparklines. */
  dailyLatency: DailyLatency[];
  /** Daily calibration gap — used by calibration-gap sparkline. */
  dailyCalibrationGap: DailyCalibrationGap[];

  /** Verdict score distribution histogram (4 buckets: 0–25, 26–50, 51–75, 76–100). */
  verdictDistribution: VerdictBucket[];
}

/* ─────────────── Main fetch function ─────────────── */

/**
 * Fetch all stats data in as few round-trips as possible.
 * Designed to complete in <500 ms server time on Neon (VAL-STATS-001).
 * Returns zero-safe defaults if Neon is unreachable so the page never crashes.
 */
export async function getStatsData(): Promise<StatsData> {
  const client = getPool();

  try {
    // Run all aggregate queries in parallel for minimal latency
    const [
      verdictsResult,
      walletsResult,
      tracesResult,
      anchorsResult,
      feesResult,
      builderTradesResult,
      externalResult,
      avgScoreResult,
      latencyResult,
      calibrationResult,
      dailyVerdictsResult,
      dailyWalletsResult,
      dailyTracesResult,
      dailyAnchorsResult,
      dailyFeesResult,
      dailyX402Result,
      dailyScoresResult,
      dailyLatencyResult,
      dailyCalibrationGapResult,
      distributionResult,
    ] = await Promise.all([
      // ── Core aggregates ──
      client.query("SELECT count(*) AS cnt FROM validations"),
      client.query(
        "SELECT count(DISTINCT requester_address) AS cnt FROM validations WHERE requester_address IS NOT NULL",
      ),
      client.query("SELECT count(*) AS cnt FROM traces"),
      client.query(
        `SELECT count(*) AS cnt
           FROM traces t
           JOIN validations v ON v.trace_id = t.trace_id
          WHERE t.tx_hash IS NOT NULL
            AND v.tx_hash IS NOT NULL`,
      ),
      client.query(
        `SELECT COALESCE(SUM(size * COALESCE(fill_price::numeric, 0)) * 0.001, 0)::numeric(20,6) AS total
           FROM trades
          WHERE status IN ('paper_filled', 'filled')`,
      ),
      client.query(
        `SELECT count(*) AS cnt
           FROM trades
          WHERE status IN ('paper_filled', 'filled')
            AND builder_code IS NOT NULL`,
      ),
      client.query(
        `SELECT count(*) AS cnt
           FROM validations
          WHERE requester_address IS NOT NULL
            AND lower(requester_address) NOT IN (${INTERNAL_WALLET_ADDRESSES.map((_, i) => `$${i + 1}`).join(", ")})`,
        [...INTERNAL_WALLET_ADDRESSES],
      ),
      client.query(
        "SELECT AVG(verdict_score)::numeric(10,2) AS avg FROM validations",
      ),
      // Latency: time between trace creation and validation creation
      client.query(
        `SELECT
           percentile_cont(0.5)  WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (v.created_at - t.created_at))) AS p50,
           percentile_cont(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (v.created_at - t.created_at))) AS p95
         FROM validations v
         JOIN traces t ON t.trace_id = v.trace_id`,
      ),
      // Calibration gap: score spread between PASS/ENDORSE vs REJECT verdicts
      client.query(
        `SELECT
           COALESCE(AVG(verdict_score) FILTER (WHERE verdict_score >= 75), 0) AS good_avg,
           COALESCE(AVG(verdict_score) FILTER (WHERE verdict_score <= 25), 0) AS bad_avg
         FROM validations`,
      ),

      // ── 7-day sparklines ──
      client.query(
        `SELECT DATE(created_at)::text AS date, count(*)::int AS cnt
           FROM validations
          WHERE created_at >= NOW() - INTERVAL '7 days'
          GROUP BY DATE(created_at)
          ORDER BY date`,
      ),
      client.query(
        `SELECT DATE(created_at)::text AS date, count(DISTINCT requester_address)::int AS cnt
           FROM validations
          WHERE created_at >= NOW() - INTERVAL '7 days'
            AND requester_address IS NOT NULL
          GROUP BY DATE(created_at)
          ORDER BY date`,
      ),
      client.query(
        `SELECT DATE(created_at)::text AS date, count(*)::int AS cnt
           FROM traces
          WHERE created_at >= NOW() - INTERVAL '7 days'
          GROUP BY DATE(created_at)
          ORDER BY date`,
      ),
      client.query(
        `SELECT DATE(v.created_at)::text AS date, count(*)::int AS cnt
           FROM validations v
           JOIN traces t ON t.trace_id = v.trace_id
          WHERE v.created_at >= NOW() - INTERVAL '7 days'
            AND t.tx_hash IS NOT NULL
            AND v.tx_hash IS NOT NULL
          GROUP BY DATE(v.created_at)
          ORDER BY date`,
      ),
      client.query(
        `SELECT DATE(created_at)::text AS date,
                COALESCE(SUM(size * COALESCE(fill_price::numeric, 0)) * 0.001, 0)::numeric(20,6) AS fee
           FROM trades
          WHERE status IN ('paper_filled', 'filled')
            AND created_at >= NOW() - INTERVAL '7 days'
          GROUP BY DATE(created_at)
          ORDER BY date`,
      ),
      client.query(
        `SELECT DATE(created_at)::text AS date, count(*)::int AS cnt
           FROM validations
          WHERE created_at >= NOW() - INTERVAL '7 days'
            AND requester_address IS NOT NULL
            AND lower(requester_address) NOT IN (${INTERNAL_WALLET_ADDRESSES.map((_, i) => `$${i + 1}`).join(", ")})
          GROUP BY DATE(created_at)
          ORDER BY date`,
        [...INTERNAL_WALLET_ADDRESSES],
      ),
      client.query(
        `SELECT DATE(created_at)::text AS date, AVG(verdict_score)::numeric(10,2) AS avg
           FROM validations
          WHERE created_at >= NOW() - INTERVAL '7 days'
          GROUP BY DATE(created_at)
          ORDER BY date`,
      ),
      // Daily average latency for sparkline
      client.query(
        `SELECT DATE(v.created_at)::text AS date,
                AVG(EXTRACT(EPOCH FROM (v.created_at - t.created_at)))::numeric(10,2) AS avg_seconds
           FROM validations v
           JOIN traces t ON t.trace_id = v.trace_id
          WHERE v.created_at >= NOW() - INTERVAL '7 days'
          GROUP BY DATE(v.created_at)
          ORDER BY date`,
      ),
      // Daily calibration gap for sparkline
      client.query(
        `SELECT DATE(created_at)::text AS date,
                COALESCE(AVG(verdict_score) FILTER (WHERE verdict_score >= 75), 0)
                - COALESCE(AVG(verdict_score) FILTER (WHERE verdict_score <= 25), 0) AS gap
           FROM validations
          WHERE created_at >= NOW() - INTERVAL '7 days'
          GROUP BY DATE(created_at)
          ORDER BY date`,
      ),

      // ── Verdict distribution histogram ──
      client.query(
        `SELECT
           CASE
             WHEN verdict_score BETWEEN  0 AND 25 THEN '0–25'
             WHEN verdict_score BETWEEN 26 AND 50 THEN '26–50'
             WHEN verdict_score BETWEEN 51 AND 75 THEN '51–75'
             WHEN verdict_score BETWEEN 76 AND 100 THEN '76–100'
           END AS label,
           CASE
             WHEN verdict_score BETWEEN  0 AND 25 THEN 0
             WHEN verdict_score BETWEEN 26 AND 50 THEN 26
             WHEN verdict_score BETWEEN 51 AND 75 THEN 51
             WHEN verdict_score BETWEEN 76 AND 100 THEN 76
           END AS lower,
           count(*)::int AS cnt
         FROM validations
         GROUP BY label, lower
         ORDER BY lower`,
      ),
    ]);

    // Extract scalar values
    const verdictsIssued = Number(verdictsResult.rows[0]?.cnt ?? 0);
    const uniqueWallets = Number(walletsResult.rows[0]?.cnt ?? 0);
    const tracesValidated = Number(tracesResult.rows[0]?.cnt ?? 0);
    const onChainAnchors = Number(anchorsResult.rows[0]?.cnt ?? 0);
    const builderFees = String(feesResult.rows[0]?.total ?? "0");
    const builderAttributedTrades = Number(builderTradesResult.rows[0]?.cnt ?? 0);
    const externalX402Calls = Number(externalResult.rows[0]?.cnt ?? 0);
    const avgVerdictScore = String(avgScoreResult.rows[0]?.avg ?? "0");
    const p50Seconds = Number(latencyResult.rows[0]?.p50 ?? 0);
    const p95Seconds = Number(latencyResult.rows[0]?.p95 ?? 0);
    const goodAvg = Number(calibrationResult.rows[0]?.good_avg ?? 0);
    const badAvg = Number(calibrationResult.rows[0]?.bad_avg ?? 0);
    const calibrationGap = Math.round(goodAvg - badAvg);

    // Map sparkline data
    const mapDailyCount = (rows: Record<string, unknown>[]): DailyCount[] =>
      rows.map((r) => ({ date: String(r.date), count: Number(r.cnt) }));

    const mapDailyFee = (rows: Record<string, unknown>[]): DailyFee[] =>
      rows.map((r) => ({ date: String(r.date), fee: String(r.fee) }));

    const mapDailyAvg = (rows: Record<string, unknown>[]): DailyAvg[] =>
      rows.map((r) => ({ date: String(r.date), avg: Number(r.avg) }));

    const mapDailyLatency = (rows: Record<string, unknown>[]): DailyLatency[] =>
      rows.map((r) => ({ date: String(r.date), avgSeconds: Number(r.avg_seconds) }));

    const mapDailyCalibrationGap = (rows: Record<string, unknown>[]): DailyCalibrationGap[] =>
      rows.map((r) => ({ date: String(r.date), gap: Math.round(Number(r.gap)) }));

    const mapDistribution = (
      rows: Record<string, unknown>[],
    ): VerdictBucket[] => {
      // Ensure all 4 buckets are present even if DB returns fewer
      const defaults: VerdictBucket[] = [
        { label: "0–25", lower: 0, count: 0 },
        { label: "26–50", lower: 26, count: 0 },
        { label: "51–75", lower: 51, count: 0 },
        { label: "76–100", lower: 76, count: 0 },
      ];
      const filled = defaults.map((d) => {
        const match = rows.find((r) => String(r.label) === d.label);
        return { ...d, count: match ? Number(match.cnt) : 0 };
      });
      return filled;
    };

    return {
      verdictsIssued,
      uniqueWallets,
      tracesValidated,
      onChainAnchors,
      builderFees,
      builderAttributedTrades,
      externalX402Calls,
      avgVerdictScore,
      latencyP50: formatLatency(p50Seconds),
      latencyP95: formatLatency(p95Seconds),
      calibrationGap,
      dailyVerdicts: mapDailyCount(dailyVerdictsResult.rows),
      dailyWallets: mapDailyCount(dailyWalletsResult.rows),
      dailyTraces: mapDailyCount(dailyTracesResult.rows),
      dailyAnchors: mapDailyCount(dailyAnchorsResult.rows),
      dailyFees: mapDailyFee(dailyFeesResult.rows),
      dailyX402Calls: mapDailyCount(dailyX402Result.rows),
      dailyScores: mapDailyAvg(dailyScoresResult.rows),
      dailyLatency: mapDailyLatency(dailyLatencyResult.rows),
      dailyCalibrationGap: mapDailyCalibrationGap(dailyCalibrationGapResult.rows),
      verdictDistribution: mapDistribution(distributionResult.rows),
    };
  } catch {
    // Return zero-safe defaults so the page never crashes
    return {
      verdictsIssued: 0,
      uniqueWallets: 0,
      tracesValidated: 0,
      onChainAnchors: 0,
      builderFees: "0",
      builderAttributedTrades: 0,
      externalX402Calls: 0,
      avgVerdictScore: "0",
      latencyP50: "—",
      latencyP95: "—",
      calibrationGap: 0,
      dailyVerdicts: [],
      dailyWallets: [],
      dailyTraces: [],
      dailyAnchors: [],
      dailyFees: [],
      dailyX402Calls: [],
      dailyScores: [],
      dailyLatency: [],
      dailyCalibrationGap: [],
      verdictDistribution: [
        { label: "0–25", lower: 0, count: 0 },
        { label: "26–50", lower: 26, count: 0 },
        { label: "51–75", lower: 51, count: 0 },
        { label: "76–100", lower: 76, count: 0 },
      ],
    };
  }
}

/* ─────────────── Subset for LiveActivityStrip ─────────────── */

/**
 * Lightweight activity stats consumed by the landing-page strip.
 * Returns the same numbers as the /stats tiles so the two surfaces
 * are always consistent (VAL-WIDGETS-003, VAL-CROSS-010).
 */
export interface ActivityStats {
  traces: number;
  validations: number;
  trades: number;
  flagged: number;
  /** Unique external wallets — the same number as the "Unique wallets connected" tile. */
  uniqueWallets: number;
  /** On-chain anchors — the same number as the "On-chain anchors" tile. */
  onChainAnchors: number;
  /** External x402 calls — the same number as the "External x402 calls served" tile. */
  externalX402Calls: number;
}

/**
 * Fetch activity stats for the landing page strip.
 * Replaces the old getActivityStats() from db.ts.
 * The numbers match the /stats tiles exactly (single source of truth).
 */
export async function getActivityStats(): Promise<ActivityStats> {
  const client = getPool();

  try {
    const result = await client.query(
      `SELECT
         (SELECT count(*) FROM traces)                                                                    AS traces,
         (SELECT count(*) FROM validations)                                                               AS validations,
         (SELECT count(*) FROM trades)                                                                    AS trades,
         (SELECT count(*) FROM validations WHERE verdict_score < 50)                                      AS flagged,
         (SELECT count(DISTINCT requester_address) FROM validations WHERE requester_address IS NOT NULL)  AS unique_wallets,
         (SELECT count(*) FROM traces t JOIN validations v ON v.trace_id = t.trace_id
              WHERE t.tx_hash IS NOT NULL AND v.tx_hash IS NOT NULL)                                      AS on_chain_anchors,
         (SELECT count(*) FROM validations WHERE requester_address IS NOT NULL
              AND lower(requester_address) NOT IN ($1, $2))                                              AS external_x402_calls`,
      [...INTERNAL_WALLET_ADDRESSES],
    );

    const row = result.rows[0] ?? {};
    return {
      traces: Number(row.traces ?? 0),
      validations: Number(row.validations ?? 0),
      trades: Number(row.trades ?? 0),
      flagged: Number(row.flagged ?? 0),
      uniqueWallets: Number(row.unique_wallets ?? 0),
      onChainAnchors: Number(row.on_chain_anchors ?? 0),
      externalX402Calls: Number(row.external_x402_calls ?? 0),
    };
  } catch {
    return {
      traces: 0,
      validations: 0,
      trades: 0,
      flagged: 0,
      uniqueWallets: 0,
      onChainAnchors: 0,
      externalX402Calls: 0,
    };
  }
}

/* ─────────────── Helpers ─────────────── */

/** Format a duration in seconds to a human-readable string. */
function formatLatency(seconds: number): string {
  if (seconds <= 0 || !Number.isFinite(seconds)) return "—";
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${minutes}m ${secs}s`;
}

/** Format a fee string (numeric) to at most 6 decimal places with USDC suffix. */
export function formatFee(feeStr: string): string {
  const fee = parseFloat(feeStr);
  if (Number.isNaN(fee) || fee === 0) return "0";
  return fee.toFixed(6).replace(/\.?0+$/, "");
}

/** Close the pool (for testing / shutdown). Delegates to the shared singleton in db.ts. */
export async function closeStatsPool(): Promise<void> {
  await closePool();
}
