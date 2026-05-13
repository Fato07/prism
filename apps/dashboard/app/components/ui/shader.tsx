"use client";

/**
 * Shader — client wrapper around @paper-design/shaders-react.
 *
 * Renders a GPU-accelerated mesh-gradient shader as a hero background.
 * Falls back to a CSS animated gradient if the shader fails to mount
 * (no WebGL, reduced motion, etc.).
 *
 * Brand mapping:
 *   - "spectrum"  → trader-cyan → violet → sentinel-magenta dispersion
 *   - "trader"    → cyan-dominant (used in trader panel backdrop)
 *   - "sentinel"  → magenta-dominant (used in sentinel panel backdrop)
 */

import { MeshGradient, GrainGradient } from "@paper-design/shaders-react";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

type ShaderVariant = "spectrum" | "trader" | "sentinel" | "verdict";

interface ShaderProps {
  variant?: ShaderVariant;
  className?: string;
  intensity?: "subtle" | "vivid";
  grain?: boolean;
}

const PALETTES: Record<ShaderVariant, string[]> = {
  // Full chromatic dispersion — the "prism" hero. Brighter, more saturated
  // so the texture reads against the dark canvas without overpowering text.
  spectrum: ["#0EA5E9", "#6366F1", "#A855F7", "#EC4899", "#F97316"],
  // Cyan-dominant — incoming light
  trader: ["#06B6D4", "#22D3EE", "#67E8F9", "#A5F3FC", "#E0F2FE"],
  // Magenta-dominant — critical refraction
  sentinel: ["#A21CAF", "#D946EF", "#E879F9", "#F0ABFC", "#FCE7F3"],
  // Green-amber-red — verdict spectrum
  verdict: ["#16A34A", "#84CC16", "#EAB308", "#F97316", "#DC2626"],
};

export function Shader({
  variant = "spectrum",
  className,
  intensity = "subtle",
  grain = false,
}: ShaderProps) {
  const [mounted, setMounted] = useState(false);
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);

  useEffect(() => {
    setMounted(true);
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setPrefersReducedMotion(mq.matches);
    const handler = (e: MediaQueryListEvent) => setPrefersReducedMotion(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  const colors = PALETTES[variant];
  const speed = prefersReducedMotion ? 0 : intensity === "subtle" ? 0.22 : 0.5;
  const distortion = intensity === "subtle" ? 0.7 : 1.1;
  const swirl = intensity === "subtle" ? 0.35 : 0.65;

  // SSR / pre-mount fallback: CSS gradient. Same colors, no GPU.
  if (!mounted) {
    return (
      <div
        className={cn(
          "absolute inset-0 -z-10 animate-drift opacity-70",
          className,
        )}
        style={{
          backgroundImage: `radial-gradient(circle at 25% 30%, ${colors[1]}, transparent 55%),
                            radial-gradient(circle at 75% 70%, ${colors[3]}, transparent 55%),
                            radial-gradient(circle at 50% 50%, ${colors[2]}, transparent 60%)`,
          backgroundColor: "var(--color-canvas)",
        }}
        aria-hidden="true"
      />
    );
  }

  if (grain) {
    return (
      <div
        className={cn("absolute inset-0 -z-10 mix-blend-screen", className)}
        aria-hidden="true"
      >
        <GrainGradient
          colors={colors}
          speed={speed * 0.6}
          softness={0.7}
          intensity={intensity === "subtle" ? 0.55 : 0.8}
          noise={0.95}
          shape="wave"
          style={{ width: "100%", height: "100%" }}
        />
      </div>
    );
  }

  return (
    <div className={cn("absolute inset-0 -z-10", className)} aria-hidden="true">
      <MeshGradient
        colors={colors}
        speed={speed}
        distortion={distortion}
        swirl={swirl}
        style={{ width: "100%", height: "100%" }}
      />
    </div>
  );
}
