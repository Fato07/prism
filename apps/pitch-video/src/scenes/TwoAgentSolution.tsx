import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate } from "remotion";

/**
 * Scene 3: Two-Agent Solution (25-45s)
 * Trader (Claude) → Trading-R1 trace → Sentinel (GPT-4o-mini) adversarially challenges.
 * Cross-family pressure catches reasoning failures.
 */
export const TwoAgentSolution: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const opacity = (start: number) =>
    interpolate(frame, [fps * start, fps * (start + 0.6)], [0, 1], {
      extrapolateRight: "clamp",
      extrapolateLeft: "clamp",
    });

  const slideX = (start: number, from: number) =>
    interpolate(frame, [fps * start, fps * (start + 0.8)], [from, 0], {
      extrapolateRight: "clamp",
      extrapolateLeft: "clamp",
    });

  const arrowProgress = interpolate(frame, [fps * 4, fps * 7], [0, 1], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: 60,
        gap: 40,
      }}
    >
      {/* Title */}
      <div
        style={{
          opacity: opacity(0),
          color: "white",
          fontSize: 40,
          fontFamily: "'Inter', sans-serif",
          fontWeight: 700,
          textAlign: "center",
        }}
      >
        Two agents. Different LLM families.
      </div>

      {/* Agent cards side by side */}
      <div style={{ display: "flex", gap: 60, alignItems: "stretch" }}>
        {/* Trader card */}
        <div
          style={{
            opacity: opacity(1),
            transform: `translateX(${slideX(1, -60)}px)`,
            backgroundColor: "rgba(59, 130, 246, 0.1)",
            border: "1px solid rgba(59, 130, 246, 0.3)",
            borderRadius: 16,
            padding: "32px 40px",
            width: 400,
            display: "flex",
            flexDirection: "column",
            gap: 12,
          }}
        >
          <div style={{ color: "#3b82f6", fontSize: 28, fontWeight: 700 }}>Trader</div>
          <div style={{ color: "rgba(255,255,255,0.7)", fontSize: 20 }}>Claude family · Mirascope</div>
          <div style={{ color: "white", fontSize: 22, fontWeight: 500, marginTop: 8 }}>
            Trading-R1 Reasoning Trace
          </div>
          <div style={{ color: "rgba(255,255,255,0.5)", fontSize: 17, lineHeight: 1.5 }}>
            Thesis composition → Evidence collection → Volatility-adjusted decision
          </div>
        </div>

        {/* Arrow */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: 120,
          }}
        >
          <svg viewBox="0 0 120 40" width={120} height={40}>
            <line
              x1={0}
              y1={20}
              x2={120 * arrowProgress}
              y2={20}
              stroke="#8b5cf6"
              strokeWidth={3}
            />
            {arrowProgress > 0.8 && (
              <polygon
                points="110,12 120,20 110,28"
                fill="#8b5cf6"
                opacity={interpolate(arrowProgress, [0.8, 1], [0, 1])}
              />
            )}
          </svg>
        </div>

        {/* Sentinel card */}
        <div
          style={{
            opacity: opacity(2),
            transform: `translateX(${slideX(2, 60)}px)`,
            backgroundColor: "rgba(239, 68, 68, 0.1)",
            border: "1px solid rgba(239, 68, 68, 0.3)",
            borderRadius: 16,
            padding: "32px 40px",
            width: 400,
            display: "flex",
            flexDirection: "column",
            gap: 12,
          }}
        >
          <div style={{ color: "#ef4444", fontSize: 28, fontWeight: 700 }}>Sentinel</div>
          <div style={{ color: "rgba(255,255,255,0.7)", fontSize: 20 }}>GPT-4o-mini · DSPy</div>
          <div style={{ color: "white", fontSize: 22, fontWeight: 500, marginTop: 8 }}>
            Adversarial Challenges
          </div>
          <div style={{ color: "rgba(255,255,255,0.5)", fontSize: 17, lineHeight: 1.5 }}>
            Evidence claims → Probability calibration → Decision logic
          </div>
        </div>
      </div>

      {/* Cross-family note */}
      <div
        style={{
          opacity: opacity(10),
          color: "#8b5cf6",
          fontSize: 26,
          fontFamily: "'Inter', sans-serif",
          fontWeight: 600,
          textAlign: "center",
          marginTop: 10,
          padding: "12px 24px",
          backgroundColor: "rgba(139, 92, 246, 0.1)",
          borderRadius: 8,
          border: "1px solid rgba(139, 92, 246, 0.2)",
        }}
      >
        Claude ≠ GPT — cross-family pressure catches family-correlated failures
      </div>
    </AbsoluteFill>
  );
};
