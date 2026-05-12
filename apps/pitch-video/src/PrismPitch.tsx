import { AbsoluteFill, Sequence, useCurrentFrame, useVideoConfig } from "remotion";
import { Hook } from "./scenes/Hook";
import { Problem } from "./scenes/Problem";
import { TwoAgentSolution } from "./scenes/TwoAgentSolution";
import { OnChainProof } from "./scenes/OnChainProof";
import { PolymarketAttribution } from "./scenes/PolymarketAttribution";
import { PlatformPlay } from "./scenes/PlatformPlay";
import { CircleSurface } from "./scenes/CircleSurface";
import { Close } from "./scenes/Close";
import { Background } from "./components/Background";

/**
 * Main composition for the Prism 90-second pitch video.
 * Each scene maps to a section of the pitch script in docs/pitch-script.md.
 */
export const PrismPitch: React.FC = () => {
  const { fps } = useVideoConfig();
  const frame = useCurrentFrame();
  const seconds = frame / fps;

  // Scene timings (matching pitch-script.md sections)
  const scenes = [
    { start: 0, duration: 10, label: "hook" },           // 0-10s
    { start: 10, duration: 15, label: "problem" },        // 10-25s
    { start: 25, duration: 20, label: "two-agent" },      // 25-45s
    { start: 45, duration: 15, label: "on-chain" },       // 45-60s
    { start: 60, duration: 8, label: "polymarket" },     // 60-68s
    { start: 68, duration: 10, label: "platform" },       // 68-78s
    { start: 78, duration: 7, label: "circle" },         // 78-85s
    { start: 85, duration: 5, label: "close" },          // 85-90s
  ];

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
        <Close />
      </Sequence>
    </AbsoluteFill>
  );
};
