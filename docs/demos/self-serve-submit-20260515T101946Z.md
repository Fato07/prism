# Prism — first self-serve validation by a connected wallet

**When:** 2026-05-15T10:19:46Z (Day 5 of the Agora hackathon)

**Where:** [`https://prism-dashboard-production-e6e3.up.railway.app/submit`](https://prism-dashboard-production-e6e3.up.railway.app/submit)

This is the first end-to-end run where a real human connected a wallet, paid 0.01 USDC via x402, and got an adversarial verdict back — entirely through the public dashboard, no scripts, no API keys.

---

## What happened

1. Visitor opened `/submit` on the production dashboard
2. Connected MetaMask via Reown AppKit (Base Sepolia)
3. Funded their wallet with 20 USDC from `https://faucet.circle.com`
4. Pasted IPFS CID:
   ```txt
   QmNzqnPEEQUMn3GMbiEZANpKXZRPmTHxVwt5nNevR8iXt8
   ```
5. Clicked **Validate**
6. Signed an EIP-3009 `transferWithAuthorization` for 0.01 USDC in MetaMask
7. The dashboard relayed the signed payment to the sentinel's MCP `/mcp/` endpoint
8. The sentinel forwarded the payment to the public x402.org facilitator
9. Settlement landed on Base Sepolia
10. The sentinel pulled the trace from IPFS, ran an adversarial DSPy + GPT verdict, pinned the verdict back to IPFS
11. The dashboard redirected the visitor to the new verdict permalink

Total user-visible time: under 30 seconds from clicking Validate to landing on the verdict page.

---

## Receipts

| Field | Value |
|---|---|
| Connected wallet (payer) | [`0xaf131B054B08E57c20b31080A1Ffd406e429db6F`](https://sepolia.basescan.org/address/0xaf131B054B08E57c20b31080A1Ffd406e429db6F) |
| Recipient (sentinel) | [`0xaf131B054B08E57c20b31080A1Ffd406e429db6F`](https://sepolia.basescan.org/address/0xaf131B054B08E57c20b31080A1Ffd406e429db6F) |
| Amount paid | 0.01 USDC |
| Network | Base Sepolia (chain 84532) |
| USDC contract | [`0x036CbD53842c5426634e7929541eC2318f3dCF7e`](https://sepolia.basescan.org/address/0x036CbD53842c5426634e7929541eC2318f3dCF7e) |
| **x402 settlement tx (Base Sepolia)** | [`0x63bf70941e8890b2b92459addfa18ecb57dd06bba7ea715391f00322faf58d68`](https://sepolia.basescan.org/tx/0x63bf70941e8890b2b92459addfa18ecb57dd06bba7ea715391f00322faf58d68) |
| Facilitator | x402.org public facilitator |
| Sentinel endpoint | `https://prism-sentinel-production.up.railway.app/mcp/` |
| Sentinel agent ID (ERC-8004) | 4148 |
| Trace IPFS | [`QmNzqnPEEQUMn3GMbiEZANpKXZRPmTHxVwt5nNevR8iXt8`](https://gateway.pinata.cloud/ipfs/QmNzqnPEEQUMn3GMbiEZANpKXZRPmTHxVwt5nNevR8iXt8) |
| Trace ID | `d6cdd60f-f5e0-43ab-ba2d-7dcab76a8e24` |
| **Verdict score** | **65 / 100 PASS** |
| Verdict IPFS | [`QmZstzFWhWhRVrpYoHxhV5qfMzjvM91zkG66QDxkTk1RSb`](https://gateway.pinata.cloud/ipfs/QmZstzFWhWhRVrpYoHxhV5qfMzjvM91zkG66QDxkTk1RSb) |
| **Verdict permalink** | [`/trace/d6cdd60f-f5e0-43ab-ba2d-7dcab76a8e24`](https://prism-dashboard-production-e6e3.up.railway.app/trace/d6cdd60f-f5e0-43ab-ba2d-7dcab76a8e24) |
| Visible on `/me` | Yes — `/api/verdicts/by-address?address=0xaf131B054B08E57c20b31080A1Ffd406e429db6F` returns this row |

---

## Why this matters

This is the loop the hackathon judges said they wanted to see:

> "Real users, real transactions, real volume during the event window. Great founders ship and get users in two weeks."

Up to this point Prism's traction was internally generated traces (the trader auto-pipeline), one external x402 call from our own demo client (`scripts/call_prism_sentinel.py`), and a couple of paper trades. This receipt is qualitatively different: a human used the public product, paid stablecoin into the system, and got a verifiable on-chain settlement plus an adversarial verdict back.

It also closes the **self-serve** loop:

- No API keys
- No allowlist
- No backend account
- Just a wallet, USDC on Base Sepolia, and an IPFS CID

That is the Agora "agents talking to agents" thesis in product form, except the first agent here was a person.

---

## Bugs surfaced and fixed during this test

This run was the forcing function for two real fixes that were merged the same hour:

1. **`48ce823 fix(dashboard): don't bridge from Base Sepolia to itself on submit`**
   - The Circle App Kit Bridge widget tried to bridge `Base Sepolia → Base Sepolia` when the wallet was already on the payment chain
   - Now it shows a faucet/funding affordance instead

2. **`02f5b12 fix(dashboard): emit full x402 v2 payment payload from submit form`**
   - The browser was sending only `{authorization, signature}` but the public facilitator requires the full x402 v2 envelope (`x402Version: 2`, `payload`, `accepted`, `resource`, `extensions`)
   - Now the dashboard emits the same shape the official Python SDK produces, matching `scripts/call_prism_sentinel.py`

3. **`cd092f4 fix(mcp): persist x402 payer address as requester_address in validations`**
   - The MCP `validate` tool was capturing payment tx hash but not the payer address
   - Fixed so future self-serve runs auto-attach to `/me`
   - This row was backfilled by hand with the known payer

---

## What this unlocks for the submission

- A receipt we can cite in `arc-canteen update traction` under RFB 02 and RFB 06
- A real number for the "active users" traction metric: 1, going up
- Concrete demo footage for the pitch video (the connect → fund → submit → verdict loop is the entire elevator pitch)
- Validation of the x402 self-serve thesis without needing custom Solidity, custodial accounts, or any pre-shared credentials
