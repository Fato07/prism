"""Validation coordination logic.

Orchestrates the full validation flow: trace fetch → adversarial review →
verdict output → IPFS pin → DB persist → on-chain submission (Phase 1).
"""

from __future__ import annotations

import structlog

from sentinel.adversarial import generate_verdict
from sentinel.ipfs import PinataClient
from sentinel.persistence import persist_verdict, update_verdict_response_uri

logger = structlog.get_logger("prism.sentinel.validation")


async def validate_trace_full(
    trace_uri: str,
    trace_hash: str,
) -> dict[str, str]:
    """Run the full validation pipeline on a trace.

    This is a convenience function that orchestrates the full flow.
    In production, the FastAPI endpoint handles this directly.

    Returns a dict with verdict metadata.
    """
    # Fetch trace from IPFS
    trace_cid = trace_uri.replace("ipfs://", "")
    pinata = PinataClient()
    trace_data = await pinata.fetch_json(trace_cid)

    import json

    trace_json_str = json.dumps(trace_data)
    trace_id = trace_data.get("trace_id", "")

    # Generate verdict
    import hashlib

    request_hash = hashlib.sha256(f"{trace_uri}:{trace_hash}".encode()).hexdigest()

    import os

    sentinel_agent_id = int(os.environ.get("SENTINEL_AGENT_ID", "2"))

    verdict = await generate_verdict(
        trace_json=trace_json_str,
        request_hash=request_hash,
        trace_id=trace_id,
        sentinel_agent_id=sentinel_agent_id,
    )

    # Pin verdict to IPFS
    ipfs_cid = await pinata.pin_json(verdict.model_dump(mode="json"))

    # Persist to DB
    persist_verdict(verdict)
    update_verdict_response_uri(request_hash, f"ipfs://{ipfs_cid}")

    await pinata.close()

    return {
        "request_hash": request_hash,
        "trace_id": verdict.trace_id,
        "verdict_score": str(verdict.verdict_score),
        "verdict_label": verdict.verdict_label,
        "ipfs_cid": ipfs_cid,
        "content_hash_hex": verdict.content_hash().hex(),
    }
