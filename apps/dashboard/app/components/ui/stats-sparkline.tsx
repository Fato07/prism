"use client";

/**
 * StatsSparkline — a tiny recharts area chart for 7-day trends.
 *
 * Generic sparkline that works with either count or numeric data.
 * Falls back to a dash placeholder when data has <2 points.
 * Used on every /stats tile (VAL-STATS-014).
 */

import { AreaChart, Area, ResponsiveContainer } from "recharts";

type Tone = "trader" | "sentinel" | "good" | "warn" | "neutral";

const TONE_COLOR: Record<Tone, string> = {
  trader: "var(--color-trader)",
  sentinel: "var(--color-sentinel)",
  good: "var(--color-verdict-good)",
  warn: "var(--color-warning)",
  neutral: "var(--color-fg-muted)",
};

interface StatsSparklineProps {
  /** Data points — each must have a `value` key. */
  data: { date: string; value: number }[];
  /** Color tone. */
  tone?: Tone;
  /** Chart height in px. */
  height?: number;
  /** Chart width in px. */
  width?: number;
  /** Gradient ID suffix to avoid SVG ID collisions when multiple sparklines render. */
  gradientId?: string;
}

export function StatsSparkline({
  data,
  tone = "neutral",
  height = 32,
  width = 80,
  gradientId = "statsGrad",
}: StatsSparklineProps) {
  if (data.length < 2) {
    return (
      <span
        className="inline-flex items-center text-fg-faint"
        style={{ height }}
        aria-label="Insufficient data for sparkline"
      >
        —
      </span>
    );
  }

  const color = TONE_COLOR[tone];
  const chartData = data.map((d) => ({ date: d.date, value: d.value }));

  return (
    <div style={{ height, width }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={chartData}
          margin={{ top: 2, right: 0, bottom: 2, left: 0 }}
        >
          <defs>
            <linearGradient
              id={`${gradientId}-${tone}`}
              x1="0"
              y1="0"
              x2="0"
              y2="1"
            >
              <stop
                offset="0%"
                stopColor={color}
                stopOpacity={0.3}
              />
              <stop
                offset="100%"
                stopColor={color}
                stopOpacity={0.05}
              />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={1.5}
            fill={`url(#${gradientId}-${tone})`}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
