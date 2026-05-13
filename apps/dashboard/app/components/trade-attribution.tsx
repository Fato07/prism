/**
 * Trade attribution panel — shows the most recent trade with builder code,
 * size, side, status, and a link to Polymarket if a tx hash is present.
 */

import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Pill } from "@/components/ui/pill";
import { HashChip } from "@/components/ui/hash-chip";
import { EmptyState } from "@/components/ui/empty-state";
import { Zap, CreditCard } from "lucide-react";
import type { TradeRow } from "@/lib/schemas";

interface TradeAttributionProps {
  trade: TradeRow | null;
  marketQuestion: string | null;
}

function statusTone(status: string): "good" | "warn" | "neutral" | "bad" {
  if (status === "filled" || status === "paper_filled") return "good";
  if (status === "open" || status === "pending") return "warn";
  if (status === "cancelled" || status === "failed") return "bad";
  return "neutral";
}

export function TradeAttribution({
  trade,
  marketQuestion,
}: TradeAttributionProps) {
  if (!trade) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Zap
              className="h-4 w-4 text-[var(--color-trader)]"
              strokeWidth={1.8}
            />
            Trade attribution
          </CardTitle>
          <Pill tone="neutral" emphasis="outline" size="xs">
            no trades
          </Pill>
        </CardHeader>
        <CardContent>
          <EmptyState
            title="No trades executed"
            description="Once the trader places an order on Polymarket V2 with our builder code, attribution appears here."
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Zap
            className="h-4 w-4 text-[var(--color-trader)]"
            strokeWidth={1.8}
          />
          Trade attribution
        </CardTitle>
        <div className="flex items-center gap-2">
          <Pill tone={trade.side === "BUY" ? "buy" : "sell"} emphasis="soft" size="sm">
            {trade.side}
          </Pill>
          <Pill tone={statusTone(trade.status)} emphasis="outline" size="xs">
            <span className="text-mono">{trade.status}</span>
          </Pill>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <span className="text-mono text-[10px] font-medium uppercase tracking-[var(--tracking-wide)] text-fg-faint">
            Market question
          </span>
          <p className="mt-1 text-sm leading-relaxed text-fg">
            {marketQuestion ?? trade.market_id}
          </p>
        </div>

        <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl bg-[var(--color-border)]">
          <Cell label="Size">
            <span className="text-mono text-fg">{trade.size}</span>
            <span className="ml-1 text-fg-faint">USDC</span>
          </Cell>
          <Cell label="Status" emphasis="trader">
            <span className="text-mono">{trade.status}</span>
          </Cell>
        </div>

        <div>
          <span className="inline-flex items-center gap-1.5 text-mono text-[10px] font-medium uppercase tracking-[var(--tracking-wide)] text-fg-faint">
            <CreditCard className="h-3 w-3" strokeWidth={2} />
            Builder code
          </span>
          <div className="mt-1.5">
            <HashChip
              value={trade.builder_code}
              truncate={10}
              size="sm"
            />
          </div>
        </div>

        {trade.polymarket_tx && (
          <div>
            <span className="text-mono text-[10px] font-medium uppercase tracking-[var(--tracking-wide)] text-fg-faint">
              Polymarket TX
            </span>
            <div className="mt-1.5">
              <HashChip
                value={trade.polymarket_tx}
                truncate={8}
                size="sm"
              />
            </div>
          </div>
        )}

        <div className="border-t border-[var(--color-border)] pt-3 text-mono text-[10px] text-fg-faint">
          <span className="text-fg-faint">order_id · </span>
          <span className="text-fg-muted">{trade.order_id}</span>
        </div>
      </CardContent>
    </Card>
  );
}

function Cell({
  label,
  children,
  emphasis,
}: {
  label: string;
  children: React.ReactNode;
  emphasis?: "trader";
}) {
  return (
    <div className="flex flex-col gap-1 bg-[var(--color-canvas-raised)] p-3">
      <span className="text-mono text-[10px] font-medium uppercase tracking-[var(--tracking-wide)] text-fg-faint">
        {label}
      </span>
      <span
        className={`text-sm ${
          emphasis === "trader" ? "text-[var(--color-trader)]" : "text-fg"
        }`}
      >
        {children}
      </span>
    </div>
  );
}
