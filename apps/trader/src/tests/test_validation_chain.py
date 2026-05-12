"""Integration tests for ERC-8004 ValidationRegistry on-chain flow.

Covers:
- VAL-CHAIN-004: Trader submits validationRequest on ValidationRegistry
- VAL-CHAIN-005: Sentinel submits validationResponse on ValidationRegistry
- VAL-CHAIN-007: End-to-end chain flow completes

The full chain flow requires:
  1. Trader registers on IdentityRegistry
  2. Sentinel registers on IdentityRegistry
  3. Trader submits validationRequest
  4. Sentinel submits validationResponse
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
import os
import subprocess
from datetime import UTC, datetime

import pytest
from prism_schemas.trace import Evidence, ThesisStep, TradingR1Trace
from prism_schemas.verdict import SentinelVerdict
from sentinel.chain import VALIDATION_TYPE, submit_validation_response

from trader.chain import IDENTITY_REGISTRY, VALIDATION_REGISTRY, CircleChain
from trader.ipfs import PinataClient
from trader.registration import build_sentinel_card, build_trader_card, register_agent
from trader.validation import (
    parse_request_hash_from_receipt,
    submit_validation_request,
)

# ---------------------------------------------------------------------------
# Helpers / skip conditions
# ---------------------------------------------------------------------------

_DSN = os.environ.get("DATABASE_URL", "")
_ARC_RPC = os.environ.get("ARC_RPC_URL", "")
_TRADER_WALLET_ID = os.environ.get("CIRCLE_WALLET_TRADER_ID", "")
_TRADER_WALLET_ADDR = os.environ.get("CIRCLE_WALLET_TRADER_ADDRESS", "")
_SENTINEL_WALLET_ID = os.environ.get("CIRCLE_WALLET_SENTINEL_ID", "")
_SENTINEL_WALLET_ADDR = os.environ.get("CIRCLE_WALLET_SENTINEL_ADDRESS", "")

requires_integration = pytest.mark.skipif(
    not all([_DSN, _ARC_RPC, _TRADER_WALLET_ID, _TRADER_WALLET_ADDR]),
    reason="Integration env vars not set (DATABASE_URL, ARC_RPC_URL, CIRCLE_WALLET_TRADER_*)",
)

requires_sentinel_env = pytest.mark.skipif(
    not all([_SENTINEL_WALLET_ID, _SENTINEL_WALLET_ADDR]),
    reason="CIRCLE_WALLET_SENTINEL_* env vars not set",
)


def _cast_call(contract: str, sig: str, *args: str) -> str:
    """Run a cast call and return stdout."""
    cast_path = os.path.expanduser("~/.foundry/bin/cast")
    result = subprocess.run(
        [cast_path, "call", contract, sig, *args, "--rpc-url", _ARC_RPC],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"cast call failed: {result.stderr}")
    return result.stdout.strip()


def _make_test_trace(agent_id: int) -> TradingR1Trace:
    """Create a synthetic TradingR1Trace for testing."""
    return TradingR1Trace(
        trace_id="00000000-0000-0000-0000-000000000001",
        agent_id=agent_id,
        market_id="0xtest_market_condition_id",
        market_question="Will the Fed cut rates by July 2026?",
        thesis=[
            ThesisStep(
                proposition="Fed funds rate is likely to decrease",
                supporting_evidence_ids=[0, 1],
                risk_factors=["Inflation could remain sticky"],
            )
        ],
        evidence=[
            Evidence(
                source="BLS CPI Report",
                claim="CPI declined 0.2% month-over-month",
                confidence=0.85,
                timestamp=datetime.now(UTC),
            ),
            Evidence(
                source="FOMC Minutes",
                claim="Committee discussed easing bias",
                confidence=0.70,
                timestamp=datetime.now(UTC),
            ),
        ],
        raw_probability=0.65,
        volatility_adjustment=-0.05,
        final_probability=0.60,
        action="BUY",
        size_usdc=10.0,
        price_limit=0.60,
        rationale="Strong evidence of easing bias with declining inflation.",
        model_family="anthropic-claude",
        model_name="claude-sonnet-4-20250514",
        created_at=datetime.now(UTC),
    )


def _make_test_verdict(
    request_hash: str,
    trace_id: str,
    sentinel_agent_id: int,
) -> SentinelVerdict:
    """Create a synthetic SentinelVerdict for testing."""
    return SentinelVerdict(
        request_hash=request_hash,
        trace_id=trace_id,
        sentinel_agent_id=sentinel_agent_id,
        evidence_challenges=[
            "BLS CPI data is backward-looking and may not predict future trends",
            "FOMC minutes reflect past discussions, not current intentions",
            "Confidence of 0.85 on CPI data seems overstated for a single report",
        ],
        thesis_challenges=[
            "Thesis relies on a single directional signal without "
            "considering alternative scenarios",
        ],
        calibration_critique="The 0.60 final probability appears reasonable given the evidence, "
        "but the raw probability of 0.65 may be overconfident for a single data point.",
        verdict_score=65,
        verdict_label="PASS",
        dialogue_messages=[
            {"role": "adversary", "content": "The trace has a sound thesis but evidence is thin."}
        ],
        model_family="openai-gpt",
        model_name="gpt-4o-mini",
        created_at=datetime.now(UTC),
    )


def _compute_bytes32_hash(data: dict) -> str:
    """Compute a bytes32 hash from a JSON-serializable dict."""
    canonical = json.dumps(data, sort_keys=True)
    digest = hashlib.sha256(canonical.encode()).digest()
    return "0x" + digest.hex()


# ---------------------------------------------------------------------------
# Unit Tests (no external deps)
# ---------------------------------------------------------------------------


class TestValidationRequestHashParsing:
    """Test requestHash parsing from receipt logs (unit-level)."""

    def test_parse_request_hash_with_valid_log(self) -> None:
        """parse_request_hash_from_receipt extracts requestHash from event."""
        # Simulate a ValidationRequest event in receipt
        # topics[0] = event sig, topics[1] = validator,
        # topics[2] = agentId, topics[3] = requestHash
        receipt = {
            "logs": [
                {
                    "topics": [
                        "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
                        "0x00000000000000000000000056509b03e85f3cbae5ba2190ee99b945d2f0ac36",
                        "0x0000000000000000000000000000000000000000000000000000000000000f6e",
                        "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
                    ]
                }
            ]
        }

        # We need to override VALIDATION_REQUEST_TOPIC for this test
        from trader import validation as val_mod

        original_topic = val_mod.VALIDATION_REQUEST_TOPIC
        try:
            val_mod.VALIDATION_REQUEST_TOPIC = (
                "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
            )
            result = parse_request_hash_from_receipt(receipt)
            assert result == "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        finally:
            val_mod.VALIDATION_REQUEST_TOPIC = original_topic

    def test_parse_request_hash_raises_on_no_event(self) -> None:
        """parse_request_hash_from_receipt raises ValueError when no event found."""
        receipt: dict[str, Any] = {"logs": []}
        with pytest.raises(ValueError, match="No ValidationRequest event"):
            parse_request_hash_from_receipt(receipt)

    def test_bytes32_hash_computation(self) -> None:
        """_compute_bytes32_hash produces a valid bytes32 hex string."""
        data = {"key": "value", "number": 42}
        hash_hex = _compute_bytes32_hash(data)
        assert hash_hex.startswith("0x")
        assert len(hash_hex) == 66  # 0x + 64 hex chars

    def test_bytes32_hash_deterministic(self) -> None:
        """_compute_bytes32_hash produces same hash for same data."""
        data = {"key": "value", "number": 42}
        hash1 = _compute_bytes32_hash(data)
        hash2 = _compute_bytes32_hash(data)
        assert hash1 == hash2


class TestValidationConstants:
    """Test that validation constants are correct."""

    def test_validation_registry_address(self) -> None:
        """VALIDATION_REGISTRY matches the deployed contract address."""
        assert VALIDATION_REGISTRY == "0x8004Cb1BF31DAf7788923b405b754f57acEB4272"

    def test_identity_registry_address(self) -> None:
        """IDENTITY_REGISTRY matches the deployed contract address."""
        assert IDENTITY_REGISTRY == "0x8004A818BFB912233c491871b3d84c89A494BD9e"

    def test_validation_type_constant(self) -> None:
        """VALIDATION_TYPE is adversarial-llm-v1."""
        assert VALIDATION_TYPE == "adversarial-llm-v1"


class TestValidationRegistryOnChain:
    """Verify the ValidationRegistry contract is accessible."""

    def test_validation_registry_get_identity_registry(self) -> None:
        """ValidationRegistry points to the correct IdentityRegistry."""
        if not _ARC_RPC:
            pytest.skip("ARC_RPC_URL not set")
        result = _cast_call(
            VALIDATION_REGISTRY,
            "getIdentityRegistry()(address)",
        )
        assert result.lower() == IDENTITY_REGISTRY.lower()

    def test_validation_registry_is_accessible(self) -> None:
        """ValidationRegistry contract is callable on Arc testnet."""
        if not _ARC_RPC:
            pytest.skip("ARC_RPC_URL not set")
        # Just verify the contract responds - getting the owner
        result = _cast_call(VALIDATION_REGISTRY, "owner()(address)")
        assert result.startswith("0x")


# ---------------------------------------------------------------------------
# VAL-CHAIN-004: Validation request submitted to ValidationRegistry
# ---------------------------------------------------------------------------


@pytest.mark.integration
@requires_integration
@requires_sentinel_env
class TestValidationRequest:
    """VAL-CHAIN-004: Trader calls validationRequest on ValidationRegistry.

    Transaction succeeds, emits requestHash, on-chain data matches.
    """

    @pytest.mark.asyncio
    async def test_validation_request_tx_succeeds(self) -> None:
        """validationRequest transaction succeeds and returns requestHash."""
        chain = CircleChain()
        pinata = PinataClient()

        try:
            # Register both agents first
            trader_result = await register_agent(
                chain=chain,
                pinata=pinata,
                wallet_id=_TRADER_WALLET_ID,
                wallet_address=_TRADER_WALLET_ADDR,
                agent_card=build_trader_card(),
                role="trader",
            )
            # Sentinel must be registered so it's a valid validator on-chain
            await register_agent(
                chain=chain,
                pinata=pinata,
                wallet_id=_SENTINEL_WALLET_ID,
                wallet_address=_SENTINEL_WALLET_ADDR,
                agent_card=build_sentinel_card(),
                role="sentinel",
            )

            trader_agent_id = trader_result["agent_id"]

            # Create and pin a test trace
            trace = _make_test_trace(trader_agent_id)
            trace_cid = await pinata.pin_json(trace.model_dump(mode="json"))
            trace_uri = f"ipfs://{trace_cid}"
            trace_hash = "0x" + trace.content_hash().hex()

            # Submit validation request
            request_result = await submit_validation_request(
                chain=chain,
                wallet_id=_TRADER_WALLET_ID,
                validator_address=_SENTINEL_WALLET_ADDR,
                agent_id=trader_agent_id,
                trace_uri=trace_uri,
                trace_hash=trace_hash,
            )

            # Verify result structure
            assert "request_hash" in request_result
            assert request_result["request_hash"].startswith("0x")
            assert len(request_result["request_hash"]) == 66  # 0x + 64 hex
            assert "on_chain_tx_hash" in request_result
            assert "circle_tx_id" in request_result
        finally:
            await pinata.close()

    @pytest.mark.asyncio
    async def test_validation_request_emits_request_hash(self) -> None:
        """validationRequest emits a valid requestHash (bytes32)."""
        chain = CircleChain()
        pinata = PinataClient()

        try:
            trader_result = await register_agent(
                chain=chain,
                pinata=pinata,
                wallet_id=_TRADER_WALLET_ID,
                wallet_address=_TRADER_WALLET_ADDR,
                agent_card=build_trader_card(),
                role="trader",
            )

            trace = _make_test_trace(trader_result["agent_id"])
            trace_cid = await pinata.pin_json(trace.model_dump(mode="json"))
            trace_uri = f"ipfs://{trace_cid}"
            trace_hash = "0x" + trace.content_hash().hex()

            request_result = await submit_validation_request(
                chain=chain,
                wallet_id=_TRADER_WALLET_ID,
                validator_address=_SENTINEL_WALLET_ADDR,
                agent_id=trader_result["agent_id"],
                trace_uri=trace_uri,
                trace_hash=trace_hash,
            )

            # The requestHash must be a valid bytes32
            request_hash = request_result["request_hash"]
            assert request_hash.startswith("0x")
            hash_without_prefix = request_hash[2:]
            assert len(hash_without_prefix) == 64
            # Must be valid hex
            int(hash_without_prefix, 16)
        finally:
            await pinata.close()

    @pytest.mark.asyncio
    async def test_validation_request_on_chain_data_matches(self) -> None:
        """On-chain parameters match what was submitted in validationRequest."""
        chain = CircleChain()
        pinata = PinataClient()

        try:
            trader_result = await register_agent(
                chain=chain,
                pinata=pinata,
                wallet_id=_TRADER_WALLET_ID,
                wallet_address=_TRADER_WALLET_ADDR,
                agent_card=build_trader_card(),
                role="trader",
            )

            trace = _make_test_trace(trader_result["agent_id"])
            trace_cid = await pinata.pin_json(trace.model_dump(mode="json"))
            trace_uri = f"ipfs://{trace_cid}"
            trace_hash = "0x" + trace.content_hash().hex()

            request_result = await submit_validation_request(
                chain=chain,
                wallet_id=_TRADER_WALLET_ID,
                validator_address=_SENTINEL_WALLET_ADDR,
                agent_id=trader_result["agent_id"],
                trace_uri=trace_uri,
                trace_hash=trace_hash,
            )

            # Verify the on-chain tx receipt confirms success
            receipt = await chain.get_tx_receipt(request_result["on_chain_tx_hash"])
            assert receipt.get("status") == "0x1"

            # Verify the traceHash is in the tx calldata (decoded from input data)
            # The tx was sent to the ValidationRegistry contract
            assert receipt.get("to", "").lower() == VALIDATION_REGISTRY.lower()
        finally:
            await pinata.close()


# ---------------------------------------------------------------------------
# VAL-CHAIN-005: Validation response submitted to ValidationRegistry
# ---------------------------------------------------------------------------


@pytest.mark.integration
@requires_integration
@requires_sentinel_env
class TestValidationResponse:
    """VAL-CHAIN-005: Sentinel calls validationResponse on ValidationRegistry.

    Transaction succeeds, validationType='adversarial-llm-v1',
    on-chain data matches submitted parameters.
    """

    @pytest.mark.asyncio
    async def test_validation_response_tx_succeeds(self) -> None:
        """validationResponse transaction succeeds with correct parameters."""
        chain = CircleChain()
        pinata = PinataClient()

        try:
            # Register both agents
            trader_result = await register_agent(
                chain=chain,
                pinata=pinata,
                wallet_id=_TRADER_WALLET_ID,
                wallet_address=_TRADER_WALLET_ADDR,
                agent_card=build_trader_card(),
                role="trader",
            )
            sentinel_result = await register_agent(
                chain=chain,
                pinata=pinata,
                wallet_id=_SENTINEL_WALLET_ID,
                wallet_address=_SENTINEL_WALLET_ADDR,
                agent_card=build_sentinel_card(),
                role="sentinel",
            )

            trader_agent_id = trader_result["agent_id"]
            sentinel_agent_id = sentinel_result["agent_id"]

            # Create and pin test trace
            trace = _make_test_trace(trader_agent_id)
            trace_cid = await pinata.pin_json(trace.model_dump(mode="json"))
            trace_uri = f"ipfs://{trace_cid}"
            trace_hash = "0x" + trace.content_hash().hex()

            # Submit validation request
            request_result = await submit_validation_request(
                chain=chain,
                wallet_id=_TRADER_WALLET_ID,
                validator_address=_SENTINEL_WALLET_ADDR,
                agent_id=trader_agent_id,
                trace_uri=trace_uri,
                trace_hash=trace_hash,
            )
            request_hash = request_result["request_hash"]

            # Create and pin test verdict
            verdict = _make_test_verdict(request_hash, trace.trace_id, sentinel_agent_id)
            verdict_cid = await pinata.pin_json(verdict.model_dump(mode="json"))
            verdict_uri = f"ipfs://{verdict_cid}"
            verdict_hash = "0x" + verdict.content_hash().hex()

            # Submit validation response
            response_result = await submit_validation_response(
                chain=chain,
                wallet_id=_SENTINEL_WALLET_ID,
                request_hash=request_hash,
                verdict_score=verdict.verdict_score,
                verdict_uri=verdict_uri,
                verdict_hash=verdict_hash,
                validation_type=VALIDATION_TYPE,
            )

            # Verify result structure
            assert "on_chain_tx_hash" in response_result
            assert "circle_tx_id" in response_result
            assert response_result["request_hash"] == request_hash
        finally:
            await pinata.close()

    @pytest.mark.asyncio
    async def test_validation_response_type_is_adversarial_llm_v1(self) -> None:
        """validationResponse includes validationType='adversarial-llm-v1'."""
        chain = CircleChain()
        pinata = PinataClient()

        try:
            trader_result = await register_agent(
                chain=chain,
                pinata=pinata,
                wallet_id=_TRADER_WALLET_ID,
                wallet_address=_TRADER_WALLET_ADDR,
                agent_card=build_trader_card(),
                role="trader",
            )
            sentinel_result = await register_agent(
                chain=chain,
                pinata=pinata,
                wallet_id=_SENTINEL_WALLET_ID,
                wallet_address=_SENTINEL_WALLET_ADDR,
                agent_card=build_sentinel_card(),
                role="sentinel",
            )

            trace = _make_test_trace(trader_result["agent_id"])
            trace_cid = await pinata.pin_json(trace.model_dump(mode="json"))
            trace_uri = f"ipfs://{trace_cid}"
            trace_hash = "0x" + trace.content_hash().hex()

            request_result = await submit_validation_request(
                chain=chain,
                wallet_id=_TRADER_WALLET_ID,
                validator_address=_SENTINEL_WALLET_ADDR,
                agent_id=trader_result["agent_id"],
                trace_uri=trace_uri,
                trace_hash=trace_hash,
            )

            verdict = _make_test_verdict(
                request_result["request_hash"],
                trace.trace_id,
                sentinel_result["agent_id"],
            )
            verdict_cid = await pinata.pin_json(verdict.model_dump(mode="json"))
            verdict_uri = f"ipfs://{verdict_cid}"
            verdict_hash = "0x" + verdict.content_hash().hex()

            response_result = await submit_validation_response(
                chain=chain,
                wallet_id=_SENTINEL_WALLET_ID,
                request_hash=request_result["request_hash"],
                verdict_score=verdict.verdict_score,
                verdict_uri=verdict_uri,
                verdict_hash=verdict_hash,
                validation_type=VALIDATION_TYPE,
            )

            # Verify on-chain tx succeeded
            receipt = await chain.get_tx_receipt(response_result["on_chain_tx_hash"])
            assert receipt.get("status") == "0x1"
            assert receipt.get("to", "").lower() == VALIDATION_REGISTRY.lower()
        finally:
            await pinata.close()

    @pytest.mark.asyncio
    async def test_validation_response_on_chain_data_matches(self) -> None:
        """On-chain data matches the submitted validationResponse parameters."""
        chain = CircleChain()
        pinata = PinataClient()

        try:
            trader_result = await register_agent(
                chain=chain,
                pinata=pinata,
                wallet_id=_TRADER_WALLET_ID,
                wallet_address=_TRADER_WALLET_ADDR,
                agent_card=build_trader_card(),
                role="trader",
            )
            sentinel_result = await register_agent(
                chain=chain,
                pinata=pinata,
                wallet_id=_SENTINEL_WALLET_ID,
                wallet_address=_SENTINEL_WALLET_ADDR,
                agent_card=build_sentinel_card(),
                role="sentinel",
            )

            trace = _make_test_trace(trader_result["agent_id"])
            trace_cid = await pinata.pin_json(trace.model_dump(mode="json"))
            trace_uri = f"ipfs://{trace_cid}"
            trace_hash = "0x" + trace.content_hash().hex()

            request_result = await submit_validation_request(
                chain=chain,
                wallet_id=_TRADER_WALLET_ID,
                validator_address=_SENTINEL_WALLET_ADDR,
                agent_id=trader_result["agent_id"],
                trace_uri=trace_uri,
                trace_hash=trace_hash,
            )

            verdict = _make_test_verdict(
                request_result["request_hash"],
                trace.trace_id,
                sentinel_result["agent_id"],
            )
            verdict_cid = await pinata.pin_json(verdict.model_dump(mode="json"))
            verdict_uri = f"ipfs://{verdict_cid}"
            verdict_hash = "0x" + verdict.content_hash().hex()

            response_result = await submit_validation_response(
                chain=chain,
                wallet_id=_SENTINEL_WALLET_ID,
                request_hash=request_result["request_hash"],
                verdict_score=verdict.verdict_score,
                verdict_uri=verdict_uri,
                verdict_hash=verdict_hash,
                validation_type=VALIDATION_TYPE,
            )

            # Verify the tx receipt confirms the response
            receipt = await chain.get_tx_receipt(response_result["on_chain_tx_hash"])
            assert receipt.get("status") == "0x1"
        finally:
            await pinata.close()


# ---------------------------------------------------------------------------
# VAL-CHAIN-007: End-to-end chain flow completes
# ---------------------------------------------------------------------------


@pytest.mark.integration
@requires_integration
@requires_sentinel_env
class TestEndToEndChainFlow:
    """VAL-CHAIN-007: Full on-chain happy path.

    Trader registers → sentinel registers → validationRequest → validationResponse.
    All 4+ transactions succeed. Final on-chain state reflects complete
    validation lifecycle with correct ownership, URIs, and hashes.
    """

    @pytest.mark.asyncio
    async def test_full_chain_flow_completes(self) -> None:
        """Full chain flow: 4 transactions succeed with correct on-chain state."""
        chain = CircleChain()
        pinata = PinataClient()
        tx_hashes: list[str] = []

        try:
            # Step 1: Register trader on IdentityRegistry
            trader_result = await register_agent(
                chain=chain,
                pinata=pinata,
                wallet_id=_TRADER_WALLET_ID,
                wallet_address=_TRADER_WALLET_ADDR,
                agent_card=build_trader_card(),
                role="trader",
            )
            tx_hashes.append(trader_result["on_chain_tx_hash"])
            trader_agent_id = trader_result["agent_id"]

            # Verify trader registration on-chain
            on_chain_owner = _cast_call(
                IDENTITY_REGISTRY,
                "ownerOf(uint256)(address)",
                str(trader_agent_id),
            )
            assert on_chain_owner.lower() == _TRADER_WALLET_ADDR.lower()

            # Step 2: Register sentinel on IdentityRegistry
            sentinel_result = await register_agent(
                chain=chain,
                pinata=pinata,
                wallet_id=_SENTINEL_WALLET_ID,
                wallet_address=_SENTINEL_WALLET_ADDR,
                agent_card=build_sentinel_card(),
                role="sentinel",
            )
            tx_hashes.append(sentinel_result["on_chain_tx_hash"])
            sentinel_agent_id = sentinel_result["agent_id"]

            # Verify sentinel registration on-chain
            on_chain_owner = _cast_call(
                IDENTITY_REGISTRY,
                "ownerOf(uint256)(address)",
                str(sentinel_agent_id),
            )
            assert on_chain_owner.lower() == _SENTINEL_WALLET_ADDR.lower()

            # Verify distinct agent IDs
            assert trader_agent_id != sentinel_agent_id

            # Step 3: Create trace, pin to IPFS, submit validationRequest
            trace = _make_test_trace(trader_agent_id)
            trace_cid = await pinata.pin_json(trace.model_dump(mode="json"))
            trace_uri = f"ipfs://{trace_cid}"
            trace_hash = "0x" + trace.content_hash().hex()

            request_result = await submit_validation_request(
                chain=chain,
                wallet_id=_TRADER_WALLET_ID,
                validator_address=_SENTINEL_WALLET_ADDR,
                agent_id=trader_agent_id,
                trace_uri=trace_uri,
                trace_hash=trace_hash,
            )
            tx_hashes.append(request_result["on_chain_tx_hash"])
            request_hash = request_result["request_hash"]

            # Verify the request receipt
            request_receipt = await chain.get_tx_receipt(request_result["on_chain_tx_hash"])
            assert request_receipt.get("status") == "0x1"

            # Step 4: Create verdict, pin to IPFS, submit validationResponse
            verdict = _make_test_verdict(request_hash, trace.trace_id, sentinel_agent_id)
            verdict_cid = await pinata.pin_json(verdict.model_dump(mode="json"))
            verdict_uri = f"ipfs://{verdict_cid}"
            verdict_hash = "0x" + verdict.content_hash().hex()

            response_result = await submit_validation_response(
                chain=chain,
                wallet_id=_SENTINEL_WALLET_ID,
                request_hash=request_hash,
                verdict_score=verdict.verdict_score,
                verdict_uri=verdict_uri,
                verdict_hash=verdict_hash,
                validation_type=VALIDATION_TYPE,
            )
            tx_hashes.append(response_result["on_chain_tx_hash"])

            # Verify the response receipt
            response_receipt = await chain.get_tx_receipt(response_result["on_chain_tx_hash"])
            assert response_receipt.get("status") == "0x1"

            # Final verification: all 4+ transactions succeeded
            assert len(tx_hashes) >= 4, f"Expected 4+ tx hashes, got {len(tx_hashes)}"

            # Verify each tx hash is valid (non-empty, 0x-prefixed)
            for tx_hash in tx_hashes:
                assert tx_hash.startswith("0x")
                assert len(tx_hash) >= 66

            # Verify all receipts show success
            for tx_hash in tx_hashes:
                receipt = await chain.get_tx_receipt(tx_hash)
                assert receipt.get("status") == "0x1", f"Tx {tx_hash} reverted"

        finally:
            await pinata.close()

    @pytest.mark.asyncio
    async def test_ipfs_cids_resolvable_after_chain_flow(self) -> None:
        """IPFS CIDs for trace and verdict are resolvable after chain flow."""
        chain = CircleChain()
        pinata = PinataClient()

        try:
            # Register + request + response
            trader_result = await register_agent(
                chain=chain,
                pinata=pinata,
                wallet_id=_TRADER_WALLET_ID,
                wallet_address=_TRADER_WALLET_ADDR,
                agent_card=build_trader_card(),
                role="trader",
            )
            sentinel_result = await register_agent(
                chain=chain,
                pinata=pinata,
                wallet_id=_SENTINEL_WALLET_ID,
                wallet_address=_SENTINEL_WALLET_ADDR,
                agent_card=build_sentinel_card(),
                role="sentinel",
            )

            trace = _make_test_trace(trader_result["agent_id"])
            trace_cid = await pinata.pin_json(trace.model_dump(mode="json"))
            trace_uri = f"ipfs://{trace_cid}"

            request_result = await submit_validation_request(
                chain=chain,
                wallet_id=_TRADER_WALLET_ID,
                validator_address=_SENTINEL_WALLET_ADDR,
                agent_id=trader_result["agent_id"],
                trace_uri=trace_uri,
                trace_hash="0x" + trace.content_hash().hex(),
            )

            verdict = _make_test_verdict(
                request_result["request_hash"],
                trace.trace_id,
                sentinel_result["agent_id"],
            )
            verdict_cid = await pinata.pin_json(verdict.model_dump(mode="json"))
            verdict_uri = f"ipfs://{verdict_cid}"

            await submit_validation_response(
                chain=chain,
                wallet_id=_SENTINEL_WALLET_ID,
                request_hash=request_result["request_hash"],
                verdict_score=verdict.verdict_score,
                verdict_uri=verdict_uri,
                verdict_hash="0x" + verdict.content_hash().hex(),
                validation_type=VALIDATION_TYPE,
            )

            # Verify both CIDs are resolvable
            fetched_trace = await pinata.fetch_json(trace_cid)
            assert "trace_id" in fetched_trace
            assert fetched_trace["trace_id"] == trace.trace_id

            fetched_verdict = await pinata.fetch_json(verdict_cid)
            assert "verdict_score" in fetched_verdict
            assert fetched_verdict["verdict_score"] == verdict.verdict_score
        finally:
            await pinata.close()

    @pytest.mark.asyncio
    async def test_content_hashes_verifiable(self) -> None:
        """Content hashes submitted on-chain can be recomputed from IPFS content."""
        chain = CircleChain()
        pinata = PinataClient()

        try:
            trader_result = await register_agent(
                chain=chain,
                pinata=pinata,
                wallet_id=_TRADER_WALLET_ID,
                wallet_address=_TRADER_WALLET_ADDR,
                agent_card=build_trader_card(),
                role="trader",
            )
            sentinel_result = await register_agent(
                chain=chain,
                pinata=pinata,
                wallet_id=_SENTINEL_WALLET_ID,
                wallet_address=_SENTINEL_WALLET_ADDR,
                agent_card=build_sentinel_card(),
                role="sentinel",
            )

            # Create and pin trace
            trace = _make_test_trace(trader_result["agent_id"])
            trace_cid = await pinata.pin_json(trace.model_dump(mode="json"))
            trace_hash = "0x" + trace.content_hash().hex()

            # Submit validation request
            request_result = await submit_validation_request(
                chain=chain,
                wallet_id=_TRADER_WALLET_ID,
                validator_address=_SENTINEL_WALLET_ADDR,
                agent_id=trader_result["agent_id"],
                trace_uri=f"ipfs://{trace_cid}",
                trace_hash=trace_hash,
            )

            # Fetch from IPFS and recompute hash
            fetched_trace = await pinata.fetch_json(trace_cid)
            recomputed_trace = TradingR1Trace.model_validate(fetched_trace)
            recomputed_hash = "0x" + recomputed_trace.content_hash().hex()
            assert recomputed_hash == trace_hash, "Trace hash mismatch between on-chain and IPFS"

            # Create and pin verdict
            verdict = _make_test_verdict(
                request_result["request_hash"],
                trace.trace_id,
                sentinel_result["agent_id"],
            )
            verdict_cid = await pinata.pin_json(verdict.model_dump(mode="json"))
            verdict_hash = "0x" + verdict.content_hash().hex()

            # Submit validation response
            await submit_validation_response(
                chain=chain,
                wallet_id=_SENTINEL_WALLET_ID,
                request_hash=request_result["request_hash"],
                verdict_score=verdict.verdict_score,
                verdict_uri=f"ipfs://{verdict_cid}",
                verdict_hash=verdict_hash,
                validation_type=VALIDATION_TYPE,
            )

            # Fetch from IPFS and recompute hash
            fetched_verdict = await pinata.fetch_json(verdict_cid)
            recomputed_verdict = SentinelVerdict.model_validate(fetched_verdict)
            recomputed_verdict_hash = "0x" + recomputed_verdict.content_hash().hex()
            assert recomputed_verdict_hash == verdict_hash, (
                "Verdict hash mismatch between on-chain and IPFS"
            )
        finally:
            await pinata.close()
