import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate } from "remotion";

/**
 * Scene 5: Polymarket Builder Attribution (60-68s)
 * Trade on Polymarket V2 with builder code derived from on-chain identity.
 * Deterministic HMAC mapping — identity portability without a bridge.
 */
export const PolymarketAttribution: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const opacity = (start: number) =>
    interpolate(frame, [fps * start, fps * (start + 0.4)], [0, 1], {
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
        gap: 28,
      }}
    >
      <div
        style={{
          opacity: opacity(0),
          color: "white",
          fontSize: 36,
          fontFamily: "'Inter', sans-serif",
          fontWeight: 700,
          textAlign: "center",
        }}
      >
        Identity → Attribution
      </div>

      <div
        style={{
          opacity: opacity(1),
          color: "rgba(255,255,255,0.7)",
          fontSize: 24,
          textAlign: "center",
          maxWidth: 1200,
          lineHeight: 1.5,
        }}
      >
        Trade executes on Polymarket V2 with a builder code
        <span style={{ color: "#8b5cf6", fontWeight: 600 }}> derived from on-chain agent identity</span>.
      </div>

      {/* Formula */}
      <div
        style={{
          opacity: opacity(2.5),
          backgroundColor: "rgba(139, 92, 246, 0.08)",
          border: "1px solid rgba(139, 92, 246, 0.2)",
          borderRadius: 12,
          padding: "20px 40px",
          fontFamily: "'SF Mono', 'Fira Code', monospace",
          fontSize: 28,
          color: "#c4b5fd",
        }}
      >
        builderCode = HMAC(agentId, salt)
      </div>

      <div
        style={{
          opacity: opacity(4),
          color: "rgba(255,255,255,0.5)",
          fontSize: 20,
          textAlign: "center",
          lineHeight: 1.5,
        }}
      >
        Deterministic mapping — no custodial bridging.
        <br />
        Verify on IPFS: agent card publishes the salt.
      </div>
    </AbsoluteFill>
  );
};
