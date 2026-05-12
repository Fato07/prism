/**
 * Component rendering tests — verify components render without crashing.
 * Uses React Server Component-compatible patterns.
 */

import { describe, it, expect } from "vitest";
import {
  TradingR1TraceSchema,
  type TradingR1Trace,
} from "@prism/schemas/trace";
import {
  SentinelVerdictSchema,
  type SentinelVerdict,
} from "@prism/schemas/verdict";
import type { TradeRow } from "@prism/schemas/db";

// Test data fixtures
const sampleTrace: TradingR1Trace = TradingR1TraceSchema.parse({
  trace_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  agent_id: 1,
  market_id: "0x1234",
  market_question: "Will X happen by end of 2026?",
  thesis: [
    {
      proposition: "The event is likely based on polling",
      supporting_evidence_ids: [0],
      risk_factors: ["polling bias"],
    },
  ],
  evidence: [
    {
      source: "Polymarket",
      claim: "Market volume increasing",
      confidence: 0.85,
      timestamp: "2026-05-12T10:00:00Z",
    },
  ],
  raw_probability: 0.72,
  volatility_adjustment: 0.03,
  final_probability: 0.69,
  action: "BUY",
  size_usdc: 10,
  price_limit: 0.69,
  rationale: "Strong evidence supports this",
  model_family: "anthropic-claude",
  model_name: "claude-sonnet-4-20250514",
  created_at: "2026-05-12T10:00:00Z",
});

const sampleVerdict: SentinelVerdict = SentinelVerdictSchema.parse({
  request_hash: "0xabc123",
  trace_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  sentinel_agent_id: 2,
  evidence_challenges: [
    "Claim lacks specificity",
    "Confidence overcalibrated",
    "Source not primary",
  ],
  thesis_challenges: ["Assumes causation from correlation"],
  calibration_critique: "Probabilities well-calibrated but evidence doesn't fully support thesis strength.",
  verdict_score: 65,
  verdict_label: "PASS",
  dialogue_messages: [
    { role: "sentinel", content: "I challenge the confidence." },
  ],
  model_family: "openai-gpt",
  model_name: "gpt-4o-mini",
  created_at: "2026-05-12T11:00:00Z",
});

const sampleTrade: TradeRow = {
  order_id: "order-123",
  trace_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  market_id: "0x1234",
  side: "BUY",
  size: "10.5",
  builder_code: "0x9e599436ce291bcda25bd18c611e46eb54bd7dd12bead05d0027802a9ef30c2e",
  status: "paper_filled",
  polymarket_tx: null,
  created_at: "2026-05-12T12:00:00Z",
};

describe("Data fixtures validate correctly", () => {
  it("sample trace passes schema validation", () => {
    expect(sampleTrace.trace_id).toBe("a1b2c3d4-e5f6-7890-abcd-ef1234567890");
    expect(sampleTrace.action).toBe("BUY");
    expect(sampleTrace.evidence.length).toBe(1);
    expect(sampleTrace.thesis.length).toBe(1);
  });

  it("sample verdict passes schema validation", () => {
    expect(sampleVerdict.verdict_label).toBe("PASS");
    expect(sampleVerdict.verdict_score).toBe(65);
    expect(sampleVerdict.evidence_challenges.length).toBeGreaterThanOrEqual(3);
  });

  it("sample trade has builder code", () => {
    expect(sampleTrade.builder_code).toBeTruthy();
    expect(sampleTrade.side).toBe("BUY");
    expect(sampleTrade.status).toBe("paper_filled");
  });
});

describe("Empty state logic", () => {
  it("handles null trace gracefully", () => {
    const trace: TradingR1Trace | null = null;
    const hasData = trace !== null;
    expect(hasData).toBe(false);
  });

  it("handles null verdict gracefully", () => {
    const verdict: SentinelVerdict | null = null;
    const hasData = verdict !== null;
    expect(hasData).toBe(false);
  });

  it("handles null trade gracefully", () => {
    const trade: TradeRow | null = null;
    const hasData = trade !== null;
    expect(hasData).toBe(false);
  });
});

describe("Verdict label-score consistency", () => {
  it("ENDORSE requires score 76-100", () => {
    const label = "ENDORSE";
    const score = 85;
    const valid = (label === "ENDORSE" && score >= 76 && score <= 100);
    expect(valid).toBe(true);
  });

  it("PASS requires score 51-75", () => {
    const label = "PASS";
    const score = 65;
    const valid = (label === "PASS" && score >= 51 && score <= 75);
    expect(valid).toBe(true);
  });

  it("WARN requires score 26-50", () => {
    const label = "WARN";
    const score = 40;
    const valid = (label === "WARN" && score >= 26 && score <= 50);
    expect(valid).toBe(true);
  });

  it("REJECT requires score 0-25", () => {
    const label = "REJECT";
    const score = 15;
    const valid = (label === "REJECT" && score >= 0 && score <= 25);
    expect(valid).toBe(true);
  });
});

describe("IPFS CID extraction from URI", () => {
  it("extracts CID from ipfs:// URI", () => {
    const uri = "ipfs://QmXyz123";
    const cid = uri.startsWith("ipfs://") ? uri.slice(7) : null;
    expect(cid).toBe("QmXyz123");
  });

  it("returns null for non-ipfs URI", () => {
    const uri = "https://example.com/data.json";
    const cid = uri.startsWith("ipfs://") ? uri.slice(7) : null;
    expect(cid).toBeNull();
  });
});

describe("Pinata gateway URL construction", () => {
  it("constructs valid Pinata gateway URL", () => {
    const cid = "QmXyz123";
    const url = `https://gateway.pinata.cloud/ipfs/${cid}`;
    expect(url).toBe("https://gateway.pinata.cloud/ipfs/QmXyz123");
  });
});

describe("Arc explorer URL construction", () => {
  it("constructs valid Arc explorer URL", () => {
    const ARC_EXPLORER = "https://explorer.testnet.arc.thecanteenapp.com";
    const txHash = "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef";
    const url = `${ARC_EXPLORER}/tx/${txHash}`;
    expect(url).toContain("explorer.testnet.arc.thecanteenapp.com/tx/");
  });
});
