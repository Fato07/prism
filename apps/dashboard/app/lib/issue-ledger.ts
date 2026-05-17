import type { ChallengeResolution, SentinelVerdict } from "@/lib/schemas";

const RESOLVED_STATUSES = new Set(["resolved", "superseded"]);
const UNRESOLVED_STATUSES = new Set(["open", "answered", "conceded"]);

export interface IssueLedgerSummary {
  totalIssues: number;
  resolvedCount: number;
  unresolvedBlockingCount: number;
  unresolvedMaterialCount: number;
  activePolicyConstraints: string[];
  cleanPassAllowed: boolean;
  endorsementAllowed: boolean;
  explanation: string;
}

export function latestResolutionForChallenge(
  verdict: SentinelVerdict,
  challengeId: string,
): ChallengeResolution | null {
  const matches = (verdict.challenge_resolutions ?? []).filter(
    (resolution) => resolution.challenge_id === challengeId,
  );
  if (matches.length === 0) return null;

  return matches.reduce((latest, resolution) => {
    const latestMs = timestampMs(latest.created_at);
    const nextMs = timestampMs(resolution.created_at);
    return nextMs > latestMs ? resolution : latest;
  });
}

function timestampMs(value: string): number {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : Number.NEGATIVE_INFINITY;
}

export function getIssueLedgerSummary(verdict: SentinelVerdict): IssueLedgerSummary {
  const challenges = verdict.structured_challenges ?? [];
  const metadata = verdict.resolution_metadata ?? null;
  const unresolvedBlockingCount = metadata?.unresolved_blocking_count ?? challenges.filter(
    (challenge) => challenge.blocking_pass && UNRESOLVED_STATUSES.has(challenge.resolution_status),
  ).length;
  const unresolvedMaterialCount = metadata?.unresolved_material_count ?? challenges.filter(
    (challenge) => challenge.severity === "material" && UNRESOLVED_STATUSES.has(challenge.resolution_status),
  ).length;
  const resolvedCount = challenges.filter((challenge) => (
    RESOLVED_STATUSES.has(challenge.resolution_status)
  )).length;

  const activePolicyConstraints = policyConstraints({
    totalIssues: challenges.length,
    unresolvedBlockingCount,
    unresolvedMaterialCount,
  });

  return {
    totalIssues: challenges.length,
    resolvedCount,
    unresolvedBlockingCount,
    unresolvedMaterialCount,
    activePolicyConstraints,
    cleanPassAllowed: unresolvedBlockingCount === 0,
    endorsementAllowed: unresolvedBlockingCount === 0 && unresolvedMaterialCount === 0,
    explanation: explanationForVerdict({
      label: verdict.verdict_label,
      score: verdict.verdict_score,
      totalIssues: challenges.length,
      unresolvedBlockingCount,
      unresolvedMaterialCount,
      stopReason: metadata?.stop_reason ?? null,
    }),
  };
}

function policyConstraints({
  totalIssues,
  unresolvedBlockingCount,
  unresolvedMaterialCount,
}: {
  totalIssues: number;
  unresolvedBlockingCount: number;
  unresolvedMaterialCount: number;
}): string[] {
  if (totalIssues === 0) {
    return ["Legacy receipt: no structured issue ledger was recorded."];
  }

  const constraints: string[] = [];
  if (unresolvedBlockingCount > 0) {
    constraints.push("Clean PASS is blocked until every blocking issue is resolved.");
  }
  if (unresolvedMaterialCount > 0) {
    constraints.push("ENDORSE is blocked while material issues remain unresolved.");
  }
  if (constraints.length === 0) {
    constraints.push("No active issue-ledger gates remain.");
  }
  return constraints;
}

function explanationForVerdict({
  label,
  score,
  totalIssues,
  unresolvedBlockingCount,
  unresolvedMaterialCount,
  stopReason,
}: {
  label: string;
  score: number;
  totalIssues: number;
  unresolvedBlockingCount: number;
  unresolvedMaterialCount: number;
  stopReason: string | null;
}): string {
  if (totalIssues === 0) {
    return `Sentinel returned ${label} at ${score}/100. This legacy receipt has no structured issue ledger.`;
  }

  if (unresolvedBlockingCount > 0) {
    return `Sentinel returned ${label} at ${score}/100 with ${unresolvedBlockingCount} unresolved blocking issue${unresolvedBlockingCount === 1 ? "" : "s"}. Clean PASS remains gated.`;
  }

  if (unresolvedMaterialCount > 0) {
    return `Sentinel returned ${label} at ${score}/100 with material issues still open. ENDORSE remains gated.`;
  }

  const suffix = stopReason ? ` Stop reason: ${stopReason}.` : "";
  return `Sentinel returned ${label} at ${score}/100 after issue-ledger gates cleared.${suffix}`;
}
