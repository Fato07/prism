/**
 * Trade attribution panel — displays builder code and market question.
 */

import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { TradeRow } from "@/lib/schemas";

interface TradeAttributionProps {
  trade: TradeRow | null;
  marketQuestion: string | null;
}

export function TradeAttribution({ trade, marketQuestion }: TradeAttributionProps) {
  if (!trade) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <span className="text-cyan-400">⚡</span> Trade Attribution
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-gray-500">No trades executed yet.</p>
        </CardContent>
      </Card>
    );
  }

  const sideVariant = trade.side === "BUY" ? "buy" : "sell";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <span className="text-cyan-400">⚡</span> Trade Attribution
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div>
          <div className="mb-1 text-xs font-medium uppercase tracking-wider text-gray-500">
            Market Question
          </div>
          <p className="text-sm text-gray-200">
            {marketQuestion ?? trade.market_id}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Badge variant={sideVariant}>{trade.side}</Badge>
          <span className="text-xs text-gray-400">
            Size: <span className="text-gray-200">{trade.size} USDC</span>
          </span>
          <span className="text-xs text-gray-400">
            Status: <span className="text-gray-200">{trade.status}</span>
          </span>
        </div>

        <div>
          <div className="mb-1 text-xs font-medium uppercase tracking-wider text-gray-500">
            Builder Code
          </div>
          <code className="block break-all rounded bg-gray-800/50 p-2 font-mono text-xs text-cyan-300">
            {trade.builder_code}
          </code>
        </div>

        {trade.polymarket_tx && (
          <div>
            <div className="mb-1 text-xs font-medium uppercase tracking-wider text-gray-500">
              Polymarket TX
            </div>
            <code className="font-mono text-xs text-gray-400">{trade.polymarket_tx}</code>
          </div>
        )}

        <div className="text-xs text-gray-500">
          Order ID: <code className="font-mono">{trade.order_id}</code>
        </div>
      </CardContent>
    </Card>
  );
}
