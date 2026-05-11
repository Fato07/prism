"""CircleChain — async wrapper around Circle Developer-Controlled Wallets SDK."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger("prism.trader.chain")

BLOCKCHAIN = "ARC-TESTNET"
ACCOUNT_TYPE = "SCA"


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
        from circle.web3.developer_controlled_wallets import (
            CreateContractExecutionTransactionForDeveloperRequest,
            TransactionsApi,
        )

        api = TransactionsApi(self.client)
        request_body = CreateContractExecutionTransactionForDeveloperRequest(
            wallet_id=wallet_id,
            blockchain=BLOCKCHAIN,
            contract_address=contract_address,
            abi_function_signature=abi_function_signature,
            abi_parameters=abi_parameters,
            fee_level=fee_level,
        )

        logger.info(
            "executing_contract",
            contract_address=contract_address,
            function=abi_function_signature,
            wallet_id=wallet_id,
        )

        response = await asyncio.to_thread(
            api.create_contract_execution_transaction_for_developer,
            idempotency_key_str="",  # SDK requires this positional arg
            create_contract_execution_transaction_for_developer_request=request_body,
        )

        tx_id = response.data.transaction.id
        logger.info("contract_execution_submitted", tx_id=tx_id)
        return tx_id

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
