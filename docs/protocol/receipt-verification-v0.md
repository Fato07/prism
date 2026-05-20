# Receipt Verification v0 — Step-by-step

**Version:** v0 (May 2026)
**Protocol:** [`prism.report.v0`](./prism-protocol-v0.md)
**Schema:** [`prism-report-v0.schema.json`](./prism-report-v0.schema.json)

A Prism report is a bundle of independently verifiable receipts. This guide walks through verifying each receipt type. Every step is self-contained — you can verify IPFS CIDs without running the Prism dashboard, and you can check onchain transactions without trusting any Prism service.

---

## 1. IPFS CID verification

Every Prism trace is pinned to IPFS. The trace's `ipfs_cid` references the full Trading-R1 trace JSON — reasoning steps, market context, evidence references, and the trader's final action.

### Verify from any public gateway

Fetch the trace content using any IPFS gateway. The `/ipfs/<CID>` path pattern is gateway-agnostic — swap the host to any gateway you trust:

```
https://ipfs.io/ipfs/<CID>
https://gateway.pinata.cloud/ipfs/<CID>
https://dweb.link/ipfs/<CID>
```

**Canonical PASS example:**

- [View canonical PASS trace on IPFS](https://ipfs.io/ipfs/QmNzqnPEEQUMn3GMbiEZANpKXZRPmTHxVwt5nNevR8iXt8) — resolves `ipfs://QmNzqnPEEQUMn3GMbiEZANpKXZRPmTHxVwt5nNevR8iXt8` through a public gateway.
- Bare gateway URL: `https://ipfs.io/ipfs/QmNzqnPEEQUMn3GMbiEZANpKXZRPmTHxVwt5nNevR8iXt8`

### Verification steps

1. Resolve the CID from any public IPFS gateway using the `/ipfs/<CID>` path.
2. Confirm the returned JSON content matches the trace identity fields in the report (`trace_id`, `agent_id`, `market_id`, `action`).
3. Compute the content hash of the returned JSON (see [section 4](#4-content-hash-recomputation)) and confirm it matches `content_hashes.trace_json_hash` in the report.

If any gateway returns different content for the same CID, or if the content hash does not match, the report is invalid — IPFS CIDs are content-addressable and should be deterministic.

---

## 2. Base Sepolia x402 payment receipt verification

Paid Prism validations use x402 — an HTTP 402-based micropayment protocol. Every paid validation produces an onchain transaction on Base Sepolia.

### Verify on BaseScan

Look up the x402 transaction hash on a Base Sepolia block explorer:

```
https://sepolia.basescan.org/tx/<tx_hash>
```

**Canonical CLI example:**

```
https://sepolia.basescan.org/tx/0xd6ab0cbba99dfa1162ab24ccf35c9e9544c1bb64a550a0e349e8033ebd4f43e1
```

### Verification steps

1. Extract `payment_receipts[].tx_hash` from the report for the entry with `protocol == "x402"`.
2. Open `https://sepolia.basescan.org/tx/<tx_hash>` in a browser or query the Base Sepolia RPC.
3. Confirm the transaction status is successful (status `1`).
4. Confirm the `amount_usdc` field in the report is consistent with the onchain transfer amount.
5. Confirm the `network` field is `"base-sepolia"` or equivalent.

The x402 protocol settles on Base Sepolia before the Prism sentinel returns a verdict. If the payment transaction is not found or has failed, the validation was never completed and the report is not authentic.

---

## 3. Arc validation-tx verification

Every Prism validation request and response is submitted to the deployed Arc ERC-8004 ValidationRegistry. This produces onchain transaction hashes that anchor the validation to Arc testnet.

### Verify on ArcScan

Look up the Arc transaction hash on the Arc testnet block explorer:

```
https://testnet.arcscan.app/tx/<tx_hash>
```

**Canonical PASS example:**

```
https://testnet.arcscan.app/tx/0x5adb156fa8de6c1cf7e0d50c2197d8315eb9a501da2c00ffbf52996d2407d786
```

### Verification steps

1. Extract `onchain_receipts.validation_arc_tx` from the report.
2. Open `https://testnet.arcscan.app/tx/<tx_hash>` or query the Arc testnet RPC.
3. Confirm the transaction exists and was successful.
4. Confirm the `erc8004_request_hash` in the report matches the ValidationRequest event emitted by the transaction logs.
5. If the trace also has its own Arc anchoring, repeat for `onchain_receipts.trace_arc_tx`.

Arc validation transactions are the onchain proof that a sentinel reviewed a trace and submitted a verdict through the ERC-8004 contract. Without a valid Arc transaction, the validation is not onchain-anchored.

---

## 4. Content hash recomputation

Every Prism report carries three content hashes under `content_hashes`:

| Hash field             | What it covers                            |
|------------------------|-------------------------------------------|
| `trace_json_hash`      | The full Trading-R1 trace JSON            |
| `verdict_json_hash`    | The sentinel's verdict payload JSON       |
| `report_json_hash`     | The entire `prism.report.v0` report JSON  |

These hashes are computed using **deterministic JSON canonicalization** — the JSON is serialized with sorted keys and a canonical encoding before hashing.

### Canonicalization method

The canonicalization follows [RFC 8785](https://datatracker.ietf.org/doc/html/rfc8785) (JSON Canonicalization Scheme, JCS):
- Object keys are sorted lexicographically.
- No whitespace outside string literals.
- Unicode characters are represented in their shortest UTF-8 encoding.
- String escaping uses the minimal representation (`\n` for newline, no `\u000a`).

The resulting canonical JSON byte sequence is hashed with Keccak-256, producing a 32-byte (64-hex) digest prefixed with `0x`.

### `report_json_hash` self-reference handling

The `report_json_hash` field is self-referential — it covers the report JSON that contains it. To break the circular dependency, `report_json_hash` MUST be **omitted** from the report JSON before canonicalization and hashing:

1. Take the full report JSON object.
2. Delete the key `content_hashes.report_json_hash` (remove it entirely from the object — or set it to `null` before canonicalization; the canonical form is the object without this field).
3. Canonicalize the remaining object according to RFC 8785 / JCS.
4. Hash the resulting UTF-8 bytes with Keccak-256.
5. Insert the resulting `0x`-prefixed hex digest back into `content_hashes.report_json_hash`.

**Note:** `trace_json_hash` and `verdict_json_hash` do not have this self-reference problem — they hash separate JSON payloads (the trace JSON and the verdict JSON), not the report JSON that contains them.

### `generated_at` participation

The `generated_at` timestamp is part of the report JSON and therefore **participates in `report_json_hash`**. If a report is regenerated with a different `generated_at`, the `report_json_hash` will differ. `generated_at` also participates in `trace_json_hash` and `verdict_json_hash` if those payloads include a timestamp. This is intentional — content hashes are a fingerprint of the exact payload at the exact generation time.

### Verification steps

1. Obtain the canonical JSON for the target object (trace, verdict, or report).
2. Serialize using RFC 8785 / JCS canonicalization rules: sorted keys, no extra whitespace, minimal escaping.
3. Compute Keccak-256 of the canonical bytes.
4. Compare the resulting `0x`-prefixed hex digest against the corresponding `content_hashes.*` field in the report.

**Tooling:** Most languages have JCS libraries (`json-canonicalize` in JS/TS, `canonicaljson` in Python). If you do not have a JCS library, sorting keys alphabetically and stripping whitespace produces equivalent results for Prism's JSON payloads (which use only ASCII-safe strings and standard JSON value types).

The content hash chain provides integrity: if any hash mismatches, either the JSON was tampered with or the canonicalization was not applied correctly.

---

## 5. MPP and AP2 — future payment receipt protocols

The `payment_receipts` array in a `prism.report.v0` report uses a discriminated union on the `protocol` field. In v0, only `x402` is implemented as a strict, fully-constrained receipt shape.

**MPP** (Multiparty Payment Protocol) and **AP2** (Agent Payment Protocol v2) are reserved protocol identifiers. They appear in the schema's `oneOf` branches with only `protocol` required and a `receipt_header_hash` placeholder field. No MPP-specific or AP2-specific fields beyond the placeholder are defined in v0.

These slots follow the **adapter pattern**: a future protocol version can fill in the full MPP or AP2 receipt shape under a **new `schema_version`** (e.g., `prism.report.v1`). v0 consumers will reject enriched MPP or AP2 receipts with unknown fields — this is intended behavior to prevent silent misinterpretation. A v0 consumer encountering a `protocol: "mpp"` or `protocol: "ap2"` receipt should:

1. Validate that `protocol` is one of the known reserved values.
2. Treat the receipt as unverifiable beyond schema conformance (since no verification logic is implemented).
3. Skip the receipt without rejecting the entire report.

MPP and AP2 are **not implemented** in v0. They are adapter-only future slots reserved to avoid namespace collisions when Prism adds support for additional payment receipt protocols.

---

## 6. Full verification checklist

For a complete end-to-end verification of a `prism.report.v0` report:

- [ ] **Schema validation.** Validate against `prism-report-v0.schema.json` using a JSON Schema Draft 2020-12 validator.
- [ ] **Schema version.** Confirm `schema_version == "prism.report.v0"`.
- [ ] **IPFS CID.** Resolve `trace.ipfs_cid` from a public gateway; confirm content matches.
- [ ] **Trace content hash.** Recompute `trace_json_hash` from canonical JSON; confirm match.
- [ ] **Verdict content hash.** Recompute `verdict_json_hash` from canonical JSON; confirm match.
- [ ] **Report content hash.** Recompute `report_json_hash` from canonical JSON; confirm match.
- [ ] **Evidence receipts.** For each evidence receipt, confirm `source_url` is well-formed and `source_content_hash` is a valid 64-hex digest.
- [ ] **x402 payment.** Look up `payment_receipts` x402 `tx_hash` on Base Sepolia; confirm settlement.
- [ ] **Arc validation tx.** Look up `onchain_receipts.validation_arc_tx` on ArcScan testnet; confirm presence.
- [ ] **ERC-8004 request hash.** Confirm `erc8004_request_hash` matches the ValidationRequest event.
- [ ] **Capital gate.** Confirm `capital_gate.status` is a valid enum value and consistent with the verdict.
- [ ] **Issue ledger.** Review `issue_ledger` for unresolved blocking issues; confirm tool receipts.
- [ ] **Banned content.** Confirm no raw prompts, scraped pages, secrets, or chain-of-thought appear in onchain-anchored fields.

---

## Related artifacts

- **Protocol spec:** [`prism-protocol-v0.md`](./prism-protocol-v0.md)
- **JSON Schema:** [`prism-report-v0.schema.json`](./prism-report-v0.schema.json)
- **Guarantees page:** [Verification guarantees](/docs/verification-guarantees)
- **Receipts documentation:** [Receipts](/docs/receipts)
