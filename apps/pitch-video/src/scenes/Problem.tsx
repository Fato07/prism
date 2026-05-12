import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate } from "remotion";

/**
 * Scene 2: The Problem (10-25s)
 * Lucky bad reasoning → high score. Brilliant reasoning, unresolved → no credit.
 * ERC-8004 has a ValidationRegistry for adversarial validation — but nobody filled the slot.
 */
export const Problem: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const opacity = (start: number) =>
    interpolate(frame, [fps * start, fps * (start + 0.8)], [0, 1], {
      extrapolateRight: "clamp",
      extrapolateLeft: "clamp",
    });

  const yShift = (start: number) =>
    interpolate(frame, [fps * start, fps * (start + 0.8)], [20, 0], {
      extrapolateRight: "clamp",
      extrapolateLeft: "clamp",
    });

  return (
    <AbsoluteFill
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "flex-start",
        justifyContent: "center",
        padding: "80px 120px",
        gap: 24,
      }}
    >
      {/* Bad reasoning scenario */}
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div
          style={{
            opacity: opacity(0),
            transform: `translateY(${yShift(0)}px)`,
            color: "#fbbf24",
            fontSize: 36,
            fontFamily: "'Inter', sans-serif",
            fontWeight: 600,
          }}
        >
          ❌ Agent gets lucky with bad reasoning → high reputation score
        </div>
        <div
          style={{
            opacity: opacity(1),
            transform: `translateY(${yShift(1)}px)`,
            color: "#fbbf24",
            fontSize: 36,
            fontFamily: "'Inter', sans-serif",
            fontWeight: 600,
          }}
        >
          ❌ Brilliant reasoning, unresolved position → no credit
        </div>
      </div>

      {/* Divider */}
      <div
        style={{
          opacity: opacity(3),
          width: 600,
          height: 2,
          backgroundColor: "rgba(255,255,255,0.15)",
          marginTop: 12,
          marginBottom: 12,
        }}
      />

      {/* ERC-8004 opening */}
      <div
        style={{
          opacity: opacity(4),
          transform: `translateY(${yShift(4)}px)`,
          color: "white",
          fontSize: 32,
          fontFamily: "'Inter', sans-serif",
          fontWeight: 400,
          lineHeight: 1.5,
          maxWidth: 1500,
        }}
      >
        ERC-8004's ValidationRegistry has a slot for adversarial validation —
        where the spec <span style={{ color: "#8b5cf6", fontWeight: 600 }}>forbids self-validation</span>.
      </div>

      <div
        style={{
          opacity: opacity(6),
          color: "#8b5cf6",
          fontSize: 38,
          fontFamily: "'Inter', sans-serif",
          fontWeight: 700,
        }}
      >
        Nobody has filled the slot with adversarial AI. Until now.
      </div>
    </AbsoluteFill>
  );
};
