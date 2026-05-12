"""FastMCP server exposing the sentinel adversarial validator as an MCP tool.

The MCP server is designed to be mounted as an ASGI sub-app on the sentinel
FastAPI service at the ``/mcp`` path, behind the same x402 PaymentMiddleware
that protects ``POST /validate``. External agents discover the ``validate``
tool via ``tools/list`` and invoke it through ``tools/call``.

The tool runs the same pipeline as ``POST /validate``:

  1. Fetch trace JSON from IPFS via Pinata gateway.
  2. Generate the adversarial verdict via DSPy + GPT.
  3. Pin verdict JSON to IPFS via Pinata.
  4. Persist verdict to the Neon ``validations`` table.
  5. If ``PRISM_ONCHAIN`` is enabled and ``on_chain_request_hash`` is
     provided, submit ``validationResponse`` on Arc via the Circle SDK.

The tool's input schema mirrors ``ValidateRequest`` from the sentinel and
the output mirrors ``ValidateResponse`` (minus ``payment_tx_hash`` which is
controlled at the HTTP middleware layer).
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import TYPE_CHECKING

import structlog
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from prism_schemas.verdict import SentinelVerdict

logger = structlog.get_logger("prism.mcp")

MCP_SERVER_NAME = "prism-sentinel"


class ValidateMcpResult(BaseModel):
    """Output schema for the MCP ``validate`` tool.

    Mirrors the sentinel ``ValidateResponse`` so external agents see the
    same surface whether they call the HTTP endpoint or the MCP tool.
    """

    request_hash: str
    trace_id: str
    sentinel_agent_id: int
    verdict_score: int = Field(ge=0, le=100)
    verdict_label: str
    evidence_challenges: list[str]
    thesis_challenges: list[str]
    calibration_critique: str
    ipfs_cid: str
    content_hash_hex: str
    tx_hash: str | None = None


def _is_onchain_enabled() -> bool:
    """Whether on-chain validationResponse submission is enabled."""
    return os.environ.get("PRISM_ONCHAIN", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _sentinel_agent_id() -> int:
    return int(os.environ.get("SENTINEL_AGENT_ID", "2"))


def _strip_ipfs_scheme(trace_uri: str) -> str:
    """Return the bare CID from an ``ipfs://CID`` URI (or the input as-is)."""
    return trace_uri[7:] if trace_uri.startswith("ipfs://") else trace_uri


def _compute_request_hash(trace_uri: str, trace_hash: str) -> str:
    """Deterministic request hash for the MCP tool — matches HTTP /validate."""
    return hashlib.sha256(f"{trace_uri}:{trace_hash}".encode()).hexdigest()


async def _run_validation(
    trace_uri: str,
    trace_hash: str,
    on_chain_request_hash: str | None,
) -> ValidateMcpResult:
    """Run the sentinel pipeline and return the structured verdict.

    Raises ``ToolError`` on recoverable failures so the MCP client receives
    a structured error rather than an unhandled exception.
    """
    from sentinel.ipfs import PinataClient
    from sentinel.persistence import (
        persist_verdict,
        update_validation_tx_hash,
        update_verdict_response_uri,
    )

    request_hash = _compute_request_hash(trace_uri, trace_hash)
    trace_cid = _strip_ipfs_scheme(trace_uri)

    logger.info(
        "mcp_validate_invoked",
        trace_uri=trace_uri,
        request_hash=request_hash,
        onchain=on_chain_request_hash is not None and _is_onchain_enabled(),
    )

    try:
        pinata = PinataClient()
        trace_data = await pinata.fetch_json(trace_cid)
        await pinata.close()
    except Exception as exc:
        logger.error("mcp_trace_fetch_failed", trace_uri=trace_uri, error=str(exc))
        raise ToolError(f"trace_fetch_failed: cannot resolve {trace_uri} ({exc})") from exc

    trace_id = str(trace_data.get("trace_id", "")) if isinstance(trace_data, dict) else ""
    trace_json_str = json.dumps(trace_data)

    from sentinel.adversarial import generate_verdict

    sentinel_agent_id = _sentinel_agent_id()
    try:
        verdict: SentinelVerdict = await generate_verdict(
            trace_json=trace_json_str,
            request_hash=request_hash,
            trace_id=trace_id,
            sentinel_agent_id=sentinel_agent_id,
        )
    except Exception as exc:
        logger.error("mcp_verdict_generation_failed", error=str(exc))
        raise ToolError(f"verdict_generation_failed: {exc}") from exc

    try:
        pinata = PinataClient()
        ipfs_cid = await pinata.pin_json(verdict.model_dump(mode="json"))
        await pinata.close()
    except Exception as exc:
        logger.error("mcp_ipfs_pin_failed", error=str(exc))
        raise ToolError(f"ipfs_pin_failed: {exc}") from exc

    try:
        persist_verdict(verdict)
        update_verdict_response_uri(request_hash, f"ipfs://{ipfs_cid}")
    except Exception as exc:
        logger.error("mcp_db_persist_failed", error=str(exc))
        raise ToolError(f"db_persist_failed: {exc}") from exc

    content_hash_hex = verdict.content_hash().hex()

    tx_hash: str | None = None
    if _is_onchain_enabled() and on_chain_request_hash:
        try:
            from sentinel.chain import submit_validation_response_from_env

            result = await submit_validation_response_from_env(
                request_hash=on_chain_request_hash,
                verdict_score=verdict.verdict_score,
                verdict_uri=f"ipfs://{ipfs_cid}",
                verdict_hash=f"0x{content_hash_hex}",
            )
            tx_hash = result.get("on_chain_tx_hash")
            if tx_hash:
                update_validation_tx_hash(request_hash, tx_hash)
            logger.info(
                "mcp_onchain_response_submitted",
                trace_id=verdict.trace_id,
                tx_hash=tx_hash,
            )
        except Exception as exc:
            logger.error(
                "mcp_onchain_response_failed",
                trace_id=verdict.trace_id,
                error=str(exc),
            )

    logger.info(
        "mcp_validate_complete",
        trace_id=verdict.trace_id,
        verdict_score=verdict.verdict_score,
        verdict_label=verdict.verdict_label,
        ipfs_cid=ipfs_cid,
        tx_hash=tx_hash,
    )

    return ValidateMcpResult(
        request_hash=request_hash,
        trace_id=verdict.trace_id,
        sentinel_agent_id=verdict.sentinel_agent_id,
        verdict_score=verdict.verdict_score,
        verdict_label=verdict.verdict_label,
        evidence_challenges=verdict.evidence_challenges,
        thesis_challenges=verdict.thesis_challenges,
        calibration_critique=verdict.calibration_critique,
        ipfs_cid=ipfs_cid,
        content_hash_hex=content_hash_hex,
        tx_hash=tx_hash,
    )


def build_mcp_server() -> FastMCP:
    """Construct and return the Prism FastMCP server with the ``validate`` tool."""
    server: FastMCP = FastMCP(
        name=MCP_SERVER_NAME,
        instructions=(
            "Prism sentinel-as-a-service. Use the validate tool to obtain an "
            "adversarial verdict on a Trading-R1 reasoning trace pinned to IPFS. "
            "Each invocation requires a x402 USDC nanopayment on Base."
        ),
    )

    @server.tool(
        name="validate",
        description=(
            "Adversarially validate a Trading-R1 reasoning trace pinned to IPFS. "
            "Returns a structured SentinelVerdict (score 0-100, label, evidence "
            "challenges, thesis challenges, calibration critique) and the IPFS CID "
            "of the pinned verdict JSON. If on_chain_request_hash is provided and "
            "PRISM_ONCHAIN is enabled, the verdict is also anchored on Arc via "
            "ERC-8004 ValidationRegistry.validationResponse and the on-chain "
            "tx_hash is returned."
        ),
    )
    async def validate(
        trace_uri: str,
        trace_hash: str,
        on_chain_request_hash: str | None = None,
    ) -> ValidateMcpResult:
        if not trace_uri or not trace_uri.strip():
            raise ToolError("invalid_trace_uri: trace_uri must be a non-empty string")
        if not trace_hash or not trace_hash.strip():
            raise ToolError("invalid_trace_hash: trace_hash must be a non-empty string")

        return await _run_validation(
            trace_uri=trace_uri.strip(),
            trace_hash=trace_hash.strip(),
            on_chain_request_hash=on_chain_request_hash,
        )

    return server


mcp: FastMCP = build_mcp_server()
