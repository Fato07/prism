/**
 * Tool Connectors page tests — /connectors
 */

import { describe, expect, it } from "vitest";

async function readSource(pathFromDashboard: string): Promise<string> {
  const fs = await import("node:fs/promises");
  const path = await import("node:path");
  return fs.readFile(path.resolve(__dirname, pathFromDashboard), "utf-8");
}

describe("VAL-CONNECTORS-001: connectors page describes the tool connection flow", () => {
  it("lists the four connector paths", async () => {
    const source = await readSource("../app/connectors/page.tsx");

    expect(source).toContain("MCP evidence server");
    expect(source).toContain("x402 paid tool");
    expect(source).toContain("Custom webhook bridge");
    expect(source).toContain("Direct adapter reference");
  });

  it("documents click-to-connect phases", async () => {
    const source = await readSource("../app/connectors/page.tsx");

    expect(source).toContain("Discover");
    expect(source).toContain("Normalize");
    expect(source).toContain("Prove");
    expect(source).toContain("Arm");
    expect(source).toContain("click connector → map schemas → smoke test → arm runtime");
  });

  it("keeps every connector CTA anchor backed by a page section", async () => {
    const source = await readSource("../app/connectors/page.tsx");

    for (const anchor of ["connect-mcp", "connect-x402", "connect-webhook", "connect-direct"]) {
      expect(source).toContain(`href: "#${anchor}"`);
      expect(source).toContain(`id=\"${anchor}\"`);
    }
  });

  it("includes the live connector passport client and API flow", async () => {
    const pageSource = await readSource("../app/connectors/page.tsx");
    const clientSource = await readSource("../app/connectors/connector-studio-client.tsx");

    expect(pageSource).toContain("ConnectorStudioClient");
    expect(clientSource).toContain("/api/connectors");
    expect(clientSource).toContain("Save connector passport");
    expect(clientSource).toContain("Run smoke");
    expect(clientSource).toContain("Arm connector");
  });

  it("uses MCP-first server-side env config without real secrets", async () => {
    const source = await readSource("../app/connectors/page.tsx");

    expect(source).toContain("PRISM_EVIDENCE_PROVIDER=mcp");
    expect(source).toContain("PRISM_EVIDENCE_MCP_INPUT_MAPPER=query_limit");
    expect(source).toContain("no secrets shown");
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

describe("VAL-CONNECTORS-002: global nav exposes connectors route", () => {
  it("adds /connectors to GlobalNav", async () => {
    const source = await readSource("../app/components/global-nav.tsx");

    expect(source).toContain('href: "/connectors"');
    expect(source).toContain('label: "Connectors"');
    expect(source).toContain('shortLabel: "Tools"');
  });
});
