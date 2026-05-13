"use client";

/**
 * Expandable — wraps any panel and exposes a top-right "Maximize" button
 * that re-renders the same children inside a centered Dialog modal.
 *
 * Usage:
 *   <Expandable label="Trader reasoning">
 *     <TraderPanel ... />
 *   </Expandable>
 *
 * The wrapper itself adds zero layout; it just absolutely-positions the
 * maximize button over the top-right corner of the child. The same children
 * subtree is re-mounted inside the Dialog when opened, so any client-state
 * inside the child resets — which is fine for read-only data panels.
 */

import { Maximize2, Minimize2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Dialog } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

interface ExpandableProps {
  label: string;
  description?: string;
  /** `max-w-*` Tailwind class controlling the modal width. Default: max-w-5xl. */
  modalMaxWidthClass?: string;
  /** Position the maximize button. Default: `top-right`. */
  buttonPosition?: "top-right" | "header-inline";
  className?: string;
  children: ReactNode;
}

export function Expandable({
  label,
  description,
  modalMaxWidthClass = "max-w-5xl",
  buttonPosition = "top-right",
  className,
  children,
}: ExpandableProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className={cn("relative", className)}>
      {/* Inline child — natural rendering, no styling overhead */}
      {children}

      {/* Maximize affordance — sits over the top-right corner. The actual
          card's header is usually padding p-5, so top-3 right-3 lands nicely
          over the title row without intersecting the title text. */}
      {buttonPosition === "top-right" && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label={`Expand ${label}`}
          title={`Expand ${label}`}
          className="focus-ring absolute right-3 top-3 z-10 inline-flex h-7 w-7 items-center justify-center rounded-md border border-[var(--color-border)] bg-[var(--color-canvas-raised)]/70 text-fg-muted backdrop-blur-sm transition-all hover:scale-105 hover:border-[var(--color-border-strong)] hover:text-fg"
        >
          <Maximize2 className="h-3.5 w-3.5" strokeWidth={2} />
        </button>
      )}

      {/* Modal — re-renders the same children with more breathing room */}
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title={label}
        description={description}
        maxWidthClass={modalMaxWidthClass}
      >
        <div className="p-1">{children}</div>
      </Dialog>
    </div>
  );
}

/* ─────────────── Hook variant for components that want to manage their own button placement ─────────────── */

export function useExpandable() {
  const [open, setOpen] = useState(false);
  return {
    open,
    expand: () => setOpen(true),
    collapse: () => setOpen(false),
    toggle: () => setOpen((v) => !v),
  };
}

/* ─────────────── Standalone Expand button (for headers that render their own controls) ─────────────── */

export function ExpandButton({
  onClick,
  label,
  expanded,
  className,
}: {
  onClick: () => void;
  label: string;
  expanded?: boolean;
  className?: string;
}) {
  const Icon = expanded ? Minimize2 : Maximize2;
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={expanded ? `Collapse ${label}` : `Expand ${label}`}
      title={expanded ? `Collapse ${label}` : `Expand ${label}`}
      className={cn(
        "focus-ring inline-flex h-7 w-7 items-center justify-center rounded-md border border-[var(--color-border)] text-fg-muted transition-colors hover:border-[var(--color-border-strong)] hover:text-fg",
        className,
      )}
    >
      <Icon className="h-3.5 w-3.5" strokeWidth={2} />
    </button>
  );
}
