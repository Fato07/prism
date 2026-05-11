# ERC-8004 Contract Interface Reference for Prism

> Auto-generated from EIP-8004 spec + Arc testnet verification on 2026-05-12.

## Contract Addresses (Arc Testnet — Chain ID 5042002)

| Registry | Address | Verified |
|---|---|---|
| **IdentityRegistry** | `0x8004A818BFB912233c491871b3d84c89A494BD9e` | ✅ name()="AgentIdentity", symbol()="AGENT" |
| **ReputationRegistry** | `0x8004B663056A597Dffe9eCcC1965A193B7388713` | ✅ getIdentityRegistry() returns IdentityRegistry address |
| **ValidationRegistry** | `0x8004Cb1BF31DAf7788923b405b754f57acEB4272` | ✅ getIdentityRegistry() returns IdentityRegistry address |
| **USDC Precompile** | `0x3600000000000000000000000000000000000000` | (ERC-20 interface, 6 decimals) |

**Public RPC:** `https://rpc.testnet.arc.network/`  
**Explorer:** `https://testnet.arcscan.app/`

---

## 1. IdentityRegistry (ERC-721 + ERC-8004 Extensions)

The IdentityRegistry is an ERC-721 with URIStorage extension. Each agent is an NFT.

### Write Functions (for Circle Developer-Controlled Wallets `abiFunctionSignature`)

| Function | Selector | Access Control |
|---|---|---|
| `register(string)` | `0xf2c298be` | Anyone — mints a new agent NFT to `msg.sender`, takes `agentURI` |
| `register()` | `0x1aa3a008` | Anyone — mints without URI (set later via `setAgentURI`) |
| `setAgentURI(uint256,string)` | `0x0af28bd3` | Owner/operator of `agentId` only |
| `setMetadata(uint256,string,bytes)` | `0x466648da` | Owner/operator of `agentId` only. Cannot set reserved key `agentWallet` |
| `setAgentWallet(uint256,address,uint256,bytes)` | `0x2d1ef5ae` | Owner/operator. Requires EIP-712 or ERC-1271 signature from `newWallet` |
| `unsetAgentWallet(uint256)` | `0x3fddcf19` | Owner/operator |

### Read Functions

| Function | Selector | Returns |
|---|---|---|
| `name()` | `0x06fdde03` | `string` — "AgentIdentity" |
| `symbol()` | `0x95d89b41` | `string` — "AGENT" |
| `ownerOf(uint256)` | `0x6352211e` | `address` |
| `tokenURI(uint256)` | `0xc87b56dd` | `string` — the agentURI (IPFS/HTTPS) |
| `balanceOf(address)` | `0x70a08231` | `uint256` |
| `getMetadata(uint256,string)` | `0xcb4799f2` | `bytes` — metadata value for key |
| `getAgentWallet(uint256)` | `0x00339509` | `address` — payment wallet for agent |

### Events

| Event | Topic0 |
|---|---|
| `Transfer(address indexed from, address indexed to, uint256 indexed tokenId)` | `0xddf252ad...` |
| `URIUpdated(uint256 indexed agentId, string newURI, address indexed updatedBy)` | `0x3a2c7fff...` |
| `MetadataSet(uint256 indexed agentId, string indexed indexedMetadataKey, string metadataKey, bytes metadataValue)` | `0x2c149ed5...` |

### Circle SDK Usage Pattern

```python
# Register agent identity
tx = await circle_client.createContractExecutionTransaction({
    "walletAddress": owner_wallet_address,
    "blockchain": "ARC-TESTNET",
    "contractAddress": "0x8004A818BFB912233c491871b3d84c89A494BD9e",
    "abiFunctionSignature": "register(string)",
    "abiParameters": [metadata_uri],
    "feeLevel": "MEDIUM",
})
```

---

## 2. ReputationRegistry

### Write Functions

| Function | Selector | Access Control |
|---|---|---|
| `giveFeedback(uint256,int128,uint8,string,string,string,string,bytes32)` | `0x3c036a7e` | Anyone EXCEPT the agent's owner/operator (prevents self-dealing) |
| `revokeFeedback(uint256,uint64)` | `0x4ab3ca99` | Only the original feedback submitter (`clientAddress`) |

**`giveFeedback` parameter details:**
1. `uint256 agentId` — must be a valid registered agent
2. `int128 value` — signed feedback score (e.g., 95 for positive, -50 for negative)
3. `uint8 valueDecimals` — decimal precision (0-18). Use 0 for integer scores
4. `string tag1` — primary category tag (e.g., "successful_trade", "reasoning_quality"). OPTIONAL
5. `string tag2` — secondary tag. OPTIONAL
6. `string endpoint` — endpoint URI. OPTIONAL (emitted but NOT stored)
7. `string feedbackURI` — IPFS URI to detailed feedback JSON. OPTIONAL (emitted but NOT stored)
8. `bytes32 feedbackHash` — keccak256 of feedback content. OPTIONAL for IPFS URIs (emitted but NOT stored)

**Important:** Fields `value`, `valueDecimals`, `tag1`, `tag2`, and `isRevoked` are **stored on-chain**. Fields `endpoint`, `feedbackURI`, and `feedbackHash` are **emitted in events only** (not stored).

### Read Functions

| Function | Selector | Returns |
|---|---|---|
| `getSummary(uint256,address[],string,string)` | `0x81bbba58` | `(uint64 count, int128 summaryValue, uint8 summaryValueDecimals)` |
| `getClients(uint256)` | `0x42dd519c` | `address[]` — all addresses that gave feedback |
| `getLastIndex(uint256,address)` | `0xf2d81759` | `uint64` — last feedback index from that client |
| `getIdentityRegistry()` | `0xbc4d861b` | `address` |

**`getSummary` notes:**
- `agentId` and `clientAddresses` are mandatory
- `tag1` and `tag2` are optional filters
- `clientAddresses` MUST be non-empty (filtering by reviewer is required to mitigate Sybil attacks)

### Events

| Event | Topic0 |
|---|---|
| `NewFeedback(uint256 indexed agentId, address indexed clientAddress, uint64 feedbackIndex, int128 value, uint8 valueDecimals, string indexed indexedTag1, string tag1, string tag2, string endpoint, string feedbackURI, bytes32 feedbackHash)` | `0x6a4a6174...` |
| `FeedbackRevoked(uint256 indexed agentId, address indexed clientAddress, uint64 indexed feedbackIndex)` | `0x25156fd3...` |

### Circle SDK Usage Pattern

```python
# Record reputation (must use a DIFFERENT wallet than the agent owner)
tx = await circle_client.createContractExecutionTransaction({
    "walletAddress": oracle_wallet_address,  # NOT the agent owner
    "blockchain": "ARC-TESTNET",
    "contractAddress": "0x8004B663056A597Dffe9eCcC1965A193B7388713",
    "abiFunctionSignature": "giveFeedback(uint256,int128,uint8,string,string,string,string,bytes32)",
    "abiParameters": [agent_id, "95", "0", "successful_trade", "", "", feedback_uri, feedback_hash],
    "feeLevel": "MEDIUM",
})
```

---

## 3. ValidationRegistry

### Write Functions

| Function | Selector | Access Control |
|---|---|---|
| `validationRequest(address,uint256,string,bytes32)` | `0xaaf400c4` | Owner/operator of `agentId` only |
| `validationResponse(bytes32,uint8,string,bytes32,string)` | `0x3d659a96` | Only the `validatorAddress` specified in the original request |

**`validationRequest` parameters:**
1. `address validatorAddress` — the address that will respond
2. `uint256 agentId` — the agent being validated
3. `string requestURI` — points to off-chain data for the validator
4. `bytes32 requestHash` — keccak256 commitment to the request payload. Also serves as the request ID

**`validationResponse` parameters:**
1. `bytes32 requestHash` — references the original request
2. `uint8 response` — 0-100 score (0=failed, 100=passed, intermediate for spectrum)
3. `string responseURI` — off-chain evidence/audit. OPTIONAL
4. `bytes32 responseHash` — commitment to response content. OPTIONAL
5. `string tag` — custom categorization. OPTIONAL

**Important:** `validationResponse()` can be called MULTIPLE TIMES for the same `requestHash` (progressive validation, updates).

### Read Functions

| Function | Selector | Returns |
|---|---|---|
| `getValidationStatus(bytes32)` | `0xff2febfc` | `(address validatorAddress, uint256 agentId, uint8 response, bytes32 responseHash, string tag, uint256 lastUpdate)` |
| `getSummary(uint256,address[],string)` | `0x1b7cabd6` | `(uint64 count, uint8 averageResponse)` |
| `getAgentValidations(uint256)` | `0x8d5d0c2d` | `bytes32[]` — all requestHashes for the agent |
| `getValidatorRequests(address)` | `0x4bf3158c` | `bytes32[]` — all requestHashes assigned to a validator |
| `getIdentityRegistry()` | `0xbc4d861b` | `address` |

### Events

| Event | Topic0 |
|---|---|
| `ValidationRequest(address indexed validatorAddress, uint256 indexed agentId, bytes32 indexed requestHash, string requestURI)` | `0xeeea83f2...` |
| `ValidationResponse(address indexed validatorAddress, uint256 indexed agentId, bytes32 indexed requestHash, uint8 response, string responseURI, bytes32 responseHash, string tag)` | `0xafddf629...` |

### Circle SDK Usage Pattern

```python
# Owner requests validation
tx = await circle_client.createContractExecutionTransaction({
    "walletAddress": trader_wallet_address,  # Agent owner
    "blockchain": "ARC-TESTNET",
    "contractAddress": "0x8004Cb1BF31DAf7788923b405b754f57acEB4272",
    "abiFunctionSignature": "validationRequest(address,uint256,string,bytes32)",
    "abiParameters": [sentinel_wallet_address, agent_id, trace_ipfs_uri, request_hash],
    "feeLevel": "MEDIUM",
})

# Sentinel responds with validation verdict
tx = await circle_client.createContractExecutionTransaction({
    "walletAddress": sentinel_wallet_address,  # Must match validatorAddress
    "blockchain": "ARC-TESTNET",
    "contractAddress": "0x8004Cb1BF31DAf7788923b405b754f57acEB4272",
    "abiFunctionSignature": "validationResponse(bytes32,uint8,string,bytes32,string)",
    "abiParameters": [request_hash, str(verdict_score), response_uri, response_hash, tag],
    "feeLevel": "MEDIUM",
})
```

---

## Differences from MISSION.md Assumptions

| What MISSION.md assumes | Actual (EIP-8004 spec) | Impact |
|---|---|---|
| `register(string agentCardUri)` | `register(string)` — param name is `agentURI` not `agentCardUri` | **No impact** — same ABI signature, param name doesn't affect encoding |
| `getAgentCard(uint256 agentId)` | `tokenURI(uint256)` — standard ERC-721 tokenURI | **Must use `tokenURI` not `getAgentCard`** |
| ReputationRegistry `giveFeedback` with param names from AGENTS.md | Confirmed exact match: `giveFeedback(uint256,int128,uint8,string,string,string,string,bytes32)` | ✅ Matches |
| ValidationRegistry signatures | Confirmed exact match for both `validationRequest` and `validationResponse` | ✅ Matches |
| — | `getSummary` has different signatures in Reputation vs Validation registries | Be careful: Reputation has `(uint256,address[],string,string)`, Validation has `(uint256,address[],string)` |

---

## Gotchas & Key Notes

1. **Self-dealing prevention**: `giveFeedback` will REVERT if called by the agent's owner or approved operator. Prism's oracle-wallet MUST be a different wallet than the trader-wallet.

2. **No `getAgentCard` function**: The function name from MISSION.md doesn't exist. Use standard ERC-721 `tokenURI(uint256)` instead.

3. **Gas costs**: On Arc, gas is ~0.006 USDC per transaction. All functions are non-payable (no ETH/USDC value attached to calls).

4. **requestHash is the key**: In ValidationRegistry, `requestHash` is both a commitment AND the primary key for lookups. Prism should compute `requestHash = keccak256(trace_content)` to make it deterministic.

5. **Multiple validation responses**: `validationResponse()` can be called multiple times for the same `requestHash`, overwriting the previous response. This enables progressive validation.

6. **Feedback storage split**: In ReputationRegistry, `value`, `valueDecimals`, `tag1`, `tag2`, `isRevoked` are stored on-chain. But `endpoint`, `feedbackURI`, `feedbackHash` are ONLY emitted in events (not stored). Use event indexing to retrieve these.

7. **ERC-721 Transfer events**: When `register()` is called, it mints an NFT emitting a standard `Transfer(address(0), owner, tokenId)` event. Parse this to get the `agentId` (tokenId).

8. **Circle SDK blockchain value**: Use `"ARC-TESTNET"` (not a chain ID number) when calling `createContractExecutionTransaction`.

9. **USDC decimals mismatch**: Native USDC gas uses 18 decimals, but ERC-20 USDC interface uses 6 decimals. Always use the ERC-20 interface for balance/transfer operations.

10. **Wallet type**: Arc docs recommend `accountType: "SCA"` (Smart Contract Account) for ERC-8004 flows with Circle wallets.
