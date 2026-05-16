/**
 * Route-level loading shell shown immediately during App Router transitions.
 * Keeps navigation feeling responsive while server components fetch Neon/IPFS.
 */
export default function Loading() {
  return (
    <div className="min-h-screen bg-canvas text-fg">
      <div className="sticky top-0 z-50 border-b border-[var(--color-border)] bg-[var(--color-canvas)]/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3 sm:px-6">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <path d="M4 17L10 3L16 17Z" stroke="url(#loading-prism-gradient)" strokeWidth="1.4" strokeLinejoin="round" />
            <defs>
              <linearGradient id="loading-prism-gradient" x1="3" y1="3" x2="17" y2="17" gradientUnits="userSpaceOnUse">
                <stop stopColor="var(--color-trader)" />
                <stop offset="0.6" stopColor="var(--color-sentinel)" />
                <stop offset="1" stopColor="var(--color-verdict-good)" />
              </linearGradient>
            </defs>
          </svg>
          <span className="text-sm font-semibold tracking-[var(--tracking-tight)] text-fg">
            Prism
          </span>
          <span className="text-mono text-xs text-fg-faint">loading…</span>
        </div>
      </div>

      <main className="mx-auto max-w-6xl px-6 py-10">
        <div className="mb-8 h-7 w-56 animate-pulse rounded-lg bg-[var(--color-canvas-raised)]" />
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="h-40 animate-pulse rounded-2xl border border-[var(--color-border)] bg-[var(--color-canvas-raised)]/65" />
          <div className="h-40 animate-pulse rounded-2xl border border-[var(--color-border)] bg-[var(--color-canvas-raised)]/65" />
          <div className="h-40 animate-pulse rounded-2xl border border-[var(--color-border)] bg-[var(--color-canvas-raised)]/65" />
        </div>
        <div className="mt-4 h-64 animate-pulse rounded-2xl border border-[var(--color-border)] bg-[var(--color-canvas-raised)]/50" />
      </main>
    </div>
  );
}
