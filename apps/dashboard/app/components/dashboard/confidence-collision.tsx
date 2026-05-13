"use client";

/**
 * ConfidenceCollision — the adversarial-tension viz between trader & sentinel.
 *
 * Renders the trader's `final_probability` (0..1, mapped to 0..100) and the
 * sentinel's `verdict_score` (0..100) on a shared horizontal axis. The two
 * markers are connected by a "tension band" colored by the magnitude of the
 * gap: small gap → green (alignment), wide gap → magenta (divergence).
 *
 * This is the product's thesis distilled into one image: two independent
 * agents, two opinions, one visible discrepancy.
 */

import { motion, useInView } from "motion/react";
import { useRef, useState } from "react";
import { Pill } from "@/components/ui/pill";
import { Dialog } from "@/components/ui/dialog";
import { ExpandButton } from "@/components/ui/expandable";

interface ConfidenceCollisionProps {
  /** Trader's stated final probability, 0..1. */
  traderProbability: number | null;
  /** Sentinel's verdict score, 0..100. */
  sentinelScore: number | null;
  /** Action label so the trader marker can communicate direction (BUY/SELL/etc). */
  traderAction?: string | null;
  /** Sentinel verdict label (REJECT/WARN/PASS/ENDORSE). */
  sentinelLabel?: string | null;
  /** Hides the expand button — set when rendered inside the expanded modal. */
  noExpand?: boolean;
}

const FADE_EASE = [0.16, 1, 0.3, 1] as const;

function gapTone(gap: number): {
  label: string;
  color: string;
  tone: "good" | "warn" | "sentinel";
} {
  if (gap <= 8) {
    return {
      label: "Aligned",
      color: "var(--color-verdict-good)",
      tone: "good",
    };
  }
  if (gap <= 25) {
    return {
      label: `${gap.toFixed(0)}-pt gap`,
      color: "var(--color-warning)",
      tone: "warn",
    };
  }
  return {
    label: "Adversarial divergence",
    color: "var(--color-sentinel)",
    tone: "sentinel",
  };
}

export function ConfidenceCollision({
  traderProbability,
  sentinelScore,
  traderAction,
  sentinelLabel,
  noExpand,
}: ConfidenceCollisionProps) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: false, margin: "-40px" });
  const [modalOpen, setModalOpen] = useState(false);
  const showExpand = !noExpand;

  const hasData = traderProbability !== null && sentinelScore !== null;

  if (!hasData) {
    return (
      <div
        ref={ref}
        className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-canvas-raised)]/40 p-5 backdrop-blur-sm"
      >
        <div className="flex items-center justify-between">
          <div className="text-mono text-[10px] font-medium uppercase tracking-[var(--tracking-wide)] text-fg-faint">
            Adversarial tension
          </div>
          {showExpand && (
            <ExpandButton
              onClick={() => setModalOpen(true)}
              label="Adversarial tension"
            />
          )}
        </div>
        <p className="mt-2 text-sm text-fg-faint">
          Waiting for a trace + verdict pair to compare confidences.
        </p>
      </div>
    );
  }

  const traderPct = Math.max(0, Math.min(100, traderProbability * 100));
  const sentinelPct = Math.max(0, Math.min(100, sentinelScore));
  const gap = Math.abs(traderPct - sentinelPct);
  const { label: gapLabel, color: gapColor, tone: gapToneName } = gapTone(gap);

  const leftPct = Math.min(traderPct, sentinelPct);
  const rightPct = Math.max(traderPct, sentinelPct);
  const bandWidth = Math.max(rightPct - leftPct, 0.5);

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 8 }}
      animate={inView ? { opacity: 1, y: 0 } : { opacity: 0, y: 8 }}
      transition={{ duration: 0.55, ease: FADE_EASE }}
      className="relative overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-canvas-raised)]/65 p-5 backdrop-blur-sm"
    >
      {/* Subtle accent glow that reacts to gap magnitude */}
      <span
        className="pointer-events-none absolute -right-20 -top-20 h-44 w-44 rounded-full blur-3xl"
        style={{
          backgroundColor: `color-mix(in oklch, ${gapColor} 35%, transparent)`,
          opacity: 0.4,
        }}
        aria-hidden="true"
      />

      {/* Header row */}
      <div className="relative mb-4 flex items-center justify-between gap-3">
        <div className="text-mono text-[10px] font-medium uppercase tracking-[var(--tracking-wide)] text-fg-faint">
          Adversarial tension
        </div>
        <div className="flex items-center gap-2">
          <Pill tone={gapToneName} emphasis="soft" size="xs">
            {gapLabel}
          </Pill>
          {showExpand && (
            <ExpandButton
              onClick={() => setModalOpen(true)}
              label="Adversarial tension"
            />
          )}
        </div>
      </div>

      {/* Endpoint summary */}
      <div className="relative mb-4 grid grid-cols-2 gap-3 text-mono text-[11px]">
        <div className="flex items-center justify-between">
          <span className="inline-flex items-center gap-1.5 text-fg-faint">
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{ backgroundColor: "var(--color-trader)" }}
            />
            Trader
          </span>
          <span className="text-fg-muted">
            <span className="text-[var(--color-trader)] tabular-nums">
              {traderPct.toFixed(0)}
            </span>
            <span className="ml-1 text-fg-faint">% conf</span>
            {traderAction && (
              <span className="ml-1.5 text-fg-faint">{traderAction}</span>
            )}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="inline-flex items-center gap-1.5 text-fg-faint">
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{ backgroundColor: "var(--color-sentinel)" }}
            />
            Sentinel
          </span>
          <span className="text-fg-muted">
            <span className="text-[var(--color-sentinel)] tabular-nums">
              {sentinelPct.toFixed(0)}
            </span>
            <span className="ml-1 text-fg-faint">/ 100</span>
            {sentinelLabel && (
              <span className="ml-1.5 text-fg-faint">{sentinelLabel}</span>
            )}
          </span>
        </div>
      </div>

      {/* Track */}
      <div className="relative">
        <div className="relative h-9">
          {/* Track line */}
          <div className="absolute left-0 right-0 top-1/2 h-px -translate-y-1/2 bg-[var(--color-border)]" />

          {/* Tension band — animates width */}
          <motion.div
            className="absolute top-1/2 h-1 -translate-y-1/2 rounded-full"
            style={{
              left: `${leftPct}%`,
              backgroundColor: gapColor,
              boxShadow: `0 0 12px -2px color-mix(in oklch, ${gapColor} 60%, transparent)`,
            }}
            initial={{ width: 0 }}
            animate={inView ? { width: `${bandWidth}%` } : { width: 0 }}
            transition={{ duration: 0.7, ease: FADE_EASE, delay: 0.15 }}
            aria-hidden="true"
          />

          {/* Trader marker */}
          <Marker
            pct={traderPct}
            color="var(--color-trader)"
            label="T"
            inView={inView}
            delay={0.25}
          />

          {/* Sentinel marker */}
          <Marker
            pct={sentinelPct}
            color="var(--color-sentinel)"
            label="S"
            inView={inView}
            delay={0.35}
          />
        </div>

        {/* Axis ticks */}
        <div className="mt-1 flex items-center justify-between text-mono text-[10px] text-fg-faint">
          <span>0</span>
          <span>25</span>
          <span>50</span>
          <span>75</span>
          <span>100</span>
        </div>
      </div>

      {showExpand && (
        <Dialog
          open={modalOpen}
          onClose={() => setModalOpen(false)}
          title="Adversarial tension"
          description="Gap between trader confidence and sentinel verdict"
          maxWidthClass="max-w-3xl"
        >
          <div className="p-5">
            <ConfidenceCollision
              traderProbability={traderProbability}
              sentinelScore={sentinelScore}
              traderAction={traderAction}
              sentinelLabel={sentinelLabel}
              noExpand
            />
          </div>
        </Dialog>
      )}
    </motion.div>
  );
}

interface MarkerProps {
  pct: number;
  color: string;
  label: string;
  inView: boolean;
  delay: number;
}

function Marker({ pct, color, label, inView, delay }: MarkerProps) {
  return (
    <motion.div
      className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2"
      style={{ left: `${pct}%` }}
      initial={{ scale: 0, opacity: 0 }}
      animate={inView ? { scale: 1, opacity: 1 } : { scale: 0, opacity: 0 }}
      transition={{ duration: 0.5, ease: FADE_EASE, delay }}
    >
      {/* Halo */}
      <span
        className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 animate-pulse-dot rounded-full"
        style={{
          width: 18,
          height: 18,
          backgroundColor: `color-mix(in oklch, ${color} 35%, transparent)`,
        }}
        aria-hidden="true"
      />
      {/* Dot */}
      <span
        className="relative inline-flex h-3.5 w-3.5 items-center justify-center rounded-full text-mono text-[8px] font-semibold text-canvas"
        style={{ backgroundColor: color }}
      >
        {label}
      </span>
    </motion.div>
  );
}
