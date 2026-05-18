import React from "react";
import { AbsoluteFill, Audio as RemotionAudio, Sequence, staticFile } from "remotion";
import { z } from "zod";
import { COLORS, FONT, SHOWCASE_PROOF, SHOWCASE_STATS } from "./brand";
import {
  AgentBeam,
  CapitalGateGraphic,
  EvidenceRail,
  FadeIn,
  OptionalBroll,
  PrismMark,
  ProofCard,
  RefractionBackdrop,
  SceneShell,
  StatPill,
} from "./components/ShowcasePrimitives";
import { prismShowcaseSchema } from "./index";

export type PrismShowcaseProps = z.infer<typeof prismShowcaseSchema>;

const fps = 30;
const AudioTrack = RemotionAudio as unknown as React.FC<{
  src: string;
  volume?: number;
  loop?: boolean;
}>;

function audioSource(src: string) {
  return src.startsWith("http") ? src : staticFile(src);
}

export const PrismShowcase: React.FC<PrismShowcaseProps> = ({
  voiceoverSrc,
  musicSrc,
  broll,
  stats,
}) => {
  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.bg }}>
      <RefractionBackdrop />
      {musicSrc && <AudioTrack src={audioSource(musicSrc)} volume={0.12} loop />}
      {voiceoverSrc && <AudioTrack src={audioSource(voiceoverSrc)} volume={1} />}

      <Sequence from={0} durationInFrames={6 * fps}>
        <HookScene brollSrc={broll.refractionSrc} />
      </Sequence>
      <Sequence from={6 * fps} durationInFrames={9 * fps}>
        <ProblemScene />
      </Sequence>
      <Sequence from={15 * fps} durationInFrames={13 * fps}>
        <MechanismScene brollSrc={broll.traceAssemblySrc} />
      </Sequence>
      <Sequence from={28 * fps} durationInFrames={14 * fps}>
        <EvidenceScene brollSrc={broll.urlVerificationSrc} />
      </Sequence>
      <Sequence from={42 * fps} durationInFrames={10 * fps}>
        <CapitalGateScene brollSrc={broll.capitalGateSrc} />
      </Sequence>
      <Sequence from={52 * fps} durationInFrames={10 * fps}>
        <SettlementScene brollSrc={broll.arcAnchorSrc} />
      </Sequence>
      <Sequence from={62 * fps} durationInFrames={8 * fps}>
        <CloseScene stats={stats} />
      </Sequence>
    </AbsoluteFill>
  );
};

function HookScene({ brollSrc }: { brollSrc?: string }) {
  return (
    <SceneShell eyebrow="brand film" title="See through the reasoning.">
      <OptionalBroll src={brollSrc} />
      <div style={{ marginTop: 42 }}>
        <PrismMark size={210} />
      </div>
      <FadeIn delay={46}>
        <p style={subtitleStyle}>
          A trust runtime for autonomous agents before capital moves.
        </p>
      </FadeIn>
    </SceneShell>
  );
}

function ProblemScene() {
  return (
    <SceneShell eyebrow="problem" title="Confidence is not a reasoning audit." align="left">
      <div style={{ display: "flex", gap: 22, marginTop: 50 }}>
        <RiskCard title="Lucky trade" body="Bad reasoning can still make money." tone={COLORS.warn} delay={14} />
        <RiskCard title="Stale evidence" body="Old citations can masquerade as current conviction." tone={COLORS.blocked} delay={26} />
        <RiskCard title="No provenance" body="A claim without a source cannot move capital." tone={COLORS.sentinel} delay={38} />
      </div>
      <FadeIn delay={66}>
        <div style={{ ...captionStyle, marginTop: 46 }}>
          Prism turns uncertainty into an explicit gate instead of hidden risk.
        </div>
      </FadeIn>
    </SceneShell>
  );
}

function MechanismScene({ brollSrc }: { brollSrc?: string }) {
  return (
    <SceneShell eyebrow="mechanism" title="The trader proposes. The sentinel attacks.">
      <OptionalBroll src={brollSrc} />
      <div style={{ display: "flex", alignItems: "center", gap: 54, marginTop: 58 }}>
        <AgentBeam label="Claude / Mirascope" detail="Trader writes a Trading-R1 trace" color={COLORS.trader} side="left" delay={14} />
        <div style={{ width: 170, display: "flex", justifyContent: "center" }}>
          <PrismMark size={150} />
        </div>
        <AgentBeam label="GPT / DSPy" detail="Sentinel challenges evidence and calibration" color={COLORS.sentinel} side="right" delay={32} />
      </div>
      <FadeIn delay={76}>
        <div style={{ ...captionStyle, marginTop: 38 }}>
          Different model family. Different wallet. Different blind spots.
        </div>
      </FadeIn>
    </SceneShell>
  );
}

function EvidenceScene({ brollSrc }: { brollSrc?: string }) {
  return (
    <SceneShell eyebrow="evidence" title="Evidence becomes a receipt.">
      <OptionalBroll src={brollSrc} />
      <EvidenceRail />
      <div style={{ display: "flex", gap: 18, marginTop: 48 }}>
        <ProofCard title="Search provider" value="Exa MCP" accent={COLORS.sentinel} delay={56} />
        <ProofCard title="Search tool" value={SHOWCASE_PROOF.searchTool} accent={COLORS.trader} delay={68} />
        <ProofCard title="URL fetch" value={SHOWCASE_PROOF.fetchTool} accent={COLORS.verified} delay={80} />
        <ProofCard title="Source hash" value={SHOWCASE_PROOF.contentHash} accent={COLORS.arc} delay={92} />
      </div>
      <FadeIn delay={112}>
        <div style={{ ...captionStyle, marginTop: 34 }}>
          Missing, stale, unreadable, or non-matching evidence fails closed.
        </div>
      </FadeIn>
    </SceneShell>
  );
}

function CapitalGateScene({ brollSrc }: { brollSrc?: string }) {
  return (
    <SceneShell eyebrow="capital gate" title="If the proof fails, capital waits.">
      <OptionalBroll src={brollSrc} />
      <CapitalGateGraphic />
      <FadeIn delay={72}>
        <div style={{ ...captionStyle, marginTop: 18 }}>
          Prism treats blocked trades as safety wins, not product failures.
        </div>
      </FadeIn>
    </SceneShell>
  );
}

function SettlementScene({ brollSrc }: { brollSrc?: string }) {
  return (
    <SceneShell eyebrow="settlement" title="Agents can pay. Anyone can verify.">
      <OptionalBroll src={brollSrc} />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 22, marginTop: 56 }}>
        <ProofCard title="x402 paid validation" value={SHOWCASE_PROOF.x402Tx} accent={COLORS.usdc} delay={14} />
        <ProofCard title="Verdict IPFS" value={SHOWCASE_PROOF.verdictCid} accent={COLORS.arc} delay={28} />
        <ProofCard title="Canonical report" value={SHOWCASE_PROOF.canonicalTraceId.slice(0, 18) + "…"} accent={COLORS.sentinel} delay={42} />
        <ProofCard title="Outcome" value={SHOWCASE_PROOF.score} accent={COLORS.verified} delay={56} />
      </div>
      <FadeIn delay={86}>
        <div style={{ ...captionStyle, marginTop: 42 }}>
          x402 payments, IPFS content, Arc/ERC-8004 receipts, and URL-verified source hashes.
        </div>
      </FadeIn>
    </SceneShell>
  );
}

function CloseScene({ stats }: { stats: PrismShowcaseProps["stats"] }) {
  return (
    <SceneShell eyebrow="close" title="Prism">
      <div style={{ marginTop: 18 }}>
        <PrismMark size={190} />
      </div>
      <FadeIn delay={34}>
        <div style={{ ...captionStyle, marginTop: 22, fontSize: 34 }}>
          The trust layer for money-moving agents.
        </div>
      </FadeIn>
      <FadeIn delay={56}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 14, justifyContent: "center", maxWidth: 1260, marginTop: 46 }}>
          <StatPill label="verdicts" value={stats.verdictsIssued.toLocaleString()} accent={COLORS.sentinel} />
          <StatPill label="traces" value={stats.tracesValidated.toLocaleString()} accent={COLORS.trader} />
          <StatPill label="anchors" value={stats.onChainAnchors.toLocaleString()} accent={COLORS.arc} />
          <StatPill label="x402 calls" value={stats.externalX402Calls.toLocaleString()} accent={COLORS.usdc} />
          <StatPill label="builder trades" value={stats.builderAttributedTrades.toLocaleString()} accent={COLORS.verified} />
        </div>
      </FadeIn>
      <FadeIn delay={94}>
        <div style={{ marginTop: 40, fontFamily: FONT.mono, color: COLORS.faint, fontSize: 22 }}>
          prism-dashboard-production-e6e3.up.railway.app
        </div>
      </FadeIn>
    </SceneShell>
  );
}

function RiskCard({
  title,
  body,
  tone,
  delay,
}: {
  title: string;
  body: string;
  tone: string;
  delay: number;
}) {
  return (
    <FadeIn delay={delay} y={30}>
      <div
        style={{
          width: 420,
          minHeight: 230,
          borderRadius: 26,
          border: `1px solid ${tone}45`,
          background: `linear-gradient(135deg, ${tone}12, ${COLORS.panel})`,
          padding: 28,
          boxShadow: `0 0 38px ${tone}14`,
        }}
      >
        <div style={{ fontFamily: FONT.mono, color: tone, fontSize: 18, textTransform: "uppercase", letterSpacing: "0.15em" }}>
          {title}
        </div>
        <div style={{ color: COLORS.text, fontSize: 32, lineHeight: 1.12, letterSpacing: "-0.035em", fontWeight: 720, marginTop: 30 }}>
          {body}
        </div>
      </div>
    </FadeIn>
  );
}

const subtitleStyle: React.CSSProperties = {
  margin: 0,
  color: COLORS.muted,
  fontFamily: FONT.sans,
  fontSize: 34,
  lineHeight: 1.35,
  maxWidth: 980,
  textAlign: "center",
};

const captionStyle: React.CSSProperties = {
  color: COLORS.muted,
  fontFamily: FONT.sans,
  fontSize: 28,
  lineHeight: 1.35,
  maxWidth: 1180,
  textAlign: "center",
};

export const defaultShowcaseStats = {
  verdictsIssued: SHOWCASE_STATS.verdictsIssued,
  tracesValidated: SHOWCASE_STATS.tracesValidated,
  onChainAnchors: SHOWCASE_STATS.onChainAnchors,
  builderAttributedTrades: SHOWCASE_STATS.builderAttributedTrades,
  builderFeesUsdc: SHOWCASE_STATS.builderFeesUsdc,
  externalX402Calls: SHOWCASE_STATS.externalX402Calls,
};
