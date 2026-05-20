# Oracle Review — Prism Report v0

**Date:** 2026-05-19
**Reviewer:** mission-oracle (read-only second-opinion reviewer)
**Artifacts reviewed:**
- [`prism-report-v0.schema.json`](./prism-report-v0.schema.json) — JSON Schema Draft 2020-12
- [`prism-protocol-v0.md`](./prism-protocol-v0.md) — Human-readable protocol specification
**Verdict:** Proceed with changes before freezing `prism.report.v0`. The split from live `validation` into top-level `validator` + `verdict` is preserved, and the `oneOf` discriminators are unambiguous. Main risks are unconstrained placeholder fields, missing cross-field invariants, and protocol claims that schema validation alone cannot enforce.

---

## Findings

### Issue 1: `{}` subschemas accept any value, weakening onchain-forbidden rule (blocking)

**Location:**
- Schema: `issue_ledger.properties.resolution_metadata` (`"resolution_metadata": {}`)
- Schema: `issue_ledger.properties.issues.items.properties.tool_receipt` (`"tool_receipt": {}`)
- Schema: `issue_ledger.properties.issues.items.properties.latest_resolution` (`"latest_resolution": {}`)
- Protocol: "Mandatory onchain-forbidden rule" section (lines ~71–79), which claims `additionalProperties: false` closures enforce the onchain-forbidden rule structurally.

**Problem:** In JSON Schema, `{}` accepts **any JSON value** — objects, strings, arrays, null, raw scraped text, secrets, or chain-of-thought reasoning. These three empty subschemas are inside the `issue_ledger` which is lifted verbatim from the live dashboard API and is thus onchain-referenced. This directly weakens the protocol's mandatory rule that raw prompts, scraped pages, secrets, and chain-of-thought MUST NEVER appear onchain or in any onchain-referenced artifact.

**Severity:** Blocking. If a dashboard adapter dumps unredacted tool receipts or internal resolution state into these fields, the schema will accept it silently, creating a false sense of onchain safety.

### Resolution 1

Replace each `{}` subschema with a strict typed object:

- **`tool_receipt`**: Define as `{"type": "object", "additionalProperties": false, "required": ["source_url", "source_content_hash", "retrieved_at", "provider"], "properties": {...}}` — evidence-source metadata only, NO raw content.
- **`latest_resolution`**: Define as `{"type": "object", "additionalProperties": false, "required": ["status", "resolved_at"], "properties": {...}}` with an optional `evidence_receipt_ref` (a hash or index into `evidence_receipts[]`).
- **`resolution_metadata`**: Define as `{"type": "object", "additionalProperties": false, "properties": {"policy_version": {"type": "string"}, ...}}` — versioned policy metadata, not an open bag.

If any of these are intentionally opaque extension slots, the protocol doc MUST explicitly state they are **not safe for onchain-referenced artifacts** and consumers should treat their content as untrusted until independently verified.

**Status:** TODO — requires schema change (blocking, flagged in discoveredIssues). Must be resolved before v0 freeze.

---

### Issue 2: `report_json_hash` canonicalization is under-specified and self-referential (blocking)

**Location:**
- Schema: `content_hashes.properties.report_json_hash` (`pattern: "^0x[0-9a-fA-F]{64}$"`)
- Protocol: "Worked example: canonical PASS trace" section (lines ~129–139), which says content hashes can be recomputed using deterministic JSON canonicalization but does not define the exact procedure or how to handle the self-referential `report_json_hash` field.

**Problem:** The report JSON contains the field `content_hashes.report_json_hash`, which is the hash of the report JSON. This is circular: to compute the hash, the hash field must already be known. Different implementations could omit it, null it, or set it to a sentinel before hashing — producing different valid-looking hashes. The schema and protocol provide no guidance on which approach is canonical.

**Severity:** Blocking. Without a normative hashing procedure, different Prism implementations will produce incompatible content hashes, breaking the portability thesis of the entire protocol.

### Resolution 2

Add a normative "Content hash canonicalization" section to the protocol doc specifying:

1. **Algorithm**: RFC 8785 (JSON Canonicalization Scheme / JCS) or equivalent deterministic serialization
2. **Self-referential field handling**: `report_json_hash` MUST be omitted from the JSON before hashing (or set to `null`). The hash covers all other fields.
3. **Encoding**: UTF-8 bytes of the canonicalized JSON, hashed with Keccak-256 (or SHA-256), hex-encoded with `0x` prefix.
4. **`generated_at` participation**: Yes — `generated_at` is part of the report and participates in the hash.
5. **Test vector**: Provide a minimal report JSON and its expected `report_json_hash` so implementers can verify their canonicalization.

**Status:** TODO — requires protocol doc change (blocking, flagged in discoveredIssues). Must be resolved before v0 freeze.

---

### Issue 3: Raw/capped/display verdict score relationship is ambiguous (non-blocking)

**Location:**
- Schema: `verdict.required` includes `verdict_score` and `verdict_label`, but NOT `raw_verdict_score` or `capped_verdict_score`
- Schema: `verdict.properties.raw_verdict_score` and `capped_verdict_score` are both optional
- Protocol: "Report shape overview" table (line ~96) says the verdict includes "raw-vs-capped scores"

**Problem:** Consumers cannot determine what `verdict_score` represents — is it the raw score, the capped score, a display alias, or a legacy field? The implicit invariant that `capped_verdict_score <= raw_verdict_score` is not stated in the schema, protocol, or enforceable by JSON Schema alone (`<=` is not a JSON Schema keyword). If `verdict_score` is an alias for `capped_verdict_score`, the schema promotes redundancy without defining the relationship.

**Severity:** Non-blocking. The schema already defines all three fields; the issue is about semantics and enforcement.

### Resolution 3

Option A (preferred): Require both `raw_verdict_score` and `capped_verdict_score` in `verdict.required`, and deprecate `verdict_score` as a display alias for `capped_verdict_score`. Document the invariant `capped_verdict_score <= raw_verdict_score` in the protocol and enforce it in conformance tests (custom ajv keyword or post-validation assertion).

Option B (lighter-weight): Keep `verdict_score` as required and define it as equal to `capped_verdict_score` when present, or equal to `raw_verdict_score` when no cap is applied. Document clearly in the protocol.

**Status:** TODO — requires schema + protocol doc change (non-blocking). Recommended for v0 freeze but not a gate. If deferred to v1, document the ambiguity explicitly so consumers know to check both fields.

---

### Issue 4: Fail-closed criteria are not stated normatively in the protocol (non-blocking)

**Location:**
- Schema: `capital_gate.properties.status.enum` (includes `BLOCK`), `issue_ledger.summary.properties.unresolved_blocking_count`
- Protocol: "Fail-closed capital gate" (line ~162) and "Trust assumptions" (line ~184), which say the gate "blocks or requires review" but do not give the exact fail-closed rule

**Problem:** The canonical fail-closed criteria (at least one of: `capital_gate.status == "BLOCK"`, `verdict.verdict_label == "REJECT"`, `issue_ledger.summary.unresolved_blocking_count > 0`) are defined in the mission's internal architecture and validation contract but NOT in the public protocol document. A third-party implementer reading only `prism-protocol-v0.md` would not know the exact rule. Additionally, the prose "blocks or requires review" could be misread as treating `REVIEW` as part of fail-closed behavior, but the canonical rule explicitly excludes `REVIEW`.

**Severity:** Non-blocking. The information exists in the mission internals but a public protocol consumer needs it in the protocol doc.

### Resolution 4

Add a "Fail-closed semantics" subsection to the protocol doc with:

- The exact three-pronged rule: `fail_closed iff capital_gate.status == "BLOCK" OR verdict.verdict_label == "REJECT" OR issue_ledger.summary.unresolved_blocking_count > 0`
- An explicit note: `capital_gate.status == "REVIEW"` is NOT fail-closed — it means "needs human review", which is a distinct state.

**Status:** TODO — requires protocol doc change (non-blocking). Recommended for clarity.

---

### Issue 5: `capital_gate.checks` duplicates `issue_ledger.summary` fields, risking silent drift (non-blocking)

**Location:**
- Schema: `issue_ledger.properties.summary.properties.clean_pass_allowed` and `endorsement_allowed`
- Schema: `capital_gate.properties.checks.properties.clean_pass_allowed` and `endorsement_allowed`
- Note: `capital_gate.checks` is optional — only `capital_gate.status` is required.

**Problem:** The same two boolean fields (`clean_pass_allowed`, `endorsement_allowed`) appear in both `issue_ledger.summary` and `capital_gate.checks`. If a report has `issue_ledger.summary.clean_pass_allowed: true` but `capital_gate.checks.clean_pass_allowed: false`, schema validation would pass — the fields can silently disagree. Since `capital_gate.checks` is optional, consumers may also not find the values where they expect them.

**Severity:** Non-blocking. The schema correctly captures both locations, but the duplication creates a maintenance burden and potential for inconsistency.

### Resolution 5

Option A (preferred): Require `capital_gate.checks` in the capital_gate subschema, and define an equality invariant (`capital_gate.checks.clean_pass_allowed === issue_ledger.summary.clean_pass_allowed` and same for `endorsement_allowed`), enforced in conformance tests since JSON Schema cannot express equality across paths.

Option B: Remove `clean_pass_allowed` and `endorsement_allowed` from `capital_gate.checks` and treat `issue_ledger.summary` as the single canonical source for these booleans. Keep `capital_gate.checks` for gate-specific fields only (`validation_present`, `trace_ready`).

**Status:** TODO — requires schema change (non-blocking). Recommended for v0 freeze to eliminate the maintenance burden.

---

### Issue 6: `verdict.request_hash` duplicates `onchain_receipts.erc8004_request_hash` (non-blocking)

**Location:**
- Schema: `verdict.properties.request_hash` (optional, `pattern: "^0x[0-9a-fA-F]{64}$"`)
- Schema: `verdict.properties.response_uri` (optional, unconstrained `"type": "string"`)
- Schema: `onchain_receipts.properties.erc8004_request_hash` (required, `pattern: "^0x[0-9a-fA-F]{64}$"`)

**Problem:** The ERC-8004 validation request hash appears twice — once as optional under `verdict` and once as required under `onchain_receipts`. A report could have the required field in `onchain_receipts` but a different (or missing) value in `verdict`, passing schema validation. The `response_uri` field, which is important for ERC-8004 verification (it points to the offchain validation response), is optional and has no format constraint — it accepts any string.

**Severity:** Non-blocking. The duplication is low-risk because `onchain_receipts.erc8004_request_hash` is required and sufficient for verification.

### Resolution 6

Option A (preferred): Remove `verdict.request_hash` and treat `onchain_receipts.erc8004_request_hash` as the single canonical location for this hash. Keep `verdict.response_uri` but constrain it with `format: "uri"` and either make it required for onchain-backed reports or link it explicitly to `onchain_receipts.validation_arc_tx`.

Option B: If keeping both, add an equality invariant in conformance tests and document it in the protocol.

**Status:** TODO — requires schema change (non-blocking). Low priority; the required `onchain_receipts` field is sufficient.

---

### Issue 7: Live-envelope drift risk — `issue_ledger.issues[].tool_receipt` vs top-level `evidence_receipts[]` (non-blocking)

**Location:**
- Schema: `issue_ledger.properties.issues.items.properties.tool_receipt` (required per-issue)
- Schema: `evidence_receipts[]` (top-level array)
- Protocol: "v0 envelope vs live API envelope" table (lines ~111–124), which states live evidence receipts are inline under `issue_ledger.issues[].tool_receipt` and v0 reorganizes them into top-level `evidence_receipts[]`

**Problem:** The v0 schema preserves BOTH per-issue `tool_receipt` (lifted from the live API) AND adds top-level `evidence_receipts[]` (derived/reorganized), but the schema does not define how they relate. A dashboard adapter could emit inconsistent source URLs, content hashes, or providers across these two locations and still pass schema validation. Consumers reading both locations may see contradictory evidence.

**Severity:** Non-blocking. The top-level `evidence_receipts[]` is the canonical v0 shape; per-issue `tool_receipt` is a legacy field carried over from the live envelope.

### Resolution 7

Define the relationship normatively: either (a) `issues[].tool_receipt` is a STRICT subset or reference into `evidence_receipts[]` (e.g., by `source_content_hash`), or (b) `issues[].tool_receipt` is marked as informational/backward-compatible and consumers SHOULD prefer `evidence_receipts[]`. Enforce consistency in conformance tests.

**Status:** TODO — requires schema and/or protocol doc change (non-blocking). Lower priority because the top-level array is the intended canonical surface.

---

### Issue 8: Several scalar fields lack bounds, patterns, or minLength constraints (suggestion)

**Location:**
- Schema: `trace.properties.raw_probability`, `trace.properties.final_probability` — no `minimum`/`maximum`
- Schema: `action_intent_prediction_market.properties.raw_probability`, `final_probability` — no `minimum`/`maximum`
- Schema: `reasoning_metrics.properties.avg_evidence_confidence` — no `0..1` bounds
- Schema: `payment_receipt_x402.properties.amount_usdc` — unconstrained `"type": "string"`, no decimal regex
- Schema: `action_intent_prediction_market.properties.size_usdc` — unconstrained `"type": "string"`
- Schema: `warnings.items`, `adequacy_checks.items`, `market_question` — strings may be empty (no `minLength: 1`)

**Problem:** Fields with known numeric domains (probabilities 0..1, confidence 0..1) have no bounds. Monetary strings (`amount_usdc`, `size_usdc`) have no format constraint, so `"-50.00"`, `"free"`, or `"💸"` would all validate. Several string fields lack `minLength: 1`, allowing empty strings where they semantically shouldn't be empty.

**Severity:** Suggestion. These do not break the protocol but reduce its robustness as a portable validation surface.

### Resolution 8

Add constraints where semantics are known:

- `raw_probability`, `final_probability`, `avg_evidence_confidence`: `"minimum": 0, "maximum": 1`
- `amount_usdc`, `size_usdc`: add `"pattern": "^[0-9]+(\\.[0-9]{1,6})?$"` for non-negative decimal USDC amounts
- `market_question`, `warnings` items, `action` string: add `"minLength": 1`
- `chain_id`: add `"minimum": 1`
- `payer`, `payee` (x402 receipt): optionally add EVM address pattern `"pattern": "^0x[0-9a-fA-F]{40}$"`

**Status:** TODO — requires schema change (suggestion). Nice-to-have for v0 freeze.

---

### Issue 9: `readiness` enum is under-defined relative to capital gate (suggestion)

**Location:**
- Schema: `readiness` enum: `["usable", "needs_review", "not_ready"]`
- Protocol: "Report shape overview" table (line ~98): "Overall readiness assessment"

**Problem:** The three readiness states (`usable`, `needs_review`, `not_ready`) are not normatively defined relative to `capital_gate.status` or `verdict.verdict_label`. For example, does `not_ready` always imply `capital_gate.status == "BLOCK"`? Does `needs_review` map to `REVIEW`? Without explicit cross-field semantics, different sentinel implementations may assign readiness differently, reducing portability.

**Severity:** Suggestion. The enum itself is valid; the ambiguity is about cross-field relationships.

### Resolution 9

Add a normative definition in the protocol doc:

- `not_ready`: the trace is incomplete, evidence is missing, or the sentinel could not complete evaluation. Expected to correlate with `capital_gate.status == "BLOCK"`.
- `needs_review`: the trace has issues that require human attention before execution. Expected to correlate with `capital_gate.status == "REVIEW"` or `verdict.verdict_label == "WARN"`.
- `usable`: the trace passed adversarial review with no blocking issues. Required (but not sufficient) for `capital_gate.status ∈ {"ALLOW_PAPER", "ENDORSE"}`.

**Status:** TODO — requires protocol doc change (suggestion). Improves portability for third-party implementers.

---

### Issue 10: Reserved `oneOf` branches with `additionalProperties: false` limit future extension within v0 (suggestion)

**Location:**
- Schema: `$defs.action_intent_payment_batch`, `action_intent_defi_rebalance`, `action_intent_treasury_move` — all have `"additionalProperties": false` with only `type` required
- Schema: `$defs.payment_receipt_mpp`, `payment_receipt_ap2` — same pattern
- Protocol: Lines ~55–65 say future versions "can fill in the full receipt shape without breaking v0 consumers"

**Problem:** Branch selection is safe because `const` discriminators (`type`, `protocol`) do not overlap. However, `additionalProperties: false` on reserved branches means that if a future implementation adds fields to `payment_batch` or `mpp` before bumping `schema_version`, those enriched payloads will fail v0 validation. This is actually a *feature* (it prevents v0 consumers from silently accepting v1 data), but the protocol doc's phrasing "without breaking v0 consumers" could be misinterpreted as "v0 consumers will accept v1 payloads."

**Severity:** Suggestion. The schema behavior is correct; the protocol doc wording is ambiguous.

### Resolution 10

Clarify in the protocol doc: "Richer reserved-branch semantics require a new `schema_version` constant. v0 consumers will reject reports with unknown fields in reserved branches, which is the intended behavior — it prevents silent acceptance of formats the consumer does not understand."

**Status:** TODO — requires protocol doc clarification only (suggestion). No schema change needed.

---

## Summary

| # | Issue | Severity | Requires schema change | Requires protocol change |
|---|-------|----------|----------------------|------------------------|
| 1 | `{}` subschemas weaken onchain-forbidden rule | **Blocking** | Yes | Yes |
| 2 | `report_json_hash` canonicalization under-specified | **Blocking** | No | Yes |
| 3 | Raw/capped/display verdict score ambiguity | Non-blocking | Yes | Yes |
| 4 | Fail-closed criteria not normative in protocol | Non-blocking | No | Yes |
| 5 | `capital_gate.checks` duplicates `issue_ledger.summary` | Non-blocking | Yes | Yes |
| 6 | `verdict.request_hash` duplicates `onchain_receipts` | Non-blocking | Yes | No |
| 7 | `tool_receipt` vs `evidence_receipts[]` drift risk | Non-blocking | Maybe | Yes |
| 8 | Scalar fields lack bounds/patterns/minLength | Suggestion | Yes | No |
| 9 | `readiness` enum under-defined vs capital gate | Suggestion | No | Yes |
| 10 | Reserved `oneOf` wording ambiguous | Suggestion | No | Yes |

**Next step:** The two blocking issues (1, 2) are flagged for the orchestrator to create fix features. The remaining eight issues are documented here as follow-up TODOs and recommended for resolution before v0 freeze.
