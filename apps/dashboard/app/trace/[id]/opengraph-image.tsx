/**
 * Open Graph Image Route — /trace/[id]/opengraph-image
 *
 * Generates a 1200×630 PNG for Twitter/X card previews using the
 * Next.js Metadata API + ImageResponse (Satori).
 *
 * Layout:
 *   Dark gradient background (canvas → canvas-raised)
 *   "PRISM" brand top-left
 *   Large score number centre-left
 *   Verdict label pill (PASS / REJECT / WARN / ENDORSE) centre
 *   Market name bottom area
 *
 * Unknown UUID → fallback image reading "Trace not found" (not 404 —
 * OG fetchers don't handle 404 gracefully per VAL-OG-003).
 */

import { ImageResponse } from "next/og";
import { getTraceDetailData } from "@/lib/db";
import type { TradingR1Trace, SentinelVerdict } from "@/lib/schemas";

/* ─────────────── Route segment config ─────────────── */

export const alt = "Prism trace verdict card";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

/* ─────────────── UUID validation ─────────────── */

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function isValidUUID(id: string): boolean {
  return UUID_RE.test(id);
}

/* ─────────────── Verdict colour helpers ─────────────── */

type VerdictLabel = "REJECT" | "WARN" | "PASS" | "ENDORSE";

/** Returns an RGB hex string for the verdict pill background. */
function verdictBg(label: string): string {
  const map: Record<VerdictLabel, string> = {
    REJECT: "#b32429", // red
    WARN: "#a67c1a",   // amber
    PASS: "#1a8a4a",   // green
    ENDORSE: "#0f7a3e", // deep green
  };
  return (map[label as VerdictLabel] ?? "#555555");
}

/** Returns an RGB hex string for the verdict pill text. */
function verdictFg(label: string): string {
  const map: Record<VerdictLabel, string> = {
    REJECT: "#fde8e8",
    WARN: "#fef3d0",
    PASS: "#d4fce8",
    ENDORSE: "#c0f5d6",
  };
  return (map[label as VerdictLabel] ?? "#ffffff");
}

/** Maps a 0–100 score to an approximate hex colour along the spectrum. */
function scoreColor(score: number): string {
  const clamped = Math.max(0, Math.min(100, score));
  // Red (0) → Amber (50) → Green (100)
  if (clamped <= 50) {
    const t = clamped / 50;
    const r = Math.round(200 - t * 40);
    const g = Math.round(60 + t * 120);
    const b = Math.round(40 - t * 10);
    return `rgb(${r},${g},${b})`;
  }
  const t = (clamped - 50) / 50;
  const r = Math.round(160 - t * 120);
  const g = Math.round(180 + t * 40);
  const b = Math.round(30 + t * 70);
  return `rgb(${r},${g},${b})`;
}

/* ─────────────── Fallback image ─────────────── */

function fallbackImage(): ImageResponse {
  return new ImageResponse(
    (
      <div
        style={{
          width: 1200,
          height: 630,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          background: "linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #1a1a2e 100%)",
          fontFamily: "system-ui, sans-serif",
          color: "#8a8a9a",
        }}
      >
        {/* Brand */}
        <div
          style={{
            fontSize: 20,
            fontWeight: 700,
            letterSpacing: "0.15em",
            color: "#6a6a7a",
            marginBottom: 32,
          }}
        >
          PRISM
        </div>

        {/* Icon */}
        <div
          style={{
            fontSize: 48,
            marginBottom: 16,
          }}
        >
          ⬡
        </div>

        {/* Message */}
        <div
          style={{
            fontSize: 32,
            fontWeight: 600,
            color: "#6a6a7a",
          }}
        >
          Trace not found
        </div>

        <div
          style={{
            fontSize: 16,
            color: "#4a4a5a",
            marginTop: 12,
          }}
        >
          The first adversarial AI validator on ERC-8004
        </div>
      </div>
    ),
    {
      width: 1200,
      height: 630,
    },
  );
}

/* ─────────────── Route handler ─────────────── */

interface ImageProps {
  params: Promise<{ id: string }>;
}

export default async function OpengraphImage({ params }: ImageProps) {
  const { id } = await params;

  // VAL-OG-003: malformed UUID → fallback image (not 404)
  if (!isValidUUID(id)) {
    return fallbackImage();
  }

  const data = await getTraceDetailData(id);

  // VAL-OG-003: unknown UUID → fallback image (not 404)
  if (!data) {
    return fallbackImage();
  }

  const { trace, validation } = data;
  const traceContent = data.traceContent as TradingR1Trace | null;
  const verdictContent = data.verdictContent as SentinelVerdict | null;

  const marketName =
    traceContent?.market_question ?? trace.market_id;
  const score = validation?.verdict_score ?? 0;
  const verdictLabel = verdictContent?.verdict_label ?? null;
  const side = traceContent?.action ?? null;

  // Truncate market name for image (avoid overflow)
  const displayMarket =
    marketName.length > 80 ? marketName.slice(0, 77) + "…" : marketName;

  return new ImageResponse(
    (
      <div
        style={{
          width: 1200,
          height: 630,
          display: "flex",
          flexDirection: "column",
          background:
            "linear-gradient(135deg, #1a1a2e 0%, #0f1a2a 40%, #16213e 70%, #1a1a2e 100%)",
          fontFamily: "system-ui, sans-serif",
          color: "#e8e8f0",
          padding: 0,
          position: "relative",
          overflow: "hidden",
        }}
      >
        {/* Decorative accent line (top) */}
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            height: 4,
            background: "linear-gradient(90deg, #4ac1e0, #c84aca, #1a8a4a)",
          }}
        />

        {/* Main content area */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            flex: 1,
            padding: "56px 72px 48px 72px",
            justifyContent: "space-between",
          }}
        >
          {/* Top row: Brand + Side pill */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            {/* Brand */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
              }}
            >
              <div
                style={{
                  fontSize: 14,
                  fontWeight: 700,
                  letterSpacing: "0.2em",
                  color: "#6a6a7a",
                }}
              >
                PRISM
              </div>
              <div
                style={{
                  fontSize: 12,
                  color: "#4a4a5a",
                }}
              >
                Adversarial AI Validator
              </div>
            </div>

            {/* Side pill */}
            {side && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                }}
              >
                <div
                  style={{
                    fontSize: 13,
                    fontWeight: 600,
                    padding: "4px 16px",
                    borderRadius: 20,
                    background:
                      side === "BUY"
                        ? "rgba(74, 193, 224, 0.15)"
                        : side === "SELL"
                          ? "rgba(200, 74, 202, 0.15)"
                          : "rgba(100, 100, 120, 0.15)",
                    color:
                      side === "BUY"
                        ? "#4ac1e0"
                        : side === "SELL"
                          ? "#c84aca"
                          : "#8a8a9a",
                    border:
                      side === "BUY"
                        ? "1px solid rgba(74, 193, 224, 0.3)"
                        : side === "SELL"
                          ? "1px solid rgba(200, 74, 202, 0.3)"
                          : "1px solid rgba(100, 100, 120, 0.3)",
                  }}
                >
                  {side}
                </div>
              </div>
            )}
          </div>

          {/* Centre: Score + Verdict pill */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 40,
              marginTop: 24,
            }}
          >
            {/* Score number */}
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "flex-start",
              }}
            >
              <div
                style={{
                  fontSize: 120,
                  fontWeight: 800,
                  lineHeight: 1,
                  color: scoreColor(score),
                  letterSpacing: "-0.04em",
                }}
              >
                {score}
              </div>
              <div
                style={{
                  fontSize: 14,
                  color: "#6a6a7a",
                  marginTop: 8,
                  letterSpacing: "0.1em",
                }}
              >
                VERDICT SCORE
              </div>
            </div>

            {/* Verdict label pill */}
            {verdictLabel && (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "flex-start",
                  gap: 8,
                }}
              >
                <div
                  style={{
                    fontSize: 36,
                    fontWeight: 700,
                    padding: "10px 28px",
                    borderRadius: 16,
                    background: verdictBg(verdictLabel),
                    color: verdictFg(verdictLabel),
                    letterSpacing: "0.08em",
                  }}
                >
                  {verdictLabel}
                </div>
                <div
                  style={{
                    fontSize: 13,
                    color: "#5a5a6a",
                  }}
                >
                  / 100
                </div>
              </div>
            )}
          </div>

          {/* Bottom: Market name */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 8,
              marginTop: 32,
            }}
          >
            <div
              style={{
                fontSize: 36,
                fontWeight: 600,
                lineHeight: 1.3,
                color: "#d0d0e0",
                maxWidth: 1000,
              }}
            >
              {displayMarket}
            </div>
            <div
              style={{
                fontSize: 14,
                color: "#5a5a6a",
                letterSpacing: "0.02em",
              }}
            >
              erc-8004 · arc testnet · prediction market
            </div>
          </div>
        </div>

        {/* Bottom accent bar */}
        <div
          style={{
            height: 2,
            background: "linear-gradient(90deg, transparent, rgba(74,193,224,0.3), rgba(200,74,202,0.3), transparent)",
          }}
        />
      </div>
    ),
    {
      width: 1200,
      height: 630,
    },
  );
}
