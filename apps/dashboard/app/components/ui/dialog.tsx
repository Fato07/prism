"use client";

/**
 * Dialog — accessible modal primitive.
 *
 * Portals into document.body. Renders a backdrop with blur + a centered
 * content card that animates in (scale + fade). Dismisses on Escape, on
 * backdrop click, and on Close-button click. Restores body scroll lock.
 *
 * No Radix dependency — focus management is best-effort (autofocus on the
 * close button, return focus to opener on close).
 */

import { AnimatePresence, motion } from "motion/react";
import { X } from "lucide-react";
import {
  type ReactNode,
  useCallback,
  useEffect,
  useRef,
} from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  description?: string;
  /** `max-w-*` Tailwind class for the content width. Default: max-w-4xl. */
  maxWidthClass?: string;
  /** Pass `false` to hide the built-in close button (for embedded controls). */
  showClose?: boolean;
  children: ReactNode;
}

const FADE_EASE = [0.16, 1, 0.3, 1] as const;

export function Dialog({
  open,
  onClose,
  title,
  description,
  maxWidthClass = "max-w-4xl",
  showClose = true,
  children,
}: DialogProps) {
  const openerRef = useRef<HTMLElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  // Capture the active element when the dialog opens so we can restore focus
  useEffect(() => {
    if (open) {
      openerRef.current = document.activeElement as HTMLElement | null;
    } else if (openerRef.current && typeof openerRef.current.focus === "function") {
      openerRef.current.focus();
    }
  }, [open]);

  // Body scroll lock
  useEffect(() => {
    if (!open) return;
    const original = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = original;
    };
  }, [open]);

  // Escape to close
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // Autofocus the close button on open
  useEffect(() => {
    if (open) {
      const id = window.setTimeout(() => closeButtonRef.current?.focus(), 80);
      return () => window.clearTimeout(id);
    }
  }, [open]);

  const onBackdropClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (e.target === e.currentTarget) onClose();
    },
    [onClose],
  );

  if (typeof document === "undefined") return null;

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          key="prism-dialog-root"
          className="fixed inset-0 z-[100] flex items-center justify-center px-4 sm:px-6"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18, ease: FADE_EASE }}
          aria-hidden={!open}
        >
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-[var(--color-canvas)]/75 backdrop-blur-md"
            onClick={onBackdropClick}
            aria-hidden="true"
          />

          {/* Content */}
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby={title ? "prism-dialog-title" : undefined}
            aria-describedby={description ? "prism-dialog-description" : undefined}
            initial={{ opacity: 0, scale: 0.96, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }}
            transition={{ duration: 0.22, ease: FADE_EASE }}
            className={cn(
              "relative z-10 max-h-[88vh] w-full overflow-hidden rounded-2xl",
              "border border-[var(--color-border-strong)] bg-[var(--color-canvas-raised)]",
              "shadow-[0_24px_64px_-12px_oklch(0_0_0/0.6),0_0_0_1px_oklch(1_0_0/0.04)_inset]",
              maxWidthClass,
            )}
          >
            {(title || showClose) && (
              <div className="flex items-center justify-between gap-4 border-b border-[var(--color-border)] px-5 py-3.5">
                <div className="min-w-0">
                  {title && (
                    <h2
                      id="prism-dialog-title"
                      className="text-base font-semibold tracking-[var(--tracking-tight)] text-fg"
                    >
                      {title}
                    </h2>
                  )}
                  {description && (
                    <p
                      id="prism-dialog-description"
                      className="text-mono text-[11px] text-fg-faint"
                    >
                      {description}
                    </p>
                  )}
                </div>
                {showClose && (
                  <button
                    ref={closeButtonRef}
                    type="button"
                    onClick={onClose}
                    aria-label="Close dialog"
                    className="focus-ring inline-flex h-8 w-8 items-center justify-center rounded-md border border-[var(--color-border)] text-fg-muted transition-colors hover:border-[var(--color-border-strong)] hover:text-fg"
                  >
                    <X className="h-4 w-4" strokeWidth={2} />
                  </button>
                )}
              </div>
            )}
            <div className="max-h-[calc(88vh-64px)] overflow-auto">
              {children}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
