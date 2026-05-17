import { z } from "zod/v4";

import { isSafeConnectorUrl, redactConnectorUrl } from "@/lib/connector-url-policy";
import {
  ToolConnectorRowSchema,
  ToolConnectorSmokeReceiptSchema,
  ToolConnectorSmokeStatusSchema,
  ToolConnectorTransportSchema,
  type ToolConnectorRow,
  type ToolConnectorSmokeReceipt,
} from "@/lib/schemas";

export const EvidenceInputMapperSchema = z.enum([
  "query",
  "query_limit",
  "query_max_results",
  "q_count",
  "prism_evidence_request",
]);

export const EvidenceResultMapperSchema = z.enum([
  "generic_search",
  "custom_webhook",
  "firecrawl_search",
  "exa_search",
  "parallel_search",
  "tavily_search",
  "brave_search",
]);

export const CreateMcpConnectorRequestSchema = z.object({
  id: z.string().uuid().optional(),
  name: z.string().trim().min(1).max(120),
  server_url: z.string().trim().url().refine(isSafeConnectorUrl, "Connector URL is not allowed"),
  tool_name: z.string().trim().min(1).max(120),
  input_mapper: EvidenceInputMapperSchema.default("query"),
  result_mapper: EvidenceResultMapperSchema.default("generic_search"),
  allowed_tools: z.array(z.string().trim().min(1).max(120)).max(20).default([]),
  timeout_seconds: z.number().positive().max(120).default(20),
  max_results: z.number().int().min(1).max(20).default(5),
  max_usdc: z.string().regex(/^\d+(\.\d{1,6})?$/).nullable().optional(),
  bearer_token: z.string().trim().min(1).max(4096).optional(),
  fail_closed: z.boolean().default(true),
});

export type CreateMcpConnectorRequest = z.infer<typeof CreateMcpConnectorRequestSchema>;

export const ConnectorPassportSchema = z.object({
  id: z.string(),
  name: z.string(),
  connector_kind: z.literal("evidence"),
  transport: ToolConnectorTransportSchema,
  provider: z.string(),
  server_url: z.string().nullable(),
  tool_name: z.string().nullable(),
  input_mapper: z.string(),
  result_mapper: z.string(),
  allowed_tools: z.array(z.string()),
  timeout_seconds: z.number(),
  max_results: z.number().int().min(1).max(20),
  max_usdc: z.string().nullable(),
  auth_configured: z.boolean(),
  auth_secret_hint: z.string().nullable(),
  smoke_status: ToolConnectorSmokeStatusSchema,
  smoke_receipt: ToolConnectorSmokeReceiptSchema.nullable(),
  armed: z.boolean(),
  armable: z.boolean(),
  fail_closed: z.boolean(),
  status_label: z.enum(["armed", "smoke_passed", "smoke_failed", "smoke_needed", "unconfigured"]),
  created_at: z.string(),
  updated_at: z.string(),
});

export type ConnectorPassport = z.infer<typeof ConnectorPassportSchema>;

export const ConnectorManifestSchema = z.object({
  connectors: z.array(ConnectorPassportSchema),
  active_connector_id: z.string().nullable(),
  active_transport: ToolConnectorTransportSchema.nullable(),
  mcp_first: z.literal(true),
  fail_closed_default: z.literal(true),
});

export type ConnectorManifest = z.infer<typeof ConnectorManifestSchema>;

export const EMPTY_CONNECTOR_MANIFEST: ConnectorManifest = ConnectorManifestSchema.parse({
  connectors: [],
  active_connector_id: null,
  active_transport: null,
  mcp_first: true,
  fail_closed_default: true,
});

export function smokeReceiptPassed(receipt: ToolConnectorSmokeReceipt | null): boolean {
  return Boolean(
    receipt &&
      receipt.status === "passed" &&
      receipt.transport_ok &&
      receipt.tool_reachable &&
      receipt.schema_ok &&
      receipt.mapper_ok &&
      receipt.fail_closed_ok &&
      receipt.cost_cap_ok
  );
}

export function canArmConnector(row: ToolConnectorRow): boolean {
  return row.fail_closed && row.smoke_status === "passed" && smokeReceiptPassed(row.smoke_receipt);
}

export function statusLabelForConnector(row: ToolConnectorRow): ConnectorPassport["status_label"] {
  if (!row.server_url || !row.tool_name) return "unconfigured";
  if (row.armed) return "armed";
  if (canArmConnector(row)) return "smoke_passed";
  if (row.smoke_status === "failed") return "smoke_failed";
  return "smoke_needed";
}

export function toConnectorPassport(row: ToolConnectorRow): ConnectorPassport {
  const parsed = ToolConnectorRowSchema.parse(row);
  const passport = {
    id: parsed.id,
    name: parsed.name,
    connector_kind: parsed.connector_kind,
    transport: parsed.transport,
    provider: parsed.provider,
    server_url: redactConnectorUrl(parsed.server_url),
    tool_name: parsed.tool_name,
    input_mapper: parsed.input_mapper,
    result_mapper: parsed.result_mapper,
    allowed_tools: parsed.allowed_tools,
    timeout_seconds: Number(parsed.timeout_seconds),
    max_results: parsed.max_results,
    max_usdc: parsed.max_usdc,
    auth_configured: Boolean(parsed.auth_secret_ciphertext),
    auth_secret_hint: parsed.auth_secret_hint,
    smoke_status: parsed.smoke_status,
    smoke_receipt: parsed.smoke_receipt,
    armed: parsed.armed,
    armable: canArmConnector(parsed),
    fail_closed: parsed.fail_closed,
    status_label: statusLabelForConnector(parsed),
    created_at: parsed.created_at,
    updated_at: parsed.updated_at,
  } satisfies ConnectorPassport;

  return ConnectorPassportSchema.parse(passport);
}

export function buildConnectorManifest(rows: ToolConnectorRow[]): ConnectorManifest {
  const connectors = rows.map(toConnectorPassport);
  const active = connectors.find((connector) => connector.armed) ?? null;
  return ConnectorManifestSchema.parse({
    connectors,
    active_connector_id: active?.id ?? null,
    active_transport: active?.transport ?? null,
    mcp_first: true,
    fail_closed_default: true,
  });
}
