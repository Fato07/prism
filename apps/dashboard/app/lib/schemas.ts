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

export const ChallengeTypeSchema = z.enum([
  "temporal",
  "source_quality",
  "relevance",
  "calibration",
  "logic",
  "market_structure",
  "risk",
]);

export const ChallengeSeveritySchema = z.enum(["minor", "material", "blocking"]);

export const ChallengeResolutionStatusSchema = z.enum([
  "open",
  "answered",
  "resolved",
  "conceded",
  "superseded",
]);

export const ResolutionStopReasonSchema = z.enum([
  "single_shot",
  "confidence_reached",
  "max_rounds",
  "unresolved_blockers",
  "insufficient_evidence",
]);

export const AdversarialChallengeSchema = z.object({
  id: z.string(),
  type: ChallengeTypeSchema,
  severity: ChallengeSeveritySchema,
  question: z.string(),
  required_resolution: z.string(),
  blocking_pass: z.boolean().default(false),
  claim_ref: z.string().nullable().optional(),
  resolution_status: ChallengeResolutionStatusSchema.default("open"),
});

export type AdversarialChallenge = z.infer<typeof AdversarialChallengeSchema>;

export const EvidenceToolReceiptSchema = z.object({
  provider: z.string(),
  tool_name: z.string().nullable().optional(),
  source_title: z.string(),
  source_url: z.string(),
  source_published_at: z.string().nullable().optional(),
  retrieved_at: z.string().nullable().optional(),
  confidence: z.number().min(0).max(1).default(0),
  adequacy_checks: z.array(z.string()).default([]),
  extractor_provider: z.string().nullable().optional(),
  extractor_tool_name: z.string().nullable().optional(),
  source_content_hash: z.string().nullable().optional(),
  source_excerpt: z.string().nullable().optional(),
  extracted_at: z.string().nullable().optional(),
  extraction_checks: z.array(z.string()).default([]),
});

export type EvidenceToolReceipt = z.infer<typeof EvidenceToolReceiptSchema>;

export const ChallengeResolutionSchema = z.object({
  challenge_id: z.string(),
  status: ChallengeResolutionStatusSchema,
  responder: z.enum(["trader", "sentinel", "evidence_tool", "system"]),
  response: z.string(),
  created_at: z.string(),
  tool_receipt: EvidenceToolReceiptSchema.nullable().optional(),
});

export type ChallengeResolution = z.infer<typeof ChallengeResolutionSchema>;

export const ResolutionRoundSchema = z.object({
  round_index: z.number().int().min(0),
  opened_challenge_ids: z.array(z.string()),
  resolved_challenge_ids: z.array(z.string()),
  prompt: z.string(),
  response: z.string(),
  created_at: z.string(),
});

export type ResolutionRound = z.infer<typeof ResolutionRoundSchema>;

export const AdversarialResolutionMetadataSchema = z.object({
  confidence: z.number().min(0).max(1),
  stop_reason: ResolutionStopReasonSchema,
  unresolved_blocking_count: z.number().int().min(0),
  unresolved_material_count: z.number().int().min(0),
  max_rounds: z.number().int().min(0),
});

export type AdversarialResolutionMetadata = z.infer<typeof AdversarialResolutionMetadataSchema>;

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
  structured_challenges: z.array(AdversarialChallengeSchema).default([]),
  challenge_resolutions: z.array(ChallengeResolutionSchema).default([]),
  resolution_rounds: z.array(ResolutionRoundSchema).default([]),
  resolution_metadata: AdversarialResolutionMetadataSchema.nullable().optional(),
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
