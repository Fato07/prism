# Prism — The First Adversarial AI Validator on ERC-8004

> Two AI agents debate your trade reasoning on-chain. One generates. One challenges. Both are accountable.

[![Live Demo](https://img.shields.io/badge/demo-live-brightgreen)](https://prism-dashboard-production-e6e3.up.railway.app)
[![Docs](https://img.shields.io/badge/docs-live-cyan)](https://prism-docs-production.up.railway.app)
[![Pitch Video](https://img.shields.io/badge/pitch_video-coming_soon-lightgrey)](#-pitch-video-3-min)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![Arc Testnet](https://img.shields.io/badge/chain-Arc_Testnet_(5042002)-purple)](https://docs.arc.network/)

**Prism** is an adversarial AI validation system built on [ERC-8004](https://eips.ethereum.org/EIPS/eip-8004). A **Trader** agent (Claude/Mirascope) generates structured reasoning traces for prediction markets. A **Sentinel** agent (GPT/DSPy) adversarially challenges every claim. Both are registered on-chain, every validation is anchored on Arc testnet, and the sentinel is exposed as an x402-protected service other agents can call.

> *Prism makes AI agents accountable to other AI agents.*

---

## Try it in 30 seconds

1. Open the live dashboard: <https://prism-dashboard-production-e6e3.up.railway.app/submit>
2. Connect MetaMask and switch to **Base Sepolia**
3. Get free testnet USDC from the [Circle faucet](https://faucet.circle.com) (Base Sepolia + USDC)
4. Paste this known-good IPFS CID: `QmNzqnPEEQUMn3GMbiEZANpKXZRPmTHxVwt5nNevR8iXt8`
5. Click **Validate**, sign the 0.01 USDC payment in MetaMask
6. You land on `/trace/[id]` with the cross-family adversarial verdict

First real self-serve run on 2026-05-15 settled at [`0x63bf7094…`](https://sepolia.basescan.org/tx/0x63bf70941e8890b2b92459addfa18ecb57dd06bba7ea715391f00322faf58d68) on Base Sepolia. Receipt: [`docs/demos/self-serve-submit-20260515T101946Z.md`](docs/demos/self-serve-submit-20260515T101946Z.md).

First live CLI paid validation on 2026-05-16 settled at [`0xd6ab0cbb…`](https://sepolia.basescan.org/tx/0xd6ab0cbba99dfa1162ab24ccf35c9e9544c1bb64a550a0e349e8033ebd4f43e1) on Base Sepolia. Receipt: [`docs/demos/cli-paid-validation-20260516T214837Z.md`](docs/demos/cli-paid-validation-20260516T214837Z.md).

---

## Architecture

```
                     Arc Testnet (chain 5042002)
                     USDC native gas · ~$0.01/tx · sub-second finality
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
     IdentityRegistry   ValidationRegistry   ReputationRegistry
     0x8004A8…BD9e      0x8004Cb…4272        0x8004B6…8713
              │               │               │
              └───────────────┼───────────────┘
                              │
                    Circle Dev-Controlled Wallets
                    (signs + submits all txs)
                              │
          ┌───────────────────┴───────────────────┐
          ▼                                       ▼
  Trader Agent (Python)                    Sentinel Agent (Python)
  Mirascope · Claude family                DSPy · GPT-4o-mini
  Trading-R1 trace generation              TraceAdversary + MIPROv2
  Treasury (USYC dry-run scaffold)                  │
           │                                        │
  Polymarket V2 SDK                                 ▼
  (builder code)                           x402-protected MCP
           │                               ($0.01 USDC/validation)
           ▵                                        │
  Polymarket CLOB (Polygon)                         │
                                                      │
                              ┌───────────────────────┘
                              ▼
                    Dashboard (Next.js 16)
                    split-screen dialogue + on-chain receipts
                    wallet-connected · self-serve validation
```

---

## Data Flow

1. Fetch Polymarket market → 2. Trader generates Trading-R1 trace → 3. Pin to IPFS → 4. Persist to Postgres → 5. On-chain `validationRequest` → 6. Sentinel challenges trace → 7. Verdict + dialogue → 8. Pin to IPFS → 9. Persist to Postgres → 10. On-chain `validationResponse` → 11. Paper trade with builder code → 12. Dashboard display

---

## What's Live

### Dashboard Routes

| Route | Description |
|-------|-------------|
| `/` | Landing page with the product story, live activity strip, and waitlist |
| `/dashboard` | Split-screen trace + verdict dialogue, on-chain receipts |
| `/trace/[id]` | Trace detail page — server component with structured layout and dynamic OG image |
| `/history` | Paginated history of all traces and verdicts |
| `/me` | Wallet-connected verdict history (wagmi v2 + Reown AppKit) |
| `/submit` | Self-serve x402 validation — sign EIP-3009 transfers from the browser; shows Circle App Kit Bridge widget when USDC balance < 0.01 |
| `/builder-fees` | Polymarket builder-code attribution — paper-fill fee model plus live-fill receipts when available |
| `/stats` | Receipt-linked activity stats — validations, Arc anchors, x402 calls, builder attribution, latency, calibration |

### Infrastructure

- **Web3 wallet connection** — Reown AppKit + wagmi v2 across all pages; connected address available in `/me` and `/submit`
- **Circle App Kit Bridge** — conditional bridge widget on `/submit` when wallet USDC < 0.01 (bridge USDC from other chains to Base Sepolia for x402 payments)
- **Treasury module** — trader service includes a USYC park/unpark scaffold; it runs in dry-run mode until an Arc Testnet USYC address is configured. Events are tracked via `treasury_events`.
- **Dual x402 facilitator scaffold** — public x402 payments settle on Base Sepolia today; Arc Testnet Circle-facilitator mode is implemented behind `X402_FACILITATOR_MODE` and remains off until Circle publishes a stable Arc facilitator endpoint.
- **@prism/builder-codes** — shared workspace package for HMAC-based builder code extraction from ERC-8004 agent IDs
- **Remotion pitch video** — 90s parameterized composition at `apps/pitch-video/`, served on port 3001
- **3 Neon migrations** — `001_fill_price`, `002_requester_address`, `003_treasury_events`

### External x402 + MCP Endpoint

The sentinel is a paid public service: any external agent can pay $0.01 USDC and get an adversarial verdict. See the [Call the Sentinel Yourself](#call-the-sentinel-yourself--external-x402--mcp-demo) section below for the 3-command demo.

### Developer Docs + CLI

Developer docs are live at <https://prism-docs-production.up.railway.app>. They cover the quickstart, CLI, x402/MCP validation, public APIs, receipts, security model, and architecture.

The CLI is the developer-facing surface for pulling Prism metrics without opening the dashboard. It supports trace inspection, public stats/history, trace reports, market surfacing, token resolution, wallet funding guidance, and x402 validation orchestration. It never reads private keys: `prism validate` either submits an externally signed `X-PAYMENT` header or asks Circle CLI to sign the EIP-712 authorization with a Circle wallet.

```bash
uvx --from "prism-cli @ git+https://github.com/Fato07/prism.git#subdirectory=apps/cli" prism demo

# or, from a clone:
cd apps/cli
uv run prism --version
uv run prism doctor
uv run prism demo
uv run prism inspect ipfs://QmNzqnPEEQUMn3GMbiEZANpKXZRPmTHxVwt5nNevR8iXt8 --json
uv run prism stats
uv run prism history --limit 5
uv run prism report d6cdd60f-f5e0-43ab-ba2d-7dcab76a8e24
uv run prism markets --limit 5
uv run prism market resolve "<question from prism markets>" --json
uv run prism quote ipfs://QmNzqnPEEQUMn3GMbiEZANpKXZRPmTHxVwt5nNevR8iXt8 \
  --trace-hash 0x1a750011608a7480e9cb11f1d20587e32efb7a7dd433b85820f0dbfcdee19fdb
uv run prism validate ipfs://Qm... --trace-hash 0x... --x-payment-file ./x-payment.txt
uv run prism demo --pay --circle-address 0xYourCircleWallet --max-amount-usdc 0.01
uv run prism validate ipfs://Qm... --trace-hash 0x... \
  --circle-address 0xYourCircleWallet --max-amount-usdc 0.01
```

---

## Calibration Corpus

The calibration corpus is the sentinel's evaluation ground truth — a local-first, deterministically split, immutably sealed dataset of labeled reasoning traces. It ships as a CLI in `packages/calibration-python/`.

```bash
uv run python -m prism_calibration.cli --help
```

**Key workflows:**

1. **Build** — scaffold a new corpus with schema and split configuration
2. **Harvest** — pull real traces from Prism's activity store → IPFS → normalize → hash-verify → write local rows
3. **Label** — generate synthetic traces, mutations, or AI-prelabel existing rows (3 subcommands: `generate-synthetic`, `generate-mutations`, `prelabel`)
4. **Freeze** — export an immutable snapshot (manifest.json + rows/ + .sealed marker)
5. **Sync** — mirror the frozen export to Braintrust (datasets, review queue)
6. **Eval** — run the sentinel against the corpus and score discrimination
7. **Inspect** — examine corpus metadata, splits, and sealed milestones
8. **Validate** — run regression assertions against sealed milestones (43/43 passed across 5 milestones)

**Architecture — local-first:**

- Local frozen exports are the **authoritative** data source
- Braintrust is a **mirror and experiment surface** (datasets, experiments, review queue, runtime logs)
- Deterministic split assignment via lineage-hash-v1 (no randomness, fully reproducible)
- Holdout lockout: holdout rows are isolated from training/labeling and locked after freeze
- Immutable sealed exports: once a milestone is sealed, its rows cannot be modified
- Clean-replay regression: re-run eval on any sealed milestone and bit-compare to the original result

---

## What's Open / What's Gated

| Open | Gated (not in this repo) |
|------|--------------------------|
| ERC-8004 client & validator SDK scaffolding | Production sentinel prompts (MIPROv2-optimized) |
| Agent harness & trace generation pipeline | HMAC seed material |
| Sample reasoning traces | Circle Entity Secret & wallet private keys |
| Dashboard public routes + wallet connection | |
| Self-serve x402 validation page | |
| Builder-code attribution page | |
| Contract addresses & ABIs | |
| x402 middleware setup (dual facilitator mode) | |
| DSPy `TraceAdversary` signature | |
| Treasury dry-run scaffold (USYC park/unpark path) | |
| Calibration CLI + schemas (8 commands, 149 tests) | |

---

## On-Chain State

Both agents are registered on Arc testnet's ERC-8004 IdentityRegistry:

| Agent | agentId | Role |
|-------|---------|------|
| Trader | **4140** | Generates Trading-R1 traces, requests validation, executes paper trades, treasury operations |
| Sentinel | **4148** | Adversarially validates traces, submits verdicts on-chain |

**Contract Addresses (Arc Testnet, chain 5042002):**

| Registry | Address |
|----------|---------|
| IdentityRegistry | `0x8004A818BFB912233c491871b3d84c89A494BD9e` |
| ValidationRegistry | `0x8004Cb1BF31DAf7788923b405b754f57acEB4272` |
| ReputationRegistry | `0x8004B663056A597Dffe9eCcC1965A193B7388713` |
| ERC-8183 AgenticCommerce | `0x0747EEf0706327138c69792bF28Cd525089e4583` |

---

## Live Demo

Dashboard deployed on Railway:

**[https://prism-dashboard-production-e6e3.up.railway.app](https://prism-dashboard-production-e6e3.up.railway.app)**

The split-screen view shows the trader's reasoning trace on the left and the sentinel's adversarial challenges on the right, with on-chain validation receipts below. Connect your wallet to view your verdict history (`/me`) or submit a trace for validation (`/submit`).

---

## Call the Sentinel Yourself — External x402 + MCP Demo

Prism's sentinel is a paid public service: any external agent can pay
$0.01 USDC on Base Sepolia and get an adversarial verdict on its
reasoning trace. The flow is x402 (payment protocol) over MCP
(Model Context Protocol).

**Reference client:** [`scripts/call_prism_sentinel.py`](./scripts/call_prism_sentinel.py)

It's ~470 lines of standalone Python with PEP 723 inline dependencies —
fork it, swap the wallet/trace, point it at your own sentinel. No
Circle account, API key, or special tooling required on the caller side.

### Run it in 3 commands

```bash
# 1. First run — generates a fresh keypair, prints the address, exits cleanly
#    (the private key persists to .local/prism-client.key, gitignored)
uv run scripts/call_prism_sentinel.py

# 2. Fund the address it printed with ~0.05 USDC on Base Sepolia
#    (free from https://faucet.circle.com — select Base Sepolia + USDC)

# 3. Re-run — executes the full x402+MCP dance, saves Markdown receipt
uv run scripts/call_prism_sentinel.py
```

Expected output:

```text
Prism — external x402 + MCP demo client
========================================================

  • Loaded client wallet from .local/prism-client.key
  • Client address: 0x993F4D56e1329b6e3b91A13B9ACe1a890a023518
  • USDC balance on base-sepolia: 19.9300 USDC

  > [0/4] MCP handshake — initialize …
  ✓ Session: 468d6db939c94831853f5956…
  > [1/4] Calling sentinel /mcp with session but no payment …
  ✓ 402 received · 0.01 USDC to 0x1453ba8a… on base-sepolia
  > [2/4] Signing EIP-3009 transferWithAuthorization …
  ✓ Payment payload ready (956 char base64)
  > [3/4] Re-calling /mcp with X-PAYMENT header …
  ✓ 200 OK · response 3020 bytes
  > [4/4] Parsing verdict + saving receipt …
  ✓ Receipt: docs/demos/external-call-<timestamp>.md

  Verdict: PASS (score 65/100)
  Settlement: https://sepolia.basescan.org/tx/0xc8d5ed99…
```

### What's verifiable when you run it

- A real **EIP-3009 USDC transferWithAuthorization** signed by your client
  wallet, settled on Base Sepolia by the [x402.org public facilitator](https://www.x402.org/facilitator)
- A real **adversarial verdict** from a different model family than the
  trace's original author, pinned to IPFS
- A **committed Markdown receipt** in `docs/demos/` with all hashes and
  explorer links — shareable, screenshot-able, gitable

### How it works under the hood

See [`docs/architecture.md`](./docs/architecture.md) for the full sequence
diagram. The short version:

1. **MCP handshake** — `initialize` then `notifications/initialized` (free,
   exempt from x402 paywall so clients can establish a session)
2. **First `tools/call validate`** — sentinel returns `HTTP 402` with x402
   payment requirements in a JSON-RPC error envelope
3. **Client signs** an EIP-3009 `TransferWithAuthorization` typed-data
   payload (USDC contract on Base Sepolia, name="USDC", version="2")
4. **Second `tools/call validate`** with the base64-encoded signed
   `PaymentPayload` in the `X-PAYMENT` header
5. **Sentinel forwards** to the x402.org facilitator which submits the
   USDC transfer on Base, then runs the DSPy adversarial verdict and
  returns the result (as MCP `tools/call` SSE/JSON response)

Latest receipt: [`docs/demos/external-call-20260513T230443+0000.md`](./docs/demos/external-call-20260513T230443+0000.md)

### Why this is the integration template for other teams

- **No Circle account required on the caller side.** The example uses
  `eth_account` (pure-Python keypair management). Other teams can swap
  in their own wallet stack — MetaMask via WalletConnect, hardware
  wallets, custodial signers, whatever.
- **No special MCP knowledge required.** The handshake + tool-call shape
  is in the script verbatim.
- **Single file.** `uv run` resolves the deps inline via PEP 723. No
  `pyproject.toml`, no venv, no install step.
- **Backwards-compatible upgrade path.** Replace `base-sepolia` with
  `base` mainnet once your sentinel is wired to a mainnet x402
  facilitator (CDP from Coinbase).

---

## 📹 Pitch Video (3 min)

_Coming soon — the founder pitch will go up on YouTube before the May 25 hackathon submission. Slide animations are scaffolded with [Remotion](https://remotion.dev) in `apps/pitch-video/`._

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Trader | Python · [Mirascope](https://mirascope.com) · Claude (Anthropic) |
| Sentinel | Python · [DSPy](https://dspy.ai) · GPT-4o-mini (OpenAI) |
| Data Models | Pydantic v2 / Zod — all I/O boundaries typed |
| Chain | Circle Dev-Controlled Wallets SDK (Python) + [viem](https://viem.sh) (TypeScript) |
| IPFS | Pinata (pinning) + ipfs.io (gateway) |
| Database | Neon serverless Postgres |
| MCP | [FastMCP](https://github.com/jlowin/fastmcp) |
| Payments | [x402](https://x402.org) protocol — HTTP-native USDC micropayments (Base Sepolia public facilitator live; Arc facilitator scaffolded) |
| Polymarket | `@polymarket/clob-client-v2` (V2 SDK) |
| Dashboard | Next.js 16 · React 19 · Tailwind · shadcn/ui · wagmi v2 · Reown AppKit |
| Treasury | USYC park/unpark scaffold — dry-run until Arc Testnet token address is configured |
| Deployment | Railway (services) + Neon (DB) |
| Python toolchain | `uv` · Python 3.12+ · FastAPI · ruff · mypy |
| Node toolchain | `pnpm` · Node 20 LTS · Hono · TypeScript strict |

**Key design choice:** Trader and sentinel use **different LLM families** (Claude vs GPT). Cross-family adversarial pressure catches family-correlated reasoning failures that same-family review would miss. Enforced at startup — same family → immediate fail.

---

## Services

| Service | Stack | Key Endpoints |
|---------|-------|---------------|
| **Trader** | Python, FastAPI, Mirascope | `POST /trigger`, `GET /health`, `POST /treasury/park`, `POST /treasury/unpark` |
| **Sentinel** | Python, FastAPI, DSPy | `POST /validate`, `GET /health` |
| **Polymarket Gateway** | Node, Hono, V2 SDK | `GET /markets`, `GET /markets/recommended`, `GET /markets/resolve`, `POST /trade`, `GET /health` |
| **MCP Server** | Python, FastMCP | Live at sentinel `/mcp` — `validate`, stats, manifest, and issue-ledger tools |
| **Dashboard** | Next.js 16, React 19 | Public routes + `/api/public/stats`, `/api/public/history`, `/api/public/traces/[id]/report` |
| **CLI** | Python, Typer | `prism doctor`, `prism demo`, `prism inspect`, `prism stats`, `prism history`, `prism report`, `prism markets`, `prism market resolve`, `prism quote`, `prism validate` |
| **Pitch Video** | Remotion | `apps/pitch-video/` — parameterized 90s composition on port 3001 |

---

## Getting Started

### Prerequisites

- Python 3.12+
- Node 20 LTS or 22 LTS
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [pnpm](https://pnpm.io/) (Node package manager)

### Setup

```bash
# 1. Clone the repo
git clone https://github.com/Fato07/prism.git
cd prism

# 2. Configure environment
cp .env.example .env
# Edit .env and fill in your API keys:
#   - ANTHROPIC_API_KEY (Claude for trader)
#   - OPENAI_API_KEY (GPT for sentinel)
#   - CIRCLE_API_KEY, CIRCLE_ENTITY_SECRET, CIRCLE_WALLET_SET_ID (Circle wallets)
#   - CIRCLE_WALLET_TRADER_ID, CIRCLE_WALLET_SENTINEL_ID, CIRCLE_WALLET_ORACLE_ID
#   - PINATA_API_KEY, PINATA_SECRET_KEY, PINATA_JWT (IPFS pinning)
#   - DATABASE_URL (Neon Postgres pooled connection string)
#   - ARC_RPC_URL (Arc testnet RPC endpoint)
#   - POLY_BUILDER_CODE (Polymarket builder attribution code)
#   - TRADER_AGENT_ID, SENTINEL_AGENT_ID (ERC-8004 token IDs, after registration)
#   - X402_FACILITATOR_URL, X402_NETWORK, X402_PRICE_USDC, X402_RECIPIENT_ADDRESS (x402 config)
#   - PRISM_TRADE_MODE (paper or live — default: paper)
#   - NEXT_PUBLIC_REOWN_PROJECT_ID (Reown AppKit project ID for wallet connection)
#   - NEXT_PUBLIC_ARC_RPC_URL (Arc RPC URL exposed to the dashboard frontend)
#   - TRADER_YIELD_MODE (off, park, or smart — USYC treasury scaffold)
#   - X402_FACILITATOR_MODE (public or circle — public Base Sepolia is live; circle is scaffolded)
#   - X402_ARC_RECIPIENT_ADDRESS (USDC recipient on Arc Testnet when facilitator mode is circle)
#   - USYC_ARC_TESTNET_ADDRESS (optional USYC token contract address; empty = treasury dry-run)

# 3. Install Python dependencies
uv sync

# 4. Install Node dependencies
pnpm install

# 5. Run database migrations
#    Apply the three Neon migrations in order:
uv run python -m prism_schemas.migrations 001_fill_price
uv run python -m prism_schemas.migrations 002_requester_address
uv run python -m prism_schemas.migrations 003_treasury_events
#    Or apply all at once via Neon's SQL editor / psql using the SQL files in packages/schemas-python/migrations/
```

### Running Services

```bash
# Start all services (local dev)
docker compose up

# Or individually:
cd apps/trader && uv run uvicorn trader.main:app --port 3201          # Trader
cd apps/sentinel && uv run uvicorn sentinel.main:app --port 3202      # Sentinel
cd apps/polymarket-gateway && pnpm dev                                  # Gateway
cd apps/dashboard && pnpm dev                                           # Dashboard
cd apps/pitch-video && pnpm dev                                         # Pitch video (port 3001)
```

---

## Testing

```bash
# Python (all services)
uv run pytest

# Node (per service)
cd apps/polymarket-gateway && pnpm test
cd apps/dashboard && pnpm test
```

**Current test counts:**

| Suite | Tests |
|-------|-------|
| Dashboard | 475 |
| CLI | 10 |
| Polymarket Gateway | 93 |
| Sentinel | 118 |
| Trader | 156 |
| Calibration | 149 |
| **Total** | **1,001** |

---

## Project Structure

```
prism/
├── apps/
│   ├── trader/                   # Python · Claude · Mirascope · treasury scaffold
│   ├── sentinel/                 # Python · GPT · DSPy · x402 + MCP
│   ├── polymarket-gateway/       # Node · Hono · V2 SDK
│   ├── dashboard/                # Next.js 16 · React 19 · wagmi · Reown AppKit
│   └── pitch-video/              # Remotion 90s pitch
├── packages/
│   ├── schemas-python/           # Pydantic v2 models (Trace, Verdict, Feedback)
│   ├── schemas-typescript/       # Zod mirrors of Python schemas
│   ├── arc-contracts/            # Contract addresses + ABIs
│   ├── builder-codes/           # HMAC-based builder code extraction from ERC-8004 agent IDs
│   └── calibration-python/      # Calibration corpus CLI — build, harvest, label, freeze, sync, eval, inspect, validate
├── tests/                        # E2E pipeline integration
├── docs/                         # Architecture, demo receipts, puzzle submissions
└── infra/                        # Circle setup, Arc CLI wrappers
```

---

## Circle Products

| Product | Usage |
|---------|-------|
| **Programmable Wallets** | Every ERC-8004 tx goes through a Developer-Controlled Wallet (EOA on Arc Testnet) |
| **Contract Execution** | `register`, `validationRequest`, `validationResponse`, `giveFeedback` via Circle SDK |
| **Native USDC** (Arc) | Gas token — all costs denominated in USDC |
| **Gas Station** | Future SCA migration path; Phase 0 wallets are EOA and pay their own Arc gas in USDC |
| **Nanopayments** (x402) | Sentinel charges $0.01 USDC/validation via HTTP 402 using the public Base Sepolia facilitator |
| **App Kit Bridge** | Conditional bridge widget on `/submit` — guides users toward Base Sepolia testnet USDC |
| **Circle Facilitator** | Arc Testnet x402 mode is scaffolded but disabled until a stable public Arc facilitator endpoint is available |

---

## Key Schemas

**Trading-R1 Trace** (Trader → Sentinel): `trace_id`, `agent_id` (ERC-8004 tokenId), `thesis` (proposition→evidence→risk), `evidence` (source, claim, confidence), `final_probability`, `action` (BUY/SELL/HOLD), `size_usdc`, `model_family`

**Sentinel Verdict** (Sentinel → On-chain): `request_hash` (on-chain), `evidence_challenges`, `thesis_challenges`, `calibration_critique`, `verdict_score` (0–100), `verdict_label` (REJECT/WARN/PASS/ENDORSE), `dialogue_messages`

Full Pydantic models in [`packages/schemas-python/`](packages/schemas-python/).

---

## Database Migrations

Three Neon migrations ship with the traction sprint:

| Migration | Description |
|-----------|-------------|
| `001_fill_price` | Adds `fill_price` column to trades table for tracking paper/live fill prices |
| `002_requester_address` | Adds `requester_address` column to validations table for wallet-connected attribution |
| `003_treasury_events` | Creates `treasury_events` table for USYC park/unpark audit trail |

Apply them in order via the migration runner or directly through Neon's SQL editor using the files in `packages/schemas-python/migrations/`.

---

## ERC-8004 ↔ Polymarket Identity Bridge

Polymarket lives on Polygon, not Arc. Prism uses a **deterministic mapping**: the builder code is computed as the last 32 bytes of an HMAC over `(agentId, salt)`. The agent card pinned to IPFS publishes the salt, so anyone can verify which Arc `agentId` corresponds to which Polymarket builder attribution — on-chain identity surfaces in off-chain systems via deterministic derivation, not custodial bridging.

The shared `@prism/builder-codes` package (`packages/builder-codes/`) provides the HMAC extraction logic for both Python and TypeScript consumers.

---

## Research Lineage

- Irving et al. 2018 — *AI Safety via Debate*
- Du et al. 2023 — *Multiagent Debate*
- NeurIPS 2025 — *LLM Judge Debate*
- Trading-R1 (TauricResearch) — structured reasoning for trading agents
- [ERC-8004 specification](https://eips.ethereum.org/EIPS/eip-8004) — on-chain agent identity and validation

---

## Hackathon

Prism is built for the **Agora Agent Hackathon** (Canteen × Circle × Arc), May 11–25, 2026.

---

## Security

- Trader wallet cap: **100 USDC** (max 25% per trade)
- Sentinel wallet cap: **50 USDC**
- All chain ops via Circle Programmable Wallets — **no raw private keys in code**
- API keys in `.env` (gitignored), `.env.example` as template
- Polymarket geofencing enforced at startup
- EIP-3009 signed transfers only — no raw key exposure in the browser

---

## Links

- [ERC-8004 Specification](https://eips.ethereum.org/EIPS/eip-8004)
- [Arc Documentation](https://docs.arc.network/)
- [Circle Developer Docs](https://developers.circle.xyz/)

---

## License

[Apache-2.0](LICENSE)

---

*Prism — See through the reasoning.*
