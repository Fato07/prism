"use client";

/**
 * VerdictHistoryStrip — a slim sparkline-style row of recent verdicts.
 *
 * Each bar's color is mapped to the verdict spectrum (red → amber → green)
 * and its height to the score (40-100% of the strip). Hovering reveals a
 * compact tooltip with the score, age, and a hash chip.
 *
 * Animates in on mount with a staggered slide-up; subsequent updates
 * morph the bars rather than re-stagger so a fresh poll feels alive
 * without re-introducing the whole row.
 */

import { motion } from "motion/react";
import { useState } from "react";
import { Activity } from "lucide-react";
import { formatRelativeTime } from "@/lib/utils";
import { Dialog } from "@/components/ui/dialog";
import { ExpandButton } from "@/components/ui/expandable";
import type { VerdictHistoryEntry } from "@/lib/db";

interface VerdictHistoryStripProps {
  entries: VerdictHistoryEntry[]; // newest first
  noExpand?: boolean;
}

const FADE_EASE = [0.16, 1, 0.3, 1] as const;

function colorForScore(score: number): string {
  if (score < 26) return "var(--color-verdict-bad)";
  if (score < 51) return "var(--color-verdict-mid)";
  if (score < 76) return "oklch(0.78 0.18 110)"; // light green
  return "var(--color-verdict-good)";
}

function heightForScore(score: number): number {
  // Map 0..100 → 28..100 (percent of strip height), so even a low score
  // shows a visible bar.
  return 28 + (Math.max(0, Math.min(100, score)) / 100) * 72;
}

function labelForScore(score: number): string {
  if (score < 26) return "REJECT";
  if (score < 51) return "WARN";
  if (score < 76) return "PASS";
  return "ENDORSE";
}

export function VerdictHistoryStrip({ entries, noExpand }: VerdictHistoryStripProps) {
  const [modalOpen, setModalOpen] = useState(false);
  const showExpand = !noExpand;

  if (entries.length === 0) {
    return (
      <div className="flex items-center justify-between gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-canvas-raised)]/60 px-4 py-3 backdrop-blur-sm">
        <div className="flex items-center gap-2">
          <Activity className="h-3.5 w-3.5 text-fg-faint" strokeWidth={1.8} />
          <span className="text-mono text-xs text-fg-faint">
            No verdicts yet — history will appear here once validations run.
          </span>
        </div>
        {showExpand && (
          <ExpandButton
            onClick={() => setModalOpen(true)}
            label="Verdict history"
          />
        )}
      </div>
    );
  }

  // Display oldest → newest so the most recent reads on the right.
  const ordered = [...entries].reverse();

  // Summary metrics
  const avg =
    ordered.reduce((acc, e) => acc + e.verdict_score, 0) / ordered.length;
  const minScore = Math.min(...ordered.map((e) => e.verdict_score));
  const maxScore = Math.max(...ordered.map((e) => e.verdict_score));
  const flagged = ordered.filter((e) => e.verdict_score < 50).length;

  return (
    <>
    <div className="overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-canvas-raised)]/60 backdrop-blur-sm">
      {/* Header row */}
      <div className="flex items-center justify-between gap-3 border-b border-[var(--color-border)] px-4 py-2.5">
        <div className="flex items-center gap-2">
          <Activity
            className="h-3.5 w-3.5 text-[var(--color-sentinel)]"
            strokeWidth={1.8}
          />
          <span className="text-mono text-[11px] font-medium uppercase tracking-[var(--tracking-wide)] text-fg-muted">
            Verdict history · last {ordered.length}
          </span>
        </div>
        <div className="flex items-center gap-3 text-mono text-[10px] text-fg-faint">
          <Stat label="avg" value={avg.toFixed(0)} />
          <Stat label="min" value={String(minScore)} />
          <Stat label="max" value={String(maxScore)} />
          <Stat
            label="flagged"
            value={String(flagged)}
            tone={flagged > 0 ? "warn" : undefined}
          />
          {showExpand && (
            <ExpandButton
              onClick={() => setModalOpen(true)}
              label="Verdict history"
              className="ml-1"
            />
          )}
        </div>
      </div>

      {/* Bars */}
      <div className="flex h-20 items-end gap-[2px] px-4 py-2">
        {ordered.map((entry, i) => {
          const color = colorForScore(entry.verdict_score);
          const heightPct = heightForScore(entry.verdict_score);
          return (
            <motion.div
              key={entry.request_hash}
              initial={{ scaleY: 0, opacity: 0 }}
              animate={{ scaleY: 1, opacity: 1 }}
              transition={{
                duration: 0.4,
                ease: FADE_EASE,
                delay: Math.min(i * 0.018, 0.55),
              }}
              style={{
                height: `${heightPct}%`,
                backgroundColor: color,
                transformOrigin: "bottom",
                boxShadow: `0 0 6px -2px color-mix(in oklch, ${color} 60%, transparent)`,
              }}
              className="group relative min-w-[3px] flex-1 cursor-default rounded-t-sm transition-all hover:scale-y-105 hover:!opacity-100"
              aria-label={`Verdict ${entry.verdict_score} on ${entry.created_at}`}
            >
              {/* Tooltip */}
              <div
                className="pointer-events-none absolute bottom-[calc(100%+8px)] left-1/2 z-10 hidden -translate-x-1/2 group-hover:block"
                role="tooltip"
              >
                <div
                  className="whitespace-nowrap rounded-md border px-2.5 py-1.5 text-xs shadow-lg"
                  style={{
                    backgroundColor: "var(--color-canvas-raised)",
                    borderColor: `color-mix(in oklch, ${color} 40%, var(--color-border))`,
                  }}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className="text-mono font-semibold"
                      style={{ color }}
                    >
                      {entry.verdict_score}
                    </span>
                    <span className="text-mono text-[10px] uppercase tracking-[var(--tracking-wide)] text-fg-muted">
                      {labelForScore(entry.verdict_score)}
                    </span>
                  </div>
                  <div className="mt-0.5 text-[10px] text-fg-faint">
                    {formatRelativeTime(entry.created_at)}
                  </div>
                </div>
                {/* Arrow */}
                <div
                  className="mx-auto h-2 w-2 rotate-45 border-b border-r"
                  style={{
                    marginTop: "-4px",
                    backgroundColor: "var(--color-canvas-raised)",
                    borderColor: `color-mix(in oklch, ${color} 40%, var(--color-border))`,
                  }}
                  aria-hidden="true"
                />
              </div>
            </motion.div>
          );
        })}
      </div>

      {/* Axis hint */}
      <div className="flex items-center justify-between border-t border-[var(--color-border)] px-4 py-2 text-mono text-[10px] text-fg-faint">
        <span>← older</span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-1 w-3 rounded-full bg-[var(--color-verdict-bad)]" />
          reject
          <span className="ml-2 h-1 w-3 rounded-full bg-[var(--color-verdict-mid)]" />
          warn
          <span
            className="ml-2 h-1 w-3 rounded-full"
            style={{ backgroundColor: "oklch(0.78 0.18 110)" }}
          />
          pass
          <span className="ml-2 h-1 w-3 rounded-full bg-[var(--color-verdict-good)]" />
          endorse
        </span>
        <span>newest →</span>
      </div>
    </div>

    {showExpand && (
      <Dialog
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title="Verdict history"
        description={`Last ${entries.length} sentinel verdicts — color-mapped by score`}
        maxWidthClass="max-w-6xl"
      >
        <div className="p-5">
          <VerdictHistoryStrip entries={entries} noExpand />
        </div>
      </Dialog>
    )}
    </>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "warn";
}) {
  return (
    <span className="inline-flex items-baseline gap-1">
      <span className="uppercase tracking-[var(--tracking-wide)] text-fg-faint">
        {label}
      </span>
      <span
        className={
          tone === "warn"
            ? "text-[var(--color-warning)] tabular-nums"
            : "text-fg tabular-nums"
        }
      >
        {value}
      </span>
    </span>
  );
}
