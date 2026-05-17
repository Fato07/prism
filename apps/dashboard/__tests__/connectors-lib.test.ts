import { describe, expect, it } from "vitest";

import {
  buildConnectorManifest,
  canArmConnector,
  smokeReceiptPassed,
  statusLabelForConnector,
  toConnectorPassport,
} from "@/lib/connectors";
import type { ToolConnectorRow } from "@/lib/schemas";

const baseConnector = {
  id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  owner_scope: "workspace",
  connector_kind: "evidence",
  name: "Demo MCP evidence",
  transport: "mcp_http",
  provider: "mcp",
  server_url: "https://mcp.example.com",
  tool_name: "search",
  input_mapper: "query_limit",
  result_mapper: "generic_search",
  allowed_tools: ["search"],
  timeout_seconds: "20.000",
  max_results: 5,
  max_usdc: "0.050000",
  auth_secret_ciphertext: "v1:not-a-real-secret",
  auth_secret_hint: "…1234",
  smoke_status: "passed",
  smoke_receipt: {
    status: "passed",
    checked_at: "2026-05-17T00:00:00Z",
    transport_ok: true,
    tool_reachable: true,
    schema_ok: true,
    mapper_ok: true,
    fail_closed_ok: true,
    cost_cap_ok: true,
    evidence_count: 2,
  },
  armed: false,
  fail_closed: true,
  created_at: "2026-05-17T00:00:00Z",
  updated_at: "2026-05-17T00:00:00Z",
} satisfies ToolConnectorRow;

describe("connector passport helpers", () => {
  it("marks a fail-closed smoked connector as armable", () => {
    expect(smokeReceiptPassed(baseConnector.smoke_receipt)).toBe(true);
    expect(canArmConnector(baseConnector)).toBe(true);
    expect(statusLabelForConnector(baseConnector)).toBe("smoke_passed");
  });

  it("redacts raw ciphertext while preserving non-secret auth state", () => {
    const passport = toConnectorPassport(baseConnector);
    const serialized = JSON.stringify(passport);

    expect(passport.auth_configured).toBe(true);
    expect(passport.auth_secret_hint).toBe("…1234");
    expect(serialized).not.toContain("auth_secret_ciphertext");
    expect(serialized).not.toContain("not-a-real-secret");
  });

  it("does not arm connectors with failed smoke receipts", () => {
    const failed = {
      ...baseConnector,
      smoke_status: "failed",
      smoke_receipt: {
        ...baseConnector.smoke_receipt,
        status: "failed",
        transport_ok: false,
        tool_reachable: false,
        error_code: "transport_error",
        error_message: "server unreachable",
      },
    } satisfies ToolConnectorRow;

    expect(canArmConnector(failed)).toBe(false);
    expect(statusLabelForConnector(failed)).toBe("smoke_failed");
  });

  it("builds an MCP-first redacted manifest with a single active connector", () => {
    const armed = { ...baseConnector, armed: true } satisfies ToolConnectorRow;
    const manifest = buildConnectorManifest([armed]);

    expect(manifest.active_connector_id).toBe(armed.id);
    expect(manifest.active_transport).toBe("mcp_http");
    expect(manifest.mcp_first).toBe(true);
    expect(JSON.stringify(manifest)).not.toContain("auth_secret_ciphertext");
  });
});
