"""Entry point: run the Prism MCP server standalone over streamable HTTP.

In production deployment, the MCP server is mounted as an ASGI sub-app
inside the sentinel FastAPI service at ``/mcp`` so it shares the same port
and x402 PaymentMiddleware. This entry point is provided as a convenience
for local exploration and is *not* used in the Railway deployment.
"""

from __future__ import annotations

from prism_mcp.server import mcp


def main() -> None:
    """Run the Prism MCP server using FastMCP's built-in streamable HTTP transport."""
    mcp.run(transport="http", host="0.0.0.0", port=3204)


if __name__ == "__main__":
    main()
