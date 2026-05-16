"""Configuration defaults for the Prism CLI."""

from __future__ import annotations

from pydantic import BaseModel, Field

DEFAULT_DASHBOARD_URL = "https://prism-dashboard-production-e6e3.up.railway.app"
DEFAULT_SENTINEL_MCP_URL = "https://prism-sentinel-production.up.railway.app/mcp/"
DEFAULT_IPFS_GATEWAY = "https://gateway.pinata.cloud/ipfs"
BASE_SEPOLIA_USDC = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
BASE_SEPOLIA_EXPLORER = "https://sepolia.basescan.org"
CIRCLE_FAUCET_URL = "https://faucet.circle.com"


class CliConfig(BaseModel):
    """Runtime configuration for read-only Prism CLI commands."""

    dashboard_url: str = Field(default=DEFAULT_DASHBOARD_URL)
    sentinel_url: str = Field(default=DEFAULT_SENTINEL_MCP_URL)
    ipfs_gateway: str = Field(default=DEFAULT_IPFS_GATEWAY)
    timeout_seconds: float = Field(default=30.0, gt=0)

    def normalized_dashboard_url(self) -> str:
        """Return the dashboard URL without a trailing slash."""
        return self.dashboard_url.rstrip("/")

    def normalized_ipfs_gateway(self) -> str:
        """Return the IPFS gateway URL without a trailing slash."""
        return self.ipfs_gateway.rstrip("/")
