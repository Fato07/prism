"""Evidence retrieval abstraction for adversarial resolution.

This intentionally starts small: the resolution loop depends on a provider
interface, not on any one vendor. Future adapters can wrap Parallel x402,
Brave, Tavily, Exa, Firecrawl, or domain APIs while returning the same
provider-neutral result shape.
"""

from __future__ import annotations

import os
from typing import Protocol

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


def evidence_provider_from_env() -> EvidenceProvider:
    """Return the configured evidence provider.

    `noop` is the only implemented provider in this patch. The env switch is
    deliberately present so future adapter work can be additive and easy to
    smoke-test in Railway.
    """
    provider = os.environ.get("PRISM_EVIDENCE_PROVIDER", "noop").strip().lower()
    if provider != "noop":
        logger.warning(
            "evidence_provider_not_implemented",
            provider=provider,
            fallback="noop",
        )
    return NoopEvidenceProvider()


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
