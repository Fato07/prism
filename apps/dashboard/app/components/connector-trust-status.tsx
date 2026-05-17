import Link from "next/link";
import { CheckCircle2, PlugZap, ShieldAlert, ShieldCheck } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Pill } from "@/components/ui/pill";
import type { ConnectorManifest, ConnectorPassport } from "@/lib/connectors";

interface ConnectorTrustStatusProps {
  manifest: ConnectorManifest;
}

export function ConnectorTrustStatus({ manifest }: ConnectorTrustStatusProps) {
  const activeConnector = manifest.connectors.find(
    (connector) => connector.id === manifest.active_connector_id,
  );

  return (
    <Card tone="sentinel">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <PlugZap className="h-4 w-4 text-[var(--color-sentinel)]" strokeWidth={1.8} />
          Evidence tool route
        </CardTitle>
        <Pill tone={activeConnector ? "good" : "neutral"} emphasis="soft" size="xs">
          {activeConnector ? "armed" : "fail-closed idle"}
        </Pill>
      </CardHeader>
      <CardContent className="space-y-4">
        {activeConnector ? (
          <ActiveConnectorSummary connector={activeConnector} />
        ) : (
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-canvas-sunken)]/40 p-4">
            <div className="flex items-start gap-3">
              <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-fg-faint" strokeWidth={1.8} />
              <div>
                <p className="text-sm font-medium text-fg">No evidence connector is armed.</p>
                <p className="mt-1 text-xs leading-5 text-fg-muted">
                  Sentinel will not call external tools during issue resolution. If evidence is missing,
                  blockers stay unresolved instead of silently passing.
                </p>
              </div>
            </div>
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-canvas-sunken)]/30 px-3 py-2">
          <p className="max-w-md text-xs leading-5 text-fg-faint">
            Sentinel can call an armed, smoke-tested evidence tool only when an issue needs proof.
          </p>
          <Link
            href="/connectors"
            className="inline-flex items-center rounded-full border border-[var(--color-border)] px-3 py-1.5 text-xs font-medium text-fg-muted transition-colors hover:text-fg"
          >
            Manage tools
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}

function ActiveConnectorSummary({ connector }: { connector: ConnectorPassport }) {
  const smoke = connector.smoke_receipt;

  return (
    <div className="space-y-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-canvas-sunken)]/40 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-fg">{connector.name}</p>
          <p className="mt-1 text-mono text-[11px] text-fg-faint">
            {connector.tool_name ?? "tool"} · {connector.input_mapper} → {connector.result_mapper}
          </p>
        </div>
        <Pill tone={connector.smoke_status === "passed" ? "good" : "warn"} emphasis="soft" size="xs">
          smoke {connector.smoke_status}
        </Pill>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs text-fg-muted md:grid-cols-4">
        <Metric label="fail closed" value={connector.fail_closed ? "yes" : "no"} good={connector.fail_closed} />
        <Metric label="auth" value={connector.auth_configured ? "configured" : "none"} good={connector.auth_configured} />
        <Metric label="evidence" value={String(smoke?.evidence_count ?? 0)} good={(smoke?.evidence_count ?? 0) > 0} />
        <Metric label="checked" value={smoke?.checked_at ? shortTimestamp(smoke.checked_at) : "not run"} good={connector.smoke_status === "passed"} />
      </div>
    </div>
  );
}

function Metric({ label, value, good }: { label: string; value: string; good: boolean }) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-canvas)]/35 p-2">
      <div className="mb-1 flex items-center gap-1.5 text-mono text-[10px] uppercase tracking-[var(--tracking-wide)] text-fg-faint">
        {good ? (
          <CheckCircle2 className="h-3 w-3 text-[var(--color-success)]" strokeWidth={2} />
        ) : (
          <ShieldCheck className="h-3 w-3 text-fg-faint" strokeWidth={2} />
        )}
        {label}
      </div>
      <p className="truncate text-xs font-medium text-fg-muted">{value}</p>
    </div>
  );
}

function shortTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "checked";
  return date.toISOString().slice(0, 16).replace("T", " ");
}
