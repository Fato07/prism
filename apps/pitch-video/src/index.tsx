import React from "react";
import { Composition, registerRoot } from "remotion";
import { z } from "zod";
import { PrismPitch } from "./PrismPitch";

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

const defaultProps = prismPitchSchema.parse({});

const RemotionRoot: React.FC = () => {
  return (
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
  );
};

registerRoot(RemotionRoot);
