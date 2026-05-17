/**
 * Workspace tool settings tests — /connectors and dashboard connector IA.
 */

import { describe, expect, it } from "vitest";

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
  });

  it("offers provider presets before exposing advanced mapper fields", async () => {
    const clientSource = await readSource("../app/connectors/connector-studio-client.tsx");

    expect(clientSource).toContain("Evidence source setup");
    expect(clientSource).toContain("Exa hosted MCP");
    expect(clientSource).toContain("https://mcp.exa.ai/mcp");
    expect(clientSource).toContain("web_search_exa");
    expect(clientSource).toContain("exa_mcp_text");
    expect(clientSource).toContain("choose → smoke → arm");
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

describe("VAL-CONNECTORS-002: dashboard owns live connector trust state", () => {
  it("adds connector trust status to dashboard near Sentinel reasoning", async () => {
    const source = await readSource("../app/dashboard/page.tsx");

    expect(source).toContain("ConnectorTrustStatus");
    expect(source).toContain("getConnectorManifestForDashboard");
    expect(source).toContain("<ConnectorTrustStatus manifest={connectorManifest} />");
  });

  it("connector status component summarizes fail-closed armed tool state without secrets", async () => {
    const source = await readSource("../app/components/connector-trust-status.tsx");

    expect(source).toContain("Evidence tool route");
    expect(source).toContain("Sentinel can call an armed, smoke-tested evidence tool only when an issue needs proof.");
    expect(source).toContain("Manage tools");
    expect(source).not.toContain("auth_secret_ciphertext");
    expect(source).not.toContain("CONNECTOR_SECRETS_KEY");
    expect(source).not.toContain("bearer_token");
  });
});

describe("VAL-CONNECTORS-003: global nav de-emphasizes admin surface", () => {
  it("labels /connectors as Tools, not a marketplace-like Connectors page", async () => {
    const source = await readSource("../app/components/global-nav.tsx");

    expect(source).toContain('href: "/connectors"');
    expect(source).toContain('label: "Tools"');
    expect(source).toContain('shortLabel: "Tools"');
    expect(source).not.toContain('label: "Connectors"');
  });
});
