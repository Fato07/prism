/**
 * Sentinel verdict schema — Zod v4 mirror of Python Pydantic model.
 */

import { z } from "zod/v4";

/** A dialogue message from the sentinel's adversarial review. */
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

/** Adversarial validation verdict from the sentinel. */
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
