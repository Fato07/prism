import type { CapitalGateStatus } from "@/lib/capital-gate";

export type TraceExplainerTone = "trader" | "sentinel" | "good" | "warn" | "bad" | "neutral";

export interface TraceExplainerStep {
  title: string;
  body: string;
  tone: TraceExplainerTone;
}

export interface TraceExplainerInput {
  action: "BUY" | "SELL" | "HOLD" | string | null;
  verdictLabel: string | null;
  capitalGateStatus: CapitalGateStatus;
  cleanPassAllowed: boolean | null;
  unresolvedBlockingCount: number | null;
  unresolvedMaterialCount: number | null;
  totalIssues: number | null;
}

export interface TraceExplainer {
  headline: string;
  summary: string;
  steps: TraceExplainerStep[];
}

export function buildTraceExplainer(input: TraceExplainerInput): TraceExplainer {
  const unresolvedBlocking = Math.max(0, input.unresolvedBlockingCount ?? 0);
  const unresolvedMaterial = Math.max(0, input.unresolvedMaterialCount ?? 0);
  const totalIssues = Math.max(0, input.totalIssues ?? 0);
  const action = input.action ? `${input.action} market action` : "market action";

  return {
    headline: headlineForGate(input.capitalGateStatus),
    summary: summaryForGate(input.capitalGateStatus, input.cleanPassAllowed),
    steps: [
      {
        title: "Trader proposed",
        body: `Trader proposed a ${action} with a structured reasoning trace and recorded evidence fields.`,
        tone: "trader",
      },
      {
        title: "Sentinel challenged",
        body: input.verdictLabel
          ? `A separate Sentinel model family challenged the trace and returned ${input.verdictLabel}.`
          : "Sentinel has not returned a verdict for this trace yet.",
        tone: "sentinel",
      },
      {
        title: "Issues adjudicated",
        body: issueLedgerBody(totalIssues, unresolvedBlocking, unresolvedMaterial),
        tone: unresolvedBlocking > 0 ? "bad" : unresolvedMaterial > 0 ? "warn" : totalIssues > 0 ? "good" : "neutral",
      },
      {
        title: "Capital gate",
        body: capitalGateBody(input.capitalGateStatus),
        tone: toneForGate(input.capitalGateStatus),
      },
    ],
  };
}

function headlineForGate(status: CapitalGateStatus): string {
  switch (status) {
    case "BLOCK":
      return "This trace shows why capital should not move yet.";
    case "REVIEW":
      return "This trace needs review before capital can scale.";
    case "ALLOW_PAPER":
      return "This trace cleared blockers for paper-mode execution.";
    case "ENDORSE":
      return "This trace cleared Sentinel's current issue-ledger gates.";
    case "PENDING_VALIDATION":
    default:
      return "This trace is waiting for adversarial validation.";
  }
}

function summaryForGate(status: CapitalGateStatus, cleanPassAllowed: boolean | null): string {
  if (status === "BLOCK") {
    return "Sentinel found unresolved risk. Clean PASS stayed gated and the capital gate remains BLOCK.";
  }
  if (status === "REVIEW") {
    return "Sentinel left material concerns for human or agent review before capital scales.";
  }
  if (status === "ALLOW_PAPER") {
    return cleanPassAllowed
      ? "No blocking issues remain, so Prism allows paper-mode continuation while live risk limits still apply."
      : "Paper-mode continuation is allowed, but this receipt predates the clean-pass gate.";
  }
  if (status === "ENDORSE") {
    return "No material or blocking issue-ledger gates remain, so the trace is endorsed within configured risk limits.";
  }
  return "No Sentinel verdict has been recorded yet, so Prism keeps the trace out of capital flow.";
}

function issueLedgerBody(totalIssues: number, unresolvedBlocking: number, unresolvedMaterial: number): string {
  if (totalIssues === 0) {
    return "No structured issue ledger was recorded on this receipt, so Prism treats it as legacy evidence.";
  }
  if (unresolvedBlocking > 0) {
    return `Evidence and responses could not resolve ${pluralize(unresolvedBlocking, "blocking issue")}; Prism fails closed.`;
  }
  if (unresolvedMaterial > 0) {
    return `Blocking issues are clear, but ${pluralize(unresolvedMaterial, "material issue")} still need review.`;
  }
  return `No material or blocking issue-ledger gates remain across ${pluralize(totalIssues, "recorded issue")}.`;
}

function capitalGateBody(status: CapitalGateStatus): string {
  switch (status) {
    case "BLOCK":
      return "Clean PASS is gated; capital gate remains BLOCK.";
    case "REVIEW":
      return "Capital gate is REVIEW; keep this in paper mode or route it to an operator.";
    case "ALLOW_PAPER":
      return "Capital gate allows paper mode; live execution still depends on wallet and market risk limits.";
    case "ENDORSE":
      return "Capital gate endorses execution within configured wallet and market risk limits.";
    case "PENDING_VALIDATION":
    default:
      return "Capital remains pending until Sentinel produces a verdict.";
  }
}

function toneForGate(status: CapitalGateStatus): TraceExplainerTone {
  switch (status) {
    case "BLOCK":
      return "bad";
    case "REVIEW":
      return "warn";
    case "ALLOW_PAPER":
    case "ENDORSE":
      return "good";
    case "PENDING_VALIDATION":
    default:
      return "neutral";
  }
}

function pluralize(count: number, label: string): string {
  return `${count} ${label}${count === 1 ? "" : "s"}`;
}
