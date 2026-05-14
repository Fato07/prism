/**
 * Zod v4 schemas for the Prism dashboard.
 * Local copies that mirror packages/schemas-typescript for Turbopack compatibility.
 * The source of truth remains packages/schemas-typescript.
 */

import { z } from "zod/v4";

// --- Trace schemas ---

export const EvidenceSchema = z.object({
  source: z.string(),
  claim: z.string(),
  confidence: z.number().min(0).max(1),
  timestamp: z.string(),
});

export type Evidence = z.infer<typeof EvidenceSchema>;

export const ThesisStepSchema = z.object({
  proposition: z.string(),
  supporting_evidence_ids: z.array(z.number()),
  risk_factors: z.array(z.string()),
});

export type ThesisStep = z.infer<typeof ThesisStepSchema>;

export const TradingR1TraceSchema = z.object({
  trace_id: z.string(),
  agent_id: z.number(),
  market_id: z.string(),
  market_question: z.string(),
  thesis: z.array(ThesisStepSchema),
  evidence: z.array(EvidenceSchema),
  raw_probability: z.number().min(0).max(1),
  volatility_adjustment: z.number(),
  final_probability: z.number().min(0).max(1),
  action: z.enum(["BUY", "SELL", "HOLD"]),
  size_usdc: z.number(),
  price_limit: z.number(),
  rationale: z.string(),
  model_family: z.enum(["anthropic-claude", "openai-gpt"]),
  model_name: z.string(),
  created_at: z.string(),
});

export type TradingR1Trace = z.infer<typeof TradingR1TraceSchema>;

// --- Verdict schemas ---

export const DialogueMessageSchema = z.object({
  role: z.string(),
  content: z.string(),
});

export type DialogueMessage = z.infer<typeof DialogueMessageSchema>;

export const SentinelVerdictSchema = z.object({
  request_hash: z.string(),
  trace_id: z.string(),
  sentinel_agent_id: z.number(),
  evidence_challenges: z.array(z.string()),
  thesis_challenges: z.array(z.string()),
  calibration_critique: z.string(),
  verdict_score: z.number().int().min(0).max(100),
  verdict_label: z.enum(["REJECT", "WARN", "PASS", "ENDORSE"]),
  dialogue_messages: z.array(DialogueMessageSchema),
  model_family: z.enum(["anthropic-claude", "openai-gpt"]),
  model_name: z.string(),
  created_at: z.string(),
});

export type SentinelVerdict = z.infer<typeof SentinelVerdictSchema>;

// --- Agent Card schemas ---

export const AgentCardServiceSchema = z.object({
  name: z.string(),
  description: z.string(),
  endpoint: z.string().nullable().optional(),
});

export type AgentCardService = z.infer<typeof AgentCardServiceSchema>;

export const X402SupportSchema = z.object({
  enabled: z.boolean(),
  price_usdc: z.number(),
  recipient: z.string().nullable().optional(),
});

export type X402Support = z.infer<typeof X402SupportSchema>;

export const AgentCardSchema = z.object({
  name: z.string(),
  description: z.string(),
  services: z.array(AgentCardServiceSchema).min(1),
  x402Support: X402SupportSchema.optional(),
  active: z.boolean().optional(),
  version: z.string().optional(),
  agent_role: z.string(),
});

export type AgentCard = z.infer<typeof AgentCardSchema>;

// --- DB Row schemas ---

export const AgentRowSchema = z.object({
  agent_id: z.number(),
  role: z.enum(["trader", "sentinel", "oracle"]),
  wallet_address: z.string(),
  agent_card_cid: z.string().nullable(),
  registration_tx_hash: z.string().nullable(),
  created_at: z.string(),
});

export type AgentRow = z.infer<typeof AgentRowSchema>;

export const TraceRowSchema = z.object({
  trace_id: z.string(),
  agent_id: z.number(),
  market_id: z.string(),
  ipfs_cid: z.string(),
  content_hash: z.string(),
  tx_hash: z.string().nullable(),
  created_at: z.string(),
});

export type TraceRow = z.infer<typeof TraceRowSchema>;

export const ValidationRowSchema = z.object({
  request_hash: z.string(),
  trace_id: z.string(),
  sentinel_agent_id: z.number(),
  verdict_score: z.number().int().min(0).max(100),
  response_uri: z.string(),
  tx_hash: z.string().nullable(),
  created_at: z.string(),
});

export type ValidationRow = z.infer<typeof ValidationRowSchema>;

export const TradeRowSchema = z.object({
  order_id: z.string(),
  trace_id: z.string(),
  market_id: z.string(),
  side: z.enum(["BUY", "SELL"]),
  size: z.string(),
  builder_code: z.string(),
  status: z.string(),
  fill_price: z.string().nullable(),
  polymarket_tx: z.string().nullable(),
  created_at: z.string(),
});

export type TradeRow = z.infer<typeof TradeRowSchema>;

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

export const TreasuryEventRowSchema = z.object({
  id: z.string(),
  agent_id: z.number(),
  wallet_address: z.string(),
  event_type: z.enum(["park", "unpark"]),
  usdc_amount: z.string().nullable(),
  usyc_amount: z.string().nullable(),
  rationale: z.string().nullable(),
  tx_hash: z.string().nullable(),
  created_at: z.string(),
});

export type TreasuryEventRow = z.infer<typeof TreasuryEventRowSchema>;
