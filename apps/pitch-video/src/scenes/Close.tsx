import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate } from "remotion";
import { PrismLogo } from "../components/PrismLogo";

/**
 * Scene 8: Close (85-90s)
 * "Prism. See through the reasoning. The first adversarial AI validator on ERC-8004."
 */
export const Close: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const logoOpacity = interpolate(frame, [0, fps * 0.5], [0, 1], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  const logoScale = interpolate(frame, [0, fps * 0.8], [0.7, 1], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  const taglineOpacity = interpolate(frame, [fps * 0.8, fps * 1.5], [0, 1], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  const subtitleOpacity = interpolate(frame, [fps * 1.5, fps * 2.2], [0, 1], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  const urlOpacity = interpolate(frame, [fps * 2.5, fps * 3.2], [0, 1], {
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
        gap: 20,
      }}
    >
      <div style={{ opacity: logoOpacity, transform: `scale(${logoScale})` }}>
        <PrismLogo size={90} />
      </div>
      <div
        style={{
          opacity: taglineOpacity,
          color: "white",
          fontSize: 56,
          fontFamily: "'Inter', sans-serif",
          fontWeight: 800,
          textAlign: "center",
          letterSpacing: "-0.03em",
        }}
      >
        See through the reasoning.
      </div>
      <div
        style={{
          opacity: subtitleOpacity,
          color: "#8b5cf6",
          fontSize: 30,
          fontFamily: "'Inter', sans-serif",
          fontWeight: 600,
          textAlign: "center",
        }}
      >
        The first adversarial AI validator on ERC-8004
      </div>
      <div
        style={{
          opacity: subtitleOpacity,
          color: "rgba(255,255,255,0.4)",
          fontSize: 22,
          textAlign: "center",
        }}
      >
        Built on Arc · Powered by Circle
      </div>
      <div
        style={{
          opacity: urlOpacity,
          color: "rgba(255,255,255,0.3)",
          fontSize: 18,
          fontFamily: "'SF Mono', monospace",
          marginTop: 8,
        }}
      >
        prism-dashboard-production-e6e3.up.railway.app
      </div>
    </AbsoluteFill>
  );
};
