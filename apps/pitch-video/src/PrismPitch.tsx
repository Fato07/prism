import React from "react";
import { AbsoluteFill, Sequence } from "remotion";
import { z } from "zod";
import { Hook } from "./scenes/Hook";
import { Problem } from "./scenes/Problem";
import { TwoAgentSolution } from "./scenes/TwoAgentSolution";
import { OnChainProof } from "./scenes/OnChainProof";
import { PolymarketAttribution } from "./scenes/PolymarketAttribution";
import { PlatformPlay } from "./scenes/PlatformPlay";
import { CircleSurface } from "./scenes/CircleSurface";
import { Close } from "./scenes/Close";
import { Background } from "./components/Background";
import { prismPitchSchema } from "./index";

/** Props type derived from the zod schema. */
export type PrismPitchProps = z.infer<typeof prismPitchSchema>;

/** Live traction metrics injected at render time. */
export type TractionNumbers = PrismPitchProps["tractionNumbers"];

/**
 * Main composition for the Prism 90-second pitch video.
 * Each scene maps to a section of the pitch script.
 *
 * Scene timings (90 seconds @ 30 fps = 2700 frames):
 *  0-10s   Hook               — "Autonomous AI agents are about to trade billions."
 * 10-25s   Problem             — Lucky bad reasoning, brilliant reasoning ignored.
 * 25-45s   Two-Agent Solution  — Trader (Claude) vs Sentinel (GPT).
 * 45-60s   On-Chain Proof      — Every dialogue anchored on Arc via ERC-8004.
 * 60-68s   Polymarket          — Builder-code attribution from on-chain identity.
 * 68-78s   Platform Play       — Sentinel-as-a-Service, $0.01/validation.
 * 78-85s   Circle Surface      — Five Circle products powering Prism.
 * 85-90s   Close               — "See through the reasoning."
 */
export const PrismPitch: React.FC<PrismPitchProps> = ({
  operatorVideoSrc,
  tractionNumbers,
}) => {
  const fps = 30;

  return (
    <AbsoluteFill style={{ backgroundColor: "#0a0a0a" }}>
      <Background />
      <Sequence from={0} durationInFrames={10 * fps}>
        <Hook />
      </Sequence>
      <Sequence from={10 * fps} durationInFrames={15 * fps}>
        <Problem />
      </Sequence>
      <Sequence from={25 * fps} durationInFrames={20 * fps}>
        <TwoAgentSolution />
      </Sequence>
      <Sequence from={45 * fps} durationInFrames={15 * fps}>
        <OnChainProof />
      </Sequence>
      <Sequence from={60 * fps} durationInFrames={8 * fps}>
        <PolymarketAttribution />
      </Sequence>
      <Sequence from={68 * fps} durationInFrames={10 * fps}>
        <PlatformPlay />
      </Sequence>
      <Sequence from={78 * fps} durationInFrames={7 * fps}>
        <CircleSurface />
      </Sequence>
      <Sequence from={85 * fps} durationInFrames={5 * fps}>
        <Close
          operatorVideoSrc={operatorVideoSrc}
          tractionNumbers={tractionNumbers}
        />
      </Sequence>
    </AbsoluteFill>
  );
};
