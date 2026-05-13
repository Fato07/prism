/**
 * EmptyState — shown when a panel has no data yet.
 *
 * Uses a subtle prism-fragment SVG to keep the dashboard on-brand even
 * when the data layer is sparse.
 */

import { cn } from "@/lib/utils";

interface EmptyStateProps {
  title: string;
  description: string;
  className?: string;
}

function PrismFragment() {
  return (
    <svg
      width="48"
      height="48"
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M9 39L24 5L39 39Z"
        stroke="url(#empty-gradient)"
        strokeWidth="1.2"
        strokeLinejoin="round"
        opacity="0.7"
      />
      <line
        x1="32"
        y1="22"
        x2="42"
        y2="22"
        stroke="var(--color-trader)"
        strokeWidth="1"
        opacity="0.45"
      />
      <line
        x1="32"
        y1="26"
        x2="44"
        y2="26"
        stroke="var(--color-sentinel)"
        strokeWidth="1"
        opacity="0.45"
      />
      <line
        x1="32"
        y1="30"
        x2="40"
        y2="30"
        stroke="var(--color-verdict-good)"
        strokeWidth="1"
        opacity="0.45"
      />
      <defs>
        <linearGradient id="empty-gradient" x1="9" y1="5" x2="39" y2="39">
          <stop stopColor="var(--color-trader)" />
          <stop offset="0.5" stopColor="var(--color-sentinel)" />
          <stop offset="1" stopColor="var(--color-verdict-good)" />
        </linearGradient>
      </defs>
    </svg>
  );
}

export function EmptyState({ title, description, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 py-14 text-center",
        className,
      )}
    >
      <PrismFragment />
      <h3 className="text-base font-medium text-fg-muted">{title}</h3>
      <p className="max-w-xs text-sm text-fg-faint">{description}</p>
    </div>
  );
}
