export type VerdictLabel = "REJECT" | "WARN" | "PASS" | "ENDORSE";
export type Readiness = "usable" | "needs_review" | "not_ready";
export type CapitalGateStatus = "PENDING_VALIDATION" | "BLOCK" | "REVIEW" | "ALLOW_PAPER" | "ENDORSE";
export type CapitalGateTone = "neutral" | "bad" | "warn" | "good";

export interface CapitalGateInput {
  verdictScore: number | null;
  verdictLabel: VerdictLabel | null;
  readiness?: Readiness | null;
  unresolvedBlockingCount?: number | null;
  unresolvedMaterialCount?: number | null;
  totalIssues?: number | null;
}

export interface CapitalGate {
  status: CapitalGateStatus;
  label: string;
  tone: CapitalGateTone;
  recommended_action: string;
  reason: string;
  policy_constraints: string[];
  checks: {
    validation_present: boolean;
    trace_ready: boolean | null;
    clean_pass_allowed: boolean | null;
    endorsement_allowed: boolean | null;
  };
}

export function deriveCapitalGate(input: CapitalGateInput): CapitalGate {
  const constraints: string[] = [];
  const validationPresent = input.verdictScore !== null && input.verdictLabel !== null;
  const traceReady = input.readiness ? input.readiness === "usable" : null;
  const unresolvedBlockingCount = Math.max(0, input.unresolvedBlockingCount ?? 0);
  const unresolvedMaterialCount = Math.max(0, input.unresolvedMaterialCount ?? 0);
  const hasStructuredIssueLedger = validationPresent && (input.totalIssues ?? 0) > 0;
  const cleanPassAllowed = validationPresent && hasStructuredIssueLedger
    ? unresolvedBlockingCount === 0
    : null;
  const endorsementAllowed = validationPresent && hasStructuredIssueLedger
    ? unresolvedBlockingCount === 0 && unresolvedMaterialCount === 0
    : null;

  if (!validationPresent) {
    constraints.push("Sentinel validation is required before capital can move.");
    return {
      status: "PENDING_VALIDATION",
      label: "Pending validation",
      tone: "neutral",
      recommended_action: "Do not trade until an adversarial verdict exists.",
      reason: "No sentinel verdict has been recorded for this trace yet.",
      policy_constraints: constraints,
      checks: {
        validation_present: false,
        trace_ready: traceReady,
        clean_pass_allowed: null,
        endorsement_allowed: null,
      },
    };
  }

  if (input.readiness === "not_ready") {
    constraints.push("Deterministic trace readiness is not_ready.");
  }
  if (input.readiness === "needs_review") {
    constraints.push("Deterministic trace readiness needs review.");
  }
  if (validationPresent && !hasStructuredIssueLedger) {
    constraints.push("Legacy receipt: no structured issue ledger was recorded.");
  }
  if (input.verdictLabel === "REJECT" || (input.verdictScore ?? 0) <= 25) {
    constraints.push("Sentinel verdict is REJECT or score is in the rejection band.");
  }
  if (unresolvedBlockingCount > 0) {
    constraints.push("Unresolved blocking issues remain in the issue ledger.");
  }
  if (unresolvedMaterialCount > 0) {
    constraints.push("Unresolved material issues remain in the issue ledger.");
  }

  if (
    input.readiness === "not_ready" ||
    input.verdictLabel === "REJECT" ||
    (input.verdictScore ?? 0) <= 25 ||
    unresolvedBlockingCount > 0
  ) {
    return {
      status: "BLOCK",
      label: "Capital blocked",
      tone: "bad",
      recommended_action: "Do not route capital from this trace.",
      reason: firstReason(constraints, "The sentinel found a blocking validation failure."),
      policy_constraints: constraints,
      checks: {
        validation_present: true,
        trace_ready: traceReady,
        clean_pass_allowed: cleanPassAllowed,
        endorsement_allowed: endorsementAllowed,
      },
    };
  }

  if (
    input.verdictLabel === "WARN" ||
    (input.verdictScore ?? 0) <= 50 ||
    unresolvedMaterialCount > 0 ||
    input.readiness === "needs_review" ||
    !hasStructuredIssueLedger
  ) {
    if (constraints.length === 0) {
      constraints.push("Sentinel verdict requires human or agent review before capital scales.");
    }
    return {
      status: "REVIEW",
      label: "Review required",
      tone: "warn",
      recommended_action: "Keep this in review or paper mode until issues are resolved.",
      reason: firstReason(constraints, "The trace is not cleared for autonomous execution."),
      policy_constraints: constraints,
      checks: {
        validation_present: true,
        trace_ready: traceReady,
        clean_pass_allowed: cleanPassAllowed,
        endorsement_allowed: endorsementAllowed,
      },
    };
  }

  if (input.verdictLabel === "ENDORSE" || (input.verdictScore ?? 0) >= 76) {
    return {
      status: "ENDORSE",
      label: "Execution endorsed",
      tone: "good",
      recommended_action: "Eligible for execution under configured wallet and market risk limits.",
      reason: "High-confidence sentinel verdict with no unresolved material or blocking issues.",
      policy_constraints: ["No active issue-ledger gates remain."],
      checks: {
        validation_present: true,
        trace_ready: traceReady,
        clean_pass_allowed: cleanPassAllowed,
        endorsement_allowed: endorsementAllowed,
      },
    };
  }

  return {
    status: "ALLOW_PAPER",
    label: "Paper mode allowed",
    tone: "good",
    recommended_action: "Allowed to continue in paper mode; live execution still depends on configured risk limits.",
    reason: "Sentinel returned PASS with no unresolved blocking issues in the structured issue ledger.",
    policy_constraints: ["No active blocking issue-ledger gates remain."],
    checks: {
      validation_present: true,
      trace_ready: traceReady,
      clean_pass_allowed: cleanPassAllowed,
      endorsement_allowed: endorsementAllowed,
    },
  };
}

function firstReason(values: string[], fallback: string): string {
  return values[0] ?? fallback;
}
