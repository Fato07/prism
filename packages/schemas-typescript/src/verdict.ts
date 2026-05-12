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

  model_family: z.enum(["anthropic-claude", "openai-gpt"]),
  model_name: z.string(),
  created_at: z.string(),
});

export type SentinelVerdict = z.infer<typeof SentinelVerdictSchema>;
