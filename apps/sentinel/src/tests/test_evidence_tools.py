"""Evidence provider adapter tests."""

from __future__ import annotations

import json

import httpx
import pytest
from fastmcp import FastMCP
from prism_schemas.verdict import AdversarialChallenge

from sentinel.evidence_tools import (
    BraveSearchEvidenceProvider,
    CustomWebhookEvidenceProvider,
    EvidenceConnectorConfig,
    EvidenceSearchRequest,
    ExaSearchEvidenceProvider,
    FirecrawlSearchEvidenceProvider,
    McpEvidenceProvider,
    NoopEvidenceProvider,
    ParallelSearchEvidenceProvider,
    TavilySearchEvidenceProvider,
    ToolConnectorManifest,
    available_evidence_input_mappers,
    available_evidence_result_mappers,
    evidence_provider_from_env,
    map_evidence_results,
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


def test_tool_connector_manifest_accepts_mcp_evidence_config() -> None:
    manifest = ToolConnectorManifest(
        evidence=[
            EvidenceConnectorConfig(
                id="firecrawl-mcp",
                transport="mcp_http",
                server_url_env="FIRECRAWL_MCP_URL",
                tool_name="search",
                result_mapper="firecrawl_search",
                input_mapper="query_limit",
                auth_token_env="FIRECRAWL_MCP_TOKEN",
                allowed_tools=["search"],
                timeout_seconds=15,
                max_results=3,
            )
        ]
    )

    connector = manifest.evidence[0]
    assert connector.transport == "mcp_http"
    assert connector.tool_name == "search"
    assert connector.result_mapper == "firecrawl_search"
    assert connector.input_mapper == "query_limit"
    assert connector.allowed_tools == ["search"]


def test_evidence_result_mapper_registry_maps_generic_and_provider_shapes() -> None:
    assert "generic_search" in available_evidence_result_mappers()
    assert "firecrawl_search" in available_evidence_result_mappers()
    assert "query" in available_evidence_input_mappers()
    assert "query_limit" in available_evidence_input_mappers()

    generic_results = map_evidence_results(
        "generic_search",
        {
            "results": [
                {
                    "title": "Generic source",
                    "url": "https://example.com/generic",
                    "snippet": "Generic MCP tool output.",
                }
            ]
        },
    )
    firecrawl_results = map_evidence_results(
        "firecrawl_search",
        {
            "success": True,
            "data": {
                "web": [
                    {
                        "title": "Firecrawl source",
                        "url": "https://example.com/firecrawl",
                        "markdown": "Firecrawl mapped output.",
                    }
                ]
            },
        },
    )

    assert generic_results[0].provider == "generic_search"
    assert firecrawl_results[0].provider == "firecrawl_search"
    assert map_evidence_results("missing_mapper", {"results": []}) == []


@pytest.mark.asyncio
async def test_mcp_evidence_provider_calls_tool_and_maps_generic_results() -> None:
    server = FastMCP("evidence-test")

    @server.tool
    def search(
        query: str,
        max_results: int,
        market_question: str,
        challenge: dict[str, object],
    ) -> dict[str, object]:
        assert "LeBron" in query
        assert max_results == 5
        assert "LeBron" in market_question
        assert challenge["id"] == "sys-temporal-stale-evidence"
        return {
            "results": [
                {
                    "title": "MCP current source",
                    "url": "https://example.com/mcp-current",
                    "snippet": "MCP tool returned current evidence.",
                    "confidence": 0.88,
                }
            ]
        }

    provider = McpEvidenceProvider(
        tool_name="search",
        result_mapper="generic_search",
        input_mapper="prism_evidence_request",
        transport=server,
    )

    results = await provider.search(_request())

    assert len(results) == 1
    assert results[0].provider == "generic_search"
    assert results[0].url == "https://example.com/mcp-current"
    assert results[0].confidence == 0.88


@pytest.mark.asyncio
async def test_mcp_evidence_provider_supports_query_only_tools() -> None:
    server = FastMCP("evidence-test")

    @server.tool
    def search(query: str) -> dict[str, object]:
        return {
            "results": [
                {
                    "title": query,
                    "url": "https://example.com/query-only",
                    "snippet": "Query-only MCP tools remain compatible.",
                }
            ]
        }

    provider = McpEvidenceProvider(
        tool_name="search",
        result_mapper="generic_search",
        input_mapper="query",
        transport=server,
    )

    results = await provider.search(_request())

    assert results[0].url == "https://example.com/query-only"


@pytest.mark.asyncio
async def test_mcp_evidence_provider_supports_query_limit_tools() -> None:
    server = FastMCP("evidence-test")

    @server.tool
    def search(query: str, limit: int) -> dict[str, object]:
        return {
            "results": [
                {
                    "title": f"{query} {limit}",
                    "url": "https://example.com/query-limit",
                    "snippet": "Query-limit MCP tools remain compatible.",
                }
            ]
        }

    provider = McpEvidenceProvider(
        tool_name="search",
        result_mapper="generic_search",
        input_mapper="query_limit",
        transport=server,
    )

    results = await provider.search(_request())

    assert "5" in results[0].title
    assert results[0].url == "https://example.com/query-limit"


@pytest.mark.asyncio
async def test_mcp_evidence_provider_fails_closed_on_tool_error() -> None:
    server = FastMCP("evidence-test")

    @server.tool
    def broken(query: str) -> dict[str, object]:
        raise RuntimeError(f"boom for {query}")

    provider = McpEvidenceProvider(
        tool_name="broken",
        result_mapper="generic_search",
        input_mapper="query",
        transport=server,
    )

    assert await provider.search(_request()) == []


@pytest.mark.asyncio
async def test_mcp_evidence_provider_fails_closed_on_malformed_output() -> None:
    server = FastMCP("evidence-test")

    @server.tool
    def malformed(query: str) -> dict[str, object]:
        return {"items": [{"text": query}]}

    provider = McpEvidenceProvider(
        tool_name="malformed",
        result_mapper="generic_search",
        input_mapper="query",
        transport=server,
    )

    assert await provider.search(_request()) == []


@pytest.mark.asyncio
async def test_mcp_evidence_provider_enforces_allowlist() -> None:
    server = FastMCP("evidence-test")

    @server.tool
    def search(query: str) -> dict[str, object]:
        return {"results": [{"title": query, "url": "https://example.com", "snippet": query}]}

    provider = McpEvidenceProvider(
        tool_name="search",
        result_mapper="generic_search",
        input_mapper="query",
        allowed_tools=["other_tool"],
        transport=server,
    )

    assert await provider.search(_request()) == []


@pytest.mark.asyncio
async def test_firecrawl_search_provider_posts_query_and_parses_markdown() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("authorization")
        body = request.read().decode()
        captured["body"] = body
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "web": [
                        {
                            "url": "https://example.com/firecrawl-current",
                            "title": "Firecrawl current evidence",
                            "description": "Fallback description.",
                            "markdown": "# Current Firecrawl evidence",
                            "metadata": {"publishedDate": "2026-05-16T00:00:00Z"},
                        }
                    ]
                },
                "creditsUsed": 1,
            },
        )

    provider = FirecrawlSearchEvidenceProvider(
        api_key="firecrawl-key",
        country="US",
        location="San Francisco,California,United States",
        tbs="qdr:w",
        category="research",
        scrape_format="markdown",
        transport=httpx.MockTransport(handler),
    )

    results = await provider.search(_request())

    assert captured["authorization"] == "Bearer firecrawl-key"
    request_body = json.loads(str(captured["body"]))
    assert request_body["query"] == _request().query
    assert request_body["limit"] == 5
    assert request_body["sources"] == ["web"]
    assert request_body["country"] == "US"
    assert request_body["location"] == "San Francisco,California,United States"
    assert request_body["tbs"] == "qdr:w"
    assert request_body["categories"] == [{"type": "research"}]
    assert request_body["scrapeOptions"] == {"formats": [{"type": "markdown"}]}
    assert len(results) == 1
    assert results[0].provider == "firecrawl_search"
    assert results[0].snippet == "# Current Firecrawl evidence"
    assert results[0].published_at == "2026-05-16T00:00:00Z"


@pytest.mark.asyncio
async def test_firecrawl_search_provider_disables_scrape_and_falls_back() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read().decode())
        assert "scrapeOptions" not in body
        assert "categories" not in body
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "web": [
                        {
                            "url": "https://example.com/firecrawl-description",
                            "description": "Description-only result is still useful.",
                        }
                    ]
                },
            },
        )

    provider = FirecrawlSearchEvidenceProvider(
        api_key="firecrawl-key",
        category="bad-category",
        scrape_format="none",
        transport=httpx.MockTransport(handler),
    )

    results = await provider.search(_request())

    assert provider.category is None
    assert provider.scrape_format is None
    assert results[0].title == "https://example.com/firecrawl-description"
    assert results[0].snippet == "Description-only result is still useful."


@pytest.mark.asyncio
async def test_firecrawl_search_provider_requests_summary_format() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read().decode()
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "web": [
                        {
                            "url": "https://example.com/firecrawl-summary",
                            "title": "Summary result",
                            "summary": "Summary-format result is compact evidence.",
                        }
                    ]
                },
            },
        )

    provider = FirecrawlSearchEvidenceProvider(
        api_key="firecrawl-key",
        country="   ",
        location="  ",
        tbs="  ",
        scrape_format="summary",
        transport=httpx.MockTransport(handler),
    )

    results = await provider.search(_request())

    request_body = json.loads(str(captured["body"]))
    assert "country" not in request_body
    assert "location" not in request_body
    assert "tbs" not in request_body
    assert request_body["scrapeOptions"] == {"formats": [{"type": "summary"}]}
    assert results[0].snippet == "Summary-format result is compact evidence."


@pytest.mark.asyncio
async def test_firecrawl_search_provider_returns_empty_on_invalid_json() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    provider = FirecrawlSearchEvidenceProvider(
        api_key="firecrawl-key",
        transport=httpx.MockTransport(handler),
    )

    assert await provider.search(_request()) == []


@pytest.mark.asyncio
async def test_firecrawl_search_provider_returns_empty_on_http_failure() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    provider = FirecrawlSearchEvidenceProvider(
        api_key="firecrawl-key",
        transport=httpx.MockTransport(handler),
    )

    assert await provider.search(_request()) == []


@pytest.mark.asyncio
async def test_exa_search_provider_posts_query_and_parses_highlights() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["api_key"] = request.headers.get("x-api-key")
        body = request.read().decode()
        captured["body"] = body
        return httpx.Response(
            200,
            json={
                "requestId": "exa_test",
                "results": [
                    {
                        "url": "https://example.com/exa-current",
                        "title": "Exa current evidence",
                        "publishedDate": "2026-05-16T00:00:00.000Z",
                        "highlights": ["Current Exa highlight.", "Second Exa highlight."],
                        "score": 0.82,
                    }
                ],
            },
        )

    provider = ExaSearchEvidenceProvider(
        api_key="exa-key",
        search_type="neural",
        category="news",
        user_location="US",
        text_max_characters=900,
        transport=httpx.MockTransport(handler),
    )

    results = await provider.search(_request())

    assert captured["api_key"] == "exa-key"
    request_body = json.loads(str(captured["body"]))
    assert request_body["query"] == _request().query
    assert request_body["type"] == "neural"
    assert request_body["category"] == "news"
    assert request_body["userLocation"] == "US"
    assert request_body["numResults"] == 5
    assert request_body["contents"]["highlights"]["maxCharacters"] == 900
    assert request_body["contents"]["highlights"]["query"] == _request().query
    assert len(results) == 1
    assert results[0].provider == "exa_search"
    assert results[0].snippet == "Current Exa highlight.\n\nSecond Exa highlight."
    assert results[0].published_at == "2026-05-16T00:00:00.000Z"
    assert results[0].confidence == 0.82


@pytest.mark.asyncio
async def test_exa_search_provider_falls_back_for_missing_title_and_score() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://example.com/exa-summary",
                        "summary": "Exa summary should be preferred.",
                        "score": 2.0,
                    },
                    {
                        "url": "https://example.com/exa-text",
                        "text": "Text fallback should become snippet.",
                    },
                ]
            },
        )

    provider = ExaSearchEvidenceProvider(
        api_key="exa-key",
        search_type="invalid",
        category="not-a-category",
        text_max_characters=-10,
        transport=httpx.MockTransport(handler),
    )

    results = await provider.search(_request())

    assert provider.search_type == "auto"
    assert provider.category is None
    assert provider.text_max_characters == 1
    assert results[0].title == "https://example.com/exa-summary"
    assert results[0].snippet == "Exa summary should be preferred."
    assert results[0].confidence == 1.0
    assert results[1].confidence == 0.74


@pytest.mark.asyncio
async def test_exa_search_provider_returns_empty_on_invalid_json() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    provider = ExaSearchEvidenceProvider(
        api_key="exa-key",
        transport=httpx.MockTransport(handler),
    )

    assert await provider.search(_request()) == []


@pytest.mark.asyncio
async def test_exa_search_provider_returns_empty_on_http_failure() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    provider = ExaSearchEvidenceProvider(
        api_key="exa-key",
        transport=httpx.MockTransport(handler),
    )

    assert await provider.search(_request()) == []


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
async def test_tavily_search_provider_posts_query_and_parses_results() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("authorization")
        body = request.read().decode()
        captured["body"] = body
        return httpx.Response(
            200,
            json={
                "query": "LeBron current status",
                "results": [
                    {
                        "title": "Tavily current evidence",
                        "url": "https://example.com/tavily-current",
                        "content": "Current Tavily source excerpt.",
                        "score": 0.86,
                    }
                ],
                "response_time": 1.2,
            },
        )

    provider = TavilySearchEvidenceProvider(
        api_key="tavily-key",
        search_depth="advanced",
        topic="news",
        time_range="week",
        transport=httpx.MockTransport(handler),
    )

    results = await provider.search(_request())

    assert captured["authorization"] == "Bearer tavily-key"
    request_body = json.loads(str(captured["body"]))
    assert request_body["query"] == _request().query
    assert request_body["search_depth"] == "advanced"
    assert request_body["topic"] == "news"
    assert request_body["time_range"] == "week"
    assert request_body["max_results"] == 5
    assert request_body["include_raw_content"] is False
    assert len(results) == 1
    assert results[0].provider == "tavily_search"
    assert results[0].snippet == "Current Tavily source excerpt."
    assert results[0].confidence == 0.86


@pytest.mark.asyncio
async def test_tavily_search_provider_falls_back_for_missing_title_and_score() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://example.com/no-title",
                        "content": "Untitled result is still useful evidence.",
                        "score": 1.7,
                    },
                    {
                        "title": "No score result",
                        "url": "https://example.com/no-score",
                        "content": "Missing score should use fallback confidence.",
                    },
                ]
            },
        )

    provider = TavilySearchEvidenceProvider(
        api_key="tavily-key",
        search_depth="invalid",
        topic="sports",
        time_range="forever",
        transport=httpx.MockTransport(handler),
    )

    results = await provider.search(_request())

    assert provider.search_depth == "basic"
    assert provider.topic == "general"
    assert provider.time_range is None
    assert results[0].title == "https://example.com/no-title"
    assert results[0].confidence == 1.0
    assert results[1].confidence == 0.72


@pytest.mark.asyncio
async def test_tavily_search_provider_returns_empty_on_invalid_json() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    provider = TavilySearchEvidenceProvider(
        api_key="tavily-key",
        transport=httpx.MockTransport(handler),
    )

    assert await provider.search(_request()) == []


@pytest.mark.asyncio
async def test_tavily_search_provider_returns_empty_on_http_failure() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": {"error": "unauthorized"}})

    provider = TavilySearchEvidenceProvider(
        api_key="tavily-key",
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


def test_evidence_provider_from_env_uses_mcp_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRISM_EVIDENCE_PROVIDER", "mcp")
    monkeypatch.setenv("PRISM_EVIDENCE_MCP_URL", "https://tools.example.com/mcp/")
    monkeypatch.setenv("PRISM_EVIDENCE_MCP_TOOL", "search")
    monkeypatch.setenv("PRISM_EVIDENCE_RESULT_MAPPER", "firecrawl_search")
    monkeypatch.setenv("PRISM_EVIDENCE_MCP_INPUT_MAPPER", "query_limit")
    monkeypatch.setenv("PRISM_EVIDENCE_MCP_AUTH_TOKEN", "secret-token")
    monkeypatch.setenv("PRISM_EVIDENCE_MCP_ALLOWED_TOOLS", "search,extract")
    monkeypatch.setenv("PRISM_EVIDENCE_MCP_TIMEOUT_SECONDS", "bad-value")

    provider = evidence_provider_from_env()

    assert isinstance(provider, McpEvidenceProvider)
    assert provider.server_url == "https://tools.example.com/mcp/"
    assert provider.tool_name == "search"
    assert provider.result_mapper == "firecrawl_search"
    assert provider.input_mapper == "query_limit"
    assert provider.auth_token == "secret-token"
    assert provider.allowed_tools == ["search", "extract"]
    assert provider.timeout_seconds == 20.0


def test_evidence_provider_from_env_falls_back_to_noop_for_unknown_mcp_mapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRISM_EVIDENCE_PROVIDER", "mcp")
    monkeypatch.setenv("PRISM_EVIDENCE_MCP_URL", "https://tools.example.com/mcp/")
    monkeypatch.setenv("PRISM_EVIDENCE_MCP_TOOL", "search")
    monkeypatch.setenv("PRISM_EVIDENCE_RESULT_MAPPER", "not-real")

    assert isinstance(evidence_provider_from_env(), NoopEvidenceProvider)


def test_evidence_provider_from_env_falls_back_to_noop_for_unknown_mcp_input_mapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRISM_EVIDENCE_PROVIDER", "mcp")
    monkeypatch.setenv("PRISM_EVIDENCE_MCP_URL", "https://tools.example.com/mcp/")
    monkeypatch.setenv("PRISM_EVIDENCE_MCP_TOOL", "search")
    monkeypatch.setenv("PRISM_EVIDENCE_MCP_INPUT_MAPPER", "not-real")

    assert isinstance(evidence_provider_from_env(), NoopEvidenceProvider)


def test_evidence_provider_from_env_falls_back_to_noop_without_mcp_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRISM_EVIDENCE_PROVIDER", "mcp")
    monkeypatch.delenv("PRISM_EVIDENCE_MCP_URL", raising=False)
    monkeypatch.setenv("PRISM_EVIDENCE_MCP_TOOL", "search")

    assert isinstance(evidence_provider_from_env(), NoopEvidenceProvider)


def test_evidence_provider_from_env_uses_firecrawl_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRISM_EVIDENCE_PROVIDER", "firecrawl_search")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "firecrawl-key")
    monkeypatch.setenv("FIRECRAWL_SEARCH_COUNTRY", "US")
    monkeypatch.setenv("FIRECRAWL_SEARCH_LOCATION", "Tallinn,Estonia")
    monkeypatch.setenv("FIRECRAWL_SEARCH_TBS", "qdr:w")
    monkeypatch.setenv("FIRECRAWL_SEARCH_CATEGORY", "github")
    monkeypatch.setenv("FIRECRAWL_SEARCH_FORMAT", "summary")
    monkeypatch.setenv("FIRECRAWL_SEARCH_TIMEOUT_SECONDS", "bad-value")

    provider = evidence_provider_from_env()

    assert isinstance(provider, FirecrawlSearchEvidenceProvider)
    assert provider.api_key == "firecrawl-key"
    assert provider.country == "US"
    assert provider.location == "Tallinn,Estonia"
    assert provider.tbs == "qdr:w"
    assert provider.category == "github"
    assert provider.scrape_format == "summary"
    assert provider.timeout_seconds == 30.0


def test_evidence_provider_from_env_falls_back_to_firecrawl_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRISM_EVIDENCE_PROVIDER", "firecrawl_search")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "firecrawl-key")
    monkeypatch.setenv("FIRECRAWL_SEARCH_CATEGORY", "bad-category")
    monkeypatch.setenv("FIRECRAWL_SEARCH_FORMAT", "bad-format")
    monkeypatch.setenv("FIRECRAWL_SEARCH_TIMEOUT_SECONDS", "0")

    provider = evidence_provider_from_env()

    assert isinstance(provider, FirecrawlSearchEvidenceProvider)
    assert provider.category is None
    assert provider.scrape_format == "markdown"
    assert provider.timeout_seconds == 30.0


def test_evidence_provider_from_env_falls_back_to_noop_without_firecrawl_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRISM_EVIDENCE_PROVIDER", "firecrawl_search")
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)

    assert isinstance(evidence_provider_from_env(), NoopEvidenceProvider)


def test_evidence_provider_from_env_uses_exa_search(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRISM_EVIDENCE_PROVIDER", "exa_search")
    monkeypatch.setenv("EXA_API_KEY", "exa-key")
    monkeypatch.setenv("EXA_SEARCH_TYPE", "fast")
    monkeypatch.setenv("EXA_SEARCH_CATEGORY", "news")
    monkeypatch.setenv("EXA_SEARCH_USER_LOCATION", "US")
    monkeypatch.setenv("EXA_SEARCH_TEXT_MAX_CHARACTERS", "900")
    monkeypatch.setenv("EXA_SEARCH_TIMEOUT_SECONDS", "bad-value")

    provider = evidence_provider_from_env()

    assert isinstance(provider, ExaSearchEvidenceProvider)
    assert provider.api_key == "exa-key"
    assert provider.search_type == "fast"
    assert provider.category == "news"
    assert provider.user_location == "US"
    assert provider.text_max_characters == 900
    assert provider.timeout_seconds == 30.0


def test_evidence_provider_from_env_falls_back_to_exa_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRISM_EVIDENCE_PROVIDER", "exa_search")
    monkeypatch.setenv("EXA_API_KEY", "exa-key")
    monkeypatch.setenv("EXA_SEARCH_TYPE", "invalid")
    monkeypatch.setenv("EXA_SEARCH_CATEGORY", "not-a-category")
    monkeypatch.setenv("EXA_SEARCH_TEXT_MAX_CHARACTERS", "-1")
    monkeypatch.setenv("EXA_SEARCH_TIMEOUT_SECONDS", "0")

    provider = evidence_provider_from_env()

    assert isinstance(provider, ExaSearchEvidenceProvider)
    assert provider.search_type == "auto"
    assert provider.category is None
    assert provider.text_max_characters == 1200
    assert provider.timeout_seconds == 30.0


def test_evidence_provider_from_env_falls_back_to_noop_without_exa_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRISM_EVIDENCE_PROVIDER", "exa_search")
    monkeypatch.delenv("EXA_API_KEY", raising=False)

    assert isinstance(evidence_provider_from_env(), NoopEvidenceProvider)


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


def test_evidence_provider_from_env_uses_tavily_search(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRISM_EVIDENCE_PROVIDER", "tavily_search")
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-key")
    monkeypatch.setenv("TAVILY_SEARCH_DEPTH", "fast")
    monkeypatch.setenv("TAVILY_SEARCH_TOPIC", "news")
    monkeypatch.setenv("TAVILY_SEARCH_TIME_RANGE", "week")
    monkeypatch.setenv("TAVILY_SEARCH_TIMEOUT_SECONDS", "bad-value")

    provider = evidence_provider_from_env()

    assert isinstance(provider, TavilySearchEvidenceProvider)
    assert provider.api_key == "tavily-key"
    assert provider.search_depth == "fast"
    assert provider.topic == "news"
    assert provider.time_range == "week"
    assert provider.timeout_seconds == 20.0


def test_evidence_provider_from_env_falls_back_to_tavily_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRISM_EVIDENCE_PROVIDER", "tavily_search")
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-key")
    monkeypatch.setenv("TAVILY_SEARCH_DEPTH", "invalid")
    monkeypatch.setenv("TAVILY_SEARCH_TOPIC", "sports")
    monkeypatch.setenv("TAVILY_SEARCH_TIME_RANGE", "forever")
    monkeypatch.setenv("TAVILY_SEARCH_TIMEOUT_SECONDS", "0")

    provider = evidence_provider_from_env()

    assert isinstance(provider, TavilySearchEvidenceProvider)
    assert provider.search_depth == "basic"
    assert provider.topic == "general"
    assert provider.time_range is None
    assert provider.timeout_seconds == 20.0


def test_evidence_provider_from_env_falls_back_to_noop_without_tavily_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRISM_EVIDENCE_PROVIDER", "tavily_search")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

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
