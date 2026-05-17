"use client";

/**
 * DashboardShell — client wrapper that owns the page-level layout state.
 *
 * The Adversarial dialogue can be in one of three positions:
 *   - `none`  : inline after core workspace/proof (default)
 *   - `left`  : sticky full-height column on the left
 *   - `right` : sticky full-height column on the right
 *
 * The dock side is exposed via DockContext so the AdversarialDialogue
 * component (and only it, for now) can mutate it from its own header
 * controls. The side preference persists across page navigations via
 * localStorage.
 *
 * Layout strategy:
 *   When `side === "none"`, render content as a normal single-column main with
 *   proof before the longer dialogue deep-dive so receipt cards do not get
 *   pushed beneath the chat transcript. When docked, the page becomes a
 *   2-column flex with a sticky aside. The dialogue content is rendered EITHER
 *   inline OR in the aside, never both — driven by the same context.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type DockSide = "none" | "left" | "right";

interface DockContextValue {
  side: DockSide;
  setSide: (next: DockSide) => void;
}

/** Exported so other pages (e.g. /trace/[id]) can provide a DockContext for AdversarialDialogue. */
export const DockContext = createContext<DockContextValue>({
  side: "none",
  setSide: () => {},
});

export function useDock(): DockContextValue {
  return useContext(DockContext);
}

const STORAGE_KEY = "prism:dialogue:dock-side";

function isDockSide(value: unknown): value is DockSide {
  return value === "none" || value === "left" || value === "right";
}

interface DashboardShellProps {
  workspace: ReactNode;
  proof: ReactNode;
  /** The dialogue node. Rendered inline after workspace/proof when undocked;
   *  rendered in the side aside when docked. */
  dialogue: ReactNode;
  /** Optional aside title — defaults to "Adversarial dialogue". */
  asideTitle?: string;
}

export function DashboardShell({
  workspace,
  proof,
  dialogue,
  asideTitle = "Adversarial dialogue",
}: DashboardShellProps) {
  const [side, setSideState] = useState<DockSide>("none");

  // Restore docked side on mount
  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (isDockSide(stored)) setSideState(stored);
    } catch {
      /* localStorage unavailable */
    }
  }, []);

  const setSide = useCallback((next: DockSide) => {
    setSideState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* ignore */
    }
  }, []);

  const value = useMemo(() => ({ side, setSide }), [side, setSide]);

  const docked = side !== "none";

  return (
    <DockContext.Provider value={value}>
      {docked ? (
        <div className="mx-auto flex w-full max-w-[1600px] gap-0 px-0">
          {side === "left" && (
            <DialogueAside title={asideTitle}>{dialogue}</DialogueAside>
          )}
          <main className="min-w-0 flex-1 px-6 pb-16 pt-8">
            {workspace}
            <div className="mt-14">{proof}</div>
          </main>
          {side === "right" && (
            <DialogueAside title={asideTitle}>{dialogue}</DialogueAside>
          )}
        </div>
      ) : (
        <main className="mx-auto max-w-7xl px-6 pb-16 pt-8">
          {workspace}
          <div className="mt-14">{proof}</div>
          {/* Centered inline dialogue when undocked, after core workspace/proof */}
          <div className="mx-auto mt-14 w-full max-w-4xl">{dialogue}</div>
        </main>
      )}
    </DockContext.Provider>
  );
}

/* ─────────────── Sticky aside ─────────────── */

function DialogueAside({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <aside
      role="complementary"
      aria-label={title}
      // Width tuned for chat readability (380px); sticky inside the page so
      // it stays visible while the main column scrolls. Header offset (~60px)
      // accounts for the sticky dashboard header.
      className="hidden w-[380px] shrink-0 border-x border-[var(--color-border)] bg-[var(--color-canvas)]/85 backdrop-blur-md lg:block"
    >
      <div className="sticky top-[var(--dashboard-header-h,64px)] flex h-[calc(100vh-var(--dashboard-header-h,64px))] flex-col">
        {children}
      </div>
    </aside>
  );
}
