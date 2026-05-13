/**
 * Badge — legacy badge component, kept for backward compat.
 *
 * Variants are mapped onto the new Pill tone system internally. Prefer
 * `Pill` for new components.
 */

import { cn } from "@/lib/utils";

const variantStyles: Record<string, string> = {
  default:
    "bg-[var(--color-canvas-raised)] text-fg border-[var(--color-border)]",
  reject:
    "bg-[var(--color-danger)]/10 text-[var(--color-danger)] border-[var(--color-danger)]/40",
  warn:
    "bg-[var(--color-warning)]/10 text-[var(--color-warning)] border-[var(--color-warning)]/40",
  pass:
    "bg-[var(--color-success)]/10 text-[var(--color-success)] border-[var(--color-success)]/40",
  endorse:
    "bg-[var(--color-success)]/15 text-[var(--color-success)] border-[var(--color-success)]/50",
  outline:
    "border-[var(--color-border-strong)] text-fg-muted",
  buy:
    "bg-[var(--color-verdict-good)]/10 text-[var(--color-verdict-good)] border-[var(--color-verdict-good)]/40",
  sell:
    "bg-[var(--color-verdict-bad)]/10 text-[var(--color-verdict-bad)] border-[var(--color-verdict-bad)]/40",
};

export function Badge({
  className,
  variant = "default",
  children,
}: {
  className?: string;
  variant?: keyof typeof variantStyles;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium tracking-tight",
        variantStyles[variant] ?? variantStyles.default,
        className,
      )}
    >
      {children}
    </span>
  );
}
