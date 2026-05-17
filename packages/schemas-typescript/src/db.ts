/**
 * Database row schemas — Zod v4 mirrors of Neon DB table shapes.
 * Used by the dashboard for type-safe data fetching.
 */

import { z } from "zod/v4";

/** agents table row */
export const AgentRowSchema = z.object({
  agent_id: z.number(),
  role: z.enum(["trader", "sentinel", "oracle"]),
  wallet_address: z.string(),
  agent_card_cid: z.string().nullable(),
  created_at: z.string(),
});

export type AgentRow = z.infer<typeof AgentRowSchema>;

/** traces table row (as returned from DB) */
export const TraceRowSchema = z.object({
  trace_id: z.string(),
  agent_id: z.number(),
  market_id: z.string(),
  ipfs_cid: z.string(),
  content_hash: z.string(), // hex-encoded bytea
  created_at: z.string(),
  // Joined fields from IPFS content
  market_question: z.string().optional(),
});

export type TraceRow = z.infer<typeof TraceRowSchema>;

/** validations table row */
export const ValidationRowSchema = z.object({
  request_hash: z.string(), // hex-encoded bytea
  trace_id: z.string(),
  sentinel_agent_id: z.number(),
  verdict_score: z.number().int().min(0).max(100),
  response_uri: z.string(),
  created_at: z.string(),
  requester_address: z.string().nullable().optional(),
});

export type ValidationRow = z.infer<typeof ValidationRowSchema>;

/** trades table row */
export const TradeRowSchema = z.object({
  order_id: z.string(),
  trace_id: z.string(),
  market_id: z.string(),
  side: z.enum(["BUY", "SELL"]),
  size: z.string(), // NUMERIC returned as string
  builder_code: z.string(),
  status: z.string(),
  fill_price: z.string().nullable(), // NUMERIC returned as string, NULL until order fills
  polymarket_tx: z.string().nullable(),
  created_at: z.string(),
});

export type TradeRow = z.infer<typeof TradeRowSchema>;

/** feedback table row */
export const FeedbackRowSchema = z.object({
  id: z.number(),
  agent_id: z.number(),
  oracle_address: z.string(),
  value_fixed_point: z.number(),
  decimals: z.number(),
  tag1: z.string().nullable(),
  tag2: z.string().nullable(),
  ipfs_cid: z.string().nullable(),
  created_at: z.string(),
});

export type FeedbackRow = z.infer<typeof FeedbackRowSchema>;

/** treasury_events table row */
export const TreasuryEventRowSchema = z.object({
  id: z.string(), // UUID
  agent_id: z.number(),
  wallet_address: z.string(),
  event_type: z.enum(["park", "unpark"]),
  usdc_amount: z.string().nullable(), // NUMERIC(20,6) returned as string
  usyc_amount: z.string().nullable(), // NUMERIC(20,6) returned as string
  rationale: z.string().nullable(),
  tx_hash: z.string().nullable(),
  created_at: z.string(),
});

export type TreasuryEventRow = z.infer<typeof TreasuryEventRowSchema>;

/** tool_connectors table row */
export const ToolConnectorTransportSchema = z.enum([
  "mcp_http",
  "x402_http",
  "custom_webhook",
  "direct_adapter",
]);

export const ToolConnectorSmokeStatusSchema = z.enum([
  "not_run",
  "passed",
  "failed",
]);

export const ToolConnectorSmokeReceiptSchema = z.object({
  status: ToolConnectorSmokeStatusSchema,
  checked_at: z.string(),
  transport_ok: z.boolean(),
  tool_reachable: z.boolean(),
  schema_ok: z.boolean(),
  mapper_ok: z.boolean(),
  fail_closed_ok: z.boolean(),
  cost_cap_ok: z.boolean(),
  evidence_count: z.number().int().min(0).optional(),
  error_code: z.string().optional(),
  error_message: z.string().optional(),
});

export type ToolConnectorSmokeReceipt = z.infer<typeof ToolConnectorSmokeReceiptSchema>;

export const ToolConnectorRowSchema = z.object({
  id: z.string(),
  owner_scope: z.literal("workspace"),
  connector_kind: z.literal("evidence"),
  name: z.string(),
  transport: ToolConnectorTransportSchema,
  provider: z.string(),
  server_url: z.string().nullable(),
  tool_name: z.string().nullable(),
  input_mapper: z.string(),
  result_mapper: z.string(),
  allowed_tools: z.array(z.string()),
  timeout_seconds: z.string(),
  max_results: z.number().int().min(1).max(20),
  max_usdc: z.string().nullable(),
  auth_secret_ciphertext: z.string().nullable(),
  auth_secret_hint: z.string().nullable(),
  smoke_status: ToolConnectorSmokeStatusSchema,
  smoke_receipt: ToolConnectorSmokeReceiptSchema.nullable(),
  armed: z.boolean(),
  fail_closed: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
});

export type ToolConnectorRow = z.infer<typeof ToolConnectorRowSchema>;
