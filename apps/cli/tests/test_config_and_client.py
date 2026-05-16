from __future__ import annotations

from prism_cli.client import extract_cid, extract_trace_id, is_ipfs_cid
from prism_cli.config import DEFAULT_SENTINEL_MCP_URL


def test_default_sentinel_url_keeps_mcp_trailing_slash() -> None:
    assert DEFAULT_SENTINEL_MCP_URL.endswith("/mcp/")


def test_ipfs_cid_helpers_accept_known_good_cid() -> None:
    cid = "QmNzqnPEEQUMn3GMbiEZANpKXZRPmTHxVwt5nNevR8iXt8"
    assert is_ipfs_cid(cid)
    assert extract_cid(cid) == cid
    assert extract_cid(f"ipfs://{cid}") == cid


def test_trace_id_extraction_accepts_dashboard_url() -> None:
    trace_id = "d6cdd60f-f5e0-43ab-ba2d-7dcab76a8e24"
    url = f"https://prism-dashboard-production-e6e3.up.railway.app/trace/{trace_id}"
    assert extract_trace_id(trace_id) == trace_id
    assert extract_trace_id(url) == trace_id
