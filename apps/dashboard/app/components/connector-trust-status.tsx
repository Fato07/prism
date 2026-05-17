import Link from "next/link";
import { CheckCircle2, ShieldAlert, ShieldCheck, SlidersHorizontal } from "lucide-react";

import { ProviderBadge, connectorProviderBrand } from "@/components/provider-badge";
import { Pill } from "@/components/ui/pill";
import { getToolResolutionSummary } from "@/lib/issue-ledger";
import type { ConnectorManifest, ConnectorPassport } from "@/lib/connectors";
import type { SentinelVerdict } from "@/lib/schemas";

interface ConnectorTrustStatusProps {
  manifest: ConnectorManifest;
  verdict?: SentinelVerdict | null;
}

export function ConnectorTrustStatus({ manifest, verdict }: ConnectorTrustStatusProps) {
  const activeConnector = manifest.connectors.find(
    (connector) => connector.id === manifest.active_connector_id,
  );
  const brand = connectorProviderBrand(activeConnector);
  const toolSummary = verdict ? getToolResolutionSummary(verdict) : null;

  return (
    <section
      aria-label="Evidence tool route"
      className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-canvas-raised)]/55 px-4 py-3 shadow-[var(--shadow-soft)] backdrop-blur-sm transition-colors hover:border-[var(--color-border-strong)]"
    >
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <ProviderBadge brand={brand} size="lg" showName={false} />
          <div className="min-w-0">
            <div className="mb-1 flex flex-wrap items-center gap-2">
              <span className="text-mono text-[10px] font-medium uppercase tracking-[var(--tracking-wide)] text-fg-faint">
                Evidence harness
              </span>
              <Pill tone={activeConnector ? "good" : "neutral"} emphasis="soft" size="xs">
                {activeConnector ? "armed route" : "fail-closed idle"}
              </Pill>
            </div>
            <h3 className="truncate text-base font-semibold tracking-[var(--tracking-tight)] text-fg">
              {activeConnector ? `${brand.name} evidence route` : "No evidence connector armed"}
            </h3>
            <p className="mt-1 hidden max-w-2xl text-xs leading-5 text-fg-muted sm:block">
              {activeConnector
                ? "Sentinel can call this smoke-tested tool only when an issue needs proof. Bad or missing evidence still leaves issues unresolved."
                : "Sentinel will not call external tools during issue resolution. Missing evidence stays fail-closed instead of silently passing."}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 lg:justify-end">
          {activeConnector ? (
            <ActiveRouteChips connector={activeConnector} toolSummary={toolSummary} />
          ) : (
            <Pill tone="warn" emphasis="soft" size="xs">
              <ShieldAlert className="h-3 w-3" strokeWidth={2} />
              no armed source
            </Pill>
          )}
          <Link
            href="/connectors"
            className="inline-flex items-center gap-1.5 rounded-full border border-[var(--color-border)] px-3 py-1.5 text-xs font-medium text-fg-muted transition-colors hover:text-fg"
          >
            <SlidersHorizontal className="h-3 w-3" strokeWidth={2} />
            Manage tools
          </Link>
        </div>
      </div>
    </section>
  );
}

function ActiveRouteChips({
  connector,
  toolSummary,
}: {
  connector: ConnectorPassport;
  toolSummary: ReturnType<typeof getToolResolutionSummary> | null;
}) {
  const smokePassed = connector.smoke_status === "passed";

  return (
    <>
      <Pill tone={smokePassed ? "good" : "warn"} emphasis="soft" size="xs">
        {smokePassed ? <CheckCircle2 className="h-3 w-3" strokeWidth={2} /> : <ShieldAlert className="h-3 w-3" strokeWidth={2} />}
        smoke {connector.smoke_status}
      </Pill>
      <Pill tone={connector.fail_closed ? "good" : "warn"} emphasis="soft" size="xs">
        <ShieldCheck className="h-3 w-3" strokeWidth={2} />
        fail-closed {connector.fail_closed ? "on" : "off"}
      </Pill>
      {toolSummary ? (
        <>
          <Pill tone={toolSummary.resolvedCount > 0 ? "good" : "neutral"} emphasis="outline" size="xs">
            {toolSummary.resolvedCount} resolved
          </Pill>
          {toolSummary.noEvidenceCount > 0 && (
            <Pill tone="warn" emphasis="outline" size="xs">
              {toolSummary.noEvidenceCount} fail-closed
            </Pill>
          )}
        </>
      ) : (
        <Pill tone="neutral" emphasis="outline" size="xs">
          smoke evidence {connector.smoke_receipt?.evidence_count ?? 0}
        </Pill>
      )}
    </>
  );
}
