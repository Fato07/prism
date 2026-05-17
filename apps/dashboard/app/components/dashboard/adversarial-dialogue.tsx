"use client";

/**
 * AdversarialDialogue — chat-bubble view of the trader↔sentinel exchange.
 *
 * Layout modes (selected via DockContext, header controls expose them):
 *   - inline  : flows in the workspace zone, max-w-4xl centered
 *   - left    : dialogue takes a full-height sticky column on the left
 *   - right   : same on the right
 *
 * When docked, the inline placement is replaced by the DashboardShell with
 * an aside; the bubble list grows to fill the column height with internal
 * scroll. The dock controls are visible in every mode.
 */

import { motion, useInView, useReducedMotion } from "motion/react";
import { useRef, useState } from "react";
import {
  MessagesSquare,
  ArrowDownToLine,
  Maximize2,
  PanelLeftOpen,
  PanelRightOpen,
  Layers,
} from "lucide-react";
import { connectorProviderBrand, type ProviderBrand } from "@/components/provider-badge";
import { Pill } from "@/components/ui/pill";
import { Dialog } from "@/components/ui/dialog";
import { useDock, type DockSide } from "@/components/dashboard/dashboard-shell";
import { cn } from "@/lib/utils";
import type { ConnectorPassport } from "@/lib/connectors";
import type { DialogueMessage } from "@/lib/schemas";

interface AdversarialDialogueProps {
  messages: DialogueMessage[];
  verdictScore?: number | null;
  verdictLabel?: string | null;
  traderModel?: string | null;
  sentinelModel?: string | null;
  evidenceConnector?: ConnectorPassport | null;
}

const FADE_EASE = [0.16, 1, 0.3, 1] as const;
const TOOL_MESSAGE_PREVIEW_CHARS = 520;

type Side = "trader" | "sentinel" | "neutral";

function sideForRole(role: string): Side {
  const r = role.toLowerCase();
  if (r.includes("trader") || r === "user") return "trader";
  if (r.includes("sentinel") || r === "assistant" || r === "validator")
    return "sentinel";
  return "neutral";
}

function verdictColor(score?: number | null): string {
  if (score === null || score === undefined) return "var(--color-fg-muted)";
  if (score < 26) return "var(--color-verdict-bad)";
  if (score < 51) return "var(--color-verdict-mid)";
  if (score < 76) return "oklch(0.78 0.18 110)";
  return "var(--color-verdict-good)";
}

function cleanDialogueText(value: string): string {
  return value.replace(/\uFFFD/g, "").replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, "");
}

export function AdversarialDialogue({
  messages,
  verdictScore,
  verdictLabel,
  traderModel,
  sentinelModel,
  evidenceConnector,
}: AdversarialDialogueProps) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-60px" });
  const reduced = useReducedMotion();

  const { side: dockSide, setSide } = useDock();
  const [modalOpen, setModalOpen] = useState(false);
  const evidenceBrand = evidenceConnector ? connectorProviderBrand(evidenceConnector) : null;

  const headerControls = (
    <DockControls dockSide={dockSide} setSide={setSide} onExpand={() => setModalOpen(true)} />
  );

  const body = (
    <DialogueBody
      messages={messages}
      verdictScore={verdictScore}
      verdictLabel={verdictLabel}
      inView={inView}
      reduced={!!reduced}
      evidenceBrand={evidenceBrand}
    />
  );

  // When docked, render as a full-height column (no rounded card, no extra
  // ambient glow — it's the aside content already styled by DashboardShell).
  if (dockSide !== "none") {
    if (messages.length === 0) {
      return (
        <div ref={ref} className="flex h-full flex-col">
          <DialogueHeader
            count={0}
            traderModel={traderModel}
            sentinelModel={sentinelModel}
            controls={headerControls}
            dockedColumn
          />
          <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 py-12 text-center">
            <MessagesSquare className="h-7 w-7 text-fg-faint" strokeWidth={1.4} />
            <p className="max-w-sm text-sm text-fg-faint">
              No adversarial exchange yet. When the sentinel and trader debate a
              trace, their back-and-forth appears here.
            </p>
          </div>
          <ModalCopy
            open={modalOpen}
            onClose={() => setModalOpen(false)}
            traderModel={traderModel}
            sentinelModel={sentinelModel}
            messages={messages}
            body={body}
          />
        </div>
      );
    }

    return (
      <div ref={ref} className="flex h-full flex-col">
        <DialogueHeader
          count={messages.length}
          traderModel={traderModel}
          sentinelModel={sentinelModel}
          controls={headerControls}
          dockedColumn
        />
        <div className="flex-1 overflow-auto">{body}</div>
        <ModalCopy
          open={modalOpen}
          onClose={() => setModalOpen(false)}
          traderModel={traderModel}
          sentinelModel={sentinelModel}
          messages={messages}
          body={body}
        />
      </div>
    );
  }

  // Default inline rendering — rounded card, ambient glows
  if (messages.length === 0) {
    return (
      <div
        ref={ref}
        className="overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-canvas-raised)]/60 backdrop-blur-sm"
      >
        <DialogueHeader
          count={0}
          traderModel={traderModel}
          sentinelModel={sentinelModel}
          controls={headerControls}
        />
        <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
          <MessagesSquare className="h-7 w-7 text-fg-faint" strokeWidth={1.4} />
          <p className="max-w-sm text-sm text-fg-faint">
            No adversarial exchange yet. When the sentinel and trader debate a
            trace, their back-and-forth appears here.
          </p>
        </div>
      </div>
    );
  }

  return (
    <>
      <div
        ref={ref}
        className="relative overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-canvas-raised)]/60 backdrop-blur-sm"
      >
        <span
          className="pointer-events-none absolute -left-20 top-1/2 h-48 w-48 -translate-y-1/2 rounded-full blur-3xl"
          style={{
            backgroundColor:
              "color-mix(in oklch, var(--color-trader) 20%, transparent)",
            opacity: 0.4,
          }}
          aria-hidden="true"
        />
        <span
          className="pointer-events-none absolute -right-20 top-1/2 h-48 w-48 -translate-y-1/2 rounded-full blur-3xl"
          style={{
            backgroundColor:
              "color-mix(in oklch, var(--color-sentinel) 20%, transparent)",
            opacity: 0.4,
          }}
          aria-hidden="true"
        />

        <DialogueHeader
          count={messages.length}
          traderModel={traderModel}
          sentinelModel={sentinelModel}
          controls={headerControls}
        />

        {body}
      </div>

      <ModalCopy
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        traderModel={traderModel}
        sentinelModel={sentinelModel}
        messages={messages}
        body={body}
      />
    </>
  );
}

/* ─────────────── Modal copy ─────────────── */

function ModalCopy({
  open,
  onClose,
  traderModel,
  sentinelModel,
  messages,
  body,
}: {
  open: boolean;
  onClose: () => void;
  traderModel?: string | null;
  sentinelModel?: string | null;
  messages: DialogueMessage[];
  body: React.ReactNode;
}) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Adversarial dialogue"
      maxWidthClass="max-w-3xl"
    >
      <DialogueHeader
        count={messages.length}
        traderModel={traderModel}
        sentinelModel={sentinelModel}
        controls={null}
        embedded
      />
      <div className="max-h-[70vh] overflow-auto">{body}</div>
    </Dialog>
  );
}

/* ─────────────── Body ─────────────── */

function DialogueBody({
  messages,
  verdictScore,
  verdictLabel,
  inView,
  reduced,
  evidenceBrand,
}: {
  messages: DialogueMessage[];
  verdictScore?: number | null;
  verdictLabel?: string | null;
  inView: boolean;
  reduced: boolean;
  evidenceBrand: ProviderBrand | null;
}) {
  return (
    <ol className="relative flex flex-col gap-3 p-5">
      {messages.map((msg, i) => {
        const side = sideForRole(msg.role);
        return (
          <motion.li
            key={`${msg.role}-${i}`}
            initial={reduced ? false : { opacity: 0, y: 8 }}
            animate={inView ? { opacity: 1, y: 0 } : { opacity: 0, y: 8 }}
            transition={{
              duration: 0.45,
              ease: FADE_EASE,
              delay: 0.05 + i * 0.08,
            }}
            className="flex"
            style={{
              justifyContent:
                side === "trader"
                  ? "flex-start"
                  : side === "sentinel"
                    ? "flex-end"
                    : "center",
            }}
          >
            <Bubble side={side} sequence={i + 1} role={msg.role} evidenceBrand={evidenceBrand}>
              {msg.content}
            </Bubble>
          </motion.li>
        );
      })}

      {verdictScore !== undefined && verdictScore !== null && (
        <motion.li
          initial={reduced ? false : { opacity: 0, y: 8 }}
          animate={inView ? { opacity: 1, y: 0 } : { opacity: 0, y: 8 }}
          transition={{
            duration: 0.55,
            ease: FADE_EASE,
            delay: 0.05 + messages.length * 0.08 + 0.2,
          }}
          className="flex justify-center pt-2"
        >
          <div
            className="inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-mono text-xs"
            style={{
              borderColor: `color-mix(in oklch, ${verdictColor(verdictScore)} 40%, var(--color-border))`,
              backgroundColor: `color-mix(in oklch, ${verdictColor(verdictScore)} 8%, transparent)`,
            }}
          >
            <ArrowDownToLine
              className="h-3 w-3"
              strokeWidth={2}
              style={{ color: verdictColor(verdictScore) }}
            />
            <span className="text-fg-faint">verdict</span>
            <span
              className="font-semibold tabular-nums"
              style={{ color: verdictColor(verdictScore) }}
            >
              {verdictScore}
            </span>
            {verdictLabel && (
              <span className="uppercase tracking-[var(--tracking-wide)] text-fg-muted">
                {verdictLabel}
              </span>
            )}
          </div>
        </motion.li>
      )}
    </ol>
  );
}

/* ─────────────── Dock controls ─────────────── */

function DockControls({
  dockSide,
  setSide,
  onExpand,
}: {
  dockSide: DockSide;
  setSide: (s: DockSide) => void;
  onExpand: () => void;
}) {
  return (
    <div className="inline-flex items-center gap-1 rounded-md border border-[var(--color-border)] bg-[var(--color-canvas)]/60 p-0.5">
      <DockButton
        label="Dock left"
        active={dockSide === "left"}
        onClick={() => setSide(dockSide === "left" ? "none" : "left")}
      >
        <PanelLeftOpen className="h-3.5 w-3.5" strokeWidth={2} />
      </DockButton>
      <DockButton
        label="Inline"
        active={dockSide === "none"}
        onClick={() => setSide("none")}
      >
        <Layers className="h-3.5 w-3.5" strokeWidth={2} />
      </DockButton>
      <DockButton
        label="Dock right"
        active={dockSide === "right"}
        onClick={() => setSide(dockSide === "right" ? "none" : "right")}
      >
        <PanelRightOpen className="h-3.5 w-3.5" strokeWidth={2} />
      </DockButton>
      <span className="mx-0.5 h-4 w-px bg-[var(--color-border)]" />
      <button
        type="button"
        onClick={onExpand}
        aria-label="Expand dialogue"
        title="Expand"
        className="focus-ring inline-flex h-6 w-6 items-center justify-center rounded text-fg-muted transition-colors hover:text-fg"
      >
        <Maximize2 className="h-3.5 w-3.5" strokeWidth={2} />
      </button>
    </div>
  );
}

function DockButton({
  label,
  active,
  onClick,
  children,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      aria-label={label}
      title={label}
      className={cn(
        "focus-ring inline-flex h-6 w-6 items-center justify-center rounded transition-colors",
        active
          ? "bg-[var(--color-canvas-raised)] text-fg shadow-[0_0_0_1px_var(--color-border-strong)_inset]"
          : "text-fg-faint hover:text-fg",
      )}
    >
      {children}
    </button>
  );
}

/* ─────────────── Header ─────────────── */

function DialogueHeader({
  count,
  traderModel,
  sentinelModel,
  controls,
  embedded,
  dockedColumn,
}: {
  count: number;
  traderModel?: string | null;
  sentinelModel?: string | null;
  controls?: React.ReactNode;
  embedded?: boolean;
  dockedColumn?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border)]",
        dockedColumn ? "px-4 py-3" : "px-5 py-3.5",
      )}
    >
      <div className="flex items-center gap-2">
        {!embedded && (
          <MessagesSquare
            className="h-4 w-4 text-[var(--color-fg-muted)]"
            strokeWidth={1.8}
          />
        )}
        {!embedded && (
          <span
            className={cn(
              "font-semibold tracking-[var(--tracking-tight)] text-fg",
              dockedColumn ? "text-sm" : "text-base",
            )}
          >
            Adversarial dialogue
          </span>
        )}
        {count > 0 && (
          <Pill tone="neutral" emphasis="outline" size="xs">
            <span className="text-mono">{count} msg</span>
          </Pill>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {/* Model identity row — hide in narrow docked column to keep header tight */}
        {!dockedColumn && (
          <div className="flex flex-wrap items-center gap-1.5 text-mono text-[10px]">
            <span className="inline-flex items-center gap-1.5">
              <span
                className="h-1.5 w-1.5 rounded-full"
                style={{ backgroundColor: "var(--color-trader)" }}
              />
              <span className="text-fg-faint">trader</span>
              {traderModel && (
                <span className="text-fg-muted">· {traderModel}</span>
              )}
            </span>
            <span className="text-fg-faint">⇄</span>
            <span className="inline-flex items-center gap-1.5">
              <span
                className="h-1.5 w-1.5 rounded-full"
                style={{ backgroundColor: "var(--color-sentinel)" }}
              />
              <span className="text-fg-faint">sentinel</span>
              {sentinelModel && (
                <span className="text-fg-muted">· {sentinelModel}</span>
              )}
            </span>
          </div>
        )}

        {controls && <div className="ml-2 flex items-center gap-1.5">{controls}</div>}
      </div>
    </div>
  );
}

/* ─────────────── Bubble ─────────────── */

interface BubbleProps {
  side: Side;
  sequence: number;
  role: string;
  evidenceBrand: ProviderBrand | null;
  children: React.ReactNode;
}

function Bubble({ side, sequence, role, evidenceBrand, children }: BubbleProps) {
  const isTrader = side === "trader";
  const isSentinel = side === "sentinel";
  const isNeutral = side === "neutral";
  const textContent = typeof children === "string" ? cleanDialogueText(children) : null;
  const isToolMessage = role.toLowerCase().includes("evidence_tool");
  const toolSummary = isToolMessage && textContent
    ? textContent.split(" — ")[0].slice(0, TOOL_MESSAGE_PREVIEW_CHARS)
    : null;

  const accentVar = isTrader
    ? "var(--color-trader)"
    : isSentinel
      ? "var(--color-sentinel)"
      : "var(--color-fg-muted)";

  const avatarLetter = isTrader ? "T" : isSentinel ? "S" : "·";

  return (
    <div
      className={cn(
        "flex max-w-[78%] items-start gap-2.5",
        isSentinel ? "flex-row-reverse" : "flex-row",
      )}
    >
      {!isNeutral && (
        <span
          className="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-mono text-[10px] font-semibold"
          style={{
            color: accentVar,
            borderColor: `color-mix(in oklch, ${accentVar} 40%, var(--color-border))`,
            backgroundColor: `color-mix(in oklch, ${accentVar} 12%, transparent)`,
          }}
          aria-hidden="true"
        >
          {avatarLetter}
        </span>
      )}

      <div
        className={cn(
          "min-w-0 flex-1 flex flex-col gap-1",
          isSentinel ? "items-end text-right" : "items-start text-left",
        )}
      >
        <span className="inline-flex flex-wrap items-center gap-1.5 text-mono text-[10px] uppercase tracking-[var(--tracking-wide)] text-fg-faint">
          <span>{role} · #{sequence}</span>
          {isToolMessage && evidenceBrand && (
            <span className="inline-flex items-center gap-1 rounded bg-[var(--color-canvas-raised)] px-1.5 py-0.5 normal-case tracking-normal text-fg-muted">
              <img src={evidenceBrand.logoSrc} alt="" aria-hidden="true" className="h-3.5 w-3.5 object-contain" />
              <span>{evidenceBrand.shortName}</span>
            </span>
          )}
        </span>

        <div
          className="relative rounded-2xl border px-3.5 py-2.5 text-sm leading-relaxed text-fg break-words [overflow-wrap:anywhere]"
          style={{
            borderColor: isNeutral
              ? "var(--color-border)"
              : `color-mix(in oklch, ${accentVar} 30%, var(--color-border))`,
            backgroundColor: isNeutral
              ? "var(--color-canvas-sunken)"
              : `color-mix(in oklch, ${accentVar} 6%, var(--color-canvas-sunken))`,
            borderTopLeftRadius: isTrader ? "6px" : undefined,
            borderTopRightRadius: isSentinel ? "6px" : undefined,
          }}
        >
          {toolSummary ? (
            <>
              {toolSummary}
              <span className="mt-2 block text-mono text-[10px] uppercase tracking-[var(--tracking-wide)] text-fg-faint">
                Full evidence is preserved in the issue ledger and receipt.
              </span>
            </>
          ) : (
            textContent ?? children
          )}
        </div>
      </div>
    </div>
  );
}
