/**
 * Trader panel — displays the most recent Trading-R1 trace.
 * Server component — fetches trace from DB and IPFS.
 */

import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { formatRelativeTime } from "@/lib/utils";
import type { TradingR1Trace } from "@/lib/schemas";

interface TraderPanelProps {
  trace: TradingR1Trace | null;
  ipfsCid: string | null;
  contentHash: string | null;
}

function formatProbability(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function actionVariant(action: string): "buy" | "sell" | "default" {
  if (action === "BUY") return "buy";
  if (action === "SELL") return "sell";
  return "default";
}

export function TraderPanel({ trace, ipfsCid, contentHash }: TraderPanelProps) {
  if (!trace) {
    return (
      <Card className="h-full">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <span className="text-blue-400">▶</span> Trader Reasoning
          </CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState
            title="No traces yet"
            description="The trader has not generated any reasoning traces. Run the trader pipeline to populate this panel."
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="h-full overflow-auto">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span className="text-blue-400">▶</span> Trader Reasoning
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Market Question */}
        <div>
          <h4 className="mb-1 text-xs font-medium uppercase tracking-wider text-gray-500">
            Market Question
          </h4>
          <p className="text-sm font-medium text-gray-100">{trace.market_question}</p>
        </div>

        {/* Action + Probabilities */}
        <div className="flex flex-wrap items-center gap-3">
          <Badge variant={actionVariant(trace.action)}>{trace.action}</Badge>
          <span className="text-xs text-gray-500">
            Size: <span className="text-gray-300">{trace.size_usdc} USDC</span>
          </span>
          <span className="text-xs text-gray-500">
            Price Limit: <span className="text-gray-300">{trace.price_limit}</span>
          </span>
        </div>

        <div className="grid grid-cols-3 gap-2">
          <div className="rounded bg-gray-800/50 p-2 text-center">
            <div className="text-xs text-gray-500">Raw Prob</div>
            <div className="text-sm font-mono text-gray-200">{formatProbability(trace.raw_probability)}</div>
          </div>
          <div className="rounded bg-gray-800/50 p-2 text-center">
            <div className="text-xs text-gray-500">Vol Adjust</div>
            <div className="text-sm font-mono text-gray-200">{trace.volatility_adjustment.toFixed(3)}</div>
          </div>
          <div className="rounded bg-gray-800/50 p-2 text-center">
            <div className="text-xs text-gray-500">Final Prob</div>
            <div className="text-sm font-mono font-bold text-gray-100">{formatProbability(trace.final_probability)}</div>
          </div>
        </div>

        {/* Thesis Steps */}
        <div>
          <h4 className="mb-2 text-xs font-medium uppercase tracking-wider text-gray-500">
            Thesis Composition
          </h4>
          <div className="space-y-2">
            {trace.thesis.map((step, i) => (
              <div key={i} className="rounded border border-gray-800 bg-gray-800/30 p-3">
                <p className="text-sm text-gray-200">
                  <span className="mr-1 font-mono text-xs text-gray-500">Step {i + 1}:</span>
                  {step.proposition}
                </p>
                {step.supporting_evidence_ids.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap items-center gap-1">
                    <span className="text-xs text-gray-500">Evidence:</span>
                    {step.supporting_evidence_ids.map((eid) => (
                      <Badge key={eid} variant="default" className="bg-blue-900/40 text-blue-300 text-[10px] px-1.5 py-0">
                        E-{eid}
                      </Badge>
                    ))}
                  </div>
                )}
                {step.risk_factors.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {step.risk_factors.map((rf, j) => (
                      <span key={j} className="rounded bg-amber-900/30 px-1.5 py-0.5 text-xs text-amber-400">
                        ⚠ {rf}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Evidence */}
        <div>
          <h4 className="mb-2 text-xs font-medium uppercase tracking-wider text-gray-500">
            Evidence
          </h4>
          <div className="space-y-2">
            {trace.evidence.map((ev, i) => (
              <div key={i} className="rounded border border-gray-800 bg-gray-800/30 p-3">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <p className="text-sm text-gray-200">{ev.claim}</p>
                    <p className="mt-0.5 text-xs text-gray-500">Source: {ev.source}</p>
                  </div>
                  <div className="ml-2 flex flex-col items-end gap-0.5">
                    <span className="text-xs font-mono text-gray-400">
                      {(ev.confidence * 100).toFixed(0)}%
                    </span>
                    {ev.timestamp && (
                      <span className="text-[10px] text-gray-500" title={new Date(ev.timestamp).toLocaleString()}>
                        {formatRelativeTime(ev.timestamp)}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Rationale */}
        <div>
          <h4 className="mb-1 text-xs font-medium uppercase tracking-wider text-gray-500">
            Rationale
          </h4>
          <p className="text-sm text-gray-300">{trace.rationale}</p>
        </div>

        {/* IPFS + Hash links */}
        <div className="border-t border-gray-800 pt-3">
          <h4 className="mb-2 text-xs font-medium uppercase tracking-wider text-gray-500">
            On-Chain & IPFS
          </h4>
          <div className="space-y-1 text-xs">
            {ipfsCid && (
              <div>
                <span className="text-gray-500">Trace CID: </span>
                <a
                  href={`https://gateway.pinata.cloud/ipfs/${ipfsCid}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-mono text-blue-400 underline decoration-blue-400/30 hover:text-blue-300"
                >
                  {ipfsCid.slice(0, 20)}…
                </a>
              </div>
            )}
            {contentHash && (
              <div>
                <span className="text-gray-500">Content Hash: </span>
                <code className="font-mono text-gray-400">{contentHash.slice(0, 32)}…</code>
              </div>
            )}
          </div>
        </div>

        {/* Meta */}
        <div className="border-t border-gray-800 pt-3 text-xs text-gray-500">
          <div>Model: {trace.model_name} ({trace.model_family})</div>
          <div>Trace ID: <code className="font-mono">{trace.trace_id}</code></div>
          <div>Created: {new Date(trace.created_at).toLocaleString()}</div>
        </div>
      </CardContent>
    </Card>
  );
}
