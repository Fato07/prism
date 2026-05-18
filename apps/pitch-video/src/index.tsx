import React from "react";
import { Composition, registerRoot } from "remotion";
import { z } from "zod";
import { PrismPitch } from "./PrismPitch";
import { PrismShowcase } from "./PrismShowcase";
import { SHOWCASE_STATS } from "./brand";

/**
 * Zod schema for the PrismPitch composition props.
 * This enables visual editing in Remotion Studio and type-safe rendering.
 *
 * - operatorVideoSrc: Path or URL to a video clip of the operator
 *   speaking. Replace with your own recording before rendering the
 *   face+voice version. Default is "" which produces the slide-only
 *   build with no face/voice.
 *
 * - tractionNumbers: Live traction metrics pulled from Neon at render
 *   time. Swap these before rendering for the latest counts.
 */
export const prismPitchSchema = z.object({
  operatorVideoSrc: z.string().default(""),
  tractionNumbers: z.object({
    verdictsIssued: z.number().default(27),
    uniqueWallets: z.number().default(1),
    tracesValidated: z.number().default(27),
    onChainAnchors: z.number().default(54),
    builderFeesUsdc: z.number().default(0.0),
    externalX402Calls: z.number().default(0),
  }).default({
    verdictsIssued: 27,
    uniqueWallets: 1,
    tracesValidated: 27,
    onChainAnchors: 54,
    builderFeesUsdc: 0.0,
    externalX402Calls: 0,
  }),
});

export const prismShowcaseSchema = z.object({
  voiceoverSrc: z.string().default(""),
  musicSrc: z.string().default(""),
  broll: z.object({
    refractionSrc: z.string().default(""),
    traceAssemblySrc: z.string().default(""),
    urlVerificationSrc: z.string().default(""),
    capitalGateSrc: z.string().default(""),
    arcAnchorSrc: z.string().default(""),
  }).default({
    refractionSrc: "",
    traceAssemblySrc: "",
    urlVerificationSrc: "",
    capitalGateSrc: "",
    arcAnchorSrc: "",
  }),
  stats: z.object({
    verdictsIssued: z.number().default(SHOWCASE_STATS.verdictsIssued),
    tracesValidated: z.number().default(SHOWCASE_STATS.tracesValidated),
    onChainAnchors: z.number().default(SHOWCASE_STATS.onChainAnchors),
    builderAttributedTrades: z.number().default(SHOWCASE_STATS.builderAttributedTrades),
    builderFeesUsdc: z.string().default(SHOWCASE_STATS.builderFeesUsdc),
    externalX402Calls: z.number().default(SHOWCASE_STATS.externalX402Calls),
  }).default({
    verdictsIssued: SHOWCASE_STATS.verdictsIssued,
    tracesValidated: SHOWCASE_STATS.tracesValidated,
    onChainAnchors: SHOWCASE_STATS.onChainAnchors,
    builderAttributedTrades: SHOWCASE_STATS.builderAttributedTrades,
    builderFeesUsdc: SHOWCASE_STATS.builderFeesUsdc,
    externalX402Calls: SHOWCASE_STATS.externalX402Calls,
  }),
});

const defaultProps = prismPitchSchema.parse({});
const defaultShowcaseProps = prismShowcaseSchema.parse({});
const defaultShowcaseBrollProps = prismShowcaseSchema.parse({
  musicSrc: "audio/prism-showcase-bed.wav",
  broll: {
    refractionSrc: "broll/refraction.mp4",
    traceAssemblySrc: "broll/trace-assembly.mp4",
    urlVerificationSrc: "broll/url-verification.mp4",
    capitalGateSrc: "broll/capital-gate.mp4",
    arcAnchorSrc: "broll/arc-anchor.mp4",
  },
});

const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="PrismPitch"
        component={PrismPitch}
        durationInFrames={2700}
        fps={30}
        width={1920}
        height={1080}
        schema={prismPitchSchema}
        defaultProps={defaultProps}
      />
      <Composition
        id="PrismShowcase"
        component={PrismShowcase}
        durationInFrames={2100}
        fps={30}
        width={1920}
        height={1080}
        schema={prismShowcaseSchema}
        defaultProps={defaultShowcaseProps}
      />
      <Composition
        id="PrismShowcaseBroll"
        component={PrismShowcase}
        durationInFrames={2100}
        fps={30}
        width={1920}
        height={1080}
        schema={prismShowcaseSchema}
        defaultProps={defaultShowcaseBrollProps}
      />
    </>
  );
};

registerRoot(RemotionRoot);
