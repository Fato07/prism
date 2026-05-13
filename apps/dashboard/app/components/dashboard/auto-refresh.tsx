"use client";

/**
 * AutoRefresh — silently re-runs the server component tree on a timer.
 *
 * Uses `router.refresh()` which re-fetches all server data without a full
 * page navigation or client unmount. IPFS calls stay cached for 5 min via
 * the existing `next: { revalidate: 300 }` config, so the polling cost is
 * mostly the DB aggregates.
 *
 * Pauses when the tab is hidden to keep Neon traffic sane.
 */

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { LiveDot } from "@/components/ui/live-dot";
import { RotateCw } from "lucide-react";

interface AutoRefreshProps {
  intervalMs?: number;
}

export function AutoRefresh({ intervalMs = 8000 }: AutoRefreshProps) {
  const router = useRouter();
  const [lastRefreshed, setLastRefreshed] = useState<Date>(() => new Date());
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | null = null;

    const tick = () => {
      if (cancelled) return;
      if (document.hidden) return;
      setBusy(true);
      router.refresh();
      // Brief visual feedback — refresh() resolves synchronously
      // so we rely on a short timer to clear the busy state.
      setTimeout(() => {
        if (!cancelled) {
          setLastRefreshed(new Date());
          setBusy(false);
        }
      }, 400);
    };

    timer = setInterval(tick, intervalMs);

    const onVis = () => {
      if (!document.hidden) tick();
    };
    document.addEventListener("visibilitychange", onVis);

    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [router, intervalMs]);

  return (
    <span className="inline-flex items-center gap-1.5 text-mono text-[11px] text-fg-faint">
      <LiveDot tone={busy ? "pending" : "online"} pulse size="sm" />
      <span>
        {busy ? "syncing" : "live"} ·{" "}
        <RelativeAge date={lastRefreshed} />
      </span>
      <button
        type="button"
        onClick={() => {
          setBusy(true);
          router.refresh();
          setTimeout(() => {
            setLastRefreshed(new Date());
            setBusy(false);
          }, 400);
        }}
        aria-label="Refresh now"
        className="inline-flex h-5 w-5 items-center justify-center rounded text-fg-faint transition-colors hover:text-fg focus-ring"
      >
        <RotateCw
          className={`h-3 w-3 ${busy ? "animate-spin" : ""}`}
          strokeWidth={2}
        />
      </button>
    </span>
  );
}

function RelativeAge({ date }: { date: Date }) {
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, []);
  const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (seconds < 2) return <span>just now</span>;
  if (seconds < 60) return <span>{seconds}s ago</span>;
  const minutes = Math.floor(seconds / 60);
  return <span>{minutes}m ago</span>;
}
