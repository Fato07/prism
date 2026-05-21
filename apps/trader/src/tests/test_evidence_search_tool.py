"""Tests for evidence_search tool — VAL-TOOL-009 through VAL-TOOL-013.

Tests cover:
  - VAL-TOOL-009: evidence_search calls sentinel /evidence with correct request
  - VAL-TOOL-010: Reads SENTINEL_EVIDENCE_URL with default fallback
  - VAL-TOOL-011: Handles sentinel unavailability → returns [], logs warning
  - VAL-TOOL-012: Handles malformed response → returns [], logs warning
  - VAL-TOOL-013: Handles HTTP error responses → returns [], logs warning, no retry
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from trader.tools.evidence_search import (
    _DEFAULT_SENTINEL_URL,
    _DEFAULT_TIMEOUT_SECONDS,
    _sentinel_evidence_url,
    evidence_search,
    map_result_to_receipt,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(**overrides):
    """Create an EvidenceSearchResult for testing."""
    from sentinel.evidence_tools import EvidenceSearchResult

    defaults = {
        "title": "Test Result",
        "url": "https://example.com/test",
        "snippet": "Test evidence snippet.",
        "provider": "test_provider",
        "confidence": 0.75,
    }
    defaults.update(overrides)
    return EvidenceSearchResult(**defaults)


# ---------------------------------------------------------------------------
# VAL-TOOL-009: evidence_search calls sentinel /evidence with correct request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evidence_search_sends_correct_post_request() -> None:
    """evidence_search sends POST to the correct sentinel URL with the right body."""
    with patch.dict(os.environ, {"SENTINEL_EVIDENCE_URL": "http://localhost:3202"}, clear=False):
        json_body = {
            "results": [
                {
                    "title": "Found evidence",
                    "url": "https://example.com/evidence",
                    "snippet": "Evidence text.",
                    "provider": "test_provider",
                    "confidence": 0.9,
                }
            ],
            "budget_remaining": 2,
            "from_cache": [False],
        }

        # Build mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = json_body

        # Build mock client where post() returns the mock response
        mock_post = AsyncMock(return_value=mock_response)

        with patch.object(httpx.AsyncClient, "post", mock_post):
            results = await evidence_search("Will ETH hit $5000?")

            # Verify the POST was called with correct URL and body
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args.kwargs
            assert call_kwargs["json"]["market_question"] == "Will ETH hit $5000?"
            assert call_kwargs["json"]["query"] == "Will ETH hit $5000?"
            assert call_kwargs["json"]["max_results"] == 5
            assert "X402-Bypass" in call_kwargs["headers"]

            # Verify results were parsed
            assert len(results) == 1
            assert results[0].title == "Found evidence"
            assert results[0].provider == "test_provider"


# ---------------------------------------------------------------------------
# VAL-TOOL-010: evidence_search reads SENTINEL_EVIDENCE_URL with default
# ---------------------------------------------------------------------------


def test_sentinel_evidence_url_default() -> None:
    """Default sentinel URL is http://localhost:3202 when env var is unset."""
    assert _DEFAULT_SENTINEL_URL == "http://localhost:3202"


def test_sentinel_evidence_url_from_env() -> None:
    """Custom SENTINEL_EVIDENCE_URL is used when env var is set."""
    with patch.dict(
        os.environ, {"SENTINEL_EVIDENCE_URL": "https://sentinel.example.com"}, clear=False
    ):
        url = _sentinel_evidence_url()
        assert url == "https://sentinel.example.com/evidence"


def test_sentinel_evidence_url_trailing_slash_handled() -> None:
    """Trailing slash in SENTINEL_EVIDENCE_URL is stripped."""
    with patch.dict(os.environ, {"SENTINEL_EVIDENCE_URL": "http://localhost:9999/"}, clear=False):
        url = _sentinel_evidence_url()
        assert url == "http://localhost:9999/evidence"


# ---------------------------------------------------------------------------
# VAL-TOOL-011: evidence_search handles sentinel unavailability
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evidence_search_handles_connection_error() -> None:
    """When sentinel is unreachable, returns [] and does not raise."""
    with patch.object(
        httpx.AsyncClient, "post", AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
    ):
        results = await evidence_search("Test question")
        assert results == []


@pytest.mark.asyncio
async def test_evidence_search_handles_timeout() -> None:
    """When sentinel times out, returns [] and does not raise."""
    with patch.object(
        httpx.AsyncClient, "post", AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
    ):
        results = await evidence_search("Test question")
        assert results == []


# ---------------------------------------------------------------------------
# VAL-TOOL-012: evidence_search handles malformed response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evidence_search_handles_malformed_json() -> None:
    """When sentinel returns non-JSON, returns []."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.side_effect = ValueError("Invalid JSON")

    with patch.object(httpx.AsyncClient, "post", AsyncMock(return_value=mock_response)):
        results = await evidence_search("Test question")
        assert results == []


@pytest.mark.asyncio
async def test_evidence_search_handles_missing_results_key() -> None:
    """When response dict has no 'results' key, returns []."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"budget_remaining": 3, "from_cache": []}

    with patch.object(httpx.AsyncClient, "post", AsyncMock(return_value=mock_response)):
        results = await evidence_search("Test question")
        assert results == []


@pytest.mark.asyncio
async def test_evidence_search_handles_results_not_a_list() -> None:
    """When results is not a list, returns []."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"results": "not_a_list", "budget_remaining": 3}

    with patch.object(httpx.AsyncClient, "post", AsyncMock(return_value=mock_response)):
        results = await evidence_search("Test question")
        assert results == []


@pytest.mark.asyncio
async def test_evidence_search_skips_invalid_individual_results() -> None:
    """Invalid individual result items are skipped; valid ones are returned."""
    json_body = {
        "results": [
            {
                "title": "Valid Result",
                "url": "https://example.com",
                "snippet": "Snippet.",
                "provider": "test",
                "confidence": 0.5,
            },
            {"not": "valid"},
        ],
        "budget_remaining": 2,
        "from_cache": [False],
    }
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = json_body

    with patch.object(httpx.AsyncClient, "post", AsyncMock(return_value=mock_response)):
        results = await evidence_search("Test question")
        assert len(results) == 1
        assert results[0].title == "Valid Result"


# ---------------------------------------------------------------------------
# VAL-TOOL-013: evidence_search handles HTTP error responses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evidence_search_handles_422_response() -> None:
    """HTTP 422 returns [], no retry."""
    mock_response = MagicMock()
    mock_response.status_code = 422

    with patch.object(httpx.AsyncClient, "post", AsyncMock(return_value=mock_response)):
        results = await evidence_search("Test question")
        assert results == []


@pytest.mark.asyncio
async def test_evidence_search_handles_500_response() -> None:
    """HTTP 500 returns [], no retry."""
    mock_response = MagicMock()
    mock_response.status_code = 500

    with patch.object(httpx.AsyncClient, "post", AsyncMock(return_value=mock_response)):
        results = await evidence_search("Test question")
        assert results == []


@pytest.mark.asyncio
async def test_evidence_search_handles_402_response() -> None:
    """HTTP 402 returns [], no retry."""
    mock_response = MagicMock()
    mock_response.status_code = 402

    with patch.object(httpx.AsyncClient, "post", AsyncMock(return_value=mock_response)):
        results = await evidence_search("Test question")
        assert results == []


# ---------------------------------------------------------------------------
# EvidenceSearchResult → EvidenceToolReceipt mapping
# ---------------------------------------------------------------------------


def test_map_result_to_receipt_direct_fields() -> None:
    """map_result_to_receipt preserves all core fields from the search result."""
    result = _make_result(
        title="Market Evidence",
        url="https://evidence.example.com/doc",
        snippet="Evidence snippet text.",
        provider="brave_search",
        tool_name="web_search",
        published_at="2026-05-20T00:00:00Z",
        retrieved_at="2026-05-22T00:00:00Z",
        confidence=0.88,
    )
    receipt = map_result_to_receipt(result)

    assert receipt.provider == "brave_search"
    assert receipt.tool_name == "web_search"
    assert receipt.source_title == "Market Evidence"
    assert receipt.source_url == "https://evidence.example.com/doc"
    assert receipt.source_published_at == "2026-05-20T00:00:00Z"
    assert receipt.retrieved_at == "2026-05-22T00:00:00Z"
    assert receipt.confidence == 0.88
    # Extra fields default to empty
    assert receipt.adequacy_checks == []
    assert receipt.source_content_hash is None
    assert receipt.extraction_checks == []


def test_map_result_to_receipt_minimal_fields() -> None:
    """Minimal search result (only required fields) maps correctly."""
    result = _make_result(
        title="Minimal",
        url="https://example.com",
        snippet=".",
        provider="test_provider",
        confidence=0.0,
    )
    receipt = map_result_to_receipt(result)

    assert receipt.provider == "test_provider"
    assert receipt.source_title == "Minimal"
    assert receipt.source_url == "https://example.com"
    assert receipt.confidence == 0.0
    assert receipt.tool_name is None
    assert receipt.source_published_at is None


# ---------------------------------------------------------------------------
# Timeout configuration
# ---------------------------------------------------------------------------


def test_evidence_search_timeout_default() -> None:
    """Default timeout is 10 seconds."""
    from trader.tools.evidence_search import _evidence_search_timeout

    with patch.dict(os.environ, {}, clear=True):
        assert _evidence_search_timeout() == _DEFAULT_TIMEOUT_SECONDS


def test_evidence_search_timeout_from_env() -> None:
    """Custom timeout from EVIDENCE_SEARCH_TIMEOUT_SECONDS."""
    from trader.tools.evidence_search import _evidence_search_timeout

    with patch.dict(os.environ, {"EVIDENCE_SEARCH_TIMEOUT_SECONDS": "5.0"}, clear=False):
        assert _evidence_search_timeout() == 5.0


def test_evidence_search_timeout_invalid_falls_back() -> None:
    """Invalid timeout values fall back to default."""
    from trader.tools.evidence_search import _evidence_search_timeout

    with patch.dict(os.environ, {"EVIDENCE_SEARCH_TIMEOUT_SECONDS": "not_a_number"}, clear=False):
        assert _evidence_search_timeout() == _DEFAULT_TIMEOUT_SECONDS

    with patch.dict(os.environ, {"EVIDENCE_SEARCH_TIMEOUT_SECONDS": "-1"}, clear=False):
        assert _evidence_search_timeout() == _DEFAULT_TIMEOUT_SECONDS

    with patch.dict(os.environ, {"EVIDENCE_SEARCH_TIMEOUT_SECONDS": "0"}, clear=False):
        assert _evidence_search_timeout() == _DEFAULT_TIMEOUT_SECONDS
