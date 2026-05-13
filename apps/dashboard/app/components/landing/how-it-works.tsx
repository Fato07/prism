"use client";

/**
 * HowItWorks — three-step mechanism explainer with chromatic motion.
 *
 * The spectrum connector line draws in from left to right as the section
 * enters the viewport, then a "photon" pulse travels across it to suggest
 * signal flowing through the prism. Each step card animates in with a
 * staggered entrance and exposes a richer hover state (lift + accent glow).
 *
 *   01 Trace      → trader's reasoning (cyan, incoming light)
 *   02 Challenge  → sentinel's adversarial pass (magenta, refraction)
 *   03 Anchor     → on-chain verdict on Arc (green, the spectrum)
 */

import { motion, useReducedMotion, useInView } from "motion/react";
import { useRef } from "react";
import { ArrowRight, FileCode, ShieldAlert, Anchor } from "lucide-react";

const STEPS = [
  {
    num: "01",
    accent: "trader" as const,
    accentVar: "var(--color-trader)",
    icon: FileCode,
    title: "Trader reasons",
    body: "The trader agent generates a Trading-R1 trace — thesis, evidence, risk factors — and pins it to IPFS with a content hash.",
    artifact: "trace_id",
    artifactValue: "ipfs://Qm…",
  },
  {
    num: "02",
    accent: "sentinel" as const,
    accentVar: "var(--color-sentinel)",
    icon: ShieldAlert,
    title: "Sentinel challenges",
    body: "An adversarial validator from a different model family picks the trace apart — evidence challenges, thesis challenges, calibration critique.",
    artifact: "verdict_score",
    artifactValue: "0 — 100",
  },
  {
    num: "03",
    accent: "good" as const,
    accentVar: "var(--color-verdict-good)",
    icon: Anchor,
    title: "Arc anchors it",
    body: "The verdict lands on ERC-8004 ValidationRegistry. Immutable. Sub-second finality. USDC-native gas. Anyone can verify.",
    artifact: "tx_hash",
    artifactValue: "0x…",
  },
];

const FADE_EASE = [0.16, 1, 0.3, 1] as const;

export function HowItWorks() {
  const reduced = useReducedMotion();
  const sectionRef = useRef<HTMLElement>(null);
  const inView = useInView(sectionRef, { once: true, margin: "-100px" });

  return (
    <section
      ref={sectionRef}
      className="relative border-b border-[var(--color-border)] bg-[var(--color-canvas)]"
      aria-labelledby="how-it-works"
    >
      <div className="mx-auto max-w-6xl px-6 py-24 sm:py-32">
        {/* Section header */}
        <div className="mb-16 flex flex-col items-start gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-mono text-xs font-medium uppercase tracking-[var(--tracking-wide)] text-fg-faint">
              How Prism works
            </p>
            <h2
              id="how-it-works"
              className="mt-2 max-w-2xl text-balance text-3xl font-semibold tracking-[var(--tracking-tight)] text-fg sm:text-4xl"
            >
              One signal in. A spectrum of verdicts out.
            </h2>
          </div>
          <p className="max-w-sm text-sm leading-relaxed text-fg-muted">
            Two agents. Two model families. One verdict, anchored on Arc. The
            sentinel is paid per validation in USDC over x402.
          </p>
        </div>

        {/* Spectrum line connecting the steps */}
        <div className="relative">
          {/* Track (always present, dim) */}
          <div
            className="absolute left-0 right-0 top-[60px] hidden h-px bg-[var(--color-border)] lg:block"
            aria-hidden="true"
          />

          {/* Spectrum line — draws in left → right when in view */}
          <motion.div
            className="absolute left-0 top-[60px] hidden h-px origin-left lg:block"
            style={{
              right: 0,
              background:
                "linear-gradient(90deg, transparent 0%, var(--color-trader) 15%, var(--color-sentinel) 50%, var(--color-verdict-good) 85%, transparent 100%)",
              opacity: 0.85,
            }}
            initial={reduced ? false : { scaleX: 0 }}
            animate={inView ? { scaleX: 1 } : { scaleX: 0 }}
            transition={{ duration: 1.4, ease: FADE_EASE, delay: 0.25 }}
            aria-hidden="true"
          />

          {/* Photon — a bright pulse that travels along the line after it draws */}
          {!reduced && (
            <motion.div
              className="absolute top-[57px] hidden h-1.5 w-1.5 rounded-full lg:block"
              style={{
                background: "var(--color-fg)",
                boxShadow:
                  "0 0 12px 2px color-mix(in oklch, var(--color-trader) 60%, transparent), 0 0 24px 4px color-mix(in oklch, var(--color-sentinel) 45%, transparent)",
              }}
              initial={{ left: "0%", opacity: 0 }}
              animate={
                inView
                  ? {
                      left: ["0%", "50%", "100%"],
                      opacity: [0, 1, 1, 0],
                    }
                  : { left: "0%", opacity: 0 }
              }
              transition={{
                duration: 2.2,
                ease: FADE_EASE,
                delay: 1.5,
                times: [0, 0.1, 0.9, 1],
                repeat: Infinity,
                repeatDelay: 4,
              }}
              aria-hidden="true"
            />
          )}

          <ol className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            {STEPS.map((step, i) => (
              <StepCard
                key={step.num}
                step={step}
                index={i}
                inView={inView}
                reduced={!!reduced}
              />
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}

/* ─────────────────────────── Step Card ─────────────────────────── */

interface StepCardProps {
  step: (typeof STEPS)[number];
  index: number;
  inView: boolean;
  reduced: boolean;
}

function StepCard({ step, index, inView, reduced }: StepCardProps) {
  const Icon = step.icon;

  return (
    <motion.li
      initial={reduced ? false : { opacity: 0, y: 24 }}
      animate={inView ? { opacity: 1, y: 0 } : { opacity: 0, y: 24 }}
      transition={{
        duration: 0.7,
        ease: FADE_EASE,
        delay: 0.4 + index * 0.12,
      }}
      whileHover={
        reduced
          ? undefined
          : {
              y: -4,
              transition: { duration: 0.25, ease: FADE_EASE },
            }
      }
      className="group relative flex flex-col gap-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-canvas-raised)]/60 p-6 backdrop-blur-sm transition-colors duration-[var(--duration-base)] hover:border-[var(--color-border-strong)]"
    >
      {/* Hover glow — strengthens on hover */}
      <span
        className="pointer-events-none absolute inset-0 rounded-xl opacity-0 transition-opacity duration-[var(--duration-base)] group-hover:opacity-100"
        style={{
          boxShadow: `inset 0 0 0 1px color-mix(in oklch, ${step.accentVar} 30%, transparent), 0 0 32px -8px color-mix(in oklch, ${step.accentVar} 45%, transparent)`,
        }}
        aria-hidden="true"
      />

      {/* Top: step number + accent dot (pulses on hover) */}
      <div className="relative flex items-center justify-between">
        <span className="text-mono text-xs font-medium uppercase tracking-[var(--tracking-wide)] text-fg-faint">
          Step {step.num}
        </span>
        <motion.span
          className="relative inline-flex h-2 w-2 items-center justify-center"
          aria-hidden="true"
        >
          <span
            className="absolute h-3 w-3 rounded-full opacity-0 transition-opacity duration-[var(--duration-base)] group-hover:opacity-100"
            style={{ backgroundColor: `color-mix(in oklch, ${step.accentVar} 45%, transparent)` }}
          />
          <span
            className="relative h-2 w-2 rounded-full"
            style={{ backgroundColor: step.accentVar }}
          />
        </motion.span>
      </div>

      {/* Icon — rotates in on entrance, scales on hover */}
      <motion.div
        initial={reduced ? false : { rotate: -12, scale: 0.85, opacity: 0 }}
        animate={
          inView
            ? { rotate: 0, scale: 1, opacity: 1 }
            : { rotate: -12, scale: 0.85, opacity: 0 }
        }
        transition={{
          duration: 0.6,
          ease: FADE_EASE,
          delay: 0.6 + index * 0.12,
        }}
        whileHover={
          reduced ? undefined : { scale: 1.08, rotate: 4, transition: { duration: 0.25 } }
        }
        className="relative inline-flex h-10 w-10 items-center justify-center rounded-lg border border-[var(--color-border)]"
        style={{
          backgroundColor: `color-mix(in oklch, ${step.accentVar} 12%, transparent)`,
        }}
      >
        <Icon
          className="h-5 w-5"
          style={{ color: step.accentVar }}
          strokeWidth={1.8}
        />
      </motion.div>

      {/* Title */}
      <h3 className="relative text-xl font-semibold tracking-[var(--tracking-tight)] text-fg">
        {step.title}
      </h3>

      {/* Body */}
      <p className="relative text-sm leading-relaxed text-fg-muted">
        {step.body}
      </p>

      {/* Artifact line */}
      <div className="relative mt-auto border-t border-[var(--color-border)] pt-4">
        <div className="flex items-center gap-2 text-mono text-xs">
          <motion.span
            initial={false}
            animate={{ x: [0, 3, 0] }}
            transition={{
              duration: 1.6,
              ease: "easeInOut",
              repeat: Infinity,
              repeatDelay: 2.5 + index * 0.4,
            }}
          >
            <ArrowRight
              className="h-3 w-3 text-fg-faint"
              strokeWidth={2}
            />
          </motion.span>
          <span className="text-fg-faint">{step.artifact}</span>
          <span className="text-fg-muted">=</span>
          <span
            className="font-medium"
            style={{ color: step.accentVar }}
          >
            {step.artifactValue}
          </span>
        </div>
      </div>
    </motion.li>
  );
}
