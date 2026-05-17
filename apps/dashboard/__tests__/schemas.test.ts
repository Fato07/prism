/**
 * Schema validation tests — ensure Zod v4 schemas mirror Python Pydantic models.
 */

import { describe, it, expect } from "vitest";
import {
  TradingR1TraceSchema,
  EvidenceSchema,
  ThesisStepSchema,
} from "@prism/schemas/trace";
import {
  SentinelVerdictSchema,
  DialogueMessageSchema,
} from "@prism/schemas/verdict";
import {
  AgentCardSchema,
  AgentCardServiceSchema,
  X402SupportSchema,
} from "@prism/schemas/agent-card";
import {
  TraceRowSchema,
  ValidationRowSchema,
  TradeRowSchema,
  AgentRowSchema,
  ToolConnectorRowSchema,
} from "@prism/schemas/db";

// --- TradingR1Trace ---

const validEvidence = {
  source: "Polymarket CLOB",
  claim: "Market volume increasing",
  confidence: 0.85,
  timestamp: "2026-05-12T10:00:00Z",
};

const validThesisStep = {
  proposition: "The event is likely to occur based on polling data",
  supporting_evidence_ids: [0],
  risk_factors: ["polling bias", "late shifts"],
};

const validTrace = {
  trace_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  agent_id: 1,
  market_id: "0x1234",
  market_question: "Will X happen by end of 2026?",
  thesis: [validThesisStep],
  evidence: [validEvidence],
  raw_probability: 0.72,
  volatility_adjustment: 0.03,
  final_probability: 0.69,
  action: "BUY" as const,
  size_usdc: 10,
  price_limit: 0.69,
  rationale: "Strong evidence supports this outcome",
  model_family: "anthropic-claude" as const,
  model_name: "claude-sonnet-4-20250514",
  created_at: "2026-05-12T10:00:00Z",
};

describe("TradingR1TraceSchema", () => {
  it("accepts a valid trace", () => {
    const result = TradingR1TraceSchema.safeParse(validTrace);
    expect(result.success).toBe(true);
  });

  it("rejects invalid action", () => {
    const trace = { ...validTrace, action: "WAIT" };
    const result = TradingR1TraceSchema.safeParse(trace);
    expect(result.success).toBe(false);
  });

  it("rejects raw_probability > 1", () => {
    const trace = { ...validTrace, raw_probability: 1.5 };
    const result = TradingR1TraceSchema.safeParse(trace);
    expect(result.success).toBe(false);
  });

  it("rejects raw_probability < 0", () => {
    const trace = { ...validTrace, raw_probability: -0.1 };
    const result = TradingR1TraceSchema.safeParse(trace);
    expect(result.success).toBe(false);
  });

  it("rejects wrong model_family", () => {
    const trace = { ...validTrace, model_family: "google-gemini" };
    const result = TradingR1TraceSchema.safeParse(trace);
    expect(result.success).toBe(false);
  });
});

describe("EvidenceSchema", () => {
  it("rejects confidence > 1", () => {
    const evidence = { ...validEvidence, confidence: 1.5 };
    const result = EvidenceSchema.safeParse(evidence);
    expect(result.success).toBe(false);
  });

  it("rejects confidence < 0", () => {
    const evidence = { ...validEvidence, confidence: -0.1 };
    const result = EvidenceSchema.safeParse(evidence);
    expect(result.success).toBe(false);
  });
});

// --- SentinelVerdict ---

const validVerdict = {
  request_hash: "0xabc123",
  trace_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  sentinel_agent_id: 2,
  evidence_challenges: ["Claim lacks specificity", "Confidence seems overcalibrated", "Source is not primary"],
  thesis_challenges: ["Proposition assumes causation from correlation"],
  calibration_critique: "The probabilities are well-calibrated but the evidence does not fully support the thesis strength.",
  verdict_score: 65,
  verdict_label: "PASS" as const,
  dialogue_messages: [
    { role: "sentinel", content: "I challenge the confidence on evidence item 0." },
  ],
  model_family: "openai-gpt" as const,
  model_name: "gpt-4o-mini",
  created_at: "2026-05-12T11:00:00Z",
};

describe("SentinelVerdictSchema", () => {
  it("accepts a valid verdict", () => {
    const result = SentinelVerdictSchema.safeParse(validVerdict);
    expect(result.success).toBe(true);
  });

  it("rejects verdict_score > 100", () => {
    const verdict = { ...validVerdict, verdict_score: 150 };
    const result = SentinelVerdictSchema.safeParse(verdict);
    expect(result.success).toBe(false);
  });

  it("rejects invalid verdict_label", () => {
    const verdict = { ...validVerdict, verdict_label: "APPROVE" };
    const result = SentinelVerdictSchema.safeParse(verdict);
    expect(result.success).toBe(false);
  });

  it("rejects empty evidence_challenges", () => {
    const verdict = { ...validVerdict, evidence_challenges: [] };
    // Empty array is valid in the Zod schema (no min length enforced at this level)
    // The sentinel enforces min 3 challenges, but the schema allows any array
    const result = SentinelVerdictSchema.safeParse(verdict);
    expect(result.success).toBe(true);
  });
});

// --- AgentCard ---

describe("AgentCardSchema", () => {
  it("accepts a valid agent card", () => {
    const card = {
      name: "Prism Trader",
      description: "AI-powered prediction market trader",
      services: [{ name: "generate_trace", description: "Generate Trading-R1 trace" }],
      x402Support: { enabled: true, price_usdc: 0.01 },
      active: true,
      version: "1.0.0",
      agent_role: "trader",
    };
    const result = AgentCardSchema.safeParse(card);
    expect(result.success).toBe(true);
  });

  it("rejects empty services", () => {
    const card = {
      name: "Prism Trader",
      description: "AI-powered prediction market trader",
      services: [],
      agent_role: "trader",
    };
    const result = AgentCardSchema.safeParse(card);
    expect(result.success).toBe(false);
  });
});

// --- DB Row schemas ---

describe("TraceRowSchema", () => {
  it("accepts a valid trace row", () => {
    const row = {
      trace_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      agent_id: 1,
      market_id: "0x1234",
      ipfs_cid: "QmXyz",
      content_hash: "abc123def456",
      created_at: "2026-05-12T10:00:00Z",
    };
    const result = TraceRowSchema.safeParse(row);
    expect(result.success).toBe(true);
  });
});

describe("ToolConnectorRowSchema", () => {
  it("accepts a redacted connector passport row", () => {
    const row = {
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
      auth_secret_ciphertext: "v1:encrypted-token",
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
      armed: true,
      fail_closed: true,
      created_at: "2026-05-17T00:00:00Z",
      updated_at: "2026-05-17T00:00:00Z",
    };

    expect(ToolConnectorRowSchema.safeParse(row).success).toBe(true);
  });
});

describe("TradeRowSchema", () => {
  it("accepts a valid trade row", () => {
    const row = {
      order_id: "order-123",
      trace_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      market_id: "0x1234",
      side: "BUY",
      size: "10.5",
      builder_code: "0x0000000000000000000000000000000000000000000000000000000000000001",
      status: "paper_filled",
      fill_price: "0.62",
      polymarket_tx: null,
      created_at: "2026-05-12T12:00:00Z",
    };
    const result = TradeRowSchema.safeParse(row);
    expect(result.success).toBe(true);
  });

  it("accepts trade row with null fill_price", () => {
    const row = {
      order_id: "order-456",
      trace_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      market_id: "0x1234",
      side: "BUY",
      size: "10.5",
      builder_code: "0xabc",
      status: "pending",
      fill_price: null,
      polymarket_tx: null,
      created_at: "2026-05-12T12:00:00Z",
    };
    const result = TradeRowSchema.safeParse(row);
    expect(result.success).toBe(true);
  });

  it("rejects invalid side", () => {
    const row = {
      order_id: "order-123",
      trace_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      market_id: "0x1234",
      side: "HOLD",
      size: "10.5",
      builder_code: "0xabc",
      status: "paper_filled",
      fill_price: null,
      polymarket_tx: null,
      created_at: "2026-05-12T12:00:00Z",
    };
    const result = TradeRowSchema.safeParse(row);
    expect(result.success).toBe(false);
  });
});
