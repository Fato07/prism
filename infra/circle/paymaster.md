# Circle Gas Station on Arc Testnet — Prism Paymaster Setup

This document describes how Prism uses **Circle Gas Station** to deliver
gasless ERC-8004 operations on Arc Testnet, which wallets are covered, the
sponsorship policy in effect, and how this surfaces in the demo.

---

## 1. How Gas Station Is Enabled

Circle Gas Station is configured **per project, per chain** in the Circle
Developer Console (or via the Circle API). For Prism on Arc Testnet, the
operator enables sponsorship for the project's developer-controlled wallet set
under **Wallets → Gas Station → Arc Testnet**.

Steps to enable:

1. Sign in to the Circle Developer Console with the project owner account.
2. Navigate to **Wallets → Gas Station**.
3. Select **Arc Testnet** as the chain.
4. Choose **Sponsor all wallets in this wallet set** (recommended for Prism;
   covers trader, sentinel, and oracle wallets in one switch) and set the
   policy scope to **All contract executions** so that ERC-8004
   `register`, `validationRequest`, `validationResponse`, and `giveFeedback`
   calls are all covered.
5. Save. Sponsorship becomes active immediately for new transactions; previous
   transactions are not retroactively re-priced.

No on-chain Paymaster contract needs to be deployed and no `paymaster` field
needs to be passed into the SDK — Circle's infrastructure intercepts the
EIP-4337 UserOperation or wraps the EOA transaction with sponsored gas
on the bundler layer.

Prism's `CircleChain.execute_contract()` does accept an optional
``paymaster`` parameter for forward-compatibility with environments such as
Base mainnet, where per-call sponsor addresses may be required in a future
phase. On Arc Testnet, this parameter is logged for observability but
otherwise ignored — sponsorship is implicit.

## 2. Wallets Covered

The Gas Station policy applies to the project's wallet set
(`CIRCLE_WALLET_SET_ID`), which contains three wallets used by Prism:

| Role     | Env var (id)                       | Env var (address)                       |
| -------- | ---------------------------------- | --------------------------------------- |
| Trader   | `CIRCLE_WALLET_TRADER_ID`          | `CIRCLE_WALLET_TRADER_ADDRESS`          |
| Sentinel | `CIRCLE_WALLET_SENTINEL_ID`        | `CIRCLE_WALLET_SENTINEL_ADDRESS`        |
| Oracle   | `CIRCLE_WALLET_ORACLE_ID`          | `CIRCLE_WALLET_ORACLE_ADDRESS`          |

All three are developer-controlled wallets on Arc Testnet
(`blockchain = "ARC-TESTNET"`). For Prism Phase 1, the trader and sentinel
wallets are the active surfaces for sponsored gas — the oracle wallet only
writes to `ReputationRegistry` in Phase 2.

## 3. Sponsorship Policy

The default policy used by Prism is:

- **Scope:** all wallets in the configured wallet set.
- **Coverage:** all contract executions on Arc Testnet, including
  `register`, `validationRequest`, `validationResponse`, and
  `giveFeedback`, plus USDC token transfers via
  `CircleChain.transfer_usdc()`.
- **Cap:** Circle imposes a testnet-side rate limit, but for Prism's
  expected volume (≤ 100 transactions/day across all wallets) we run well
  within the free tier. There is no per-wallet USDC cap enforced by
  Prism — wallet caps are enforced upstream in business logic
  (trader ≤ 100 USDC balance, sentinel ≤ 50 USDC).
- **Verification:** the Circle Transaction object exposes a
  `network_fee` field. When sponsorship is active, this field is `0` (or
  near-zero up to rounding tolerance). Prism's gas-station integration
  tests in `apps/trader/src/tests/test_gas_station.py` assert this
  invariant.

If sponsorship is not active for a wallet (e.g. the operator has not yet
enabled the policy in Circle Console), the gas-station tests skip with a
clear message pointing back to this document. The implementation itself
does not depend on the policy being active — it works identically whether
the wallet pays gas in USDC or sponsorship covers it.

## 4. Demo Bullet — "Trader Operates Gasless"

Prism's pitch surface for judges includes the line **"the trader operates
gasless on Arc"**. The on-chain evidence:

- The Arc testnet explorer transaction page shows `gas paid by sponsor`
  (or, equivalently, the wallet's USDC balance is unchanged before and
  after `register()` / `validationRequest()` / `validationResponse()`
  calls).
- The Circle Transaction API returns `network_fee = "0"` for sponsored
  transactions on Arc Testnet, which Prism's dashboard surfaces as a
  "Gas Sponsored by Circle" badge next to each on-chain receipt.

This locks in two Circle product surfaces for the hackathon scoring:
**Programmable Wallets** (for the contract execution itself) and
**Gas Station** (for the sponsorship). Combined with **USDC as native
gas**, the trader-runs-gasless story is the centerpiece of the Circle
stack section of the demo.

---

*Last updated: May 12, 2026 — Prism Phase 1, Milestone "live-trading".*
