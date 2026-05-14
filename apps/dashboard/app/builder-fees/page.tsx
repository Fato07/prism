/**
 * Builder Fees Leaderboard — /builder-fees
 *
 * Server component. Renders a leaderboard table showing:
 *   rank, agent ID, wallet (HashChip), # trades, total USDC fees,
 *   last trade timestamp, and a recharts sparkline per row.
 *
 * Fee calculation: 0.1% of fill notional (size * fill_price * 0.001)
 * for trades with status IN ('paper_filled', 'filled').
 *
 * Builder codes are matched to agents via the HMAC function from
 * @prism/builder-codes (the shared workspace package).
 */

import type { Metadata } from "next";
import {
  getBuilderFeesLeaderboard,
  enrichBuilderFeesWithAgents,
  getAgents,
} from "@/lib/db";
import { mapAgentIdToBuilderCode } from "@prism/builder-codes";
import { HashChip } from "@/components/ui/hash-chip";
import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Pill } from "@/components/ui/pill";
import { FeeSparkline } from "@/components/ui/fee-sparkline";
import { ConnectWalletButton } from "@/components/connect-wallet-button";
import { BrandMark } from "@/components/brands/brand-mark";
import { DollarSign, Activity } from "lucide-react";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Builder Fees — Prism",
  description:
    "Leaderboard of Polymarket builder fees attributed to Prism agents via HMAC builder codes.",
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
      <BuilderFeesNav agents={agents} />

      <main className="mx-auto max-w-5xl px-6 py-10">
        <div className="mb-8">
          <h1 className="text-2xl font-semibold tracking-[var(--tracking-tight)] text-fg">
            Builder Fees Leaderboard
          </h1>
          <p className="mt-2 text-sm text-fg-muted">
            Polymarket builder fee attribution via HMAC-derived builder codes.
            Fees calculated at 0.1% of fill notional for paper-filled and live-filled trades.
          </p>
        </div>

        {entries.length === 0 ? (
          <Card>
            <CardContent>
              <EmptyState
                title="No qualifying trades yet"
                description="Once trades with 'paper_filled' or 'filled' status exist, the builder fees leaderboard will appear here."
              />
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <DollarSign
                  className="h-4 w-4 text-[var(--color-verdict-good)]"
                  strokeWidth={1.8}
                />
                Fee Attribution
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
                      <ThCell>Wallet</ThCell>
                      <ThCell className="text-right">Trades</ThCell>
                      <ThCell className="text-right">Total Fees</ThCell>
                      <ThCell>Trend (7d)</ThCell>
                      <ThCell>Last Trade</ThCell>
                    </tr>
                  </thead>
                  <tbody>
                    {entries.map((entry, i) => (
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
                          <span className="text-mono tabular-nums text-[var(--color-verdict-good)]">
                            {formatFee(entry.total_fees)}
                          </span>
                          <span className="ml-1 text-fg-faint">USDC</span>
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
                    ))}
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
            Builder fees are estimated at <strong>0.1%</strong> of fill notional{" "}
            <span className="text-mono">(size x fill_price x 0.001)</span> for trades
            with <span className="text-mono">paper_filled</span> or{" "}
            <span className="text-mono">filled</span> status. Builder codes are derived
            via HMAC-SHA256 from the agent&apos;s ERC-8004 agentId using{" "}
            <span className="text-mono">@prism/builder-codes</span>. Once live trades
            fill on Polymarket, real builder fee data from{" "}
            <span className="text-mono">getBuilderTrades()</span> will replace these
            estimates.
          </p>
        </div>
      </main>
    </div>
  );
}

/* ─────────────── Helpers ─────────────── */

/** Format a fee string (numeric) to at most 6 decimal places with USDC suffix. */
function formatFee(feeStr: string): string {
  const fee = parseFloat(feeStr);
  if (Number.isNaN(fee) || fee === 0) return "0";
  // Show up to 6 decimals, but strip trailing zeros
  return fee.toFixed(6).replace(/\.?0+$/, "");
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

/* ─────────────── Nav ─────────────── */

function BuilderFeesNav({
  agents,
}: {
  agents: { agent_id: number; role: string; wallet_address: string }[];
}) {
  const traderAgent = agents.find((a) => a.role === "trader");

  return (
    <nav className="sticky top-0 z-40 border-b border-[var(--color-border)] bg-[var(--color-canvas)]/80 backdrop-blur-md">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-3">
        <div className="flex items-center gap-3">
          <a
            href="/"
            className="inline-flex items-center gap-2 text-base font-semibold tracking-[var(--tracking-tight)] text-fg"
          >
            <Wordmark />
            <span>Prism</span>
          </a>
          <span className="text-fg-faint">/</span>
          <span className="text-mono text-xs uppercase tracking-[var(--tracking-wide)] text-fg-muted">
            builder-fees
          </span>
        </div>
        <div className="flex items-center gap-2">
          <ConnectWalletButton />
          <a
            href="/history"
            className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-sm font-medium text-fg-muted transition-colors hover:border-[var(--color-border-strong)] hover:text-fg"
          >
            History
          </a>
          <a
            href="/dashboard"
            className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border-strong)] bg-[var(--color-canvas-raised)] px-3.5 py-1.5 text-sm font-medium text-fg transition-colors hover:bg-[var(--color-panel)]"
          >
            Dashboard
          </a>
        </div>
      </div>
    </nav>
  );
}

function Wordmark() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 20 20"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M4 17L10 3L16 17Z"
        stroke="url(#bf-prism-gradient)"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
      <defs>
        <linearGradient
          id="bf-prism-gradient"
          x1="3"
          y1="3"
          x2="17"
          y2="17"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="var(--color-trader)" />
          <stop offset="0.6" stopColor="var(--color-sentinel)" />
          <stop offset="1" stopColor="var(--color-verdict-good)" />
        </linearGradient>
      </defs>
    </svg>
  );
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
