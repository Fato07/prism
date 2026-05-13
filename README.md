# Prism — The First Adversarial AI Validator on ERC-8004

> Two AI agents debate your trade reasoning on-chain. One generates. One challenges. Both are accountable.

[![Live Demo](https://img.shields.io/badge/demo-live-brightgreen)](https://prism-dashboard-production-e6e3.up.railway.app)
[![Pitch Video](https://img.shields.io/badge/pitch_video-90s-red)](https://youtube.com/watch?v=PLACEHOLDER)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![Arc Testnet](https://img.shields.io/badge/chain-Arc_Testnet_(5042002)-purple)](https://docs.arc.network/)

**Prism** is an adversarial AI validation system built on [ERC-8004](https://eips.ethereum.org/EIPS/eip-8004). A **Trader** agent (Claude/Mirascope) generates structured reasoning traces for prediction markets. A **Sentinel** agent (GPT/DSPy) adversarially challenges every claim. Both are registered on-chain, every validation is anchored on Arc testnet, and the sentinel is exposed as an x402-protected service other agents can call.

> *Prism makes AI agents accountable to other AI agents.*

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
           │                                        │
  Polymarket V2 SDK                                 ▼
  (builder code)                           x402-protected MCP
           │                               ($0.01 USDC/validation)
           ▼                                        │
  Polymarket CLOB (Polygon)                         │
                                                      │
                              ┌───────────────────────┘
                              ▼
                    Dashboard (Next.js 16)
                    split-screen dialogue + on-chain receipts
```

---

## Data Flow

1. Fetch Polymarket market → 2. Trader generates Trading-R1 trace → 3. Pin to IPFS → 4. Persist to Postgres → 5. On-chain `validationRequest` → 6. Sentinel challenges trace → 7. Verdict + dialogue → 8. Pin to IPFS → 9. Persist to Postgres → 10. On-chain `validationResponse` → 11. Paper trade with builder code → 12. Dashboard display

---

## What's Open / What's Gated

| Open | Gated (not in this repo) |
|------|--------------------------|
| ERC-8004 client & validator SDK scaffolding | Full calibration corpus (eval ground truth) |
| Agent harness & trace generation pipeline | Production sentinel prompts (MIPROv2-optimized) |
| Sample reasoning traces | HMAC seed material |
| Dashboard (split-screen dialogue + receipts) | Circle Entity Secret & wallet private keys |
| Contract addresses & ABIs | |
| x402 middleware setup | |
| DSPy `TraceAdversary` signature | |

---

## On-Chain State

Both agents are registered on Arc testnet's ERC-8004 IdentityRegistry:

| Agent | agentId | Role |
|-------|---------|------|
| Trader | **4062** | Generates Trading-R1 traces, requests validation, executes paper trades |
| Sentinel | **4070** | Adversarially validates traces, submits verdicts on-chain |

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

The split-screen view shows the trader's reasoning trace on the left and the sentinel's adversarial challenges on the right, with on-chain validation receipts below.

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

## 📹 Pitch Video (90s)

**[▶ Watch the Pitch on YouTube](https://youtube.com/watch?v=PLACEHOLDER)**

A 90-second walkthrough covering: the problem (AI reasoning is unauditable), the two-agent adversarial solution (Claude trader vs GPT sentinel), on-chain proof on Arc with ERC-8004, Polymarket builder attribution, x402 sentinel-as-a-service, and five Circle products powering the stack.

Video generated with [Remotion](https://remotion.dev) — see `apps/pitch-video/` and `docs/pitch-script.md` for the source.

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
| Payments | [x402](https://x402.org) protocol — HTTP-native USDC micropayments |
| Polymarket | `@polymarket/clob-client-v2` (V2 SDK) |
| Dashboard | Next.js 16 · React 19 · Tailwind · shadcn/ui |
| Deployment | Railway (services) + Neon (DB) |
| Python toolchain | `uv` · Python 3.12+ · FastAPI · ruff · mypy |
| Node toolchain | `pnpm` · Node 20 LTS · Hono · TypeScript strict |

**Key design choice:** Trader and sentinel use **different LLM families** (Claude vs GPT). Cross-family adversarial pressure catches family-correlated reasoning failures that same-family review would miss. Enforced at startup — same family → immediate fail.

---

## Services

| Service | Stack | Key Endpoints |
|---------|-------|---------------|
| **Trader** | Python, FastAPI, Mirascope | `POST /trigger`, `GET /health` |
| **Sentinel** | Python, FastAPI, DSPy | `POST /validate`, `GET /health` |
| **Polymarket Gateway** | Node, Hono, V2 SDK | `GET /markets`, `POST /trade`, `GET /health` |
| **MCP Server** | Python, FastMCP | Live at sentinel `/mcp` — `tools/list` and `tools/call` work |
| **Dashboard** | Next.js 16, React 19 | Split-screen trace + verdict view |

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

# 3. Install Python dependencies
uv sync

# 4. Install Node dependencies
pnpm install
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

---

## Project Structure

```
prism/
├── apps/
│   ├── trader/                   # Python · Claude · Mirascope
│   ├── sentinel/                 # Python · GPT · DSPy
│   ├── polymarket-gateway/       # Node · Hono · V2 SDK
│   ├── dashboard/                # Next.js 16 · React 19
│   └── pitch-video/              # Remotion 90s pitch
├── packages/
│   ├── schemas-python/           # Pydantic v2 models (Trace, Verdict, Feedback)
│   ├── schemas-typescript/       # Zod mirrors of Python schemas
│   └── arc-contracts/            # Contract addresses + ABIs
├── tests/                        # E2E pipeline integration
├── docs/                         # Architecture, demo script, traction log
└── infra/                        # Circle setup, Arc CLI wrappers
```

---

## Circle Products

| Product | Usage |
|---------|-------|
| **Programmable Wallets** | Every ERC-8004 tx goes through a Developer-Controlled Wallet (SCA on Arc) |
| **Contract Execution** | `register`, `validationRequest`, `validationResponse`, `giveFeedback` via Circle SDK |
| **Native USDC** (Arc) | Gas token — all costs denominated in USDC |
| **Gas Station** | Gasless trader contract executions (Phase 1) |
| **Nanopayments** (x402) | Sentinel charges $0.01 USDC/validation via HTTP 402 + Circle settlement |

---

## Key Schemas

**Trading-R1 Trace** (Trader → Sentinel): `trace_id`, `agent_id` (ERC-8004 tokenId), `thesis` (proposition→evidence→risk), `evidence` (source, claim, confidence), `final_probability`, `action` (BUY/SELL/HOLD), `size_usdc`, `model_family`

**Sentinel Verdict** (Sentinel → On-chain): `request_hash` (on-chain), `evidence_challenges`, `thesis_challenges`, `calibration_critique`, `verdict_score` (0–100), `verdict_label` (REJECT/WARN/PASS/ENDORSE), `dialogue_messages`

Full Pydantic models in [`packages/schemas-python/`](packages/schemas-python/).

---

## ERC-8004 ↔ Polymarket Identity Bridge

Polymarket lives on Polygon, not Arc. Prism uses a **deterministic mapping**: the builder code is computed as the last 32 bytes of an HMAC over `(agentId, salt)`. The agent card pinned to IPFS publishes the salt, so anyone can verify which Arc `agentId` corresponds to which Polymarket builder attribution — on-chain identity surfaces in off-chain systems via deterministic derivation, not custodial bridging.

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

| Criterion | Weight | Prism's Strength |
|-----------|--------|-----------------|
| Agentic Sophistication | 30% | Two-agent adversarial system, cross-model validation, MCP-as-a-service |
| Traction | 30% | X threads, Discord engagement, waitlist, sentinel calls from external agents |
| Circle Tool Usage | 20% | Programmable Wallets, contract execution, native USDC, Paymaster, Nanopayments |
| Innovation | 20% | First adversarial AI validator on ERC-8004, first identity bridge to prediction markets |

---

## Security

- Trader wallet cap: **100 USDC** (max 25% per trade)
- Sentinel wallet cap: **50 USDC**
- All chain ops via Circle Programmable Wallets — **no raw private keys in code**
- API keys in `.env` (gitignored), `.env.example` as template
- Polymarket geofencing enforced at startup

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
