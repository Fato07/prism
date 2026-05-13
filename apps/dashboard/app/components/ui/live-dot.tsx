/**
 * LiveDot — a pulsing status indicator.
 *
 * Used in:
 *   - Dashboard header: agent online/offline rows
 *   - Pending-validation badge on sentinel panel
 *   - Block-height ticker
 */

import { cn } from "@/lib/utils";

type LiveDotTone = "online" | "pending" | "offline" | "trader" | "sentinel";

interface LiveDotProps {
  tone?: LiveDotTone;
  size?: "sm" | "md";
  pulse?: boolean;
  label?: string;
  className?: string;
}

const TONE_CLASSES: Record<LiveDotTone, { dot: string; halo: string }> = {
  online: {
    dot: "bg-[var(--color-success)]",
    halo: "bg-[var(--color-success)]/35",
  },
  pending: {
    dot: "bg-[var(--color-warning)]",
    halo: "bg-[var(--color-warning)]/35",
  },
  offline: {
    dot: "bg-[var(--color-fg-faint)]",
    halo: "bg-[var(--color-fg-faint)]/0",
  },
  trader: {
    dot: "bg-[var(--color-trader)]",
    halo: "bg-[var(--color-trader)]/30",
  },
  sentinel: {
    dot: "bg-[var(--color-sentinel)]",
    halo: "bg-[var(--color-sentinel)]/30",
  },
};

export function LiveDot({
  tone = "online",
  size = "sm",
  pulse = true,
  label,
  className,
}: LiveDotProps) {
  const dim = size === "sm" ? "h-1.5 w-1.5" : "h-2 w-2";
  const haloDim = size === "sm" ? "h-3 w-3" : "h-4 w-4";
  const { dot, halo } = TONE_CLASSES[tone];

  return (
    <span
      className={cn("inline-flex items-center gap-2", className)}
      aria-live={tone === "pending" ? "polite" : "off"}
    >
      <span className="relative inline-flex items-center justify-center">
        {pulse && tone !== "offline" && (
          <span
            className={cn(
              "absolute rounded-full",
              haloDim,
              halo,
              "animate-pulse-dot",
            )}
            aria-hidden="true"
          />
        )}
        <span className={cn("relative rounded-full", dim, dot)} />
      </span>
      {label && (
        <span className="text-xs text-fg-muted">{label}</span>
      )}
    </span>
  );
}
