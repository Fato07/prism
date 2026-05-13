"use client";

/**
 * Trader panel — displays the most recent Trading-R1 trace.
 *
 * Header layout: title (left) · action/model pills + expand button (right).
 * Clicking expand opens the same panel content in a Dialog with `noExpand`
 * set so the expand button doesn't recurse inside the modal.
 */

import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Pill } from "@/components/ui/pill";
import { EmptyState } from "@/components/ui/empty-state";
import { ConfidenceBar } from "@/components/ui/confidence-bar";
import { HashChip } from "@/components/ui/hash-chip";
import { Separator } from "@/components/ui/separator";
import { Dialog } from "@/components/ui/dialog";
import { ExpandButton } from "@/components/ui/expandable";
import { formatRelativeTime } from "@/lib/utils";
import { useState } from "react";
import {
  FileCode,
  AlertTriangle,
  Lightbulb,
  ChevronRight,
  Activity,
  ScrollText,
} from "lucide-react";
import type { TradingR1Trace } from "@/lib/schemas";

interface TraderPanelProps {
  trace: TradingR1Trace | null;
  ipfsCid: string | null;
  contentHash: string | null;
  /** Hides the expand button — set when rendered inside the expanded modal. */
  noExpand?: boolean;
}

function formatProbability(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export function TraderPanel({ trace, ipfsCid, contentHash, noExpand }: TraderPanelProps) {
  const [modalOpen, setModalOpen] = useState(false);
  const showExpand = !noExpand;

  if (!trace) {
    return (
      <Card tone="trader" className="h-full">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileCode
              className="h-4 w-4 text-[var(--color-trader)]"
              strokeWidth={1.8}
            />
            Trader reasoning
          </CardTitle>
          <div className="flex items-center gap-2">
            <Pill tone="trader" emphasis="outline" size="xs">
              idle
            </Pill>
            {showExpand && (
              <ExpandButton
                onClick={() => setModalOpen(true)}
                label="Trader reasoning"
              />
            )}
          </div>
        </CardHeader>
        <CardContent>
          <EmptyState
            title="No traces yet"
            description="Run the trader pipeline to populate this panel."
          />
        </CardContent>
        {showExpand && (
          <Dialog
            open={modalOpen}
            onClose={() => setModalOpen(false)}
            title="Trader reasoning"
            maxWidthClass="max-w-5xl"
          >
            <TraderPanel
              trace={trace}
              ipfsCid={ipfsCid}
              contentHash={contentHash}
              noExpand
            />
          </Dialog>
        )}
      </Card>
    );
  }

  const ipfsHref = ipfsCid
    ? `https://gateway.pinata.cloud/ipfs/${ipfsCid}`
    : undefined;

  return (
    <>
    <Card tone="trader" className="flex h-full flex-col">
      {/* Header */}
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileCode
            className="h-4 w-4 text-[var(--color-trader)]"
            strokeWidth={1.8}
          />
          Trader reasoning
        </CardTitle>
        <div className="flex items-center gap-2">
          <Pill tone={trace.action === "BUY" ? "buy" : trace.action === "SELL" ? "sell" : "neutral"} emphasis="soft" size="sm">
            {trace.action}
          </Pill>
          <Pill tone="trader" emphasis="outline" size="xs">
            <span className="text-mono">{trace.model_family}</span>
          </Pill>
          {showExpand && (
            <ExpandButton
              onClick={() => setModalOpen(true)}
              label="Trader reasoning"
            />
          )}
        </div>
      </CardHeader>

      {/* Scrollable body */}
      <CardContent className="flex-1 space-y-6 overflow-auto p-5">
        {/* Market question */}
        <div>
          <Eyebrow icon={Activity}>Market question</Eyebrow>
          <p className="text-balance text-base font-medium leading-relaxed text-fg">
            {trace.market_question}
          </p>
        </div>

        {/* Probability triplet */}
        <div className="grid grid-cols-3 gap-px overflow-hidden rounded-xl bg-[var(--color-border)]">
          <ProbabilityCell
            label="Raw"
            value={formatProbability(trace.raw_probability)}
          />
          <ProbabilityCell
            label="Vol adj"
            value={trace.volatility_adjustment.toFixed(3)}
            muted
          />
          <ProbabilityCell
            label="Final"
            value={formatProbability(trace.final_probability)}
            emphasized
          />
        </div>

        {/* Size + price limit */}
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-fg-muted">
          <KV label="Size">
            <span className="text-mono text-fg">{trace.size_usdc}</span>
            <span className="ml-1 text-fg-faint">USDC</span>
          </KV>
          <KV label="Price limit">
            <span className="text-mono text-fg">{trace.price_limit}</span>
          </KV>
        </div>

        {/* Thesis composition */}
        <section>
          <Eyebrow icon={Lightbulb}>
            Thesis composition · {trace.thesis.length}
          </Eyebrow>
          <ol className="space-y-2.5">
            {trace.thesis.map((step, i) => (
              <li
                key={i}
                className="rounded-lg border border-[var(--color-border)] bg-[var(--color-canvas-sunken)]/50 p-3.5"
              >
                <div className="flex items-start gap-3">
                  <span className="mt-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded bg-[var(--color-trader)]/15 px-1.5 text-mono text-[10px] font-semibold text-[var(--color-trader)]">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <p className="flex-1 text-sm leading-relaxed text-fg">
                    {step.proposition}
                  </p>
                </div>

                {step.supporting_evidence_ids.length > 0 && (
                  <div className="mt-2.5 flex flex-wrap items-center gap-1.5 pl-8">
                    <span className="text-mono text-[10px] uppercase tracking-[var(--tracking-wide)] text-fg-faint">
                      Evidence
                    </span>
                    {step.supporting_evidence_ids.map((eid) => (
                      <Pill key={eid} tone="trader" emphasis="soft" size="xs">
                        <span className="text-mono">E-{eid}</span>
                      </Pill>
                    ))}
                  </div>
                )}

                {step.risk_factors.length > 0 && (
                  <ul className="mt-2 space-y-1 pl-8">
                    {step.risk_factors.map((rf, j) => (
                      <li
                        key={j}
                        className="inline-flex items-center gap-1.5 rounded-md bg-[var(--color-warning)]/10 px-2 py-0.5 text-xs text-[var(--color-warning)]"
                      >
                        <AlertTriangle className="h-3 w-3" strokeWidth={2} />
                        {rf}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ol>
        </section>

        {/* Evidence */}
        <section>
          <Eyebrow icon={ScrollText}>
            Evidence · {trace.evidence.length}
          </Eyebrow>
          <ul className="space-y-3">
            {trace.evidence.map((ev, i) => (
              <li
                key={i}
                className="rounded-lg border border-[var(--color-border)] bg-[var(--color-canvas-sunken)]/50 p-3.5"
              >
                <div className="flex items-start justify-between gap-3">
                  <p className="flex-1 text-sm leading-relaxed text-fg">
                    {ev.claim}
                  </p>
                  {ev.timestamp && (
                    <span
                      className="shrink-0 text-mono text-[10px] text-fg-faint"
                      title={new Date(ev.timestamp).toLocaleString()}
                    >
                      {formatRelativeTime(ev.timestamp)}
                    </span>
                  )}
                </div>
                <div className="mt-2 flex items-center gap-3">
                  <span className="text-mono text-[10px] uppercase tracking-[var(--tracking-wide)] text-fg-faint">
                    {ev.source}
                  </span>
                  <Separator orientation="vertical" className="h-3" />
                  <ConfidenceBar
                    value={ev.confidence}
                    tone="trader"
                    showLabel
                    className="max-w-32 flex-1"
                  />
                </div>
              </li>
            ))}
          </ul>
        </section>

        {/* Rationale */}
        <section>
          <Eyebrow icon={ChevronRight}>Rationale</Eyebrow>
          <p className="text-sm leading-relaxed text-fg-muted">
            {trace.rationale}
          </p>
        </section>

        {/* Footer meta */}
        <section className="space-y-3 border-t border-[var(--color-border)] pt-4">
          <div className="flex flex-wrap items-center gap-2">
            {ipfsCid && (
              <HashChip
                label="IPFS"
                value={ipfsCid}
                href={ipfsHref}
                truncate={6}
                size="xs"
              />
            )}
            {contentHash && (
              <HashChip
                label="hash"
                value={contentHash}
                truncate={6}
                size="xs"
              />
            )}
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-mono text-[10px] text-fg-faint">
            <span>
              <span className="text-fg-faint">model · </span>
              <span className="text-fg-muted">{trace.model_name}</span>
            </span>
            <span>
              <span className="text-fg-faint">created · </span>
              <span className="text-fg-muted">
                {formatRelativeTime(trace.created_at)}
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
        title="Trader reasoning"
        description="Full Trading-R1 trace"
        maxWidthClass="max-w-5xl"
      >
        <TraderPanel
          trace={trace}
          ipfsCid={ipfsCid}
          contentHash={contentHash}
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

function KV({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="text-fg-faint">{label}</span>
      <span>{children}</span>
    </span>
  );
}

function ProbabilityCell({
  label,
  value,
  muted,
  emphasized,
}: {
  label: string;
  value: string;
  muted?: boolean;
  emphasized?: boolean;
}) {
  return (
    <div className="flex flex-col gap-1 bg-[var(--color-canvas-raised)] p-3 text-center">
      <span className="text-mono text-[10px] font-medium uppercase tracking-[var(--tracking-wide)] text-fg-faint">
        {label}
      </span>
      <span
        className={`text-mono font-semibold tabular-nums ${
          emphasized
            ? "text-base text-[var(--color-trader)]"
            : muted
              ? "text-sm text-fg-muted"
              : "text-sm text-fg"
        }`}
      >
        {value}
      </span>
    </div>
  );
}
