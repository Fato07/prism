"""Evidence retrieval abstraction for adversarial resolution.

This intentionally starts small: the resolution loop depends on a provider
interface, not on any one vendor. Future adapters can wrap Parallel x402,
Brave, Tavily, Exa, Firecrawl, or domain APIs while returning the same
provider-neutral result shape.
"""

from __future__ import annotations

import base64
import binascii
import enum
import hashlib
import json
import os
import re
import time
from collections.abc import Callable, Mapping
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit

import httpx
import psycopg
import structlog
from cachetools import TTLCache
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastmcp import Client
from fastmcp.client.auth import BearerAuth
from prism_schemas.verdict import AdversarialChallenge
from pydantic import BaseModel, Field, ValidationError

logger = structlog.get_logger("prism.sentinel.evidence_tools")

EvidenceResultMapper = Callable[[Any], list["EvidenceSearchResult"]]
EvidenceInputMapper = Callable[["EvidenceSearchRequest"], dict[str, Any]]
ConnectorTransport = Literal["mcp_http", "x402_http", "custom_webhook", "direct_adapter"]


class EvidenceSearchRequest(BaseModel):
    """Request for targeted evidence to resolve an adversarial challenge."""

    market_question: str
    challenge: AdversarialChallenge
    query: str
    max_results: int = Field(default=5, ge=1, le=20)


class EvidenceSearchResult(BaseModel):
    """Provider-neutral search/extraction result."""

    title: str
    url: str
    snippet: str
    provider: str
    tool_name: str | None = None
    published_at: str | None = None
    retrieved_at: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class EvidenceProvider(Protocol):
    """Provider interface used by the resolution loop."""

    async def search(self, request: EvidenceSearchRequest) -> list[EvidenceSearchResult]:
        """Return evidence candidates for the targeted request."""


def _with_default_tool_name(
    results: list[EvidenceSearchResult],
    tool_name: str,
) -> list[EvidenceSearchResult]:
    """Backfill stable tool identity while preserving provider-supplied names."""
    return [
        result if result.tool_name else result.model_copy(update={"tool_name": tool_name})
        for result in results
    ]


class EvidenceConnectorConfig(BaseModel):
    """Configuration for one trust-relevant evidence connector."""

    id: str
    transport: ConnectorTransport
    result_mapper: str = "generic_search"
    input_mapper: str = "query"
    tool_name: str | None = None
    server_url: str | None = None
    server_url_env: str | None = None
    endpoint: str | None = None
    endpoint_env: str | None = None
    adapter: str | None = None
    auth_token_env: str | None = None
    timeout_seconds: float = Field(default=20.0, gt=0)
    max_results: int = Field(default=5, ge=1, le=20)
    allowed_tools: list[str] = Field(default_factory=list)
    max_usdc: float | None = Field(default=None, ge=0)


class ToolConnectorManifest(BaseModel):
    """MCP-first connector manifest used by Prism's tool layer."""

    evidence: list[EvidenceConnectorConfig] = Field(default_factory=list)


class NoopEvidenceProvider:
    """Safe default provider: records the gap without doing paid/network calls."""

    async def search(self, request: EvidenceSearchRequest) -> list[EvidenceSearchResult]:
        """Return no results and leave the challenge unresolved."""
        logger.info(
            "evidence_provider_noop",
            challenge_id=request.challenge.id,
            query=request.query,
        )
        return []


class StaticEvidenceProvider:
    """Test/deterministic provider keyed by challenge ID."""

    def __init__(self, results_by_challenge_id: dict[str, list[EvidenceSearchResult]]) -> None:
        """Create provider from precomputed results."""
        self._results_by_challenge_id = results_by_challenge_id

    async def search(self, request: EvidenceSearchRequest) -> list[EvidenceSearchResult]:
        """Return static results for a challenge ID."""
        return self._results_by_challenge_id.get(request.challenge.id, [])


class BudgetAwareEvidenceProvider:
    """Wraps any EvidenceProvider with per-invocation call budgeting.

    Each ``search()`` call counts as one budget unit regardless of the result
    count.  When the budget is exhausted remaining calls are skipped, a
    ``budget_exhausted`` log is emitted, and an empty list is returned.  The
    wrapper implements the EvidenceProvider protocol and is composable with
    other wrappers (cache, circuit breaker).
    """

    def __init__(self, provider: EvidenceProvider, budget: int) -> None:
        """Wrap *provider* with a per-invocation call cap of *budget*."""
        self._provider = provider
        self._budget = budget
        self._remaining = budget

    async def search(self, request: EvidenceSearchRequest) -> list[EvidenceSearchResult]:
        """Return evidence if budget remains, otherwise skip with empty list."""
        if self._remaining <= 0:
            logger.info(
                "budget_exhausted",
                budget=self._budget,
                challenge_id=request.challenge.id,
                query=request.query,
            )
            return []
        self._remaining -= 1
        return await self._provider.search(request)

    @property
    def remaining(self) -> int:
        """Number of calls still available in the current budget window."""
        return self._remaining

    @property
    def budget(self) -> int:
        """Immutable per-invocation call cap."""
        return self._budget


def _cache_key(provider_id: str, query: str) -> tuple[str, str]:
    """Build a deterministic (provider-scoped, query-deterministic) cache key.

    Returns ``(provider_id, sha256_hex_of_query)`` so that two different
    providers searching the same query produce distinct entries while the
    same provider + same query always maps to one entry.
    """
    query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()
    return (provider_id, query_hash)


class CacheAwareEvidenceProvider:
    """Wraps any EvidenceProvider with a ``cachetools.TTLCache`` for result caching.

    Cache key is ``(provider_id, sha256(query))`` — provider-scoped and
    query-deterministic.  Cache hits return stored results immediately without
    calling the underlying provider.  Cache misses delegate to the provider and
    store the result list (including empty lists) under the cache key.

    Parameters:
        provider: The underlying evidence provider to wrap.
        provider_id: Stable identifier for this provider (e.g. ``"brave_search"``).
        cache: Optional pre-built ``TTLCache`` instance (shared across wrappers).
        ttl: Time-to-live in seconds (only used when *cache* is ``None``).
        maxsize: Maximum cache entries (0 disables caching entirely).
    """

    def __init__(
        self,
        provider: EvidenceProvider,
        provider_id: str,
        *,
        cache: TTLCache[tuple[str, str], list[EvidenceSearchResult]] | None = None,
        ttl: int = 300,
        maxsize: int = 256,
    ) -> None:
        """Wrap *provider* with an optional shared ``TTLCache``."""
        self._provider = provider
        self._provider_id = provider_id
        self._cache: TTLCache[tuple[str, str], list[EvidenceSearchResult]] = (
            cache if cache is not None else TTLCache(maxsize=maxsize, ttl=ttl)
        )
        self._hits = 0
        self._misses = 0
        self._disabled = maxsize == 0 and cache is None

    async def search(self, request: EvidenceSearchRequest) -> list[EvidenceSearchResult]:
        """Return cached results if available, otherwise delegate to provider."""
        if self._disabled:
            self._misses += 1
            return await self._provider.search(request)

        key = _cache_key(self._provider_id, request.query)

        if key in self._cache:
            self._hits += 1
            logger.info(
                "evidence_cache_hit",
                provider_id=self._provider_id,
                query_hash=key[1],
            )
            return list(self._cache[key])

        self._misses += 1
        logger.info(
            "evidence_cache_miss",
            provider_id=self._provider_id,
            query_hash=key[1],
        )
        results = await self._provider.search(request)
        # Store a copy so mutations to the returned list don't corrupt the cache.
        self._cache[key] = list(results)
        return results

    @property
    def hits(self) -> int:
        """Number of cache hits in the current validation window."""
        return self._hits

    @property
    def misses(self) -> int:
        """Number of cache misses in the current validation window."""
        return self._misses

    @property
    def disabled(self) -> bool:
        """Whether caching is entirely disabled (maxsize=0)."""
        return self._disabled


# ---------------------------------------------------------------------------
# Circuit breaker state machine
# ---------------------------------------------------------------------------

CircuitBreakerState = enum.Enum(
    "CircuitBreakerState",
    ["CLOSED", "OPEN", "HALF_OPEN"],
)
"""Circuit breaker state machine states.

CLOSED: normal operation, requests flow through.
OPEN: failing, requests return empty immediately (fail-closed).
HALF_OPEN: trial state after cooldown, allows one test request.
"""


class CircuitBreakerAwareEvidenceProvider:
    """Wraps any EvidenceProvider with a per-provider circuit breaker.

    States:
      - CLOSED: normal, delegates to the inner provider.
      - OPEN: fail-closed, returns ``[]`` immediately without calling provider.
      - HALF_OPEN: after cooldown, one trial call is allowed — success closes
        the circuit, failure re-opens it.

    Only **exceptions** (not empty result lists) count as failures.
    Non-consecutive failures reset the counter on the next success.

    Parameters:
        provider: The underlying evidence provider to wrap.
        provider_id: Stable identifier (used for per-provider isolation).
        failure_threshold: Consecutive exceptions before circuit opens (default 3).
        cooldown_seconds: Seconds before HALF-OPEN trial (default 60).
    """

    def __init__(
        self,
        provider: EvidenceProvider,
        provider_id: str,
        *,
        failure_threshold: int = 3,
        cooldown_seconds: float = 60.0,
    ) -> None:
        self._provider = provider
        self._provider_id = provider_id
        self._failure_threshold = max(1, failure_threshold)
        self._cooldown_seconds = max(0.0, cooldown_seconds)
        self._state: CircuitBreakerState = CircuitBreakerState.CLOSED
        self._consecutive_failures: int = 0
        self._opened_at: float | None = None
        self._last_call_failed: bool = False

    async def search(self, request: EvidenceSearchRequest) -> list[EvidenceSearchResult]:
        """Return evidence if circuit is CLOSED/HALF_OPEN, else ``[]``."""
        now = time.monotonic()

        if self._state is CircuitBreakerState.OPEN:
            if self._opened_at is not None and (now - self._opened_at) >= self._cooldown_seconds:
                self._state = CircuitBreakerState.HALF_OPEN
                logger.info(
                    "circuit_breaker_half_open",
                    provider_id=self._provider_id,
                    consecutive_failures=self._consecutive_failures,
                )
            else:
                logger.warning(
                    "circuit_breaker_open",
                    provider_id=self._provider_id,
                    consecutive_failures=self._consecutive_failures,
                )
                self._last_call_failed = False
                return []

        # CLOSED or HALF_OPEN: delegate to provider
        try:
            results = await self._provider.search(request)
        except Exception as exc:
            self._consecutive_failures += 1
            self._last_call_failed = True
            logger.warning(
                "circuit_breaker_failure",
                provider_id=self._provider_id,
                consecutive_failures=self._consecutive_failures,
                failure_threshold=self._failure_threshold,
                error=type(exc).__name__,
            )
            if self._state is CircuitBreakerState.HALF_OPEN:
                # HALF_OPEN failure → re-OPEN immediately
                self._state = CircuitBreakerState.OPEN
                self._opened_at = now
                logger.warning(
                    "circuit_breaker_half_open_failed",
                    provider_id=self._provider_id,
                )
            elif self._consecutive_failures >= self._failure_threshold:
                self._state = CircuitBreakerState.OPEN
                self._opened_at = now
                logger.warning(
                    "circuit_breaker_opened",
                    provider_id=self._provider_id,
                    consecutive_failures=self._consecutive_failures,
                )
            return []

        # Success: reset failure counter
        self._last_call_failed = False
        if self._consecutive_failures > 0:
            self._consecutive_failures = 0
            logger.info(
                "circuit_breaker_failure_counter_reset",
                provider_id=self._provider_id,
            )
        if self._state is CircuitBreakerState.HALF_OPEN:
            self._state = CircuitBreakerState.CLOSED
            logger.info(
                "circuit_breaker_closed_after_half_open_success",
                provider_id=self._provider_id,
            )
        return results

    @property
    def state(self) -> CircuitBreakerState:
        """Current circuit breaker state."""
        return self._state

    @property
    def consecutive_failures(self) -> int:
        """Number of consecutive provider failures."""
        return self._consecutive_failures

    @property
    def last_call_failed(self) -> bool:
        """Whether the most recent ``search()`` call failed with an exception."""
        return self._last_call_failed

    @property
    def provider_id(self) -> str:
        """Stable identifier for per-provider isolation."""
        return self._provider_id


class McpEvidenceProvider:
    """Evidence provider that calls an MCP tool and maps its output explicitly."""

    def __init__(
        self,
        *,
        server_url: str | None = None,
        tool_name: str,
        result_mapper: str = "generic_search",
        input_mapper: str = "query",
        auth_token: str | None = None,
        timeout_seconds: float = 20.0,
        allowed_tools: list[str] | None = None,
        transport: Any | None = None,
    ) -> None:
        """Create an MCP evidence provider.

        `transport` is primarily for tests/in-process FastMCP servers. Production
        config should use `server_url`.
        """
        self.transport = transport if transport is not None else server_url
        self.server_url = server_url
        self.tool_name = tool_name
        self.result_mapper = result_mapper.strip().lower()
        self.input_mapper = input_mapper.strip().lower()
        self.auth_token = auth_token
        self.timeout_seconds = timeout_seconds
        self.allowed_tools = allowed_tools or [tool_name]

    async def search(self, request: EvidenceSearchRequest) -> list[EvidenceSearchResult]:
        """Call the configured MCP tool and normalize the returned artifacts."""
        if self.tool_name not in self.allowed_tools:
            logger.warning(
                "mcp_evidence_tool_not_allowed",
                tool_name=self.tool_name,
            )
            return []
        if self.transport is None:
            logger.warning(
                "mcp_evidence_missing_transport",
                tool_name=self.tool_name,
            )
            return []

        auth = BearerAuth(self.auth_token) if self.auth_token else None
        try:
            async with Client(
                self.transport,
                auth=auth,
                timeout=self.timeout_seconds,
            ) as client:
                result = await client.call_tool(
                    self.tool_name,
                    _mcp_tool_arguments(self.input_mapper, request),
                    raise_on_error=False,
                    timeout=self.timeout_seconds,
                )
        except Exception as exc:
            logger.warning(
                "mcp_evidence_call_failed",
                tool_name=self.tool_name,
                mapper=self.result_mapper,
                input_mapper=self.input_mapper,
                error=str(exc),
            )
            return []

        if getattr(result, "is_error", False):
            logger.warning(
                "mcp_evidence_tool_returned_error",
                tool_name=self.tool_name,
                mapper=self.result_mapper,
                input_mapper=self.input_mapper,
            )
            return []

        body = _mcp_result_body(result)
        if body is None:
            logger.warning(
                "mcp_evidence_unparseable_result",
                tool_name=self.tool_name,
                mapper=self.result_mapper,
                input_mapper=self.input_mapper,
            )
            return []
        results = map_evidence_results(self.result_mapper, body)[: request.max_results]
        return _with_default_tool_name(results, self.tool_name)


class FirecrawlSearchEvidenceProvider:
    """Evidence provider backed by Firecrawl's Search API."""

    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str = "https://api.firecrawl.dev/v2/search",
        country: str | None = None,
        location: str | None = None,
        tbs: str | None = None,
        category: str | None = None,
        scrape_format: str = "markdown",
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Create a Firecrawl Search provider with a user-supplied API key."""
        self.api_key = api_key
        self.endpoint = endpoint
        self.country = _optional_string(country)
        self.location = _optional_string(location)
        self.tbs = _optional_string(tbs)
        self.category = _normalize_firecrawl_category(category)
        self.scrape_format = _normalize_firecrawl_scrape_format(scrape_format)
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def search(self, request: EvidenceSearchRequest) -> list[EvidenceSearchResult]:
        """Query Firecrawl Search and normalize scraped web results."""
        payload: dict[str, Any] = {
            "query": request.query,
            "limit": request.max_results,
            "sources": ["web"],
        }
        if self.country:
            payload["country"] = self.country
        if self.location:
            payload["location"] = self.location
        if self.tbs:
            payload["tbs"] = self.tbs
        if self.category:
            payload["categories"] = [{"type": self.category}]
        if self.scrape_format is not None:
            payload["scrapeOptions"] = {"formats": [{"type": self.scrape_format}]}

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
                "firecrawl_search_failed",
                challenge_id=request.challenge.id,
                error=str(exc),
            )
            return []

        body = _response_json_or_none(
            response,
            provider="firecrawl_search",
            challenge_id=request.challenge.id,
        )
        if body is None:
            return []
        return _with_default_tool_name(_parse_firecrawl_results(body), "firecrawl_search")


class ExaSearchEvidenceProvider:
    """Evidence provider backed by Exa's Search API."""

    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str = "https://api.exa.ai/search",
        search_type: str = "auto",
        category: str | None = None,
        user_location: str | None = None,
        text_max_characters: int = 1200,
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Create an Exa Search provider with a user-supplied API key."""
        self.api_key = api_key
        self.endpoint = endpoint
        self.search_type = _normalize_exa_search_type(search_type)
        self.category = _normalize_exa_category(category)
        self.user_location = user_location
        self.text_max_characters = max(1, text_max_characters)
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def search(self, request: EvidenceSearchRequest) -> list[EvidenceSearchResult]:
        """Query Exa Search and normalize highlighted web results."""
        payload: dict[str, Any] = {
            "query": request.query,
            "type": self.search_type,
            "numResults": request.max_results,
            "contents": {
                "highlights": {
                    "maxCharacters": self.text_max_characters,
                    "query": request.query,
                }
            },
        }
        if self.category:
            payload["category"] = self.category
        if self.user_location:
            payload["userLocation"] = self.user_location

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
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
                "exa_search_failed",
                challenge_id=request.challenge.id,
                error=str(exc),
            )
            return []

        body = _response_json_or_none(
            response,
            provider="exa_search",
            challenge_id=request.challenge.id,
        )
        if body is None:
            return []
        return _with_default_tool_name(_parse_exa_results(body), "exa_search")


class ParallelSearchEvidenceProvider:
    """Evidence provider backed by Parallel's Search API."""

    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str = "https://api.parallel.ai/v1/search",
        mode: str = "advanced",
        location: str | None = None,
        max_chars_total: int | None = None,
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Create a Parallel Search provider with a user-supplied API key."""
        self.api_key = api_key
        self.endpoint = endpoint
        self.mode = mode
        self.location = location
        self.max_chars_total = max_chars_total
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def search(self, request: EvidenceSearchRequest) -> list[EvidenceSearchResult]:
        """Query Parallel Search and normalize excerpted web results."""
        payload: dict[str, Any] = {
            "objective": _parallel_objective(request),
            "search_queries": [request.query],
            "mode": self.mode,
            "advanced_settings": {"max_results": request.max_results},
        }
        if self.location:
            payload["advanced_settings"]["location"] = self.location
        if self.max_chars_total is not None:
            payload["max_chars_total"] = self.max_chars_total

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
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
                "parallel_search_failed",
                challenge_id=request.challenge.id,
                error=str(exc),
            )
            return []

        body = _response_json_or_none(
            response,
            provider="parallel_search",
            challenge_id=request.challenge.id,
        )
        if body is None:
            return []
        return _with_default_tool_name(_parse_parallel_results(body), "parallel_search")


class BraveSearchEvidenceProvider:
    """Evidence provider backed by Brave Search's Web Search API."""

    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str = "https://api.search.brave.com/res/v1/web/search",
        country: str | None = None,
        search_lang: str | None = None,
        freshness: str | None = None,
        timeout_seconds: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Create a Brave Search provider with a user-supplied API key."""
        self.api_key = api_key
        self.endpoint = endpoint
        self.country = country
        self.search_lang = search_lang
        self.freshness = freshness
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def search(self, request: EvidenceSearchRequest) -> list[EvidenceSearchResult]:
        """Query Brave Search and normalize web results."""
        params: dict[str, str | int] = {
            "q": request.query,
            "count": request.max_results,
        }
        if self.country:
            params["country"] = self.country
        if self.search_lang:
            params["search_lang"] = self.search_lang
        if self.freshness:
            params["freshness"] = self.freshness

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.api_key,
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.get(self.endpoint, params=params, headers=headers)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning(
                "brave_search_failed",
                challenge_id=request.challenge.id,
                error=str(exc),
            )
            return []

        body = _response_json_or_none(
            response,
            provider="brave_search",
            challenge_id=request.challenge.id,
        )
        if body is None:
            return []
        return _with_default_tool_name(_parse_brave_results(body), "brave_search")


class TavilySearchEvidenceProvider:
    """Evidence provider backed by Tavily Search."""

    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str = "https://api.tavily.com/search",
        search_depth: str = "basic",
        topic: str = "general",
        time_range: str | None = None,
        timeout_seconds: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Create a Tavily Search provider with a user-supplied API key."""
        self.api_key = api_key
        self.endpoint = endpoint
        self.search_depth = _normalize_tavily_search_depth(search_depth)
        self.topic = _normalize_tavily_topic(topic)
        self.time_range = _normalize_tavily_time_range(time_range)
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def search(self, request: EvidenceSearchRequest) -> list[EvidenceSearchResult]:
        """Query Tavily Search and normalize ranked web results."""
        payload: dict[str, Any] = {
            "query": request.query,
            "search_depth": self.search_depth,
            "max_results": request.max_results,
            "topic": self.topic,
            "include_answer": False,
            "include_raw_content": False,
        }
        if self.time_range:
            payload["time_range"] = self.time_range

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
                "tavily_search_failed",
                challenge_id=request.challenge.id,
                error=str(exc),
            )
            return []

        body = _response_json_or_none(
            response,
            provider="tavily_search",
            challenge_id=request.challenge.id,
        )
        if body is None:
            return []
        return _with_default_tool_name(_parse_tavily_results(body), "tavily_search")


class CustomWebhookEvidenceProvider:
    """BYO evidence provider backed by a user-controlled HTTP webhook.

    The webhook receives the provider-neutral request shape and can call any
    internal tool, MCP server, search API, data warehouse, or paid x402 service
    the operator wants. It returns either `{ "results": [...] }` or a bare list
    of result objects compatible with `EvidenceSearchResult`.
    """

    def __init__(
        self,
        *,
        url: str,
        bearer_token: str | None = None,
        timeout_seconds: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Create a custom webhook provider."""
        self.url = url
        self.bearer_token = bearer_token
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def search(self, request: EvidenceSearchRequest) -> list[EvidenceSearchResult]:
        """POST a targeted evidence request to the configured webhook."""
        headers = {"Content-Type": "application/json"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"

        payload = request.model_dump(mode="json")
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.post(self.url, json=payload, headers=headers)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning(
                "custom_evidence_webhook_failed",
                url=_redacted_url_for_log(self.url),
                challenge_id=request.challenge.id,
                error=type(exc).__name__,
                status_code=_http_status_code(exc),
            )
            return []

        body = _response_json_or_none(
            response,
            provider="custom_webhook",
            challenge_id=request.challenge.id,
        )
        if body is None:
            return []
        return _with_default_tool_name(
            _parse_webhook_results(body, fallback_provider="custom_webhook"),
            "custom_webhook",
        )


def evidence_provider_from_env() -> EvidenceProvider:
    """Return the configured evidence provider.

    Supported values:
    - `noop` (default): no network or paid calls.
    - `custom_webhook`: POST requests to `PRISM_EVIDENCE_WEBHOOK_URL`.
    - `brave_search`: query Brave's Web Search API with `BRAVE_SEARCH_API_KEY`.
    - `parallel_search`: query Parallel's Search API with `PARALLEL_API_KEY`.
    - `tavily_search`: query Tavily Search with `TAVILY_API_KEY`.
    - `exa_search`: query Exa Search with `EXA_API_KEY`.
    - `firecrawl_search`: query Firecrawl Search with `FIRECRAWL_API_KEY`.
    """
    provider = os.environ.get("PRISM_EVIDENCE_PROVIDER", "noop").strip().lower()
    if provider == "noop":
        return NoopEvidenceProvider()
    if provider in {"mcp", "mcp_http"}:
        server_url = _env_optional_string("PRISM_EVIDENCE_MCP_URL")
        tool_name = _env_optional_string("PRISM_EVIDENCE_MCP_TOOL")
        if server_url is None or tool_name is None:
            logger.warning(
                "mcp_evidence_missing_required_config",
                has_server_url=server_url is not None,
                has_tool_name=tool_name is not None,
                fallback="noop",
            )
            return NoopEvidenceProvider()
        result_mapper = os.environ.get("PRISM_EVIDENCE_RESULT_MAPPER", "generic_search")
        input_mapper = os.environ.get("PRISM_EVIDENCE_MCP_INPUT_MAPPER", "query")
        if not _is_known_evidence_result_mapper(result_mapper):
            logger.warning(
                "mcp_evidence_unknown_result_mapper",
                mapper=result_mapper.strip().lower(),
                fallback="noop",
            )
            return NoopEvidenceProvider()
        if not _is_known_evidence_input_mapper(input_mapper):
            logger.warning(
                "mcp_evidence_unknown_input_mapper",
                input_mapper=input_mapper.strip().lower(),
                fallback="noop",
            )
            return NoopEvidenceProvider()
        timeout_seconds = _float_env("PRISM_EVIDENCE_MCP_TIMEOUT_SECONDS", 20.0)
        return McpEvidenceProvider(
            server_url=server_url,
            tool_name=tool_name,
            result_mapper=result_mapper,
            input_mapper=input_mapper,
            auth_token=os.environ.get("PRISM_EVIDENCE_MCP_AUTH_TOKEN"),
            timeout_seconds=timeout_seconds,
            allowed_tools=_csv_env("PRISM_EVIDENCE_MCP_ALLOWED_TOOLS") or [tool_name],
        )
    if provider in {"firecrawl", "firecrawl_search"}:
        api_key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
        if not api_key:
            logger.warning(
                "firecrawl_search_missing_api_key",
                fallback="noop",
            )
            return NoopEvidenceProvider()
        timeout_seconds = _float_env("FIRECRAWL_SEARCH_TIMEOUT_SECONDS", 30.0)
        return FirecrawlSearchEvidenceProvider(
            api_key=api_key,
            country=_env_optional_string("FIRECRAWL_SEARCH_COUNTRY"),
            location=_env_optional_string("FIRECRAWL_SEARCH_LOCATION"),
            tbs=_env_optional_string("FIRECRAWL_SEARCH_TBS"),
            category=_env_optional_string("FIRECRAWL_SEARCH_CATEGORY"),
            scrape_format=os.environ.get("FIRECRAWL_SEARCH_FORMAT", "markdown"),
            timeout_seconds=timeout_seconds,
        )
    if provider in {"exa", "exa_search"}:
        api_key = os.environ.get("EXA_API_KEY", "").strip()
        if not api_key:
            logger.warning(
                "exa_search_missing_api_key",
                fallback="noop",
            )
            return NoopEvidenceProvider()
        timeout_seconds = _float_env("EXA_SEARCH_TIMEOUT_SECONDS", 30.0)
        return ExaSearchEvidenceProvider(
            api_key=api_key,
            search_type=_exa_search_type_from_env(),
            category=_exa_category_from_env(),
            user_location=os.environ.get("EXA_SEARCH_USER_LOCATION"),
            text_max_characters=_int_env_or_none("EXA_SEARCH_TEXT_MAX_CHARACTERS") or 1200,
            timeout_seconds=timeout_seconds,
        )
    if provider in {"parallel", "parallel_search"}:
        api_key = os.environ.get("PARALLEL_API_KEY", "").strip()
        if not api_key:
            logger.warning(
                "parallel_search_missing_api_key",
                fallback="noop",
            )
            return NoopEvidenceProvider()
        timeout_seconds = _float_env("PARALLEL_SEARCH_TIMEOUT_SECONDS", 30.0)
        return ParallelSearchEvidenceProvider(
            api_key=api_key,
            mode=_parallel_mode_from_env(),
            location=os.environ.get("PARALLEL_SEARCH_LOCATION"),
            max_chars_total=_int_env_or_none("PARALLEL_SEARCH_MAX_CHARS_TOTAL"),
            timeout_seconds=timeout_seconds,
        )
    if provider in {"tavily", "tavily_search"}:
        api_key = os.environ.get("TAVILY_API_KEY", "").strip()
        if not api_key:
            logger.warning(
                "tavily_search_missing_api_key",
                fallback="noop",
            )
            return NoopEvidenceProvider()
        timeout_seconds = _float_env("TAVILY_SEARCH_TIMEOUT_SECONDS", 20.0)
        return TavilySearchEvidenceProvider(
            api_key=api_key,
            search_depth=_tavily_search_depth_from_env(),
            topic=_tavily_topic_from_env(),
            time_range=_tavily_time_range_from_env(),
            timeout_seconds=timeout_seconds,
        )
    if provider in {"brave", "brave_search"}:
        api_key = os.environ.get("BRAVE_SEARCH_API_KEY", "").strip()
        if not api_key:
            logger.warning(
                "brave_search_missing_api_key",
                fallback="noop",
            )
            return NoopEvidenceProvider()
        timeout_seconds = _float_env("BRAVE_SEARCH_TIMEOUT_SECONDS", 20.0)
        return BraveSearchEvidenceProvider(
            api_key=api_key,
            country=os.environ.get("BRAVE_SEARCH_COUNTRY"),
            search_lang=os.environ.get("BRAVE_SEARCH_LANG"),
            freshness=os.environ.get("BRAVE_SEARCH_FRESHNESS"),
            timeout_seconds=timeout_seconds,
        )
    if provider == "custom_webhook":
        url = os.environ.get("PRISM_EVIDENCE_WEBHOOK_URL", "").strip()
        if not url:
            logger.warning(
                "custom_evidence_webhook_missing_url",
                fallback="noop",
            )
            return NoopEvidenceProvider()
        timeout_seconds = _float_env("PRISM_EVIDENCE_WEBHOOK_TIMEOUT_SECONDS", 20.0)
        return CustomWebhookEvidenceProvider(
            url=url,
            bearer_token=os.environ.get("PRISM_EVIDENCE_WEBHOOK_BEARER_TOKEN"),
            timeout_seconds=timeout_seconds,
        )

    logger.warning(
        "evidence_provider_not_implemented",
        provider=provider,
        fallback="noop",
    )
    return NoopEvidenceProvider()


# ---------------------------------------------------------------------------
# Module-level singletons for persistence across validations
# ---------------------------------------------------------------------------

_shared_evidence_cache: TTLCache[tuple[str, str], list[EvidenceSearchResult]] | None = None
"""Shared TTLCache instance persisted across /validate and /evidence invocations."""

_circuit_breaker_registry: dict[str, CircuitBreakerAwareEvidenceProvider] = {}
"""Per-provider circuit breaker instances persisted across validations."""


def _get_shared_cache() -> TTLCache[tuple[str, str], list[EvidenceSearchResult]]:
    """Return (or lazily create) the shared ``TTLCache`` instance.

    The cache is created once at first access with TTL and maxsize read from
    environment variables.  A ``maxsize`` of 0 means caching is disabled —
    a dummy cache is returned in that case.
    """
    global _shared_evidence_cache
    if _shared_evidence_cache is None:
        maxsize = _read_cache_maxsize()
        ttl = _read_cache_ttl()
        if maxsize == 0:
            # Dummy cache — never actually used (cache wrapper checks disabled flag).
            _shared_evidence_cache = TTLCache(maxsize=1, ttl=1)
        else:
            _shared_evidence_cache = TTLCache(maxsize=maxsize, ttl=ttl)
    return _shared_evidence_cache


def _get_or_create_circuit_breaker(
    inner_provider: EvidenceProvider,
    provider_id: str,
) -> CircuitBreakerAwareEvidenceProvider:
    """Return an existing circuit breaker for *provider_id* or create a new one.

    Circuit breaker state persists across validations — the same instance is
    reused for the same provider identity.  The *inner_provider* argument is
    only used when creating a new circuit breaker.
    """
    if provider_id in _circuit_breaker_registry:
        return _circuit_breaker_registry[provider_id]
    cb = CircuitBreakerAwareEvidenceProvider(
        inner_provider,
        provider_id,
        failure_threshold=_read_circuit_breaker_threshold(),
        cooldown_seconds=_read_circuit_breaker_cooldown(),
    )
    _circuit_breaker_registry[provider_id] = cb
    return cb


def evidence_provider_from_runtime(
    dsn: str | None = None,
) -> EvidenceProvider:
    """Return the raw configured evidence provider (from DB connector or env).

    This is the *raw* unevaluated provider.  The resolution loop is responsible
    for composing the full wrapper stack (budget → cache → circuit breaker).

    ``NoopEvidenceProvider`` is returned bare — the resolution loop must skip
    wrappers when it receives a noop provider.
    """
    raw = evidence_provider_from_active_connector(dsn=dsn)
    if raw is None:
        raw = evidence_provider_from_env()
    return raw


def build_evidence_provider_stack(
    raw_provider: EvidenceProvider,
    *,
    budget: int,
) -> EvidenceProvider:
    """Build the full evidence provider wrapper stack around *raw_provider*.

    Layering order (outside-in):
        CircuitBreakerAware → CacheAware → BudgetAware → *raw_provider*

    This ensures:
      - Cache hits short-circuit before budget check or circuit breaker.
      - Circuit-open returns ``[]`` without consuming budget.
      - Only actual provider invocations consume a budget unit.
      - Failed provider calls do NOT populate the cache (exceptions propagate
        before the cache's store line).

    ``NoopEvidenceProvider`` is returned as-is (no wrappers applied).
    """
    if isinstance(raw_provider, NoopEvidenceProvider):
        return raw_provider

    provider_id = _provider_identity(raw_provider)

    # Budget wrapper (innermost — only actual provider calls consume budget)
    provider: EvidenceProvider = BudgetAwareEvidenceProvider(raw_provider, budget)

    # Cache wrapper (shared cache across validations, sits above budget)
    cache = _get_shared_cache()
    maxsize = _read_cache_maxsize()
    provider = CacheAwareEvidenceProvider(
        provider,
        provider_id=provider_id,
        cache=cache,
        ttl=_read_cache_ttl(),
        maxsize=maxsize,
    )

    # Circuit breaker wrapper (outermost — catches exceptions from all layers)
    provider = _get_or_create_circuit_breaker(provider, provider_id)

    return provider


def _provider_identity(raw: EvidenceProvider) -> str:
    """Derive a stable identity string for the raw provider instance.

    Used as a cache key prefix and circuit-breaker registry key.
    """
    # Use isinstance checks for reliable identity (class names change in tests)
    if isinstance(raw, NoopEvidenceProvider):
        return "noop"
    if isinstance(raw, StaticEvidenceProvider):
        return "static"

    class_name = type(raw).__name__
    # Map known provider class names to stable short IDs
    if class_name == "BraveSearchEvidenceProvider":
        return "brave_search"
    if class_name == "ParallelSearchEvidenceProvider":
        return "parallel_search"
    if class_name == "TavilySearchEvidenceProvider":
        return "tavily_search"
    if class_name == "ExaSearchEvidenceProvider":
        return "exa_search"
    if class_name == "FirecrawlSearchEvidenceProvider":
        return "firecrawl_search"
    if class_name == "CustomWebhookEvidenceProvider":
        return "custom_webhook"
    if class_name == "McpEvidenceProvider":
        return "mcp_evidence"
    # Fallback: use class name lowercased
    return class_name.lower()


def evidence_provider_from_active_connector(dsn: str | None = None) -> EvidenceProvider | None:
    """Load the one armed evidence connector from Neon and return a provider."""
    if os.environ.get("PRISM_EVIDENCE_DB_CONNECTORS", "1").strip().lower() in {"0", "false", "no"}:
        return None

    database_url = dsn or os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return None

    try:
        row = _active_connector_row(database_url)
    except (psycopg.Error, OSError) as exc:
        logger.warning(
            "active_evidence_connector_lookup_failed",
            error=type(exc).__name__,
            fallback="noop",
        )
        return NoopEvidenceProvider()
    if row is None:
        return None
    return evidence_provider_from_connector_row(row)


def evidence_provider_from_connector_row(row: Mapping[str, Any]) -> EvidenceProvider:
    """Convert a DB connector passport row into a fail-closed evidence provider."""
    connector_id = str(row.get("id", ""))
    transport = str(row.get("transport", "")).strip().lower()
    smoke_status = str(row.get("smoke_status", "")).strip().lower()
    fail_closed = bool(row.get("fail_closed", True))
    if smoke_status != "passed" or not fail_closed:
        logger.warning(
            "active_evidence_connector_not_usable",
            connector_id=connector_id,
            transport=transport,
            smoke_status=smoke_status,
            fail_closed=fail_closed,
            fallback="noop",
        )
        return NoopEvidenceProvider()

    server_url = _optional_string(_row_string(row, "server_url"))
    tool_name = _optional_string(_row_string(row, "tool_name"))
    result_mapper = _row_string(row, "result_mapper") or "generic_search"
    input_mapper = _row_string(row, "input_mapper") or "query"
    if server_url is None or (transport == "mcp_http" and tool_name is None):
        logger.warning(
            "active_evidence_connector_missing_required_config",
            connector_id=connector_id,
            fallback="noop",
        )
        return NoopEvidenceProvider()
    if not _is_known_evidence_result_mapper(result_mapper):
        logger.warning(
            "active_evidence_connector_unknown_result_mapper",
            connector_id=connector_id,
            mapper=result_mapper.strip().lower(),
            fallback="noop",
        )
        return NoopEvidenceProvider()
    if not _is_known_evidence_input_mapper(input_mapper):
        logger.warning(
            "active_evidence_connector_unknown_input_mapper",
            connector_id=connector_id,
            input_mapper=input_mapper.strip().lower(),
            fallback="noop",
        )
        return NoopEvidenceProvider()

    auth_token_value = _decrypt_connector_token_from_row(row)
    if auth_token_value is _TOKEN_UNAVAILABLE:
        logger.warning(
            "active_evidence_connector_token_unavailable",
            connector_id=connector_id,
            fallback="noop",
        )
        return NoopEvidenceProvider()

    auth_token = auth_token_value if isinstance(auth_token_value, str) else None
    timeout_seconds = _row_float(row.get("timeout_seconds"), fallback=20.0)
    if transport == "custom_webhook":
        return CustomWebhookEvidenceProvider(
            url=server_url,
            bearer_token=auth_token,
            timeout_seconds=timeout_seconds,
        )
    if transport != "mcp_http":
        logger.warning(
            "active_evidence_connector_unsupported_transport",
            connector_id=connector_id,
            transport=transport,
            fallback="noop",
        )
        return NoopEvidenceProvider()

    assert tool_name is not None
    allowed_tools = _row_string_list(row.get("allowed_tools")) or [tool_name]
    return McpEvidenceProvider(
        server_url=server_url,
        tool_name=tool_name,
        result_mapper=result_mapper,
        input_mapper=input_mapper,
        auth_token=auth_token,
        timeout_seconds=timeout_seconds,
        allowed_tools=allowed_tools,
    )


def _active_connector_row(dsn: str) -> Mapping[str, Any] | None:
    """Fetch the one armed evidence connector row from Postgres."""
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text AS id,
                   transport,
                   server_url,
                   tool_name,
                   input_mapper,
                   result_mapper,
                   allowed_tools,
                   timeout_seconds::text AS timeout_seconds,
                   auth_secret_ciphertext,
                   smoke_status,
                   fail_closed
            FROM tool_connectors
            WHERE connector_kind = 'evidence' AND armed = TRUE
            ORDER BY updated_at DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        if row is None:
            return None
        columns = [desc.name for desc in cur.description or []]
        return dict(zip(columns, row, strict=True))


_TOKEN_UNAVAILABLE = object()


def _decrypt_connector_token_from_row(row: Mapping[str, Any]) -> str | None | object:
    """Decrypt an encrypted connector bearer token, returning a sentinel on failure."""
    ciphertext = _optional_string(_row_string(row, "auth_secret_ciphertext"))
    if ciphertext is None:
        return None
    key = os.environ.get("CONNECTOR_SECRETS_KEY")
    if not key:
        return _TOKEN_UNAVAILABLE
    try:
        return decrypt_connector_token(ciphertext, key)
    except ConnectorTokenError:
        return _TOKEN_UNAVAILABLE


class ConnectorTokenError(ValueError):
    """Raised when a connector token envelope cannot be decrypted."""


def decrypt_connector_token(envelope: str, raw_key: str) -> str:
    """Decrypt the v1 AES-GCM connector token envelope produced by the dashboard."""
    parts = envelope.split(":")
    if len(parts) != 4 or parts[0] != "v1":
        raise ConnectorTokenError("invalid connector token envelope")
    key = _decode_connector_key(raw_key)
    try:
        iv = _b64url_decode(parts[1])
        tag = _b64url_decode(parts[2])
        ciphertext = _b64url_decode(parts[3])
        return AESGCM(key).decrypt(iv, ciphertext + tag, None).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, InvalidTag, ValueError) as exc:
        raise ConnectorTokenError("invalid connector token envelope") from exc


def _decode_connector_key(raw_key: str) -> bytes:
    """Decode CONNECTOR_SECRETS_KEY using the dashboard-compatible formats."""
    key = raw_key.strip()
    if not key:
        raise ConnectorTokenError("missing connector token key")
    if len(key) == 64:
        try:
            decoded = bytes.fromhex(key)
        except ValueError:
            decoded = b""
        if len(decoded) == 32:
            return decoded
    for decoder in (_b64decode, _b64url_decode):
        try:
            decoded = decoder(key)
        except binascii.Error:
            continue
        if len(decoded) == 32:
            return decoded
    raw = key.encode("utf-8")
    if len(raw) == 32:
        return raw
    raise ConnectorTokenError("connector token key must decode to 32 bytes")


def _b64decode(value: str) -> bytes:
    return base64.b64decode(_pad_base64(value), validate=True)


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(_pad_base64(value))


def _pad_base64(value: str) -> str:
    return value + "=" * (-len(value) % 4)


def _row_string(row: Mapping[str, Any], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    return str(value)


def _row_float(value: Any, *, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _row_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _env_optional_string(name: str) -> str | None:
    """Return a stripped environment value, treating blanks as unset."""
    return _optional_string(os.environ.get(name))


def _csv_env(name: str) -> list[str]:
    """Return a comma-separated env var as stripped non-empty values."""
    raw_value = os.environ.get(name, "")
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def _redacted_url_for_log(url: str) -> str:
    """Return a log-safe URL origin without credentials, path, query, or fragment."""
    try:
        parsed = urlsplit(url)
    except ValueError:
        return "redacted-url"
    if not parsed.scheme or parsed.hostname is None:
        return "redacted-url"
    host = parsed.hostname
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return f"{parsed.scheme}://{host}"


def _http_status_code(exc: httpx.HTTPError) -> int | None:
    """Return a response status code without serializing request URLs."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code
    return None


def _optional_string(value: str | None) -> str | None:
    """Return a stripped string value, treating blanks as unset."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_firecrawl_category(category: str | None) -> str | None:
    """Return a supported Firecrawl search category."""
    if category is None:
        return None
    normalized = category.strip().lower()
    if normalized == "":
        return None
    if normalized in {"github", "research", "pdf"}:
        return normalized
    logger.warning(
        "invalid_firecrawl_category",
        category=normalized,
        fallback=None,
    )
    return None


def _normalize_firecrawl_scrape_format(scrape_format: str) -> str | None:
    """Return a supported Firecrawl scrape format or disable scraping."""
    normalized = scrape_format.strip().lower()
    if normalized in {"markdown", "summary"}:
        return normalized
    if normalized in {"", "none", "off", "false"}:
        return None
    logger.warning(
        "invalid_firecrawl_scrape_format",
        scrape_format=normalized,
        fallback="markdown",
    )
    return "markdown"


def _exa_search_type_from_env() -> str:
    """Return a supported Exa search type from environment config."""
    return _normalize_exa_search_type(os.environ.get("EXA_SEARCH_TYPE", "auto"))


def _normalize_exa_search_type(search_type: str) -> str:
    """Return a supported Exa search type."""
    normalized = search_type.strip().lower()
    if normalized in {"neural", "fast", "auto", "deep", "deep-reasoning", "instant"}:
        return normalized
    logger.warning(
        "invalid_exa_search_type",
        search_type=normalized,
        fallback="auto",
    )
    return "auto"


def _exa_category_from_env() -> str | None:
    """Return a supported Exa category from environment config."""
    return _normalize_exa_category(os.environ.get("EXA_SEARCH_CATEGORY"))


def _normalize_exa_category(category: str | None) -> str | None:
    """Return a supported Exa category."""
    if category is None:
        return None
    normalized = category.strip().lower()
    if normalized == "":
        return None
    allowed_categories = {
        "company",
        "research paper",
        "news",
        "pdf",
        "github",
        "personal site",
        "people",
        "financial report",
    }
    if normalized in allowed_categories:
        return normalized
    logger.warning(
        "invalid_exa_category",
        category=normalized,
        fallback=None,
    )
    return None


def _parallel_mode_from_env() -> str:
    """Return a supported Parallel Search mode from environment config."""
    mode = os.environ.get("PARALLEL_SEARCH_MODE", "advanced").strip().lower()
    if mode in {"basic", "advanced"}:
        return mode
    logger.warning(
        "invalid_parallel_search_mode",
        mode=mode,
        fallback="advanced",
    )
    return "advanced"


def _tavily_search_depth_from_env() -> str:
    """Return a supported Tavily search depth from environment config."""
    return _normalize_tavily_search_depth(os.environ.get("TAVILY_SEARCH_DEPTH", "basic"))


def _normalize_tavily_search_depth(search_depth: str) -> str:
    """Return a supported Tavily search depth."""
    normalized = search_depth.strip().lower()
    if normalized in {"advanced", "basic", "fast", "ultra-fast"}:
        return normalized
    logger.warning(
        "invalid_tavily_search_depth",
        search_depth=normalized,
        fallback="basic",
    )
    return "basic"


def _tavily_topic_from_env() -> str:
    """Return a supported Tavily topic from environment config."""
    return _normalize_tavily_topic(os.environ.get("TAVILY_SEARCH_TOPIC", "general"))


def _normalize_tavily_topic(topic: str) -> str:
    """Return a supported Tavily topic."""
    normalized = topic.strip().lower()
    if normalized in {"general", "news", "finance"}:
        return normalized
    logger.warning(
        "invalid_tavily_search_topic",
        topic=normalized,
        fallback="general",
    )
    return "general"


def _tavily_time_range_from_env() -> str | None:
    """Return a supported Tavily time range from environment config."""
    return _normalize_tavily_time_range(os.environ.get("TAVILY_SEARCH_TIME_RANGE", ""))


def _normalize_tavily_time_range(time_range: str | None) -> str | None:
    """Return a supported Tavily time range."""
    if time_range is None:
        return None
    normalized = time_range.strip().lower()
    if normalized == "":
        return None
    if normalized in {"day", "week", "month", "year", "d", "w", "m", "y"}:
        return normalized
    logger.warning(
        "invalid_tavily_search_time_range",
        time_range=normalized,
        fallback=None,
    )
    return None


def _int_env_or_none(name: str) -> int | None:
    """Parse an optional positive integer env var with fail-closed fallback."""
    raw_value = os.environ.get(name)
    if raw_value is None or raw_value.strip() == "":
        return None
    try:
        parsed = int(raw_value)
    except ValueError:
        logger.warning(
            "invalid_int_env",
            name=name,
            fallback=None,
        )
        return None
    if parsed <= 0:
        logger.warning(
            "invalid_positive_int_env",
            name=name,
            fallback=None,
        )
        return None
    return parsed


def _read_evidence_budget(env_var: str, default: int) -> int:
    """Read a non-negative integer evidence budget from *env_var*.

    Returns *default* when the variable is unset.  Zero, negative, and
    non-numeric values are treated as 0 (no evidence calls) with a warning.
    """
    raw = os.environ.get(env_var, str(default))
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "invalid_evidence_budget_non_numeric",
            env_var=env_var,
            raw=raw,
            fallback=0,
        )
        return 0
    if value < 0:
        logger.warning(
            "invalid_evidence_budget_negative",
            env_var=env_var,
            value=value,
            fallback=0,
        )
        return 0
    return value


def _read_cache_ttl() -> int:
    """Read ``SENTINEL_EVIDENCE_CACHE_TTL`` with validation and default fallback.

    Returns the TTL in seconds (default 300).  Invalid values log a warning and
    fall back to the default.  Non-positive values also fall back to the default.
    """
    raw = os.environ.get("SENTINEL_EVIDENCE_CACHE_TTL", "300")
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "invalid_evidence_cache_ttl_non_numeric",
            raw=raw,
            fallback=300,
        )
        return 300
    if value <= 0:
        logger.warning(
            "invalid_evidence_cache_ttl_non_positive",
            value=value,
            fallback=300,
        )
        return 300
    return value


def _read_cache_maxsize() -> int:
    """Read ``SENTINEL_EVIDENCE_CACHE_MAXSIZE`` with validation and default fallback.

    Returns the max cache entries (default 256).  0 disables caching entirely.
    Negative values log a warning and fall back to the default.
    """
    raw = os.environ.get("SENTINEL_EVIDENCE_CACHE_MAXSIZE", "256")
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "invalid_evidence_cache_maxsize_non_numeric",
            raw=raw,
            fallback=256,
        )
        return 256
    if value < 0:
        logger.warning(
            "invalid_evidence_cache_maxsize_negative",
            value=value,
            fallback=256,
        )
        return 256
    return value


def _float_env(name: str, default: float) -> float:
    """Parse a float environment variable with fail-closed fallback."""
    raw_value = os.environ.get(name)
    if raw_value is None or raw_value.strip() == "":
        return default
    try:
        parsed = float(raw_value)
    except ValueError:
        logger.warning(
            "invalid_float_env",
            name=name,
            fallback=default,
        )
        return default
    if parsed <= 0:
        logger.warning(
            "invalid_positive_float_env",
            name=name,
            fallback=default,
        )
        return default
    return parsed


def _read_circuit_breaker_threshold() -> int:
    """Read ``SENTINEL_EVIDENCE_CB_FAILURE_THRESHOLD`` with validation and default.

    Returns the consecutive failure threshold (default 3).  Non-positive and
    non-numeric values log a warning and fall back to the default.
    """
    raw = os.environ.get("SENTINEL_EVIDENCE_CB_FAILURE_THRESHOLD", "3")
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "invalid_cb_failure_threshold_non_numeric",
            raw=raw,
            fallback=3,
        )
        return 3
    if value <= 0:
        logger.warning(
            "invalid_cb_failure_threshold_non_positive",
            value=value,
            fallback=3,
        )
        return 3
    return value


def _read_circuit_breaker_cooldown() -> float:
    """Read ``SENTINEL_EVIDENCE_CB_COOLDOWN_SECONDS`` with validation and default.

    Returns the cooldown in seconds (default 60).  Non-positive and non-numeric
    values log a warning and fall back to the default.
    """
    raw = os.environ.get("SENTINEL_EVIDENCE_CB_COOLDOWN_SECONDS", "60")
    try:
        value = float(raw)
    except ValueError:
        logger.warning(
            "invalid_cb_cooldown_non_numeric",
            raw=raw,
            fallback=60.0,
        )
        return 60.0
    if value <= 0:
        logger.warning(
            "invalid_cb_cooldown_non_positive",
            value=value,
            fallback=60.0,
        )
        return 60.0
    return value


def _response_json_or_none(
    response: httpx.Response,
    *,
    provider: str,
    challenge_id: str,
) -> Any | None:
    """Return JSON response bodies or fail closed to no evidence."""
    try:
        return response.json()
    except ValueError as exc:
        logger.warning(
            "evidence_provider_invalid_json",
            provider=provider,
            challenge_id=challenge_id,
            error=str(exc),
        )
        return None


def _mcp_tool_arguments(mapper_name: str, request: EvidenceSearchRequest) -> dict[str, Any]:
    """Build MCP tool arguments using an explicit input mapper."""
    normalized_name = mapper_name.strip().lower()
    mapper = _EVIDENCE_INPUT_MAPPERS.get(normalized_name)
    if mapper is None:
        logger.warning(
            "unknown_evidence_input_mapper",
            input_mapper=normalized_name,
        )
        return {}
    return mapper(request)


def _input_query(request: EvidenceSearchRequest) -> dict[str, Any]:
    """Map to the most common MCP search-tool shape."""
    return {"query": request.query}


def _input_query_limit(request: EvidenceSearchRequest) -> dict[str, Any]:
    """Map to Firecrawl-style search-tool args."""
    return {"query": request.query, "limit": request.max_results}


def _input_query_max_results(request: EvidenceSearchRequest) -> dict[str, Any]:
    """Map to agent-search tools that use max_results."""
    return {"query": request.query, "max_results": request.max_results}


def _input_q_count(request: EvidenceSearchRequest) -> dict[str, Any]:
    """Map to web-search tools that use q/count names."""
    return {"q": request.query, "count": request.max_results}


def _input_prism_evidence_request(request: EvidenceSearchRequest) -> dict[str, Any]:
    """Map to Prism's full provider-neutral evidence request shape."""
    return {
        "query": request.query,
        "max_results": request.max_results,
        "market_question": request.market_question,
        "challenge": request.challenge.model_dump(mode="json"),
    }


_EVIDENCE_INPUT_MAPPERS: dict[str, EvidenceInputMapper] = {
    "query": _input_query,
    "query_limit": _input_query_limit,
    "query_max_results": _input_query_max_results,
    "q_count": _input_q_count,
    "prism_evidence_request": _input_prism_evidence_request,
}


def _is_known_evidence_input_mapper(mapper_name: str) -> bool:
    """Return whether an MCP input mapper is configured."""
    return mapper_name.strip().lower() in _EVIDENCE_INPUT_MAPPERS


def available_evidence_input_mappers() -> list[str]:
    """Return the configured MCP evidence input mapper names."""
    return sorted(_EVIDENCE_INPUT_MAPPERS)


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


def _parse_webhook_results(
    body: Any,
    *,
    fallback_provider: str,
) -> list[EvidenceSearchResult]:
    """Parse flexible webhook response shapes into normalized results."""
    raw_results: Any
    if isinstance(body, list):
        raw_results = body
    elif isinstance(body, dict):
        raw_results = body.get("results")
        if raw_results is None and isinstance(body.get("data"), dict):
            raw_results = body["data"].get("results")
    else:
        raw_results = None

    if not isinstance(raw_results, list):
        return []

    results: list[EvidenceSearchResult] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        candidate = dict(item)
        candidate.setdefault("provider", fallback_provider)
        try:
            parsed = EvidenceSearchResult.model_validate(candidate)
        except ValidationError:
            continue
        results.append(parsed)
    return results


def _parse_firecrawl_results(body: Any) -> list[EvidenceSearchResult]:
    """Normalize Firecrawl Search results into evidence results."""
    if not isinstance(body, dict):
        return []
    raw_results = _firecrawl_raw_results(body)
    if not isinstance(raw_results, list):
        return []

    results: list[EvidenceSearchResult] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str):
            continue
        snippet = _firecrawl_snippet(item)
        if snippet is None:
            continue
        title = item.get("title")
        published_at = _firecrawl_published_at(item)
        results.append(
            EvidenceSearchResult(
                title=title if isinstance(title, str) and title else url,
                url=url,
                snippet=snippet,
                provider="firecrawl_search",
                published_at=published_at,
                confidence=0.76,
            )
        )
    return results


def _firecrawl_raw_results(body: dict[str, Any]) -> Any:
    """Return the likely result list from Firecrawl's flexible response shape."""
    data = body.get("data")
    if not isinstance(data, dict):
        return None
    web_results = data.get("web")
    if isinstance(web_results, list):
        return web_results
    return None


def _firecrawl_snippet(item: dict[str, Any]) -> str | None:
    """Choose the best Firecrawl content field for a compact evidence snippet."""
    for key in ("summary", "markdown", "description", "content"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value[:1600]
    return None


def _firecrawl_published_at(item: dict[str, Any]) -> str | None:
    """Extract a publication timestamp from Firecrawl result metadata if present."""
    for key in ("publishedAt", "published_at", "date"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    metadata = item.get("metadata")
    if not isinstance(metadata, dict):
        return None
    for key in ("publishedAt", "published_at", "publishedDate", "date"):
        value = metadata.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _parse_exa_results(body: Any) -> list[EvidenceSearchResult]:
    """Normalize Exa Search results into evidence results."""
    if not isinstance(body, dict):
        return []
    raw_results = body.get("results")
    if not isinstance(raw_results, list):
        return []

    results: list[EvidenceSearchResult] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str):
            continue
        snippet = _exa_snippet(item)
        if snippet is None:
            continue
        title = item.get("title")
        published_date = item.get("publishedDate")
        score = item.get("score")
        results.append(
            EvidenceSearchResult(
                title=title if isinstance(title, str) and title else url,
                url=url,
                snippet=snippet,
                provider="exa_search",
                published_at=published_date if isinstance(published_date, str) else None,
                confidence=_confidence_from_score(score, fallback=0.74),
            )
        )
    return results


def _exa_snippet(item: dict[str, Any]) -> str | None:
    """Choose the best Exa content field for a compact evidence snippet."""
    summary = item.get("summary")
    if isinstance(summary, str) and summary:
        return summary
    highlights = item.get("highlights")
    if isinstance(highlights, list):
        cleaned = [
            highlight for highlight in highlights if isinstance(highlight, str) and highlight
        ]
        if cleaned:
            return "\n\n".join(cleaned[:2])
    text = item.get("text")
    if isinstance(text, str) and text:
        return text[:1200]
    return None


def _parallel_objective(request: EvidenceSearchRequest) -> str:
    """Build a focused Parallel Search objective for one open challenge."""
    return (
        "Resolve this Prism adversarial validation issue with current, source-linked evidence. "
        f"Market: {request.market_question}. "
        f"Issue: {request.challenge.question}. "
        f"Required resolution: {request.challenge.required_resolution}."
    )


def _parse_parallel_results(body: Any) -> list[EvidenceSearchResult]:
    """Normalize Parallel Search results into evidence results."""
    if not isinstance(body, dict):
        return []
    raw_results = body.get("results")
    if not isinstance(raw_results, list):
        return []

    results: list[EvidenceSearchResult] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str):
            continue
        raw_excerpts = item.get("excerpts")
        if not isinstance(raw_excerpts, list):
            continue
        excerpts = [excerpt for excerpt in raw_excerpts if isinstance(excerpt, str) and excerpt]
        if not excerpts:
            continue
        title = item.get("title")
        publish_date = item.get("publish_date")
        results.append(
            EvidenceSearchResult(
                title=title if isinstance(title, str) and title else url,
                url=url,
                snippet="\n\n".join(excerpts[:2]),
                provider="parallel_search",
                published_at=publish_date if isinstance(publish_date, str) else None,
                confidence=0.78,
            )
        )
    return results


def _parse_tavily_results(body: Any) -> list[EvidenceSearchResult]:
    """Normalize Tavily Search results into evidence results."""
    if not isinstance(body, dict):
        return []
    raw_results = body.get("results")
    if not isinstance(raw_results, list):
        return []

    results: list[EvidenceSearchResult] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        url = item.get("url")
        content = item.get("content") or item.get("raw_content")
        if not isinstance(url, str) or not isinstance(content, str):
            continue
        score = item.get("score")
        published_date = item.get("published_date") or item.get("publish_date")
        results.append(
            EvidenceSearchResult(
                title=title if isinstance(title, str) and title else url,
                url=url,
                snippet=content,
                provider="tavily_search",
                published_at=published_date if isinstance(published_date, str) else None,
                confidence=_confidence_from_score(score, fallback=0.72),
            )
        )
    return results


def _confidence_from_score(value: Any, *, fallback: float) -> float:
    """Clamp provider relevance scores into Prism's confidence range."""
    if isinstance(value, int | float) and not isinstance(value, bool):
        return max(0.0, min(1.0, float(value)))
    return fallback


def _parse_brave_results(body: Any) -> list[EvidenceSearchResult]:
    """Normalize Brave web-search results into evidence results."""
    if not isinstance(body, dict):
        return []
    web = body.get("web")
    if not isinstance(web, dict):
        return []
    raw_results = web.get("results")
    if not isinstance(raw_results, list):
        return []

    results: list[EvidenceSearchResult] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        url = item.get("url")
        snippet = item.get("description") or item.get("snippet")
        if not isinstance(title, str) or not isinstance(url, str) or not isinstance(snippet, str):
            continue
        page_age = item.get("page_age")
        page_fetched = item.get("page_fetched")
        results.append(
            EvidenceSearchResult(
                title=title,
                url=url,
                snippet=snippet,
                provider="brave_search",
                published_at=page_age if isinstance(page_age, str) else None,
                retrieved_at=page_fetched if isinstance(page_fetched, str) else None,
                confidence=0.7,
            )
        )
    return results


def _parse_generic_search_results(body: Any) -> list[EvidenceSearchResult]:
    """Normalize Prism/generic search tool output into evidence results."""
    return _parse_webhook_results(body, fallback_provider="generic_search")


def _parse_exa_mcp_text_results(body: Any) -> list[EvidenceSearchResult]:
    """Normalize Exa hosted MCP text blocks into evidence results."""
    text = body.get("text") if isinstance(body, dict) else body
    if not isinstance(text, str) or not text.strip():
        return []

    results: list[EvidenceSearchResult] = []
    for block in re.split(r"(?m)^Title:\s*", text):
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        title = lines[0].strip() if lines else ""
        url = _exa_mcp_line_value(block, "URL")
        if not title or url is None:
            continue
        published_at = _exa_mcp_line_value(block, "Published")
        if published_at == "N/A":
            published_at = None
        snippet = _exa_mcp_highlights(block) or title
        results.append(
            EvidenceSearchResult(
                title=title,
                url=url,
                snippet=snippet[:1600],
                provider="exa_mcp",
                published_at=published_at,
                confidence=0.76,
            )
        )
    return results


def _exa_mcp_line_value(block: str, label: str) -> str | None:
    """Extract a single `Label: value` line from Exa MCP text output."""
    prefix = f"{label}:"
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            value = stripped.removeprefix(prefix).strip()
            return value or None
    return None


def _exa_mcp_highlights(block: str) -> str | None:
    """Extract compact highlight text from one Exa MCP result block."""
    marker = "Highlights:"
    if marker not in block:
        return None
    raw = block.split(marker, 1)[1]
    lines = [line.strip() for line in raw.splitlines() if line.strip() and line.strip() != "[...]"]
    return "\n".join(lines) or None


_EVIDENCE_RESULT_MAPPERS: dict[str, EvidenceResultMapper] = {
    "generic_search": _parse_generic_search_results,
    "custom_webhook": lambda body: _parse_webhook_results(
        body,
        fallback_provider="custom_webhook",
    ),
    "firecrawl_search": _parse_firecrawl_results,
    "exa_search": _parse_exa_results,
    "exa_mcp_text": _parse_exa_mcp_text_results,
    "parallel_search": _parse_parallel_results,
    "tavily_search": _parse_tavily_results,
    "brave_search": _parse_brave_results,
}


def _is_known_evidence_result_mapper(mapper_name: str) -> bool:
    """Return whether an evidence result mapper is configured."""
    return mapper_name.strip().lower() in _EVIDENCE_RESULT_MAPPERS


def map_evidence_results(mapper_name: str, body: Any) -> list[EvidenceSearchResult]:
    """Map raw tool/provider output into normalized evidence results."""
    normalized_name = mapper_name.strip().lower()
    mapper = _EVIDENCE_RESULT_MAPPERS.get(normalized_name)
    if mapper is None:
        logger.warning(
            "unknown_evidence_result_mapper",
            mapper=normalized_name,
        )
        return []
    return mapper(body)


def available_evidence_result_mappers() -> list[str]:
    """Return the configured evidence result mapper names."""
    return sorted(_EVIDENCE_RESULT_MAPPERS)


def query_for_challenge(market_question: str, challenge: AdversarialChallenge) -> str:
    """Build a targeted search query for a challenge."""
    if challenge.type == "temporal":
        return f"{market_question} latest current evidence status date"
    if challenge.type == "market_structure":
        return f"{market_question} Polymarket end date resolved active"
    if challenge.type == "source_quality":
        return f"{market_question} primary source official data"
    if challenge.type == "calibration":
        return f"{market_question} odds probability market price latest"
    return f"{market_question} {challenge.question}"
