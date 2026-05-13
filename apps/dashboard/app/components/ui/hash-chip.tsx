"use client";

/**
 * HashChip — a click-to-copy monospace hash block.
 *
 * Used everywhere we surface a hash: tx hashes, IPFS CIDs, content hashes,
 * wallet addresses. Renders truncated by default with a hover-revealed
 * copy button; opens an explorer link in a new tab when `href` is provided.
 */

import { Check, Copy, ExternalLink } from "lucide-react";
import { useState, useCallback } from "react";
import { cn } from "@/lib/utils";

interface HashChipProps {
  value: string;
  href?: string;
  label?: string;
  truncate?: number;
  className?: string;
  size?: "xs" | "sm";
}

function truncateMiddle(value: string, keep: number): string {
  if (value.length <= keep * 2 + 3) return value;
  return `${value.slice(0, keep)}…${value.slice(-keep)}`;
}

export function HashChip({
  value,
  href,
  label,
  truncate = 6,
  className,
  size = "sm",
}: HashChipProps) {
  const [copied, setCopied] = useState(false);
  const display = truncate > 0 ? truncateMiddle(value, truncate) : value;

  const copy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      /* clipboard blocked — quiet */
    }
  }, [value]);

  const textSize = size === "xs" ? "text-[10px]" : "text-xs";
  const iconSize = size === "xs" ? "h-2.5 w-2.5" : "h-3 w-3";

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border border-[var(--color-border)]",
        "bg-[var(--color-canvas-sunken)]/60 px-2 py-1",
        "text-mono text-fg-muted",
        "transition-colors hover:border-[var(--color-border-strong)] hover:text-fg",
        textSize,
        className,
      )}
    >
      {label && <span className="text-fg-faint">{label}</span>}
      {href ? (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-fg hover:text-trader"
        >
          <span>{display}</span>
          <ExternalLink className={iconSize} />
        </a>
      ) : (
        <span className="text-fg">{display}</span>
      )}
      <button
        type="button"
        onClick={copy}
        aria-label={copied ? "Copied" : `Copy ${label ?? "value"}`}
        className={cn(
          "inline-flex items-center text-fg-faint hover:text-fg transition-colors",
          "focus-ring rounded",
        )}
      >
        {copied ? (
          <Check className={cn(iconSize, "text-[var(--color-success)]")} />
        ) : (
          <Copy className={iconSize} />
        )}
      </button>
    </span>
  );
}
