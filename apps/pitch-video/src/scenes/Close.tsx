import React from "react";
import {
  AbsoluteFill,
  Sequence,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  Video,
  staticFile,
} from "remotion";
import { PrismLogo } from "../components/PrismLogo";
import type { PrismPitchProps } from "../PrismPitch";

/** Traction metrics shape from the composition schema. */
type TractionNumbers = PrismPitchProps["tractionNumbers"];

interface CloseProps {
  /** Path or URL to operator video. Empty string = slide-only (no face/voice). */
  operatorVideoSrc: string;
  /** Traction metrics from Neon. */
  tractionNumbers: TractionNumbers;
}

/**
 * Scene 8: Close (85-90s)
 * "Prism. See through the reasoning. The first adversarial AI validator on ERC-8004."
 *
 * When operatorVideoSrc is provided, the operator clip plays in the
 * upper portion. When empty (slide-only build), the static slide
 * with logo, tagline, and traction stats is shown.
 */
export const Close: React.FC<CloseProps> = ({
  operatorVideoSrc,
  tractionNumbers,
}) => {
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

  const statsOpacity = interpolate(frame, [fps * 2.0, fps * 2.8], [0, 1], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  const urlOpacity = interpolate(frame, [fps * 3.0, fps * 3.8], [0, 1], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  const hasOperatorVideo = operatorVideoSrc !== "";

  return (
    <AbsoluteFill
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: hasOperatorVideo ? 12 : 20,
      }}
    >
      {/* Operator video clip — only rendered when src is provided */}
      {hasOperatorVideo && (
        <Sequence from={0} durationInFrames={5 * fps}>
          <div
            style={{
              position: "absolute",
              top: 40,
              right: 60,
              width: 400,
              height: 225,
              borderRadius: 12,
              overflow: "hidden",
              border: "1px solid rgba(255,255,255,0.1)",
              opacity: interpolate(frame, [0, fps * 0.3], [0, 1], {
                extrapolateRight: "clamp",
                extrapolateLeft: "clamp",
              }),
            }}
          >
            <Video
              src={operatorVideoSrc.startsWith("http") ? operatorVideoSrc : staticFile(operatorVideoSrc)}
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
              volume={1}
            />
          </div>
        </Sequence>
      )}

      <div style={{ opacity: logoOpacity, transform: `scale(${logoScale})` }}>
        <PrismLogo size={90} />
      </div>
      <div
        style={{
          opacity: taglineOpacity,
          color: "white",
          fontSize: hasOperatorVideo ? 44 : 56,
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
          fontSize: hasOperatorVideo ? 24 : 30,
          fontFamily: "'Inter', sans-serif",
          fontWeight: 600,
          textAlign: "center",
        }}
      >
        The first adversarial AI validator on ERC-8004
      </div>

      {/* Traction stats — rendered from injected metrics */}
      <div
        style={{
          opacity: statsOpacity,
          display: "flex",
          gap: 20,
          marginTop: 8,
        }}
      >
        <StatBadge
          label="Verdicts"
          value={tractionNumbers.verdictsIssued.toString()}
        />
        <StatBadge
          label="On-chain"
          value={tractionNumbers.onChainAnchors.toString()}
        />
        <StatBadge
          label="Wallets"
          value={tractionNumbers.uniqueWallets.toString()}
        />
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
          marginTop: 4,
        }}
      >
        prism-dashboard-production-e6e3.up.railway.app
      </div>
    </AbsoluteFill>
  );
};

/** Small badge showing a metric label + value. */
const StatBadge: React.FC<{ label: string; value: string }> = ({
  label,
  value,
}) => (
  <div
    style={{
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      padding: "8px 20px",
      backgroundColor: "rgba(139, 92, 246, 0.08)",
      border: "1px solid rgba(139, 92, 246, 0.2)",
      borderRadius: 8,
    }}
  >
    <div
      style={{
        color: "white",
        fontSize: 28,
        fontWeight: 700,
        fontFamily: "'SF Mono', monospace",
      }}
    >
      {value}
    </div>
    <div style={{ color: "rgba(255,255,255,0.5)", fontSize: 14, marginTop: 2 }}>
      {label}
    </div>
  </div>
);
