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
