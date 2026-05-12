import React from "react";
import { Composition, registerRoot } from "remotion";
import { PrismPitch } from "./PrismPitch";

const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="PrismPitch"
      component={PrismPitch}
      durationInFrames={2700}
      fps={30}
      width={1920}
      height={1080}
    />
  );
};

registerRoot(RemotionRoot);
