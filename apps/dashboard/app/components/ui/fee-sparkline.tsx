"use client";

/**
 * FeeSparkline — a tiny recharts area chart showing daily fee accumulation.
 *
 * Renders an inline sparkline (no axes, no tooltips by default).
 * Falls back to a dash placeholder when data has <2 points.
 */

import { AreaChart, Area, ResponsiveContainer } from "recharts";

interface FeeSparklineProps {
  data: { date: string; fee: string }[];
  color?: string;
  height?: number;
  className?: string;
}

export function FeeSparkline({
  data,
  color = "var(--color-verdict-good)",
  height = 32,
  className,
}: FeeSparklineProps) {
  if (data.length < 2) {
    // Not enough data for a sparkline — render a subtle dash placeholder
    return (
      <span
        className={`inline-flex items-center text-fg-faint ${className ?? ""}`}
        style={{ height }}
        aria-label="Insufficient data for sparkline"
      >
        —
      </span>
    );
  }

  const chartData = data.map((d) => ({
    date: d.date,
    fee: parseFloat(d.fee) || 0,
  }));

  return (
    <div className={className} style={{ height, width: 80 }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData} margin={{ top: 2, right: 0, bottom: 2, left: 0 }}>
          <defs>
            <linearGradient id="feeGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.3} />
              <stop offset="100%" stopColor={color} stopOpacity={0.05} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="fee"
            stroke={color}
            strokeWidth={1.5}
            fill="url(#feeGrad)"
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
