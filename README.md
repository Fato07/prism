# Prism

> **The first adversarial AI validator on ERC-8004 — two agents debate your trade reasoning on-chain.**

[![Live Demo](https://img.shields.io/badge/demo-live-brightgreen)](https://prism-dashboard-production-e6e3.up.railway.app)
[![Pitch Video](https://img.shields.io/badge/pitch_video-90s-red)](https://youtube.com/watch?v=PLACEHOLDER)
[![Python Tests](https://img.shields.io/badge/python_tests-177+-blue)](https://github.com/Fato07/prism)
[![Node Tests](https://img.shields.io/badge/node_tests-74-blue)](https://github.com/Fato07/prism)
[![Arc Testnet](https://img.shields.io/badge/chain-Arc_Testnet_(5042002)-purple)](https://docs.arc.network/)

---

## What is Prism?

Autonomous AI trading agents are starting to hold real capital and move real markets. Today, nobody can audit whether their **reasoning** is sound — only whether their P&L is positive. If an agent gets lucky with bad reasoning, current systems give it a high score. If an agent reasons brilliantly but takes a costly position that hasn't resolved yet, current systems give it no credit.

**Prism fixes this** with a two-agent adversarial system on Arc testnet:

- **Trader** (Claude family / Mirascope) generates structured Trading-R1 reasoning traces for Polymarket markets
- **Sentinel** (GPT family / DSPy) adversarially challenges every evidence claim, probability calibration, and decision step
- **Both registered on ERC-8004** — the sentinel validates via `ValidationRegistry`, where the spec forbids self-validation
- **Paper trading on Polymarket** with builder code attribution derived from on-chain identity
- **Every dialogue pinned to IPFS**, every validation anchored on-chain — sub-$0.01 gas on Arc

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
  ┌──────────────────┐                     ┌──────────────────┐
  │ Mirascope        │   Trading-R1 trace  │ DSPy             │
  │ Claude family    │ ─────────────────▶  │ GPT-4o-mini      │
  │ Trading-R1 schema│   IPFS (Pinata)     │ TraceAdversary   │
  └──────────────────┘                     │ MIPROv2 optimized │
           │                               └──────────────────┘
           ▼                                        │
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

## Data Flow (12 Steps)

Every trade follows this pipeline end-to-end:

| Step | Action | Where |
|------|--------|-------|
| 1 | Fetch Polymarket market question | Polymarket CLOB API |
| 2 | Trader generates Trading-R1 reasoning trace | `apps/trader` (Claude/Mirascope) |
| 3 | Pin trace to IPFS | Pinata |
| 4 | Persist trace metadata to Neon Postgres | `DATABASE_URL` |
| 5 | Submit on-chain `validationRequest` | ValidationRegistry via Circle SDK |
| 6 | Sentinel fetches trace and adversarially challenges | `apps/sentinel` (GPT/DSPy) |
| 7 | Generate verdict with dialogue | Sentinel agent |
| 8 | Pin verdict + dialogue to IPFS | Pinata |
| 9 | Persist verdict metadata to Neon Postgres | `DATABASE_URL` |
| 10 | Submit on-chain `validationResponse` | ValidationRegistry via Circle SDK |
| 11 | Execute paper trade with builder code attribution | Polymarket CLOB V2 |
| 12 | Display trace + verdict + on-chain receipts | Dashboard |

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

## 📹 Pitch Video (90s)

**[▶ Watch the Pitch on YouTube](https://youtube.com/watch?v=PLACEHOLDER)**

A 90-second walkthrough covering: the problem (AI reasoning is unauditable), the two-agent adversarial solution (Claude trader vs GPT sentinel), on-chain proof on Arc with ERC-8004, Polymarket builder attribution, x402 sentinel-as-a-service, and five Circle products powering the stack.

Video generated with [Remotion](https://remotion.dev) — see `apps/pitch-video/` and `docs/pitch-script.md` for the source.

---

## Tech Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Trader LLM | Mirascope + Claude (Anthropic API) | Pydantic-native structured outputs |
| Sentinel LLM | DSPy + GPT-4o-mini (OpenAI API) | Typed Signatures, MIPROv2 optimizer |
| Data Models | Pydantic v2 / Zod | All I/O boundaries typed |
| Chain Interaction | Circle Dev-Controlled Wallets SDK (Python) + viem (TypeScript) | No raw private keys |
| IPFS Pinning | Pinata (free tier) | Reliable, hash returned immediately |
| Database | Neon serverless Postgres (pooled) | Scale-to-zero, branching, pgvector |
| MCP Server | FastMCP | Sentinel-as-a-service for other agents |
| Agent Payments | x402 protocol | HTTP-native USDC micropayments |
| Polymarket | `@polymarket/clob-client-v2` | Official V2 SDK with builder code |
| Dashboard | Next.js 16 + React 19 + Tailwind + shadcn/ui | Modern server components |
| Observability | OpenTelemetry → Honeycomb | Trace every agent step |
| Deployment | Railway (services) + Neon (DB) | Polyglot, private inter-service network |
| Python | `uv`, Python 3.12+, FastAPI | Fast, modern toolchain |
| Node | `pnpm`, Node 20 LTS, Hono, TypeScript strict | Type-safe, fast |

**Key design choice:** Trader and sentinel use **different LLM families** (Claude vs GPT). Cross-family adversarial pressure catches family-correlated reasoning failures that same-family review would miss. This is enforced at startup — if both are configured to the same family, the system fails immediately.

---

## Services

| Service | Stack | Port | Endpoints |
|---------|-------|------|-----------|
| **Trader** | Python, FastAPI, Mirascope | 3201 | `POST /trigger`, `GET /health` |
| **Sentinel** | Python, FastAPI, DSPy | 3202 | `POST /validate`, `GET /health` |
| **Polymarket Gateway** | Node, Hono, V2 SDK | 3203 | `GET /markets`, `POST /trade`, `GET /health` |
| **Dashboard** | Next.js 16, React 19 | 3200 | Split-screen trace + verdict view |

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

# 3. Install Python dependencies
uv sync

# 4. Install Node dependencies
pnpm install
```

### Running Services

```bash
# Start all services (local dev)
docker compose up

# Or start individually:

# Trader
cd apps/trader && uv run uvicorn trader.main:app --port 3201

# Sentinel
cd apps/sentinel && uv run uvicorn sentinel.main:app --port 3202

# Polymarket Gateway
cd apps/polymarket-gateway && pnpm dev

# Dashboard
cd apps/dashboard && pnpm dev
```

---

## Testing

### Python Tests

```bash
# Run all Python tests (177+ tests)
uv run pytest

# Run with markers
uv run pytest -m "not integration"    # unit tests only
uv run pytest -m "not slow"           # skip slow LLM/on-chain tests
```

Test suites:
- `apps/trader/src/tests/` — trace generation, schema validation, registration, on-chain validation, infrastructure
- `apps/sentinel/src/tests/` — sentinel validation, calibration (good/mediocre/bad traces)
- `packages/schemas-python/src/tests/` — Pydantic schema validation
- `tests/` — E2E pipeline integration

### Node Tests

```bash
# Gateway tests (44 tests)
cd apps/polymarket-gateway && pnpm test

# Dashboard tests (30 tests)
cd apps/dashboard && pnpm test
```

Test suites:
- `apps/polymarket-gateway/tests/` — API routes, builder code, trade sizing, market queries, trade logic
- `apps/dashboard/__tests__/` — components, utilities, schema validation

---

## Project Structure

```
prism/
├── apps/
│   ├── trader/                   # Python · Claude family · Mirascope
│   │   ├── src/trader/
│   │   │   ├── agent.py          # main agent loop
│   │   │   ├── trading_r1.py     # Trading-R1 trace generation
│   │   │   ├── prompts.py        # system prompts
│   │   │   └── tools/            # market lookup, data tools
│   │   └── src/tests/
│   │
│   ├── sentinel/                 # Python · GPT family · DSPy
│   │   ├── src/sentinel/
│   │   │   ├── agent.py          # adversarial validation agent
│   │   │   ├── adversarial.py    # DSPy TraceAdversary signature
│   │   │   ├── prompts.py        # adversarial prompt suite
│   │   │   └── validation.py     # ValidationRegistry interaction
│   │   └── src/tests/
│   │
│   ├── polymarket-gateway/       # Node · Hono · V2 SDK
│   │   └── src/
│   │       ├── index.ts          # Hono server
│   │       ├── clob.ts           # V2 client wrapper
│   │       └── builder.ts        # builderCode mapping logic
│   │
│   └── dashboard/                # Next.js 16 · React 19 · Tailwind
│       └── app/
│           ├── page.tsx          # split-screen dialogue + receipts
│           ├── traces/[id]/      # individual trace detail
│           ├── api/              # API routes
│           └── components/       # shadcn/ui + custom components
│
├── packages/
│   ├── schemas-python/           # Pydantic v2 models (Trace, Verdict, Feedback)
│   ├── schemas-typescript/       # Mirror schemas via Zod
│   └── arc-contracts/            # Contract addresses + ABIs (no source code)
│
├── tests/
│   └── test_e2e_pipeline.py     # End-to-end pipeline integration test
│
├── .env.example                  # Environment variable template
├── pyproject.toml                # Python workspace config (uv)
├── package.json                  # Node workspace config (pnpm)
└── docker-compose.yml            # Local development orchestration
```

---

## Circle Product Surface

Prism integrates multiple Circle products — visible in the demo, essential to the architecture:

1. **Programmable Wallets** — every ERC-8004 contract call goes through a Developer-Controlled Wallet (SCA on Arc)
2. **Contract Execution** — `register`, `validationRequest`, `validationResponse`, `giveFeedback` all via Circle SDK
3. **Native USDC** — Arc's gas token, all costs denominated in USDC
4. **Paymaster** (Phase 1) — gasless trader operations
5. **Nanopayments** (Phase 1) — sentinel charges $0.01 USDC/validation via x402 + Circle settlement

---

## Key Schemas

### Trading-R1 Trace (Trader Output)

```python
class TradingR1Trace(BaseModel):
    trace_id: str                     # UUID
    agent_id: int                     # ERC-8004 tokenId
    market_id: str                    # Polymarket condition ID
    market_question: str
    thesis: list[ThesisStep]          # proposition → evidence → risk
    evidence: list[Evidence]          # source, claim, confidence, timestamp
    raw_probability: float            # [0.0, 1.0]
    volatility_adjustment: float
    final_probability: float          # [0.0, 1.0]
    action: Literal['BUY', 'SELL', 'HOLD']
    size_usdc: float
    price_limit: float
    rationale: str
    model_family: Literal['anthropic-claude', 'openai-gpt']
    created_at: datetime
```

### Sentinel Verdict (Sentinel Output)

```python
class SentinelVerdict(BaseModel):
    request_hash: bytes               # on-chain request hash
    trace_id: str
    sentinel_agent_id: int
    evidence_challenges: list[str]    # specific claims questioned
    thesis_challenges: list[str]      # reasoning steps challenged
    calibration_critique: str        # probability calibration audit
    verdict_score: int                # 0–100 (0=reject, 100=endorse)
    verdict_label: Literal['REJECT', 'WARN', 'PASS', 'ENDORSE']
    dialogue_messages: list[dict]    # full trader↔sentinel exchange
    model_family: Literal['anthropic-claude', 'openai-gpt']
    created_at: datetime
```

---

## ERC-8004 ↔ Polymarket Identity Bridge

Polymarket lives on Polygon, not Arc, so there is no literal cross-chain bridge. Instead, Prism uses a **deterministic mapping**: the builder code is computed as the last 32 bytes of an HMAC over `(agentId, salt)`. The agent card pinned to IPFS publishes the salt, so anyone can verify which Arc `agentId` corresponds to which Polymarket builder attribution. This is the same pattern as ENS resolvers or Farcaster frame attribution — on-chain identity surfaces in off-chain systems via deterministic derivation, not custodial bridging.

---

## Research Lineage

Prism builds on established adversarial AI research:

- Irving et al. 2018 — *AI Safety via Debate*
- Du et al. 2023 — *Multiagent Debate*
- NeurIPS 2025 — *LLM Judge Debate*
- Trading-R1 (TauricResearch) — structured reasoning for trading agents
- ERC-8004 specification — on-chain agent identity and validation

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

- Trader wallet balance cap: **100 USDC** (max 25% per trade)
- Sentinel wallet balance cap: **50 USDC**
- All chain ops via **Circle Programmable Wallets** — no raw private keys in code
- All API keys in `.env` (gitignored), with `.env.example` as template
- Env vars referencing keys end in `_KEY`, `_SECRET`, or `_API_KEY`
- Polymarket geofencing enforced at startup (Estonia verified eligible)
- No agent has direct private key access

---

## License

Private repository. All rights reserved.

---

*Prism — See through the reasoning.*
