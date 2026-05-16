"""Evidence retrieval abstraction for adversarial resolution.

This intentionally starts small: the resolution loop depends on a provider
interface, not on any one vendor. Future adapters can wrap Parallel x402,
Brave, Tavily, Exa, Firecrawl, or domain APIs while returning the same
provider-neutral result shape.
"""

from __future__ import annotations

import os
from typing import Any, Protocol

import httpx
import structlog
from prism_schemas.verdict import AdversarialChallenge
from pydantic import BaseModel, Field, ValidationError

logger = structlog.get_logger("prism.sentinel.evidence_tools")


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
    published_at: str | None = None
    retrieved_at: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class EvidenceProvider(Protocol):
    """Provider interface used by the resolution loop."""

    async def search(self, request: EvidenceSearchRequest) -> list[EvidenceSearchResult]:
        """Return evidence candidates for the targeted request."""


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
        return _parse_firecrawl_results(body)


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
        return _parse_exa_results(body)


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
        return _parse_parallel_results(body)


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
        return _parse_brave_results(body)


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
        return _parse_tavily_results(body)


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
                url=self.url,
                challenge_id=request.challenge.id,
                error=str(exc),
            )
            return []

        body = _response_json_or_none(
            response,
            provider="custom_webhook",
            challenge_id=request.challenge.id,
        )
        if body is None:
            return []
        return _parse_webhook_results(body, fallback_provider="custom_webhook")


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


def _env_optional_string(name: str) -> str | None:
    """Return a stripped environment value, treating blanks as unset."""
    return _optional_string(os.environ.get(name))


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
