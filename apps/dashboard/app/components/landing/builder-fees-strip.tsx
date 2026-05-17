/**
 * BuilderFeesStrip — widget for landing-page execution attribution.
 *
 * Server component. Renders builder code, optional agent id/wallet, attributed
 * paper/live trade count, and fee status for the top 3 builder codes.
 * Shows EmptyState when no qualifying trades exist.
 */

import {
  getBuilderFeesLeaderboard,
  enrichBuilderFeesWithAgents,
  getAgents,
  type BuilderFeesEntry,
} from "@/lib/db";
import { HashChip } from "@/components/ui/hash-chip";
import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { FeeSparkline } from "@/components/ui/fee-sparkline";
import { BrandMark } from "@/components/brands/brand-mark";
import { Activity } from "lucide-react";

const BUILDER_HMAC_SECRET = process.env.BUILDER_HMAC_SECRET ?? "";

interface BuilderFeesStripProps {
  /** Pre-fetched top entries. Pass null to trigger internal fetch. */
  entries?: BuilderFeesEntry[] | null;
}

export async function BuilderFeesStrip({ entries: propEntries }: BuilderFeesStripProps) {
  let entries = propEntries;

  if (!entries) {
    const [raw, agents] = await Promise.all([
      getBuilderFeesLeaderboard(),
      getAgents(),
    ]);
    entries = BUILDER_HMAC_SECRET
      ? await enrichBuilderFeesWithAgents(raw, agents, BUILDER_HMAC_SECRET)
      : raw;
  }

  const top3 = entries.slice(0, 3);

  if (top3.length === 0) {
    return (
      <section aria-labelledby="builder-fees-strip" className="border-b border-[var(--color-border)]">
        <div className="mx-auto max-w-6xl px-6 py-12">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Activity
                  className="h-4 w-4 text-[var(--color-verdict-good)]"
                  strokeWidth={1.8}
                />
                Execution attribution
              </CardTitle>
            </CardHeader>
            <CardContent>
              <EmptyState
                title="No execution attribution yet"
                description="When paper or live trades carry Prism builder codes, attribution will appear here."
              />
            </CardContent>
          </Card>
        </div>
      </section>
    );
  }

  return (
    <section aria-labelledby="builder-fees-strip" className="border-b border-[var(--color-border)]">
      <div className="mx-auto max-w-6xl px-6 py-12">
        <div className="mb-6">
          <h2
            id="builder-fees-strip"
            className="text-mono text-xs font-medium uppercase tracking-[var(--tracking-wide)] text-fg-faint"
          >
            Execution attribution — builder codes
          </h2>
          <p className="mt-2 max-w-2xl text-sm text-fg-muted">
            Prism links validated reasoning traces to Prism trade receipts with Polymarket-compatible builder codes. Live fills reconcile to Polymarket builder-trade receipts when present.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {top3.map((entry, i) => {
            const fee = feeDisplay(entry);
            return (
              <Card key={entry.builder_code}>
                <CardContent className="flex flex-col gap-3 p-4">
                  <div className="flex items-center justify-between">
                    <span className="text-mono text-[10px] font-medium uppercase tracking-[var(--tracking-wide)] text-fg-faint">
                      #{i + 1}
                    </span>
                    {entry.wallet_address ? (
                      <HashChip
                        value={entry.wallet_address}
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
                  </div>

                  <div className="flex items-center gap-2">
                    {entry.agent_id !== null && (
                      <BrandMark
                        name="arc"
                        size={14}
                        aria-label={`Agent ${entry.agent_id}`}
                      />
                    )}
                    <span className="text-mono text-sm font-semibold text-fg">
                      {entry.agent_id !== null ? `Agent ${entry.agent_id}` : "Builder code"}
                    </span>
                  </div>

                  <div>
                    <span
                      className={`text-mono text-2xl font-semibold tabular-nums ${
                        fee.pending ? "text-fg-muted" : "text-[var(--color-verdict-good)]"
                      }`}
                    >
                      {fee.label}
                    </span>
                    {!fee.pending && <span className="ml-1 text-sm text-fg-faint">USDC</span>}
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="text-mono text-[10px] text-fg-faint">
                      {entry.trade_count} attributed trade{entry.trade_count !== 1 ? "s" : ""}
                    </span>
                    <FeeSparkline data={entry.daily_fees} height={24} />
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>
    </section>
  );
}

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
