/**
 * History Page — /history
 *
 * Server component listing all traces+verdicts as cards (most recent first,
 * paginated 20/page). Each card shows: market name, side, ScoreDonut,
 * verdict label, timestamp, link to /trace/[id].
 *
 * Uses URL search params (?page=N) for pagination — no client-side state.
 * Renders EmptyState when the traces table has no validated entries.
 */

import type { Metadata } from "next";
import Link from "next/link";
import { getHistoryEntries } from "@/lib/db";
import { ScoreDonut } from "@/components/ui/score-donut";
import { Pill } from "@/components/ui/pill";
import { EmptyState } from "@/components/ui/empty-state";
import { GlobalNav } from "@/components/global-nav";
import {
  ChevronLeft,
  ChevronRight,
  Clock,
} from "lucide-react";
import { formatRelativeTime } from "@/lib/utils";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "History",
  description:
    "All adversarial validation traces and verdicts on Prism, ordered by most recent.",
};

const PAGE_SIZE = 20;

/* ─────────────── Helpers ─────────────── */

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

/* ─────────────── Page ─────────────── */

interface HistoryPageProps {
  searchParams: Promise<{ page?: string }>;
}

export default async function HistoryPage({ searchParams }: HistoryPageProps) {
  const params = await searchParams;
  const currentPage = Math.max(1, Number(params.page ?? "1") || 1);

  const { entries, total } = await getHistoryEntries(currentPage, PAGE_SIZE);
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  // VAL-HISTORY-006: Empty state when no rows
  if (entries.length === 0) {
    return (
      <div className="min-h-screen bg-canvas text-fg">
        <GlobalNav currentPage="history" />
        <main className="mx-auto max-w-5xl px-6 pb-16 pt-8">
          <EmptyState
            title="No validated traces yet"
            description="Once the trader and sentinel produce traces with verdicts, they will appear here as a card grid."
          />
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-canvas text-fg">
      <GlobalNav currentPage="history" />

      <main className="mx-auto max-w-5xl px-6 pb-16 pt-8">
        {/* Results summary */}
        <div className="mb-5 flex items-center justify-between">
          <span className="text-mono text-xs text-fg-faint">
            {total} trace{total !== 1 ? "s" : ""} · page {currentPage} of {totalPages}
          </span>
        </div>

        {/* Card grid */}
        <div
          className="grid grid-cols-1 gap-4 md:grid-cols-2"
          data-testid="history-cards"
        >
          {entries.map((entry) => (
            <HistoryCard key={entry.trace_id} entry={entry} />
          ))}
        </div>

        {/* Pagination controls */}
        {totalPages > 1 && (
          <nav
            aria-label="History pagination"
            className="mt-8 flex items-center justify-center gap-2"
          >
            {currentPage > 1 ? (
              <PaginationLink
                href={`/history?page=${currentPage - 1}`}
                label="Previous"
                icon={<ChevronLeft className="h-4 w-4" strokeWidth={2} />}
              />
            ) : (
              <span className="inline-flex items-center gap-1 rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-sm text-fg-faint cursor-not-allowed opacity-40">
                <ChevronLeft className="h-4 w-4" strokeWidth={2} />
                Previous
              </span>
            )}

            <span className="text-mono text-xs text-fg-faint">
              {currentPage} / {totalPages}
            </span>

            {currentPage < totalPages ? (
              <PaginationLink
                href={`/history?page=${currentPage + 1}`}
                label="Next"
                icon={<ChevronRight className="h-4 w-4" strokeWidth={2} />}
              />
            ) : (
              <span className="inline-flex items-center gap-1 rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-sm text-fg-faint cursor-not-allowed opacity-40">
                Next
                <ChevronRight className="h-4 w-4" strokeWidth={2} />
              </span>
            )}
          </nav>
        )}
      </main>
    </div>
  );
}

/* ─────────────── History Card ─────────────── */

interface HistoryCardProps {
  entry: {
    trace_id: string;
    market_name: string | null;
    side: string | null;
    verdict_score: number;
    verdict_label: string | null;
    created_at: string;
    ipfs_cid: string | null;
  };
}

function HistoryCard({ entry }: HistoryCardProps) {
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
      data-testid={`history-card-${entry.trace_id}`}
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

/* ─────────────── Pagination link ─────────────── */

function PaginationLink({
  href,
  label,
  icon,
}: {
  href: string;
  label: string;
  icon: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      prefetch
      className="inline-flex items-center gap-1 rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-sm font-medium text-fg-muted transition-colors hover:border-[var(--color-border-strong)] hover:text-fg focus-ring"
    >
      {icon}
      {label}
    </Link>
  );
}
