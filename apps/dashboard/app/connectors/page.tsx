import type { Metadata } from "next";
import Link from "next/link";
import { BookOpen, PlugZap, ShieldCheck, Workflow } from "lucide-react";

import { GlobalNav } from "@/components/global-nav";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Pill } from "@/components/ui/pill";
import { ConnectorStudioClient } from "@/connectors/connector-studio-client";
import { EMPTY_CONNECTOR_MANIFEST } from "@/lib/connectors";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Workspace Tools — Prism",
  description:
    "Configure the smoke-tested evidence tool Sentinel may call during adversarial issue resolution.",
};

const TRUST_RULES = [
  "Sentinel calls the connector only when an issue needs evidence.",
  "Smoke must pass before the connector can be armed.",
  "Failures return no evidence and leave blockers unresolved.",
  "External callers can propose evidence, but Sentinel adjudicates resolution state.",
] as const;

export default function ConnectorsPage() {
  return (
    <div className="min-h-screen bg-canvas text-fg">
      <GlobalNav currentPage="tools" />

      <main className="mx-auto max-w-7xl px-6 pb-16 pt-10">
        <section className="mb-8 grid grid-cols-1 gap-6 lg:grid-cols-[1fr_0.8fr]">
          <div>
            <Pill tone="sentinel" emphasis="glass" size="sm">
              <PlugZap className="h-3.5 w-3.5" strokeWidth={2} />
              Workspace tools
            </Pill>
            <h1 className="mt-4 max-w-4xl text-balance text-3xl font-semibold tracking-[var(--tracking-tight)] text-fg sm:text-5xl">
              Configure the evidence route Sentinel may use when reasoning gets challenged.
            </h1>
            <p className="mt-4 max-w-2xl text-sm leading-6 text-fg-muted sm:text-base">
              Connector Passport is not a tool marketplace. It is a workspace control that lets
              Sentinel call one armed, smoke-tested MCP evidence tool during issue resolution.
            </p>
          </div>

          <Card tone="sentinel" className="self-start">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-[var(--color-sentinel)]" strokeWidth={2} />
                Runtime rule
              </CardTitle>
              <Pill tone="good" emphasis="soft" size="xs">fail closed</Pill>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2.5 text-sm leading-6 text-fg-muted">
                {TRUST_RULES.map((rule) => (
                  <li key={rule} className="flex gap-2">
                    <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-sentinel)]" />
                    <span>{rule}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </section>

        <ConnectorStudioClient initialManifest={EMPTY_CONNECTOR_MANIFEST} />

        <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Workflow className="h-4 w-4 text-[var(--color-verdict-good)]" strokeWidth={2} />
                Where this appears
              </CardTitle>
              <Pill tone="sentinel" emphasis="outline" size="xs">dashboard-first</Pill>
            </CardHeader>
            <CardContent>
              <p className="text-sm leading-6 text-fg-muted">
                The live connector state now belongs in the dashboard trust center, next to
                Sentinel challenges and the issue ledger. Use this page only to save, smoke,
                and arm the workspace evidence route.
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BookOpen className="h-4 w-4 text-fg-muted" strokeWidth={2} />
                Technical setup
              </CardTitle>
              <Pill tone="neutral" emphasis="outline" size="xs">docs</Pill>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm leading-6 text-fg-muted">
                MCP input/result mappers, deployment envs, x402 tools, webhook bridges, and
                direct adapter fallbacks live in the developer docs rather than this workspace UI.
              </p>
              <Link
                href="https://prism-docs-production.up.railway.app"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center rounded-full border border-[var(--color-border)] px-3 py-1.5 text-xs font-medium text-fg-muted transition-colors hover:text-fg"
              >
                Open docs
              </Link>
            </CardContent>
          </Card>
        </section>
      </main>
    </div>
  );
}
