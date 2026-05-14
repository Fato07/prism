/**
 * GlobalNav — shared navigation bar for all Prism dashboard pages.
 *
 * Renders a consistent set of route links across every page so that
 * every new route is reachable from the global nav (VAL-CROSS-007).
 * Responsive at 375px viewport — no horizontal scroll (VAL-CROSS-008).
 *
 * This is a server component. The only client sub-component is
 * <ConnectWalletButton> which is already marked 'use client'.
 */

import { ConnectWalletButton } from "@/components/connect-wallet-button";
import { Separator } from "@/components/ui/separator";

/** Route entries displayed in the nav. */
const NAV_ROUTES: readonly {
  readonly href: string;
  readonly label: string;
  readonly shortLabel: string;
  readonly page: string;
}[] = [
  { href: "/dashboard", label: "Dashboard", shortLabel: "Home", page: "dashboard" },
  { href: "/history", label: "History", shortLabel: "History", page: "history" },
  { href: "/submit", label: "Submit", shortLabel: "Submit", page: "submit" },
  { href: "/me", label: "Me", shortLabel: "Me", page: "me" },
  { href: "/builder-fees", label: "Fees", shortLabel: "Fees", page: "builder-fees" },
  { href: "/stats", label: "Stats", shortLabel: "Stats", page: "stats" },
] as const;

interface GlobalNavProps {
  /** Identifies the current page for breadcrumb and active-link styling. */
  currentPage?: string;
  /** Extra content rendered on the right side of the nav (e.g., dashboard badges). */
  rightExtra?: React.ReactNode;
  /** Optional inline styles on the <nav> element (e.g., CSS custom properties). */
  style?: React.CSSProperties;
}

export function GlobalNav({ currentPage, rightExtra, style }: GlobalNavProps) {
  return (
    <nav
      className="sticky top-0 z-50 border-b border-[var(--color-border)] bg-[var(--color-canvas)]/80 backdrop-blur-md"
      aria-label="Main navigation"
      style={style}
    >
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-2 gap-y-2 px-4 py-2.5 sm:px-6 sm:py-3">
        {/* ── Left: Wordmark + breadcrumb ── */}
        <a
          href="/"
          className="inline-flex shrink-0 items-center gap-2 text-base font-semibold tracking-[var(--tracking-tight)] text-fg"
        >
          <Wordmark />
          <span className="hidden sm:inline">Prism</span>
        </a>

        {currentPage && currentPage !== "home" && (
          <>
            <span className="text-fg-faint text-xs" aria-hidden="true">/</span>
            <span className="text-mono text-xs uppercase tracking-[var(--tracking-wide)] text-fg-muted">
              {currentPage}
            </span>
          </>
        )}

        <Separator orientation="vertical" className="mx-1 hidden h-4 sm:block" />

        {/* ── Center: Route links ── */}
        <div className="flex flex-wrap items-center gap-1">
          {NAV_ROUTES.map((route) => {
            const isActive = currentPage === route.page;
            return (
              <a
                key={route.href}
                href={route.href}
                aria-current={isActive ? "page" : undefined}
                className={`inline-flex items-center rounded-md border px-2 py-1 text-xs font-medium transition-colors focus-ring sm:px-2.5 sm:py-1.5 sm:text-sm ${
                  isActive
                    ? "border-[var(--color-border-strong)] bg-[var(--color-canvas-raised)] text-fg"
                    : "border-transparent text-fg-muted hover:border-[var(--color-border)] hover:text-fg"
                }`}
              >
                {route.label}
              </a>
            );
          })}
        </div>

        {/* ── Right: Wallet + extras ── */}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <ConnectWalletButton />
          {rightExtra}
        </div>
      </div>
    </nav>
  );
}

/* ─────────────── Wordmark SVG ─────────────── */

function Wordmark() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 20 20"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M4 17L10 3L16 17Z"
        stroke="url(#globalnav-prism-gradient)"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
      <defs>
        <linearGradient
          id="globalnav-prism-gradient"
          x1="3"
          y1="3"
          x2="17"
          y2="17"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="var(--color-trader)" />
          <stop offset="0.6" stopColor="var(--color-sentinel)" />
          <stop offset="1" stopColor="var(--color-verdict-good)" />
        </linearGradient>
      </defs>
    </svg>
  );
}
