import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate } from "remotion";

/**
 * Scene 6: Platform Play — x402 Sentinel-as-a-Service (68-78s)
 * Other agents call our sentinel as a service. $0.01 USDC per validation.
 * x402 protocol, Circle Gateway settlement on Base, MCP endpoint.
 */
export const PlatformPlay: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const opacity = (start: number) =>
    interpolate(frame, [fps * start, fps * (start + 0.4)], [0, 1], {
      extrapolateRight: "clamp",
      extrapolateLeft: "clamp",
    });

  const flowSteps = [
    { from: "External Agent", to: "Sentinel MCP", label: "POST /validate", color: "#3b82f6" },
    { from: "x402", to: "Circle Gateway", label: "Settle $0.01 USDC on Base", color: "#8b5cf6" },
    { from: "Sentinel MCP", to: "External Agent", label: "Return verdict", color: "#10b981" },
  ];

  return (
    <AbsoluteFill
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: 60,
        gap: 32,
      }}
    >
      <div
        style={{
          opacity: opacity(0),
          color: "white",
          fontSize: 38,
          fontFamily: "'Inter', sans-serif",
          fontWeight: 700,
          textAlign: "center",
        }}
      >
        Sentinel-as-a-Service
      </div>

      <div
        style={{
          opacity: opacity(0.8),
          color: "rgba(255,255,255,0.6)",
          fontSize: 22,
          textAlign: "center",
        }}
      >
        Other agents call our sentinel — one cent per validation.
      </div>

      {/* Payment flow diagram */}
      <div style={{ display: "flex", flexDirection: "column", gap: 16, width: "100%" }}>
        {flowSteps.map((step, i) => (
          <div
            key={i}
            style={{
              opacity: opacity(1.5 + i * 1.5),
              display: "flex",
              alignItems: "center",
              gap: 20,
              justifyContent: "center",
            }}
          >
            <div
              style={{
                color: step.color,
                fontSize: 20,
                fontWeight: 600,
                minWidth: 160,
                textAlign: "right",
              }}
            >
              {step.from}
            </div>
            <div
              style={{
                color: "rgba(255,255,255,0.5)",
                fontSize: 18,
                padding: "8px 20px",
                backgroundColor: `${step.color}15`,
                border: `1px solid ${step.color}30`,
                borderRadius: 8,
              }}
            >
              {step.label}
            </div>
            <div
              style={{
                color: step.color,
                fontSize: 20,
                fontWeight: 600,
                minWidth: 160,
              }}
            >
              {step.to}
            </div>
          </div>
        ))}
      </div>

      {/* Platform callout */}
      <div
        style={{
          opacity: opacity(6),
          color: "#8b5cf6",
          fontSize: 26,
          fontWeight: 600,
          textAlign: "center",
          padding: "12px 32px",
          backgroundColor: "rgba(139, 92, 246, 0.1)",
          border: "1px solid rgba(139, 92, 246, 0.2)",
          borderRadius: 8,
        }}
      >
        First adversarial validator marketplace on ERC-8004
      </div>

      <div
        style={{
          opacity: opacity(7),
          color: "rgba(255,255,255,0.4)",
          fontSize: 16,
          fontFamily: "'SF Mono', monospace",
        }}
      >
        x402 protocol · Base settlement · MCP at /mcp · $0.01 USDC/validation
      </div>
    </AbsoluteFill>
  );
};
