"use client";

/**
 * MeWalletPanel — client component that reads the connected wallet address
 * via wagmi useAccount() and renders verdict history.
 *
 * Disconnected state: CTA card prompting the visitor to connect their wallet.
 * Connected state: fetches /api/verdicts/by-address?address=<lower(address)>
 * and renders verdicts in the same card grid style as /history.
 * Empty-state message when no verdicts yet for that address.
 *
 * VAL-ME-002: CTA card when disconnected (not empty/undefined).
 * VAL-ME-003: Fetches with lower-cased address within 5 s of mount.
 * VAL-ME-004: Cards render in /history style OR empty state.
 * VAL-ME-005: Address lower-cased before query; displayed via <HashChip>.
 */

import Link from "next/link";
import { useAccount } from "wagmi";
import { useEffect, useState } from "react";
import { HashChip } from "@/components/ui/hash-chip";
import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScoreDonut } from "@/components/ui/score-donut";
import { Pill } from "@/components/ui/pill";
import { Separator } from "@/components/ui/separator";
import {
  Wallet,
  Clock,
  Loader2,
} from "lucide-react";
import { formatRelativeTime } from "@/lib/utils";
import type { HistoryEntry } from "@/lib/db";

/* ─────────────── Types ─────────────── */

type VerdictLabel = "REJECT" | "WARN" | "PASS" | "ENDORSE";

function verdictTone(
  label: string | null | undefined,
): "bad" | "warn" | "good" | "neutral" {
  if (!label) return "neutral";
  const map: Record<VerdictLabel, "bad" | "warn" | "good"> = {
    REJECT: "bad",
    WARN: "warn",
    PASS: "good",
    ENDORSE: "good",
  };
  return map[label as VerdictLabel] ?? "neutral";
}

function formatTimestamp(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZoneName: "short",
    });
  } catch {
    return iso;
  }
}

/* ─────────────── Panel ─────────────── */

export function MeWalletPanel() {
  const { address, isConnected } = useAccount();
  const [verdicts, setVerdicts] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isConnected || !address) {
      setVerdicts([]);
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;

    const lowerAddress = address.toLowerCase();

    setLoading(true);
    setError(null);

    fetch(`/api/verdicts/by-address?address=${lowerAddress}`)
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({ error: "Request failed" }));
          throw new Error(
            (body as { error?: string }).error ?? `HTTP ${res.status}`,
          );
        }
        return res.json() as Promise<HistoryEntry[]>;
      })
      .then((data) => {
        if (!cancelled) {
          setVerdicts(data);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Failed to fetch verdicts",
          );
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [isConnected, address]);

  // ── Disconnected state ──────────────────────────────────────────
  if (!isConnected) {
    return (
      <Card tone="verdict" className="mx-auto max-w-md">
        <CardContent className="flex flex-col items-center gap-4 py-10 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[var(--color-canvas-sunken)]">
            <Wallet className="h-6 w-6 text-fg-muted" strokeWidth={2} />
          </div>
          <h2 className="text-lg font-semibold text-fg">
            Connect to view your verdicts
          </h2>
          <p className="text-sm text-fg-faint">
            Connect your wallet to see the adversarial validation verdicts you
            requested. Your address is used to filter verdicts attributed to
            you.
          </p>
        </CardContent>
      </Card>
    );
  }

  // ── Connected state ──────────────────────────────────────────────
  // At this point isConnected is true and address is non-null (guarded above).
  const displayAddress = address as `0x${string}`;

  return (
    <div>
      {/* Wallet identity bar */}
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--color-canvas-sunken)]">
          <Wallet className="h-4 w-4 text-fg-muted" strokeWidth={2} />
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-xs text-fg-faint">Connected wallet</span>
          <HashChip
            value={displayAddress}
            truncate={8}
            size="sm"
          />
        </div>
      </div>

      <Separator className="mb-6" />

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center gap-2 py-14 text-fg-muted">
          <Loader2 className="h-5 w-5 animate-spin" strokeWidth={2} />
          <span className="text-sm">Loading your verdicts...</span>
        </div>
      )}

      {/* Error */}
      {!loading && error && (
        <Card tone="default" className="mx-auto max-w-md">
          <CardContent className="py-8 text-center">
            <p className="text-sm text-[var(--color-danger)]">
              {error}
            </p>
            <p className="mt-2 text-xs text-fg-faint">
              Try refreshing the page or reconnecting your wallet.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Verdicts grid (same style as /history) */}
      {!loading && !error && verdicts.length > 0 && (
        <>
          <div className="mb-5">
            <span className="text-mono text-xs text-fg-faint">
              {verdicts.length} verdict{verdicts.length !== 1 ? "s" : ""} for your wallet
            </span>
          </div>
          <div
            className="grid grid-cols-1 gap-4 md:grid-cols-2"
            data-testid="me-cards"
          >
            {verdicts.map((entry) => (
              <MeVerdictCard key={entry.trace_id} entry={entry} />
            ))}
          </div>
        </>
      )}

      {/* Empty state — connected but no verdicts yet */}
      {!loading && !error && verdicts.length === 0 && (
        <EmptyState
          title="No verdicts yet"
          description="You haven't requested any adversarial validations yet. Use the submit page to request a validation and it will appear here."
        />
      )}
    </div>
  );
}

/* ─────────────── Verdict Card (mirrors /history HistoryCard) ──── */

interface MeVerdictCardProps {
  entry: HistoryEntry;
}

function MeVerdictCard({ entry }: MeVerdictCardProps) {
  const tone = verdictTone(entry.verdict_label);
  const cardAccent =
    tone === "good"
      ? "var(--color-verdict-good)"
      : tone === "warn"
        ? "var(--color-warning)"
        : tone === "bad"
          ? "var(--color-danger)"
          : "var(--color-border)";

  return (
    <Link
      href={`/trace/${entry.trace_id}`}
      prefetch={false}
      className="group relative block overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-canvas-raised)]/65 backdrop-blur-sm shadow-[var(--shadow-soft)] transition-colors hover:border-[var(--color-border-strong)]"
      data-testid={`me-card-${entry.trace_id}`}
    >
      {/* Accent ring */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-px"
        style={{
          background: `linear-gradient(90deg, transparent 0%, ${cardAccent} 50%, transparent 100%)`,
          opacity: 0.7,
        }}
      />
      {/* Glow */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -right-20 -top-20 h-40 w-40 rounded-full blur-3xl"
        style={{
          backgroundColor: `color-mix(in oklch, ${cardAccent} 25%, transparent)`,
        }}
      />

      <div className="relative flex items-center gap-4 p-5">
        {/* ScoreDonut */}
        <div className="shrink-0">
          <ScoreDonut
            score={entry.verdict_score}
            label={entry.verdict_label ?? undefined}
            size="sm"
          />
        </div>

        {/* Content */}
        <div className="min-w-0 flex-1">
          {/* Market name */}
          <h3 className="truncate text-sm font-semibold text-fg group-hover:text-fg">
            {entry.market_name ?? entry.trace_id}
          </h3>

          {/* Meta row: side + verdict pill + timestamp */}
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {entry.side && (
              <Pill
                tone={entry.side === "BUY" ? "buy" : entry.side === "SELL" ? "sell" : "neutral"}
                emphasis="soft"
                size="xs"
              >
                {entry.side}
              </Pill>
            )}

            {entry.verdict_label && (
              <Pill
                tone={tone}
                emphasis="solid"
                size="xs"
              >
                {entry.verdict_label}
              </Pill>
            )}

            <span className="inline-flex items-center gap-1 text-mono text-[10px] text-fg-faint">
              <Clock className="h-3 w-3" strokeWidth={2} />
              {formatTimestamp(entry.created_at)}
            </span>
          </div>

          {/* Relative time hint */}
          <span className="mt-1 block text-mono text-[10px] text-fg-faint">
            {formatRelativeTime(entry.created_at)}
          </span>
        </div>
      </div>
    </Link>
  );
}
