"""HTTP and input-loading helpers for the Prism CLI."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import httpx
from pydantic import ValidationError

from prism_cli.config import CliConfig
from prism_cli.models import (
    PublicHistoryResponse,
    PublicStatsResponse,
    PublicTraceReport,
    TradingR1Trace,
)

CID_RE = re.compile(r"^(Qm[1-9A-HJ-NP-Za-km-z]{44}|baf[0-9a-zA-Z]{20,})$")
TRACE_URL_RE = re.compile(r"/trace/([0-9a-fA-F-]{36})(?:$|[/?#])")
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
)


class PrismCliError(RuntimeError):
    """User-facing CLI error."""


def is_ipfs_cid(value: str) -> bool:
    """Return whether a string looks like an IPFS CID."""
    return bool(CID_RE.match(value.strip()))


def extract_cid(value: str) -> str | None:
    """Extract a CID from CID or ipfs://CID input."""
    raw = value.strip()
    if raw.startswith("ipfs://"):
        raw = raw.removeprefix("ipfs://")
    return raw if is_ipfs_cid(raw) else None


def extract_trace_id(value: str) -> str | None:
    """Extract a trace UUID from a raw UUID or dashboard trace URL."""
    raw = value.strip()
    if UUID_RE.match(raw):
        return raw
    match = TRACE_URL_RE.search(raw)
    return match.group(1) if match else None


async def load_trace(source: str, config: CliConfig) -> TradingR1Trace:
    """Load a Trading-R1 trace from a local JSON file or IPFS CID/URI."""
    path = Path(source)
    if path.exists():
        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise PrismCliError(f"Trace file is not valid JSON: {path}") from exc
        return _parse_trace(payload)

    cid = extract_cid(source)
    if cid:
        url = f"{config.normalized_ipfs_gateway()}/{cid}"
        async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
            response = await client.get(url)
        if response.status_code != 200:
            raise PrismCliError(f"IPFS gateway returned {response.status_code} for CID {cid}")
        return _parse_trace(response.json())

    raise PrismCliError(
        "Unsupported trace source. Provide a local JSON file, ipfs://CID, or raw IPFS CID."
    )


async def fetch_public_stats(config: CliConfig) -> PublicStatsResponse:
    """Fetch public Prism stats from the dashboard API."""
    url = f"{config.normalized_dashboard_url()}/api/public/stats"
    async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
        response = await client.get(url)
    if response.status_code != 200:
        raise PrismCliError(f"Stats API returned {response.status_code}: {response.text[:160]}")
    return PublicStatsResponse.model_validate(response.json())


async def fetch_public_history(config: CliConfig, limit: int) -> PublicHistoryResponse:
    """Fetch recent public Prism validations from the dashboard API."""
    safe_limit = max(1, min(100, limit))
    url = f"{config.normalized_dashboard_url()}/api/public/history?limit={safe_limit}"
    async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
        response = await client.get(url)
    if response.status_code != 200:
        raise PrismCliError(f"History API returned {response.status_code}: {response.text[:160]}")
    return PublicHistoryResponse.model_validate(response.json())


async def fetch_public_report(config: CliConfig, trace_source: str) -> PublicTraceReport:
    """Fetch a public report for a trace UUID or dashboard /trace URL."""
    trace_id = extract_trace_id(trace_source)
    if not trace_id:
        raise PrismCliError("Report source must be a trace UUID or dashboard /trace/<id> URL.")
    url = f"{config.normalized_dashboard_url()}/api/public/traces/{quote(trace_id)}/report"
    async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
        response = await client.get(url)
    if response.status_code == 404:
        raise PrismCliError(f"Trace not found: {trace_id}")
    if response.status_code != 200:
        raise PrismCliError(f"Report API returned {response.status_code}: {response.text[:160]}")
    return PublicTraceReport.model_validate(response.json())


def dashboard_from_trace_url(value: str) -> str | None:
    """Return the origin from a dashboard trace URL if present."""
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc and TRACE_URL_RE.search(value):
        return f"{parsed.scheme}://{parsed.netloc}"
    return None


def _parse_trace(payload: Any) -> TradingR1Trace:
    """Validate raw JSON as a Trading-R1 trace."""
    try:
        return TradingR1Trace.model_validate(payload)
    except ValidationError as exc:
        message = exc.errors()[0]["msg"]
        raise PrismCliError(f"Input is not a valid Trading-R1 trace: {message}") from exc
