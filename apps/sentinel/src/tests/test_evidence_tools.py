"""Evidence provider adapter tests."""

from __future__ import annotations

import httpx
import pytest
from prism_schemas.verdict import AdversarialChallenge

from sentinel.evidence_tools import (
    CustomWebhookEvidenceProvider,
    EvidenceSearchRequest,
    NoopEvidenceProvider,
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
