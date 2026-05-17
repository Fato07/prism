import type { ChallengeResolution, SentinelVerdict } from "@/lib/schemas";

const RESOLVED_STATUSES = new Set(["resolved", "superseded"]);
const UNRESOLVED_STATUSES = new Set(["open", "answered", "conceded"]);

export type ToolResolutionStatus = "resolved" | "no_evidence" | "not_attempted";

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

export interface ToolResolutionSummary {
  resolvedCount: number;
  noEvidenceCount: number;
  notRecordedCount: number;
  label: string;
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

export function toolResolutionStatus(
  resolution: ChallengeResolution | null,
): ToolResolutionStatus {
  if (!resolution) return "not_attempted";
  return toolResolutionStatusFromResolutions([resolution]);
}

export function toolResolutionStatusForChallenge(
  verdict: SentinelVerdict,
  challengeId: string,
): ToolResolutionStatus {
  const resolutions = (verdict.challenge_resolutions ?? []).filter(
    (resolution) => resolution.challenge_id === challengeId,
  );
  return toolResolutionStatusFromResolutions(resolutions);
}

function toolResolutionStatusFromResolutions(
  resolutions: ChallengeResolution[],
): ToolResolutionStatus {
  if (resolutions.some((resolution) => (
    resolution.responder === "evidence_tool" && RESOLVED_STATUSES.has(resolution.status)
  ))) {
    return "resolved";
  }
  if (resolutions.some((resolution) => (
    resolution.responder === "evidence_tool" || isNoEvidenceResolution(resolution)
  ))) {
    return "no_evidence";
  }
  return "not_attempted";
}

export function getToolResolutionSummary(verdict: SentinelVerdict): ToolResolutionSummary {
  const challenges = verdict.structured_challenges ?? [];
  const statuses = challenges.map((challenge) => (
    toolResolutionStatusForChallenge(verdict, challenge.id)
  ));
  const resolvedCount = statuses.filter((status) => status === "resolved").length;
  const noEvidenceCount = statuses.filter((status) => status === "no_evidence").length;
  const notRecordedCount = statuses.filter((status) => status === "not_attempted").length;

  return {
    resolvedCount,
    noEvidenceCount,
    notRecordedCount,
    label: toolResolutionLabel({ resolvedCount, noEvidenceCount }),
  };
}

function isNoEvidenceResolution(resolution: ChallengeResolution): boolean {
  if (resolution.responder !== "system") return false;
  const response = resolution.response.toLowerCase();
  return response.includes("no configured evidence provider") ||
    response.includes("no additional evidence retrieved");
}

function toolResolutionLabel({
  resolvedCount,
  noEvidenceCount,
}: {
  resolvedCount: number;
  noEvidenceCount: number;
}): string {
  if (resolvedCount === 0 && noEvidenceCount === 0) {
    return "No evidence-tool resolution was recorded.";
  }
  if (resolvedCount > 0 && noEvidenceCount === 0) {
    return "Evidence tool resolved every recorded issue.";
  }
  if (resolvedCount > 0) {
    return "Evidence tool resolved some issues; the rest stayed fail-closed.";
  }
  return "Evidence route accepted no usable evidence; issues stayed fail-closed.";
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
