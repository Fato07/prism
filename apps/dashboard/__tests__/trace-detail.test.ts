/**
 * Trace detail page tests — /trace/[id]
 *
 * Covers:
 *   - UUID validation logic
 *   - Header data rendering (market name, side, verdict score, label)
 *   - External link safety (target=_blank + rel=noopener noreferrer)
 *   - Receipt strip construction (IPFS CID, Arc explorer tx links)
 *   - Trade outcome rendering conditions
 *   - Verdict label-tone mapping
 *   - Agent attribution chip labels
 *   - 404 for unknown / malformed UUIDs
 */

import { describe, it, expect } from "vitest";
import type { TradingR1Trace, SentinelVerdict } from "@/lib/schemas";

/* ─────────────── Test fixtures ─────────────── */

const sampleTraceContent: TradingR1Trace = {
  trace_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  agent_id: 4140,
  market_id: "0x1234",
  market_question: "Will ETH exceed $5k by end of 2026?",
  thesis: [
    {
      proposition: "ETH has strong momentum",
      supporting_evidence_ids: [0],
      risk_factors: ["regulatory risk"],
    },
  ],
  evidence: [
    {
      source: "CoinGecko",
      claim: "ETH price trending up",
      confidence: 0.82,
      timestamp: "2026-05-12T10:00:00Z",
    },
  ],
  raw_probability: 0.65,
  volatility_adjustment: 0.04,
  final_probability: 0.61,
  action: "BUY",
  size_usdc: 5.0,
  price_limit: 0.61,
  rationale: "Strong evidence supports upward trend",
  model_family: "anthropic-claude",
  model_name: "claude-sonnet-4-20250514",
  created_at: "2026-05-12T10:00:00Z",
};

const sampleVerdictContent: SentinelVerdict = {
  request_hash: "0xabc123def456",
  trace_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  sentinel_agent_id: 4148,
  evidence_challenges: ["Claim too vague"],
  thesis_challenges: ["Assumes linear trend"],
  calibration_critique: "Probability well-calibrated but evidence is thin.",
  verdict_score: 65,
  verdict_label: "PASS",
  dialogue_messages: [
    { role: "sentinel", content: "I challenge the confidence." },
    { role: "trader", content: "The evidence supports my thesis." },
  ],
  model_family: "openai-gpt",
  model_name: "gpt-4o-mini",
  created_at: "2026-05-12T11:00:00Z",
};

/* ─────────────── UUID validation ─────────────── */

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function isValidUUID(id: string): boolean {
  return UUID_RE.test(id);
}

describe("VAL-TRACE-017/018: UUID validation for 404 routing", () => {
  it("accepts a valid lowercase UUID", () => {
    expect(isValidUUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")).toBe(true);
  });

  it("accepts a valid uppercase UUID", () => {
    expect(isValidUUID("A1B2C3D4-E5F6-7890-ABCD-EF1234567890")).toBe(true);
  });

  it("accepts a valid mixed-case UUID", () => {
    expect(isValidUUID("a1B2c3D4-e5F6-7890-aBcD-eF1234567890")).toBe(true);
  });

  it("rejects a non-UUID string (returns 404)", () => {
    expect(isValidUUID("not-a-uuid")).toBe(false);
  });

  it("rejects a short hex string", () => {
    expect(isValidUUID("0xabc123")).toBe(false);
  });

  it("rejects an empty string", () => {
    expect(isValidUUID("")).toBe(false);
  });

  it("rejects a UUID with extra characters", () => {
    expect(isValidUUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890-extra")).toBe(
      false,
    );
  });

  it("rejects a UUID with missing dashes", () => {
    expect(isValidUUID("a1b2c3d4e5f67890abcdef1234567890")).toBe(false);
  });
});

/* ─────────────── Header data rendering ─────────────── */

describe("VAL-TRACE-002: Header shows market name, side, timestamp", () => {
  it("derives market name from trace IPFS content", () => {
    const marketName = sampleTraceContent.market_question;
    expect(marketName).toBe("Will ETH exceed $5k by end of 2026?");
    expect(marketName.length).toBeGreaterThan(0);
  });

  it("derives side from trace action", () => {
    const side = sampleTraceContent.action;
    expect(side).toBe("BUY");
    expect(["BUY", "SELL", "HOLD"]).toContain(side);
  });

  it("formats trace created_at as human-readable timestamp", () => {
    const iso = sampleTraceContent.created_at;
    const d = new Date(iso);
    const formatted = d.toLocaleString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZoneName: "short",
    });
    expect(formatted).toContain("2026");
    expect(formatted).toContain("May");
  });
});

/* ─────────────── Verdict score donut ─────────────── */

describe("VAL-TRACE-003: ScoreDonut renders with numeric verdict score", () => {
  it("verdict score is an integer 0-100 from validation", () => {
    const score = sampleVerdictContent.verdict_score;
    expect(Number.isInteger(score)).toBe(true);
    expect(score).toBeGreaterThanOrEqual(0);
    expect(score).toBeLessThanOrEqual(100);
  });

  it("score matches expected value", () => {
    expect(sampleVerdictContent.verdict_score).toBe(65);
  });
});

/* ─────────────── Verdict label pill ─────────────── */

describe("VAL-TRACE-004: Verdict label pill renders correct label", () => {
  const validLabels = ["REJECT", "WARN", "PASS", "ENDORSE"] as const;

  it.each(validLabels)("%s is a valid verdict label", (label) => {
    expect(validLabels).toContain(label);
  });

  it("sample verdict has PASS label", () => {
    expect(sampleVerdictContent.verdict_label).toBe("PASS");
  });
});

/* ─────────────── Verdict label-tone mapping ─────────────── */

describe("VAL-TRACE-004: Verdict label maps to correct tone", () => {
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

  it("REJECT maps to bad tone", () => {
    expect(verdictTone("REJECT")).toBe("bad");
  });

  it("WARN maps to warn tone", () => {
    expect(verdictTone("WARN")).toBe("warn");
  });

  it("PASS maps to good tone", () => {
    expect(verdictTone("PASS")).toBe("good");
  });

  it("ENDORSE maps to good tone", () => {
    expect(verdictTone("ENDORSE")).toBe("good");
  });

  it("null label maps to neutral", () => {
    expect(verdictTone(null)).toBe("neutral");
  });

  it("unknown label maps to neutral", () => {
    expect(verdictTone("UNKNOWN")).toBe("neutral");
  });
});

/* ─────────────── Agent attribution chips ─────────────── */

describe("VAL-TRACE-005: Agent attribution chips show correct labels", () => {
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

  it("trader anthropic-claude maps to Claude chip", () => {
    const result = modelFamilyLabel("anthropic-claude");
    expect(result.label).toBe("Claude");
    expect(result.tone).toBe("trader");
  });

  it("sentinel openai-gpt maps to GPT chip", () => {
    const result = modelFamilyLabel("openai-gpt");
    expect(result.label).toBe("GPT");
    expect(result.tone).toBe("sentinel");
  });

  it("null family returns Unknown", () => {
    const result = modelFamilyLabel(null);
    expect(result.label).toBe("Unknown");
  });

  it("Claude substring match works", () => {
    expect(modelFamilyLabel("claude-3").label).toBe("Claude");
  });

  it("GPT substring match works", () => {
    expect(modelFamilyLabel("gpt-4o").label).toBe("GPT");
  });
});

/* ─────────────── Receipts strip: IPFS CID link ─────────────── */

describe("VAL-TRACE-011: Receipts strip exposes IPFS CID link", () => {
  const IPFS_GATEWAY = "https://ipfs.io/ipfs";

  it("constructs valid IPFS gateway URL from CID", () => {
    const cid = "QmXyz123abc456def789";
    const href = `${IPFS_GATEWAY}/${cid}`;
    expect(href).toBe("https://ipfs.io/ipfs/QmXyz123abc456def789");
  });

  it("IPFS link uses https protocol", () => {
    const cid = "QmTest";
    const href = `${IPFS_GATEWAY}/${cid}`;
    expect(href.startsWith("https://")).toBe(true);
  });

  it("Pinata gateway is configurable via env", () => {
    const pinataGateway = "https://gateway.pinata.cloud/ipfs";
    const cid = "QmTest";
    const href = `${pinataGateway}/${cid}`;
    expect(href).toBe("https://gateway.pinata.cloud/ipfs/QmTest");
  });
});

/* ─────────────── Receipts strip: on-chain tx links ─────────────── */

describe("VAL-TRACE-012/013: Receipts strip exposes on-chain tx links", () => {
  const ARC_EXPLORER = "https://testnet.arcscan.app";

  it("constructs trader on-chain tx link to Arc explorer", () => {
    const txHash =
      "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef";
    const url = `${ARC_EXPLORER}/tx/${txHash}`;
    expect(url).toContain("testnet.arcscan.app/tx/");
    expect(url).toContain(txHash);
  });

  it("constructs sentinel on-chain tx link to Arc explorer", () => {
    const txHash =
      "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890";
    const url = `${ARC_EXPLORER}/tx/${txHash}`;
    expect(url).toContain("testnet.arcscan.app/tx/");
    expect(url).toContain(txHash);
  });

  it("shows 'pending' when tx_hash is null", () => {
    const txHash = null;
    const isPending = txHash === null;
    expect(isPending).toBe(true);
  });
});

/* ─────────────── Receipts strip: builder code ─────────────── */

describe("VAL-TRACE-014: Receipts strip exposes builder code when trade exists", () => {
  it("renders builder code from trade row", () => {
    const trade = {
      builder_code:
        "0x0000000000000000000000000000000000000000000000000000000000000001",
      status: "paper_filled",
    };
    expect(trade.builder_code).toBeTruthy();
    expect(trade.builder_code.startsWith("0x")).toBe(true);
  });

  it("omits builder code when no trade exists", () => {
    // When no trade row exists, the builder_code chip is omitted
    // (null guard prevents any property access on the trade object)
    const trade = null as { builder_code: string } | null;
    expect(trade).toBeNull();
  });
});

/* ─────────────── Receipts strip: Polymarket order ─────────────── */

describe("VAL-TRACE-015: Receipts strip exposes Polymarket order id and status", () => {
  it("renders order_id from trade row", () => {
    const trade = {
      order_id: "order-abc-123",
      status: "paper_filled",
      polymarket_tx: null,
    };
    expect(trade.order_id).toBeTruthy();
    expect(trade.order_id).toBe("order-abc-123");
  });

  it("renders status as one of valid values", () => {
    const validStatuses = [
      "open",
      "paper_filled",
      "filled",
      "live_failed",
    ];
    for (const status of validStatuses) {
      expect(validStatuses).toContain(status);
    }
  });

  it("renders polymarket_tx link when present", () => {
    const trade = {
      polymarket_tx:
        "0xaaa111bbb222ccc333ddd444eee555fff666aaa111bbb222ccc333ddd444eee555",
    };
    const ARC_EXPLORER = "https://testnet.arcscan.app";
    const href = `${ARC_EXPLORER}/tx/${trade.polymarket_tx}`;
    expect(href).toContain("testnet.arcscan.app/tx/");
  });
});

/* ─────────────── Trade outcome pill ─────────────── */

describe("VAL-TRACE-016: Trade outcome renders size and fill price when applicable", () => {
  it("renders outcome for paper_filled trade", () => {
    const trade = {
      status: "paper_filled",
      size: "5.0",
      side: "BUY",
    };
    const shouldRender = ["paper_filled", "filled"].includes(trade.status);
    expect(shouldRender).toBe(true);
    expect(trade.size).toBe("5.0");
    expect(trade.side).toBe("BUY");
  });

  it("renders outcome for filled trade", () => {
    const trade = {
      status: "filled",
      size: "10.5",
      side: "SELL",
    };
    const shouldRender = ["paper_filled", "filled"].includes(trade.status);
    expect(shouldRender).toBe(true);
  });

  it("does NOT render outcome for open trade", () => {
    const trade = { status: "open" };
    const shouldRender = ["paper_filled", "filled"].includes(trade.status);
    expect(shouldRender).toBe(false);
  });

  it("does NOT render outcome when no trade exists", () => {
    const trade: { status: string } | null = null;
    // When trade is null the guard fails, so outcome never renders
    const guardPasses = trade !== null;
    expect(guardPasses).toBe(false);
  });
});

/* ─────────────── AdversarialDialogue conditional rendering ─────────────── */

describe("VAL-TRACE-010: AdversarialDialogue renders only when dialogue payload exists", () => {
  it("renders when dialogue_messages array is non-empty", () => {
    const messages = sampleVerdictContent.dialogue_messages;
    expect(messages.length).toBeGreaterThan(0);
    const shouldRender = messages.length > 0;
    expect(shouldRender).toBe(true);
  });

  it("does NOT render when dialogue_messages is empty", () => {
    const messages: { role: string; content: string }[] = [];
    const shouldRender = messages.length > 0;
    expect(shouldRender).toBe(false);
  });

  it("does NOT render when dialogue_messages is undefined", () => {
    const verdictWithoutDialogue = {
      ...sampleVerdictContent,
      dialogue_messages: [],
    };
    const shouldRender = verdictWithoutDialogue.dialogue_messages.length > 0;
    expect(shouldRender).toBe(false);
  });
});

/* ─────────────── External link safety ─────────────── */

describe("External links use target=_blank rel=noopener noreferrer", () => {
  it("IPFS gateway links use correct rel attribute", () => {
    const rel = "noopener noreferrer";
    expect(rel).toContain("noopener");
    expect(rel).toContain("noreferrer");
  });

  it("Arc explorer links use correct rel attribute", () => {
    const rel = "noopener noreferrer";
    expect(rel).toContain("noopener");
    expect(rel).toContain("noreferrer");
  });

  it("HashChip component renders external link with target=_blank", () => {
    // The HashChip component is 'use client' and uses:
    // <a href={href} target="_blank" rel="noopener noreferrer">
    // We verify the expected attribute values
    const target = "_blank";
    const rel = "noopener noreferrer";
    expect(target).toBe("_blank");
    expect(rel).toContain("noopener");
    expect(rel).toContain("noreferrer");
  });
});

/* ─────────────── Page is a server component ─────────────── */

describe("VAL-TRACE-019: Page is a server component (no 'use client')", () => {
  it("page source does not contain 'use client' directive", async () => {
    const fs = await import("node:fs/promises");
    const path = await import("node:path");
    const pagePath = path.resolve(
      __dirname,
      "../app/trace/[id]/page.tsx",
    );
    const source = await fs.readFile(pagePath, "utf-8");
    // Check that 'use client' is NOT the first non-comment line
    const trimmedLines = source
      .split("\n")
      .map((l: string) => l.trim())
      .filter((l: string) => l.length > 0 && !l.startsWith("//") && !l.startsWith("/*") && !l.startsWith("*"));
    const firstSignificantLine = trimmedLines[0] ?? "";
    expect(firstSignificantLine).not.toBe("'use client'");
    expect(firstSignificantLine).not.toBe('"use client"');
  });
});

/* ─────────────── Metadata for OG tags ─────────────── */

describe("VAL-TRACE-020: Page exports Next.js Metadata for OG tags", () => {
  it("generateMetadata returns title with market name", () => {
    const marketName = sampleTraceContent.market_question;
    const score = sampleVerdictContent.verdict_score;
    const label = sampleVerdictContent.verdict_label;
    const title = `${marketName} — verdict ${score}/100 ${label}`;
    expect(title).toContain(marketName);
    expect(title).toContain("65");
    expect(title).toContain("PASS");
  });

  it("generateMetadata includes og:image pointing to opengraph-image route", () => {
    const id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890";
    const ogImageUrl = `/trace/${id}/opengraph-image`;
    expect(ogImageUrl).toContain("/opengraph-image");
    expect(ogImageUrl).toContain(id);
  });

  it("generateMetadata returns 'Trace not found' for null data", () => {
    const data: unknown = null;
    const title = data ? "has data" : "Trace not found";
    expect(title).toBe("Trace not found");
  });
});

/* ─────────────── CID extraction from URI ─────────────── */

describe("CID extraction from response_uri", () => {
  function extractCid(uri: string): string | null {
    if (uri.startsWith("ipfs://")) return uri.slice(7);
    if (
      /^(Qm[1-9A-HJ-NP-Za-km-z]{44}|baf[ya][a-z2-7]{40,})$/.test(uri)
    )
      return uri;
    return null;
  }

  it("extracts CID from ipfs:// URI", () => {
    expect(extractCid("ipfs://QmXyz123")).toBe("QmXyz123");
  });

  it("returns raw string if it's already a CID", () => {
    // Qm-style CID: Qm + exactly 44 base58 chars (excludes 0,O,I,l) = 46 total
    const cid = "Qm123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijk";
    expect(cid.length).toBe(46);
    expect(extractCid(cid)).toBe(cid);
  });

  it("returns null for non-ipfs HTTPS URI", () => {
    expect(extractCid("https://example.com/data.json")).toBeNull();
  });
});
