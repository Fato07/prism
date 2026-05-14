/**
 * Stats Analytics Page — /stats
 *
 * Server component. Renders tiles for key platform metrics:
 *   1. Verdicts issued          — total adversarial verdicts produced
 *   2. Unique wallets connected — distinct external requester_address values
 *   3. Traces validated         — total reasoning traces in the system
 *   4. On-chain anchors         — traces with both request+response tx hashes
 *   5. Builder fees attributed  — 0.1% of fill notional from qualifying trades
 *   6. External x402 calls      — validations from non-Prism wallets
 *   7. Avg verdict score        — mean sentinel score across all validations
 *   8. Verdict distribution     — recharts histogram of score buckets
 *   9. Latency p50              — median time from trace creation to verdict
 *  10. Latency p95              — 95th-percentile latency
 *  11. Calibration gap          — score spread between good and bad verdicts
 *
 * Each tile has a 7-day sparkline (recharts) and a "What this measures" subtitle.
 * All data sourced from lib/stats.ts (single source of truth with LiveActivityStrip).
 *
 * VAL-STATS-001..016
 */

import type { Metadata } from "next";
import {
  getStatsData,
  formatFee,
  type StatsData,
  type DailyCount,
  type DailyFee,
  type DailyAvg,
  type DailyLatency,
  type DailyCalibrationGap,
} from "@/lib/stats";
import { StatsSparkline } from "@/components/ui/stats-sparkline";
import { VerdictDistributionChart } from "@/components/ui/verdict-distribution-chart";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Pill } from "@/components/ui/pill";
import { GlobalNav } from "@/components/global-nav";
import {
  ShieldCheck,
  Users,
  FileText,
  Link2,
  DollarSign,
  Zap,
  BarChart3,
  Clock,
  Target,
} from "lucide-react";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Stats — Prism",
  description:
    "Platform analytics for Prism: verdict counts, unique wallets, on-chain anchors, builder fees, external x402 calls, latency, and calibration metrics.",
};

export default async function StatsPage() {
  const stats = await getStatsData();

  return (
    <div className="min-h-screen bg-canvas text-fg">
      <GlobalNav currentPage="stats" />

      <main className="mx-auto max-w-6xl px-6 py-10">
        <div className="mb-8">
          <h1 className="text-2xl font-semibold tracking-[var(--tracking-tight)] text-fg">
            Platform Stats
          </h1>
          <p className="mt-2 text-sm text-fg-muted">
            Real-time analytics from Neon. Numbers reconcile with direct SQL queries.
          </p>
        </div>

        {/* ── Row 1: Core metrics ── */}
        <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Tile
            title="Verdicts issued"
            value={stats.verdictsIssued.toLocaleString()}
            subtitle="Total adversarial verdicts produced by the sentinel"
            icon={<ShieldCheck className="h-4 w-4" strokeWidth={1.8} />}
            tone="sentinel"
            sparklineData={stats.dailyVerdicts.map((d) => ({
              date: d.date,
              value: d.count,
            }))}
          />
          <Tile
            title="Unique wallets connected"
            value={stats.uniqueWallets.toLocaleString()}
            subtitle="Distinct external addresses that paid for validations — proves traction"
            icon={<Users className="h-4 w-4" strokeWidth={1.8} />}
            tone="good"
            sparklineData={stats.dailyWallets.map((d) => ({
              date: d.date,
              value: d.count,
            }))}
          />
          <Tile
            title="Traces validated"
            value={stats.tracesValidated.toLocaleString()}
            subtitle="Total reasoning traces in the system"
            icon={<FileText className="h-4 w-4" strokeWidth={1.8} />}
            tone="trader"
            sparklineData={stats.dailyTraces.map((d) => ({
              date: d.date,
              value: d.count,
            }))}
          />
        </div>

        {/* ── Row 2: On-chain + revenue ── */}
        <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Tile
            title="On-chain anchors"
            value={stats.onChainAnchors.toLocaleString()}
            subtitle="Traces with both validationRequest and validationResponse on ERC-8004"
            icon={<Link2 className="h-4 w-4" strokeWidth={1.8} />}
            tone="neutral"
            sparklineData={stats.dailyAnchors.map((d) => ({
              date: d.date,
              value: d.count,
            }))}
          />
          <Tile
            title="Builder fees attributed"
            value={`${formatFee(stats.builderFees)} USDC`}
            subtitle="0.1% of fill notional from qualifying trades via HMAC builder codes"
            icon={<DollarSign className="h-4 w-4" strokeWidth={1.8} />}
            tone="good"
            sparklineData={stats.dailyFees.map((d) => ({
              date: d.date,
              value: parseFloat(d.fee) || 0,
            }))}
          />
          <Tile
            title="External x402 calls served"
            value={stats.externalX402Calls.toLocaleString()}
            subtitle="Validations requested by non-Prism wallets — excludes internal agent calls"
            icon={<Zap className="h-4 w-4" strokeWidth={1.8} />}
            tone="good"
            sparklineData={stats.dailyX402Calls.map((d) => ({
              date: d.date,
              value: d.count,
            }))}
          />
        </div>

        {/* ── Row 3: Quality metrics ── */}
        <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Tile
            title="Avg sentinel verdict score"
            value={stats.avgVerdictScore}
            subtitle="Mean verdict_score across all validations (0–100)"
            icon={<BarChart3 className="h-4 w-4" strokeWidth={1.8} />}
            tone="sentinel"
            sparklineData={stats.dailyScores.map((d) => ({
              date: d.date,
              value: d.avg,
            }))}
          />
          <Tile
            title="Verdict latency p50"
            value={stats.latencyP50}
            subtitle="Median time from trace creation to sentinel verdict"
            icon={<Clock className="h-4 w-4" strokeWidth={1.8} />}
            tone="neutral"
            sparklineData={stats.dailyLatency.map((d) => ({
              date: d.date,
              value: d.avgSeconds,
            }))}
          />
          <Tile
            title="Calibration gap"
            value={stats.calibrationGap.toString()}
            subtitle="Good vs bad synthetic-trace verdict spread — must be >= 30 per hard rule"
            icon={<Target className="h-4 w-4" strokeWidth={1.8} />}
            tone={stats.calibrationGap >= 30 ? "good" : "warn"}
            sparklineData={stats.dailyCalibrationGap.map((d) => ({
              date: d.date,
              value: d.gap,
            }))}
          />
        </div>

        {/* ── Latency p95 (standalone row) ── */}
        <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Tile
            title="Verdict latency p95"
            value={stats.latencyP95}
            subtitle="95th-percentile time from trace creation to verdict — tail latency"
            icon={<Clock className="h-4 w-4" strokeWidth={1.8} />}
            tone="neutral"
            sparklineData={stats.dailyLatency.map((d) => ({
              date: d.date,
              value: d.avgSeconds,
            }))}
          />
        </div>

        {/* ── Distribution histogram ── */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BarChart3
                className="h-4 w-4 text-[var(--color-sentinel)]"
                strokeWidth={1.8}
              />
              Verdict Score Distribution
            </CardTitle>
            <Pill tone="neutral" emphasis="outline" size="xs">
              <span className="text-mono">{stats.verdictsIssued} total</span>
            </Pill>
          </CardHeader>
          <CardContent>
            <VerdictDistributionChart data={stats.verdictDistribution} height={220} />
            <p className="mt-3 text-xs text-fg-faint">
              Buckets: REJECT (0–25) / WARN (26–50) / PASS (51–75) / ENDORSE (76–100).
              Bar heights sum to the total verdicts issued.
            </p>
          </CardContent>
        </Card>

        {/* ── Methodology note ── */}
        <div className="mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-canvas-sunken)] p-4">
          <p className="text-mono text-[10px] uppercase tracking-[var(--tracking-wide)] text-fg-faint mb-2">
            Methodology
          </p>
          <p className="text-xs text-fg-muted leading-relaxed">
            All metrics are computed from Neon Postgres via indexed queries. External x402
            calls exclude the trader wallet{" "}
            <span className="text-mono">0xc960…452b</span> and sentinel wallet{" "}
            <span className="text-mono">0x5650…ac36</span>. On-chain anchors count traces
            where both the ERC-8004 validationRequest and validationResponse transactions
            are non-null. Builder fees are estimated at 0.1% of fill notional for{" "}
            <span className="text-mono">paper_filled</span> and{" "}
            <span className="text-mono">filled</span> trades. Calibration gap is the score
            spread between high-scoring (&ge;75) and low-scoring (&le;25) verdicts. Sparklines
            cover the last 7 days of daily aggregates.
          </p>
        </div>
      </main>
    </div>
  );
}

/* ─────────────── Tile component ─────────────── */

type TileTone = "trader" | "sentinel" | "good" | "warn" | "neutral";

const TONE_ICON_COLOR: Record<TileTone, string> = {
  trader: "text-[var(--color-trader)]",
  sentinel: "text-[var(--color-sentinel)]",
  good: "text-[var(--color-verdict-good)]",
  warn: "text-[var(--color-warning)]",
  neutral: "text-[var(--color-fg-muted)]",
};

interface TileProps {
  title: string;
  value: string;
  subtitle: string;
  icon: React.ReactNode;
  tone: TileTone;
  sparklineData: { date: string; value: number }[];
}

function Tile({ title, value, subtitle, icon, tone, sparklineData }: TileProps) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1">
            <div className="mb-2 flex items-center gap-2">
              <span className={TONE_ICON_COLOR[tone]}>{icon}</span>
              <span className="text-mono text-[10px] font-medium uppercase tracking-[var(--tracking-wide)] text-fg-faint">
                {title}
              </span>
            </div>
            <p className="text-mono text-3xl font-semibold tabular-nums text-fg">
              {value}
            </p>
            <p className="mt-1.5 text-xs leading-snug text-fg-faint">
              {subtitle}
            </p>
          </div>
          <div className="flex-shrink-0 pt-1">
            <StatsSparkline
              data={sparklineData}
              tone={tone}
              height={40}
              width={90}
              gradientId={title.replace(/\s+/g, "-").toLowerCase()}
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

