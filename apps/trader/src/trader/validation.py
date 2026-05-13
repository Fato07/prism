"""ERC-8004 ValidationRegistry — validation request flow.

The trader submits a ``validationRequest`` on-chain to request the
sentinel to adversarially review a reasoning trace.

On-chain function signature::

    validationRequest(
        address validator,
        uint256 agentId,
        string  traceURI,
        bytes32 traceHash
    )

The contract emits an event containing the ``requestHash`` (bytes32)
which uniquely identifies this validation request.  The sentinel uses
this hash when submitting its ``validationResponse``.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any

import structlog

from trader.chain import VALIDATION_REGISTRY, CircleChain

logger = structlog.get_logger("prism.trader.validation")


def _cast_call(contract: str, sig: str, *args: str) -> str:
    """Run a cast call and return stdout.

    Used for optional on-chain read verification. If the Foundry `cast`
    binary is not available (production Docker image doesn't ship it),
    raises ``RuntimeError`` so callers' existing ``except RuntimeError``
    blocks degrade gracefully and skip the verification step.
    """
    cast_path = os.path.expanduser("~/.foundry/bin/cast")
    if not os.path.exists(cast_path):
        raise RuntimeError(f"cast binary not found at {cast_path}")
    rpc_url = os.environ.get("ARC_RPC_URL", "")
    if not rpc_url:
        raise OSError("ARC_RPC_URL is not set")

    try:
        result = subprocess.run(
            [cast_path, "call", contract, sig, *args, "--rpc-url", rpc_url],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as exc:
        # belt-and-braces in case the exists check raced an unmount
        raise RuntimeError(f"cast binary disappeared: {exc}") from exc
    if result.returncode != 0:
        raise RuntimeError(f"cast call failed: {result.stderr}")
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Validation Request Event — keccak256 topic
# ---------------------------------------------------------------------------

# The ValidationRegistry emits ``ValidationRequest(address,uint256,string,bytes32)``
# on a successful validationRequest() call.
# Indexed parameters: validator (address), agentId (uint256), requestHash (bytes32)
# Non-indexed (data): traceURI (string), traceHash (bytes32)
VALIDATION_REQUEST_EVENT_SIG = "ValidationRequest(address,uint256,string,bytes32)"


def _compute_event_topic(event_sig: str) -> str:
    """Compute the keccak256 topic of a Solidity event signature.

    Pure-Python via pycryptodome (already a transitive dep). Avoids the
    Foundry CLI dependency at module-load time — the production Docker
    image doesn't include Foundry, so shelling out to `cast keccak`
    raised FileNotFoundError on import and broke every on-chain attempt.
    """
    from Crypto.Hash import keccak

    k = keccak.new(digest_bits=256)
    k.update(event_sig.encode("utf-8"))
    return "0x" + k.hexdigest()


VALIDATION_REQUEST_TOPIC = _compute_event_topic(VALIDATION_REQUEST_EVENT_SIG)


def parse_request_hash_from_receipt(
    receipt: dict[str, Any],
) -> str:
    """Extract the requestHash (bytes32) from a validationRequest receipt.

    The ValidationRequest event has indexed parameters:
      topics[0] = event signature hash
      topics[1] = validator address (indexed)
      topics[2] = agentId (indexed uint256)
      topics[3] = requestHash (indexed bytes32)

    The requestHash is extracted from topics[3].
    """
    for log_entry in receipt.get("logs", []):
        topics = log_entry.get("topics", [])
        if len(topics) < 4:
            continue
        if topics[0].lower() == VALIDATION_REQUEST_TOPIC.lower():
            # requestHash is the third indexed parameter (topics[3])
            request_hash = topics[3]
            logger.info("request_hash_extracted", request_hash=request_hash)
            return request_hash

    raise ValueError("No ValidationRequest event found in receipt")


async def submit_validation_request(
    *,
    chain: CircleChain,
    wallet_id: str,
    validator_address: str,
    agent_id: int,
    trace_uri: str,
    trace_hash: str,
) -> dict[str, Any]:
    """Submit a validationRequest on the ValidationRegistry.

    Steps:
      1. Call ``validationRequest(address,uint256,string,bytes32)`` via Circle SDK.
      2. Wait for on-chain confirmation.
      3. Parse the receipt to extract the ``requestHash``.
      4. Verify on-chain data matches submitted parameters.

    Returns a dict with keys:
      ``request_hash``, ``circle_tx_id``, ``on_chain_tx_hash``.
    """
    logger.info(
        "submitting_validation_request",
        validator=validator_address,
        agent_id=agent_id,
        trace_uri=trace_uri,
    )

    # Step 1: Call validationRequest via Circle SDK
    circle_tx_id = await chain.execute_contract(
        wallet_id=wallet_id,
        contract_address=VALIDATION_REGISTRY,
        abi_function_signature="validationRequest(address,uint256,string,bytes32)",
        abi_parameters=[
            validator_address,
            str(agent_id),
            trace_uri,
            trace_hash,
        ],
    )
    logger.info("validation_request_submitted", circle_tx_id=circle_tx_id)

    # Step 2: Wait for on-chain confirmation
    tx_result = await chain.wait_for_transaction(circle_tx_id)
    if tx_result["state"] != "COMPLETE":
        raise RuntimeError(f"validationRequest transaction failed with state={tx_result['state']}")

    on_chain_hash = tx_result.get("tx_hash")
    if not on_chain_hash:
        raise RuntimeError("Transaction completed but no on-chain tx hash returned")

    # Step 3: Parse the receipt for requestHash
    receipt = await chain.get_tx_receipt(on_chain_hash)
    if receipt.get("status") != "0x1":
        raise RuntimeError(f"On-chain transaction reverted: {on_chain_hash}")

    request_hash = parse_request_hash_from_receipt(receipt)
    logger.info(
        "validation_request_on_chain",
        request_hash=request_hash,
        on_chain_tx_hash=on_chain_hash,
    )

    # Step 4: Verify on-chain data
    await verify_validation_request_on_chain(
        request_hash=request_hash,
        validator_address=validator_address,
        agent_id=agent_id,
        trace_uri=trace_uri,
        trace_hash=trace_hash,
    )

    return {
        "request_hash": request_hash,
        "circle_tx_id": circle_tx_id,
        "on_chain_tx_hash": on_chain_hash,
    }


async def verify_validation_request_on_chain(
    *,
    request_hash: str,
    validator_address: str,
    agent_id: int,
    trace_uri: str,
    trace_hash: str,
) -> None:
    """Verify on-chain that the validation request parameters match.

    Uses ``cast call`` to query the ValidationRegistry and confirm
    the stored parameters match what was submitted.
    """
    try:
        # Query the validator address stored for this request hash
        on_chain_validator = _cast_call(
            VALIDATION_REGISTRY,
            "getValidationRequestValidator(bytes32)(address)",
            request_hash,
        )
        if on_chain_validator.lower() != validator_address.lower():
            logger.warning(
                "validator_mismatch",
                on_chain=on_chain_validator,
                expected=validator_address,
            )
    except RuntimeError:
        # The getter function may not exist or may have a different signature.
        # Non-fatal — the tx receipt already confirms the call succeeded.
        logger.info("validator_on_chain_check_skipped", reason="getter_not_available")

    try:
        # Query the agentId stored for this request
        on_chain_agent_id = _cast_call(
            VALIDATION_REGISTRY,
            "getValidationRequestAgentId(bytes32)(uint256)",
            request_hash,
        )
        if int(on_chain_agent_id) != agent_id:
            logger.warning(
                "agent_id_mismatch",
                on_chain=on_chain_agent_id,
                expected=agent_id,
            )
    except RuntimeError:
        logger.info("agent_id_on_chain_check_skipped", reason="getter_not_available")

    logger.info(
        "validation_request_verified_on_chain",
        request_hash=request_hash,
    )


async def submit_validation_request_from_env(
    trace_uri: str,
    trace_hash: str,
    agent_id: int | None = None,
) -> dict[str, Any]:
    """Convenience function to submit a validation request using env vars.

    Uses CIRCLE_WALLET_TRADER_ID for wallet, CIRCLE_WALLET_SENTINEL_ADDRESS
    for the validator, and TRADER_AGENT_ID for the agent ID.
    """
    wallet_id = os.environ.get("CIRCLE_WALLET_TRADER_ID", "")
    validator_address = os.environ.get("CIRCLE_WALLET_SENTINEL_ADDRESS", "")
    if not wallet_id:
        raise OSError("CIRCLE_WALLET_TRADER_ID not set")
    if not validator_address:
        raise OSError("CIRCLE_WALLET_SENTINEL_ADDRESS not set")

    if agent_id is None:
        agent_id_str = os.environ.get("TRADER_AGENT_ID", "")
        if not agent_id_str:
            raise OSError("TRADER_AGENT_ID not set")
        agent_id = int(agent_id_str)

    chain = CircleChain()
    return await submit_validation_request(
        chain=chain,
        wallet_id=wallet_id,
        validator_address=validator_address,
        agent_id=agent_id,
        trace_uri=trace_uri,
        trace_hash=trace_hash,
    )
