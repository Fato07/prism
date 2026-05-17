"use client";

import { useMemo, useState, type FormEvent, type ReactNode } from "react";
import { Loader2, PlayCircle, RadioTower, ShieldCheck } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Pill } from "@/components/ui/pill";
import type { ConnectorManifest, ConnectorPassport } from "@/lib/connectors";

const INPUT_MAPPERS = ["query", "query_limit", "query_max_results", "q_count", "prism_evidence_request"] as const;
const INPUT_CLASS = "w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-canvas-sunken)] px-3 py-2 text-sm text-fg outline-none transition-colors placeholder:text-fg-faint focus:border-[var(--color-sentinel)]";

const RESULT_MAPPERS = [
  "generic_search",
  "custom_webhook",
  "firecrawl_search",
  "exa_search",
  "parallel_search",
  "tavily_search",
  "brave_search",
] as const;

const EMPTY_FORM = {
  name: "Primary MCP evidence server",
  server_url: "",
  tool_name: "search",
  input_mapper: "query_limit",
  result_mapper: "generic_search",
  allowed_tools: "search",
  timeout_seconds: "20",
  max_results: "5",
  max_usdc: "0.05",
  bearer_token: "",
  fail_closed: true,
};

type StudioAction = "save" | "smoke" | "arm" | "refresh";

export function ConnectorStudioClient({ initialManifest }: { initialManifest: ConnectorManifest }) {
  const [manifest, setManifest] = useState(initialManifest);
  const [form, setForm] = useState(EMPTY_FORM);
  const [adminToken, setAdminToken] = useState("");
  const [busyAction, setBusyAction] = useState<StudioAction | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const activeConnector = useMemo(
    () => manifest.connectors.find((connector) => connector.id === manifest.active_connector_id) ?? null,
    [manifest]
  );

  async function refreshManifest(): Promise<void> {
    const response = await fetch("/api/connectors", { method: "GET", headers: adminHeaders(adminToken) });
    if (!response.ok) throw new Error("Unable to refresh connectors");
    setManifest((await response.json()) as ConnectorManifest);
  }

  async function handleRefresh(): Promise<void> {
    setBusyAction("refresh");
    setMessage(null);
    try {
      await refreshManifest();
      setMessage("Connector passports refreshed.");
    } catch {
      setMessage("Refresh failed. Enter the connector admin token first.");
    } finally {
      setBusyAction(null);
    }
  }

  async function handleSave(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setBusyAction("save");
    setMessage(null);
    try {
      const response = await fetch("/api/connectors", {
        method: "POST",
        headers: { "content-type": "application/json", ...adminHeaders(adminToken) },
        body: JSON.stringify({
          name: form.name,
          server_url: form.server_url,
          tool_name: form.tool_name,
          input_mapper: form.input_mapper,
          result_mapper: form.result_mapper,
          allowed_tools: form.allowed_tools.split(",").map((tool) => tool.trim()).filter(Boolean),
          timeout_seconds: Number(form.timeout_seconds),
          max_results: Number(form.max_results),
          max_usdc: form.max_usdc || null,
          bearer_token: form.bearer_token || undefined,
          fail_closed: form.fail_closed,
        }),
      });
      if (!response.ok) throw new Error("Connector save failed");
      setForm((current) => ({ ...current, bearer_token: "" }));
      await refreshManifest();
      setMessage("Connector saved. Run smoke before arming.");
    } catch {
      setMessage("Connector save failed. Check URL, mapper, and server envs.");
    } finally {
      setBusyAction(null);
    }
  }

  async function runAction(id: string, action: "smoke" | "arm"): Promise<void> {
    setBusyAction(action);
    setMessage(null);
    try {
      const response = await fetch(`/api/connectors/${id}/${action}`, { method: "POST", headers: adminHeaders(adminToken) });
      if (!response.ok) throw new Error(`${action} failed`);
      await refreshManifest();
      setMessage(action === "smoke" ? "Smoke receipt stored." : "Connector armed for sentinel resolution.");
    } catch {
      setMessage(action === "smoke" ? "Smoke failed. Connector remains unarmed." : "Arm failed. Smoke must pass first.");
    } finally {
      setBusyAction(null);
    }
  }

  return (
    <section className="mb-10 grid grid-cols-1 gap-4 xl:grid-cols-[0.95fr_1.05fr]">
      <div id="connector-passports">
        <Card tone="sentinel">
          <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <RadioTower className="h-4 w-4 text-[var(--color-sentinel)]" strokeWidth={2} />
            Live connector passports
          </CardTitle>
          <Pill tone={activeConnector ? "good" : "neutral"} emphasis="soft" size="xs">
            {activeConnector ? "armed" : "fail-closed idle"}
          </Pill>
        </CardHeader>
        <CardContent className="space-y-4">
          <button className="inline-flex w-fit items-center gap-2 rounded-full border border-[var(--color-border)] px-3 py-1.5 text-xs font-medium text-fg-muted hover:text-fg disabled:opacity-50" disabled={busyAction !== null} onClick={handleRefresh} type="button">
            {busyAction === "refresh" ? "Refreshing…" : "Refresh passports"}
          </button>
          {manifest.connectors.length === 0 ? (
            <div className="rounded-xl border border-dashed border-[var(--color-border)] bg-[var(--color-canvas-sunken)]/40 p-4 text-sm leading-6 text-fg-muted">
              No connector passport is stored yet. Save an MCP connector, run smoke, then arm it for sentinel issue resolution.
            </div>
          ) : (
            manifest.connectors.map((connector) => (
              <ConnectorPassportCard
                key={connector.id}
                connector={connector}
                busyAction={busyAction}
                onSmoke={() => runAction(connector.id, "smoke")}
                onArm={() => runAction(connector.id, "arm")}
              />
            ))
          )}
          {message ? <p className="text-xs leading-5 text-fg-faint">{message}</p> : null}
          </CardContent>
        </Card>
      </div>

      <div id="connect-mcp-live">
        <Card>
          <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-[var(--color-verdict-good)]" strokeWidth={2} />
            Create MCP passport
          </CardTitle>
          <Pill tone="sentinel" emphasis="outline" size="xs">encrypted token capture</Pill>
        </CardHeader>
        <CardContent>
          <form className="grid grid-cols-1 gap-3 md:grid-cols-2" onSubmit={handleSave}>
            <Field label="Admin token">
              <input className={INPUT_CLASS} type="password" placeholder="required for connector control plane" value={adminToken} onChange={(event) => setAdminToken(event.target.value)} />
            </Field>
            <Field label="Name">
              <input className={INPUT_CLASS} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
            </Field>
            <Field label="MCP HTTP URL">
              <input className={INPUT_CLASS} placeholder="https://server.example/mcp" value={form.server_url} onChange={(event) => setForm({ ...form, server_url: event.target.value })} />
            </Field>
            <Field label="Tool name">
              <input className={INPUT_CLASS} value={form.tool_name} onChange={(event) => setForm({ ...form, tool_name: event.target.value })} />
            </Field>
            <Field label="Allowed tools">
              <input className={INPUT_CLASS} value={form.allowed_tools} onChange={(event) => setForm({ ...form, allowed_tools: event.target.value })} />
            </Field>
            <Field label="Input mapper">
              <select className={INPUT_CLASS} value={form.input_mapper} onChange={(event) => setForm({ ...form, input_mapper: event.target.value })}>
                {INPUT_MAPPERS.map((mapper) => <option key={mapper}>{mapper}</option>)}
              </select>
            </Field>
            <Field label="Result mapper">
              <select className={INPUT_CLASS} value={form.result_mapper} onChange={(event) => setForm({ ...form, result_mapper: event.target.value })}>
                {RESULT_MAPPERS.map((mapper) => <option key={mapper}>{mapper}</option>)}
              </select>
            </Field>
            <Field label="Timeout seconds">
              <input className={INPUT_CLASS} type="number" min="1" max="120" value={form.timeout_seconds} onChange={(event) => setForm({ ...form, timeout_seconds: event.target.value })} />
            </Field>
            <Field label="Max results">
              <input className={INPUT_CLASS} type="number" min="1" max="20" value={form.max_results} onChange={(event) => setForm({ ...form, max_results: event.target.value })} />
            </Field>
            <Field label="USDC cost cap">
              <input className={INPUT_CLASS} value={form.max_usdc} onChange={(event) => setForm({ ...form, max_usdc: event.target.value })} />
            </Field>
            <Field label="Bearer token">
              <input className={INPUT_CLASS} type="password" placeholder="stored encrypted; never echoed" value={form.bearer_token} onChange={(event) => setForm({ ...form, bearer_token: event.target.value })} />
            </Field>
            <label className="md:col-span-2 flex items-center gap-2 text-xs text-fg-muted">
              <input type="checkbox" checked={form.fail_closed} onChange={(event) => setForm({ ...form, fail_closed: event.target.checked })} />
              Fail closed: failed tools return no evidence and leave issues unresolved.
            </label>
            <button className="md:col-span-2 inline-flex items-center justify-center gap-2 rounded-full bg-[var(--color-sentinel)] px-4 py-2 text-sm font-semibold text-white transition-opacity disabled:opacity-50" type="submit" disabled={busyAction !== null}>
              {busyAction === "save" ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}
              Save connector passport
            </button>
          </form>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}

function adminHeaders(adminToken: string): HeadersInit {
  return adminToken.trim() ? { authorization: `Bearer ${adminToken.trim()}` } : {};
}

function ConnectorPassportCard({
  connector,
  busyAction,
  onSmoke,
  onArm,
}: {
  connector: ConnectorPassport;
  busyAction: StudioAction | null;
  onSmoke: () => void;
  onArm: () => void;
}) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-canvas-sunken)]/40 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-fg">{connector.name}</h3>
          <p className="mt-1 text-xs text-fg-faint">{connector.transport} · {connector.tool_name ?? "no tool"} · {connector.input_mapper} → {connector.result_mapper}</p>
        </div>
        <Pill tone={connector.armed ? "good" : connector.smoke_status === "failed" ? "bad" : "neutral"} emphasis="soft" size="xs">
          {connector.status_label}
        </Pill>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-fg-muted md:grid-cols-4">
        <span>auth: {connector.auth_configured ? `configured ${connector.auth_secret_hint ?? ""}` : "none"}</span>
        <span>tools: {connector.allowed_tools.join(", ") || "tool only"}</span>
        <span>smoke: {connector.smoke_status}</span>
        <span>fail closed: {connector.fail_closed ? "yes" : "no"}</span>
      </div>
      {connector.smoke_receipt ? (
        <div className="mt-3 rounded-lg border border-[var(--color-border)] p-3 text-mono text-[11px] leading-5 text-fg-faint">
          transport={String(connector.smoke_receipt.transport_ok)} schema={String(connector.smoke_receipt.schema_ok)} mapper={String(connector.smoke_receipt.mapper_ok)} evidence={connector.smoke_receipt.evidence_count ?? 0}
        </div>
      ) : null}
      <div className="mt-4 flex flex-wrap gap-2">
        <button className="rounded-full border border-[var(--color-border)] px-3 py-1.5 text-xs font-medium text-fg-muted hover:text-fg disabled:opacity-50" disabled={busyAction !== null} onClick={onSmoke} type="button">
          {busyAction === "smoke" ? "Smoking…" : "Run smoke"}
        </button>
        <button className="rounded-full bg-[var(--color-verdict-good)] px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50" disabled={busyAction !== null || !connector.armable} onClick={onArm} type="button">
          {busyAction === "arm" ? "Arming…" : "Arm connector"}
        </button>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="space-y-1 text-xs font-medium text-fg-muted">
      <span>{label}</span>
      {children}
    </label>
  );
}
