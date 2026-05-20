"use client";

/**
 * OperatorShell — client‑side auth + status display for /operator.
 *
 * Renders a password input for the OPERATOR_ADMIN_TOKEN.  Once a valid token
 * is provided the component fetches the trader's 8‑field runtime status via
 * GET /api/admin/runtime and displays it as a read‑only status card.
 *
 * No mutation buttons yet — read‑only surface only.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Pill } from "@/components/ui/pill";
import { Separator } from "@/components/ui/separator";
import { Lock, Eye, EyeOff, Loader2, AlertCircle } from "lucide-react";

/* ─────────────── Types ─────────────── */

interface RuntimeStatus {
  scheduler_running: boolean;
  interval_minutes: number;
  auto_pipeline_enabled: boolean;
  trade_mode: "paper" | "live";
  last_tick_timestamp: string | null;
  next_tick: string | null;
  last_error: string | null;
  service_version: string;
}

const SESSION_KEY = "prism:operator:token";

/* ─────────────── Helpers ─────────────── */

function formatTimestamp(iso: string | null): string {
  if (!iso) return "\u2014";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

type LoadState =
  | { phase: "idle" }
  | { phase: "loading" }
  | { phase: "ready"; data: RuntimeStatus }
  | { phase: "error"; message: string };

type TokenState =
  | { phase: "absent" }
  | { phase: "stored"; value: string }
  | { phase: "entered"; value: string };

/* ─────────────── Component ─────────────── */

export function OperatorShell() {
  const [token, setToken] = useState<TokenState>({ phase: "absent" });
  const [inputValue, setInputValue] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [load, setLoad] = useState<LoadState>({ phase: "idle" });
  const inputRef = useRef<HTMLInputElement>(null);
  const mountedRef = useRef(false);

  /* ── Restore token from sessionStorage on mount ── */
  useEffect(() => {
    if (mountedRef.current) return;
    mountedRef.current = true;
    try {
      const stored = sessionStorage.getItem(SESSION_KEY);
      if (stored) {
        setToken({ phase: "stored", value: stored });
      }
    } catch {
      /* sessionStorage unavailable */
    }
  }, []);

  /* ── Fetch status whenever we have a usable token ── */
  const fetchStatus = useCallback(async (tokenValue: string) => {
    setLoad({ phase: "loading" });
    try {
      const res = await fetch("/api/admin/runtime", {
        headers: { Authorization: `Bearer ${tokenValue}` },
        cache: "no-store",
      });
      if (res.ok) {
        const data: RuntimeStatus = await res.json();
        setLoad({ phase: "ready", data });
      } else {
        const body = await res.json().catch(() => ({}));
        setLoad({
          phase: "error",
          message:
            body.error === "operator_admin_required"
              ? "Invalid admin token. Check your credentials and try again."
              : `Request failed (${res.status}). Try again.`,
        });
      }
    } catch {
      setLoad({
        phase: "error",
        message: "Unable to reach the runtime service. Is the trader running?",
      });
    }
  }, []);

  /* ── Auto-fetch on stored token ── */
  useEffect(() => {
    if (token.phase === "stored") {
      fetchStatus(token.value);
    }
  }, [token, fetchStatus]);

  /* ── Handle connect button ── */
  const handleConnect = useCallback(() => {
    const trimmed = inputValue.trim();
    if (!trimmed) return;
    try {
      sessionStorage.setItem(SESSION_KEY, trimmed);
    } catch {
      /* ignore */
    }
    setToken({ phase: "entered", value: trimmed });
    setInputValue("");
    fetchStatus(trimmed);
  }, [inputValue, fetchStatus]);

  /* ── Handle Enter key ── */
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter") handleConnect();
    },
    [handleConnect],
  );

  /* ── Handle disconnect ── */
  const handleDisconnect = useCallback(() => {
    try {
      sessionStorage.removeItem(SESSION_KEY);
    } catch {
      /* ignore */
    }
    setToken({ phase: "absent" });
    setLoad({ phase: "idle" });
  }, []);

  const isAuthenticated =
    token.phase === "stored" || token.phase === "entered";

  /* ─────────────── Render ─────────────── */

  return (
    <div className="space-y-6">
      {/* ── Auth bar ── */}
      <div className="flex flex-wrap items-center gap-3">
        {!isAuthenticated ? (
          <>
            <div className="relative flex-1 min-w-[220px] max-w-sm">
              <Lock
                className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-fg-faint pointer-events-none"
                aria-hidden="true"
              />
              <input
                ref={inputRef}
                type={showPassword ? "text" : "password"}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Admin token"
                aria-label="Admin token"
                autoComplete="off"
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-canvas-raised)] py-2 pl-10 pr-10 text-sm text-fg placeholder:text-fg-faint focus:border-[var(--color-trader)] focus:outline-none focus:ring-1 focus:ring-[var(--color-trader)]/40 transition-colors"
              />
              <button
                type="button"
                onClick={() => setShowPassword((p) => !p)}
                aria-label={showPassword ? "Hide token" : "Show token"}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-fg-faint hover:text-fg-muted transition-colors"
              >
                {showPassword ? (
                  <EyeOff className="h-4 w-4" />
                ) : (
                  <Eye className="h-4 w-4" />
                )}
              </button>
            </div>
            <button
              onClick={handleConnect}
              disabled={!inputValue.trim() || load.phase === "loading"}
              className="inline-flex items-center gap-2 rounded-lg border border-[var(--color-trader)]/40 bg-[var(--color-trader)]/10 px-4 py-2 text-sm font-medium text-[var(--color-trader)] transition-colors hover:bg-[var(--color-trader)]/20 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {load.phase === "loading" ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                "Connect"
              )}
            </button>
          </>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone="good" emphasis="soft" size="sm">
              <Lock className="h-3 w-3" aria-hidden="true" />
              Authenticated
            </Pill>
            <button
              onClick={handleDisconnect}
              className="text-xs text-fg-muted hover:text-fg transition-colors underline underline-offset-2"
            >
              Disconnect
            </button>
          </div>
        )}
      </div>

      {/* ── Content area ── */}
      {load.phase === "loading" && (
        <div className="flex items-center gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-canvas-raised)]/40 px-5 py-8">
          <Loader2
            className="h-5 w-5 animate-spin text-fg-muted"
            aria-hidden="true"
          />
          <span className="text-sm text-fg-muted">
            Fetching runtime status…
          </span>
        </div>
      )}

      {load.phase === "error" && (
        <div className="flex items-start gap-3 rounded-xl border border-[var(--color-danger)]/30 bg-[var(--color-danger)]/5 px-5 py-4">
          <AlertCircle
            className="mt-0.5 h-5 w-5 shrink-0 text-[var(--color-danger)]"
            aria-hidden="true"
          />
          <div className="space-y-1 min-w-0">
            <p className="text-sm font-medium text-[var(--color-danger)]">
              Connection failed
            </p>
            <p className="text-sm text-fg-muted">{load.message}</p>
          </div>
        </div>
      )}

      {load.phase === "ready" && (
        <StatusCard data={load.data} />
      )}

      {load.phase === "idle" && !isAuthenticated && (
        <AuthPrompt />
      )}

      {load.phase === "idle" && isAuthenticated && (
        <div className="flex items-center gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-canvas-raised)]/40 px-5 py-8">
          <AlertCircle
            className="h-5 w-5 text-fg-muted"
            aria-hidden="true"
          />
          <span className="text-sm text-fg-muted">
            Unable to connect. Check that the trader service is running.
          </span>
        </div>
      )}
    </div>
  );
}

/* ─────────────── Auth prompt (unauthenticated) ─────────────── */

function AuthPrompt() {
  return (
    <div className="flex flex-col items-center gap-4 rounded-2xl border border-dashed border-[var(--color-border)] bg-[var(--color-canvas-raised)]/30 px-6 py-12 text-center">
      <Lock className="h-8 w-8 text-fg-faint" aria-hidden="true" />
      <div className="space-y-1.5">
        <h2 className="text-lg font-semibold text-fg">
          Authentication required
        </h2>
        <p className="text-sm text-fg-muted max-w-sm">
          Enter your operator admin token above to view the runtime status.
          This page is read‑only — no mutations are possible here.
        </p>
      </div>
    </div>
  );
}

/* ─────────────── Status card (authenticated + loaded) ──────── */

function StatusCard({ data }: { data: RuntimeStatus }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Runtime Status</CardTitle>
        <Pill tone="info" emphasis="outline" size="xs">
          Read-only
        </Pill>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <StatusField
            label="Scheduler"
            value={
              data.scheduler_running ? (
                <Pill tone="good" emphasis="soft" size="xs">
                  Running
                </Pill>
              ) : (
                <Pill tone="neutral" emphasis="soft" size="xs">
                  Stopped
                </Pill>
              )
            }
          />
          <StatusField
            label="Interval"
            value={formatInterval(data.interval_minutes)}
          />
          <StatusField
            label="Auto-pipeline"
            value={
              <span className="text-sm text-fg-muted">
                {data.auto_pipeline_enabled ? "Enabled" : "Disabled"}
              </span>
            }
          />
          <StatusField
            label="Trade mode"
            value={
              <Pill
                tone={data.trade_mode === "live" ? "bad" : "info"}
                emphasis="soft"
                size="xs"
              >
                {data.trade_mode}
              </Pill>
            }
          />
          <StatusField
            label="Last tick"
            value={formatTimestamp(data.last_tick_timestamp)}
          />
          <StatusField
            label="Next tick"
            value={formatTimestamp(data.next_tick)}
          />
          <StatusField
            label="Last error"
            value={
              data.last_error ? (
                <span className="text-sm text-[var(--color-danger)]">
                  {data.last_error}
                </span>
              ) : (
                <span className="text-sm text-fg-faint">{formatTimestamp(null)}</span>
              )
            }
          />
          <StatusField
            label="Version"
            value={
              <span className="font-mono text-xs text-fg-muted">
                {data.service_version}
              </span>
            }
          />
        </dl>

        <Separator className="my-4" />

        <p className="text-[11px] text-fg-faint">
          This card is read-only. Use the{" "}
          <code className="rounded bg-[var(--color-canvas)] px-1 py-0.5 text-[10px]">
            OPERATOR_ADMIN_TOKEN
          </code>{" "}
          environment variable for authentication. Scheduler control and audit
          events are available in the next release.
        </p>
      </CardContent>
    </Card>
  );
}

/* ─────────────── Status field row ─────────────── */

function StatusField({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-canvas)]/50 px-3 py-2.5">
      <dt className="text-xs font-medium text-fg-muted">{label}</dt>
      <dd className="text-sm tabular-nums">{value}</dd>
    </div>
  );
}

/* ─────────────── Helpers ─────────────── */

function formatInterval(minutes: number): string {
  if (minutes < 1) return "< 1 min";
  if (minutes === 1) return "1 min";
  return `${minutes} min`;
}
