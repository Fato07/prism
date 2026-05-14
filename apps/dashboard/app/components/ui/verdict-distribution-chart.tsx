"use client";

/**
 * VerdictDistributionChart — recharts bar chart showing verdict score buckets.
 *
 * 4 buckets: 0–25, 26–50, 51–75, 76–100.
 * Bars are color-coded from red (low scores) to green (high scores).
 * Required by VAL-STATS-009.
 */

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Cell,
} from "recharts";
import type { VerdictBucket } from "@/lib/stats";

const BAR_COLORS: Record<string, string> = {
  "0–25": "var(--color-verdict-bad, #ef4444)",
  "26–50": "var(--color-warning, #f59e0b)",
  "51–75": "var(--color-trader, #06b6d4)",
  "76–100": "var(--color-verdict-good, #22c55e)",
};

interface VerdictDistributionChartProps {
  data: VerdictBucket[];
  height?: number;
}

export function VerdictDistributionChart({
  data,
  height = 200,
}: VerdictDistributionChartProps) {
  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-sm text-fg-faint"
        style={{ height }}
      >
        No verdict data yet
      </div>
    );
  }

  return (
    <div style={{ height, width: "100%" }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          margin={{ top: 8, right: 16, bottom: 0, left: 0 }}
        >
          <XAxis
            dataKey="label"
            tick={{ fontSize: 11, fill: "var(--color-fg-faint)" }}
            axisLine={{ stroke: "var(--color-border)" }}
            tickLine={false}
          />
          <YAxis
            allowDecimals={false}
            tick={{ fontSize: 11, fill: "var(--color-fg-faint)" }}
            axisLine={false}
            tickLine={false}
            width={30}
          />
          <Bar dataKey="count" radius={[4, 4, 0, 0]} isAnimationActive={false}>
            {data.map((entry) => (
              <Cell
                key={entry.label}
                fill={BAR_COLORS[entry.label] ?? "var(--color-fg-muted)"}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
