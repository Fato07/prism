# Prism CLI paid validation receipt — 2026-05-16

A live Prism CLI paid validation was run through the x402-protected sentinel MCP endpoint.

## Command shape

```bash
cd apps/cli
uv run prism demo --pay \
  --circle-address 0x229d65c16eb0386ac9a759625836e7d2b9831c3e \
  --max-amount-usdc 0.01 \
  --json
```

Prism CLI did not read or store private keys. The payment authorization was signed through Circle CLI typed-data signing.

## Trace

- Trace ID: `d6cdd60f-f5e0-43ab-ba2d-7dcab76a8e24`
- Trace URI: `ipfs://QmNzqnPEEQUMn3GMbiEZANpKXZRPmTHxVwt5nNevR8iXt8`
- Trace hash: `0x1a750011608a7480e9cb11f1d20587e32efb7a7dd433b85820f0dbfcdee19fdb`
- Dashboard report: <https://prism-dashboard-production-e6e3.up.railway.app/trace/d6cdd60f-f5e0-43ab-ba2d-7dcab76a8e24>
- Market: Will the EU AI Act enforcement actions exceed 50 by end of 2026?
- Existing public verdict: `65 PASS`

## x402 quote

- Amount: `0.01 USDC`
- Amount units: `10000`
- Network: `base-sepolia` / `eip155:84532`
- USDC contract: `0x036CbD53842c5426634e7929541eC2318f3dCF7e`
- Recipient: `0xaf131B054B08E57c20b31080A1Ffd406e429db6F`
- Scheme: `exact`

## Paid validation result

- Request hash: `97211da3ffee822ed72e5183d1c1c5edfa1606e26baa5197208b4dcc90b94d91`
- Sentinel agent ID: `4148`
- Verdict: `50 WARN`
- Verdict CID: `QmUQpQEaggjuZqGAJpxoDXg4ghJ3ReufWM546g856KqUnk`
- Verdict IPFS: <https://gateway.pinata.cloud/ipfs/QmUQpQEaggjuZqGAJpxoDXg4ghJ3ReufWM546g856KqUnk>
- Base Sepolia x402 payment tx: <https://sepolia.basescan.org/tx/0xd6ab0cbba99dfa1162ab24ccf35c9e9544c1bb64a550a0e349e8033ebd4f43e1>
- Arc validation tx from this external paid run: `none`

## Verification

- `uv run prism doctor` after payment: `ok`
- Verdict IPFS gateway status: `200`
- Payment explorer status: `200`
- Wallet deployment preflight tx: <https://sepolia.basescan.org/tx/0x3b68fc432bb7b052352851b962728905e01818d1c88940ab2e97da29bea21d89>

## Receipt files

- JSON fixture: [`cli-paid-validation-20260516T214837Z.json`](./cli-paid-validation-20260516T214837Z.json)
- Local CLI receipt path when generated: `.prism/receipts/20260516T214837+0000-paid-d6cdd60f.json`
