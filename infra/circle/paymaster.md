# Circle Gas Station / Paymaster Notes

Prism **does not use Gas Station sponsorship in Phase 0**.

Current production wallets on Arc Testnet are Circle Developer-Controlled
Wallets with `accountType = EOA`. These wallets pay their own Arc gas in USDC.
Recent ERC-8004 contract executions have been cheap enough for the hackathon
flow (roughly a few thousandths of a USDC per call), so sponsorship is not a
Phase 0 dependency.

## Current model

| Item | Status |
|---|---|
| Wallet custody | Circle Developer-Controlled Wallets |
| Account type | EOA |
| Chain | Arc Testnet |
| Gas token | USDC |
| Gas payer | The trader/sentinel/oracle wallet itself |
| Custom paymaster contract | None |
| Gas Station sponsorship | Deferred |

## Why sponsorship is deferred

Circle Gas Station sponsorship requires an SCA/MSCA-style wallet path. The
wallets created for the Phase 0 demo are EOAs, and Circle does not offer an
in-place EOA → SCA migration for the current wallet set. A migration would mean:

1. Create fresh SCA/MSCA wallets.
2. Fund them.
3. Re-register agents on ERC-8004.
4. Update Railway env vars and public docs.
5. Re-run the on-chain receipt flow.

That is post-hackathon work, not required for the current self-serve x402 demo.

## Future migration checklist

- [ ] Create SCA/MSCA Circle wallets for trader, sentinel, and oracle.
- [ ] Enable Gas Station policy for Arc Testnet in Circle Console once supported.
- [ ] Re-register trader/sentinel identities on ERC-8004.
- [ ] Re-run `validationRequest` / `validationResponse` receipt flow.
- [ ] Update dashboard copy to show sponsored gas only after transaction data proves it.
- [ ] Update tests to assert sponsored gas only in environments where the policy is active.

## Public copy rule

Do not claim "gasless" or "Gas Station sponsored" until a live transaction
receipt proves sponsorship for the current wallets. The accurate Phase 0 copy is:

> Circle EOA wallets sign ERC-8004 transactions on Arc Testnet; gas is paid in
> USDC from the wallet balance.
