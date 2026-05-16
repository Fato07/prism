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
from pydantic import BaseModel, Field

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

        return _parse_webhook_results(response.json(), fallback_provider="custom_webhook")


def evidence_provider_from_env() -> EvidenceProvider:
    """Return the configured evidence provider.

    Supported values:
    - `noop` (default): no network or paid calls.
    - `custom_webhook`: POST requests to `PRISM_EVIDENCE_WEBHOOK_URL`.
    """
    provider = os.environ.get("PRISM_EVIDENCE_PROVIDER", "noop").strip().lower()
    if provider == "noop":
        return NoopEvidenceProvider()
    if provider == "custom_webhook":
        url = os.environ.get("PRISM_EVIDENCE_WEBHOOK_URL", "").strip()
        if not url:
            logger.warning(
                "custom_evidence_webhook_missing_url",
                fallback="noop",
            )
            return NoopEvidenceProvider()
        timeout_seconds = float(os.environ.get("PRISM_EVIDENCE_WEBHOOK_TIMEOUT_SECONDS", "20"))
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
        parsed = EvidenceSearchResult.model_validate(candidate)
        results.append(parsed)
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
