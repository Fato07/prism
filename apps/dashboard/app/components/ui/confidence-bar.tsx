/**
 * ConfidenceBar — horizontal 0-1 confidence indicator.
 *
 * Used to visualize evidence confidence and trader probabilities.
 * Color shifts along the verdict spectrum at higher confidence.
 */

import { cn } from "@/lib/utils";

interface ConfidenceBarProps {
  /** 0..1 — values outside this range are clamped. */
  value: number;
  /** Visual tone family. `neutral` uses the verdict spectrum; brand tones lock the color. */
  tone?: "neutral" | "trader" | "sentinel";
  showLabel?: boolean;
  className?: string;
}

export function ConfidenceBar({
  value,
  tone = "neutral",
  showLabel = true,
  className,
}: ConfidenceBarProps) {
  const clamped = Math.max(0, Math.min(1, value));
  const percent = Math.round(clamped * 100);

  let barColor: string;
  if (tone === "trader") {
    barColor = "var(--color-trader)";
  } else if (tone === "sentinel") {
    barColor = "var(--color-sentinel)";
  } else if (clamped < 0.34) {
    barColor = "var(--color-verdict-bad)";
  } else if (clamped < 0.67) {
    barColor = "var(--color-verdict-mid)";
  } else {
    barColor = "var(--color-verdict-good)";
  }

  return (
    <div
      className={cn("inline-flex w-full items-center gap-2", className)}
      role="meter"
      aria-valuenow={percent}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div className="relative h-1 flex-1 overflow-hidden rounded-full bg-[var(--color-canvas-sunken)]">
        <div
          className="absolute inset-y-0 left-0 rounded-full"
          style={{
            width: `${percent}%`,
            backgroundColor: barColor,
            boxShadow: `0 0 8px -2px color-mix(in oklch, ${barColor} 55%, transparent)`,
            transition: "width 500ms var(--ease-out-expo)",
          }}
        />
      </div>
      {showLabel && (
        <span className="text-mono text-[10px] font-medium tabular-nums text-fg-muted">
          {percent}%
        </span>
      )}
    </div>
  );
}
