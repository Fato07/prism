import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate } from "remotion";

/**
 * Prism logo component — a prism icon that splits white light into spectrum.
 */
export const PrismLogo: React.FC<{ size?: number }> = ({ size = 80 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const scale = interpolate(frame, [0, fps * 0.5], [0.5, 1], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  return (
    <div
      style={{
        width: size,
        height: size,
        position: "relative",
        transform: `scale(${scale})`,
      }}
    >
      {/* Prism triangle */}
      <svg viewBox="0 0 80 80" width={size} height={size}>
        <polygon
          points="40,10 70,65 10,65"
          fill="none"
          stroke="white"
          strokeWidth="2"
          opacity="0.8"
        />
        {/* Light refraction lines */}
        <line x1="0" y1="40" x2="25" y2="40" stroke="white" strokeWidth="1" opacity="0.4" />
        <line x1="55" y1="35" x2="80" y2="20" stroke="#8b5cf6" strokeWidth="1.5" opacity="0.6" />
        <line x1="55" y1="40" x2="80" y2="40" stroke="#3b82f6" strokeWidth="1.5" opacity="0.6" />
        <line x1="55" y1="45" x2="80" y2="55" stroke="#06b6d4" strokeWidth="1.5" opacity="0.6" />
        <line x1="55" y1="50" x2="80" y2="70" stroke="#10b981" strokeWidth="1.5" opacity="0.6" />
      </svg>
    </div>
  );
};
