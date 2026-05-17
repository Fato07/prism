/**
 * Execution Attribution — /builder-fees
 *
 * Server component. Renders a builder-code receipt table showing:
 *   rank, agent ID, wallet/builder code, attributed trade count, fee status,
 *   last trade timestamp, and a sparkline per row.
 *
 * Fee calculation, when fill prices are present: 0.1% of fill notional
 * (size * fill_price * 0.001) for trades with status IN ('paper_filled', 'filled').
 *
 * Builder codes are matched to agents via the HMAC function from
 * @prism/builder-codes (the shared workspace package).
 */

import type { Metadata } from "next";
import {
  getBuilderFeesLeaderboard,
  enrichBuilderFeesWithAgents,
  getAgents,
  type BuilderFeesEntry,
} from "@/lib/db";
import { HashChip } from "@/components/ui/hash-chip";
import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Pill } from "@/components/ui/pill";
import { FeeSparkline } from "@/components/ui/fee-sparkline";
import { GlobalNav } from "@/components/global-nav";
import { BrandMark } from "@/components/brands/brand-mark";
import { Activity } from "lucide-react";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Execution Attribution — Prism",
  description:
    "Polymarket builder-code attribution for Prism agents, with fee totals shown only when fill-price receipts are present.",
};

/** HMAC secret from env — used to map builder_code → agent_id. */
const BUILDER_HMAC_SECRET = process.env.BUILDER_HMAC_SECRET ?? "";

export default async function BuilderFeesPage() {
  const [rawEntries, agents] = await Promise.all([
    getBuilderFeesLeaderboard(),
    getAgents(),
  ]);

  // Enrich with agent_id and wallet_address via HMAC matching
  const entries = BUILDER_HMAC_SECRET
    ? await enrichBuilderFeesWithAgents(rawEntries, agents, BUILDER_HMAC_SECRET)
    : rawEntries;

  return (
    <div className="min-h-screen bg-canvas text-fg">
      <GlobalNav currentPage="builder-fees" />

      <main className="mx-auto max-w-5xl px-6 py-10">
        <div className="mb-8">
          <h1 className="text-2xl font-semibold tracking-[var(--tracking-tight)] text-fg">
            Execution Attribution
          </h1>
          <p className="mt-2 text-sm text-fg-muted">
            Prism links validated reasoning traces to Prism trade receipts with
            Polymarket-compatible builder codes. Live fills reconcile to Polymarket
            builder-trade receipts when present.
          </p>
        </div>

        {entries.length === 0 ? (
          <Card>
            <CardContent>
              <EmptyState
                title="No attributed trades yet"
                description="Once paper or live trades carry Prism builder codes, attribution will appear here."
              />
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Activity
                  className="h-4 w-4 text-[var(--color-verdict-good)]"
                  strokeWidth={1.8}
                />
                Builder-code receipts
              </CardTitle>
              <Pill tone="neutral" emphasis="outline" size="xs">
                <span className="text-mono">{entries.length} builder code{entries.length !== 1 ? "s" : ""}</span>
              </Pill>
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-[var(--color-border)]">
                      <ThCell>Rank</ThCell>
                      <ThCell>Agent</ThCell>
                      <ThCell>Wallet / builder code</ThCell>
                      <ThCell className="text-right">Trades</ThCell>
                      <ThCell className="text-right">Fee status</ThCell>
                      <ThCell>Trend (7d)</ThCell>
                      <ThCell>Last Trade</ThCell>
                    </tr>
                  </thead>
                  <tbody>
                    {entries.map((entry, i) => {
                      const fee = feeDisplay(entry);
                      return (
                        <tr
                          key={entry.builder_code}
                          className="border-b border-[var(--color-border)] transition-colors hover:bg-[var(--color-canvas-raised)]"
                        >
                          <TdCell className="text-mono tabular-nums text-fg-faint">
                            {i + 1}
                          </TdCell>
                          <TdCell>
                            {entry.agent_id !== null ? (
                              <span className="inline-flex items-center gap-1.5">
                                <BrandMark
                                  name={
                                    agents.find((a) => a.agent_id === entry.agent_id)
                                      ?.role === "trader"
                                      ? "arc"
                                      : "circle"
                                  }
                                  size={12}
                                  aria-label={`Agent ${entry.agent_id}`}
                                />
                                <span className="text-mono text-fg">
                                  {entry.agent_id}
                                </span>
                              </span>
                            ) : (
                              <span className="text-fg-faint">—</span>
                            )}
                          </TdCell>
                          <TdCell>
                            {entry.wallet_address ? (
                              <HashChip
                                value={entry.wallet_address}
                                href={`https://testnet.arcscan.app/address/${entry.wallet_address}`}
                                truncate={4}
                                size="xs"
                              />
                            ) : (
                              <HashChip
                                value={entry.builder_code}
                                truncate={6}
                                size="xs"
                              />
                            )}
                          </TdCell>
                          <TdCell className="text-right">
                            <span className="text-mono tabular-nums text-fg">
                              {entry.trade_count}
                            </span>
                          </TdCell>
                          <TdCell className="text-right">
                            <span
                              className={`text-mono tabular-nums ${
                                fee.pending ? "text-fg-muted" : "text-[var(--color-verdict-good)]"
                              }`}
                            >
                              {fee.label}
                            </span>
                            {!fee.pending && <span className="ml-1 text-fg-faint">USDC</span>}
                          </TdCell>
                          <TdCell>
                            <FeeSparkline data={entry.daily_fees} />
                          </TdCell>
                          <TdCell>
                            <span className="text-mono text-xs text-fg-muted">
                              {formatTimestamp(entry.last_trade_at)}
                            </span>
                          </TdCell>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Methodology note */}
        <div className="mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-canvas-sunken)] p-4">
          <p className="text-mono text-[10px] uppercase tracking-[var(--tracking-wide)] text-fg-faint mb-2">
            Methodology
          </p>
          <p className="text-xs text-fg-muted leading-relaxed">
            Builder codes create an execution-attribution link from Prism reports to
            Prism trade receipts. Paper receipts carry Polymarket-compatible builder codes;
            live fills reconcile to Polymarket builder-trade receipts when present. Fee totals use a <strong>0.1%</strong>{" "}
            fill-notional model <span className="text-mono">(size x fill_price x 0.001)</span>{" "}
            only when fill-price data is present; older paper receipts without price data stay
            marked as <span className="text-mono">Fee pending</span> rather than being counted as revenue.
          </p>
        </div>
      </main>
    </div>
  );
}

/* ─────────────── Helpers ─────────────── */

function feeDisplay(entry: BuilderFeesEntry): { label: string; pending: boolean } {
  const fee = parseFloat(entry.total_fees);
  if ((Number.isNaN(fee) || fee === 0) && entry.trade_count > 0) {
    return { label: "Fee pending", pending: true };
  }
  if (Number.isNaN(fee) || fee === 0) return { label: "0", pending: false };
  return {
    label: fee.toFixed(6).replace(/\.?0+$/, ""),
    pending: false,
  };
}

/** Format an ISO timestamp to a human-readable string. */
function formatTimestamp(ts: string | null): string {
  if (!ts) return "—";
  try {
    const d = new Date(ts);
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZoneName: "short",
    });
  } catch {
    return ts;
  }
}

/* ─────────────── Table primitives ─────────────── */

function ThCell({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <th
      className={`px-4 py-3 text-mono text-[10px] font-medium uppercase tracking-[var(--tracking-wide)] text-fg-faint ${className ?? ""}`}
    >
      {children}
    </th>
  );
}

function TdCell({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <td className={`px-4 py-3 ${className ?? ""}`}>
      {children}
    </td>
  );
}
