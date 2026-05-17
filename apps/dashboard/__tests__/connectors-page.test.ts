/**
 * Workspace tool settings tests — /connectors and dashboard connector IA.
 */

import { describe, expect, it } from "vitest";

import { connectorProviderBrand } from "@/components/provider-badge";
import type { ConnectorPassport } from "@/lib/connectors";

async function readSource(pathFromDashboard: string): Promise<string> {
  const fs = await import("node:fs/promises");
  const path = await import("node:path");
  return fs.readFile(path.resolve(__dirname, pathFromDashboard), "utf-8");
}

describe("VAL-CONNECTORS-001: connectors are workspace settings, not a marketplace page", () => {
  it("frames Connector Passport as Sentinel's evidence route", async () => {
    const source = await readSource("../app/connectors/page.tsx");

    expect(source).toContain("Workspace tools");
    expect(source).toContain("Configure the evidence route Sentinel may use");
    expect(source).toContain("not a tool marketplace");
    expect(source).toContain("save, smoke");
    expect(source).toContain("arm the workspace evidence route");
  });

  it("keeps the admin connector passport client and API flow", async () => {
    const pageSource = await readSource("../app/connectors/page.tsx");
    const clientSource = await readSource("../app/connectors/connector-studio-client.tsx");

    expect(pageSource).toContain("ConnectorStudioClient");
    expect(clientSource).toContain("/api/connectors");
    expect(clientSource).toContain("Save connector passport");
    expect(clientSource).toContain("Run smoke");
    expect(clientSource).toContain("Arm connector");
    expect(clientSource).toContain("Admin token");
    expect(clientSource).toContain("admin refresh required");
    expect(clientSource).toContain("Stored connector passports are hidden until an admin token refreshes this panel");
  });

  it("offers provider presets before exposing advanced mapper fields", async () => {
    const clientSource = await readSource("../app/connectors/connector-studio-client.tsx");

    expect(clientSource).toContain("Evidence source setup");
    expect(clientSource).toContain("Exa hosted MCP");
    expect(clientSource).toContain("https://mcp.exa.ai/mcp");
    expect(clientSource).toContain("web_search_exa");
    expect(clientSource).toContain("exa_mcp_text");
    expect(clientSource).toContain("choose → smoke → arm");
    expect(clientSource).toContain("Access details");
    expect(clientSource).toContain("Advanced tool contract");
    expect(clientSource).toContain("Presets fill this automatically");
  });

  it("moves technical setup to docs instead of product UI env templates", async () => {
    const source = await readSource("../app/connectors/page.tsx");

    expect(source).toContain("Technical setup");
    expect(source).toContain("Open docs");
    expect(source).not.toContain("PRISM_EVIDENCE_PROVIDER=mcp");
    expect(source).not.toContain("PRISM_EVIDENCE_MCP_AUTH_TOKEN");
    expect(source).not.toContain("Direct adapter reference");
    expect(source).not.toContain("x402 paid tool");
    expect(source).not.toContain("TEST_API_KEY:");
    expect(source).not.toContain("sk-");
  });

  it("page remains a server component", async () => {
    const source = await readSource("../app/connectors/page.tsx");
    const firstSignificantLine = source
      .split("\n")
      .map((line) => line.trim())
      .find((line) => line.length > 0 && !line.startsWith("/*") && !line.startsWith("*"));

    expect(firstSignificantLine).not.toBe("'use client'");
    expect(firstSignificantLine).not.toBe('"use client"');
  });
});

describe("VAL-CONNECTORS-002: dashboard surfaces tool identity inline", () => {
  it("removes the standalone evidence route card from dashboard flow", async () => {
    const source = await readSource("../app/dashboard/page.tsx");

    expect(source).toContain("getConnectorManifestForDashboard");
    expect(source).toContain("activeEvidenceConnector");
    expect(source).toContain("evidenceConnector={activeEvidenceConnector}");
    expect(source).not.toContain("ConnectorTrustStatus");
    expect(source).not.toContain("Evidence harness");
  });

  it("renders provider logos inline with Sentinel issue/tool reasoning without secrets", async () => {
    const sentinelSource = await readSource("../app/components/sentinel-panel.tsx");
    const dialogueSource = await readSource("../app/components/dashboard/adversarial-dialogue.tsx");
    const brandSource = await readSource("../app/components/provider-badge.tsx");

    expect(sentinelSource).toContain("ToolProviderChip");
    expect(sentinelSource).toContain("evidenceConnector");
    expect(dialogueSource).toContain("evidenceBrand");
    expect(dialogueSource).toContain("isToolMessage && evidenceBrand");
    expect(brandSource).toContain("/provider-logos/exa.svg");
    expect(brandSource).toContain("/provider-logos/firecrawl.svg");
    expect(brandSource).toContain("/provider-logos/tavily.svg");
    expect(brandSource).toContain("/provider-logos/brave.svg");
    expect(sentinelSource).not.toContain("auth_secret_ciphertext");
    expect(dialogueSource).not.toContain("auth_secret_ciphertext");
    expect(sentinelSource).not.toContain("CONNECTOR_SECRETS_KEY");
    expect(dialogueSource).not.toContain("bearer_token");
  });
});

describe("VAL-CONNECTORS-003: provider badges make tool routes human-readable", () => {
  const baseConnector: ConnectorPassport = {
    id: "connector-1",
    name: "Custom MCP evidence",
    connector_kind: "evidence",
    transport: "mcp_http",
    provider: "mcp",
    server_url: null,
    tool_name: "search",
    input_mapper: "query_limit",
    result_mapper: "generic_search",
    allowed_tools: ["search"],
    timeout_seconds: 20,
    max_results: 5,
    max_usdc: null,
    auth_configured: false,
    auth_secret_hint: null,
    smoke_status: "passed",
    smoke_receipt: null,
    armed: true,
    armable: true,
    fail_closed: true,
    status_label: "armed",
    created_at: "2026-05-17T00:00:00Z",
    updated_at: "2026-05-17T00:00:00Z",
  };

  it("maps known evidence providers to local logo assets", () => {
    expect(connectorProviderBrand({ ...baseConnector, name: "Exa hosted MCP evidence", tool_name: "web_search_exa", result_mapper: "exa_mcp_text" }).logoSrc).toBe("/provider-logos/exa.svg");
    expect(connectorProviderBrand({ ...baseConnector, name: "Firecrawl search", result_mapper: "firecrawl_search" }).logoSrc).toBe("/provider-logos/firecrawl.svg");
    expect(connectorProviderBrand({ ...baseConnector, name: "Tavily search", result_mapper: "tavily_search" }).logoSrc).toBe("/provider-logos/tavily.svg");
    expect(connectorProviderBrand({ ...baseConnector, name: "Brave search", result_mapper: "brave_search" }).logoSrc).toBe("/provider-logos/brave.svg");
    expect(connectorProviderBrand({ ...baseConnector, name: "Parallel search", result_mapper: "parallel_search" }).logoSrc).toBe("/provider-logos/parallel.svg");
    expect(connectorProviderBrand({ ...baseConnector, name: "Webhook bridge", transport: "custom_webhook", result_mapper: "custom_webhook" }).logoSrc).toBe("/provider-logos/webhook.svg");
  });

  it("keeps provider logo assets local", async () => {
    const fs = await import("node:fs/promises");
    const path = await import("node:path");
    const logoDir = path.resolve(__dirname, "../public/provider-logos");
    const logos = ["exa.svg", "firecrawl.svg", "tavily.svg", "brave.svg", "parallel.svg", "custom-mcp.svg", "webhook.svg"];

    for (const logo of logos) {
      await expect(fs.stat(path.join(logoDir, logo))).resolves.toBeTruthy();
    }
  });
});

describe("VAL-CONNECTORS-004: global nav de-emphasizes admin surface", () => {
  it("labels /connectors as Tools, not a marketplace-like Connectors page", async () => {
    const source = await readSource("../app/components/global-nav.tsx");

    expect(source).toContain('href: "/connectors"');
    expect(source).toContain('label: "Tools"');
    expect(source).toContain('shortLabel: "Tools"');
    expect(source).not.toContain('label: "Connectors"');
  });
});
