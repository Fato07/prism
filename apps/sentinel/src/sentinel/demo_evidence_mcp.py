"""Demo MCP evidence server for Connector Passport smoke tests.

This server is intentionally conservative: it returns one evidence-shaped result
for Prism connector smoke queries so operators can prove transport/schema/mapper
wiring, and returns no evidence for ordinary validation queries unless an explicit
demo override is enabled.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from fastmcp import FastMCP

DEMO_EVIDENCE_SERVER_NAME = "prism-demo-evidence"
SMOKE_QUERY = "Prism connector smoke test: latest public evidence for a prediction market claim"


def build_demo_evidence_mcp_server() -> FastMCP:
    """Build the read-only demo MCP evidence server."""
    server = FastMCP(DEMO_EVIDENCE_SERVER_NAME)

    @server.tool
    def search(query: str, limit: int = 5) -> dict[str, list[dict[str, Any]]]:
        """Return a connector smoke proof, not production research evidence."""
        is_dashboard_smoke_query = query.strip() == SMOKE_QUERY
        if not is_dashboard_smoke_query and not _allow_resolution_demo():
            return {"results": []}

        now = datetime.now(UTC).isoformat()
        return {
            "results": [
                {
                    "title": "Prism demo evidence connector smoke proof",
                    "url": "https://prism-docs-production.up.railway.app",
                    "snippet": (
                        "Demo MCP evidence server is reachable and returned a "
                        f"generic_search-compatible result for {min(max(limit, 1), 20)} requested item(s). "
                        "Replace this connector with a production MCP research tool before relying on it "
                        "for capital-moving validation."
                    ),
                    "provider": "prism_demo_evidence_mcp.search",
                    "published_at": now,
                    "retrieved_at": now,
                    "confidence": 0.99,
                }
            ]
        }

    return server


def _allow_resolution_demo() -> bool:
    """Return whether demo server should answer non-smoke resolution queries."""
    return os.environ.get("PRISM_DEMO_EVIDENCE_ALLOW_RESOLUTION", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
