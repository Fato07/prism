# Puzzle A2 — Circle Developer-Controlled Wallets SDK in async Python on Arc Testnet

> **Readable version for review.** The JSON payload to paste into
> `arc-canteen submit-puzzle` lives in `A2-circle-sdk-async.json`.

---

## prompt

I'm building a FastAPI service in Python 3.12 that needs to call ERC-8004
`ValidationRegistry.validationRequest(uint256,uint256,bytes32,string)` on Arc
Testnet from inside an async request handler. The wallet is a Circle
Developer-Controlled wallet (smart-account, gas sponsored by Circle Gas
Station). I want to use Circle's official Python SDK — not viem, not raw
JSON-RPC.

Write an async method `execute_contract(...) -> str` on a `CircleChain` class
that:

1. Submits the contract call via Circle's Developer-Controlled Wallets Python
   SDK, targeting Arc Testnet.
2. Returns the **on-chain transaction hash** (the 32-byte hash that appears
   on `testnet.arcscan.app`), not the Circle-internal transaction UUID.
3. Is safe to `await` from a FastAPI request handler — must not block the
   asyncio event loop while the SDK is doing network I/O.
4. Accepts a list of ABI parameter values as plain Python strings (the caller
   shouldn't have to know about SDK-internal parameter types).
5. Reads `CIRCLE_API_KEY`, `CIRCLE_ENTITY_SECRET`, and `CIRCLE_WALLET_SET_ID`
   from env. Raises `OSError` at construction if any are missing.

Show me the full working method, plus any helper polling needed to resolve
the on-chain tx hash, plus the exact imports. Use the PyPI package
`circle-developer-controlled-wallets` (version 7.x).

---

## ground_truth

```python
import asyncio
import os
from dataclasses import dataclass, field
from typing import Any

BLOCKCHAIN = "ARC-TESTNET"  # literal string, not an enum; uppercase-hyphen


@dataclass
class CircleChain:
    api_key: str = field(default_factory=lambda: os.environ.get("CIRCLE_API_KEY", ""))
    entity_secret: str = field(
        default_factory=lambda: os.environ.get("CIRCLE_ENTITY_SECRET", "")
    )
    wallet_set_id: str = field(
        default_factory=lambda: os.environ.get("CIRCLE_WALLET_SET_ID", "")
    )
    _client: Any = field(default=None, repr=False, init=False)

    def __post_init__(self) -> None:
        if not self.api_key:
            raise OSError("CIRCLE_API_KEY is not set")
        if not self.entity_secret:
            raise OSError("CIRCLE_ENTITY_SECRET is not set")
        if not self.wallet_set_id:
            raise OSError("CIRCLE_WALLET_SET_ID is not set")

    @property
    def client(self) -> Any:
        if self._client is None:
            # NB: PyPI package is `circle-developer-controlled-wallets`
            # BUT the import path is `circle.web3`, not
            # `circle_developer_controlled_wallets`.
            from circle.web3 import utils

            self._client = utils.init_developer_controlled_wallets_client(
                api_key=self.api_key,
                entity_secret=self.entity_secret,
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
        """Submit the contract call and return the ON-CHAIN tx hash."""
        from circle.web3.developer_controlled_wallets import TransactionsApi
        from circle.web3.developer_controlled_wallets.models import (
            create_contract_execution_transaction_for_developer_request as req_mod,
        )
        # Each ABI parameter must be wrapped in AbiParametersInner — passing
        # raw strings/lists silently fails Pydantic validation in the SDK.
        from circle.web3.developer_controlled_wallets.models.abi_parameters_inner import (
            AbiParametersInner,
        )

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

        # The SDK is synchronous. Calling it directly from async code blocks
        # the asyncio event loop for the duration of the HTTP round-trip to
        # api.circle.com, which under FastAPI starves every other request.
        # asyncio.to_thread() runs the blocking call on a worker thread.
        response = await asyncio.to_thread(
            api.create_developer_transaction_contract_execution,
            request_body,
        )
        circle_tx_id = response.data.id  # Circle UUID, NOT the on-chain hash.

        # Poll until terminal state to pick up the on-chain tx hash, which is
        # populated by Circle only after settlement (not present in the
        # initial response).
        settled = await self._wait_for_transaction(circle_tx_id)
        on_chain_tx_hash = settled.get("tx_hash")
        if not on_chain_tx_hash:
            raise RuntimeError(
                f"Circle tx {circle_tx_id} settled in state "
                f"{settled.get('state')} with no tx_hash"
            )
        return on_chain_tx_hash

    async def _wait_for_transaction(
        self,
        tx_id: str,
        timeout_seconds: int = 120,
        poll_interval_seconds: float = 3.0,
    ) -> dict[str, Any]:
        from circle.web3.developer_controlled_wallets import TransactionsApi

        api = TransactionsApi(self.client)
        elapsed = 0.0
        while elapsed < timeout_seconds:
            response = await asyncio.to_thread(api.get_transaction, id=tx_id)
            tx = response.data.transaction
            # tx.state is a Python Enum — pull .value for the string.
            state = tx.state.value if hasattr(tx.state, "value") else str(tx.state)
            if state in ("COMPLETE", "FAILED", "REJECTED"):
                return {
                    "id": tx.id,
                    "state": state,
                    "tx_hash": getattr(tx, "tx_hash", None),
                }
            await asyncio.sleep(poll_interval_seconds)
            elapsed += poll_interval_seconds
        raise TimeoutError(f"Transaction {tx_id} did not settle within {timeout_seconds}s")
```

---

## model

Factory Droid mission ensemble — orchestrator: Droid Core (GLM-5.1); worker: Claude Opus 4.7; validator: GPT-5.5. All three roles, spanning three independent model families (Zhipu GLM, Anthropic, OpenAI), failed on this prompt. Circle skill `use-developer-controlled-wallets` and the ARC coding context were loaded.

---

## explanation

This looks like it should be a 20-line wrapper. In practice every layer of
our Factory Droid mission ensemble — the GLM-5.1 orchestrator (Droid Core),
the Claude Opus 4.7 worker, AND the GPT-5.5 validator — failed it in
multiple distinct ways, even with Circle's `use-developer-controlled-wallets`
skill enabled and the ARC coding context loaded. Three model families
(Zhipu GLM, Anthropic, OpenAI) failing on the same prompt rules out
single-model quirks. The Circle skill covers each API in isolation but does
not flag the async-Python composition gaps.

Specific knowledge gaps the agent has to bridge:

1. **PyPI package name vs import path.** The package on PyPI is
   `circle-developer-controlled-wallets`, but the import is
   `from circle.web3 import ...`, NOT
   `from circle_developer_controlled_wallets import ...`. Agents almost
   universally guess the latter (matches Python convention of
   `pip install foo-bar` → `import foo_bar`), get
   `ModuleNotFoundError`, and then thrash. The actual package installs into
   a `circle.web3` namespace shared with future Circle Python SDKs. This
   one mismatch alone wastes ~10 minutes per session.

2. **The SDK is synchronous — `await` doesn't work.** The SDK is
   generated by OpenAPI Generator and uses `urllib3` synchronously. Calling
   `await api.create_developer_transaction_contract_execution(req)` raises
   `TypeError: object Response can't be used in 'await' expression`.
   Agents then "fix" it by removing the `await` — which makes the call
   block the FastAPI event loop for 1–3s per call (the round-trip to
   `api.circle.com`), serialising every concurrent request through the
   single asyncio thread. The correct fix is
   `await asyncio.to_thread(api.create_developer_transaction_contract_execution, req)`,
   which the Circle skill does not mention.

3. **`AbiParametersInner` wrapper.** ABI parameters must be wrapped:
   `[AbiParametersInner(p) for p in abi_parameters]`. Passing plain
   `["1", "0xabc..."]` results in a Pydantic validation error inside the
   SDK that mentions `AbiParametersInner` only in the traceback. Agents
   typically write `abi_parameters=["1", "0xabc..."]` and burn time
   reading the SDK source to find the wrapper. The skill examples show
   simple cases that happen to coerce, hiding this gotcha.

4. **Method name `create_developer_transaction_contract_execution`.**
   Agents repeatedly guess `create_contract_execution`,
   `execute_contract_call`, `create_transaction`, or anything shorter.
   The actual method name has the verb `create`, then the qualifier
   `developer_transaction`, then the operation
   `contract_execution`. Pattern is consistent across the SDK
   (`create_developer_transaction_transfer`,
   `create_transaction_estimate_fee` for the non-developer variant) but
   has to be discovered, not guessed.

5. **Circle's `response.data.id` is NOT the on-chain tx hash.** It is a
   Circle-internal UUID like `0a1b2c3d-1234-...`. The on-chain tx hash
   (the `0x...` 32-byte hash you see on `testnet.arcscan.app`) is
   populated on the `Transaction` object only AFTER Circle settles it on
   chain, via `tx.tx_hash`. The initial response from
   `create_developer_transaction_contract_execution` has `tx_hash=None`.
   You have to poll `api.get_transaction(id=circle_tx_id)` until
   `tx.state.value in ("COMPLETE", "FAILED", "REJECTED")` and then read
   `tx.tx_hash`. Agents return the Circle UUID and label it `tx_hash`,
   then downstream code tries to look it up in the Arc explorer and
   404s. This bug is invisible in unit tests that don't actually settle.

6. **`tx.state` is a Python Enum, not a string.** Comparing
   `tx.state == "COMPLETE"` always returns `False`. The correct check is
   `tx.state.value == "COMPLETE"` (or pull the enum). Agents handle this
   inconsistently and end up with infinite poll loops.

7. **`blockchain="ARC-TESTNET"` is a literal string.** Uppercase,
   hyphen. Not an enum, not `"Arc Testnet"`, not `"arc_testnet"`, not
   `"arc-testnet"`. The SDK does not export a `Blockchain` enum the user
   can introspect; the valid values are documented in Circle's API
   reference only, and Arc Testnet was added recently enough that some
   models' training data doesn't have it at all (manifesting as
   confident hallucinations like `"ARCTESTNET"` or `"arc"`).

How I derived the ground truth: this code is from the Prism trader service
(`apps/trader/src/trader/chain.py`, used in production across
`registration.py`, `validation.py`, and the sentinel `chain.py` mirror).
Verified end-to-end with `arc-canteen rpc` against Arc Testnet:
register an agent, post `validationRequest`, post `validationResponse`,
parse on-chain `tx_hash` from the polled Circle Transaction, and confirm
the hash resolves on `testnet.arcscan.app`. The package version is pinned
to `circle-developer-controlled-wallets==7.0.3` in `pyproject.toml`. The
method name, parameter wrapper, blockchain literal, and async pattern
were all derived empirically from reading the generated SDK source
(`.venv/lib/python3.12/site-packages/circle/web3/`) — none of them are
prominent in the public Circle docs.
