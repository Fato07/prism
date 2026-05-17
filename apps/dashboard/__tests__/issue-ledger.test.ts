import { describe, expect, it } from "vitest";
import type { SentinelVerdict } from "@/lib/schemas";
import {
  getIssueLedgerSummary,
  latestResolutionForChallenge,
} from "@/lib/issue-ledger";

const baseVerdict: SentinelVerdict = {
  request_hash: "0xabc123",
  trace_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  sentinel_agent_id: 4148,
  evidence_challenges: [],
  thesis_challenges: [],
  calibration_critique: "Calibrated.",
  verdict_score: 65,
  verdict_label: "PASS",
  dialogue_messages: [],
  structured_challenges: [],
  challenge_resolutions: [],
  resolution_rounds: [],
  model_family: "openai-gpt",
  model_name: "gpt-4o-mini",
  created_at: "2026-05-12T11:00:00Z",
};

describe("dashboard issue-ledger summary", () => {
  it("gates clean PASS when a blocking issue remains unresolved", () => {
    const verdict: SentinelVerdict = {
      ...baseVerdict,
      structured_challenges: [
        {
          id: "sys-temporal-stale-evidence",
          type: "temporal",
          severity: "blocking",
          question: "Evidence predates the event window.",
          required_resolution: "Retrieve current evidence or revise to HOLD.",
          blocking_pass: true,
          claim_ref: "evidence[0]",
          resolution_status: "conceded",
        },
      ],
      resolution_metadata: {
        confidence: 0.41,
        stop_reason: "unresolved_blockers",
        unresolved_blocking_count: 1,
        unresolved_material_count: 0,
        max_rounds: 1,
      },
    };

    const summary = getIssueLedgerSummary(verdict);

    expect(summary.cleanPassAllowed).toBe(false);
    expect(summary.endorsementAllowed).toBe(false);
    expect(summary.unresolvedBlockingCount).toBe(1);
    expect(summary.activePolicyConstraints[0]).toContain("Clean PASS is blocked");
    expect(summary.explanation).toContain("Clean PASS remains gated");
  });

  it("shows a resolved blocker as resolved and allows clean PASS", () => {
    const verdict: SentinelVerdict = {
      ...baseVerdict,
      structured_challenges: [
        {
          id: "sys-temporal-stale-evidence",
          type: "temporal",
          severity: "blocking",
          question: "Evidence predates the event window.",
          required_resolution: "Retrieve current evidence or revise to HOLD.",
          blocking_pass: true,
          claim_ref: "evidence[0]",
          resolution_status: "resolved",
        },
      ],
      challenge_resolutions: [
        {
          challenge_id: "sys-temporal-stale-evidence",
          status: "resolved",
          responder: "evidence_tool",
          response: "Current source confirmed the event timing.",
          created_at: "2026-05-12T12:00:00Z",
        },
      ],
    };

    const summary = getIssueLedgerSummary(verdict);
    const latest = latestResolutionForChallenge(verdict, "sys-temporal-stale-evidence");

    expect(summary.cleanPassAllowed).toBe(true);
    expect(summary.resolvedCount).toBe(1);
    expect(summary.activePolicyConstraints[0]).toContain("No active issue-ledger gates");
    expect(latest?.status).toBe("resolved");
    expect(latest?.response).toContain("Current source confirmed");
  });

  it("orders latest resolution robustly when an older timestamp is malformed", () => {
    const verdict: SentinelVerdict = {
      ...baseVerdict,
      challenge_resolutions: [
        {
          challenge_id: "issue-1",
          status: "answered",
          responder: "trader",
          response: "Malformed timestamp should not win.",
          created_at: "not-a-date",
        },
        {
          challenge_id: "issue-1",
          status: "resolved",
          responder: "evidence_tool",
          response: "Valid latest timestamp wins.",
          created_at: "2026-05-12T12:00:00Z",
        },
      ],
    };

    const latest = latestResolutionForChallenge(verdict, "issue-1");

    expect(latest?.status).toBe("resolved");
    expect(latest?.response).toContain("Valid latest");
  });

  it("handles legacy verdicts without structured issue ledgers safely", () => {
    const summary = getIssueLedgerSummary(baseVerdict);

    expect(summary.totalIssues).toBe(0);
    expect(summary.cleanPassAllowed).toBe(true);
    expect(summary.endorsementAllowed).toBe(true);
    expect(summary.activePolicyConstraints[0]).toContain("Legacy receipt");
    expect(summary.explanation).toContain("no structured issue ledger");
  });
});
