/**
 * Public API helpers — CLI/reporting contract.
 */

import { describe, expect, it } from "vitest";
import {
  buildPublicIssueLedgerReport,
  buildPublicReceiptVerificationReport,
  clampPublicLimit,
  computeTraceMetrics,
  readinessFromMetrics,
  verdictLabelFromScore,
  warningsFromMetrics,
} from "../app/lib/public-api";
import type { SentinelVerdict, ValidationRow } from "../app/lib/schemas";

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

function sampleVerdict(): SentinelVerdict {
  return {
    request_hash: "0xabc123",
    trace_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    sentinel_agent_id: 4148,
    evidence_challenges: [],
    thesis_challenges: [],
    calibration_critique: "Calibrated.",
    verdict_score: 50,
    verdict_label: "WARN",
    dialogue_messages: [],
    structured_challenges: [
      {
        id: "sys-temporal-stale-evidence",
        type: "temporal",
        severity: "blocking",
        question: "Evidence predates the market event window.",
        required_resolution: "Retrieve current evidence or revise to HOLD.",
        blocking_pass: true,
        claim_ref: "evidence[0]",
        resolution_status: "conceded",
      },
    ],
    challenge_resolutions: [
      {
        challenge_id: "sys-temporal-stale-evidence",
        status: "conceded",
        responder: "evidence_tool",
        response: "No current source found; blocker remains unresolved.",
        created_at: "2026-05-12T12:00:00Z",
      },
    ],
    resolution_rounds: [],
    resolution_metadata: {
      confidence: 0.41,
      stop_reason: "unresolved_blockers",
      unresolved_blocking_count: 1,
      unresolved_material_count: 0,
      max_rounds: 1,
    },
    model_family: "openai-gpt",
    model_name: "gpt-4o-mini",
    created_at: "2026-05-12T11:00:00Z",
  };
}

function sampleValidation(): ValidationRow {
  return {
    request_hash: "abc123",
    trace_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    sentinel_agent_id: 4148,
    verdict_score: 50,
    response_uri: "ipfs://QmVerdictReceipt",
    tx_hash: "0xarcanchor",
    created_at: "2026-05-12T11:01:00Z",
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


describe("VAL-PUBLIC-004: public issue-ledger report", () => {
  it("includes gating summary and latest resolution attempts", () => {
    const report = buildPublicIssueLedgerReport(sampleVerdict());

    expect(report).not.toBeNull();
    expect(report?.summary.unresolved_blocking_count).toBe(1);
    expect(report?.summary.clean_pass_allowed).toBe(false);
    expect(report?.summary.active_policy_constraints[0]).toContain("Clean PASS is blocked");
    expect(report?.issues[0].id).toBe("sys-temporal-stale-evidence");
    expect(report?.issues[0].latest_resolution?.responder).toBe("evidence_tool");
  });

  it("keeps legacy verdicts reportable without structured issues", () => {
    const verdict: SentinelVerdict = {
      ...sampleVerdict(),
      structured_challenges: [],
      challenge_resolutions: [],
      resolution_metadata: undefined,
    };
    const report = buildPublicIssueLedgerReport(verdict);

    expect(report?.summary.total_issues).toBe(0);
    expect(report?.summary.clean_pass_allowed).toBe(true);
    expect(report?.summary.active_policy_constraints[0]).toContain("Legacy receipt");
    expect(report?.issues).toEqual([]);
  });
});

describe("VAL-PUBLIC-005: public receipt verification fields", () => {
  it("reports DB/pinned verdict identity matches without exposing requester data", () => {
    const report = buildPublicReceiptVerificationReport(sampleValidation(), sampleVerdict());

    expect(report).not.toBeNull();
    expect(report?.schema_valid).toBe(true);
    expect(report?.request_hash_matches).toBe(true);
    expect(report?.trace_id_matches).toBe(true);
    expect(report?.sentinel_agent_id_matches).toBe(true);
    expect(report?.verdict_score_matches).toBe(true);
    expect(report?.verdict_ipfs).toBe("ipfs://QmVerdictReceipt");
    expect(JSON.stringify(report)).not.toContain("requester");
  });

  it("returns false for mismatched pinned verdict identity fields", () => {
    const validation = sampleValidation();
    const verdict: SentinelVerdict = {
      ...sampleVerdict(),
      request_hash: "0xdifferent",
      trace_id: "ffffffff-e5f6-7890-abcd-ef1234567890",
      sentinel_agent_id: 9999,
      verdict_score: 51,
    };
    const report = buildPublicReceiptVerificationReport(validation, verdict);

    expect(report?.request_hash_matches).toBe(false);
    expect(report?.trace_id_matches).toBe(false);
    expect(report?.sentinel_agent_id_matches).toBe(false);
    expect(report?.verdict_score_matches).toBe(false);
  });

  it("returns nullable match fields when the pinned verdict is unavailable", () => {
    const report = buildPublicReceiptVerificationReport(sampleValidation(), null);

    expect(report?.schema_valid).toBe(false);
    expect(report?.request_hash_matches).toBeNull();
    expect(report?.trace_id_matches).toBeNull();
    expect(report?.sentinel_agent_id_matches).toBeNull();
    expect(report?.verdict_score_matches).toBeNull();
  });
});
