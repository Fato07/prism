import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate } from "remotion";

/**
 * Scene 7: Circle Product Surface (78-85s)
 * Five Circle products powering Prism: Wallets, Contract Execution, USDC gas, Gas Station, Nanopayments.
 */
export const CircleSurface: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const opacity = (start: number) =>
    interpolate(frame, [fps * start, fps * (start + 0.3)], [0, 1], {
      extrapolateRight: "clamp",
      extrapolateLeft: "clamp",
    });

  const products = [
    { name: "Programmable Wallets", detail: "SCA wallets for every ERC-8004 call", icon: "🔐" },
    { name: "Contract Execution", detail: "register · validationRequest · validationResponse", icon: "📜" },
    { name: "Native USDC", detail: "Arc gas token — costs denominated in USDC", icon: "💲" },
    { name: "Gas Station", detail: "Zero-cost operations — gasless for agents", icon: "⛽" },
    { name: "Nanopayments", detail: "$0.01/validation via x402 + Circle Gateway", icon: "💳" },
  ];

  return (
    <AbsoluteFill
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: 50,
        gap: 16,
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
          marginBottom: 12,
        }}
      >
        Powered by Circle
      </div>

      {products.map((product, i) => (
        <div
          key={i}
          style={{
            opacity: opacity(0.5 + i * 0.7),
            display: "flex",
            alignItems: "center",
            gap: 16,
            width: 900,
            padding: "12px 24px",
            backgroundColor: "rgba(16, 185, 129, 0.06)",
            border: "1px solid rgba(16, 185, 129, 0.15)",
            borderRadius: 8,
          }}
        >
          <div style={{ fontSize: 24, width: 40, textAlign: "center" }}>{product.icon}</div>
          <div style={{ color: "#10b981", fontSize: 22, fontWeight: 700, minWidth: 260 }}>{product.name}</div>
          <div style={{ color: "rgba(255,255,255,0.6)", fontSize: 18 }}>{product.detail}</div>
        </div>
      ))}
    </AbsoluteFill>
  );
};
