import { describe, expect, it } from "vitest";
import type { SentinelVerdict } from "@/lib/schemas";
import {
  getIssueLedgerSummary,
  getToolResolutionSummary,
  latestResolutionForChallenge,
  toolResolutionStatus,
  toolResolutionStatusForChallenge,
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

  it("summarizes evidence-tool resolution and fail-closed outcomes", () => {
    const verdict: SentinelVerdict = {
      ...baseVerdict,
      structured_challenges: [
        {
          id: "issue-resolved",
          type: "source_quality",
          severity: "material",
          question: "Needs primary source.",
          required_resolution: "Retrieve current primary source.",
          blocking_pass: false,
          resolution_status: "resolved",
        },
        {
          id: "issue-fail-closed",
          type: "temporal",
          severity: "blocking",
          question: "Needs fresh evidence.",
          required_resolution: "Retrieve fresh evidence.",
          blocking_pass: true,
          resolution_status: "conceded",
        },
        {
          id: "issue-not-attempted",
          type: "logic",
          severity: "minor",
          question: "Needs clearer logic.",
          required_resolution: "Clarify reasoning.",
          blocking_pass: false,
          resolution_status: "open",
        },
      ],
      challenge_resolutions: [
        {
          challenge_id: "issue-resolved",
          status: "resolved",
          responder: "evidence_tool",
          response: "Retrieved corroborating evidence from demo.",
          created_at: "2026-05-12T12:00:00Z",
        },
        {
          challenge_id: "issue-fail-closed",
          status: "conceded",
          responder: "system",
          response: "No configured evidence provider resolved this blocking issue.",
          created_at: "2026-05-12T12:00:00Z",
        },
      ],
    };

    const resolved = latestResolutionForChallenge(verdict, "issue-resolved");
    const failClosed = latestResolutionForChallenge(verdict, "issue-fail-closed");
    const notAttempted = latestResolutionForChallenge(verdict, "issue-not-attempted");
    const summary = getToolResolutionSummary(verdict);

    expect(toolResolutionStatus(resolved)).toBe("resolved");
    expect(toolResolutionStatus(failClosed)).toBe("no_evidence");
    expect(toolResolutionStatus(notAttempted)).toBe("not_attempted");
    expect(toolResolutionStatusForChallenge(verdict, "issue-resolved")).toBe("resolved");
    expect(toolResolutionStatusForChallenge(verdict, "issue-fail-closed")).toBe("no_evidence");
    expect(toolResolutionStatusForChallenge(verdict, "issue-not-attempted")).toBe("not_attempted");
    expect(summary.resolvedCount).toBe(1);
    expect(summary.noEvidenceCount).toBe(1);
    expect(summary.notRecordedCount).toBe(1);
    expect(summary.label).toContain("fail-closed");
  });

  it("does not hide an evidence-tool resolution behind a newer system note", () => {
    const verdict: SentinelVerdict = {
      ...baseVerdict,
      structured_challenges: [
        {
          id: "issue-resolved",
          type: "source_quality",
          severity: "material",
          question: "Needs primary source.",
          required_resolution: "Retrieve current primary source.",
          blocking_pass: false,
          resolution_status: "resolved",
        },
      ],
      challenge_resolutions: [
        {
          challenge_id: "issue-resolved",
          status: "resolved",
          responder: "evidence_tool",
          response: "Retrieved corroborating evidence from demo.",
          created_at: "2026-05-12T12:00:00Z",
        },
        {
          challenge_id: "issue-resolved",
          status: "answered",
          responder: "system",
          response: "Later bookkeeping note.",
          created_at: "2026-05-12T12:05:00Z",
        },
      ],
    };

    expect(latestResolutionForChallenge(verdict, "issue-resolved")?.responder).toBe("system");
    expect(toolResolutionStatusForChallenge(verdict, "issue-resolved")).toBe("resolved");
  });
});
