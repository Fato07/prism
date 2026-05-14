/**
 * TreasuryStrip — widget for the dashboard home showing USDC parked in USYC.
 *
 * Server component (no 'use client' at the widget root).
 * Shows:
 *   - Total USDC currently parked (sum of park minus unpark, floored at 0)
 *   - Estimated yield earned (MOCK — 4.5% APY pro-rated over parked duration;
 *     no real USYC rate API exists on Arc Testnet at time of implementation.
 *     See mock documentation below.)
 *   - Last park/unpark event with relative timestamp
 *   - 7-day event count badge
 * Renders "No treasury activity yet" empty state when treasury_events is empty.
 *
 * ─── MOCK YIELD DOCUMENTATION ───
 * The `yieldEarned` field is computed as totalParked × 0.045 × (daysSinceFirstPark / 365).
 * This uses a hardcoded 4.5% APY assumption because:
 *   1. USYC is not deployed on Arc Testnet (confirmed dry-run mode in trader treasury module).
 *   2. No on-chain rate oracle or API exists for USYC yield on any testnet.
 *   3. The mock is explicitly labeled "(mock 4.5% APY)" in the UI.
 * When USYC deploys to Arc Testnet (or a rate oracle is available), replace
 * the mock calculation with a live rate fetch. The TreasuryData type's
 * yieldEarned field will carry the real value once implemented.
 * ─── END MOCK YIELD DOCUMENTATION ───
 */

import { getTreasuryData, type TreasuryData } from "@/lib/db";
import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { FeeSparkline } from "@/components/ui/fee-sparkline";
import { BrandMark } from "@/components/brands/brand-mark";
import { DollarSign, TrendingUp } from "lucide-react";

/** Mock APY for yield estimation. Replace with live rate when USYC is available on Arc Testnet. */
const MOCK_USYC_APY = 0.045;

interface TreasuryStripProps {
  /** Pre-fetched treasury data. Pass null to trigger internal fetch. */
  data?: TreasuryData | null;
}

export async function TreasuryStrip({ data: propData }: TreasuryStripProps) {
  const data = propData ?? (await getTreasuryData());

  const totalParked = parseFloat(data.totalParked);
  const hasActivity = totalParked > 0 || data.lastEvent !== null;

  if (!hasActivity) {
    return (
      <section
        data-testid="treasury-strip"
        aria-label="Treasury"
        className="border-b border-[var(--color-border)]"
      >
        <div className="mx-auto max-w-6xl px-6 py-12">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <DollarSign
                  className="h-4 w-4 text-[var(--color-verdict-good)]"
                  strokeWidth={1.8}
                />
                Treasury
              </CardTitle>
            </CardHeader>
            <CardContent>
              <EmptyState
                title="No treasury activity yet"
                description="When the trader parks idle USDC into USYC, totals and yield will appear here."
              />
            </CardContent>
          </Card>
        </div>
      </section>
    );
  }

  // Compute mock yield: totalParked × APY × (fraction of year since first event)
  // If no lastEvent, yield is zero. This is a rough estimate.
  const yieldEarned = computeMockYield(totalParked, data.lastEvent?.created_at);

  return (
    <section
      data-testid="treasury-strip"
      aria-label="Treasury"
      className="border-b border-[var(--color-border)]"
    >
      <div className="mx-auto max-w-6xl px-6 py-12">
        <div className="mb-6">
          <h2 className="text-mono text-xs font-medium uppercase tracking-[var(--tracking-wide)] text-fg-faint">
            Treasury — USYC yield
          </h2>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {/* Total parked */}
          <Card>
            <CardContent className="flex flex-col gap-3 p-4">
              <div className="flex items-center gap-2">
                <DollarSign
                  className="h-4 w-4 text-[var(--color-verdict-good)]"
                  strokeWidth={1.8}
                />
                <span className="text-mono text-[10px] font-medium uppercase tracking-[var(--tracking-wide)] text-fg-faint">
                  USDC parked in USYC
                </span>
              </div>
              <div>
                <span className="text-mono text-2xl font-semibold tabular-nums text-[var(--color-verdict-good)]">
                  {formatUsdc(data.totalParked)}
                </span>
                <span className="ml-1 text-sm text-fg-faint">USDC</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-mono text-[10px] text-fg-faint">
                  {data.recentEventCount} event{data.recentEventCount !== 1 ? "s" : ""} (7d)
                </span>
                <FeeSparkline
                  data={data.dailyParked.map((d) => ({
                    date: d.date,
                    fee: d.amount,
                  }))}
                  height={24}
                />
              </div>
            </CardContent>
          </Card>

          {/* Yield earned (mock) */}
          <Card>
            <CardContent className="flex flex-col gap-3 p-4">
              <div className="flex items-center gap-2">
                <TrendingUp
                  className="h-4 w-4 text-[var(--color-trader)]"
                  strokeWidth={1.8}
                />
                <span className="text-mono text-[10px] font-medium uppercase tracking-[var(--tracking-wide)] text-fg-faint">
                  Yield earned
                </span>
              </div>
              <div>
                <span className="text-mono text-2xl font-semibold tabular-nums text-[var(--color-trader)]">
                  {formatUsdc(yieldEarned.toFixed(6))}
                </span>
                <span className="ml-1 text-sm text-fg-faint">USDC</span>
              </div>
              <span className="text-mono text-[10px] text-fg-faint">
                Mock 4.5% APY
              </span>
            </CardContent>
          </Card>

          {/* Last event */}
          <Card>
            <CardContent className="flex flex-col gap-3 p-4">
              <div className="flex items-center gap-2">
                <BrandMark name="circle" size={14} aria-label="Circle" />
                <span className="text-mono text-[10px] font-medium uppercase tracking-[var(--tracking-wide)] text-fg-faint">
                  Last event
                </span>
              </div>
              {data.lastEvent ? (
                <>
                  <div className="flex items-center gap-2">
                    <span
                      className={`text-mono text-sm font-semibold ${
                        data.lastEvent.event_type === "park"
                          ? "text-[var(--color-verdict-good)]"
                          : "text-[var(--color-sentinel)]"
                      }`}
                    >
                      {data.lastEvent.event_type === "park" ? "Park" : "Unpark"}
                    </span>
                    <span className="text-mono text-2xl font-semibold tabular-nums text-fg">
                      {formatUsdc(data.lastEvent.usdc_amount)}
                    </span>
                    <span className="text-sm text-fg-faint">USDC</span>
                  </div>
                  <time
                    dateTime={data.lastEvent.created_at}
                    className="text-mono text-[10px] text-fg-faint"
                  >
                    {relativeTime(data.lastEvent.created_at)}
                  </time>
                </>
              ) : (
                <span className="text-mono text-sm text-fg-faint">—</span>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </section>
  );
}

/* ─────────────── Helpers ─────────────── */

/**
 * Compute mock yield earned based on total parked and time since first event.
 * Uses hardcoded 4.5% APY. Returns yield in USDC as a number.
 */
function computeMockYield(
  totalParked: number,
  firstEventCreatedAt?: string,
): number {
  if (totalParked <= 0 || !firstEventCreatedAt) return 0;

  const eventDate = new Date(firstEventCreatedAt);
  const now = new Date();
  const diffMs = now.getTime() - eventDate.getTime();
  const diffDays = Math.max(0, diffMs / (1000 * 60 * 60 * 24));
  const fractionOfYear = diffDays / 365;

  return totalParked * MOCK_USYC_APY * fractionOfYear;
}

/** Format a USDC amount string or number to a clean display string. */
function formatUsdc(value: string): string {
  const num = parseFloat(value);
  if (Number.isNaN(num) || num === 0) return "0";
  // Show up to 6 decimal places, stripping trailing zeros
  return num.toFixed(6).replace(/\.?0+$/, "");
}

/** Convert an ISO timestamp to a relative time string (e.g., "2m ago", "3h ago"). */
function relativeTime(isoTimestamp: string): string {
  const date = new Date(isoTimestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();

  if (diffMs < 0) return "just now";

  const seconds = Math.floor(diffMs / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (days > 0) return `${days}d ago`;
  if (hours > 0) return `${hours}h ago`;
  if (minutes > 0) return `${minutes}m ago`;
  return "just now";
}
