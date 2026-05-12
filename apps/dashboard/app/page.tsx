/**
 * Prism Dashboard — Main Page
 *
 * Split-screen layout: trader reasoning (left), sentinel challenges (right).
 * Server components fetch from Neon DB + IPFS.
 * Bottom panel: on-chain receipt links + trade attribution.
 */

import {
  getLatestTrace,
  getLatestValidation,
  getLatestTrade,
  fetchTraceFromIPFS,
  fetchVerdictFromIPFS,
  getAgents,
} from "@/lib/db";
import { TraderPanel } from "@/components/trader-panel";
import { SentinelPanel } from "@/components/sentinel-panel";
import { ReceiptLinks } from "@/components/receipt-links";
import { TradeAttribution } from "@/components/trade-attribution";
import type { TradingR1Trace } from "@/lib/schemas";
import type { SentinelVerdict } from "@/lib/schemas";

export const dynamic = "force-dynamic";
export const revalidate = 0; // always fetch fresh data

export default async function HomePage() {
  // Fetch DB rows
  const traceRow = await getLatestTrace();
  const validationRow = traceRow
    ? await getLatestValidation(traceRow.trace_id)
    : await getLatestValidation();
  const tradeRow = await getLatestTrade();

  // Fetch full trace content from IPFS if available
  let traceData: TradingR1Trace | null = null;
  let marketQuestion: string | null = null;

  if (traceRow?.ipfs_cid) {
    const ipfsContent = await fetchTraceFromIPFS(traceRow.ipfs_cid);
    if (ipfsContent) {
      try {
        traceData = ipfsContent as unknown as TradingR1Trace;
        marketQuestion = (ipfsContent as Record<string, unknown>).market_question as string ?? null;
      } catch {
        // IPFS content doesn't match expected schema
      }
    }
  }

  // Fetch full verdict content from IPFS if available
  let verdictData: SentinelVerdict | null = null;
  if (validationRow?.response_uri) {
    const cid = validationRow.response_uri.startsWith("ipfs://")
      ? validationRow.response_uri.slice(7)
      : validationRow.response_uri;
    const ipfsContent = await fetchVerdictFromIPFS(cid);
    if (ipfsContent) {
      try {
        verdictData = ipfsContent as unknown as SentinelVerdict;
      } catch {
        // IPFS content doesn't match expected schema
      }
    }
  }

  // Determine pending state: trace exists but no verdict
  const pendingValidation = traceRow && !validationRow;

  // On-chain tx hashes from DB columns
  // Registration tx hash from agents table
  const agents = await getAgents();
  const traderAgent = agents.find((a) => a.role === "trader");
  const registrationTxHash = traderAgent?.registration_tx_hash ?? null;

  // Validation request tx hash from traces table
  const validationRequestTxHash = traceRow?.tx_hash ?? null;

  // Validation response tx hash from validations table
  const validationResponseTxHash = validationRow?.tx_hash ?? null;

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      {/* Header */}
      <header className="border-b border-gray-800 bg-gray-950/80 px-6 py-4 backdrop-blur-sm">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">
              <span className="text-blue-400">Prism</span>
            </h1>
            <p className="text-sm text-gray-500">See through the reasoning.</p>
          </div>
          <div className="flex items-center gap-4 text-xs text-gray-500">
            <span className="rounded bg-gray-800 px-2 py-1">Arc Testnet</span>
            <span className="rounded bg-gray-800 px-2 py-1">Phase 0</span>
          </div>
        </div>
      </header>

      {/* Split-Screen Main Content */}
      <main className="mx-auto max-w-7xl px-6 py-6">
        <div className="grid min-h-[calc(100vh-200px)] grid-cols-1 gap-6 lg:grid-cols-2">
          {/* Left Panel: Trader Reasoning */}
          <div className="min-w-0">
            <TraderPanel
              trace={traceData}
              ipfsCid={traceRow?.ipfs_cid ?? null}
              contentHash={traceRow?.content_hash ?? null}
            />
          </div>

          {/* Right Panel: Sentinel Challenges */}
          <div className="min-w-0">
            <SentinelPanel
              verdict={verdictData}
              responseUri={validationRow?.response_uri ?? null}
              pendingMessage={pendingValidation ? "Trace submitted — awaiting sentinel validation" : undefined}
            />
          </div>
        </div>

        {/* Bottom Panel: Receipts + Trade Attribution */}
        <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
          <ReceiptLinks
            registrationTxHash={registrationTxHash}
            validationRequestTxHash={validationRequestTxHash}
            validationResponseTxHash={validationResponseTxHash}
          />
          <TradeAttribution
            trade={tradeRow}
            marketQuestion={marketQuestion}
          />
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-800 px-6 py-4 text-center text-xs text-gray-600">
        The first adversarial AI validator on ERC-8004 · Powered by Arc &amp; Circle
      </footer>
    </div>
  );
}
