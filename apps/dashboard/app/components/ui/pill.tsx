/**
 * Pill — a richer badge with brand-aware tones.
 *
 * Replaces the old `Badge` (which stays for backward compat with existing
 * panels). Pill variants map to Prism's tonal system rather than ad-hoc
 * Tailwind colors, so the look stays coherent as we add components.
 */

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

type PillTone =
  | "neutral"
  | "trader"
  | "sentinel"
  | "good"
  | "warn"
  | "bad"
  | "info"
  | "buy"
  | "sell";
type PillSize = "xs" | "sm" | "md";

interface PillProps {
  tone?: PillTone;
  size?: PillSize;
  /**
   * Visual emphasis:
   *   - `soft`    — default; tonal tint with matching border
   *   - `solid`   — high-emphasis filled
   *   - `outline` — minimal, outlined only
   *   - `glass`   — dark glass backdrop with tonal border + bright text;
   *                use when floating on shaders / busy backgrounds.
   */
  emphasis?: "solid" | "soft" | "outline" | "glass";
  className?: string;
  children: ReactNode;
}

const TONE_STYLES: Record<
  PillTone,
  { soft: string; solid: string; outline: string; glass: string }
> = {
  neutral: {
    soft: "bg-[var(--color-canvas-raised)] text-fg border border-[var(--color-border)]",
    solid: "bg-fg/90 text-canvas border border-fg/0",
    outline: "border border-[var(--color-border-strong)] text-fg-muted",
    glass:
      "bg-[var(--color-canvas)]/70 text-fg border border-[var(--color-border-strong)] backdrop-blur-md shadow-[0_1px_0_0_oklch(1_0_0/0.05)_inset]",
  },
  trader: {
    soft: "bg-[var(--color-trader)]/10 text-[var(--color-trader)] border border-[var(--color-trader)]/30",
    solid: "bg-[var(--color-trader)] text-canvas border border-[var(--color-trader)]",
    outline: "border border-[var(--color-trader)]/50 text-[var(--color-trader)]",
    glass:
      "bg-[var(--color-canvas)]/70 text-[var(--color-trader)] border border-[var(--color-trader)]/55 backdrop-blur-md shadow-[0_1px_0_0_oklch(1_0_0/0.05)_inset]",
  },
  sentinel: {
    soft: "bg-[var(--color-sentinel)]/10 text-[var(--color-sentinel)] border border-[var(--color-sentinel)]/30",
    solid: "bg-[var(--color-sentinel)] text-canvas border border-[var(--color-sentinel)]",
    outline: "border border-[var(--color-sentinel)]/50 text-[var(--color-sentinel)]",
    glass:
      "bg-[var(--color-canvas)]/70 text-[var(--color-sentinel)] border border-[var(--color-sentinel)]/55 backdrop-blur-md shadow-[0_1px_0_0_oklch(1_0_0/0.05)_inset]",
  },
  good: {
    soft: "bg-[var(--color-success)]/10 text-[var(--color-success)] border border-[var(--color-success)]/30",
    solid: "bg-[var(--color-success)] text-canvas border border-[var(--color-success)]",
    outline: "border border-[var(--color-success)]/50 text-[var(--color-success)]",
    glass:
      "bg-[var(--color-canvas)]/70 text-[var(--color-success)] border border-[var(--color-success)]/55 backdrop-blur-md shadow-[0_1px_0_0_oklch(1_0_0/0.05)_inset]",
  },
  warn: {
    soft: "bg-[var(--color-warning)]/10 text-[var(--color-warning)] border border-[var(--color-warning)]/30",
    solid: "bg-[var(--color-warning)] text-canvas border border-[var(--color-warning)]",
    outline: "border border-[var(--color-warning)]/50 text-[var(--color-warning)]",
    glass:
      "bg-[var(--color-canvas)]/70 text-[var(--color-warning)] border border-[var(--color-warning)]/55 backdrop-blur-md shadow-[0_1px_0_0_oklch(1_0_0/0.05)_inset]",
  },
  bad: {
    soft: "bg-[var(--color-danger)]/10 text-[var(--color-danger)] border border-[var(--color-danger)]/30",
    solid: "bg-[var(--color-danger)] text-canvas border border-[var(--color-danger)]",
    outline: "border border-[var(--color-danger)]/50 text-[var(--color-danger)]",
    glass:
      "bg-[var(--color-canvas)]/70 text-[var(--color-danger)] border border-[var(--color-danger)]/55 backdrop-blur-md shadow-[0_1px_0_0_oklch(1_0_0/0.05)_inset]",
  },
  info: {
    soft: "bg-[var(--color-info)]/10 text-[var(--color-info)] border border-[var(--color-info)]/30",
    solid: "bg-[var(--color-info)] text-canvas border border-[var(--color-info)]",
    outline: "border border-[var(--color-info)]/50 text-[var(--color-info)]",
    glass:
      "bg-[var(--color-canvas)]/70 text-[var(--color-info)] border border-[var(--color-info)]/55 backdrop-blur-md shadow-[0_1px_0_0_oklch(1_0_0/0.05)_inset]",
  },
  buy: {
    soft: "bg-[var(--color-verdict-good)]/12 text-[var(--color-verdict-good)] border border-[var(--color-verdict-good)]/30",
    solid: "bg-[var(--color-verdict-good)] text-canvas border border-[var(--color-verdict-good)]",
    outline: "border border-[var(--color-verdict-good)]/50 text-[var(--color-verdict-good)]",
    glass:
      "bg-[var(--color-canvas)]/70 text-[var(--color-verdict-good)] border border-[var(--color-verdict-good)]/55 backdrop-blur-md shadow-[0_1px_0_0_oklch(1_0_0/0.05)_inset]",
  },
  sell: {
    soft: "bg-[var(--color-verdict-bad)]/12 text-[var(--color-verdict-bad)] border border-[var(--color-verdict-bad)]/30",
    solid: "bg-[var(--color-verdict-bad)] text-canvas border border-[var(--color-verdict-bad)]",
    outline: "border border-[var(--color-verdict-bad)]/50 text-[var(--color-verdict-bad)]",
    glass:
      "bg-[var(--color-canvas)]/70 text-[var(--color-verdict-bad)] border border-[var(--color-verdict-bad)]/55 backdrop-blur-md shadow-[0_1px_0_0_oklch(1_0_0/0.05)_inset]",
  },
};

const SIZE_STYLES: Record<PillSize, string> = {
  xs: "text-[10px] px-1.5 py-0.5 leading-none rounded-md",
  sm: "text-xs px-2 py-0.5 leading-tight rounded-md",
  md: "text-sm px-2.5 py-1 leading-tight rounded-lg",
};

export function Pill({
  tone = "neutral",
  size = "sm",
  emphasis = "soft",
  className,
  children,
}: PillProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 font-medium tracking-tight whitespace-nowrap",
        TONE_STYLES[tone][emphasis],
        SIZE_STYLES[size],
        className,
      )}
    >
      {children}
    </span>
  );
}
