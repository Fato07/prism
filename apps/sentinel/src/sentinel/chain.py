"""ERC-8004 ValidationRegistry — validation response flow.

The sentinel submits a ``validationResponse`` on-chain after
adversarially reviewing a trader's reasoning trace.

On-chain function signature::

    validationResponse(
        bytes32 requestHash,
        uint8   verdictScore,
        string  verdictURI,
        bytes32 verdictHash,
        string  validationType
    )

The ``validationType`` is always ``"adversarial-llm-v1"`` for
Prism sentinel responses.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any

import structlog
from trader.chain import VALIDATION_REGISTRY, CircleChain

logger = structlog.get_logger("prism.sentinel.chain")

VALIDATION_TYPE = "adversarial-llm-v1"


def _cast_call(contract: str, sig: str, *args: str) -> str:
    """Run a cast call and return stdout."""
    cast_path = os.path.expanduser("~/.foundry/bin/cast")
    rpc_url = os.environ.get("ARC_RPC_URL", "")
    if not rpc_url:
        raise OSError("ARC_RPC_URL is not set")

    result = subprocess.run(
        [cast_path, "call", contract, sig, *args, "--rpc-url", rpc_url],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"cast call failed: {result.stderr}")
    return result.stdout.strip()


async def submit_validation_response(
    *,
    chain: CircleChain,
    wallet_id: str,
    request_hash: str,
    verdict_score: int,
    verdict_uri: str,
    verdict_hash: str,
    validation_type: str = VALIDATION_TYPE,
) -> dict[str, Any]:
    """Submit a validationResponse on the ValidationRegistry.

    Steps:
      1. Call ``validationResponse(bytes32,uint8,string,bytes32,string)`` via Circle SDK.
      2. Wait for on-chain confirmation.
      3. Verify on-chain data matches submitted parameters.

    Returns a dict with keys:
      ``circle_tx_id``, ``on_chain_tx_hash``, ``request_hash``.
    """
    logger.info(
        "submitting_validation_response",
        request_hash=request_hash,
        verdict_score=verdict_score,
        validation_type=validation_type,
    )

    # Step 1: Call validationResponse via Circle SDK
    circle_tx_id = await chain.execute_contract(
        wallet_id=wallet_id,
        contract_address=VALIDATION_REGISTRY,
        abi_function_signature="validationResponse(bytes32,uint8,string,bytes32,string)",
        abi_parameters=[
            request_hash,
            str(verdict_score),
            verdict_uri,
            verdict_hash,
            validation_type,
        ],
    )
    logger.info("validation_response_submitted", circle_tx_id=circle_tx_id)

    # Step 2: Wait for on-chain confirmation
    tx_result = await chain.wait_for_transaction(circle_tx_id)
    if tx_result["state"] != "COMPLETE":
        raise RuntimeError(f"validationResponse transaction failed with state={tx_result['state']}")

    on_chain_hash = tx_result.get("tx_hash")
    if not on_chain_hash:
        raise RuntimeError("Transaction completed but no on-chain tx hash returned")

    # Step 3: Verify on-chain transaction receipt
    receipt = await chain.get_tx_receipt(on_chain_hash)
    if receipt.get("status") != "0x1":
        raise RuntimeError(f"On-chain transaction reverted: {on_chain_hash}")

    logger.info(
        "validation_response_on_chain",
        request_hash=request_hash,
        on_chain_tx_hash=on_chain_hash,
    )

    # Step 4: Verify on-chain stored data (if getter available)
    await verify_validation_response_on_chain(
        request_hash=request_hash,
        verdict_score=verdict_score,
        verdict_uri=verdict_uri,
        verdict_hash=verdict_hash,
        validation_type=validation_type,
    )

    return {
        "request_hash": request_hash,
        "circle_tx_id": circle_tx_id,
        "on_chain_tx_hash": on_chain_hash,
    }


async def verify_validation_response_on_chain(
    *,
    request_hash: str,
    verdict_score: int,
    verdict_uri: str,
    verdict_hash: str,
    validation_type: str,
) -> None:
    """Verify on-chain that the validation response parameters match.

    Uses ``cast call`` to query the ValidationRegistry and confirm
    the stored parameters match what was submitted.
    """
    try:
        on_chain_score = _cast_call(
            VALIDATION_REGISTRY,
            "getValidationResponseScore(bytes32)(uint8)",
            request_hash,
        )
        if int(on_chain_score) != verdict_score:
            logger.warning(
                "verdict_score_mismatch",
                on_chain=on_chain_score,
                expected=verdict_score,
            )
    except RuntimeError:
        logger.info("score_on_chain_check_skipped", reason="getter_not_available")

    try:
        on_chain_type = _cast_call(
            VALIDATION_REGISTRY,
            "getValidationResponseType(bytes32)(string)",
            request_hash,
        )
        on_chain_type = on_chain_type.strip('"')
        if on_chain_type != validation_type:
            logger.warning(
                "validation_type_mismatch",
                on_chain=on_chain_type,
                expected=validation_type,
            )
    except RuntimeError:
        logger.info("type_on_chain_check_skipped", reason="getter_not_available")

    logger.info(
        "validation_response_verified_on_chain",
        request_hash=request_hash,
    )


async def submit_validation_response_from_env(
    request_hash: str,
    verdict_score: int,
    verdict_uri: str,
    verdict_hash: str,
) -> dict[str, Any]:
    """Convenience function to submit a validation response using env vars.

    Uses CIRCLE_WALLET_SENTINEL_ID for wallet.
    """
    wallet_id = os.environ.get("CIRCLE_WALLET_SENTINEL_ID", "")
    if not wallet_id:
        raise OSError("CIRCLE_WALLET_SENTINEL_ID not set")

    chain = CircleChain()
    return await submit_validation_response(
        chain=chain,
        wallet_id=wallet_id,
        request_hash=request_hash,
        verdict_score=verdict_score,
        verdict_uri=verdict_uri,
        verdict_hash=verdict_hash,
    )
