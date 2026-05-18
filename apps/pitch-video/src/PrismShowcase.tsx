import React from "react";
import { AbsoluteFill, Audio as RemotionAudio, Sequence, staticFile } from "remotion";
import { z } from "zod";
import { COLORS, FONT, SHOWCASE_PROOF, SHOWCASE_STATS } from "./brand";
import {
  AgentBeam,
  BrollPlate,
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
      {musicSrc && <AudioTrack src={audioSource(musicSrc)} volume={voiceoverSrc ? 0.18 : 0.62} loop />}
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
        <CapitalGateScene />
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
      <BrollPlate
        src={brollSrc}
        accent={COLORS.trader}
        style={{ left: 510, right: "auto", bottom: 190, width: 900, height: 500, opacity: 0.28 }}
      />
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
    <SceneShell eyebrow="problem" title="Confidence is not an audit." align="left">
      <FailClosedSignal />
      <div style={{ display: "flex", gap: 20, marginTop: 50 }}>
        <RiskCard title="Lucky trade" body="Profit can hide bad reasoning." tone={COLORS.warn} delay={14} />
        <RiskCard title="Stale evidence" body="Old citations can masquerade as conviction." tone={COLORS.blocked} delay={26} />
        <RiskCard title="No provenance" body="A claim without a source cannot move capital." tone={COLORS.sentinel} delay={38} />
      </div>
      <FadeIn delay={66}>
        <div style={{ ...captionStyle, marginTop: 46, textAlign: "left" }}>
          Prism turns hidden uncertainty into a visible capital gate.
        </div>
      </FadeIn>
    </SceneShell>
  );
}

function MechanismScene({ brollSrc }: { brollSrc?: string }) {
  return (
    <SceneShell eyebrow="mechanism" title="Trader proposes. Sentinel attacks.">
      <BrollPlate
        src={brollSrc}
        accent={COLORS.trader}
        style={{ right: 86, bottom: 84, width: 430, height: 242, opacity: 0.34, filter: "blur(0.6px) saturate(0.82)" }}
      />
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
      <BrollPlate
        src={brollSrc}
        accent={COLORS.verified}
        style={{ left: 82, right: "auto", bottom: 68, width: 380, height: 214, opacity: 0.26, filter: "blur(1.1px) saturate(0.72)" }}
      />
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

function CapitalGateScene() {
  return (
    <SceneShell eyebrow="capital gate" title="If the proof fails, capital waits.">
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
    <SceneShell eyebrow="settlement" title="Agents pay. Anyone verifies.">
      <BrollPlate
        src={brollSrc}
        accent={COLORS.arc}
        style={{ right: 72, bottom: 72, width: 500, height: 280, opacity: 0.56 }}
      />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 22, marginTop: 56 }}>
        <ProofCard title="x402 paid validation" value={SHOWCASE_PROOF.x402Tx} accent={COLORS.usdc} delay={14} />
        <ProofCard title="Verdict IPFS" value={SHOWCASE_PROOF.verdictCid} accent={COLORS.arc} delay={28} />
        <ProofCard title="Public report" value={SHOWCASE_PROOF.canonicalTraceId.slice(0, 18) + "…"} accent={COLORS.sentinel} delay={42} />
        <ProofCard title="Outcome" value={SHOWCASE_PROOF.score} accent={COLORS.verified} delay={56} />
      </div>
      <FadeIn delay={86}>
        <div style={{ ...captionStyle, marginTop: 42 }}>
          Paid validation. Pinned verdict. Public report. URL-verified source hashes.
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
          Receipts over confidence for money-moving agents.
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

function FailClosedSignal() {
  const rows = [
    ["claim", "unchecked", COLORS.warn],
    ["source", "stale", COLORS.blocked],
    ["action", "hold", COLORS.warn],
  ] as const;

  return (
    <div
      style={{
        position: "absolute",
        right: 92,
        top: 282,
        width: 390,
        borderRadius: 30,
        border: `1px solid ${COLORS.warn}36`,
        background: `linear-gradient(135deg, ${COLORS.warn}10, ${COLORS.panelStrong})`,
        boxShadow: `0 0 80px ${COLORS.warn}12`,
        padding: 26,
      }}
    >
      <div style={{ fontFamily: FONT.mono, color: COLORS.warn, fontSize: 15, letterSpacing: "0.16em", textTransform: "uppercase" }}>
        fail-closed gate
      </div>
      <div style={{ marginTop: 24, display: "grid", gap: 13 }}>
        {rows.map(([label, value, color]) => (
          <div
            key={label}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              borderRadius: 15,
              border: `1px solid ${color}2f`,
              background: `${color}0e`,
              padding: "14px 16px",
              fontFamily: FONT.mono,
              textTransform: "uppercase",
              letterSpacing: "0.12em",
            }}
          >
            <span style={{ color: COLORS.faint, fontSize: 13 }}>{label}</span>
            <span style={{ color, fontSize: 15, fontWeight: 760 }}>{value}</span>
          </div>
        ))}
      </div>
      <div style={{ marginTop: 22, color: COLORS.text, fontSize: 34, fontWeight: 780, letterSpacing: "-0.045em" }}>
        No proof, no trade.
      </div>
    </div>
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
          width: 390,
          minHeight: 218,
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
        <div style={{ color: COLORS.text, fontSize: 30, lineHeight: 1.12, letterSpacing: "-0.035em", fontWeight: 720, marginTop: 28 }}>
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
