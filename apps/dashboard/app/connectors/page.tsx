import type { Metadata } from "next";
import Link from "next/link";
import { GlobalNav } from "@/components/global-nav";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Pill } from "@/components/ui/pill";
import {
  ArrowRight,
  Bot,
  CheckCircle2,
  CircleDollarSign,
  KeyRound,
  Network,
  PlugZap,
  ShieldCheck,
  Workflow,
} from "lucide-react";

export const metadata: Metadata = {
  title: "Tool Connectors — Prism",
  description:
    "Connect MCP, x402, webhook, and fallback evidence tools to Prism's adversarial trust runtime.",
};

const CONNECTIONS = [
  {
    id: "connect-mcp",
    title: "MCP evidence server",
    label: "preferred",
    tone: "sentinel" as const,
    icon: Network,
    description:
      "Connect a search, research, market-data, or internal knowledge MCP server. Prism calls it only when a sentinel issue needs evidence.",
    cta: "Start MCP flow",
    href: "#connect-mcp",
    steps: ["Discover tools/list", "Choose input/result mappers", "Run fail-closed smoke", "Arm resolution loop"],
  },
  {
    id: "connect-x402",
    title: "x402 paid tool",
    label: "pay-per-use",
    tone: "verdict" as const,
    icon: CircleDollarSign,
    description:
      "Route paid APIs through a stablecoin quote → payment → tool call path so each evidence lookup can carry a cost receipt.",
    cta: "Design payment gate",
    href: "#connect-x402",
    steps: ["Quote price", "Set USDC cap", "Pay per call", "Attach receipt"],
  },
  {
    id: "connect-webhook",
    title: "Custom webhook bridge",
    label: "fallback",
    tone: "trader" as const,
    icon: Workflow,
    description:
      "Bridge tools that are not MCP-native yet. Explicit mappers normalize responses into Prism evidence artifacts.",
    cta: "Map webhook output",
    href: "#connect-webhook",
    steps: ["Register endpoint", "Select mapper", "Redact secrets", "Fail closed on errors"],
  },
  {
    id: "connect-direct",
    title: "Direct adapter reference",
    label: "demo",
    tone: "default" as const,
    icon: PlugZap,
    description:
      "Use Brave, Tavily, Exa, Firecrawl, or Parallel adapters as demos/reference normalizers when no MCP server is available.",
    cta: "Use fallback adapter",
    href: "#connect-direct",
    steps: ["Bring API key", "Pick provider", "Reuse mapper", "Treat as non-primary"],
  },
] as const;

const RUNTIME_PHASES = [
  {
    title: "Discover",
    copy: "Prism asks what the tool can do, which schemas it accepts, and whether a payment or token is required.",
  },
  {
    title: "Normalize",
    copy: "The operator chooses an explicit input mapper and result mapper. Prism never guesses arbitrary tool output.",
  },
  {
    title: "Prove",
    copy: "A smoke call verifies transport, schema, cost cap, and fail-closed behavior before the tool can affect a verdict.",
  },
  {
    title: "Arm",
    copy: "Only then can the sentinel invoke the connector during a bounded adversarial resolution round.",
  },
] as const;

const MCP_ENV_LINES = [
  "PRISM_EVIDENCE_PROVIDER=mcp",
  "PRISM_EVIDENCE_MCP_URL=https://your-tool-server.example/mcp/",
  "PRISM_EVIDENCE_MCP_TOOL=search",
  "PRISM_EVIDENCE_RESULT_MAPPER=generic_search",
  "PRISM_EVIDENCE_MCP_INPUT_MAPPER=query_limit",
  "PRISM_EVIDENCE_MCP_ALLOWED_TOOLS=search",
  "ADVERSARIAL_RESOLUTION_MAX_ROUNDS=2",
] as const;

export default function ConnectorsPage() {
  return (
    <div className="min-h-screen bg-canvas text-fg">
      <GlobalNav currentPage="connectors" />

      <main className="mx-auto max-w-7xl px-6 pb-16 pt-10">
        <section className="mb-8 grid grid-cols-1 gap-6 lg:grid-cols-[1.15fr_0.85fr]">
          <div>
            <Pill tone="sentinel" emphasis="glass" size="sm">
              <Bot className="h-3.5 w-3.5" strokeWidth={2} />
              Prism Tool Connection Studio
            </Pill>
            <h1 className="mt-4 max-w-4xl text-balance text-3xl font-semibold tracking-[var(--tracking-tight)] text-fg sm:text-5xl">
              Connect tools like agents connect ideas: through a challenged receipt.
            </h1>
            <p className="mt-4 max-w-2xl text-sm leading-6 text-fg-muted sm:text-base">
              The UI flow is not “paste an API key and hope.” Each connector gets a
              passport: transport, mapper, allowed tools, cost cap, smoke proof, and
              failure mode. The sentinel can only use it after that passport passes.
            </p>
          </div>

          <Card tone="sentinel" className="self-start">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-[var(--color-sentinel)]" strokeWidth={2} />
                Connection rule
              </CardTitle>
              <Pill tone="good" emphasis="soft" size="xs">MCP-first</Pill>
            </CardHeader>
            <CardContent className="space-y-3 text-sm leading-6 text-fg-muted">
              <p>
                External callers can propose evidence, but they cannot mark issues
                resolved. The sentinel adjudicates every connector result inside the
                issue ledger.
              </p>
              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-canvas-sunken)]/50 p-3 text-mono text-[11px] text-fg-faint">
                click connector → map schemas → smoke test → arm runtime
              </div>
            </CardContent>
          </Card>
        </section>

        <section className="mb-10 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          {CONNECTIONS.map((connection) => (
            <Card key={connection.id} tone={connection.tone} className="h-full">
              <CardHeader className="items-start">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <connection.icon className="h-4 w-4 text-[var(--color-sentinel)]" strokeWidth={2} />
                    {connection.title}
                  </CardTitle>
                  <p className="mt-1 text-xs leading-5 text-fg-faint">{connection.description}</p>
                </div>
                <Pill tone="neutral" emphasis="outline" size="xs">{connection.label}</Pill>
              </CardHeader>
              <CardContent className="flex h-full flex-col gap-4">
                <ol className="space-y-2 text-xs text-fg-muted">
                  {connection.steps.map((step, index) => (
                    <li key={step} className="flex items-center gap-2">
                      <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-[var(--color-border)] text-mono text-[10px] text-fg-faint">
                        {index + 1}
                      </span>
                      <span>{step}</span>
                    </li>
                  ))}
                </ol>
                <Link
                  href={connection.href}
                  className="mt-auto inline-flex items-center gap-1.5 text-sm font-medium text-[var(--color-sentinel)] transition-colors hover:text-fg"
                >
                  {connection.cta}
                  <ArrowRight className="h-3.5 w-3.5" strokeWidth={2} />
                </Link>
              </CardContent>
            </Card>
          ))}
        </section>

        <section className="mb-10">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Workflow className="h-4 w-4 text-[var(--color-verdict-good)]" strokeWidth={2} />
                The click flow
              </CardTitle>
              <Pill tone="sentinel" emphasis="outline" size="xs">operator-safe</Pill>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
                {RUNTIME_PHASES.map((phase, index) => (
                  <div key={phase.title} className="rounded-xl border border-[var(--color-border)] bg-[var(--color-canvas-sunken)]/40 p-4">
                    <div className="mb-3 flex items-center gap-2">
                      <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-[var(--color-sentinel)]/15 text-mono text-xs text-[var(--color-sentinel)]">
                        {index + 1}
                      </span>
                      <h2 className="text-sm font-semibold text-fg">{phase.title}</h2>
                    </div>
                    <p className="text-xs leading-5 text-fg-muted">{phase.copy}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </section>

        <section id="connect-mcp" className="mb-10 grid grid-cols-1 gap-4 lg:grid-cols-[0.9fr_1.1fr]">
          <Card tone="sentinel">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Network className="h-4 w-4 text-[var(--color-sentinel)]" strokeWidth={2} />
                MCP connector passport
              </CardTitle>
              <Pill tone="good" emphasis="soft" size="xs">ready today</Pill>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm leading-6 text-fg-muted">
                Today, the connection is armed through Railway/server env vars so
                secrets stay server-side. The UI gives the operator the exact shape
                to configure and the smoke command to prove it before activation.
              </p>
              <div className="space-y-2">
                {[
                  "Tool appears in tools/list",
                  "Input mapper matches the provider schema",
                  "Result mapper returns source-linked artifacts",
                  "Failures return no evidence and leave blockers unresolved",
                ].map((item) => (
                  <div key={item} className="flex items-center gap-2 text-sm text-fg-muted">
                    <CheckCircle2 className="h-4 w-4 text-[var(--color-success)]" strokeWidth={2} />
                    {item}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <KeyRound className="h-4 w-4 text-fg-muted" strokeWidth={2} />
                Server-side config template
              </CardTitle>
              <Pill tone="neutral" emphasis="outline" size="xs">no secrets shown</Pill>
            </CardHeader>
            <CardContent>
              <pre className="overflow-x-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-canvas-sunken)] p-4 text-mono text-xs leading-6 text-fg-muted">
                {MCP_ENV_LINES.join("\n")}
              </pre>
              <p className="mt-3 text-xs leading-5 text-fg-faint">
                Hosted Prism can turn this into a full one-click flow later: OAuth or
                bearer token capture → encrypted server-side secret → smoke receipt →
                connector passport minted for the sentinel.
              </p>
            </CardContent>
          </Card>
        </section>

        <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <ConnectorDetail
            id="connect-x402"
            title="x402 paid-tool gate"
            label="quote → pay → call"
            body="For paid tools, the connection flow starts with a quote and budget cap. The sentinel only calls the tool after payment settlement succeeds, then the returned evidence carries the payment receipt alongside source provenance."
          />
          <ConnectorDetail
            id="connect-webhook"
            title="Webhook bridge"
            label="MCP migration path"
            body="Webhook connectors are for internal tools that cannot speak MCP yet. They must still declare explicit mappers, redact secrets, and fail closed so unresolved blockers remain unresolved."
          />
          <ConnectorDetail
            id="connect-direct"
            title="Direct adapter fallback"
            label="reference only"
            body="Direct adapters are demo/reference implementations for providers like Brave, Tavily, Exa, Firecrawl, and Parallel. They prove mapper semantics, but the product path remains MCP-first."
          />
        </section>
      </main>
    </div>
  );
}

function ConnectorDetail({
  id,
  title,
  label,
  body,
}: {
  id: string;
  title: string;
  label: string;
  body: string;
}) {
  return (
    <div id={id}>
      <Card>
        <CardHeader className="items-start">
          <CardTitle>{title}</CardTitle>
          <Pill tone="neutral" emphasis="outline" size="xs">{label}</Pill>
        </CardHeader>
        <CardContent>
          <p className="text-sm leading-6 text-fg-muted">{body}</p>
        </CardContent>
      </Card>
    </div>
  );
}
