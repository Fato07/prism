# Prism Pitch Video

Remotion video workspace for Prism.

- `PrismPitch` — original 90-second hackathon pitch composition.
- `PrismShowcase` — 70-second premium brand-film experiment for creative testing. This is separate from the official founder-led judge demo.
- `exports/prism-showcase-production.mp4` — committed preview MP4 for easy sharing from this branch.

## Quick Start

```bash
cd apps/pitch-video
pnpm install          # install dependencies
pnpm dev              # open Remotion Studio at http://localhost:3001
pnpm build            # render MP4 to out/prism-pitch.mp4
pnpm render:showcase  # render creative showcase to out/prism-showcase.mp4
```

> **Port 3001, not 3000.** The dashboard dev server owns port 3000. This project's `dev`/`studio` scripts use `--port 3001` to avoid conflicts.

## Creative Showcase Composition

`PrismShowcase` is the new brand-film draft for testing a more premium Prism visual language. It uses deterministic Remotion graphics for the truth layer and optional b-roll slots for Higgsfield-generated clips.

Render it locally:

```bash
cd apps/pitch-video
pnpm render:showcase
pnpm still:showcase
```

### Higgsfield b-roll pipeline

The prompt pack lives at `higgsfield/broll-prompts.json`; the guarded generator is `scripts/generate-higgsfield-broll.mjs`.

Preflight cost/credits without creating jobs:

```bash
cd apps/pitch-video
pnpm higgsfield:broll:dry
```

Generate and download all b-roll clips after reviewing the estimate:

```bash
cd apps/pitch-video
HIGGSFIELD_MAX_CREDITS=60 pnpm higgsfield:broll
```

The script:

- checks `higgsfield account status`;
- estimates each clip with `higgsfield generate cost`;
- blocks if credits are insufficient or the estimate exceeds `HIGGSFIELD_MAX_CREDITS`;
- creates jobs with `--wait`;
- downloads videos to `public/broll/`;
- writes `public/broll/showcase-broll-props.json` for Remotion.

Render with generated b-roll and the procedural sound bed:

```bash
pnpm render:showcase:production
```

Copy the latest render into the committed preview slot:

```bash
cp out/prism-showcase-production.mp4 exports/prism-showcase-production.mp4
```

`PrismShowcaseBroll` is a convenience composition that points at the generated `public/broll/*.mp4` files and `public/audio/prism-showcase-bed.wav`. The audio bed is generated locally by `pnpm audio:showcase`, so it is reproducible and royalty-free. Use `PrismShowcase` when you want the deterministic Remotion-only cut.

Optional local assets can also be placed under `apps/pitch-video/public/` and passed as props manually:

```bash
pnpm render:showcase -- --props='{
  "musicSrc":"audio/prism-ambient.mp3",
  "voiceoverSrc":"audio/prism-vo.mp3",
  "broll":{
    "refractionSrc":"broll/refraction.mp4",
    "traceAssemblySrc":"broll/trace-assembly.mp4",
    "urlVerificationSrc":"broll/url-verification.mp4",
    "capitalGateSrc":"broll/capital-gate.mp4",
    "arcAnchorSrc":"broll/arc-anchor.mp4"
  }
}'
```

Guidance:

- Use Higgsfield for short abstract b-roll only: prism refraction, evidence receipts, capital gates, x402 packets, Arc anchors.
- Keep real hashes, source URLs, tx proof, and stats in Remotion overlays — never baked into generated video.
- Avoid AI avatars or fake founder footage for the official submission.
- Keep the official judge demo founder-led and receipt-backed.

Local creative brief: `../../.local/showcase-video-creative-brief.md`.

## Parameterized Pitch Composition

The `PrismPitch` composition is registered in `src/index.tsx` with a Zod schema that defines all swappable props. This enables visual editing in Remotion Studio and programmatic rendering with custom props.

### Schema (`prismPitchSchema`)

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `operatorVideoSrc` | `string` | `""` | Path or URL to an MP4 of the operator speaking. Empty string = slide-only build (no face/voice). |
| `tractionNumbers.verdictsIssued` | `number` | `27` | Total adversarial verdicts produced |
| `tractionNumbers.uniqueWallets` | `number` | `1` | Distinct external wallets that called the sentinel |
| `tractionNumbers.tracesValidated` | `number` | `27` | Trading-R1 traces validated |
| `tractionNumbers.onChainAnchors` | `number` | `54` | ERC-8004 validation request + response tx pairs |
| `tractionNumbers.builderFeesUsdc` | `number` | `0.0` | USDC builder fees attributed via HMAC |
| `tractionNumbers.externalX402Calls` | `number` | `0` | External x402-paid validations served |

### `defaultProps` Example

```ts
const defaultProps = prismPitchSchema.parse({
  operatorVideoSrc: "",
  tractionNumbers: {
    verdictsIssued: 27,
    uniqueWallets: 1,
    tracesValidated: 27,
    onChainAnchors: 54,
    builderFeesUsdc: 0.0,
    externalX402Calls: 0,
  },
});
```

To swap face/voice clips without editing source, set `operatorVideoSrc` to a path like `"operator.mp4"` and place the file in `apps/pitch-video/public/`. Then render:

```bash
pnpm render --props='{"operatorVideoSrc":"operator.mp4","tractionNumbers":{"verdictsIssued":42}}'
```

## 90-Second Script Outline

| Time | Scene | Key Points |
|------|-------|------------|
| 0–10s | **Hook** | "Autonomous AI agents are about to trade billions. Nobody audits their reasoning. I built Prism." |
| 10–25s | **Problem** | Lucky bad reasoning → high score. Brilliant reasoning → no credit. ERC-8004 has a validation slot — nobody filled it. |
| 25–45s | **Two-Agent Solution** | Trader (Claude / Mirascope) generates Trading-R1 trace. Sentinel (GPT / DSPy) adversarially challenges. Cross-family pressure catches family-correlated failures. |
| 45–60s | **On-Chain Proof** | Every dialogue anchored on Arc (chain 5042002). Register → validationRequest → adversarial review → validationResponse. Gas paid in USDC by EOA wallets in Phase 0. |
| 60–68s | **Polymarket Attribution** | Builder code = HMAC(agentId, salt). Deterministic identity → attribution without custodial bridging. |
| 68–78s | **Platform Play** | Sentinel-as-a-Service. External agents call MCP endpoint. $0.01 USDC/validation via x402. Circle Gateway settlement. |
| 78–85s | **Circle Surface** | Circle surfaces: Developer-Controlled Wallets, Contract Execution, native USDC gas, x402 payments, App Kit Bridge. |
| 85–90s | **Close** | "See through the reasoning." Logo + tagline + traction badges + live URL. |

**Speaker notes (operator recording guide):**
- Fathin Dos, solo builder, Estonia.
- Adversarial AI validator on ERC-8004 — the first to fill the adversarial validation slot.
- Reasoning traces are the product: not just "did it make money" but "was the reasoning sound?"
- Builder codes prove on-chain that AI-driven trades came from verified agent identities.
- What's live: dashboard at `prism-dashboard-production-e6e3.up.railway.app`, sentinel x402 endpoint, Arc Testnet ERC-8004 anchors.
- Traction numbers are pulled from Neon at render time via the `tractionNumbers` prop.

## Recording and Rendering Instructions

### 1. Record the operator video

Use your phone or webcam. Record in landscape (16:9). Speak the script naturally. Aim for ~90 seconds. Export as MP4.

```bash
# Place the recording in the public/ directory
cp ~/Downloads/my-pitch-recording.mp4 apps/pitch-video/public/operator.mp4
```

### 2. Render the face+voice version

```bash
cd apps/pitch-video

# Build with operator video embedded
pnpm render -- --props='{"operatorVideoSrc":"operator.mp4"}'

# Or for a custom traction snapshot:
pnpm render -- --props='{"operatorVideoSrc":"operator.mp4","tractionNumbers":{"verdictsIssued":50,"uniqueWallets":3,"onChainAnchors":100}}'
```

### 3. Render the slide-only version (no operator face/voice)

```bash
cd apps/pitch-video
pnpm build
# Output: out/prism-pitch.mp4
```

### 4. Pull live traction numbers from Neon

Before rendering, query Neon for the latest counts and pass them as props:

```bash
# Example (requires DATABASE_URL):
VERDICTS=$(psql "$DATABASE_URL" -tAc "SELECT count(*) FROM validations")
WALLETS=$(psql "$DATABASE_URL" -tAc "SELECT count(DISTINCT requester_address) FROM validations WHERE requester_address IS NOT NULL")
ANCHORS=$(psql "$DATABASE_URL" -tAc "SELECT count(*) FROM validations WHERE tx_hash IS NOT NULL")

pnpm render -- --props="{\"tractionNumbers\":{\"verdictsIssued\":$VERDICTS,\"uniqueWallets\":$WALLETS,\"onChainAnchors\":$ANCHORS}}"
```

## Output

| File | Path | Description |
|------|------|-------------|
| MP4 | `out/prism-pitch.mp4` | Rendered video (gitignored) |
| Thumbnail | `out/thumbnail.png` | First frame still (via `pnpm still`) |

Output files are gitignored — they are never committed to the repository.

## Project Structure

```
apps/pitch-video/
├── package.json          # Scripts: dev, build, render, still
├── tsconfig.json         # TypeScript strict mode
├── public/               # Static assets (place operator.mp4 here)
├── out/                  # Rendered outputs (gitignored)
└── src/
    ├── index.tsx          # Root: registers Composition with schema + defaultProps
    ├── PrismPitch.tsx     # Main composition: sequences 8 scenes
    ├── components/
    │   ├── AnimatedText.tsx
    │   ├── Background.tsx
    │   └── PrismLogo.tsx
    └── scenes/
        ├── Hook.tsx
        ├── Problem.tsx
        ├── TwoAgentSolution.tsx
        ├── OnChainProof.tsx
        ├── PolymarketAttribution.tsx
        ├── PlatformPlay.tsx
        ├── CircleSurface.tsx
        └── Close.tsx      # Accepts operatorVideoSrc + tractionNumbers props
```
