"use client";

/**
 * TraceDetailProvider — minimal DockContext wrapper for the trace detail page.
 *
 * The AdversarialDialogue component requires a DockContext (normally
 * provided by DashboardShell on the /dashboard page). On /trace/[id] we
 * don't need the full shell layout — we just need the context so the
 * dialogue can render inline. This provider always returns `side: "none"`.
 */

import { useMemo, type ReactNode } from "react";
import { DockContext } from "@/components/dashboard/dashboard-shell";

interface TraceDetailProviderProps {
  children: ReactNode;
}

export function TraceDetailProvider({ children }: TraceDetailProviderProps) {
  const value = useMemo(
    () => ({ side: "none" as const, setSide: () => {} }),
    [],
  );

  return <DockContext.Provider value={value}>{children}</DockContext.Provider>;
}
