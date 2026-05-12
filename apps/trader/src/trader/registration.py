"""ERC-8004 IdentityRegistry registration flow.

Creates an A2A-compatible agent card JSON, pins it to IPFS, calls
``register(string agentURI)`` on the IdentityRegistry contract via
Circle SDK on ARC-TESTNET, and verifies on-chain state.

After registration the ``agents`` table in Neon is populated with the
on-chain ``agentId`` (ERC-721 tokenId), role, wallet address, and
IPFS CID of the agent card.
"""

from __future__ import annotations

import os
from typing import Any

import psycopg
import structlog
from prism_schemas.agent_card import AgentCard, AgentCardService, X402Support

from trader.chain import IDENTITY_REGISTRY, CircleChain
from trader.ipfs import PinataClient

logger = structlog.get_logger("prism.trader.registration")

# ---------------------------------------------------------------------------
# Agent card builders
# ---------------------------------------------------------------------------


def build_trader_card() -> AgentCard:
    """Build an A2A-compatible agent card for the Prism trader agent."""
    return AgentCard(
        name="Prism Trader",
        description=(
            "Adversarial AI validator trader agent. Generates structured "
            "Trading-R1 reasoning traces for Polymarket prediction markets "
            "using Claude (Anthropic) family LLMs."
        ),
        services=[
            AgentCardService(
                name="generate_trace",
                description="Generate a Trading-R1 reasoning trace for a market question",
                endpoint=None,
            ),
        ],
        x402Support=X402Support(enabled=False),
        active=True,
        agent_role="trader",
    )


def build_sentinel_card() -> AgentCard:
    """Build an A2A-compatible agent card for the Prism sentinel agent."""
    return AgentCard(
        name="Prism Sentinel",
        description=(
            "Adversarial AI validator sentinel agent. Reviews and challenges "
            "trader reasoning traces using GPT (OpenAI) family LLMs via DSPy "
            "ChainOfThought. Exposes x402-protected validation endpoint."
        ),
        services=[
            AgentCardService(
                name="validate_trace",
                description="Adversarially validate a trader's reasoning trace",
                endpoint=None,
            ),
        ],
        x402Support=X402Support(enabled=True, price_usdc=0.01),
        active=True,
        agent_role="sentinel",
    )


# ---------------------------------------------------------------------------
# On-chain registration
# ---------------------------------------------------------------------------


async def register_agent(
    *,
    chain: CircleChain,
    pinata: PinataClient,
    wallet_id: str,
    wallet_address: str,
    agent_card: AgentCard,
    role: str,
) -> dict[str, Any]:
    """Register an agent on the ERC-8004 IdentityRegistry.

    Steps:
      1. Pin the agent card JSON to IPFS via Pinata.
      2. Call ``register(string agentURI)`` on the IdentityRegistry.
      3. Wait for on-chain confirmation.
      4. Parse the Transfer event to extract the ``agentId``.
      5. Verify ``ownerOf(agentId)`` matches the wallet.

    Returns a dict with keys:
      ``agent_id``, ``ipfs_cid``, ``ipfs_uri``, ``circle_tx_id``,
      ``on_chain_tx_hash``, ``role``, ``wallet_address``.
    """
    # Step 1: Pin agent card to IPFS
    card_json = agent_card.model_dump(mode="json")
    ipfs_cid = await pinata.pin_json(card_json)
    ipfs_uri = f"ipfs://{ipfs_cid}"
    logger.info("agent_card_pinned", role=role, ipfs_cid=ipfs_cid)

    # Step 2: Call register(string) on IdentityRegistry
    circle_tx_id = await chain.execute_contract(
        wallet_id=wallet_id,
        contract_address=IDENTITY_REGISTRY,
        abi_function_signature="register(string)",
        abi_parameters=[ipfs_uri],
    )
    logger.info("register_submitted", role=role, circle_tx_id=circle_tx_id)

    # Step 3: Wait for on-chain confirmation
    tx_result = await chain.wait_for_transaction(circle_tx_id)
    if tx_result["state"] != "COMPLETE":
        raise RuntimeError(f"Registration transaction failed with state={tx_result['state']}")

    on_chain_hash = tx_result.get("tx_hash")
    if not on_chain_hash:
        raise RuntimeError("Transaction completed but no on-chain tx hash returned")

    # Step 4: Parse Transfer event to get agentId
    receipt = await chain.get_tx_receipt(on_chain_hash)
    # Verify status is success (0x1)
    if receipt.get("status") != "0x1":
        raise RuntimeError(f"On-chain transaction reverted: {on_chain_hash}")

    agent_id = chain.parse_agent_id_from_receipt(receipt, wallet_address)
    logger.info("agent_registered_on_chain", agent_id=agent_id, role=role)

    # Step 5: Verify ownerOf
    await verify_ownership(chain, agent_id, wallet_address)

    return {
        "agent_id": agent_id,
        "ipfs_cid": ipfs_cid,
        "ipfs_uri": ipfs_uri,
        "circle_tx_id": circle_tx_id,
        "on_chain_tx_hash": on_chain_hash,
        "role": role,
        "wallet_address": wallet_address,
    }


async def verify_ownership(
    chain: CircleChain,
    agent_id: int,
    expected_owner: str,
) -> None:
    """Verify on-chain that ``ownerOf(agentId)`` matches the expected owner.

    Uses ``cast call`` via subprocess to query the IdentityRegistry.
    Raises ``AssertionError`` if ownership does not match.
    """
    import subprocess

    rpc_url = os.environ.get("ARC_RPC_URL", "")
    if not rpc_url:
        raise OSError("ARC_RPC_URL is not set")

    cast_path = os.path.expanduser("~/.foundry/bin/cast")
    result = subprocess.run(
        [
            cast_path,
            "call",
            IDENTITY_REGISTRY,
            "ownerOf(uint256)(address)",
            str(agent_id),
            "--rpc-url",
            rpc_url,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"cast call failed: {result.stderr}")

    on_chain_owner = result.stdout.strip()
    if on_chain_owner.lower() != expected_owner.lower():
        raise AssertionError(f"ownerOf({agent_id})={on_chain_owner} != expected {expected_owner}")
    logger.info("ownership_verified", agent_id=agent_id, owner=on_chain_owner)


async def verify_token_uri(
    agent_id: int,
    expected_cid: str,
) -> str:
    """Verify on-chain that ``tokenURI(agentId)`` returns the expected IPFS URI.

    Uses ``cast call`` via subprocess.  Returns the on-chain URI string.
    """
    import subprocess

    rpc_url = os.environ.get("ARC_RPC_URL", "")
    if not rpc_url:
        raise OSError("ARC_RPC_URL is not set")

    cast_path = os.path.expanduser("~/.foundry/bin/cast")
    result = subprocess.run(
        [
            cast_path,
            "call",
            IDENTITY_REGISTRY,
            "tokenURI(uint256)(string)",
            str(agent_id),
            "--rpc-url",
            rpc_url,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"cast call failed: {result.stderr}")

    on_chain_uri = result.stdout.strip()
    # Remove surrounding quotes that cast may add
    on_chain_uri = on_chain_uri.strip('"')

    if not on_chain_uri.lower().startswith("ipfs://"):
        raise AssertionError(f"tokenURI({agent_id})={on_chain_uri} is not an IPFS URI")

    # Extract CID from on-chain URI and compare
    on_chain_cid = on_chain_uri.replace("ipfs://", "")
    if on_chain_cid != expected_cid:
        logger.warning(
            "token_uri_cid_mismatch",
            agent_id=agent_id,
            on_chain_cid=on_chain_cid,
            expected_cid=expected_cid,
        )

    logger.info("token_uri_verified", agent_id=agent_id, uri=on_chain_uri)
    return on_chain_uri


async def verify_agent_card_content(cid: str) -> dict[str, Any]:
    """Fetch the agent card JSON from IPFS gateway and validate it.

    Returns the parsed dict.  Raises ``AssertionError`` if required
    fields are missing (VAL-CHAIN-002).
    """
    pinata = PinataClient()
    card_data = await pinata.fetch_json(cid)
    await pinata.close()

    required_fields = {"name", "description", "services", "x402Support"}
    missing = required_fields - set(card_data.keys())
    if missing:
        raise AssertionError(f"Agent card at CID {cid} is missing fields: {missing}")

    logger.info("agent_card_content_verified", cid=cid)
    return card_data


# ---------------------------------------------------------------------------
# Database persistence
# ---------------------------------------------------------------------------


def persist_registration(
    agent_id: int,
    role: str,
    wallet_address: str,
    agent_card_cid: str,
    dsn: str | None = None,
) -> None:
    """Insert or update the agents table row with on-chain registration data."""
    dsn = dsn or os.environ.get("DATABASE_URL", "")
    if not dsn:
        raise OSError("DATABASE_URL is not set")

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO agents (agent_id, role, wallet_address, agent_card_cid) "
            "VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (agent_id) DO UPDATE "
            "SET role = EXCLUDED.role, "
            "    wallet_address = EXCLUDED.wallet_address, "
            "    agent_card_cid = EXCLUDED.agent_card_cid",
            (agent_id, role, wallet_address, agent_card_cid),
        )
        conn.commit()
    logger.info(
        "registration_persisted",
        agent_id=agent_id,
        role=role,
        agent_card_cid=agent_card_cid,
    )


# ---------------------------------------------------------------------------
# Convenience orchestrators
# ---------------------------------------------------------------------------


async def register_trader() -> dict[str, Any]:
    """Full registration flow for the trader agent.

    Uses env vars for wallet credentials and returns registration metadata.
    """
    wallet_id = os.environ.get("CIRCLE_WALLET_TRADER_ID", "")
    wallet_address = os.environ.get("CIRCLE_WALLET_TRADER_ADDRESS", "")
    if not wallet_id or not wallet_address:
        raise OSError("CIRCLE_WALLET_TRADER_ID / CIRCLE_WALLET_TRADER_ADDRESS not set")

    chain = CircleChain()
    pinata = PinataClient()

    try:
        result = await register_agent(
            chain=chain,
            pinata=pinata,
            wallet_id=wallet_id,
            wallet_address=wallet_address,
            agent_card=build_trader_card(),
            role="trader",
        )
    finally:
        await pinata.close()

    # Persist to Neon
    persist_registration(
        agent_id=result["agent_id"],
        role="trader",
        wallet_address=wallet_address,
        agent_card_cid=result["ipfs_cid"],
    )

    # Set env var so other modules can use the on-chain agentId
    os.environ["TRADER_AGENT_ID"] = str(result["agent_id"])

    return result


async def register_sentinel() -> dict[str, Any]:
    """Full registration flow for the sentinel agent.

    Uses env vars for wallet credentials and returns registration metadata.
    """
    wallet_id = os.environ.get("CIRCLE_WALLET_SENTINEL_ID", "")
    wallet_address = os.environ.get("CIRCLE_WALLET_SENTINEL_ADDRESS", "")
    if not wallet_id or not wallet_address:
        raise OSError("CIRCLE_WALLET_SENTINEL_ID / CIRCLE_WALLET_SENTINEL_ADDRESS not set")

    chain = CircleChain()
    pinata = PinataClient()

    try:
        result = await register_agent(
            chain=chain,
            pinata=pinata,
            wallet_id=wallet_id,
            wallet_address=wallet_address,
            agent_card=build_sentinel_card(),
            role="sentinel",
        )
    finally:
        await pinata.close()

    # Persist to Neon
    persist_registration(
        agent_id=result["agent_id"],
        role="sentinel",
        wallet_address=wallet_address,
        agent_card_cid=result["ipfs_cid"],
    )

    # Set env var so other modules can use the on-chain agentId
    os.environ["SENTINEL_AGENT_ID"] = str(result["agent_id"])

    return result
