"""Integration tests for ERC-8004 IdentityRegistry registration flow.

Covers:
- VAL-CHAIN-001: Trader registers on IdentityRegistry
- VAL-CHAIN-002: Agent card URI resolves to valid JSON
- VAL-CHAIN-003: Sentinel registers on IdentityRegistry (distinct agentId)
"""

from __future__ import annotations

import json
import os
import subprocess

import psycopg
import pytest
from prism_schemas.agent_card import AgentCard, AgentCardService, X402Support
from prism_schemas.db import run_migration

from trader.chain import IDENTITY_REGISTRY, CircleChain
from trader.ipfs import PinataClient
from trader.registration import (
    build_sentinel_card,
    build_trader_card,
    persist_registration,
    register_agent,
    register_sentinel,
    register_trader,
    verify_agent_card_content,
    verify_token_uri,
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


# ---------------------------------------------------------------------------
# Agent Card Schema Tests (unit tests — no external deps)
# ---------------------------------------------------------------------------


class TestAgentCardSchema:
    """Validate the AgentCard Pydantic model."""

    def test_trader_card_has_required_fields(self) -> None:
        """Trader card contains name, description, services, x402Support, active."""
        card = build_trader_card()
        assert card.name
        assert card.description
        assert len(card.services) >= 1
        assert isinstance(card.x402Support, X402Support)
        assert card.active is True

    def test_sentinel_card_has_required_fields(self) -> None:
        """Sentinel card contains name, description, services, x402Support, active."""
        card = build_sentinel_card()
        assert card.name
        assert card.description
        assert len(card.services) >= 1
        assert card.x402Support.enabled is True
        assert card.active is True

    def test_trader_card_x402_disabled(self) -> None:
        """Trader does not expose x402-protected endpoints."""
        card = build_trader_card()
        assert card.x402Support.enabled is False

    def test_sentinel_card_x402_enabled(self) -> None:
        """Sentinel exposes x402-protected validation endpoint."""
        card = build_sentinel_card()
        assert card.x402Support.enabled is True
        assert card.x402Support.price_usdc == 0.01

    def test_card_serializes_to_json(self) -> None:
        """Agent card can be serialized to JSON for IPFS pinning."""
        card = build_trader_card()
        json_str = json.dumps(card.model_dump(mode="json"))
        parsed = json.loads(json_str)
        assert "name" in parsed
        assert "description" in parsed
        assert "services" in parsed
        assert "x402Support" in parsed

    def test_card_model_validate_roundtrip(self) -> None:
        """Round-trip through JSON preserves all fields."""
        card = build_trader_card()
        json_str = json.dumps(card.model_dump(mode="json"))
        parsed = AgentCard.model_validate_json(json_str)
        assert parsed.name == card.name
        assert parsed.agent_role == card.agent_role

    def test_card_requires_at_least_one_service(self) -> None:
        """Agent card must have at least one service."""
        with pytest.raises(ValueError):
            AgentCard(
                name="test",
                description="test",
                services=[],
                agent_role="test",
            )

    def test_card_service_fields(self) -> None:
        """AgentCardService has name and description."""
        svc = AgentCardService(name="test_svc", description="A test service")
        assert svc.name == "test_svc"
        assert svc.description == "A test service"

    def test_x402_support_defaults(self) -> None:
        """X402Support defaults to enabled=True, price_usdc=0.01."""
        x402 = X402Support()
        assert x402.enabled is True
        assert x402.price_usdc == 0.01


# ---------------------------------------------------------------------------
# IPFS Pinning Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@requires_integration
class TestAgentCardIPFS:
    """Test that agent cards can be pinned to IPFS and retrieved."""

    @pytest.mark.asyncio
    async def test_trader_card_pins_to_ipfs(self) -> None:
        """Trader card pins to IPFS and returns a valid CID."""
        pinata = PinataClient()
        try:
            card = build_trader_card()
            cid = await pinata.pin_json(card.model_dump(mode="json"))
            assert cid.startswith("Qm") or cid.startswith("bafy")
        finally:
            await pinata.close()

    @pytest.mark.asyncio
    async def test_pinned_card_is_retrievable(self) -> None:
        """Pinned agent card is retrievable via IPFS gateway with required fields."""
        pinata = PinataClient()
        try:
            card = build_trader_card()
            cid = await pinata.pin_json(card.model_dump(mode="json"))
            fetched = await pinata.fetch_json(cid)
            assert "name" in fetched
            assert "description" in fetched
            assert "services" in fetched
            assert "x402Support" in fetched
            assert fetched["name"] == card.name
        finally:
            await pinata.close()


# ---------------------------------------------------------------------------
# VAL-CHAIN-001: Trader registers on IdentityRegistry
# ---------------------------------------------------------------------------


@pytest.mark.integration
@requires_integration
class TestTraderRegistration:
    """VAL-CHAIN-001: Trader registers on IdentityRegistry.

    Transaction succeeds, mints ERC-721 token (agentId),
    ownerOf(agentId) returns the trader wallet address.
    """

    @pytest.mark.asyncio
    async def test_trader_register_tx_succeeds(self) -> None:
        """Trader calls register(string) → tx succeeds, agentId returned."""
        chain = CircleChain()
        pinata = PinataClient()

        try:
            result = await register_agent(
                chain=chain,
                pinata=pinata,
                wallet_id=_TRADER_WALLET_ID,
                wallet_address=_TRADER_WALLET_ADDR,
                agent_card=build_trader_card(),
                role="trader",
            )

            # Verify result structure
            assert "agent_id" in result
            assert isinstance(result["agent_id"], int)
            assert result["agent_id"] > 0
            assert "ipfs_cid" in result
            assert "on_chain_tx_hash" in result
            assert result["role"] == "trader"
        finally:
            await pinata.close()

    @pytest.mark.asyncio
    async def test_trader_owner_of_matches_wallet(self) -> None:
        """ownerOf(traderAgentId) returns the trader wallet address."""
        chain = CircleChain()
        pinata = PinataClient()

        try:
            result = await register_agent(
                chain=chain,
                pinata=pinata,
                wallet_id=_TRADER_WALLET_ID,
                wallet_address=_TRADER_WALLET_ADDR,
                agent_card=build_trader_card(),
                role="trader",
            )

            agent_id = result["agent_id"]
            on_chain_owner = _cast_call(
                IDENTITY_REGISTRY,
                "ownerOf(uint256)(address)",
                str(agent_id),
            )
            assert on_chain_owner.lower() == _TRADER_WALLET_ADDR.lower()
        finally:
            await pinata.close()

    @pytest.mark.asyncio
    async def test_trader_register_trader_convenience(self) -> None:
        """register_trader() convenience function works end-to-end."""
        result = await register_trader()

        assert result["agent_id"] > 0
        assert result["role"] == "trader"
        assert result["wallet_address"].lower() == _TRADER_WALLET_ADDR.lower()

        # Verify env var was set
        assert os.environ.get("TRADER_AGENT_ID") == str(result["agent_id"])


# ---------------------------------------------------------------------------
# VAL-CHAIN-002: Agent card URI resolves to valid JSON
# ---------------------------------------------------------------------------


@pytest.mark.integration
@requires_integration
class TestTokenURIResolves:
    """VAL-CHAIN-002: tokenURI(agentId) returns IPFS URI that resolves to valid JSON.

    The resolved JSON must contain at minimum: name, description, services, x402Support.
    """

    @pytest.mark.asyncio
    async def test_token_uri_returns_ipfs_uri(self) -> None:
        """tokenURI(agentId) returns an IPFS URI after registration."""
        chain = CircleChain()
        pinata = PinataClient()

        try:
            result = await register_agent(
                chain=chain,
                pinata=pinata,
                wallet_id=_TRADER_WALLET_ID,
                wallet_address=_TRADER_WALLET_ADDR,
                agent_card=build_trader_card(),
                role="trader",
            )

            on_chain_uri = await verify_token_uri(result["agent_id"], result["ipfs_cid"])
            assert on_chain_uri.startswith("ipfs://")
        finally:
            await pinata.close()

    @pytest.mark.asyncio
    async def test_ipfs_gateway_resolves_card_json(self) -> None:
        """Fetching CID via gateway returns valid JSON with required fields."""
        chain = CircleChain()
        pinata = PinataClient()

        try:
            result = await register_agent(
                chain=chain,
                pinata=pinata,
                wallet_id=_TRADER_WALLET_ID,
                wallet_address=_TRADER_WALLET_ADDR,
                agent_card=build_trader_card(),
                role="trader",
            )

            card_data = await verify_agent_card_content(result["ipfs_cid"])

            # VAL-CHAIN-002: must contain name, description, services, x402Support
            assert "name" in card_data
            assert "description" in card_data
            assert "services" in card_data
            assert "x402Support" in card_data
            assert isinstance(card_data["name"], str)
            assert len(card_data["name"]) > 0
        finally:
            await pinata.close()

    @pytest.mark.asyncio
    async def test_token_uri_cid_matches_pinned_cid(self) -> None:
        """The CID in tokenURI matches the CID from the Pinata pin."""
        chain = CircleChain()
        pinata = PinataClient()

        try:
            result = await register_agent(
                chain=chain,
                pinata=pinata,
                wallet_id=_TRADER_WALLET_ID,
                wallet_address=_TRADER_WALLET_ADDR,
                agent_card=build_trader_card(),
                role="trader",
            )

            on_chain_uri = _cast_call(
                IDENTITY_REGISTRY,
                "tokenURI(uint256)(string)",
                str(result["agent_id"]),
            ).strip('"')

            assert on_chain_uri == f"ipfs://{result['ipfs_cid']}"
        finally:
            await pinata.close()


# ---------------------------------------------------------------------------
# VAL-CHAIN-003: Sentinel registers on IdentityRegistry
# ---------------------------------------------------------------------------


@pytest.mark.integration
@requires_integration
@requires_sentinel_env
class TestSentinelRegistration:
    """VAL-CHAIN-003: Sentinel registers on IdentityRegistry.

    Same flow as trader but uses CIRCLE_WALLET_SENTINEL_*.
    Sentinel gets a distinct agentId ≠ trader agentId.
    ownerOf(sentinelAgentId) matches sentinel wallet.
    """

    @pytest.mark.asyncio
    async def test_sentinel_register_tx_succeeds(self) -> None:
        """Sentinel calls register(string) → tx succeeds, distinct agentId."""
        chain = CircleChain()
        pinata = PinataClient()

        try:
            result = await register_agent(
                chain=chain,
                pinata=pinata,
                wallet_id=_SENTINEL_WALLET_ID,
                wallet_address=_SENTINEL_WALLET_ADDR,
                agent_card=build_sentinel_card(),
                role="sentinel",
            )

            assert result["agent_id"] > 0
            assert result["role"] == "sentinel"
        finally:
            await pinata.close()

    @pytest.mark.asyncio
    async def test_sentinel_owner_of_matches_wallet(self) -> None:
        """ownerOf(sentinelAgentId) returns the sentinel wallet address."""
        chain = CircleChain()
        pinata = PinataClient()

        try:
            result = await register_agent(
                chain=chain,
                pinata=pinata,
                wallet_id=_SENTINEL_WALLET_ID,
                wallet_address=_SENTINEL_WALLET_ADDR,
                agent_card=build_sentinel_card(),
                role="sentinel",
            )

            on_chain_owner = _cast_call(
                IDENTITY_REGISTRY,
                "ownerOf(uint256)(address)",
                str(result["agent_id"]),
            )
            assert on_chain_owner.lower() == _SENTINEL_WALLET_ADDR.lower()
        finally:
            await pinata.close()

    @pytest.mark.asyncio
    async def test_sentinel_agent_id_distinct_from_trader(self) -> None:
        """Sentinel agentId is distinct from trader agentId."""
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

            assert trader_result["agent_id"] != sentinel_result["agent_id"]
        finally:
            await pinata.close()

    @pytest.mark.asyncio
    async def test_sentinel_register_convenience(self) -> None:
        """register_sentinel() convenience function works end-to-end."""
        result = await register_sentinel()

        assert result["agent_id"] > 0
        assert result["role"] == "sentinel"
        assert result["wallet_address"].lower() == _SENTINEL_WALLET_ADDR.lower()

        assert os.environ.get("SENTINEL_AGENT_ID") == str(result["agent_id"])

    @pytest.mark.asyncio
    async def test_sentinel_card_x402_reflected_on_chain(self) -> None:
        """Sentinel's x402 support is reflected in the IPFS agent card."""
        chain = CircleChain()
        pinata = PinataClient()

        try:
            result = await register_agent(
                chain=chain,
                pinata=pinata,
                wallet_id=_SENTINEL_WALLET_ID,
                wallet_address=_SENTINEL_WALLET_ADDR,
                agent_card=build_sentinel_card(),
                role="sentinel",
            )

            card_data = await verify_agent_card_content(result["ipfs_cid"])
            assert card_data["x402Support"]["enabled"] is True
            assert card_data["x402Support"]["price_usdc"] == 0.01
        finally:
            await pinata.close()


# ---------------------------------------------------------------------------
# DB persistence tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@requires_integration
class TestRegistrationDBPersistence:
    """Verify that the agents table is populated with on-chain registration data."""

    def setup_method(self) -> None:
        """Ensure DB is migrated before tests."""
        if _DSN:
            run_migration(_DSN)

    def test_persist_registration_inserts_agent_row(self) -> None:
        """persist_registration inserts a row with agentId, role, wallet_address, agent_card_cid."""
        if not _DSN:
            pytest.skip("DATABASE_URL not set")

        agent_id = 99999  # Use a high test ID that won't conflict
        persist_registration(
            agent_id=agent_id,
            role="trader",
            wallet_address="0xtest1234",
            agent_card_cid="QmTestCID",
            dsn=_DSN,
        )

        with psycopg.connect(_DSN) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT agent_id, role, wallet_address, agent_card_cid "
                "FROM agents WHERE agent_id = %s",
                (agent_id,),
            )
            row = cur.fetchone()
            assert row is not None
            assert row[0] == agent_id
            assert row[1] == "trader"
            assert row[2] == "0xtest1234"
            assert row[3] == "QmTestCID"

        # Clean up
        with psycopg.connect(_DSN) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM agents WHERE agent_id = %s", (agent_id,))
            conn.commit()

    def test_persist_registration_upserts_on_conflict(self) -> None:
        """persist_registration updates existing row on conflict."""
        if not _DSN:
            pytest.skip("DATABASE_URL not set")

        agent_id = 99998
        # Insert initial
        persist_registration(
            agent_id=agent_id,
            role="trader",
            wallet_address="0xinitial",
            agent_card_cid="QmInitialCID",
            dsn=_DSN,
        )

        # Upsert with new data
        persist_registration(
            agent_id=agent_id,
            role="trader",
            wallet_address="0xupdated",
            agent_card_cid="QmUpdatedCID",
            dsn=_DSN,
        )

        with psycopg.connect(_DSN) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT wallet_address, agent_card_cid FROM agents WHERE agent_id = %s",
                (agent_id,),
            )
            row = cur.fetchone()
            assert row is not None
            assert row[0] == "0xupdated"
            assert row[1] == "QmUpdatedCID"

        # Clean up
        with psycopg.connect(_DSN) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM agents WHERE agent_id = %s", (agent_id,))
            conn.commit()


# ---------------------------------------------------------------------------
# CircleChain extensions tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@requires_integration
class TestCircleChainExtensions:
    """Test CircleChain wait_for_transaction and receipt parsing."""

    def test_transfer_topic_constant(self) -> None:
        """TRANSFER_TOPIC matches keccak256 of Transfer event signature."""
        from trader.chain import TRANSFER_TOPIC

        assert TRANSFER_TOPIC.startswith("0xddf252ad")

    def test_identity_registry_constant(self) -> None:
        """IDENTITY_REGISTRY matches the deployed contract address."""
        from trader.chain import IDENTITY_REGISTRY

        assert IDENTITY_REGISTRY == "0x8004A818BFB912233c491871b3d84c89A494BD9e"

    def test_parse_agent_id_from_receipt_with_valid_log(self) -> None:
        """parse_agent_id_from_receipt extracts agentId from a Transfer event."""
        chain = CircleChain.__new__(CircleChain)

        zero_addr = "0x" + "0" * 40
        wallet = "0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B"
        padded_zero = "0x000000000000000000000000" + zero_addr[2:]
        padded_wallet = "0x000000000000000000000000" + wallet[2:].lower()
        # tokenId = 42
        padded_token_id = hex(42)

        receipt = {
            "logs": [
                {
                    "topics": [
                        "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
                        padded_zero,
                        padded_wallet,
                        padded_token_id,
                    ]
                }
            ]
        }

        agent_id = chain.parse_agent_id_from_receipt(receipt, wallet)
        assert agent_id == 42

    def test_parse_agent_id_raises_on_no_transfer(self) -> None:
        """parse_agent_id_from_receipt raises ValueError when no Transfer event found."""
        chain = CircleChain.__new__(CircleChain)

        receipt = {"logs": []}
        with pytest.raises(ValueError, match="No Transfer mint event"):
            chain.parse_agent_id_from_receipt(receipt, "0xdeadbeef")
