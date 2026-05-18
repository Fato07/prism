export const COLORS = {
  bg: "#05070b",
  bg2: "#090d14",
  panel: "rgba(12, 17, 28, 0.78)",
  panelStrong: "rgba(16, 23, 36, 0.9)",
  border: "rgba(188, 198, 255, 0.16)",
  borderStrong: "rgba(188, 198, 255, 0.28)",
  text: "#f4f7fb",
  muted: "rgba(244, 247, 251, 0.64)",
  faint: "rgba(244, 247, 251, 0.38)",
  trader: "#35d7ff",
  sentinel: "#d66bff",
  verified: "#65f08d",
  warn: "#ffbd4a",
  blocked: "#ff5b74",
  usdc: "#55d07a",
  arc: "#a7b7ff",
} as const;

export const FONT = {
  sans: "Inter, SF Pro Display, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  mono: "SF Mono, ui-monospace, Menlo, Monaco, Consolas, monospace",
} as const;

export const SHOWCASE_PROOF = {
  canonicalTraceId: "85d58b9c-f45f-4aa1-8b8a-7a4b1c1c8fea",
  reportLabel: "URL-verified Exa receipt",
  searchTool: "web_search_exa",
  fetchTool: "web_fetch_exa",
  contentHash: "c395474d…4c614ae",
  x402Tx: "0x8d5d7a4…f5c12421",
  verdictCid: "QmYmfM…bFk7AR",
  score: "65 PASS",
} as const;

export const SHOWCASE_STATS = {
  verdictsIssued: 919,
  tracesValidated: 1113,
  onChainAnchors: 890,
  builderAttributedTrades: 458,
  builderFeesUsdc: "0.031563",
  externalX402Calls: 3,
} as const;
