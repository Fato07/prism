/**
 * Card — surface primitive.
 *
 * Variant matrix:
 *   tone         visual                                   accent ring on top edge
 *   default   →  flat raised panel                        none
 *   trader    →  raised panel with cyan accent            top
 *   sentinel  →  raised panel with magenta accent         top
 *   verdict   →  raised panel with verdict-good accent    top
 *
 * Accent rings live as a 1px gradient line on the top edge — Linear-style.
 */

import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

type CardTone = "default" | "trader" | "sentinel" | "verdict";

const ACCENT_VARS: Record<CardTone, string | null> = {
  default: null,
  trader: "var(--color-trader)",
  sentinel: "var(--color-sentinel)",
  verdict: "var(--color-verdict-good)",
};

export function Card({
  className,
  tone = "default",
  children,
}: {
  className?: string;
  tone?: CardTone;
  children: ReactNode;
}) {
  const accent = ACCENT_VARS[tone];

  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-2xl",
        "border border-[var(--color-border)] bg-[var(--color-canvas-raised)]/65 backdrop-blur-sm",
        "shadow-[var(--shadow-soft)]",
        "transition-colors",
        "hover:border-[var(--color-border-strong)]",
        className,
      )}
    >
      {accent && (
        <span
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 top-0 h-px"
          style={{
            background: `linear-gradient(90deg, transparent 0%, ${accent} 50%, transparent 100%)`,
            opacity: 0.7,
          }}
        />
      )}
      {accent && (
        <span
          aria-hidden="true"
          className="pointer-events-none absolute -right-20 -top-20 h-40 w-40 rounded-full blur-3xl"
          style={{
            backgroundColor: `color-mix(in oklch, ${accent} 25%, transparent)`,
          }}
        />
      )}
      <div className="relative">{children}</div>
    </div>
  );
}

export function CardHeader({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-4 border-b border-[var(--color-border)] px-5 py-4",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function CardTitle({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <h3
      className={cn(
        "text-base font-semibold tracking-[var(--tracking-tight)] text-fg",
        className,
      )}
    >
      {children}
    </h3>
  );
}

export function CardContent({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return <div className={cn("p-5", className)}>{children}</div>;
}
