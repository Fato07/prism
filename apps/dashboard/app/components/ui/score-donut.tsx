/**
 * ScoreDonut — verdict-score visualization (0-100).
 *
 * Renders a SVG ring with the score arc colored by spectrum position:
 *   0-25  → verdict-bad (red)
 *   26-50 → verdict-mid (amber)
 *   51-75 → verdict-good (light green)
 *   76-100 → verdict-good (saturated green)
 *
 * The big number lives in the center, the label below.
 * Pure SVG, server-renderable, accessible.
 */

import { cn } from "@/lib/utils";

interface ScoreDonutProps {
  score: number; // 0-100
  label?: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}

function colorFromScore(score: number): string {
  if (score < 26) return "var(--color-verdict-bad)";
  if (score < 51) return "var(--color-verdict-mid)";
  return "var(--color-verdict-good)";
}

const DIMENSIONS: Record<NonNullable<ScoreDonutProps["size"]>, {
  outer: number;
  stroke: number;
  numberClass: string;
  labelClass: string;
}> = {
  sm: { outer: 64, stroke: 6, numberClass: "text-xl", labelClass: "text-[10px]" },
  md: { outer: 96, stroke: 8, numberClass: "text-3xl", labelClass: "text-[11px]" },
  lg: { outer: 132, stroke: 10, numberClass: "text-5xl", labelClass: "text-xs" },
};

export function ScoreDonut({
  score,
  label,
  size = "md",
  className,
}: ScoreDonutProps) {
  const clamped = Math.max(0, Math.min(100, score));
  const dim = DIMENSIONS[size];
  const radius = (dim.outer - dim.stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - clamped / 100);
  const color = colorFromScore(clamped);

  return (
    <div
      className={cn("relative inline-flex items-center justify-center", className)}
      style={{ width: dim.outer, height: dim.outer }}
      role="meter"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label ? `${label}: ${clamped} out of 100` : `${clamped} out of 100`}
    >
      <svg
        width={dim.outer}
        height={dim.outer}
        viewBox={`0 0 ${dim.outer} ${dim.outer}`}
        className="-rotate-90"
        aria-hidden="true"
      >
        {/* Track */}
        <circle
          cx={dim.outer / 2}
          cy={dim.outer / 2}
          r={radius}
          fill="none"
          stroke="var(--color-border)"
          strokeWidth={dim.stroke}
        />
        {/* Progress */}
        <circle
          cx={dim.outer / 2}
          cy={dim.outer / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={dim.stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          style={{
            transition: "stroke-dashoffset 600ms var(--ease-out-expo), stroke 200ms ease",
            filter: `drop-shadow(0 0 6px color-mix(in oklch, ${color} 50%, transparent))`,
          }}
        />
      </svg>

      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span
          className={cn("text-mono font-semibold leading-none text-fg", dim.numberClass)}
        >
          {clamped}
        </span>
        {label && (
          <span
            className={cn(
              "mt-1 font-medium uppercase tracking-[var(--tracking-wide)] text-fg-faint",
              dim.labelClass,
            )}
          >
            {label}
          </span>
        )}
      </div>
    </div>
  );
}
