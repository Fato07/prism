"""Second-stage URL extraction for evidence verification.

Search tools can return plausible URLs and snippets. This module provides a
separate, MCP-first extraction layer that fetches/normalizes page content before
Sentinel allows that URL to resolve an issue-ledger challenge.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
from collections.abc import Callable
from datetime import UTC, datetime
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

import httpx
import structlog
from fastmcp import Client
from fastmcp.client.auth import BearerAuth
from pydantic import BaseModel, Field

logger = structlog.get_logger("prism.sentinel.evidence_extraction")

EvidenceExtractInputMapper = Callable[["EvidencePageExtractRequest"], dict[str, Any]]
EvidenceExtractResultMapper = Callable[
    [Any, "EvidencePageExtractRequest"],
    "EvidencePageExtractResult | None",
]


class EvidencePageExtractRequest(BaseModel):
    """Request to extract readable content from one evidence source URL."""

    url: str
    objective: str
    challenge_id: str | None = None
    max_chars: int = Field(default=12_000, ge=100, le=50_000)


class EvidencePageExtractResult(BaseModel):
    """Provider-neutral extracted page content used to verify a source URL."""

    url: str
    text: str
    provider: str
    title: str | None = None
    final_url: str | None = None
    tool_name: str | None = None
    published_at: str | None = None
    extracted_at: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    def sanitized_url(self) -> str:
        """Return the public receipt-safe URL for this extracted source."""
        return sanitize_source_url(self.final_url or self.url)

    def content_hash(self) -> str:
        """Return a deterministic hash of the extracted content."""
        return hashlib.sha256(self.text.encode()).hexdigest()

    def excerpt(self, *, max_chars: int = 600) -> str:
        """Return a compact quote/excerpt suitable for public receipts."""
        cleaned = redact_public_text(clean_extracted_text(self.text))
        if len(cleaned) <= max_chars:
            return cleaned
        return f"{cleaned[:max_chars].rstrip()}…"


class EvidenceExtractorProvider(Protocol):
    """Provider interface for URL-to-readable-content extraction."""

    async def extract(
        self,
        request: EvidencePageExtractRequest,
    ) -> EvidencePageExtractResult | None:
        """Return extracted content for the URL, or None on fail-closed failure."""


class NoopEvidenceExtractor:
    """Safe default extractor: performs no network calls."""

    async def extract(
        self,
        request: EvidencePageExtractRequest,
    ) -> EvidencePageExtractResult | None:
        """Return no extracted content."""
        logger.info(
            "evidence_extractor_noop",
            challenge_id=request.challenge_id,
            url=sanitize_source_url(request.url),
        )
        return None


class StaticEvidenceExtractor:
    """Deterministic extractor for tests and fixtures, keyed by sanitized URL."""

    def __init__(self, results_by_url: dict[str, EvidencePageExtractResult | str]) -> None:
        """Create a static extractor from URL-to-result mappings."""
        self._results_by_url: dict[str, EvidencePageExtractResult] = {}
        for url, result in results_by_url.items():
            sanitized = sanitize_source_url(url)
            if isinstance(result, EvidencePageExtractResult):
                self._results_by_url[sanitized] = result
            else:
                self._results_by_url[sanitized] = EvidencePageExtractResult(
                    url=sanitized,
                    text=result,
                    provider="static_extractor",
                    tool_name="static_extract",
                    extracted_at=datetime.now(UTC).isoformat(),
                    confidence=1.0,
                )

    async def extract(
        self,
        request: EvidencePageExtractRequest,
    ) -> EvidencePageExtractResult | None:
        """Return a static extraction for the request URL."""
        return self._results_by_url.get(sanitize_source_url(request.url))


class McpEvidenceExtractor:
    """URL extractor backed by an MCP tool such as Parallel web_fetch or Exa fetch."""

    def __init__(
        self,
        *,
        server_url: str | None = None,
        tool_name: str,
        result_mapper: str = "generic_extract",
        input_mapper: str = "url_objective",
        auth_token: str | None = None,
        timeout_seconds: float = 30.0,
        allowed_tools: list[str] | None = None,
        transport: Any | None = None,
    ) -> None:
        """Create an MCP-backed extractor."""
        self.transport = transport if transport is not None else server_url
        self.server_url = server_url
        self.tool_name = tool_name
        self.result_mapper = result_mapper.strip().lower()
        self.input_mapper = input_mapper.strip().lower()
        self.auth_token = auth_token
        self.timeout_seconds = timeout_seconds
        self.allowed_tools = allowed_tools or [tool_name]

    async def extract(
        self,
        request: EvidencePageExtractRequest,
    ) -> EvidencePageExtractResult | None:
        """Call the configured MCP extraction tool and normalize the response."""
        if self.tool_name not in self.allowed_tools:
            logger.warning("mcp_extractor_tool_not_allowed", tool_name=self.tool_name)
            return None
        if self.transport is None:
            logger.warning("mcp_extractor_missing_transport", tool_name=self.tool_name)
            return None

        auth = BearerAuth(self.auth_token) if self.auth_token else None
        try:
            async with Client(
                self.transport,
                auth=auth,
                timeout=self.timeout_seconds,
            ) as client:
                result = await client.call_tool(
                    self.tool_name,
                    _extract_tool_arguments(self.input_mapper, request),
                    raise_on_error=False,
                    timeout=self.timeout_seconds,
                )
        except Exception as exc:
            logger.warning(
                "mcp_extractor_call_failed",
                tool_name=self.tool_name,
                mapper=self.result_mapper,
                input_mapper=self.input_mapper,
                error=type(exc).__name__,
                url=sanitize_source_url(request.url),
            )
            return None

        if getattr(result, "is_error", False):
            logger.warning(
                "mcp_extractor_tool_returned_error",
                tool_name=self.tool_name,
                mapper=self.result_mapper,
            )
            return None

        body = _mcp_result_body(result)
        extraction = map_extraction_result(self.result_mapper, body, request)
        if extraction is None:
            return None
        if extraction.tool_name:
            return extraction
        return extraction.model_copy(update={"tool_name": self.tool_name})


class FirecrawlEvidenceExtractor:
    """Direct Firecrawl scrape adapter for URL-to-markdown extraction."""

    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str = "https://api.firecrawl.dev/v2/scrape",
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Create a Firecrawl scrape extractor."""
        self.api_key = api_key
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def extract(
        self,
        request: EvidencePageExtractRequest,
    ) -> EvidencePageExtractResult | None:
        """Scrape one URL and return clean markdown content."""
        payload = {
            "url": request.url,
            "formats": ["markdown"],
            "onlyMainContent": True,
            "timeout": int(self.timeout_seconds * 1000),
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.post(self.endpoint, json=payload, headers=headers)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning(
                "firecrawl_extractor_failed",
                url=sanitize_source_url(request.url),
                error=type(exc).__name__,
                status_code=getattr(getattr(exc, "response", None), "status_code", None),
            )
            return None

        try:
            body = response.json()
        except json.JSONDecodeError:
            return None
        return _parse_firecrawl_extract(body, request)


def evidence_extractor_from_env() -> EvidenceExtractorProvider:
    """Return the configured second-stage evidence extractor.

    Default is `noop`, so no paid/network extraction runs unless explicitly
    configured by env or tests.
    """
    provider = os.environ.get("PRISM_EVIDENCE_EXTRACTOR", "noop").strip().lower()
    if provider in {"", "none", "noop"}:
        return NoopEvidenceExtractor()
    if provider in {"mcp", "mcp_http"}:
        server_url = _env_optional("PRISM_EVIDENCE_EXTRACTOR_MCP_URL")
        tool_name = _env_optional("PRISM_EVIDENCE_EXTRACTOR_MCP_TOOL")
        if server_url is None or tool_name is None:
            logger.warning(
                "mcp_extractor_missing_required_config",
                has_server_url=server_url is not None,
                has_tool_name=tool_name is not None,
            )
            return NoopEvidenceExtractor()
        return McpEvidenceExtractor(
            server_url=server_url,
            tool_name=tool_name,
            result_mapper=os.environ.get(
                "PRISM_EVIDENCE_EXTRACTOR_RESULT_MAPPER",
                "generic_extract",
            ),
            input_mapper=os.environ.get(
                "PRISM_EVIDENCE_EXTRACTOR_INPUT_MAPPER",
                "url_objective",
            ),
            auth_token=os.environ.get("PRISM_EVIDENCE_EXTRACTOR_AUTH_TOKEN"),
            timeout_seconds=_env_float("PRISM_EVIDENCE_EXTRACTOR_TIMEOUT_SECONDS", 30.0),
        )
    if provider == "firecrawl_scrape":
        api_key = _env_optional("FIRECRAWL_API_KEY")
        if api_key is None:
            logger.warning("firecrawl_extractor_missing_api_key")
            return NoopEvidenceExtractor()
        return FirecrawlEvidenceExtractor(api_key=api_key)

    logger.warning("unknown_evidence_extractor", provider=provider)
    return NoopEvidenceExtractor()


def evidence_extraction_required_from_env() -> bool:
    """Return whether URL extraction is required before issue resolution."""
    value = os.environ.get("PRISM_EVIDENCE_EXTRACTION_REQUIRED", "false").strip().lower()
    return value in {"1", "true", "yes", "on"}


def source_url_is_public_http(url: str) -> bool:
    """Return whether a URL is safe for a server-side fetch/extractor.

    This blocks literal private/local IPs and hostnames that resolve to private,
    loopback, link-local, reserved, or unspecified addresses.
    """
    try:
        parsed = urlsplit(url.strip())
        port = parsed.port
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if parsed.username or parsed.password:
        return False
    if port is not None and not (0 < port < 65536):
        return False
    hostname = parsed.hostname.strip().lower().rstrip(".")
    if hostname in {"localhost", "0", "0.0.0.0"}:
        return False
    if hostname.endswith((".localhost", ".local", ".internal")):
        return False
    return _hostname_resolves_to_public_addresses(hostname)


def _hostname_resolves_to_public_addresses(hostname: str) -> bool:
    try:
        ip = ip_address(hostname.strip("[]"))
    except ValueError:
        pass
    else:
        return _ip_is_public(ip)

    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False
    addresses = {info[4][0] for info in infos if info and info[4]}
    if not addresses:
        return False
    return all(_ip_is_public(ip_address(address)) for address in addresses)


def _ip_is_public(ip: IPv4Address | IPv6Address) -> bool:
    return not (
        getattr(ip, "is_private", True)
        or getattr(ip, "is_loopback", True)
        or getattr(ip, "is_link_local", True)
        or getattr(ip, "is_multicast", True)
        or getattr(ip, "is_reserved", True)
        or getattr(ip, "is_unspecified", True)
    )


def sanitize_source_url(url: str) -> str:
    """Return a receipt-safe source URL with credentials, query, and fragment removed."""
    raw = url.strip()
    if not raw:
        return "redacted-url"
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError:
        return "redacted-url"
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return "redacted-url"
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    netloc = f"{host}:{port}" if port is not None else host
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def clean_extracted_text(value: str) -> str:
    """Normalize extracted text for receipts and support checks."""
    return re.sub(r"\s+", " ", value.replace("\ufffd", " ")).strip()


def redact_public_text(value: str) -> str:
    """Redact common secret-looking tokens before text enters receipts/UI."""
    redacted = re.sub(
        r"(?i)\bauthorization\s*[:=]\s*bearer\s+[^\s,;]{8,}",
        "Authorization: Bearer [redacted]",
        value,
    )
    redacted = re.sub(r"(?i)\bbearer\s+[^\s,;]{8,}", "Bearer [redacted]", redacted)
    redacted = re.sub(
        r"(?i)\b(api[_-]?key|token|secret)\s*[:=]\s*[^\s,;]{8,}",
        lambda match: f"{match.group(1)}=[redacted]",
        redacted,
    )
    redacted = re.sub(r"\bsk-[A-Za-z0-9_-]{10,}\b", "sk-[redacted]", redacted)
    redacted = re.sub(
        r"\b[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{10,}\b",
        "[redacted-jwt]",
        redacted,
    )
    return redacted


def _env_optional(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("invalid_evidence_extractor_float_env", name=name)
        return default


def _extract_tool_arguments(
    mapper_name: str,
    request: EvidencePageExtractRequest,
) -> dict[str, Any]:
    mapper = _EXTRACT_INPUT_MAPPERS.get(mapper_name)
    if mapper is None:
        logger.warning("unknown_extract_input_mapper", mapper=mapper_name)
        mapper = _input_url_objective
    return mapper(request)


def _input_url(request: EvidencePageExtractRequest) -> dict[str, Any]:
    return {"url": request.url}


def _input_url_objective(request: EvidencePageExtractRequest) -> dict[str, Any]:
    return {"url": request.url, "objective": request.objective}


def _input_parallel_web_fetch(request: EvidencePageExtractRequest) -> dict[str, Any]:
    return {
        "url": request.url,
        "objective": request.objective,
        "max_chars": request.max_chars,
    }


def _input_exa_web_fetch(request: EvidencePageExtractRequest) -> dict[str, Any]:
    return {"urls": [request.url], "maxCharacters": request.max_chars}


_EXTRACT_INPUT_MAPPERS: dict[str, EvidenceExtractInputMapper] = {
    "url": _input_url,
    "url_objective": _input_url_objective,
    "parallel_web_fetch": _input_parallel_web_fetch,
    "exa_web_fetch": _input_exa_web_fetch,
}


def map_extraction_result(
    mapper_name: str,
    body: Any,
    request: EvidencePageExtractRequest,
) -> EvidencePageExtractResult | None:
    """Map raw extractor output into Prism's normalized page extraction shape."""
    mapper = _EXTRACT_RESULT_MAPPERS.get(mapper_name.strip().lower())
    if mapper is None:
        logger.warning("unknown_extract_result_mapper", mapper=mapper_name)
        return None
    return mapper(body, request)


def _parse_generic_extract(
    body: Any,
    request: EvidencePageExtractRequest,
) -> EvidencePageExtractResult | None:
    if isinstance(body, str):
        text = body
        title = None
        final_url = None
        published_at = None
    elif isinstance(body, dict):
        data = body.get("data") if isinstance(body.get("data"), dict) else body
        text = _first_string(
            data,
            "markdown",
            "text",
            "content",
            "full_content",
            "raw_content",
            "summary",
        )
        if text is None:
            excerpts = data.get("excerpts")
            if isinstance(excerpts, list):
                cleaned = [item for item in excerpts if isinstance(item, str) and item]
                text = "\n\n".join(cleaned)
        title = _first_string(data, "title")
        final_url = _first_string(data, "url", "final_url")
        published_at = _first_string(data, "published_at", "publishedDate", "publish_date")
    else:
        return None

    if not isinstance(text, str) or not text.strip():
        return None
    return EvidencePageExtractResult(
        url=request.url,
        final_url=final_url,
        title=title,
        text=text[: request.max_chars],
        provider="generic_extract",
        published_at=published_at,
        extracted_at=datetime.now(UTC).isoformat(),
        confidence=0.7,
    )


def _parse_parallel_extract(
    body: Any,
    request: EvidencePageExtractRequest,
) -> EvidencePageExtractResult | None:
    if not isinstance(body, dict):
        return _parse_generic_extract(body, request)
    raw_results = body.get("results")
    if isinstance(raw_results, list) and raw_results:
        first = raw_results[0]
        if isinstance(first, dict):
            text = _first_string(first, "full_content", "markdown", "text")
            if text is None:
                excerpts = first.get("excerpts")
                if isinstance(excerpts, list):
                    text = "\n\n".join([item for item in excerpts if isinstance(item, str)])
            if isinstance(text, str) and text.strip():
                return EvidencePageExtractResult(
                    url=request.url,
                    final_url=_first_string(first, "url"),
                    title=_first_string(first, "title"),
                    text=text[: request.max_chars],
                    provider="parallel_extract",
                    tool_name="web_fetch",
                    published_at=_first_string(first, "publish_date", "published_at"),
                    extracted_at=datetime.now(UTC).isoformat(),
                    confidence=0.82,
                )
    return _parse_generic_extract(body, request)


def _parse_exa_extract(
    body: Any,
    request: EvidencePageExtractRequest,
) -> EvidencePageExtractResult | None:
    if isinstance(body, str) and body.strip():
        return EvidencePageExtractResult(
            url=request.url,
            text=body[: request.max_chars],
            provider="exa_contents",
            tool_name="web_fetch_exa",
            extracted_at=datetime.now(UTC).isoformat(),
            confidence=0.8,
        )
    if not isinstance(body, dict):
        return None
    raw_results = body.get("results")
    if isinstance(raw_results, list) and raw_results:
        first = raw_results[0]
        if isinstance(first, dict):
            text = _first_string(first, "text", "summary", "markdown")
            if text is None:
                highlights = first.get("highlights")
                if isinstance(highlights, list):
                    text = "\n\n".join([item for item in highlights if isinstance(item, str)])
            if isinstance(text, str) and text.strip():
                return EvidencePageExtractResult(
                    url=request.url,
                    final_url=_first_string(first, "url"),
                    title=_first_string(first, "title"),
                    text=text[: request.max_chars],
                    provider="exa_contents",
                    tool_name="web_fetch_exa",
                    published_at=_first_string(first, "publishedDate", "published_at"),
                    extracted_at=datetime.now(UTC).isoformat(),
                    confidence=0.8,
                )
    return _parse_generic_extract(body, request)


def _parse_firecrawl_extract(
    body: Any,
    request: EvidencePageExtractRequest,
) -> EvidencePageExtractResult | None:
    if not isinstance(body, dict):
        return None
    data = body.get("data") if isinstance(body.get("data"), dict) else body
    text = _first_string(data, "markdown", "text", "content")
    if not isinstance(text, str) or not text.strip():
        return None
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    return EvidencePageExtractResult(
        url=request.url,
        final_url=_first_string(data, "url") or _first_string(metadata, "sourceURL", "url"),
        title=_first_string(data, "title") or _first_string(metadata, "title"),
        text=text[: request.max_chars],
        provider="firecrawl_scrape",
        tool_name="firecrawl_scrape",
        published_at=_first_string(data, "published_at", "publishedAt")
        or _first_string(metadata, "published_at", "publishedAt"),
        extracted_at=datetime.now(UTC).isoformat(),
        confidence=0.78,
    )


_EXTRACT_RESULT_MAPPERS: dict[str, EvidenceExtractResultMapper] = {
    "generic_extract": _parse_generic_extract,
    "parallel_extract": _parse_parallel_extract,
    "exa_extract": _parse_exa_extract,
    "firecrawl_scrape": _parse_firecrawl_extract,
}


def _first_string(mapping: Any, *keys: str) -> str | None:
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _mcp_result_body(result: Any) -> Any | None:
    """Extract structured content from a FastMCP call result."""
    data = getattr(result, "data", None)
    if data is not None:
        return data
    structured_content = getattr(result, "structured_content", None)
    if structured_content is not None:
        return structured_content

    content = getattr(result, "content", None)
    if not isinstance(content, list) or not content:
        return None
    text = getattr(content[0], "text", None)
    if not isinstance(text, str):
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text
