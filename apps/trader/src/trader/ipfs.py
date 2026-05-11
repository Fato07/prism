"""PinataClient — IPFS pinning via Pinata REST API (httpx)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog

logger = structlog.get_logger("prism.trader.ipfs")

PINATA_PIN_URL = "https://api.pinata.cloud/pinning/pinJSONToIPFS"
PINATA_GATEWAY = "https://gateway.pinata.cloud/ipfs"


@dataclass
class PinataClient:
    """IPFS pinning client using Pinata REST API with Bearer JWT auth."""

    jwt: str = field(default_factory=lambda: os.environ.get("PINATA_JWT", ""))
    _http: httpx.AsyncClient | None = field(default=None, repr=False, init=False)

    def __post_init__(self) -> None:
        """Validate JWT is present."""
        if not self.jwt:
            raise OSError("PINATA_JWT is not set")

    @property
    def http(self) -> httpx.AsyncClient:
        """Lazily initialise the httpx client."""
        if self._http is None:
            self._http = httpx.AsyncClient(
                headers={
                    "Authorization": f"Bearer {self.jwt}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._http

    async def pin_json(self, data: dict[str, Any]) -> str:
        """Pin a JSON payload to IPFS via Pinata. Returns the CID."""
        logger.info("pinning_json_to_ipfs")
        response = await self.http.post(PINATA_PIN_URL, json=data)
        response.raise_for_status()
        result = response.json()
        cid: str = result["IpfsHash"]
        logger.info("json_pinned", cid=cid)
        return cid

    async def fetch_json(self, cid: str) -> dict[str, Any]:
        """Fetch pinned JSON from IPFS via Pinata gateway."""
        url = f"{PINATA_GATEWAY}/{cid}"
        logger.info("fetching_from_ipfs", cid=cid)
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()

    async def close(self) -> None:
        """Close the underlying httpx client."""
        if self._http is not None:
            await self._http.aclose()
            self._http = None
