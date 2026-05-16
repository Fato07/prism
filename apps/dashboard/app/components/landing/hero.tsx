"use client";

/**
 * Hero — the chromatic landing hero.
 *
 * Renders a paper-design MeshGradient shader as the backdrop, with a
 * grain overlay for texture, then layers a centered headline, eyebrow,
 * subheadline, waitlist form, and live waitlist count above it.
 *
 * The shader animates slowly (speed 0.18) and respects prefers-reduced-motion
 * (handled inside the Shader component). The headline + form animate in
 * via Motion on mount.
 */

import { motion } from "motion/react";
import { Shader } from "@/components/ui/shader";
import { Pill } from "@/components/ui/pill";
import { LiveDot } from "@/components/ui/live-dot";
import { WaitlistSignupForm } from "@/components/waitlist-form";
import { BrandMark } from "@/components/brands/brand-mark";

interface HeroProps {
  waitlistCount: number;
}

const FADE_IN = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
};

const FADE_EASE = [0.16, 1, 0.3, 1] as const; // ease-out-expo

export function Hero({ waitlistCount }: HeroProps) {
  const countDisplay =
    waitlistCount > 0
      ? `${waitlistCount.toLocaleString()} on the waitlist`
      : "Closed beta — be first";

  return (
    <section
      className="relative isolate overflow-hidden border-b border-[var(--color-border)]"
      aria-labelledby="hero-headline"
    >
      {/* Layered shaders: mesh for chromatic dispersion + grain for texture */}
      <Shader variant="spectrum" intensity="vivid" />
      <Shader variant="spectrum" intensity="vivid" grain />

      {/* Soft inner darkening behind the text — not a hard vignette,
         just enough to anchor the headline without killing the shader. */}
      <div
        className="absolute inset-0 -z-10 pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse at 50% 55%, color-mix(in oklch, var(--color-canvas) 55%, transparent) 0%, transparent 60%)",
        }}
        aria-hidden="true"
      />

      {/* Top + bottom canvas fades — preserve nav legibility, smooth handoff
         to the next section. */}
      <div
        className="absolute inset-x-0 top-0 -z-10 h-24 pointer-events-none"
        style={{
          background:
            "linear-gradient(to bottom, var(--color-canvas) 0%, transparent 100%)",
        }}
        aria-hidden="true"
      />
      <div
        className="absolute inset-x-0 bottom-0 -z-10 h-40 pointer-events-none"
        style={{
          background:
            "linear-gradient(to top, var(--color-canvas) 0%, transparent 100%)",
        }}
        aria-hidden="true"
      />

      {/* SVG film-grain overlay — adds tactile texture across the whole hero,
         independent of the GPU shader. ~1KB inline, no extra request. */}
      <div
        className="absolute inset-0 -z-10 pointer-events-none opacity-[0.18] mix-blend-overlay"
        aria-hidden="true"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='200' height='200'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='1.2' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 0 0 0 0.5 0'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>\")",
          backgroundRepeat: "repeat",
        }}
      />

      <div className="relative mx-auto flex max-w-5xl flex-col items-center px-6 pb-40 pt-32 text-center sm:pt-40 sm:pb-48">
        {/* Eyebrow status row — glass emphasis floats cleanly above the shader */}
        <motion.div
          {...FADE_IN}
          transition={{ duration: 0.6, ease: FADE_EASE }}
          className="mb-7 flex flex-wrap items-center justify-center gap-2"
        >
          <Pill tone="info" emphasis="glass" size="sm">
            <BrandMark name="arc" size={14} aria-label="Arc" />
            <LiveDot tone="online" pulse />
            <span className="text-mono">Arc Testnet · live</span>
          </Pill>
          <Pill tone="neutral" emphasis="glass" size="sm">
            <BrandMark name="ethereum" size={12} aria-label="ERC" />
            <span className="text-mono">ERC-8004</span>
          </Pill>
          <Pill tone="neutral" emphasis="glass" size="sm">
            <BrandMark name="coinbase" size={12} aria-label="Coinbase x402" />
            <span className="text-mono">x402</span>
          </Pill>
        </motion.div>

        {/* Headline */}
        <motion.h1
          id="hero-headline"
          {...FADE_IN}
          transition={{ duration: 0.7, ease: FADE_EASE, delay: 0.05 }}
          className="text-balance text-5xl font-semibold tracking-[var(--tracking-display)] text-fg sm:text-6xl lg:text-7xl"
          style={{ letterSpacing: "var(--tracking-display)" }}
        >
          See through the{" "}
          <span
            className="bg-clip-text text-transparent"
            style={{
              backgroundImage:
                "linear-gradient(120deg, var(--color-trader) 0%, oklch(0.78 0.20 280) 35%, var(--color-sentinel) 65%, var(--color-verdict-good) 100%)",
            }}
          >
            reasoning
          </span>
          .
        </motion.h1>

        {/* Subheadline */}
        <motion.p
          {...FADE_IN}
          transition={{ duration: 0.7, ease: FADE_EASE, delay: 0.15 }}
          className="mt-6 max-w-2xl text-balance text-lg leading-relaxed text-fg-muted sm:text-xl"
        >
          Two AI agents from different model families challenge each other before
          capital moves. Every verdict is anchored on Arc with sub-second finality
          and USDC-native settlement.
        </motion.p>

        {/* Waitlist form */}
        <motion.div
          {...FADE_IN}
          transition={{ duration: 0.7, ease: FADE_EASE, delay: 0.25 }}
          className="mt-12 w-full max-w-md"
        >
          <WaitlistSignupForm />
          <p className="mt-4 inline-flex items-center justify-center gap-2 rounded-full border border-[var(--color-border-strong)] bg-[var(--color-canvas)]/70 px-3.5 py-1.5 text-xs text-fg-muted backdrop-blur-md mx-auto">
            <span
              className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--color-success)] shadow-[0_0_8px_0_var(--color-success)]"
              aria-hidden="true"
            />
            <span className="text-mono font-medium text-fg">{countDisplay}</span>
            <span className="text-fg-faint">·</span>
            <span className="text-fg-muted">
              no spam, one email when we open
            </span>
          </p>
        </motion.div>
      </div>
    </section>
  );
}
