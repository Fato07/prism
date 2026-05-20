# Prism Protocol v0 — `prism.report.v0`

**Protocol identifier:** `prism.report.v0`
**Version:** v0 (May 2026)
**Status:** Draft — implementable, not yet frozen
**Schema dialect:** [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12/schema)

---

## Why Prism Report v0 exists

Prism produces adversarial validation reports — structured, receipt-backed verdicts on AI-generated trading traces. Every report is a portable, self-contained artifact that a third party can verify without running the Prism dashboard.

The `prism.report.v0` protocol defines the canonical shape of one such report. It is the interchange format: what a Prism sentinel emits, what a consumer verifies, and what gets anchored onchain via Arc ERC-8004 registries.

**Receipt thesis:** A Prism report is not a claim of truth. It is a bundle of independently verifiable receipts — IPFS content addresses, onchain transaction hashes, x402 payment receipts, evidence content hashes, and an adversarial verdict with an auditable issue ledger. Every claim in a report can be checked against its receipts. If the receipts validate, the report is self-authenticating. If any receipt fails verification, the report is invalid regardless of its verdict score.

---

## The `action_intent` envelope

Every Prism v0 report declares an `action_intent` — what the trader intended to do with the reasoning in this trace. The envelope is a **discriminated union** using `oneOf` on the `type` field. This means a validator can inspect `action_intent.type`, determine which branch applies, and validate only the relevant sub-schema.

### Implemented in v0

| `type`                | Status         | Description                                      |
|-----------------------|----------------|--------------------------------------------------|
| `prediction_market`   | **Implemented** | A Polymarket trade with side, size, and builder code |

The `prediction_market` branch is the only strict branch in v0. It requires `type`, `market_id`, `side`, and constrains additional fields like `size_usdc`, `builder_code`, `raw_probability`, `final_probability`, and `rationale`.

### Reserved for future versions

The following `type` literals are reserved namespace — they appear in the schema's `oneOf` branches with only `type` required and no additional constrained properties. This prevents conflicting interpretations by future protocol versions.

| `type`              | Status              | Description                                            |
|---------------------|---------------------|--------------------------------------------------------|
| `payment_batch`     | **Reserved — future** | Batch payment processing (not implemented in v0)     |
| `defi_rebalance`    | **Reserved — future** | DeFi portfolio rebalancing (not implemented in v0)   |
| `treasury_move`     | **Reserved — future** | Treasury / DAO fund movement (not implemented in v0) |

These reserved types live under `$defs` in the JSON Schema, accessible via `$ref` from the `oneOf` branches. The schema's `additionalProperties: false` closure ensures no unrecognized fields can leak into reserved branches. **Richer reserved-branch semantics require a new `schema_version` constant (e.g., `prism.report.v1`). v0 consumers will reject reports with unknown fields in reserved branches — this is the intended behavior, preventing silent acceptance of formats the consumer does not understand.**

---

## Payment receipt polymorphism

Every Prism v0 report carries a `payment_receipts` array. Each entry is a payment receipt discriminated by its `protocol` field via `oneOf`.

### Implemented in v0

| `protocol` | Status            | Description                                           |
|-----------|-------------------|-------------------------------------------------------|
| `x402`    | **Implemented**   | x402 micropayment on Base Sepolia; full receipt shape |

The `x402` branch requires `protocol`, `tx_hash` (0x-prefixed 64-hex), `amount_usdc`, `network`, and constrains optional fields like `chain_id`, `payer`, and `payee`.

### Reserved for future versions

| `protocol` | Status                        | Description                                              |
|-----------|-------------------------------|----------------------------------------------------------|
| `mpp`     | **Reserved — future**          | Multiparty Payment Protocol (not implemented in v0)     |
| `ap2`     | **Reserved — future**          | Agent Payment Protocol v2 (not implemented in v0)       |

Both `mpp` and `ap2` are payment receipt protocols reserved for future adoption. In v0 their branches require only `protocol` and provide a `receipt_header_hash` placeholder. No MPP-specific or AP2-specific fields beyond the placeholder are defined. They are adapter-only slots — a future version can fill in the full receipt shape under a **new `schema_version`** (e.g., `prism.report.v1`). v0 consumers will reject enriched MPP or AP2 receipts with unknown fields; this is intended behavior to prevent silent misinterpretation.

---

## Onchain / offchain rule

Prism's adversarial validation operates on sensitive data: LLM reasoning traces, evidence retrieval logs, and sentinel internal state. The protocol enforces a **mandatory onchain-forbidden rule**: the following four categories of data MUST NEVER appear onchain or in any onchain-referenced artifact:

1. **Raw prompts** — The full text of any LLM prompt, including system prompts, few-shot examples, and tool-use instructions.

2. **Scraped pages** — Raw HTML or full text content retrieved from external URLs during evidence gathering. Only content hashes of retrieved evidence may appear onchain.

3. **Secrets** — API keys, bearer tokens, private keys, mnemonics, entity secrets, or any credential material. The schema's `additionalProperties: false` closures on every onchain-referenced subschema enforce this structurally.

4. **Chain-of-thought** — The sentinel's internal reasoning trace, deliberation steps, or intermediate scratchpad. The `verdict` and `issue_ledger` summarize the outcome without exposing the thinking process.

What MAY go onchain: content hashes, IPFS CIDs, transaction hashes, verdict scores and labels, issue-ledger summaries (without raw prompts), evidence URLs (not their content), and payment receipt transaction hashes. The principle is: **hashes go onchain, content stays offchain until verified via IPFS or equivalent content-addressable storage.**

---

## Report shape overview

A `prism.report.v0` report is a single JSON object with 15 required top-level fields:

| Field                | Category         | Description                                              |
|----------------------|------------------|----------------------------------------------------------|
| `schema_version`     | Identity         | Literal `"prism.report.v0"`                              |
| `generated_at`       | Identity         | ISO-8601 timestamp of report generation                  |
| `trace`              | Input            | Trace identity and provenance fields                     |
| `action_intent`      | Intent           | What the trader intended (discriminated union on `type`) |
| `validator`          | Identity         | Sentinel LLM identity and model fingerprint              |
| `verdict`            | Judgement        | Verdict score, label, and raw-vs-capped scores           |
| `reasoning_metrics`  | Judgement        | Quantitative reasoning quality metrics                   |
| `readiness`          | Judgement        | Overall readiness assessment                             |
| `warnings`           | Judgement        | Human-readable warning strings                           |
| `issue_ledger`       | Judgement        | Issue-by-issue audit trail with tool receipts            |
| `evidence_receipts`  | Receipts         | Evidence source URLs, content hashes, retrieval metadata |
| `capital_gate`       | Safety           | Capital gate status (`PENDING_VALIDATION`, `BLOCK`, `REVIEW`, `ALLOW_PAPER`, `ENDORSE`) |
| `payment_receipts`   | Receipts         | Payment receipts (discriminated union on `protocol`)     |
| `onchain_receipts`   | Receipts         | Arc/ERC-8004 transaction hashes                          |
| `content_hashes`     | Integrity        | Deterministic content hashes of trace, verdict, and report JSON |

The full JSON Schema is at [`prism-report-v0.schema.json`](./prism-report-v0.schema.json) ([Draft 2020-12](https://json-schema.org/draft/2020-12/schema)).

---

## The v0 envelope vs the live API envelope

The live Prism dashboard API (`getPublicTraceReport`) uses a different envelope shape than the v0 protocol. This is intentional:

| Concept             | Live API envelope                  | v0 protocol envelope                         |
|---------------------|------------------------------------|----------------------------------------------|
| Sentinel identity   | Nested under `validation`          | Separate top-level `validator`               |
| Verdict             | Nested under `validation`          | Separate top-level `verdict`                 |
| Evidence receipts   | Inline within `issue_ledger.issues[].tool_receipt` | Separate top-level `evidence_receipts[]` |
| Payment receipts    | Not present                        | Top-level `payment_receipts[]`               |
| Content hashes      | Not present                        | Top-level `content_hashes`                   |
| Action intent       | Not present (inferred from trace)  | Top-level `action_intent`                    |
| Schema version      | Not present                        | `schema_version: "prism.report.v0"`          |

The v0 envelope is designed for portability: it bundles everything a third-party verifier needs into one artifact. The live API envelope is optimized for dashboard rendering. Both describe the same underlying data.

---

## Worked example: canonical PASS trace

The canonical PASS trace demonstrates a real Prism validation end-to-end. Its identifiers are:

- **Trace ID:** `d6cdd60f-f5e0-43ab-ba2d-7dcab76a8e24`
- **Dashboard URL:** [Live PASS report](https://prism-dashboard-production-e6e3.up.railway.app/trace/d6cdd60f-f5e0-43ab-ba2d-7dcab76a8e24)
- **IPFS CID:** `QmNzqnPEEQUMn3GMbiEZANpKXZRPmTHxVwt5nNevR8iXt8`
- **Trace JSON content hash:** `0x1a750011608a7480e9cb11f1d20587e32efb7a7dd433b85820f0dbfcdee19fdb`
- **x402 payment tx:** `0xd6ab0cbba99dfa1162ab24ccf35c9e9544c1bb64a550a0e349e8033ebd4f43e1` (Base Sepolia)
- **Arc validation tx:** `0x5adb156fa8de6c1cf7e0d50c2197d8315eb9a501da2c00ffbf52996d2407d786`

These receipts are independently verifiable using the steps in [`receipt-verification-v0.md`](./receipt-verification-v0.md). Each onchain tx links to a public explorer; each IPFS CID resolves from any public gateway; each content hash can be recomputed from the corresponding JSON payload using deterministic canonicalization.

---

## Content hash canonicalization

Every `prism.report.v0` report carries three content hashes under `content_hashes`: `trace_json_hash` (hash of the Trading-R1 trace JSON), `verdict_json_hash` (hash of the sentinel's verdict payload JSON), and `report_json_hash` (hash of the entire report JSON). These hashes are computed using **deterministic JSON canonicalization** according to [RFC 8785](https://datatracker.ietf.org/doc/html/rfc8785) (JSON Canonicalization Scheme, JCS).

### Algorithm

1. **Canonicalization scheme:** RFC 8785 / JCS. Object keys are sorted lexicographically. No whitespace outside string literals. Unicode characters are represented in their shortest UTF-8 encoding. String escaping uses the minimal representation (`\n` for newline, never `\u000a`).

2. **Encoding:** The canonicalized JSON is encoded as **UTF-8** bytes.

3. **Hash algorithm:** The UTF-8 byte sequence is hashed with **Keccak-256** (the Ethereum-native hash). Alternatives (SHA-256) must be explicitly signaled by a protocol version bump.

4. **Output format:** The resulting 32-byte digest is hex-encoded with a `0x` prefix, producing a 66-character string matching the pattern `^0x[0-9a-fA-F]{64}$`.

### Self-referential `report_json_hash` handling

The `content_hashes.report_json_hash` field is self-referential — the hash covers the report JSON, but the hash itself is inside that JSON. To break the circular dependency, `report_json_hash` MUST be **omitted** from the report JSON before canonicalization and hashing. The canonicalization procedure for `report_json_hash` is:

1. Take the full report JSON object.
2. Delete the key `content_hashes.report_json_hash` (set it to `null` or remove it entirely from the object — the canonical form is the object without this field).
3. Canonicalize the remaining object according to RFC 8785 / JCS.
4. Hash the resulting UTF-8 bytes with Keccak-256.
5. Insert the resulting `0x`-prefixed hex digest back into `content_hashes.report_json_hash`.

### `generated_at` participation

The `generated_at` timestamp is part of the report JSON and therefore **participates in all three content hashes**. If `generated_at` changes (e.g., a report is regenerated), all three hashes will differ. This is intentional — content hashes are a fingerprint of the exact report at the exact generation time.

### Worked example

Given this minimal Prism Report v0 JSON (with `report_json_hash` omitted as required before hashing):

```json
{
  "schema_version": "prism.report.v0",
  "generated_at": "2026-05-19T12:00:00Z",
  "trace": {
    "trace_id": "example-trace",
    "agent_id": "example-agent",
    "market_id": "example-market",
    "market_question": "Will this example work?",
    "action": "YES",
    "raw_probability": 0.55,
    "final_probability": 0.60,
    "ipfs_cid": "QmExampleExampleExampleExampleExampleEx",
    "dashboard_url": "https://example.com/trace/example-trace"
  },
  "action_intent": {
    "type": "prediction_market",
    "market_id": "example-market",
    "side": "YES",
    "size_usdc": "5.00",
    "builder_code": "PRISM",
    "raw_probability": 0.55,
    "final_probability": 0.60,
    "rationale": "Example rationale."
  },
  "validator": {
    "sentinel_agent_id": "example-sentinel",
    "model_family": "openai-gpt",
    "model_name": "gpt-4o"
  },
  "verdict": {
    "verdict_score": 80,
    "verdict_label": "ENDORSE",
    "raw_verdict_score": 85,
    "capped_verdict_score": 80
  },
  "reasoning_metrics": {
    "evidence_count": 2,
    "source_diversity": 2,
    "thesis_steps": 2,
    "evidence_reference_count": 2,
    "evidence_coverage": 0.8,
    "invalid_evidence_refs": 0,
    "unsupported_thesis_steps": 0,
    "risk_factor_count": 1,
    "avg_evidence_confidence": 0.7,
    "probability_delta": 0.05,
    "has_falsification_language": true
  },
  "readiness": "usable",
  "warnings": [],
  "issue_ledger": {
    "summary": {
      "total_issues": 0,
      "resolved_count": 0,
      "unresolved_blocking_count": 0,
      "unresolved_material_count": 0,
      "clean_pass_allowed": true,
      "endorsement_allowed": true,
      "active_policy_constraints": [],
      "explanation": "No issues."
    },
    "issues": []
  },
  "evidence_receipts": [],
  "capital_gate": {
    "status": "ENDORSE"
  },
  "payment_receipts": [],
  "onchain_receipts": {
    "trace_arc_tx": "0x0000000000000000000000000000000000000000000000000000000000000001",
    "validation_arc_tx": "0x0000000000000000000000000000000000000000000000000000000000000002",
    "erc8004_request_hash": "0x0000000000000000000000000000000000000000000000000000000000000003"
  },
  "content_hashes": {
    "trace_json_hash": "0x0000000000000000000000000000000000000000000000000000000000000004",
    "verdict_json_hash": "0x0000000000000000000000000000000000000000000000000000000000000005"
  }
}
```

**To compute `report_json_hash` for this report:**

1. Delete `content_hashes.report_json_hash` from the object (it is already absent in the example above — the `content_hashes` block contains only `trace_json_hash` and `verdict_json_hash`).
2. Canonicalize the entire JSON object with RFC 8785 / JCS (sorted keys, no whitespace, minimal UTF-8 escaping).
3. Compute Keccak-256 of the resulting UTF-8 bytes.
4. The `0x`-prefixed hex output is `report_json_hash`.

Implementations can verify their canonicalization by checking that the JCS output of the example object produces the same bytes as a reference implementation. Different libraries may produce different output for edge cases (string escaping, number formatting) — all valid JCS implementations MUST produce identical output for the same input.

**Note:** The worked example above uses placeholder hashes (`0x00…01` through `0x00…05`) because the actual hashes depend on the exact canonicalization of the trace, verdict, and report JSON payloads. A conformance implementation should replace these with real hashes computed from actual trace and verdict data.

---

## Verdict score semantics

The verdict section of a `prism.report.v0` report carries three related score fields:

| Field                  | Type    | Range  | Description                                           |
|------------------------|---------|--------|-------------------------------------------------------|
| `raw_verdict_score`    | integer | 0–100  | The sentinel's unmodified evaluation score            |
| `capped_verdict_score` | integer | 0–100  | The score after applying any policy caps or overrides |
| `verdict_score`        | integer | 0–100  | Display/alias for `capped_verdict_score`              |

**Invariant:** `capped_verdict_score <= raw_verdict_score`. The capped score must never exceed the raw score. If no caps are in effect, `capped_verdict_score` equals `raw_verdict_score`. If a policy constraint reduces the score (e.g., evidence staleness cap, low source diversity penalty), the capped score is lower.

**`verdict_score` field:** This field is a display alias — it is always equal to `capped_verdict_score` when the latter is present. Consumers that display a single score should prefer `verdict_score` (or equivalently `capped_verdict_score`) as the "effective" score after all policy adjustments. The `raw_verdict_score` is preserved separately for auditability — it shows what the sentinel would have assigned absent any policy overrides.

**Label derivation:** The `verdict_label` is derived from `verdict_score` using fixed boundaries: score ≤ 25 → `REJECT`, ≤ 50 → `WARN`, ≤ 75 → `PASS`, ≥ 76 → `ENDORSE`. The label derivation uses `verdict_score` (i.e., the capped value), not `raw_verdict_score`.

---

## Fail-closed semantics

Prism is fail-closed by design: when evidence is insufficient, sources cannot be verified, or the sentinel cannot reach a high-confidence verdict, the capital gate prevents execution. A Prism report is **fail-closed** if and only if at least one of the following three conditions is true:

1. **`capital_gate.status == "BLOCK"`** — The capital gate explicitly blocks execution. This is the canonical and preferred fail-closed signal.

2. **`verdict.verdict_label == "REJECT"`** — The sentinel rejected the trace. A REJECT verdict is always fail-closed regardless of the capital gate state.

3. **`issue_ledger.summary.unresolved_blocking_count > 0`** — There are unresolved blocking issues in the issue ledger. Even if the capital gate has not yet been evaluated, the presence of unresolved block-level issues means the report is not safe for execution.

### `REVIEW` is NOT fail-closed

`capital_gate.status == "REVIEW"` means "needs human review" — a distinct state that is **not** fail-closed. A REVIEW gate indicates that the automated evaluation found material concerns but not at a severity that mandates automatic rejection. REVIEW is a signal to pause and inspect, not a machine-determined block. Only the three conditions above constitute fail-closed behavior.

### Fail-closed guarantee

A consumer can independently determine whether a report is fail-closed by checking these three conditions — no trust in the dashboard or sentinel is required. The conditions are deterministic and verifiable from the report JSON alone.

---

## Evidence relationship: `tool_receipt` vs `evidence_receipts[]`

The v0 protocol preserves two representations of evidence:

1. **Per-issue `tool_receipt`** (under `issue_ledger.issues[].tool_receipt`): This is the legacy field carried over from the live dashboard API. It records the tool-level evidence for a specific issue — the source content hash, retrieval timestamp, and provider for the tool that investigated that particular issue.

2. **Top-level `evidence_receipts[]`**: This is the canonical v0 representation. It reorganizes evidence into a flat array where each entry references a distinct evidence source (`source_url`), its content hash (`source_content_hash`), retrieval metadata, and adequacy checks.

**Relationship:** `issues[].tool_receipt` entries are references into `evidence_receipts[]`, matched by `source_content_hash`. Every `tool_receipt.source_content_hash` SHOULD correspond to an entry in `evidence_receipts[]`. If an issue's tool receipt has a hash not present in `evidence_receipts[]`, the evidence is incomplete — the hash is claimed but not attested at the report level. Consumers verifying evidence integrity SHOULD prefer the top-level `evidence_receipts[]` as the canonical evidence surface and treat per-issue `tool_receipt` as backward-compatible informational metadata.

---

## Readiness semantics

The `readiness` field describes the overall readiness assessment of the trace for execution. It has three possible values:

| Value          | Description                                                                                                                                                                    | Expected capital-gate correlation                                 |
|----------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------|
| `not_ready`    | The trace is incomplete, evidence is missing, or the sentinel could not complete evaluation. The report is not safe for execution under any mode.                                | Expected to correlate with `capital_gate.status == "BLOCK"`       |
| `needs_review` | The trace has issues that require human attention before execution. The sentinel found material concerns but not at automatic-block severity.                                    | Expected to correlate with `capital_gate.status == "REVIEW"` or `verdict.verdict_label == "WARN"` |
| `usable`       | The trace passed adversarial review with no blocking issues. The report is structurally valid and all evidence receipts are present. Required (but not sufficient) for execution. | Required for `capital_gate.status ∈ {"ALLOW_PAPER", "ENDORSE"}`   |

These correlations are **expected** but not schema-enforceable — the schema cannot express cross-field constraints like "if readiness == 'usable' then capital_gate.status != 'BLOCK'". Conformance tests should verify these correlations on real fixtures.

---

## What Prism guarantees

Prism makes eight concrete guarantees about every trace it validates:

1. **Provenance.** Every trace has a unique ID, agent identity, and IPFS content address. You can verify who generated a trace and when.

2. **Independent adversarial review.** Trader and sentinel use different LLM families — Mirascope for the trader, DSPy for the sentinel. No single model both generates AND judges a trace.

3. **Source URL verification.** Every evidence item links to a source URL that was verified live at retrieval time. Hallucinated sources are caught by the issue ledger.

4. **Source content hashes.** Retrieved evidence is content-hashed. If a source changes after retrieval, the mismatch appears in the evidence receipt.

5. **Issue-ledger transparency.** Every sentinel challenge is recorded: what was questioned, which tool resolved it, and whether it blocked a PASS. The ledger is public.

6. **x402 receipts.** Paid validations produce an x402 payment receipt on Base Sepolia. The canonical CLI receipt proves a live 0.01 USDC paid validation end-to-end.

7. **Arc / ERC-8004 onchain anchoring.** Validation requests and responses are submitted to deployed Arc ERC-8004 registries, producing onchain transaction hashes. Prism uses deployed Arc infrastructure — no additional contracts are deployed by Prism.

8. **Fail-closed capital gate.** Every trace passes through a deterministic capital gate before any execution signal. The gate can BLOCK, require REVIEW, allow paper mode only, or ENDORSE — but never silently pass.

---

## What Prism does NOT guarantee

Prism produces receipt-backed claims, not oracle verdicts or compliance certifications. Five things Prism explicitly does not guarantee:

1. **Truth.** A PASS means the sentinel found no blocking issues. It does not mean the prediction is correct or the market will move as expected.

2. **Profit.** Validated traces may still lose money. Capital gate states are risk signals, not profit guarantees.

3. **Complete security.** The sentinel evaluates evidence completeness, source diversity, and thesis coherence. It cannot guarantee protection against unknown attack vectors.

4. **Legal compliance.** Prism does not verify trades against any jurisdiction's regulations. Operators are responsible for their own compliance.

5. **A PASS is not an instruction to execute.** `ALLOW_PAPER` and `ENDORSE` are machine-generated signals requiring human review before real capital is routed. Prism outputs evidence, not execution commands.

---

## Trust assumptions

Prism is fail-closed by design: when evidence is missing, sources cannot be retrieved, or the sentinel cannot reach a high-confidence verdict, the capital gate blocks or requires review. The system never assumes a trace is safe by default.

Verifiable trust assumptions:

- The sentinel LLM is independent of the trader LLM (enforced at startup, validated at runtime).
- Deployed Arc ERC-8004 registries behave as specified; Prism does not deploy or modify them.
- IPFS content addresses are collision-resistant within the verification lifetime.
- x402 payments settle on Base Sepolia before validation proceeds.

These assumptions are independently verifiable: every onchain transaction links to a public explorer; every IPFS CID is fetchable from a public gateway; every x402 receipt has a BaseScan transaction.

---

## Verifying a Prism Report

To verify a `prism.report.v0` report:

1. **Schema validation.** Validate the report JSON against `prism-report-v0.schema.json` using any JSON Schema Draft 2020-12 validator (e.g., `ajv` with `ajv-formats`).
2. **Receipt verification.** Follow the step-by-step guide in [`receipt-verification-v0.md`](./receipt-verification-v0.md) to verify IPFS CIDs, onchain transactions, content hashes, and x402 payment receipts.
3. **Cross-receipt consistency.** Confirm that the `trace.trace_id`, `trace.ipfs_cid`, and `content_hashes.trace_json_hash` in the report match the canonical CLI receipt published alongside the trace.

The canonical test gate is `pnpm --dir apps/docs test`, which validates the schema against known-good PASS and fail-closed conformance fixtures.

---

## Related artifacts

- **JSON Schema:** [`prism-report-v0.schema.json`](./prism-report-v0.schema.json) — JSON Schema Draft 2020-12 definition
- **Verification guide:** [`receipt-verification-v0.md`](./receipt-verification-v0.md) — step-by-step receipt verification walkthrough
- **Guarantees page:** [Verification guarantees](/docs/verification-guarantees) — public-facing summary
- **Conformance fixtures:** [`fixtures/`](./fixtures/) — PASS and fail-closed test fixtures
