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
    """
    provider = os.environ.get("PRISM_EVIDENCE_PROVIDER", "noop").strip().lower()
    if provider == "noop":
        return NoopEvidenceProvider()
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


def _float_env(name: str, default: float) -> float:
    """Parse a float environment variable with fail-closed fallback."""
    raw_value = os.environ.get(name)
    if raw_value is None or raw_value.strip() == "":
        return default
    try:
        return float(raw_value)
    except ValueError:
        logger.warning(
            "invalid_float_env",
            name=name,
            fallback=default,
        )
        return default


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
