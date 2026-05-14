/**
 * Agent Card schema — Zod v4 mirror of Python Pydantic model.
 */

import { z } from "zod/v4";

/** A service endpoint offered by an agent. */
export const AgentCardServiceSchema = z.object({
  name: z.string(),
  description: z.string(),
  endpoint: z.string().nullable().optional(),
});

export type AgentCardService = z.infer<typeof AgentCardServiceSchema>;

/** x402 payment configuration for sentinel-as-a-service. */
export const X402SupportSchema = z.object({
  enabled: z.boolean().default(true),
  price_usdc: z.number().default(0.01),
  recipient: z.string().nullable().optional(),
});

export type X402Support = z.infer<typeof X402SupportSchema>;

/** A2A-compatible agent card JSON for ERC-8004 IdentityRegistry. */
export const AgentCardSchema = z.object({
  name: z.string(),
  description: z.string(),
  services: z.array(AgentCardServiceSchema).min(1),
  x402Support: X402SupportSchema.default({ enabled: true, price_usdc: 0.01 }),
  active: z.boolean().default(true),
  version: z.string().default("1.0.0"),
  agent_role: z.string(),
});

export type AgentCard = z.infer<typeof AgentCardSchema>;
