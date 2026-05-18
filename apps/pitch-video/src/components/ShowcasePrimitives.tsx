import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
  Video,
  staticFile,
} from "remotion";
import { COLORS, FONT } from "../brand";

export function FadeIn({
  children,
  delay = 0,
  duration = 18,
  y = 18,
}: {
  children: React.ReactNode;
  delay?: number;
  duration?: number;
  y?: number;
}) {
  const frame = useCurrentFrame();
  const progress = interpolate(frame, [delay, delay + duration], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        opacity: progress,
        transform: `translateY(${(1 - progress) * y}px)`,
      }}
    >
      {children}
    </div>
  );
}

export function SceneShell({
  eyebrow,
  title,
  children,
  align = "center",
}: {
  eyebrow: string;
  title: string;
  children: React.ReactNode;
  align?: "center" | "left";
}) {
  return (
    <AbsoluteFill
      style={{
        padding: 72,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        alignItems: align === "center" ? "center" : "flex-start",
        color: COLORS.text,
        fontFamily: FONT.sans,
      }}
    >
      <div
        style={{
          position: "absolute",
          left: 58,
          top: 42,
          fontFamily: FONT.mono,
          color: COLORS.faint,
          fontSize: 17,
          letterSpacing: "0.18em",
          textTransform: "uppercase",
        }}
      >
        Prism / {eyebrow}
      </div>
      <FadeIn>
        <h1
          style={{
            margin: 0,
            maxWidth: align === "center" ? 1240 : 1050,
            textAlign: align === "center" ? "center" : "left",
            fontSize: 76,
            lineHeight: 0.96,
            letterSpacing: "-0.055em",
            fontWeight: 760,
          }}
        >
          {title}
        </h1>
      </FadeIn>
      {children}
    </AbsoluteFill>
  );
}

export function RefractionBackdrop() {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pulse = Math.sin(frame / fps) * 0.5 + 0.5;

  return (
    <AbsoluteFill
      style={{
        overflow: "hidden",
        background:
          `radial-gradient(circle at 20% 20%, ${COLORS.sentinel}24 0%, transparent 32%),` +
          `radial-gradient(circle at 78% 62%, ${COLORS.trader}1f 0%, transparent 30%),` +
          `linear-gradient(135deg, ${COLORS.bg}, ${COLORS.bg2})`,
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          opacity: 0.18,
          backgroundImage:
            "linear-gradient(rgba(255,255,255,0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.08) 1px, transparent 1px)",
          backgroundSize: "72px 72px",
          transform: `translate(${(frame % 72) * -0.18}px, ${(frame % 72) * -0.1}px)`,
        }}
      />
      <div
        style={{
          position: "absolute",
          width: 980,
          height: 980,
          left: -260,
          top: -300,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${COLORS.trader}22, transparent 62%)`,
          filter: "blur(18px)",
          opacity: 0.5 + pulse * 0.12,
        }}
      />
      <div
        style={{
          position: "absolute",
          width: 860,
          height: 860,
          right: -180,
          bottom: -260,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${COLORS.sentinel}24, transparent 64%)`,
          filter: "blur(20px)",
          opacity: 0.48 + pulse * 0.1,
        }}
      />
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "linear-gradient(90deg, rgba(255,255,255,0.05), transparent 18%, transparent 82%, rgba(255,255,255,0.05))",
        }}
      />
    </AbsoluteFill>
  );
}

export function OptionalBroll({ src }: { src?: string }) {
  if (!src) return null;
  const resolved = src.startsWith("http") ? src : staticFile(src);
  return (
    <AbsoluteFill style={{ opacity: 0.35, mixBlendMode: "screen" }}>
      <Video
        src={resolved}
        muted
        loop
        style={{ width: "100%", height: "100%", objectFit: "cover" }}
      />
    </AbsoluteFill>
  );
}

export function PrismMark({ size = 170 }: { size?: number }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const draw = interpolate(frame, [0, fps * 0.8], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const beam = interpolate(frame, [fps * 0.6, fps * 1.25], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <svg width={size} height={size} viewBox="0 0 180 180" aria-hidden="true">
      <defs>
        <linearGradient id="prismShowcaseGradient" x1="30" y1="20" x2="150" y2="160">
          <stop stopColor={COLORS.trader} />
          <stop offset="0.5" stopColor={COLORS.sentinel} />
          <stop offset="1" stopColor={COLORS.verified} />
        </linearGradient>
        <filter id="prismGlow">
          <feGaussianBlur stdDeviation="3.5" result="coloredBlur" />
          <feMerge>
            <feMergeNode in="coloredBlur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <path
        d="M90 20 L154 150 L26 150 Z"
        fill="rgba(255,255,255,0.02)"
        stroke="url(#prismShowcaseGradient)"
        strokeWidth="3"
        strokeDasharray="390"
        strokeDashoffset={390 - draw * 390}
        filter="url(#prismGlow)"
      />
      <line x1="0" y1="92" x2={56 * beam} y2="92" stroke="#fff" strokeWidth="2.4" opacity="0.75" />
      <line x1="120" y1="92" x2={120 + 66 * beam} y2={54 - 8 * beam} stroke={COLORS.trader} strokeWidth="3" />
      <line x1="120" y1="92" x2={120 + 74 * beam} y2="92" stroke={COLORS.sentinel} strokeWidth="3" />
      <line x1="120" y1="92" x2={120 + 66 * beam} y2={130 + 8 * beam} stroke={COLORS.verified} strokeWidth="3" />
    </svg>
  );
}

export function AgentBeam({
  label,
  detail,
  color,
  side,
  delay,
}: {
  label: string;
  detail: string;
  color: string;
  side: "left" | "right";
  delay: number;
}) {
  const frame = useCurrentFrame();
  const x = interpolate(frame, [delay, delay + 22], [side === "left" ? -90 : 90, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const opacity = interpolate(frame, [delay, delay + 18], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        opacity,
        transform: `translateX(${x}px)`,
        width: 500,
        minHeight: 220,
        border: `1px solid ${color}55`,
        background: `linear-gradient(135deg, ${color}1f, rgba(9, 13, 20, 0.82))`,
        borderRadius: 28,
        padding: 30,
        boxShadow: `0 0 48px ${color}24`,
      }}
    >
      <div style={{ fontFamily: FONT.mono, color, fontSize: 20, textTransform: "uppercase", letterSpacing: "0.16em" }}>
        {label}
      </div>
      <div style={{ marginTop: 18, color: COLORS.text, fontSize: 34, fontWeight: 720, letterSpacing: "-0.035em" }}>
        {detail}
      </div>
    </div>
  );
}

export function ProofCard({
  title,
  value,
  accent = COLORS.verified,
  delay = 0,
}: {
  title: string;
  value: string;
  accent?: string;
  delay?: number;
}) {
  return (
    <FadeIn delay={delay} y={24}>
      <div
        style={{
          minWidth: 350,
          border: `1px solid ${accent}42`,
          background: `linear-gradient(135deg, ${accent}14, ${COLORS.panel})`,
          borderRadius: 18,
          padding: "20px 24px",
          boxShadow: `0 0 36px ${accent}14`,
        }}
      >
        <div style={{ fontFamily: FONT.mono, color: COLORS.faint, fontSize: 15, textTransform: "uppercase", letterSpacing: "0.14em" }}>
          {title}
        </div>
        <div style={{ marginTop: 9, color: COLORS.text, fontFamily: FONT.mono, fontSize: 28, fontWeight: 700 }}>
          {value}
        </div>
      </div>
    </FadeIn>
  );
}

export function EvidenceRail() {
  const frame = useCurrentFrame();
  const items = ["issue", "search", "fetch", "hash", "gate"];

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 18, marginTop: 46 }}>
      {items.map((item, index) => {
        const progress = interpolate(frame, [24 + index * 12, 42 + index * 12], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
        const active = progress > 0.2;
        return (
          <React.Fragment key={item}>
            <div
              style={{
                width: 138,
                height: 138,
                borderRadius: "50%",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                border: `1px solid ${active ? COLORS.verified : COLORS.borderStrong}`,
                background: active ? `${COLORS.verified}14` : COLORS.panel,
                color: active ? COLORS.verified : COLORS.faint,
                fontFamily: FONT.mono,
                fontSize: 18,
                letterSpacing: "0.11em",
                textTransform: "uppercase",
                transform: `scale(${0.9 + progress * 0.1})`,
                boxShadow: active ? `0 0 34px ${COLORS.verified}24` : "none",
              }}
            >
              {item}
            </div>
            {index < items.length - 1 && (
              <div
                style={{
                  width: 78,
                  height: 2,
                  background: `linear-gradient(90deg, ${COLORS.verified}, transparent)`,
                  opacity: progress,
                }}
              />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

export function CapitalGateGraphic() {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const gateSpring = spring({ frame: frame - 20, fps, config: { damping: 15, stiffness: 90 } });
  const blockerOpacity = interpolate(frame, [0, 18, 52, 68], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const verifiedOpacity = interpolate(frame, [56, 78], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div style={{ position: "relative", width: 1080, height: 360, marginTop: 46 }}>
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 155,
          width: 1080,
          height: 7,
          borderRadius: 99,
          background: `linear-gradient(90deg, ${COLORS.trader}, ${COLORS.warn}, ${COLORS.verified})`,
          opacity: 0.55,
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 410,
          top: 50 - gateSpring * 14,
          width: 260,
          height: 260,
          borderRadius: 34,
          border: `2px solid ${COLORS.warn}`,
          background: `${COLORS.warn}10`,
          boxShadow: `0 0 46px ${COLORS.warn}20`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          opacity: blockerOpacity,
        }}
      >
        <div style={{ textAlign: "center" }}>
          <div style={{ color: COLORS.warn, fontFamily: FONT.mono, fontSize: 22, letterSpacing: "0.14em" }}>REVIEW</div>
          <div style={{ color: COLORS.text, fontSize: 31, fontWeight: 760, marginTop: 8 }}>Capital waits</div>
        </div>
      </div>
      <div
        style={{
          position: "absolute",
          right: 70,
          top: 80,
          width: 220,
          height: 220,
          borderRadius: "50%",
          border: `2px solid ${COLORS.verified}`,
          background: `${COLORS.verified}12`,
          boxShadow: `0 0 56px ${COLORS.verified}26`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          opacity: verifiedOpacity,
        }}
      >
        <div style={{ color: COLORS.verified, fontFamily: FONT.mono, fontSize: 26, letterSpacing: "0.12em" }}>VERIFIED</div>
      </div>
    </div>
  );
}

export function StatPill({ label, value, accent }: { label: string; value: string; accent: string }) {
  return (
    <div
      style={{
        border: `1px solid ${accent}44`,
        background: `${accent}10`,
        borderRadius: 999,
        padding: "12px 18px",
        display: "flex",
        gap: 12,
        alignItems: "baseline",
      }}
    >
      <span style={{ color: accent, fontFamily: FONT.mono, fontSize: 20, fontWeight: 760 }}>{value}</span>
      <span style={{ color: COLORS.muted, fontFamily: FONT.mono, fontSize: 14, textTransform: "uppercase", letterSpacing: "0.12em" }}>{label}</span>
    </div>
  );
}
