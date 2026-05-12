"""CircleChain — async wrapper around Circle Developer-Controlled Wallets SDK."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog

logger = structlog.get_logger("prism.trader.chain")

BLOCKCHAIN = "ARC-TESTNET"
ACCOUNT_TYPE = "SCA"

IDENTITY_REGISTRY = "0x8004A818BFB912233c491871b3d84c89A494BD9e"
VALIDATION_REGISTRY = "0x8004Cb1BF31DAf7788923b405b754f57acEB4272"
REPUTATION_REGISTRY = "0x8004B663056A597Dffe9eCcC1965A193B7388713"

# keccak256("Transfer(address,address,uint256)")
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


@dataclass
class CircleChain:
    """Async wrapper for Circle Developer-Controlled Wallets SDK.

    All SDK calls are synchronous — wrapped with asyncio.to_thread().
    """

    api_key: str = field(default_factory=lambda: os.environ.get("CIRCLE_API_KEY", ""))
    entity_secret: str = field(default_factory=lambda: os.environ.get("CIRCLE_ENTITY_SECRET", ""))
    wallet_set_id: str = field(default_factory=lambda: os.environ.get("CIRCLE_WALLET_SET_ID", ""))
    _client: Any = field(default=None, repr=False, init=False)

    def __post_init__(self) -> None:
        """Validate required config and initialise the SDK client."""
        if not self.api_key:
            raise OSError("CIRCLE_API_KEY is not set")
        if not self.entity_secret:
            raise OSError("CIRCLE_ENTITY_SECRET is not set")
        if not self.wallet_set_id:
            raise OSError("CIRCLE_WALLET_SET_ID is not set")

    @property
    def client(self) -> Any:
        """Lazily initialise the Circle SDK client."""
        if self._client is None:
            from circle.web3 import utils

            self._client = utils.init_developer_controlled_wallets_client(
                api_key=self.api_key,
                entity_secret=self.entity_secret,
            )
            logger.info(
                "circle_client_initialized",
                wallet_set_id=self.wallet_set_id,
            )
        return self._client

    async def execute_contract(
        self,
        *,
        wallet_id: str,
        contract_address: str,
        abi_function_signature: str,
        abi_parameters: list[str],
        fee_level: str = "MEDIUM",
    ) -> str:
        """Execute a contract call via Circle SDK on ARC-TESTNET.

        Returns the Circle transaction ID.
        """
        from circle.web3.developer_controlled_wallets import TransactionsApi
        from circle.web3.developer_controlled_wallets.models import (
            create_contract_execution_transaction_for_developer_request as req_mod,
        )
        from circle.web3.developer_controlled_wallets.models.abi_parameters_inner import (
            AbiParametersInner,
        )

        # Circle SDK requires each parameter to be wrapped in AbiParametersInner.
        wrapped_params = [AbiParametersInner(p) for p in abi_parameters]

        api = TransactionsApi(self.client)
        request_body = req_mod.CreateContractExecutionTransactionForDeveloperRequest(
            wallet_id=wallet_id,
            blockchain=BLOCKCHAIN,
            contract_address=contract_address,
            abi_function_signature=abi_function_signature,
            abi_parameters=wrapped_params,
            fee_level=fee_level,
        )

        logger.info(
            "executing_contract",
            contract_address=contract_address,
            function=abi_function_signature,
            wallet_id=wallet_id,
        )

        response = await asyncio.to_thread(
            api.create_developer_transaction_contract_execution,
            request_body,
        )

        tx_id = response.data.id
        logger.info("contract_execution_submitted", tx_id=tx_id)
        return tx_id

    async def wait_for_transaction(
        self,
        tx_id: str,
        timeout_seconds: int = 120,
        poll_interval_seconds: float = 3.0,
    ) -> dict[str, Any]:
        """Poll Circle API until transaction reaches a terminal state.

        Returns the transaction dict with ``state`` and ``tx_hash`` (on-chain hash).
        Raises ``TimeoutError`` if the transaction does not settle within
        *timeout_seconds*.
        """
        from circle.web3.developer_controlled_wallets import TransactionsApi

        api = TransactionsApi(self.client)
        elapsed = 0.0

        while elapsed < timeout_seconds:
            response = await asyncio.to_thread(api.get_transaction, id=tx_id)
            tx = response.data.transaction
            # TransactionState enum — extract the value string (e.g. "COMPLETE")
            state_value = tx.state.value if hasattr(tx.state, "value") else str(tx.state)
            logger.debug("polling_transaction", tx_id=tx_id, state=state_value)

            if state_value in ("COMPLETE", "FAILED", "REJECTED"):
                result: dict[str, Any] = {
                    "id": tx.id,
                    "state": state_value,
                    "tx_hash": getattr(tx, "tx_hash", None),
                    "blockchain": str(tx.blockchain.value)
                    if hasattr(tx.blockchain, "value")
                    else str(tx.blockchain),
                }
                logger.info(
                    "transaction_settled",
                    tx_id=tx_id,
                    state=state_value,
                    tx_hash=result["tx_hash"],
                )
                return result

            await asyncio.sleep(poll_interval_seconds)
            elapsed += poll_interval_seconds

        raise TimeoutError(f"Transaction {tx_id} did not settle within {timeout_seconds}s")

    async def get_tx_receipt(self, tx_hash: str) -> dict[str, Any]:
        """Fetch an on-chain transaction receipt via Arc RPC (eth_getTransactionReceipt).

        Returns the JSON-RPC result dict containing ``logs``, ``status``, etc.
        """
        rpc_url = os.environ.get("ARC_RPC_URL", "")
        if not rpc_url:
            raise OSError("ARC_RPC_URL is not set")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "method": "eth_getTransactionReceipt",
                    "params": [tx_hash],
                    "id": 1,
                },
            )
            response.raise_for_status()
            body = response.json()
            result = body.get("result")
            if result is None:
                raise ValueError(f"No receipt found for tx {tx_hash}")
            return result

    def parse_agent_id_from_receipt(
        self,
        receipt: dict[str, Any],
        wallet_address: str,
    ) -> int:
        """Extract the minted agentId (ERC-721 tokenId) from a registration receipt.

        Looks for a ``Transfer(address(0), wallet, tokenId)`` event where
        ``from`` is the zero address (minting) and ``to`` matches the
        *wallet_address*.
        """
        zero_address = "0x" + "0" * 40
        for log in receipt.get("logs", []):
            topics = log.get("topics", [])
            if len(topics) < 4:
                continue
            if topics[0].lower() != TRANSFER_TOPIC.lower():
                continue
            from_addr = "0x" + topics[1][-40:].lower()
            to_addr = "0x" + topics[2][-40:].lower()
            if from_addr == zero_address and to_addr == wallet_address.lower():
                agent_id = int(topics[3], 16)
                logger.info("agent_id_extracted", agent_id=agent_id, wallet=wallet_address)
                return agent_id

        raise ValueError(f"No Transfer mint event found for wallet {wallet_address} in receipt")

    async def get_wallet_balance(self, wallet_id: str) -> dict[str, Any]:
        """Get token balances for a wallet."""
        from circle.web3.developer_controlled_wallets import WalletsApi

        api = WalletsApi(self.client)
        response = await asyncio.to_thread(
            api.get_wallet,
            id=wallet_id,
        )
        balances = {}
        for balance in response.data.wallet.balances:
            balances[balance.token.symbol] = float(balance.amount)
        return balances
