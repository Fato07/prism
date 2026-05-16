"use client";

/**
 * WhyPrism — the differentiator section.
 *
 * Asymmetric feature grid (1 big + 2 small). The big card uses a custom
 * animated SVG prism icon (light enters, splits into trader-cyan + sentinel-
 * magenta + verdict-green beams). The small cards use lucide icons wrapped
 * in motion so they breathe in on mount and bloom on hover.
 *
 * Stat numbers in the primary card animate count-up when in view.
 */

import {
  motion,
  useInView,
  useMotionValue,
  useTransform,
  animate,
  useReducedMotion,
} from "motion/react";
import { useEffect, useRef } from "react";
import { Anchor, Coins } from "lucide-react";
import { Pill } from "@/components/ui/pill";

const FADE_EASE = [0.16, 1, 0.3, 1] as const;

export function WhyPrism() {
  return (
    <section
      className="border-b border-[var(--color-border)]"
      aria-labelledby="features"
    >
      <div className="mx-auto max-w-6xl px-6 py-24 sm:py-32">
        <div className="mb-16 max-w-2xl">
          <p className="text-mono text-xs font-medium uppercase tracking-[var(--tracking-wide)] text-fg-faint">
            Why Prism
          </p>
          <h2
            id="features"
            className="mt-2 text-balance text-3xl font-semibold tracking-[var(--tracking-tight)] text-fg sm:text-4xl"
          >
            AI agents trade. Who checks their reasoning?
          </h2>
          <p className="mt-4 text-base leading-relaxed text-fg-muted sm:text-lg">
            One agent&apos;s confidence is not the same as truth. Prism pits a
            sentinel from a different model family against every trade —
            catching reasoning flaws before capital moves.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <PrimaryCard />
          <SmallCard
            accentVar="var(--color-verdict-good)"
            icon={Anchor}
            title="On-chain proof"
            description="Every verdict lands on Arc's ERC-8004 ValidationRegistry. Sub-second finality. USDC-native gas. Cryptographically verifiable forever."
            delay={0.15}
          />
          <SmallCard
            accentVar="var(--color-trader)"
            icon={Coins}
            title="Sentinel-as-a-service"
            description="Other agents pay $0.01 USDC per validation via x402 micropayments. Payments settle over x402; verdicts anchor on Arc. A reusable validation service, not just a dashboard."
            delay={0.3}
          />
        </div>
      </div>
    </section>
  );
}

/* ─────────────────────────── Primary card ─────────────────────────── */

function PrimaryCard() {
  const ref = useRef<HTMLElement>(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });
  const reduced = useReducedMotion();

  return (
    <motion.article
      ref={ref}
      initial={reduced ? false : { opacity: 0, y: 16 }}
      animate={inView ? { opacity: 1, y: 0 } : { opacity: 0, y: 16 }}
      transition={{ duration: 0.7, ease: FADE_EASE }}
      whileHover={reduced ? undefined : { y: -3 }}
      className="group relative flex flex-col gap-5 overflow-hidden rounded-2xl border border-[var(--color-border-strong)] bg-[var(--color-canvas-raised)]/60 p-6 backdrop-blur-sm transition-colors hover:bg-[var(--color-canvas-raised)] sm:p-8 lg:col-span-2 lg:row-span-2"
    >
      {/* Multi-layer glow that intensifies on hover */}
      <span
        className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full opacity-50 blur-3xl transition-all duration-500 group-hover:opacity-80 group-hover:scale-110"
        style={{
          backgroundColor:
            "color-mix(in oklch, var(--color-sentinel) 35%, transparent)",
        }}
        aria-hidden="true"
      />
      <span
        className="pointer-events-none absolute -bottom-32 -left-16 h-72 w-72 rounded-full opacity-30 blur-3xl transition-all duration-500 group-hover:opacity-50"
        style={{
          backgroundColor:
            "color-mix(in oklch, var(--color-trader) 30%, transparent)",
        }}
        aria-hidden="true"
      />

      <div className="relative flex items-center justify-between">
        <PrismIcon inView={inView} reduced={!!reduced} />
        <Pill tone="neutral" emphasis="outline" size="xs">
          <span className="text-mono uppercase tracking-[var(--tracking-wide)]">
            The core mechanism
          </span>
        </Pill>
      </div>

      <div className="relative">
        <h3 className="text-2xl font-semibold tracking-[var(--tracking-tight)] text-fg sm:text-3xl">
          Adversarial validation
        </h3>
        <p className="mt-3 text-base leading-relaxed text-fg-muted sm:text-lg">
          A sentinel from a different model family — Anthropic, OpenAI, Zhipu
          — picks each trace apart. Evidence challenges, thesis challenges,
          calibration critique. Cross-family by design.
        </p>
      </div>

      <div className="relative mt-auto grid grid-cols-2 gap-4 border-t border-[var(--color-border)] pt-5">
        <StaticStat label="Verdict scale" value="0 — 100" />
        <CountUpStat
          label="Model families"
          target={3}
          suffix=" tested"
          inView={inView}
          reduced={!!reduced}
        />
      </div>
    </motion.article>
  );
}

/* ─────────────────────────── PrismIcon ─────────────────────────── */

/**
 * Animated SVG: a single white ray enters from the left, hits the prism
 * (triangle), splits into three colored beams (cyan, magenta, green).
 * Drawn with motion paths that animate stroke-dashoffset on view-enter,
 * then re-pulse on hover.
 */
function PrismIcon({ inView, reduced }: { inView: boolean; reduced: boolean }) {
  return (
    <div
      className="relative inline-flex h-14 w-14 items-center justify-center rounded-xl border border-[var(--color-border)]"
      style={{
        backgroundColor:
          "color-mix(in oklch, var(--color-sentinel) 12%, transparent)",
      }}
    >
      <svg
        width="44"
        height="44"
        viewBox="0 0 44 44"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        {/* Triangle prism body */}
        <motion.path
          d="M22 8 L34 32 L10 32 Z"
          stroke="var(--color-fg-muted)"
          strokeWidth="1.4"
          strokeLinejoin="round"
          fill="none"
          initial={reduced ? false : { pathLength: 0, opacity: 0 }}
          animate={
            inView
              ? { pathLength: 1, opacity: 0.85 }
              : { pathLength: 0, opacity: 0 }
          }
          transition={{ duration: 0.9, ease: FADE_EASE, delay: 0.1 }}
        />

        {/* Incoming white ray from the left */}
        <motion.line
          x1="0"
          y1="22"
          x2="14"
          y2="22"
          stroke="var(--color-fg)"
          strokeWidth="1.4"
          strokeLinecap="round"
          initial={reduced ? false : { pathLength: 0, opacity: 0 }}
          animate={
            inView
              ? { pathLength: 1, opacity: 1 }
              : { pathLength: 0, opacity: 0 }
          }
          transition={{ duration: 0.45, ease: FADE_EASE, delay: 0.5 }}
        />

        {/* Three output beams — staggered, brand-mapped */}
        <motion.line
          x1="30"
          y1="22"
          x2="46"
          y2="14"
          stroke="var(--color-trader)"
          strokeWidth="1.6"
          strokeLinecap="round"
          initial={reduced ? false : { pathLength: 0, opacity: 0 }}
          animate={
            inView
              ? { pathLength: 1, opacity: 1 }
              : { pathLength: 0, opacity: 0 }
          }
          transition={{ duration: 0.6, ease: FADE_EASE, delay: 0.95 }}
        />
        <motion.line
          x1="30"
          y1="22"
          x2="48"
          y2="22"
          stroke="var(--color-sentinel)"
          strokeWidth="1.6"
          strokeLinecap="round"
          initial={reduced ? false : { pathLength: 0, opacity: 0 }}
          animate={
            inView
              ? { pathLength: 1, opacity: 1 }
              : { pathLength: 0, opacity: 0 }
          }
          transition={{ duration: 0.6, ease: FADE_EASE, delay: 1.1 }}
        />
        <motion.line
          x1="30"
          y1="22"
          x2="46"
          y2="30"
          stroke="var(--color-verdict-good)"
          strokeWidth="1.6"
          strokeLinecap="round"
          initial={reduced ? false : { pathLength: 0, opacity: 0 }}
          animate={
            inView
              ? { pathLength: 1, opacity: 1 }
              : { pathLength: 0, opacity: 0 }
          }
          transition={{ duration: 0.6, ease: FADE_EASE, delay: 1.25 }}
        />
      </svg>
    </div>
  );
}

/* ─────────────────────────── SmallCard ─────────────────────────── */

interface SmallCardProps {
  accentVar: string;
  icon: React.ComponentType<{
    className?: string;
    strokeWidth?: number;
    style?: React.CSSProperties;
  }>;
  title: string;
  description: string;
  delay: number;
}

function SmallCard({
  accentVar,
  icon: Icon,
  title,
  description,
  delay,
}: SmallCardProps) {
  const ref = useRef<HTMLElement>(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });
  const reduced = useReducedMotion();

  return (
    <motion.article
      ref={ref}
      initial={reduced ? false : { opacity: 0, y: 16 }}
      animate={inView ? { opacity: 1, y: 0 } : { opacity: 0, y: 16 }}
      transition={{ duration: 0.65, ease: FADE_EASE, delay }}
      whileHover={reduced ? undefined : { y: -3 }}
      className="group relative flex flex-col gap-5 overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-canvas-raised)]/60 p-6 backdrop-blur-sm transition-colors hover:border-[var(--color-border-strong)] sm:p-8"
    >
      <span
        className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full opacity-30 blur-3xl transition-all duration-500 group-hover:opacity-70 group-hover:scale-110"
        style={{
          backgroundColor: `color-mix(in oklch, ${accentVar} 40%, transparent)`,
        }}
        aria-hidden="true"
      />

      <div className="relative flex items-center justify-between">
        <motion.div
          initial={reduced ? false : { scale: 0.6, opacity: 0 }}
          animate={
            inView
              ? { scale: 1, opacity: 1 }
              : { scale: 0.6, opacity: 0 }
          }
          transition={{
            duration: 0.5,
            ease: FADE_EASE,
            delay: delay + 0.15,
          }}
          whileHover={
            reduced
              ? undefined
              : { rotate: 8, scale: 1.08, transition: { duration: 0.25 } }
          }
          className="inline-flex h-11 w-11 items-center justify-center rounded-xl border border-[var(--color-border)]"
          style={{
            backgroundColor: `color-mix(in oklch, ${accentVar} 10%, transparent)`,
          }}
        >
          <Icon
            className="h-5 w-5"
            strokeWidth={1.8}
            style={{ color: accentVar }}
          />
        </motion.div>
      </div>

      <div className="relative">
        <h3 className="text-lg font-semibold tracking-[var(--tracking-tight)] text-fg">
          {title}
        </h3>
        <p className="mt-3 text-sm leading-relaxed text-fg-muted">
          {description}
        </p>
      </div>
    </motion.article>
  );
}

/* ─────────────────────────── Stat (count-up) ─────────────────────────── */

function StaticStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-mono text-[10px] font-medium uppercase tracking-[var(--tracking-wide)] text-fg-faint">
        {label}
      </div>
      <div className="mt-1 text-mono text-lg font-semibold tabular-nums text-fg">
        {value}
      </div>
    </div>
  );
}

function CountUpStat({
  label,
  target,
  suffix,
  inView,
  reduced,
}: {
  label: string;
  target: number;
  suffix?: string;
  inView: boolean;
  reduced: boolean;
}) {
  const motionValue = useMotionValue(reduced ? target : 0);
  const display = useTransform(motionValue, (latest) =>
    Math.round(latest).toString(),
  );

  useEffect(() => {
    if (!inView || reduced) {
      motionValue.set(target);
      return;
    }
    const controls = animate(motionValue, target, {
      duration: 1.6,
      ease: FADE_EASE,
      delay: 0.4,
    });
    return () => controls.stop();
  }, [inView, target, reduced, motionValue]);

  return (
    <div>
      <div className="text-mono text-[10px] font-medium uppercase tracking-[var(--tracking-wide)] text-fg-faint">
        {label}
      </div>
      <div className="mt-1 text-mono text-lg font-semibold tabular-nums text-fg">
        <motion.span>{display}</motion.span>
        {suffix && <span className="text-fg-muted">{suffix}</span>}
      </div>
    </div>
  );
}
