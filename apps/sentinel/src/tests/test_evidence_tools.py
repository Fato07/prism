"""Evidence provider adapter tests."""

from __future__ import annotations

import json

import httpx
import pytest
from prism_schemas.verdict import AdversarialChallenge

from sentinel.evidence_tools import (
    BraveSearchEvidenceProvider,
    CustomWebhookEvidenceProvider,
    EvidenceSearchRequest,
    NoopEvidenceProvider,
    ParallelSearchEvidenceProvider,
    evidence_provider_from_env,
    query_for_challenge,
)


def _challenge() -> AdversarialChallenge:
    return AdversarialChallenge(
        id="sys-temporal-stale-evidence",
        type="temporal",
        severity="blocking",
        question="Evidence is stale.",
        required_resolution="Retrieve current evidence or revise to HOLD.",
        blocking_pass=True,
        claim_ref="evidence[0]",
    )


def _request() -> EvidenceSearchRequest:
    challenge = _challenge()
    market_question = "Will LeBron break the scoring record during the Feb 7 game vs. OKC?"
    return EvidenceSearchRequest(
        market_question=market_question,
        challenge=challenge,
        query=query_for_challenge(market_question, challenge),
    )


@pytest.mark.asyncio
async def test_parallel_search_provider_posts_objective_and_parses_excerpts() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["api_key"] = request.headers.get("x-api-key")
        body = request.read().decode()
        captured["body"] = body
        return httpx.Response(
            200,
            json={
                "search_id": "search_test",
                "session_id": "session_test",
                "results": [
                    {
                        "url": "https://example.com/parallel-current",
                        "title": "Parallel current evidence",
                        "publish_date": "2026-05-16",
                        "excerpts": ["Current source excerpt.", "Second relevant excerpt."],
                    }
                ],
            },
        )

    provider = ParallelSearchEvidenceProvider(
        api_key="parallel-key",
        location="us",
        max_chars_total=4000,
        transport=httpx.MockTransport(handler),
    )

    results = await provider.search(_request())

    assert captured["api_key"] == "parallel-key"
    request_body = json.loads(str(captured["body"]))
    assert request_body["objective"].startswith(
        "Resolve this Prism adversarial validation issue"
    )
    assert request_body["search_queries"] == [_request().query]
    assert request_body["mode"] == "advanced"
    assert request_body["advanced_settings"] == {"max_results": 5, "location": "us"}
    assert request_body["max_chars_total"] == 4000
    assert len(results) == 1
    assert results[0].provider == "parallel_search"
    assert results[0].snippet == "Current source excerpt.\n\nSecond relevant excerpt."
    assert results[0].published_at == "2026-05-16"


@pytest.mark.asyncio
async def test_parallel_search_provider_returns_empty_on_invalid_json() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    provider = ParallelSearchEvidenceProvider(
        api_key="parallel-key",
        transport=httpx.MockTransport(handler),
    )

    assert await provider.search(_request()) == []


@pytest.mark.asyncio
async def test_parallel_search_provider_returns_empty_on_http_failure() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"error": "bad request"})

    provider = ParallelSearchEvidenceProvider(
        api_key="parallel-key",
        transport=httpx.MockTransport(handler),
    )

    assert await provider.search(_request()) == []


@pytest.mark.asyncio
async def test_brave_search_provider_gets_web_results() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["token"] = request.headers.get("x-subscription-token")
        captured["query"] = request.url.params.get("q")
        captured["count"] = request.url.params.get("count")
        captured["country"] = request.url.params.get("country")
        return httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        {
                            "title": "LeBron current game status",
                            "url": "https://example.com/lebron-current",
                            "description": "A current source resolves the stale evidence issue.",
                            "page_age": "2026-05-16T00:00:00Z",
                            "page_fetched": "2026-05-16T12:00:00Z",
                        }
                    ]
                }
            },
        )

    provider = BraveSearchEvidenceProvider(
        api_key="brave-key",
        country="US",
        transport=httpx.MockTransport(handler),
    )

    results = await provider.search(_request())

    assert captured["token"] == "brave-key"
    assert "LeBron" in str(captured["query"])
    assert captured["count"] == "5"
    assert captured["country"] == "US"
    assert len(results) == 1
    assert results[0].provider == "brave_search"
    assert results[0].snippet == "A current source resolves the stale evidence issue."
    assert results[0].published_at == "2026-05-16T00:00:00Z"


@pytest.mark.asyncio
async def test_brave_search_provider_returns_empty_on_http_failure() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate_limited"})

    provider = BraveSearchEvidenceProvider(
        api_key="brave-key",
        transport=httpx.MockTransport(handler),
    )

    assert await provider.search(_request()) == []


@pytest.mark.asyncio
async def test_brave_search_provider_returns_empty_on_invalid_json() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    provider = BraveSearchEvidenceProvider(
        api_key="brave-key",
        transport=httpx.MockTransport(handler),
    )

    assert await provider.search(_request()) == []


@pytest.mark.asyncio
async def test_custom_webhook_provider_posts_normalized_request_and_parses_results() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = request.read().decode()
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Current NBA report",
                        "url": "https://example.com/current-nba-report",
                        "snippet": "Current context resolves the stale evidence issue.",
                        "published_at": "2026-05-16T00:00:00Z",
                        "confidence": 0.91,
                    }
                ]
            },
        )

    provider = CustomWebhookEvidenceProvider(
        url="https://evidence.example/search",
        bearer_token="test-token",
        transport=httpx.MockTransport(handler),
    )

    results = await provider.search(_request())

    assert captured["authorization"] == "Bearer test-token"
    assert "sys-temporal-stale-evidence" in str(captured["body"])
    assert len(results) == 1
    assert results[0].provider == "custom_webhook"
    assert results[0].url == "https://example.com/current-nba-report"
    assert results[0].confidence == 0.91


@pytest.mark.asyncio
async def test_custom_webhook_provider_returns_empty_on_http_failure() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "down"})

    provider = CustomWebhookEvidenceProvider(
        url="https://evidence.example/search",
        transport=httpx.MockTransport(handler),
    )

    assert await provider.search(_request()) == []


def test_evidence_provider_from_env_uses_parallel_search(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRISM_EVIDENCE_PROVIDER", "parallel_search")
    monkeypatch.setenv("PARALLEL_API_KEY", "parallel-key")
    monkeypatch.setenv("PARALLEL_SEARCH_MODE", "basic")
    monkeypatch.setenv("PARALLEL_SEARCH_LOCATION", "us")
    monkeypatch.setenv("PARALLEL_SEARCH_MAX_CHARS_TOTAL", "6000")
    monkeypatch.setenv("PARALLEL_SEARCH_TIMEOUT_SECONDS", "bad-value")

    provider = evidence_provider_from_env()

    assert isinstance(provider, ParallelSearchEvidenceProvider)
    assert provider.api_key == "parallel-key"
    assert provider.mode == "basic"
    assert provider.location == "us"
    assert provider.max_chars_total == 6000
    assert provider.timeout_seconds == 30.0


def test_evidence_provider_from_env_falls_back_to_parallel_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRISM_EVIDENCE_PROVIDER", "parallel_search")
    monkeypatch.setenv("PARALLEL_API_KEY", "parallel-key")
    monkeypatch.setenv("PARALLEL_SEARCH_MODE", "invalid")
    monkeypatch.setenv("PARALLEL_SEARCH_MAX_CHARS_TOTAL", "-1")
    monkeypatch.setenv("PARALLEL_SEARCH_TIMEOUT_SECONDS", "0")

    provider = evidence_provider_from_env()

    assert isinstance(provider, ParallelSearchEvidenceProvider)
    assert provider.mode == "advanced"
    assert provider.max_chars_total is None
    assert provider.timeout_seconds == 30.0


def test_evidence_provider_from_env_falls_back_to_noop_without_parallel_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRISM_EVIDENCE_PROVIDER", "parallel_search")
    monkeypatch.delenv("PARALLEL_API_KEY", raising=False)

    assert isinstance(evidence_provider_from_env(), NoopEvidenceProvider)


def test_evidence_provider_from_env_uses_brave_search(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRISM_EVIDENCE_PROVIDER", "brave_search")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "brave-key")
    monkeypatch.setenv("BRAVE_SEARCH_COUNTRY", "US")
    monkeypatch.setenv("BRAVE_SEARCH_LANG", "en")
    monkeypatch.setenv("BRAVE_SEARCH_FRESHNESS", "pm")
    monkeypatch.setenv("BRAVE_SEARCH_TIMEOUT_SECONDS", "bad-value")

    provider = evidence_provider_from_env()

    assert isinstance(provider, BraveSearchEvidenceProvider)
    assert provider.api_key == "brave-key"
    assert provider.country == "US"
    assert provider.search_lang == "en"
    assert provider.freshness == "pm"
    assert provider.timeout_seconds == 20.0


def test_evidence_provider_from_env_falls_back_to_noop_without_brave_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRISM_EVIDENCE_PROVIDER", "brave_search")
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)

    assert isinstance(evidence_provider_from_env(), NoopEvidenceProvider)


def test_evidence_provider_from_env_uses_custom_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRISM_EVIDENCE_PROVIDER", "custom_webhook")
    monkeypatch.setenv("PRISM_EVIDENCE_WEBHOOK_URL", "https://evidence.example/search")
    monkeypatch.setenv("PRISM_EVIDENCE_WEBHOOK_BEARER_TOKEN", "secret")

    provider = evidence_provider_from_env()

    assert isinstance(provider, CustomWebhookEvidenceProvider)
    assert provider.url == "https://evidence.example/search"
    assert provider.bearer_token == "secret"


def test_evidence_provider_from_env_falls_back_to_noop_without_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRISM_EVIDENCE_PROVIDER", "custom_webhook")
    monkeypatch.delenv("PRISM_EVIDENCE_WEBHOOK_URL", raising=False)

    assert isinstance(evidence_provider_from_env(), NoopEvidenceProvider)
