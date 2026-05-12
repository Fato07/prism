import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate } from "remotion";
import { PrismLogo } from "../components/PrismLogo";

/**
 * Scene 1: Hook (0-10s)
 * "Autonomous AI agents are about to trade billions.
 *  Today, nobody can audit their reasoning. I built Prism."
 */
export const Hook: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const text1Opacity = interpolate(frame, [0, fps * 1.5], [0, 1], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  const text2Opacity = interpolate(frame, [fps * 2, fps * 3.5], [0, 1], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  const taglineOpacity = interpolate(frame, [fps * 5, fps * 7], [0, 1], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  const logoScale = interpolate(frame, [fps * 5, fps * 7], [0.5, 1], {
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
        gap: 30,
        padding: 80,
      }}
    >
      <div
        style={{
          opacity: text1Opacity,
          color: "white",
          fontSize: 42,
          fontFamily: "'Inter', sans-serif",
          fontWeight: 600,
          textAlign: "center",
          lineHeight: 1.4,
          maxWidth: 1400,
        }}
      >
        Autonomous AI agents are about to trade billions of dollars.
      </div>
      <div
        style={{
          opacity: text2Opacity,
          color: "#ef4444",
          fontSize: 38,
          fontFamily: "'Inter', sans-serif",
          fontWeight: 500,
          textAlign: "center",
          lineHeight: 1.4,
          maxWidth: 1400,
        }}
      >
        Today, nobody can audit their reasoning — only whether their P&L is positive.
      </div>
      <div style={{ opacity: taglineOpacity, display: "flex", flexDirection: "column", alignItems: "center", gap: 16 }}>
        <div style={{ transform: `scale(${logoScale})` }}>
          <PrismLogo size={60} />
        </div>
        <div
          style={{
            color: "#8b5cf6",
            fontSize: 52,
            fontFamily: "'Inter', sans-serif",
            fontWeight: 700,
            textAlign: "center",
            letterSpacing: "-0.02em",
          }}
        >
          I built Prism.
        </div>
      </div>
    </AbsoluteFill>
  );
};
