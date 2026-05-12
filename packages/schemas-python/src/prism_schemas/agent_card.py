"""Agent Card — A2A-compatible identity descriptor for ERC-8004 agents.

Pinned to IPFS and referenced by ``register(string agentURI)`` on the
IdentityRegistry contract.  The on-chain ``tokenURI(agentId)`` call returns
the IPFS URI which resolves to this JSON.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentCardService(BaseModel):
    """A service endpoint offered by an agent."""

    name: str
    description: str
    endpoint: str | None = None


class X402Support(BaseModel):
    """x402 payment configuration for sentinel-as-a-service."""

    enabled: bool = True
    price_usdc: float = Field(default=0.01, description="USDC price per call")
    recipient: str | None = Field(
        default=None, description="Wallet address receiving payment"
    )


class AgentCard(BaseModel):
    """A2A-compatible agent card JSON for ERC-8004 IdentityRegistry.

    Required fields match the validation contract (VAL-CHAIN-002):
    ``name``, ``description``, ``services``, ``x402Support``, ``active``.
    """

    name: str
    description: str
    services: list[AgentCardService] = Field(min_length=1)
    x402Support: X402Support = Field(default_factory=X402Support)
    active: bool = True
    version: str = "1.0.0"
    agent_role: str = Field(description="trader, sentinel, or oracle")
