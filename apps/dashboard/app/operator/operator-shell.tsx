"use client";

/**
 * OperatorShell — client‑side auth + status display + mutation controls for /operator.
 *
 * Renders a password input for the OPERATOR_ADMIN_TOKEN.  Once a valid token
 * is provided the component fetches the trader's 8‑field runtime status via
 * GET /api/admin/runtime and displays it as a read‑only status card.
 *
 * Adds mutation controls (Start/Stop) with shadcn/ui Dialog confirmation,
 * an audit events table, inline mutation errors, and auto‑refresh polling.
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
import { Dialog } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import {
  Lock,
  Eye,
  EyeOff,
  Loader2,
  AlertCircle,
  Play,
  Square,
  RefreshCw,
  History,
  XCircle,
  CheckCircle2,
  ShieldAlert,
} from "lucide-react";

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

interface AuditEvent {
  id: string;
  actor: string;
  action: string;
  old_state: Record<string, unknown> | null;
  new_state: Record<string, unknown> | null;
  timestamp: string;
  result: "success" | "failure" | "unauthorized";
  error: string | null;
}

const SESSION_KEY = "prism:operator:token";

/** Auto‑refresh status every 30 seconds (GET only, never triggers mutations). */
const REFRESH_INTERVAL_MS = 30_000;

/* ─────────────── Helpers ─────────────── */

function formatTimestamp(iso: string | null): string {
  if (!iso) return "\u2014";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function formatInterval(minutes: number): string {
  if (minutes < 1) return "< 1 min";
  if (minutes === 1) return "1 min";
  return `${minutes} min`;
}

function formatAuditTimestamp(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

function formatAuditAction(action: string): string {
  switch (action) {
    case "start_scheduler":
      return "Start Scheduler";
    case "stop_scheduler":
      return "Stop Scheduler";
    case "update_interval":
      return "Update Interval";
    default:
      return action;
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

type MutationState =
  | { phase: "idle" }
  | { phase: "loading" }
  | { phase: "error"; message: string };

type DialogAction = "start" | "stop" | null;

/* ─────────────── Component ─────────────── */

export function OperatorShell() {
  const [token, setToken] = useState<TokenState>({ phase: "absent" });
  const [inputValue, setInputValue] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [load, setLoad] = useState<LoadState>({ phase: "idle" });
  const inputRef = useRef<HTMLInputElement>(null);
  const mountedRef = useRef(false);

  // Mutation state
  const [dialogAction, setDialogAction] = useState<DialogAction>(null);
  const [mutation, setMutation] = useState<MutationState>({ phase: "idle" });

  // Audit events
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);

  // Auto‑refresh timer ref
  const refreshTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

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

  /* ── Fetch audit events ── */
  const fetchAuditEvents = useCallback(
    async (tokenValue: string) => {
      setAuditLoading(true);
      try {
        const res = await fetch("/api/admin/audit?limit=50", {
          headers: { Authorization: `Bearer ${tokenValue}` },
          cache: "no-store",
        });
        if (res.ok) {
          const body = await res.json();
          setAuditEvents((body.events as AuditEvent[]) ?? []);
        }
      } catch {
        /* Swallow — audit table degrades gracefully */
      } finally {
        setAuditLoading(false);
      }
    },
    [],
  );

  /* ── Auto‑fetch on stored token ── */
  useEffect(() => {
    if (token.phase === "stored" || token.phase === "entered") {
      const tokenValue =
        token.phase === "stored" ? token.value : token.value;
      fetchStatus(tokenValue);
      fetchAuditEvents(tokenValue);
    }
  }, [token, fetchStatus, fetchAuditEvents]);

  /* ── Auto‑refresh polling (GET only, never triggers mutations) ── */
  useEffect(() => {
    const isAuth =
      token.phase === "stored" || token.phase === "entered";
    if (!isAuth) return;

    const tokenValue =
      token.phase === "stored" ? token.value : token.value;

    // Clear any existing timer
    if (refreshTimerRef.current) {
      clearInterval(refreshTimerRef.current);
    }

    refreshTimerRef.current = setInterval(() => {
      fetchStatus(tokenValue);
      fetchAuditEvents(tokenValue);
    }, REFRESH_INTERVAL_MS);

    return () => {
      if (refreshTimerRef.current) {
        clearInterval(refreshTimerRef.current);
        refreshTimerRef.current = null;
      }
    };
  }, [token, fetchStatus, fetchAuditEvents]);

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
    fetchAuditEvents(trimmed);
  }, [inputValue, fetchStatus, fetchAuditEvents]);

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
    setAuditEvents([]);
    setMutation({ phase: "idle" });
    if (refreshTimerRef.current) {
      clearInterval(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
  }, []);

  /* ── Mutation: open confirmation dialog ── */
  const handleOpenDialog = useCallback((action: "start" | "stop") => {
    setDialogAction(action);
    setMutation({ phase: "idle" });
  }, []);

  /* ── Mutation: close dialog without action ── */
  const handleCancelDialog = useCallback(() => {
    setDialogAction(null);
  }, []);

  /* ── Mutation: confirm and send POST ── */
  const handleConfirmMutation = useCallback(async () => {
    if (!dialogAction) return;

    const tokenValue =
      token.phase === "stored" || token.phase === "entered"
        ? (token.phase === "stored" ? token.value : token.value)
        : null;
    if (!tokenValue) return;

    const endpoint =
      dialogAction === "start"
        ? "/api/admin/schedule/start"
        : "/api/admin/schedule/stop";

    setMutation({ phase: "loading" });

    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${tokenValue}`,
          "Content-Type": "application/json",
        },
        cache: "no-store",
      });

      if (res.ok) {
        // Close dialog
        setDialogAction(null);
        setMutation({ phase: "idle" });
        // Refresh status and audit events
        await fetchStatus(tokenValue);
        await fetchAuditEvents(tokenValue);
      } else {
        const body = await res.json().catch(() => ({}));
        setMutation({
          phase: "error",
          message:
            body.error === "operator_admin_required"
              ? "Authentication failed. Please reconnect."
              : body.error === "trader_unreachable"
                ? "Trader is unreachable. Check that the service is running."
                : `Request failed (${res.status}). Try again.`,
        });
      }
    } catch {
      setMutation({
        phase: "error",
        message:
          "Network error. Check that the dashboard and trader services are running.",
      });
    }
  }, [
    dialogAction,
    token,
    fetchStatus,
    fetchAuditEvents,
  ]);

  const isAuthenticated =
    token.phase === "stored" || token.phase === "entered";

  /* ── Derive UI state ── */
  const schedulerRunning =
    load.phase === "ready" ? load.data.scheduler_running : false;
  const tradeMode =
    load.phase === "ready" ? load.data.trade_mode : "paper";

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
            {load.phase === "ready" && (
              <Pill tone="info" emphasis="outline" size="xs">
                <RefreshCw className="h-3 w-3" aria-hidden="true" />
                Auto-refresh {REFRESH_INTERVAL_MS / 1000}s
              </Pill>
            )}
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
        <>
          {/* ── Status card ── */}
          <StatusCard
            data={load.data}
            schedulerRunning={schedulerRunning}
            onStart={() => handleOpenDialog("start")}
            onStop={() => handleOpenDialog("stop")}
            mutation={mutation}
          />

          {/* ── Mutation error ── */}
          {mutation.phase === "error" && (
            <div className="flex items-start gap-3 rounded-xl border border-[var(--color-danger)]/30 bg-[var(--color-danger)]/5 px-5 py-4 animate-in fade-in slide-in-from-top-2">
              <XCircle
                className="mt-0.5 h-5 w-5 shrink-0 text-[var(--color-danger)]"
                aria-hidden="true"
              />
              <div className="space-y-1 min-w-0">
                <p className="text-sm font-medium text-[var(--color-danger)]">
                  Mutation failed
                </p>
                <p className="text-sm text-fg-muted">{mutation.message}</p>
              </div>
              <button
                type="button"
                onClick={() => setMutation({ phase: "idle" })}
                className="ml-auto shrink-0 p-1 text-fg-faint hover:text-fg-muted transition-colors"
                aria-label="Dismiss error"
              >
                <XCircle className="h-4 w-4" />
              </button>
            </div>
          )}

          {/* ── Audit events table ── */}
          <AuditEventsTable
            events={auditEvents}
            loading={auditLoading}
          />
        </>
      )}

      {load.phase === "idle" && !isAuthenticated && <AuthPrompt />}

      {load.phase === "idle" && isAuthenticated && (
        <div className="flex items-center gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-canvas-raised)]/40 px-5 py-8">
          <AlertCircle className="h-5 w-5 text-fg-muted" aria-hidden="true" />
          <span className="text-sm text-fg-muted">
            Unable to connect. Check that the trader service is running.
          </span>
        </div>
      )}

      {/* ── Confirmation Dialog ── */}
      <Dialog
        open={dialogAction !== null}
        onClose={handleCancelDialog}
        title={
          dialogAction === "start"
            ? "Start Scheduler"
            : "Stop Scheduler"
        }
        maxWidthClass="max-w-md"
      >
        <div className="px-5 py-4 space-y-4">
          {/* Current state context */}
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-canvas)]/50 px-3 py-2.5 space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-fg-muted">Current state</span>
              <Pill
                tone={schedulerRunning ? "good" : "neutral"}
                emphasis="soft"
                size="xs"
              >
                {schedulerRunning ? "Running" : "Stopped"}
              </Pill>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-fg-muted">Trade mode</span>
              <Pill
                tone={tradeMode === "live" ? "bad" : "info"}
                emphasis="soft"
                size="xs"
              >
                {tradeMode}
              </Pill>
            </div>
          </div>

          {/* Warning message */}
          <p className="text-sm text-fg-muted leading-relaxed">
            {dialogAction === "start"
              ? "This will start the automated trading pipeline. The scheduler will begin generating traces at the configured interval. Trade mode will NOT change — it remains as shown above."
              : "This will stop the automated trading pipeline. No further traces will be generated until the scheduler is restarted. Any in-progress tick will complete."}
          </p>

          {/* Inline error within dialog */}
          {mutation.phase === "error" && (
            <div className="flex items-start gap-2 rounded-lg border border-[var(--color-danger)]/30 bg-[var(--color-danger)]/5 px-3 py-2.5">
              <AlertCircle
                className="mt-0.5 h-4 w-4 shrink-0 text-[var(--color-danger)]"
                aria-hidden="true"
              />
              <p className="text-xs text-[var(--color-danger)]">
                {mutation.message}
              </p>
            </div>
          )}

          {/* Action buttons */}
          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={handleCancelDialog}
              disabled={mutation.phase === "loading"}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-canvas-raised)] px-4 py-2 text-sm font-medium text-fg-muted transition-colors hover:border-[var(--color-border-strong)] hover:text-fg disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleConfirmMutation}
              disabled={mutation.phase === "loading"}
              className={cn(
                "inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed",
                dialogAction === "start"
                  ? "border border-[var(--color-success)]/40 bg-[var(--color-success)]/10 text-[var(--color-success)] hover:bg-[var(--color-success)]/20"
                  : "border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 text-[var(--color-danger)] hover:bg-[var(--color-danger)]/20",
              )}
            >
              {mutation.phase === "loading" ? (
                <Loader2
                  className="h-4 w-4 animate-spin"
                  aria-hidden="true"
                />
              ) : dialogAction === "start" ? (
                <Play className="h-4 w-4" aria-hidden="true" />
              ) : (
                <Square className="h-4 w-4" aria-hidden="true" />
              )}
              {mutation.phase === "loading"
                ? (dialogAction === "start" ? "Starting…" : "Stopping…")
                : "Confirm"}
            </button>
          </div>
        </div>
      </Dialog>
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

function StatusCard({
  data,
  schedulerRunning,
  onStart,
  onStop,
  mutation,
}: {
  data: RuntimeStatus;
  schedulerRunning: boolean;
  onStart: () => void;
  onStop: () => void;
  mutation: MutationState;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2 flex-wrap">
          <CardTitle>Runtime Status</CardTitle>
          <Pill tone="info" emphasis="outline" size="xs">
            Read-only
          </Pill>
        </div>
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
                <span className="text-sm text-fg-faint">
                  {formatTimestamp(null)}
                </span>
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

        {/* ── Mutation controls ── */}
        <div className="flex flex-wrap items-center gap-3">
          {schedulerRunning ? (
            <button
              type="button"
              onClick={onStop}
              disabled={mutation.phase === "loading"}
              className="inline-flex items-center gap-2 rounded-lg border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 px-4 py-2 text-sm font-medium text-[var(--color-danger)] transition-colors hover:bg-[var(--color-danger)]/20 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {mutation.phase === "loading" ? (
                <Loader2
                  className="h-4 w-4 animate-spin"
                  aria-hidden="true"
                />
              ) : (
                <Square className="h-4 w-4" aria-hidden="true" />
              )}
              Stop Scheduler
            </button>
          ) : (
            <button
              type="button"
              onClick={onStart}
              disabled={mutation.phase === "loading"}
              className="inline-flex items-center gap-2 rounded-lg border border-[var(--color-success)]/40 bg-[var(--color-success)]/10 px-4 py-2 text-sm font-medium text-[var(--color-success)] transition-colors hover:bg-[var(--color-success)]/20 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {mutation.phase === "loading" ? (
                <Loader2
                  className="h-4 w-4 animate-spin"
                  aria-hidden="true"
                />
              ) : (
                <Play className="h-4 w-4" aria-hidden="true" />
              )}
              Start Scheduler
            </button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

/* ─────────────── Audit events table ─────────────── */

function AuditEventsTable({
  events,
  loading,
}: {
  events: AuditEvent[];
  loading: boolean;
}) {
  if (loading && events.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <History className="h-4 w-4 text-fg-muted" aria-hidden="true" />
            Audit Events
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-3 py-4">
            <Loader2
              className="h-4 w-4 animate-spin text-fg-muted"
              aria-hidden="true"
            />
            <span className="text-sm text-fg-muted">
              Loading audit events…
            </span>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (events.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <History className="h-4 w-4 text-fg-muted" aria-hidden="true" />
            Audit Events
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center gap-2 py-6 text-center">
            <History
              className="h-8 w-8 text-fg-faint"
              strokeWidth={1.5}
              aria-hidden="true"
            />
            <p className="text-sm text-fg-muted">No audit events yet</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <History className="h-4 w-4 text-fg-muted" aria-hidden="true" />
          Audit Events
        </CardTitle>
        <Pill tone="neutral" emphasis="outline" size="xs">
          {events.length} event{events.length !== 1 ? "s" : ""}
        </Pill>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--color-border)]">
                <th className="whitespace-nowrap py-2.5 pr-4 text-left text-xs font-medium text-fg-muted">
                  Timestamp
                </th>
                <th className="whitespace-nowrap py-2.5 pr-4 text-left text-xs font-medium text-fg-muted">
                  Actor
                </th>
                <th className="whitespace-nowrap py-2.5 pr-4 text-left text-xs font-medium text-fg-muted">
                  Action
                </th>
                <th className="whitespace-nowrap py-2.5 pr-4 text-left text-xs font-medium text-fg-muted">
                  Result
                </th>
                <th className="whitespace-nowrap py-2.5 text-left text-xs font-medium text-fg-muted">
                  Error
                </th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr
                  key={event.id}
                  className="border-b border-[var(--color-border)]/50 last:border-0"
                >
                  <td className="whitespace-nowrap py-2.5 pr-4 text-xs tabular-nums text-fg-muted">
                    {formatAuditTimestamp(event.timestamp)}
                  </td>
                  <td className="whitespace-nowrap py-2.5 pr-4 text-xs text-fg">
                    {event.actor}
                  </td>
                  <td className="whitespace-nowrap py-2.5 pr-4 text-xs text-fg">
                    {formatAuditAction(event.action)}
                  </td>
                  <td className="whitespace-nowrap py-2.5 pr-4">
                    <AuditResultPill result={event.result} />
                  </td>
                  <td className="py-2.5 text-xs text-fg-muted min-w-[120px] max-w-[200px]">
                    {event.error ? (
                      <span className="text-[var(--color-danger)] line-clamp-2">
                        {event.error}
                      </span>
                    ) : (
                      <span className="text-fg-faint">\u2014</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function AuditResultPill({ result }: { result: string }) {
  switch (result) {
    case "success":
      return (
        <span className="inline-flex items-center gap-1 text-xs text-[var(--color-success)]">
          <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
          Success
        </span>
      );
    case "failure":
      return (
        <span className="inline-flex items-center gap-1 text-xs text-[var(--color-danger)]">
          <XCircle className="h-3 w-3" aria-hidden="true" />
          Failed
        </span>
      );
    case "unauthorized":
      return (
        <span className="inline-flex items-center gap-1 text-xs text-[var(--color-warning)]">
          <ShieldAlert className="h-3 w-3" aria-hidden="true" />
          Unauthorized
        </span>
      );
    default:
      return <span className="text-xs text-fg-muted">{result}</span>;
  }
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
