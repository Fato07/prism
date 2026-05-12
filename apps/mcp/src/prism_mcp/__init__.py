"""Prism MCP server — sentinel-as-a-service over the Model Context Protocol."""

from prism_mcp.server import (
    MCP_SERVER_NAME,
    ValidateMcpResult,
    build_mcp_server,
    mcp,
)

__all__ = [
    "MCP_SERVER_NAME",
    "ValidateMcpResult",
    "build_mcp_server",
    "mcp",
]
