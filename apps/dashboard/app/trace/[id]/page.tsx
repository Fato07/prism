/**
 * Trace Detail Page — /trace/[id]
 *
 * Server component that fetches a single trace + its sentinel verdict +
 * on-chain hashes + IPFS CIDs from Neon by `trace_id` UUID.
 *
 * Layout:
 *   Header          (market name, side, timestamp, ScoreDonut, verdict pill,
 *                    agent attribution chips)
 *   Workspace       (Trader column + Sentinel column, 2-col grid)
 *   Dialogue        (AdversarialDialogue — only when dialogue messages exist)
 *   Receipts strip  (IPFS link, trader on-chain tx, sentinel on-chain tx,
 *                    builder code, Polymarket order ID)
 *   Trade outcome   (size + fill price pill — only when trade filled)
 *
 * Returns Next.js 404 (notFound) for unknown or malformed UUIDs.
 * No `'use client'` on this page — interactive sub-components are client leaves.
 */

import type { Metadata } from "next";
import { notFound } from "next/navigation";
import {
  getTraceDetailData,
  type TraceDetailData,
} from "@/lib/db";
import { ScoreDonut } from "@/components/ui/score-donut";
import { Pill } from "@/components/ui/pill";
import { ConfidenceBar } from "@/components/ui/confidence-bar";
import { HashChip } from "@/components/ui/hash-chip";
import { Separator } from "@/components/ui/separator";
import { TraderPanel } from "@/components/trader-panel";
import { SentinelPanel } from "@/components/sentinel-panel";
import { AdversarialDialogue } from "@/components/dashboard/adversarial-dialogue";
import { TraceDetailProvider } from "@/components/trace-detail-provider";
import {
  ArrowLeft,
  ExternalLink,
  FileCode,
  ShieldAlert,
  Hexagon,
  Zap,
  Clock,
  Activity,
} from "lucide-react";
import type { TradingR1Trace, SentinelVerdict } from "@/lib/schemas";
import { ConnectWalletButton } from "@/components/connect-wallet-button";

/* ─────────────── UUID validation ─────────────── */

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function isValidUUID(id: string): boolean {
  return UUID_RE.test(id);
}

/* ─────────────── Constants ─────────────── */

const ARC_EXPLORER = "https://testnet.arcscan.app";
const IPFS_GATEWAY = process.env.IPFS_GATEWAY || "https://gateway.pinata.cloud/ipfs";

/* ─────────────── Helpers ─────────────── */

type VerdictLabel = "REJECT" | "WARN" | "PASS" | "ENDORSE";

function verdictTone(
  label: string | undefined | null,
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

function modelFamilyLabel(
  family: string | undefined | null,
): { label: string; tone: "trader" | "sentinel" } {
  if (!family) return { label: "Unknown", tone: "neutral" as never };
  const lower = family.toLowerCase();
  if (lower.includes("claude") || lower.includes("anthropic"))
    return { label: "Claude", tone: "trader" };
  if (lower.includes("gpt") || lower.includes("openai"))
    return { label: "GPT", tone: "sentinel" };
  return { label: family, tone: "neutral" as never };
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

/* ─────────────── Metadata ─────────────── */

interface PageProps {
  params: Promise<{ id: string }>;
}

export async function generateMetadata({
  params,
}: PageProps): Promise<Metadata> {
  const { id } = await params;

  if (!isValidUUID(id)) {
    return { title: "Trace not found" };
  }

  const data = await getTraceDetailData(id);
  if (!data) {
    return { title: "Trace not found" };
  }

  const traceContent = data.traceContent as TradingR1Trace | null;
  const verdictContent = data.verdictContent as SentinelVerdict | null;

  const marketName =
    traceContent?.market_question ?? data.trace.market_id;
  const score = data.validation?.verdict_score;
  const label = verdictContent?.verdict_label;

  const title = score !== null && score !== undefined
    ? `${marketName} — verdict ${score}/100 ${label ?? ""}`
    : `${marketName} — Prism trace`;

  return {
    title,
    description: `Adversarial validation of "${marketName}" on Prism — the first adversarial AI validator on ERC-8004.`,
    openGraph: {
      title,
      description: `Verdict: ${score ?? "pending"}/100 ${label ?? ""}. ${marketName}`,
      type: "article",
      images: [
        {
          url: `/trace/${id}/opengraph-image`,
          width: 1200,
          height: 630,
          alt: title,
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description: `Verdict: ${score ?? "pending"}/100 ${label ?? ""}`,
      images: [`/trace/${id}/opengraph-image`],
    },
  };
}

/* ─────────────── Page ─────────────── */

export const dynamic = "force-dynamic";

export default async function TraceDetailPage({ params }: PageProps) {
  const { id } = await params;

  // VAL-TRACE-018: malformed UUID returns 404
  if (!isValidUUID(id)) {
    notFound();
  }

  const data = await getTraceDetailData(id);

  // VAL-TRACE-017: unknown UUID returns 404
  if (!data) {
    notFound();
  }

  const { trace, validation, trade, traderAgent, sentinelAgent } = data;
  const traceContent = data.traceContent as TradingR1Trace | null;
  const verdictContent = data.verdictContent as SentinelVerdict | null;

  const marketName =
    traceContent?.market_question ?? trace.market_id;
  const side = traceContent?.action ?? null;
  const score = validation?.verdict_score ?? null;
  const verdictLabel = verdictContent?.verdict_label ?? null;
  const dialogueMessages = verdictContent?.dialogue_messages ?? [];

  const traderModel = modelFamilyLabel(traceContent?.model_family);
  const sentinelModel = modelFamilyLabel(verdictContent?.model_family);

  const verdictCid = validation?.response_uri?.startsWith("ipfs://")
    ? validation.response_uri.slice(7)
    : null;

  return (
    <div className="min-h-screen bg-canvas text-fg">
      {/* ── Header ── */}
      <header className="sticky top-0 z-40 border-b border-[var(--color-border)] bg-[var(--color-canvas)]/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-4 gap-y-3 px-6 py-4">
          <ConnectWalletButton />
          <a
            href="/dashboard"
            className="inline-flex items-center gap-1.5 text-sm text-fg-muted transition-colors hover:text-fg"
          >
            <ArrowLeft className="h-4 w-4" strokeWidth={2} />
            Dashboard
          </a>
          <Separator orientation="vertical" className="h-4" />
          <a
            href="/history"
            className="inline-flex items-center gap-1 text-sm text-fg-muted transition-colors hover:text-fg"
          >
            History
          </a>
          <Separator orientation="vertical" className="h-4" />

          {/* Market name */}
          <h1 className="max-w-lg truncate text-base font-semibold tracking-[var(--tracking-tight)] text-fg">
            {marketName}
          </h1>

          {/* Side pill */}
          {side && (
            <Pill
              tone={side === "BUY" ? "buy" : side === "SELL" ? "sell" : "neutral"}
              emphasis="soft"
              size="sm"
            >
              {side}
            </Pill>
          )}

          {/* Timestamp */}
          <span className="inline-flex items-center gap-1.5 text-mono text-xs text-fg-muted">
            <Clock className="h-3 w-3" strokeWidth={2} />
            {formatTimestamp(trace.created_at)}
          </span>

          <div className="ml-auto flex flex-wrap items-center gap-3">
            {/* Score donut */}
            {score !== null && (
              <ScoreDonut score={score} label={verdictLabel ?? undefined} size="sm" />
            )}

            {/* Verdict pill */}
            {verdictLabel && (
              <Pill
                tone={verdictTone(verdictLabel)}
                emphasis="solid"
                size="md"
              >
                {verdictLabel}
              </Pill>
            )}

            {/* Agent attribution chips */}
            <div className="flex items-center gap-1.5">
              <Pill tone={traderModel.tone} emphasis="outline" size="xs">
                <span className="text-mono">{traderModel.label}</span>
              </Pill>
              <span className="text-fg-faint">vs</span>
              <Pill tone={sentinelModel.tone} emphasis="outline" size="xs">
                <span className="text-mono">{sentinelModel.label}</span>
              </Pill>
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 pb-16 pt-8">
        {/* ── Workspace: Trader + Sentinel columns ── */}
        <section aria-label="Trace workspace">
          <div className="mb-5 flex items-center gap-3">
            <span
              className="h-px w-8 shrink-0"
              style={{
                background:
                  "linear-gradient(90deg, transparent, var(--color-trader), var(--color-sentinel))",
                opacity: 0.7,
              }}
              aria-hidden="true"
            />
            <span className="text-mono text-[11px] font-medium uppercase tracking-[var(--tracking-wide)] text-fg-muted">
              Reasoning trace
            </span>
            <span
              className="ml-2 h-px flex-1"
              style={{
                background:
                  "linear-gradient(90deg, var(--color-border), transparent)",
                opacity: 0.6,
              }}
              aria-hidden="true"
            />
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <TraderPanel
              trace={traceContent}
              ipfsCid={trace.ipfs_cid}
              contentHash={trace.content_hash}
              noExpand
            />
            <SentinelPanel
              verdict={verdictContent}
              responseUri={validation?.response_uri ?? null}
              noExpand
            />
          </div>
        </section>

        {/* ── Adversarial Dialogue ── */}
        {dialogueMessages.length > 0 && (
          <section aria-label="Adversarial dialogue" className="mt-8">
            <div className="mb-5 flex items-center gap-3">
              <span
                className="h-px w-8 shrink-0"
                style={{
                  background:
                    "linear-gradient(90deg, transparent, var(--color-trader), var(--color-sentinel))",
                  opacity: 0.7,
                }}
                aria-hidden="true"
              />
              <span className="text-mono text-[11px] font-medium uppercase tracking-[var(--tracking-wide)] text-fg-muted">
                Adversarial dialogue
              </span>
              <span
                className="ml-2 h-px flex-1"
                style={{
                  background:
                    "linear-gradient(90deg, var(--color-border), transparent)",
                  opacity: 0.6,
                }}
                aria-hidden="true"
              />
            </div>
            <TraceDetailProvider>
              <AdversarialDialogue
                messages={dialogueMessages}
                verdictScore={score}
                verdictLabel={verdictLabel}
                traderModel={traceContent?.model_name ?? null}
                sentinelModel={verdictContent?.model_name ?? null}
              />
            </TraceDetailProvider>
          </section>
        )}

        {/* ── Receipts strip ── */}
        <section aria-label="Receipts" className="mt-14">
          <div className="mb-5 flex items-center gap-3">
            <span
              className="h-px w-8 shrink-0"
              style={{
                background:
                  "linear-gradient(90deg, transparent, var(--color-verdict-good))",
                opacity: 0.7,
              }}
              aria-hidden="true"
            />
            <span className="text-mono text-[11px] font-medium uppercase tracking-[var(--tracking-wide)] text-fg-muted">
              On-chain receipts
            </span>
            <span
              className="ml-2 h-px flex-1"
              style={{
                background:
                  "linear-gradient(90deg, var(--color-border), transparent)",
                opacity: 0.6,
              }}
              aria-hidden="true"
            />
          </div>

          <div className="overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-canvas-raised)]/65 backdrop-blur-sm">
            <div className="divide-y divide-[var(--color-border)]">
              {/* IPFS CID link */}
              {trace.ipfs_cid && (
                <ReceiptRow
                  icon={<FileCode className="h-4 w-4 text-[var(--color-trader)]" strokeWidth={1.8} />}
                  label="Trace IPFS"
                  sublabel="Pinned on IPFS"
                >
                  <HashChip
                    label="IPFS"
                    value={trace.ipfs_cid}
                    href={`${IPFS_GATEWAY}/${trace.ipfs_cid}`}
                    truncate={8}
                    size="sm"
                  />
                </ReceiptRow>
              )}

              {/* Verdict IPFS CID link */}
              {verdictCid && (
                <ReceiptRow
                  icon={<ShieldAlert className="h-4 w-4 text-[var(--color-sentinel)]" strokeWidth={1.8} />}
                  label="Verdict IPFS"
                  sublabel="Pinned on IPFS"
                >
                  <HashChip
                    label="IPFS"
                    value={verdictCid}
                    href={`${IPFS_GATEWAY}/${verdictCid}`}
                    truncate={8}
                    size="sm"
                  />
                </ReceiptRow>
              )}

              {/* Trader on-chain tx (validationRequest) */}
              <ReceiptRow
                icon={<FileCode className="h-4 w-4 text-[var(--color-trader)]" strokeWidth={1.8} />}
                label="Validation request"
                sublabel="ValidationRegistry · ERC-8004"
              >
                {trace.tx_hash ? (
                  <HashChip
                    value={trace.tx_hash}
                    href={`${ARC_EXPLORER}/tx/${trace.tx_hash}`}
                    truncate={6}
                    size="sm"
                  />
                ) : (
                  <Pill tone="warn" emphasis="outline" size="xs">
                    pending
                  </Pill>
                )}
              </ReceiptRow>

              {/* Sentinel on-chain tx (validationResponse) */}
              <ReceiptRow
                icon={<ShieldAlert className="h-4 w-4 text-[var(--color-sentinel)]" strokeWidth={1.8} />}
                label="Validation response"
                sublabel="ValidationRegistry · ERC-8004"
              >
                {validation?.tx_hash ? (
                  <HashChip
                    value={validation.tx_hash}
                    href={`${ARC_EXPLORER}/tx/${validation.tx_hash}`}
                    truncate={6}
                    size="sm"
                  />
                ) : (
                  <Pill tone="warn" emphasis="outline" size="xs">
                    pending
                  </Pill>
                )}
              </ReceiptRow>

              {/* Builder code (when trade exists) */}
              {trade && (
                <ReceiptRow
                  icon={<Zap className="h-4 w-4 text-[var(--color-trader)]" strokeWidth={1.8} />}
                  label="Builder code"
                  sublabel="Polymarket HMAC attribution"
                >
                  <HashChip
                    value={trade.builder_code}
                    truncate={10}
                    size="sm"
                  />
                </ReceiptRow>
              )}

              {/* Polymarket order ID (when trade exists) */}
              {trade && (
                <ReceiptRow
                  icon={<Activity className="h-4 w-4 text-[var(--color-info)]" strokeWidth={1.8} />}
                  label="Polymarket order"
                  sublabel={trade.market_id}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-mono text-xs text-fg-muted">{trade.order_id}</span>
                    <Pill
                      tone={
                        trade.status === "filled" || trade.status === "paper_filled"
                          ? "good"
                          : trade.status === "open"
                            ? "warn"
                            : "neutral"
                      }
                      emphasis="outline"
                      size="xs"
                    >
                      <span className="text-mono">{trade.status}</span>
                    </Pill>
                    {trade.polymarket_tx && (
                      <HashChip
                        value={trade.polymarket_tx}
                        href={`${ARC_EXPLORER}/tx/${trade.polymarket_tx}`}
                        truncate={6}
                        size="xs"
                      />
                    )}
                  </div>
                </ReceiptRow>
              )}
            </div>
          </div>
        </section>

        {/* ── Trade outcome pill ── */}
        {trade &&
          (trade.status === "filled" || trade.status === "paper_filled") && (
            <section aria-label="Trade outcome" className="mt-6">
              <div className="inline-flex items-center gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-canvas-raised)]/65 backdrop-blur-sm px-5 py-3">
                <Zap
                  className="h-4 w-4 text-[var(--color-verdict-good)]"
                  strokeWidth={1.8}
                />
                <span className="text-mono text-xs font-medium uppercase tracking-[var(--tracking-wide)] text-fg-faint">
                  Trade outcome
                </span>
                <Separator orientation="vertical" className="h-4" />
                <div className="flex items-center gap-4 text-sm">
                  <div>
                    <span className="text-fg-faint">Size </span>
                    <span className="text-mono font-medium text-fg">
                      {trade.size} USDC
                    </span>
                  </div>
                  <div>
                    <span className="text-fg-faint">Side </span>
                    <Pill
                      tone={trade.side === "BUY" ? "buy" : "sell"}
                      emphasis="soft"
                      size="xs"
                    >
                      {trade.side}
                    </Pill>
                  </div>
                  {trade.fill_price && (
                    <div>
                      <span className="text-fg-faint">Fill price </span>
                      <span className="text-mono font-medium text-fg">
                        {trade.fill_price}
                      </span>
                    </div>
                  )}
                  <div>
                    <span className="text-fg-faint">Status </span>
                    <Pill tone="good" emphasis="soft" size="xs">
                      <span className="text-mono">{trade.status}</span>
                    </Pill>
                  </div>
                </div>
              </div>
            </section>
          )}
      </main>

      {/* ── Footer ── */}
      <footer className="border-t border-[var(--color-border)] px-6 py-5">
        <div className="mx-auto flex max-w-7xl flex-col items-start gap-2 text-mono text-[11px] text-fg-faint sm:flex-row sm:items-center sm:justify-between">
          <span>The first adversarial AI validator on ERC-8004</span>
          <div className="flex items-center gap-3">
            <a
              href={`${ARC_EXPLORER}`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-fg-muted transition-colors hover:text-fg"
            >
              Arc Testnet
              <ExternalLink className="h-3 w-3" strokeWidth={2} />
            </a>
            <a
              href="/dashboard"
              className="text-fg-muted transition-colors hover:text-fg"
            >
              Dashboard
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}

/* ─────────────── Receipt row helper ─────────────── */

function ReceiptRow({
  icon,
  label,
  sublabel,
  children,
}: {
  icon: React.ReactNode;
  label: string;
  sublabel?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-4 px-5 py-3.5">
      <div className="flex min-w-0 items-center gap-3">
        <span className="shrink-0">{icon}</span>
        <div className="min-w-0">
          <div className="text-sm font-medium text-fg">{label}</div>
          {sublabel && (
            <div className="text-mono text-[10px] text-fg-faint">
              {sublabel}
            </div>
          )}
        </div>
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}
