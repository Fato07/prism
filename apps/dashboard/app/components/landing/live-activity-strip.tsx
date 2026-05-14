"use client";

/**
 * LiveActivityStrip — animated count-up cells fed by Neon aggregates.
 *
 * Numbers tween from 0 to the live value when the section enters view.
 * The "live" dot pulses; each cell has its own faint accent bar above
 * the number, color-coded by category.
 *
 * The stats prop comes from lib/stats.ts getActivityStats() — the same
 * source of truth as /stats page tiles (VAL-CROSS-010, VAL-WIDGETS-003).
 */

import type { ActivityStats } from "@/lib/stats";
import {
  motion,
  useInView,
  useMotionValue,
  useTransform,
  animate,
  useReducedMotion,
} from "motion/react";
import { useEffect, useRef } from "react";
import { LiveDot } from "@/components/ui/live-dot";

const FADE_EASE = [0.16, 1, 0.3, 1] as const;

type Tone = "trader" | "sentinel" | "good" | "warn" | "neutral";

const TONE_VAR: Record<Tone, string> = {
  trader: "var(--color-trader)",
  sentinel: "var(--color-sentinel)",
  good: "var(--color-verdict-good)",
  warn: "var(--color-warning)",
  neutral: "var(--color-fg-muted)",
};

interface LiveActivityStripProps {
  /** Shared stats from lib/stats.ts — single source of truth with /stats. */
  stats: ActivityStats;
  waitlistCount: number;
}

export function LiveActivityStrip({
  stats,
  waitlistCount,
}: LiveActivityStripProps) {
  const ref = useRef<HTMLElement>(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });

  const items: { label: string; value: number; tone: Tone }[] = [
    { label: "Verdicts anchored", value: stats.validations, tone: "sentinel" },
    { label: "Unique wallets", value: stats.uniqueWallets, tone: "good" },
    { label: "Traces generated", value: stats.traces, tone: "trader" },
    { label: "On-chain anchors", value: stats.onChainAnchors, tone: "neutral" },
    { label: "External x402 calls", value: stats.externalX402Calls, tone: "good" },
    { label: "Bad reasoning caught", value: stats.flagged, tone: "warn" },
    { label: "Trades placed", value: stats.trades, tone: "good" },
    { label: "Waitlist", value: waitlistCount, tone: "neutral" },
  ];

  return (
    <section
      ref={ref}
      className="border-b border-[var(--color-border)] bg-[var(--color-canvas-sunken)]"
      aria-labelledby="live-activity"
    >
      <div className="mx-auto max-w-6xl px-6 py-12">
        <div className="mb-6 flex items-center gap-3">
          <LiveDot tone="online" pulse />
          <h2
            id="live-activity"
            className="text-mono text-xs font-medium uppercase tracking-[var(--tracking-wide)] text-fg-faint"
          >
            Live · Arc Testnet · pulled from Neon
          </h2>
        </div>

        <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl bg-[var(--color-border)] sm:grid-cols-4 lg:grid-cols-4">
          {items.map((item, i) => (
            <Counter
              key={item.label}
              label={item.label}
              target={item.value}
              tone={item.tone}
              delay={i * 0.08}
              inView={inView}
            />
          ))}
        </div>
      </div>
    </section>
  );
}

interface CounterProps {
  label: string;
  target: number;
  tone: Tone;
  delay: number;
  inView: boolean;
}

function Counter({ label, target, tone, delay, inView }: CounterProps) {
  const reduced = useReducedMotion();
  const motionValue = useMotionValue(reduced ? target : 0);
  const display = useTransform(motionValue, (latest) =>
    Math.round(latest).toLocaleString(),
  );

  useEffect(() => {
    if (!inView || reduced) {
      motionValue.set(target);
      return;
    }
    const controls = animate(motionValue, target, {
      duration: 1.4 + Math.min(target, 100) / 100,
      ease: FADE_EASE,
      delay,
    });
    return () => controls.stop();
  }, [inView, target, reduced, delay, motionValue]);

  return (
    <div className="group relative flex flex-col gap-1 bg-[var(--color-canvas-sunken)] p-5 transition-colors hover:bg-[var(--color-canvas-raised)]">
      {/* Top accent bar — faint by default, brightens on hover */}
      <span
        className="absolute inset-x-5 top-0 h-px opacity-50 transition-opacity duration-300 group-hover:opacity-100"
        style={{ backgroundColor: TONE_VAR[tone] }}
        aria-hidden="true"
      />
      <span className="text-mono text-[10px] font-medium uppercase tracking-[var(--tracking-wide)] text-fg-faint">
        {label}
      </span>
      <motion.span
        className="text-mono text-3xl font-semibold tabular-nums text-fg"
        style={{ color: tone === "neutral" ? undefined : TONE_VAR[tone] }}
      >
        {display}
      </motion.span>
    </div>
  );
}
