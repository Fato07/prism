/**
 * Trading-R1 reasoning trace schema — Zod v4 mirror of Python Pydantic model.
 */

import { z } from "zod/v4";
import { EvidenceToolReceiptSchema } from "./verdict";

/** A single piece of evidence supporting the thesis. */
export const EvidenceSchema = z.object({
  source: z.string(),
  claim: z.string(),
  confidence: z.number().min(0).max(1),
  timestamp: z.string(),
});

export type Evidence = z.infer<typeof EvidenceSchema>;

/** A single step in the thesis composition. */
export const ThesisStepSchema = z.object({
  proposition: z.string(),
  supporting_evidence_ids: z.array(z.number()),
  risk_factors: z.array(z.string()),
});

export type ThesisStep = z.infer<typeof ThesisStepSchema>;

/** Complete Trading-R1 structured reasoning trace. */
export const TradingR1TraceSchema = z.object({
  trace_id: z.string(),
  agent_id: z.number(),
  market_id: z.string(),
  market_question: z.string(),

  thesis: z.array(ThesisStepSchema),
  evidence: z.array(EvidenceSchema),

  // Tool-sourced evidence receipts — proves which evidence came from
  // real tools (verifiable) vs which the LLM invented (unverifiable).
  // Defaults to empty list for backward compatibility with old traces.
  evidence_receipts: z.array(EvidenceToolReceiptSchema).default([]),

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
