import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate } from "remotion";

/**
 * Scene 4: On-Chain Proof (45-60s)
 * Every dialogue lands on Arc. Registration, validation, verdict — all on-chain.
 * Gas Station sponsored. Sub-$0.01 in gas.
 */
export const OnChainProof: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const opacity = (start: number) =>
    interpolate(frame, [fps * start, fps * (start + 0.5)], [0, 1], {
      extrapolateRight: "clamp",
      extrapolateLeft: "clamp",
    });

  const steps = [
    { label: "1. Register", detail: "IdentityRegistry mints agent NFT", color: "#3b82f6" },
    { label: "2. Request Validation", detail: "ValidationRegistry.validationRequest", color: "#8b5cf6" },
    { label: "3. Adversarial Review", detail: "Sentinel challenges pinned to IPFS", color: "#ef4444" },
    { label: "4. Submit Verdict", detail: "ValidationRegistry.validationResponse", color: "#10b981" },
  ];

  return (
    <AbsoluteFill
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "flex-start",
        justifyContent: "center",
        padding: "60px 100px",
        gap: 20,
      }}
    >
      <div
        style={{
          opacity: opacity(0),
          color: "white",
          fontSize: 38,
          fontFamily: "'Inter', sans-serif",
          fontWeight: 700,
        }}
      >
        Every dialogue lands on-chain.
      </div>

      <div style={{ color: "rgba(255,255,255,0.5)", fontSize: 22, marginBottom: 12, opacity: opacity(0.5) }}>
        Arc Testnet · Chain 5042002 · USDC native gas
      </div>

      {/* Pipeline steps */}
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {steps.map((step, i) => (
          <div
            key={i}
            style={{
              opacity: opacity(1 + i * 1.5),
              display: "flex",
              alignItems: "center",
              gap: 16,
              backgroundColor: `${step.color}10`,
              border: `1px solid ${step.color}30`,
              borderRadius: 10,
              padding: "16px 24px",
            }}
          >
            <div
              style={{
                color: step.color,
                fontSize: 22,
                fontWeight: 700,
                fontFamily: "'SF Mono', monospace",
                minWidth: 220,
              }}
            >
              {step.label}
            </div>
            <div style={{ color: "rgba(255,255,255,0.7)", fontSize: 20 }}>{step.detail}</div>
          </div>
        ))}
      </div>

      {/* Gas Station callout */}
      <div
        style={{
          opacity: opacity(9),
          display: "flex",
          alignItems: "center",
          gap: 16,
          marginTop: 20,
          padding: "16px 24px",
          backgroundColor: "rgba(16, 185, 129, 0.1)",
          border: "1px solid rgba(16, 185, 129, 0.3)",
          borderRadius: 10,
        }}
      >
        <div style={{ color: "#10b981", fontSize: 36, fontWeight: 700, fontFamily: "'SF Mono', monospace" }}>
          $0.00
        </div>
        <div style={{ color: "white", fontSize: 22 }}>
          Gas per transaction — Circle Gas Station sponsored
        </div>
      </div>

      {/* Agent IDs */}
      <div
        style={{
          opacity: opacity(10),
          color: "rgba(255,255,255,0.4)",
          fontSize: 16,
          fontFamily: "'SF Mono', monospace",
          marginTop: 8,
        }}
      >
        Trader agentId: 4062 · Sentinel agentId: 4070 · Gas: sponsored · IPFS: pinned
      </div>
    </AbsoluteFill>
  );
};
