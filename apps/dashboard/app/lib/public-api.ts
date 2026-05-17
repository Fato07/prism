import { deriveCapitalGate } from "@/lib/capital-gate";
import { getPool, getTraceDetailData } from "@/lib/db";
import {
  getIssueLedgerSummary,
  latestResolutionForChallenge,
  toolResolutionStatusForChallenge,
} from "@/lib/issue-ledger";
import {
  SentinelVerdictSchema,
  type SentinelVerdict,
  type ValidationRow,
} from "@/lib/schemas";

export type VerdictLabel = "REJECT" | "WARN" | "PASS" | "ENDORSE";
export type Readiness = "usable" | "needs_review" | "not_ready";
export type PublicToolStatus = "resolved" | "fail_closed" | "not_recorded";

export interface ReasoningMetrics {
  evidence_count: number;
  source_diversity: number;
  thesis_steps: number;
  evidence_reference_count: number;
  evidence_coverage: number;
  invalid_evidence_refs: number;
  unsupported_thesis_steps: number;
  risk_factor_count: number;
  avg_evidence_confidence: number;
  probability_delta: number;
  has_falsification_language: boolean;
}

export interface PublicHistoryEntry {
  trace_id: string;
  market_id: string;
  verdict_score: number;
  verdict_label: VerdictLabel;
  created_at: string;
  dashboard_url: string;
  trace_ipfs_cid: string | null;
  trace_tx_hash: string | null;
  validation_tx_hash: string | null;
  response_uri: string | null;
}

interface TraceEvidenceLike {
  source?: unknown;
  confidence?: unknown;
}

interface TraceThesisLike {
  supporting_evidence_ids?: unknown;
  risk_factors?: unknown;
}

export interface PublicIssueLedgerReport {
  summary: {
    total_issues: number;
    resolved_count: number;
    unresolved_blocking_count: number;
    unresolved_material_count: number;
    clean_pass_allowed: boolean;
    endorsement_allowed: boolean;
    active_policy_constraints: string[];
    explanation: string;
  };
  resolution_metadata: SentinelVerdict["resolution_metadata"] | null;
  issues: Array<{
    id: string;
    type: string;
    severity: string;
    blocking_pass: boolean;
    resolution_status: string;
    question: string;
    required_resolution: string;
    claim_ref: string | null;
    tool_status: PublicToolStatus;
    tool_provider: string | null;
    resolved_by_evidence_tool: boolean;
    latest_resolution: SentinelVerdict["challenge_resolutions"][number] | null;
  }>;
}

export interface PublicReceiptVerificationReport {
  response_uri: string | null;
  verdict_ipfs: string | null;
  validation_arc_tx: string | null;
  schema_valid: boolean;
  request_hash_matches: boolean | null;
  trace_id_matches: boolean | null;
  sentinel_agent_id_matches: boolean | null;
  verdict_score_matches: boolean | null;
  db_receipt_present: boolean;
}

function dashboardBaseUrl(): string {
  return (
    process.env.NEXT_PUBLIC_DASHBOARD_URL ??
    process.env.DASHBOARD_URL ??
    "https://prism-dashboard-production-e6e3.up.railway.app"
  ).replace(/\/$/, "");
}

export function clampPublicLimit(raw: string | number | null | undefined): number {
  const parsed = typeof raw === "number" ? raw : Number(raw ?? 10);
  if (!Number.isFinite(parsed)) return 10;
  return Math.max(1, Math.min(100, Math.floor(parsed)));
}

export function verdictLabelFromScore(score: number): VerdictLabel {
  if (score <= 25) return "REJECT";
  if (score <= 50) return "WARN";
  if (score <= 75) return "PASS";
  return "ENDORSE";
}

export function computeTraceMetrics(trace: Record<string, unknown>): ReasoningMetrics | null {
  const evidenceRaw = trace.evidence;
  const thesisRaw = trace.thesis;
  if (!Array.isArray(evidenceRaw) || !Array.isArray(thesisRaw)) return null;

  const evidence = evidenceRaw as TraceEvidenceLike[];
  const thesis = thesisRaw as TraceThesisLike[];
  const evidenceCount = evidence.length;
  const sourceDiversity = new Set(
    evidence
      .map((item) => String(item.source ?? "").trim().toLowerCase())
      .filter(Boolean),
  ).size;

  const validRefs = new Set<number>();
  let evidenceReferenceCount = 0;
  let invalidEvidenceRefs = 0;
  let unsupportedThesisSteps = 0;
  let riskFactorCount = 0;
  const falsificationParts: string[] = [String(trace.rationale ?? "")];

  for (const step of thesis) {
    const refs = Array.isArray(step.supporting_evidence_ids)
      ? step.supporting_evidence_ids
      : [];
    const risks = Array.isArray(step.risk_factors) ? step.risk_factors : [];
    riskFactorCount += risks.length;
    falsificationParts.push(...risks.map((risk) => String(risk)));

    let hasValidRef = false;
    for (const rawRef of refs) {
      const ref = Number(rawRef);
      evidenceReferenceCount += 1;
      if (Number.isInteger(ref) && ref >= 0 && ref < evidenceCount) {
        validRefs.add(ref);
        hasValidRef = true;
      } else {
        invalidEvidenceRefs += 1;
      }
    }
    if (!hasValidRef) unsupportedThesisSteps += 1;
  }

  const confidenceValues = evidence
    .map((item) => Number(item.confidence ?? 0))
    .filter((value) => Number.isFinite(value));
  const avgEvidenceConfidence = confidenceValues.length
    ? confidenceValues.reduce((sum, value) => sum + value, 0) / confidenceValues.length
    : 0;
  const rawProbability = Number(trace.raw_probability ?? 0);
  const finalProbability = Number(trace.final_probability ?? 0);
  const probabilityDelta = Math.abs(finalProbability - rawProbability);

  return {
    evidence_count: evidenceCount,
    source_diversity: sourceDiversity,
    thesis_steps: thesis.length,
    evidence_reference_count: evidenceReferenceCount,
    evidence_coverage: round4(evidenceCount ? validRefs.size / evidenceCount : 0),
    invalid_evidence_refs: invalidEvidenceRefs,
    unsupported_thesis_steps: unsupportedThesisSteps,
    risk_factor_count: riskFactorCount,
    avg_evidence_confidence: round4(avgEvidenceConfidence),
    probability_delta: round4(probabilityDelta),
    has_falsification_language:
      /\b(falsif|invalidate|disconfirm|stop loss|stop-loss|exit if|wrong if|counterevidence)\b/i.test(
        falsificationParts.join(" "),
      ),
  };
}

export function readinessFromMetrics(metrics: ReasoningMetrics): Readiness {
  if (
    metrics.evidence_count >= 2 &&
    metrics.thesis_steps >= 1 &&
    metrics.evidence_coverage >= 0.67 &&
    metrics.invalid_evidence_refs === 0 &&
    metrics.unsupported_thesis_steps === 0 &&
    metrics.risk_factor_count >= 1
  ) {
    return "usable";
  }

  if (
    metrics.evidence_count === 0 ||
    metrics.thesis_steps === 0 ||
    metrics.invalid_evidence_refs > 0
  ) {
    return "not_ready";
  }

  return "needs_review";
}

export function buildPublicIssueLedgerReport(
  verdict: SentinelVerdict | null,
): PublicIssueLedgerReport | null {
  if (!verdict) return null;

  const summary = getIssueLedgerSummary(verdict);
  return {
    summary: {
      total_issues: summary.totalIssues,
      resolved_count: summary.resolvedCount,
      unresolved_blocking_count: summary.unresolvedBlockingCount,
      unresolved_material_count: summary.unresolvedMaterialCount,
      clean_pass_allowed: summary.cleanPassAllowed,
      endorsement_allowed: summary.endorsementAllowed,
      active_policy_constraints: summary.activePolicyConstraints,
      explanation: summary.explanation,
    },
    resolution_metadata: verdict.resolution_metadata ?? null,
    issues: (verdict.structured_challenges ?? []).map((challenge) => {
      const toolStatus = publicToolStatusForChallenge(verdict, challenge.id);
      return {
        id: challenge.id,
        type: challenge.type,
        severity: challenge.severity,
        blocking_pass: challenge.blocking_pass,
        resolution_status: challenge.resolution_status,
        question: challenge.question,
        required_resolution: challenge.required_resolution,
        claim_ref: challenge.claim_ref ?? null,
        tool_status: toolStatus,
        tool_provider: evidenceToolProviderForChallenge(verdict, challenge.id),
        resolved_by_evidence_tool: toolStatus === "resolved",
        latest_resolution: latestResolutionForChallenge(verdict, challenge.id),
      };
    }),
  };
}

function publicToolStatusForChallenge(
  verdict: SentinelVerdict,
  challengeId: string,
): PublicToolStatus {
  const status = toolResolutionStatusForChallenge(verdict, challengeId);
  if (status === "resolved") return "resolved";
  if (status === "no_evidence") return "fail_closed";
  return "not_recorded";
}

function evidenceToolProviderForChallenge(
  verdict: SentinelVerdict,
  challengeId: string,
): string | null {
  const evidenceToolResolutions = (verdict.challenge_resolutions ?? []).filter(
    (resolution) => resolution.challenge_id === challengeId && resolution.responder === "evidence_tool",
  );
  const resolved = evidenceToolResolutions.find((resolution) => resolution.status === "resolved");
  const resolution = resolved ?? evidenceToolResolutions[0];
  if (!resolution) return null;
  return extractEvidenceProvider(resolution.response);
}

function extractEvidenceProvider(response: string): string | null {
  const match = response.match(/evidence from ([a-zA-Z0-9_.-]+):/);
  return match?.[1] ?? null;
}

export function buildPublicReceiptVerificationReport(
  validation: ValidationRow | null,
  verdict: SentinelVerdict | null,
): PublicReceiptVerificationReport | null {
  if (!validation) return null;

  return {
    response_uri: validation.response_uri,
    verdict_ipfs: extractCid(validation.response_uri)
      ? `ipfs://${extractCid(validation.response_uri)}`
      : null,
    validation_arc_tx: validation.tx_hash,
    schema_valid: verdict !== null,
    request_hash_matches: verdict
      ? normalizeHash(verdict.request_hash) === normalizeHash(validation.request_hash)
      : null,
    trace_id_matches: verdict ? verdict.trace_id === validation.trace_id : null,
    sentinel_agent_id_matches: verdict
      ? verdict.sentinel_agent_id === validation.sentinel_agent_id
      : null,
    verdict_score_matches: verdict ? verdict.verdict_score === validation.verdict_score : null,
    db_receipt_present: true,
  };
}

export function warningsFromMetrics(metrics: ReasoningMetrics): string[] {
  const warnings: string[] = [];
  if (metrics.evidence_count < 2) warnings.push("Trace has fewer than 2 evidence items.");
  if (metrics.source_diversity < 2 && metrics.evidence_count >= 2) {
    warnings.push("Evidence comes from fewer than 2 distinct sources.");
  }
  if (metrics.evidence_coverage < 0.67) {
    warnings.push("Less than two-thirds of evidence is referenced by thesis steps.");
  }
  if (metrics.invalid_evidence_refs > 0) {
    warnings.push("Trace contains thesis references to missing evidence IDs.");
  }
  if (metrics.unsupported_thesis_steps > 0) {
    warnings.push("At least one thesis step has no valid supporting evidence reference.");
  }
  if (metrics.risk_factor_count === 0) warnings.push("Trace lists no risk factors.");
  if (!metrics.has_falsification_language) {
    warnings.push("Trace does not state clear falsification or exit language.");
  }
  return warnings;
}

export async function getPublicHistoryEntries(limitInput: number): Promise<PublicHistoryEntry[]> {
  const limit = clampPublicLimit(limitInput);
  const client = getPool();
  const result = await client.query(
    `SELECT t.trace_id,
            t.market_id,
            t.ipfs_cid,
            t.tx_hash AS trace_tx_hash,
            v.verdict_score,
            v.response_uri,
            v.tx_hash AS validation_tx_hash,
            v.created_at::text AS created_at
       FROM validations v
       JOIN traces t ON t.trace_id = v.trace_id
      ORDER BY v.created_at DESC
      LIMIT $1`,
    [limit],
  );

  const base = dashboardBaseUrl();
  return (result.rows as Record<string, unknown>[]).map((row) => {
    const score = Number(row.verdict_score ?? 0);
    const traceId = String(row.trace_id);
    return {
      trace_id: traceId,
      market_id: String(row.market_id ?? ""),
      verdict_score: score,
      verdict_label: verdictLabelFromScore(score),
      created_at: String(row.created_at ?? ""),
      dashboard_url: `${base}/trace/${traceId}`,
      trace_ipfs_cid: row.ipfs_cid ? String(row.ipfs_cid) : null,
      trace_tx_hash: row.trace_tx_hash ? String(row.trace_tx_hash) : null,
      validation_tx_hash: row.validation_tx_hash ? String(row.validation_tx_hash) : null,
      response_uri: row.response_uri ? String(row.response_uri) : null,
    } satisfies PublicHistoryEntry;
  });
}

export async function getPublicTraceReport(traceId: string): Promise<Record<string, unknown> | null> {
  const detail = await getTraceDetailData(traceId);
  if (!detail) return null;

  const metrics = detail.traceContent ? computeTraceMetrics(detail.traceContent) : null;
  const readiness = metrics ? readinessFromMetrics(metrics) : null;
  const warnings = metrics ? warningsFromMetrics(metrics) : [];
  const score = detail.validation?.verdict_score ?? null;
  const verdictCid = extractCid(detail.validation?.response_uri ?? "");
  const parsedVerdict = detail.verdictContent
    ? SentinelVerdictSchema.safeParse(detail.verdictContent)
    : null;
  const verdict = parsedVerdict?.success ? parsedVerdict.data : null;
  const issueLedger = buildPublicIssueLedgerReport(verdict);
  const validationLabel = score !== null ? verdictLabelFromScore(score) : null;
  const capitalGate = deriveCapitalGate({
    verdictScore: score,
    verdictLabel: validationLabel,
    readiness,
    unresolvedBlockingCount: issueLedger?.summary.unresolved_blocking_count ?? null,
    unresolvedMaterialCount: issueLedger?.summary.unresolved_material_count ?? null,
    totalIssues: issueLedger?.summary.total_issues ?? null,
  });
  const receiptVerification = buildPublicReceiptVerificationReport(
    detail.validation,
    verdict,
  );

  return {
    generated_at: new Date().toISOString(),
    trace: {
      trace_id: detail.trace.trace_id,
      agent_id: detail.trace.agent_id,
      market_id: detail.trace.market_id,
      market_question: String(detail.traceContent?.market_question ?? ""),
      action: String(detail.traceContent?.action ?? ""),
      raw_probability: numberOrNull(detail.traceContent?.raw_probability),
      final_probability: numberOrNull(detail.traceContent?.final_probability),
      ipfs_cid: detail.trace.ipfs_cid,
      created_at: detail.trace.created_at,
      dashboard_url: `${dashboardBaseUrl()}/trace/${detail.trace.trace_id}`,
    },
    validation: detail.validation
      ? {
          request_hash: detail.validation.request_hash,
          sentinel_agent_id: detail.validation.sentinel_agent_id,
          verdict_score: score,
          verdict_label: validationLabel,
          response_uri: detail.validation.response_uri,
          tx_hash: detail.validation.tx_hash,
          created_at: detail.validation.created_at,
        }
      : null,
    reasoning_metrics: metrics,
    readiness,
    warnings,
    capital_gate: capitalGate,
    issue_ledger: issueLedger,
    receipt_verification: receiptVerification,
    receipts: {
      trace_ipfs: detail.trace.ipfs_cid ? `ipfs://${detail.trace.ipfs_cid}` : null,
      verdict_ipfs: verdictCid ? `ipfs://${verdictCid}` : null,
      trace_arc_tx: detail.trace.tx_hash,
      validation_arc_tx: detail.validation?.tx_hash ?? null,
      polymarket_tx: detail.trade?.polymarket_tx ?? null,
      trade_status: detail.trade?.status ?? null,
    },
  };
}

function extractCid(uri: string): string | null {
  if (uri.startsWith("ipfs://")) return uri.slice(7);
  return uri || null;
}

function numberOrNull(value: unknown): number | null {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function normalizeHash(value: string): string {
  return value.trim().replace(/^0x/i, "").toLowerCase();
}

function round4(value: number): number {
  return Math.round(value * 10_000) / 10_000;
}
