import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate } from "remotion";

interface AnimatedTextProps {
  text: string;
  style?: React.CSSProperties;
  delay?: number;
  direction?: "left" | "right" | "up" | "fade";
}

/**
 * Text component with entrance animation.
 * Fades in and slides from the specified direction.
 */
export const AnimatedText: React.FC<AnimatedTextProps> = ({
  text,
  style = {},
  delay = 0,
  direction = "fade",
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const progress = interpolate(
    frame - delay,
    [0, fps * 0.5],
    [0, 1],
    { extrapolateRight: "clamp", extrapolateLeft: "clamp" }
  );

  const opacity = progress;
  const translateY = direction === "up" ? interpolate(progress, [0, 1], [30, 0]) : 0;
  const translateX =
    direction === "left" ? interpolate(progress, [0, 1], [-40, 0]) :
    direction === "right" ? interpolate(progress, [0, 1], [40, 0]) : 0;

  return (
    <div
      style={{
        opacity,
        transform: `translate(${translateX}px, ${translateY}px)`,
        color: "white",
        fontFamily: "'Inter', 'SF Pro Display', -apple-system, sans-serif",
        ...style,
      }}
    >
      {text}
    </div>
  );
};
