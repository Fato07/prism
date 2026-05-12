import { AbsoluteFill, useCurrentFrame } from "remotion";

/**
 * Dark animated background with subtle gradient shift.
 * Provides visual consistency across all pitch scenes.
 */
export const Background: React.FC = () => {
  const frame = useCurrentFrame();
  const hueShift = Math.sin(frame / 100) * 10;

  return (
    <AbsoluteFill
      style={{
        background: `
          radial-gradient(
            ellipse at 50% 50%,
            hsl(${240 + hueShift}, 30%, 8%) 0%,
            hsl(${250 + hueShift}, 20%, 4%) 100%
          )
        `,
        opacity: 0.9,
      }}
    />
  );
};
