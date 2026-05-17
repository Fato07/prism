/**
 * Prism Dashboard — /dashboard
 *
 * Layout:
 *   Header        (sticky, single row)
 *   DashboardShell (client wrapper) renders one of two layouts based on
 *     the dialogue dock side (none / left / right):
 *
 *     side === "none"   : single column main, dialogue inline mid-workspace
 *     side === "left"   : dialogue full-height sticky column on the left
 *     side === "right"  : dialogue full-height sticky column on the right
 *
 *   Each interactive panel renders its own expand button in its header,
 *   opening a Dialog with the same content (no recursion via `noExpand`).
 *
 * Server component for data fetching; presentation in client subcomponents.
 */

import {
  getLatestTrace,
  getLatestValidation,
  getLatestValidatedTrace,
  getTraceById,
  getLatestTrade,
  fetchTraceFromIPFS,
  fetchVerdictFromIPFS,
  getAgents,
  getRecentVerdicts,
} from "@/lib/db";
import { getConnectorManifestForDashboard } from "@/lib/connector-store";
import { getActivityStats } from "@/lib/stats";
import { TraderPanel } from "@/components/trader-panel";
import { SentinelPanel } from "@/components/sentinel-panel";
import { ReceiptLinks } from "@/components/receipt-links";
import { TradeAttribution } from "@/components/trade-attribution";
import { ConnectorTrustStatus } from "@/components/connector-trust-status";
import { Pill } from "@/components/ui/pill";
import { LiveDot } from "@/components/ui/live-dot";
import { Separator } from "@/components/ui/separator";
import { HashChip } from "@/components/ui/hash-chip";
import { Shader } from "@/components/ui/shader";
import { AutoRefresh } from "@/components/dashboard/auto-refresh";
import { VerdictHistoryStrip } from "@/components/dashboard/verdict-history-strip";
import { ConfidenceCollision } from "@/components/dashboard/confidence-collision";
import { AdversarialDialogue } from "@/components/dashboard/adversarial-dialogue";
import { DashboardShell } from "@/components/dashboard/dashboard-shell";
import { GlobalNav } from "@/components/global-nav";
import { BrandMark } from "@/components/brands/brand-mark";
import { ArrowUpRight, Activity } from "lucide-react";
import type { TradingR1Trace, SentinelVerdict } from "@/lib/schemas";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function DashboardPage() {
  const [tradeRow, agents, stats, recentVerdicts, connectorManifest] = await Promise.all([
    getLatestTrade(),
    getAgents(),
    getActivityStats(),
    getRecentVerdicts(30),
    getConnectorManifestForDashboard(),
  ]);

  // Prefer the latest trace that has a validation (so we can always show both
  // trader reasoning and sentinel verdict). Fall back to the latest trace
  // alone if no validations exist yet.
  const validatedPair = await getLatestValidatedTrace();

  let traceRow = validatedPair?.trace ?? null;
  let validationRow = validatedPair?.validation ?? null;

  // If no validated pair exists, try the latest trace + its validation
  if (!traceRow) {
    traceRow = await getLatestTrace();
    validationRow = traceRow
      ? await getLatestValidation(traceRow.trace_id)
      : await getLatestValidation();
  }

  const tracePromise: Promise<TradingR1Trace | null> =
    traceRow?.ipfs_cid
      ? fetchTraceFromIPFS(traceRow.ipfs_cid).then(
          (c) => (c as unknown as TradingR1Trace) ?? null,
        )
      : Promise.resolve(null);

  const verdictCid = validationRow?.response_uri?.startsWith("ipfs://")
    ? validationRow.response_uri.slice(7)
    : validationRow?.response_uri ?? null;

  const verdictPromise: Promise<SentinelVerdict | null> = verdictCid
    ? fetchVerdictFromIPFS(verdictCid).then(
        (c) => (c as unknown as SentinelVerdict) ?? null,
      )
    : Promise.resolve(null);

  const [traceData, verdictData] = await Promise.all([
    tracePromise,
    verdictPromise,
  ]);

  const marketQuestion =
    (traceData as unknown as Record<string, unknown> | null)?.market_question as
      | string
      | undefined ?? null;

  const pendingValidation = traceRow && !validationRow;

  const traderAgent = agents.find((a) => a.role === "trader");
  const sentinelAgent = agents.find((a) => a.role === "sentinel");

  const registrationTxHash = traderAgent?.registration_tx_hash ?? null;
  const validationRequestTxHash = traceRow?.tx_hash ?? null;
  const validationResponseTxHash = validationRow?.tx_hash ?? null;

  const workspace = (
    <>
      <ZoneLabel
        eyebrow="Live workspace"
        tagline="Latest trace, sentinel verdict, and the gap between them"
      />
      <div className="space-y-4">
        <VerdictHistoryStrip entries={recentVerdicts} />
        <ConfidenceCollision
          traderProbability={traceData?.final_probability ?? null}
          sentinelScore={verdictData?.verdict_score ?? null}
          traderAction={traceData?.action ?? null}
          sentinelLabel={verdictData?.verdict_label ?? null}
        />
        <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
          <TraderPanel
            trace={traceData}
            ipfsCid={traceRow?.ipfs_cid ?? null}
            contentHash={traceRow?.content_hash ?? null}
          />
          <SentinelPanel
            verdict={verdictData}
            responseUri={validationRow?.response_uri ?? null}
            pendingMessage={
              pendingValidation
                ? "Trace submitted — awaiting sentinel validation"
                : undefined
            }
          />
        </div>
        <ConnectorTrustStatus manifest={connectorManifest} />
      </div>
    </>
  );

  const dialogue = (
    <AdversarialDialogue
      messages={verdictData?.dialogue_messages ?? []}
      verdictScore={verdictData?.verdict_score ?? null}
      verdictLabel={verdictData?.verdict_label ?? null}
      traderModel={traceData?.model_name ?? null}
      sentinelModel={verdictData?.model_name ?? null}
    />
  );

  const proof = (
    <>
      <ZoneLabel
        eyebrow="On-chain proof"
        tagline="Every step anchored on Arc — IdentityRegistry, ValidationRegistry, Polymarket builder attribution"
      />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ReceiptLinks
          registrationTxHash={registrationTxHash}
          validationRequestTxHash={validationRequestTxHash}
          validationResponseTxHash={validationResponseTxHash}
        />
        <TradeAttribution trade={tradeRow} marketQuestion={marketQuestion} />
      </div>
    </>
  );

  return (
    <div className="relative min-h-screen overflow-x-hidden bg-canvas text-fg">
      {/* Ambient corner shaders */}
      <div className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
        <div className="absolute -left-32 -top-32 h-96 w-96 opacity-25">
          <Shader variant="trader" intensity="subtle" />
        </div>
        <div className="absolute -bottom-32 -right-32 h-[28rem] w-[28rem] opacity-20">
          <Shader variant="sentinel" intensity="subtle" />
        </div>
      </div>

      <GlobalNav
        currentPage="dashboard"
        style={{ "--dashboard-header-h": "64px" } as React.CSSProperties}
        rightExtra={
          <>
            <Separator orientation="vertical" className="h-4 hidden sm:block" />
            <span className="hidden sm:inline-flex items-center gap-1.5">
              <AgentBadge tone="trader" label="T" agent={traderAgent} />
              <AgentBadge tone="sentinel" label="S" agent={sentinelAgent} />
            </span>
            <Separator orientation="vertical" className="h-4 hidden sm:block" />
            <AutoRefresh intervalMs={8000} />
            <Pill tone="info" emphasis="soft" size="sm" className="hidden sm:inline-flex">
              <BrandMark name="arc" size={12} aria-label="Arc" />
              <LiveDot tone="online" pulse size="sm" />
              <span className="text-mono">Arc Testnet</span>
            </Pill>
            <Pill tone="neutral" emphasis="outline" size="sm" className="hidden sm:inline-flex">
              <Activity className="h-3 w-3" strokeWidth={2} />
              <span className="text-mono">
                {stats.validations.toLocaleString()} verdicts
              </span>
            </Pill>
            <a
              href="https://testnet.arcscan.app"
              target="_blank"
              rel="noopener noreferrer"
              className="hidden sm:inline-flex items-center gap-1 text-mono text-xs text-fg-muted transition-colors hover:text-fg"
            >
              arcscan
              <ArrowUpRight className="h-3 w-3" strokeWidth={2} />
            </a>
          </>
        }
      />

      <DashboardShell
        workspace={workspace}
        proof={proof}
        dialogue={dialogue}
      />

      <DashboardFooter />
    </div>
  );
}

/* ─────────────── Zone label ─────────────── */

function ZoneLabel({ eyebrow, tagline }: { eyebrow: string; tagline?: string }) {
  return (
    <div className="mb-5 flex items-center gap-3">
      <span
        className="h-px w-8 shrink-0"
        style={{
          background:
            "linear-gradient(90deg, transparent, var(--color-trader), var(--color-sentinel))",
          opacity: 0.7,
        }}
        aria-hidden="true"
      />
      <span className="text-mono text-[11px] font-medium uppercase tracking-[var(--tracking-wide)] text-fg-muted">
        {eyebrow}
      </span>
      {tagline && (
        <>
          <Separator orientation="vertical" className="h-3" />
          <span className="text-mono text-[11px] text-fg-faint">{tagline}</span>
        </>
      )}
      <span
        className="ml-2 h-px flex-1"
        style={{
          background:
            "linear-gradient(90deg, var(--color-border), transparent)",
          opacity: 0.6,
        }}
        aria-hidden="true"
      />
    </div>
  );
}

/* ─────────────── Header ─────────────── */

function AgentBadge({
  tone,
  label,
  agent,
}: {
  tone: "trader" | "sentinel";
  label: string;
  agent?: { agent_id: number; wallet_address: string } | undefined;
}) {
  if (!agent) {
    return (
      <span className="inline-flex items-center gap-1.5">
        <LiveDot tone="offline" pulse={false} size="sm" />
        <span className="text-mono text-[11px] text-fg-faint">
          {label}: not registered
        </span>
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1.5">
      <LiveDot tone={tone} pulse size="sm" />
      <span className="text-mono text-[11px] text-fg-muted">
        <span className="text-fg">{label}</span>
        <span className="text-fg-faint">·{agent.agent_id}</span>
      </span>
      <HashChip
        value={agent.wallet_address}
        href={`https://testnet.arcscan.app/address/${agent.wallet_address}`}
        truncate={4}
        size="xs"
      />
    </span>
  );
}

/* ─────────────── Footer ─────────────── */

function DashboardFooter() {
  return (
    <footer className="border-t border-[var(--color-border)] px-6 py-5">
      <div className="mx-auto flex max-w-7xl flex-col items-start gap-2 text-mono text-[11px] text-fg-faint sm:flex-row sm:items-center sm:justify-between">
        <span>The first adversarial AI validator on ERC-8004</span>
        <span className="inline-flex flex-wrap items-center gap-x-3 gap-y-1">
          <span>Powered by</span>
          <a
            href="https://arc.network"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-fg-muted transition-colors hover:text-fg"
          >
            <BrandMark name="arc" size={12} aria-label="Arc" />
            Arc
          </a>
          <span className="text-fg-faint">·</span>
          <a
            href="https://www.circle.com"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-fg-muted transition-colors hover:text-fg"
          >
            <BrandMark name="circle" size={12} aria-label="Circle" />
            Circle
          </a>
          <span className="text-fg-faint">·</span>
          <a
            href="https://neon.tech"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-fg-muted transition-colors hover:text-fg"
          >
            <BrandMark name="neon" size={12} aria-label="Neon" />
            Neon
          </a>
          <span className="text-fg-faint">·</span>
          <a
            href="https://thecanteenapp.com"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-fg-muted transition-colors hover:text-fg"
          >
            <BrandMark name="canteen" size={12} aria-label="Canteen" />
            Canteen
          </a>
        </span>
      </div>
    </footer>
  );
}
