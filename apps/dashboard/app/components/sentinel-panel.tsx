"use client";

/**
 * Sentinel panel — displays the most recent adversarial verdict.
 *
 * Centerpiece is a ScoreDonut (0-100, color-mapped to verdict spectrum).
 * Around it: verdict label pill, evidence/thesis challenges, critique.
 *
 * Header layout: title (left) · verdict label + expand button (right).
 * Clicking expand opens the same panel in a Dialog with `noExpand` set.
 */

import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Pill } from "@/components/ui/pill";
import { EmptyState } from "@/components/ui/empty-state";
import { LiveDot } from "@/components/ui/live-dot";
import { HashChip } from "@/components/ui/hash-chip";
import { ScoreDonut } from "@/components/ui/score-donut";
import { Separator } from "@/components/ui/separator";
import { Dialog } from "@/components/ui/dialog";
import { ExpandButton } from "@/components/ui/expandable";
import { formatRelativeTime } from "@/lib/utils";
import {
  getIssueLedgerSummary,
  getToolResolutionSummary,
  latestResolutionForChallenge,
  toolResolutionStatusForChallenge,
} from "@/lib/issue-ledger";
import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Target,
} from "lucide-react";
import type { ChallengeResolution, SentinelVerdict } from "@/lib/schemas";

interface SentinelPanelProps {
  verdict: SentinelVerdict | null;
  responseUri: string | null;
  pendingMessage?: string;
  /** Hides the expand button — set when rendered inside the expanded modal. */
  noExpand?: boolean;
}

type VerdictLabel = "REJECT" | "WARN" | "PASS" | "ENDORSE";

function labelTone(label: string): "bad" | "warn" | "good" | "neutral" {
  const map: Record<VerdictLabel, "bad" | "warn" | "good"> = {
    REJECT: "bad",
    WARN: "warn",
    PASS: "good",
    ENDORSE: "good",
  };
  return map[label as VerdictLabel] ?? "neutral";
}

function cidFromUri(uri: string): string | null {
  if (uri.startsWith("ipfs://")) return uri.slice(7);
  return null;
}

export function SentinelPanel({
  verdict,
  responseUri,
  pendingMessage,
  noExpand,
}: SentinelPanelProps) {
  const [modalOpen, setModalOpen] = useState(false);
  const showExpand = !noExpand;

  if (!verdict) {
    return (
      <Card tone="sentinel" className="h-full">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldAlert
              className="h-4 w-4 text-[var(--color-sentinel)]"
              strokeWidth={1.8}
            />
            Sentinel challenges
          </CardTitle>
          <div className="flex items-center gap-2">
            {pendingMessage ? (
              <Pill tone="warn" emphasis="soft" size="xs">
                <LiveDot tone="pending" pulse size="sm" />
                awaiting
              </Pill>
            ) : (
              <Pill tone="sentinel" emphasis="outline" size="xs">
                idle
              </Pill>
            )}
            {showExpand && (
              <ExpandButton
                onClick={() => setModalOpen(true)}
                label="Sentinel challenges"
              />
            )}
          </div>
        </CardHeader>
        <CardContent>
          {pendingMessage ? (
            <div className="flex flex-col items-center justify-center gap-3 py-14 text-center">
              <Loader2
                className="h-6 w-6 animate-spin text-[var(--color-warning)]"
                strokeWidth={1.6}
              />
              <p className="max-w-xs text-sm text-fg-muted">{pendingMessage}</p>
            </div>
          ) : (
            <EmptyState
              title="No verdicts yet"
              description="Run the validation pipeline to populate this panel."
            />
          )}
        </CardContent>
        {showExpand && (
          <Dialog
            open={modalOpen}
            onClose={() => setModalOpen(false)}
            title="Sentinel challenges"
            maxWidthClass="max-w-5xl"
          >
            <SentinelPanel
              verdict={verdict}
              responseUri={responseUri}
              pendingMessage={pendingMessage}
              noExpand
            />
          </Dialog>
        )}
      </Card>
    );
  }

  const ipfsGateway = process.env.NEXT_PUBLIC_IPFS_GATEWAY || "https://gateway.pinata.cloud/ipfs";
  const verdictCid = responseUri ? cidFromUri(responseUri) : null;
  const ipfsHref = verdictCid
    ? `${ipfsGateway}/${verdictCid}`
    : undefined;
  const tone = labelTone(verdict.verdict_label);
  const structuredChallenges = verdict.structured_challenges ?? [];
  const resolutionMetadata = verdict.resolution_metadata ?? null;
  const issueLedgerSummary = getIssueLedgerSummary(verdict);
  const toolResolutionSummary = getToolResolutionSummary(verdict);

  return (
    <>
    <Card tone="sentinel" className="flex h-full flex-col">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldAlert
            className="h-4 w-4 text-[var(--color-sentinel)]"
            strokeWidth={1.8}
          />
          Sentinel challenges
        </CardTitle>
        <div className="flex items-center gap-2">
          <Pill tone={tone === "neutral" ? "sentinel" : tone} emphasis="soft" size="sm">
            {verdict.verdict_label}
          </Pill>
          {showExpand && (
            <ExpandButton
              onClick={() => setModalOpen(true)}
              label="Sentinel challenges"
            />
          )}
        </div>
      </CardHeader>

      <CardContent className="flex-1 space-y-6 overflow-auto p-5">
        {/* Verdict score centerpiece */}
        <div className="flex items-center justify-between gap-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-canvas-sunken)]/40 p-5">
          <ScoreDonut score={verdict.verdict_score} label="verdict" size="lg" />
          <div className="flex-1 space-y-3">
            <div>
              <span className="text-mono text-[10px] font-medium uppercase tracking-[var(--tracking-wide)] text-fg-faint">
                Score interpretation
              </span>
              <p className="mt-1 text-sm leading-relaxed text-fg-muted">
                {scoreNarrative(verdict.verdict_score)}
              </p>
            </div>
            <Pill tone="sentinel" emphasis="outline" size="xs">
              <span className="text-mono">{verdict.model_family}</span>
            </Pill>
          </div>
        </div>

        {/* Verdict explanation */}
        <section>
          <Eyebrow icon={ShieldCheck}>Verdict explanation</Eyebrow>
          <div className="space-y-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-canvas-sunken)]/40 p-4">
            <p className="text-sm leading-relaxed text-fg-muted">
              {issueLedgerSummary.explanation}
            </p>
            <div className="flex flex-wrap gap-2">
              <Pill
                tone={issueLedgerSummary.cleanPassAllowed ? "good" : "bad"}
                emphasis="soft"
                size="xs"
              >
                {issueLedgerSummary.cleanPassAllowed ? "clean PASS allowed" : "clean PASS gated"}
              </Pill>
              <Pill
                tone={issueLedgerSummary.endorsementAllowed ? "good" : "warn"}
                emphasis="soft"
                size="xs"
              >
                {issueLedgerSummary.endorsementAllowed ? "ENDORSE allowed" : "ENDORSE gated"}
              </Pill>
              <Pill tone="sentinel" emphasis="outline" size="xs">
                {issueLedgerSummary.resolvedCount}/{issueLedgerSummary.totalIssues} resolved
              </Pill>
            </div>
            <ul className="space-y-1.5 text-xs leading-relaxed text-fg-faint">
              {issueLedgerSummary.activePolicyConstraints.map((constraint) => (
                <li key={constraint} className="flex gap-2">
                  <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-sentinel)]" />
                  <span>{constraint}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* Structured issue ledger */}
        {structuredChallenges.length > 0 && (
          <section>
            <Eyebrow icon={Target}>
              Issue ledger · {structuredChallenges.length}
            </Eyebrow>
            {resolutionMetadata && (
              <div className="mb-3 space-y-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-canvas-sunken)]/40 px-3 py-2">
                <div className="flex flex-wrap items-center gap-2 text-mono text-[10px] text-fg-faint">
                  <span>
                    confidence · <span className="text-fg-muted">{Math.round(resolutionMetadata.confidence * 100)}%</span>
                  </span>
                  <Separator orientation="vertical" className="h-3" />
                  <span>
                    blockers · <span className="text-fg-muted">{resolutionMetadata.unresolved_blocking_count}</span>
                  </span>
                  <Separator orientation="vertical" className="h-3" />
                  <span>
                    material · <span className="text-fg-muted">{resolutionMetadata.unresolved_material_count}</span>
                  </span>
                  <Separator orientation="vertical" className="h-3" />
                  <span>
                    stop · <span className="text-fg-muted">{resolutionMetadata.stop_reason}</span>
                  </span>
                </div>
                <div className="flex flex-wrap items-center gap-2 text-mono text-[10px] text-fg-faint">
                  <span>
                    tool resolved · <span className="text-fg-muted">{toolResolutionSummary.resolvedCount}</span>
                  </span>
                  <Separator orientation="vertical" className="h-3" />
                  <span>
                    fail-closed · <span className="text-fg-muted">{toolResolutionSummary.noEvidenceCount}</span>
                  </span>
                  <Separator orientation="vertical" className="h-3" />
                  <span>
                    not recorded · <span className="text-fg-muted">{toolResolutionSummary.notRecordedCount}</span>
                  </span>
                  <span className="basis-full text-[11px] normal-case tracking-normal text-fg-faint sm:basis-auto">
                    {toolResolutionSummary.label}
                  </span>
                </div>
              </div>
            )}
            <ol className="space-y-2.5">
              {structuredChallenges.map((challenge) => (
                <StructuredChallengeItem
                  key={challenge.id}
                  challenge={challenge}
                  latestResolution={latestResolutionForChallenge(verdict, challenge.id)}
                  toolStatus={toolResolutionStatusForChallenge(verdict, challenge.id)}
                />
              ))}
            </ol>
          </section>
        )}

        {/* Evidence challenges */}
        {verdict.evidence_challenges.length > 0 && (
          <section>
            <Eyebrow icon={Target}>
              Evidence challenges · {verdict.evidence_challenges.length}
            </Eyebrow>
            <ol className="space-y-2.5">
              {verdict.evidence_challenges.map((challenge, i) => (
                <ChallengeItem
                  key={i}
                  index={i}
                  text={challenge}
                  severity="evidence"
                />
              ))}
            </ol>
          </section>
        )}

        {/* Thesis challenges */}
        {verdict.thesis_challenges.length > 0 && (
          <section>
            <Eyebrow icon={Sparkles}>
              Thesis challenges · {verdict.thesis_challenges.length}
            </Eyebrow>
            <ol className="space-y-2.5">
              {verdict.thesis_challenges.map((challenge, i) => (
                <ChallengeItem
                  key={i}
                  index={i}
                  text={challenge}
                  severity="thesis"
                />
              ))}
            </ol>
          </section>
        )}

        {/* Calibration critique */}
        <section>
          <Eyebrow icon={ShieldAlert}>Calibration critique</Eyebrow>
          <p className="rounded-lg border border-[var(--color-border)] bg-[var(--color-canvas-sunken)]/50 p-3.5 text-sm leading-relaxed text-fg-muted">
            {verdict.calibration_critique}
          </p>
        </section>

        {/* Footer meta */}
        <section className="space-y-3 border-t border-[var(--color-border)] pt-4">
          {verdictCid && (
            <HashChip
              label="verdict IPFS"
              value={verdictCid}
              href={ipfsHref}
              truncate={6}
              size="xs"
            />
          )}
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-mono text-[10px] text-fg-faint">
            <span>
              <span className="text-fg-faint">model · </span>
              <span className="text-fg-muted">{verdict.model_name}</span>
            </span>
            <span>
              <span className="text-fg-faint">created · </span>
              <span className="text-fg-muted">
                {formatRelativeTime(verdict.created_at)}
              </span>
            </span>
            <span className="col-span-2 truncate">
              <span className="text-fg-faint">request_hash · </span>
              <span className="text-fg-muted">
                {verdict.request_hash.slice(0, 32)}…
              </span>
            </span>
          </div>
        </section>
      </CardContent>
    </Card>

    {showExpand && (
      <Dialog
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title="Sentinel challenges"
        description="Full adversarial verdict"
        maxWidthClass="max-w-5xl"
      >
        <SentinelPanel
          verdict={verdict}
          responseUri={responseUri}
          pendingMessage={pendingMessage}
          noExpand
        />
      </Dialog>
    )}
    </>
  );
}

/* ─────────────── Helpers ─────────────── */

function Eyebrow({
  icon: Icon,
  children,
}: {
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  children: React.ReactNode;
}) {
  return (
    <h4 className="mb-3 inline-flex items-center gap-1.5 text-mono text-[10px] font-medium uppercase tracking-[var(--tracking-wide)] text-fg-faint">
      <Icon className="h-3 w-3" strokeWidth={2} />
      {children}
    </h4>
  );
}

type StructuredChallenge = NonNullable<SentinelVerdict["structured_challenges"]>[number];

function StructuredChallengeItem({
  challenge,
  latestResolution,
  toolStatus,
}: {
  challenge: StructuredChallenge;
  latestResolution: ChallengeResolution | null;
  toolStatus: ReturnType<typeof toolResolutionStatusForChallenge>;
}) {
  const accent =
    challenge.severity === "blocking"
      ? "var(--color-danger)"
      : challenge.severity === "material"
        ? "var(--color-warning)"
        : "var(--color-fg-muted)";
  const isResolved = challenge.resolution_status === "resolved" ||
    challenge.resolution_status === "superseded";

  return (
    <li
      className="rounded-lg border p-3.5"
      style={{
        borderColor: `color-mix(in oklch, ${accent} 25%, var(--color-border))`,
        backgroundColor: `color-mix(in oklch, ${accent} 5%, transparent)`,
      }}
    >
      <div className="flex items-start gap-3">
        <span
          className="mt-0.5 inline-flex min-w-16 justify-center rounded px-1.5 py-1 text-mono text-[9px] font-semibold uppercase"
          style={{
            color: accent,
            backgroundColor: `color-mix(in oklch, ${accent} 15%, transparent)`,
          }}
        >
          {challenge.severity}
        </span>
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-2 text-mono text-[10px] text-fg-faint">
            <span>{challenge.id}</span>
            <span>·</span>
            <span>{challenge.type}</span>
            <span>·</span>
            <span className="inline-flex items-center gap-1">
              {isResolved ? (
                <CheckCircle2 className="h-3 w-3 text-[var(--color-success)]" />
              ) : (
                <AlertTriangle className="h-3 w-3 text-[var(--color-warning)]" />
              )}
              {challenge.resolution_status}
            </span>
            {challenge.blocking_pass && (
              <span className="rounded bg-[var(--color-danger)]/15 px-1.5 py-0.5 text-[var(--color-danger)]">
                blocks PASS
              </span>
            )}
            {challenge.claim_ref && (
              <span className="rounded bg-[var(--color-canvas-raised)] px-1.5 py-0.5">
                {challenge.claim_ref}
              </span>
            )}
            <span className={`rounded px-1.5 py-0.5 ${toolStatusClassName(toolStatus)}`}>
              tool: {toolStatusLabel(toolStatus)}
            </span>
          </div>
          <p className="text-sm leading-relaxed text-fg">{challenge.question}</p>
          <p className="mt-1.5 text-xs leading-relaxed text-fg-faint">
            Required: {challenge.required_resolution}
          </p>
          {latestResolution && (
            <div className="mt-3 rounded-md border border-[var(--color-border)] bg-[var(--color-canvas)]/50 p-2.5">
              <div className="mb-1 flex flex-wrap items-center gap-2 text-mono text-[10px] uppercase tracking-[var(--tracking-wide)] text-fg-faint">
                <span>latest resolution</span>
                <span>·</span>
                <span>{latestResolution.status}</span>
                <span>·</span>
                <span>{latestResolution.responder}</span>
                <span>·</span>
                <span>{formatRelativeTime(latestResolution.created_at)}</span>
              </div>
              <p className="text-xs leading-relaxed text-fg-muted">
                {latestResolution.response}
              </p>
            </div>
          )}
        </div>
      </div>
    </li>
  );
}

function toolStatusLabel(status: ReturnType<typeof toolResolutionStatusForChallenge>): string {
  if (status === "resolved") return "resolved";
  if (status === "no_evidence") return "fail-closed";
  return "not attempted";
}

function toolStatusClassName(status: ReturnType<typeof toolResolutionStatusForChallenge>): string {
  if (status === "resolved") {
    return "bg-[var(--color-success)]/15 text-[var(--color-success)]";
  }
  if (status === "no_evidence") {
    return "bg-[var(--color-warning)]/15 text-[var(--color-warning)]";
  }
  return "bg-[var(--color-canvas-raised)] text-fg-faint";
}

function ChallengeItem({
  index,
  text,
  severity,
}: {
  index: number;
  text: string;
  severity: "evidence" | "thesis";
}) {
  // Evidence challenges = red-leaning; thesis challenges = amber.
  const accent =
    severity === "evidence"
      ? "var(--color-danger)"
      : "var(--color-warning)";
  return (
    <li
      className="rounded-lg border p-3.5"
      style={{
        borderColor: `color-mix(in oklch, ${accent} 25%, var(--color-border))`,
        backgroundColor: `color-mix(in oklch, ${accent} 5%, transparent)`,
      }}
    >
      <div className="flex items-start gap-3">
        <span
          className="mt-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded px-1.5 text-mono text-[10px] font-semibold"
          style={{
            color: accent,
            backgroundColor: `color-mix(in oklch, ${accent} 15%, transparent)`,
          }}
        >
          #{index + 1}
        </span>
        <p className="flex-1 text-sm leading-relaxed text-fg">{text}</p>
      </div>
    </li>
  );
}

function scoreNarrative(score: number): string {
  if (score >= 76) return "Strong reasoning. Sentinel found no fatal flaws.";
  if (score >= 51) return "Reasoning passes. Some weak evidence, but thesis holds.";
  if (score >= 26) return "Review required. Trader confidence is not fully supported by evidence.";
  return "Reject. Reasoning has critical flaws. Capital should not move.";
}
