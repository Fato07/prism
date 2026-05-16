/**
 * Public API helpers — CLI/reporting contract.
 */

import { describe, expect, it } from "vitest";
import {
  clampPublicLimit,
  computeTraceMetrics,
  readinessFromMetrics,
  verdictLabelFromScore,
  warningsFromMetrics,
} from "../app/lib/public-api";

function sampleTrace() {
  return {
    trace_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    market_id: "0xmarket",
    market_question: "Will Polymarket volume exceed $1B this month?",
    thesis: [
      {
        proposition: "Volume trend supports the trade.",
        supporting_evidence_ids: [0, 1],
        risk_factors: ["Invalidated if volume falls for three consecutive sessions."],
      },
    ],
    evidence: [
      { source: "Polymarket", claim: "Volume up", confidence: 0.72 },
      { source: "Dune", claim: "Market maker activity up", confidence: 0.68 },
    ],
    raw_probability: 0.62,
    final_probability: 0.58,
    rationale: "Position stays small and exit if market volume fails to persist.",
  };
}

describe("VAL-PUBLIC-001: verdict label derivation", () => {
  it("derives labels from score bands", () => {
    expect(verdictLabelFromScore(20)).toBe("REJECT");
    expect(verdictLabelFromScore(42)).toBe("WARN");
    expect(verdictLabelFromScore(65)).toBe("PASS");
    expect(verdictLabelFromScore(90)).toBe("ENDORSE");
  });
});

describe("VAL-PUBLIC-002: public limit clamp", () => {
  it("clamps public list limits to 1..100", () => {
    expect(clampPublicLimit("0")).toBe(1);
    expect(clampPublicLimit("10")).toBe(10);
    expect(clampPublicLimit("500")).toBe(100);
    expect(clampPublicLimit("not-a-number")).toBe(10);
  });
});

describe("VAL-PUBLIC-003: deterministic trace metrics", () => {
  it("computes reasoning metrics without an LLM call", () => {
    const metrics = computeTraceMetrics(sampleTrace());

    expect(metrics).not.toBeNull();
    expect(metrics?.evidence_count).toBe(2);
    expect(metrics?.source_diversity).toBe(2);
    expect(metrics?.thesis_steps).toBe(1);
    expect(metrics?.evidence_coverage).toBe(1);
    expect(metrics?.invalid_evidence_refs).toBe(0);
    expect(metrics?.risk_factor_count).toBe(1);
    expect(metrics?.probability_delta).toBeCloseTo(0.04, 4);
    expect(metrics?.has_falsification_language).toBe(true);
  });

  it("classifies a complete trace as usable", () => {
    const metrics = computeTraceMetrics(sampleTrace());
    expect(metrics && readinessFromMetrics(metrics)).toBe("usable");
  });

  it("warns on missing evidence references", () => {
    const trace = sampleTrace();
    trace.thesis[0].supporting_evidence_ids = [9];
    const metrics = computeTraceMetrics(trace);
    expect(metrics?.invalid_evidence_refs).toBe(1);
    expect(metrics && readinessFromMetrics(metrics)).toBe("not_ready");
    expect(metrics && warningsFromMetrics(metrics).join(" ")).toContain(
      "missing evidence IDs",
    );
  });
});
