"""Tests for POST /evidence endpoint — VAL-TOOL-001 through VAL-TOOL-008.

Tests cover:
  - VAL-TOOL-001: Valid request returns 200 with EvidenceApiResponse schema
  - VAL-TOOL-002: Invalid request bodies return 422
  - VAL-TOOL-003: /evidence is free — no x402 payment required, never returns 402
  - VAL-TOOL-004: Returns results from configured provider (noop → empty gracefully)
  - VAL-TOOL-005: Respects budget — budget_remaining decreases after provider calls
  - VAL-TOOL-006: Uses cache — from_cache flags reflect cache hits
  - VAL-TOOL-007: Handles provider errors gracefully — 200 with empty results
  - VAL-TOOL-008: Does NOT invoke DSPy pipeline
"""

from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from prism_schemas.verdict import AdversarialChallenge

from sentinel.evidence_tools import (
    EvidenceSearchResult,
    NoopEvidenceProvider,
    StaticEvidenceProvider,
)

# -- Module-level shared-state reset fixtures ---------------------------------


@pytest.fixture(autouse=True)
def _reset_shared_cache() -> None:
    """Reset module-level shared cache before each test."""
    from cachetools import TTLCache

    import sentinel.evidence_tools as et

    et._shared_evidence_cache = TTLCache(maxsize=256, ttl=300)


@pytest.fixture(autouse=True)
def _reset_cb_registry() -> None:
    """Reset module-level circuit breaker registry before each test."""
    import sentinel.evidence_tools as et

    et._circuit_breaker_registry.clear()


# -- Helpers ------------------------------------------------------------------


def _unique_id() -> str:
    """Return a short unique string for test isolation."""
    return uuid.uuid4().hex[:8]


def _make_result(title: str = "Test Result") -> EvidenceSearchResult:
    return EvidenceSearchResult(
        title=title,
        url="https://example.com/test",
        snippet="Test evidence snippet.",
        provider="test_provider",
        confidence=0.75,
    )


def _challenge(challenge_id: str = "evidence-query") -> AdversarialChallenge:
    return AdversarialChallenge(
        id=challenge_id,
        type="temporal",
        severity="material",
        question="Is there current evidence?",
        required_resolution="Retrieve current data.",
        blocking_pass=False,
    )


# -- VAL-TOOL-001: /evidence returns correct schema ---------------------------


class TestEvidenceEndpointValidRequest:
    """Tests for VAL-TOOL-001: /evidence returns correct schema."""

    @patch.dict(os.environ, {"X402_BYPASS": "1"})
    def test_valid_request_returns_200_with_correct_schema(self) -> None:
        """POST /evidence with valid body returns 200 and EvidenceApiResponse."""
        with (
            patch("sentinel.main._run_startup_gates"),
            patch("sentinel.main.run_migration"),
            patch("sentinel.main.ensure_agent_row"),
        ):
            from sentinel.main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/evidence",
                json={
                    "market_question": "Will it rain tomorrow?",
                    "query": "weather forecast tomorrow",
                    "max_results": 3,
                },
            )

            assert response.status_code == 200, (
                f"Expected 200, got {response.status_code}: {response.text}"
            )
            body = response.json()
            assert "results" in body
            assert "budget_remaining" in body
            assert "from_cache" in body
            assert isinstance(body["results"], list)
            assert isinstance(body["budget_remaining"], int)
            assert body["budget_remaining"] >= 0
            assert isinstance(body["from_cache"], list)
            assert len(body["from_cache"]) == len(body["results"])

    @patch.dict(os.environ, {"X402_BYPASS": "1"})
    def test_default_max_results_is_5(self) -> None:
        """When max_results is omitted, it defaults to 5."""
        with (
            patch("sentinel.main._run_startup_gates"),
            patch("sentinel.main.run_migration"),
            patch("sentinel.main.ensure_agent_row"),
        ):
            from sentinel.main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/evidence",
                json={
                    "market_question": "Will it rain tomorrow?",
                    "query": "weather forecast",
                },
            )
            # Default max_results should be accepted (no 422)
            assert response.status_code == 200

    @patch.dict(os.environ, {"X402_BYPASS": "1"})
    def test_results_contain_evidence_search_result_fields(self) -> None:
        """Each result in the response has the EvidenceSearchResult shape."""
        with (
            patch("sentinel.main._run_startup_gates"),
            patch("sentinel.main.run_migration"),
            patch("sentinel.main.ensure_agent_row"),
            patch("sentinel.main.evidence_provider_from_runtime") as mock_runtime,
        ):
            # Use a StaticEvidenceProvider that returns known results
            provider = StaticEvidenceProvider({"evidence-query": [_make_result("Known Result")]})
            mock_runtime.return_value = provider

            from sentinel.main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/evidence",
                json={
                    "market_question": "Will it rain tomorrow?",
                    "query": "weather forecast",
                },
            )
            assert response.status_code == 200
            body = response.json()
            assert len(body["results"]) == 1
            assert body["results"][0]["title"] == "Known Result"
            assert body["results"][0]["url"] == "https://example.com/test"


# -- VAL-TOOL-002: Invalid request bodies return 422 --------------------------


class TestEvidenceEndpointInvalidRequest:
    """Tests for VAL-TOOL-002: Invalid requests return 422."""

    @patch.dict(os.environ, {"X402_BYPASS": "1"})
    def test_missing_market_question_returns_422(self) -> None:
        """Missing market_question field returns 422."""
        with (
            patch("sentinel.main._run_startup_gates"),
            patch("sentinel.main.run_migration"),
            patch("sentinel.main.ensure_agent_row"),
        ):
            from sentinel.main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/evidence",
                json={"query": "weather forecast"},
            )
            assert response.status_code == 422

    @patch.dict(os.environ, {"X402_BYPASS": "1"})
    def test_missing_query_returns_422(self) -> None:
        """Missing query field returns 422."""
        with (
            patch("sentinel.main._run_startup_gates"),
            patch("sentinel.main.run_migration"),
            patch("sentinel.main.ensure_agent_row"),
        ):
            from sentinel.main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/evidence",
                json={"market_question": "Will it rain?"},
            )
            assert response.status_code == 422

    @patch.dict(os.environ, {"X402_BYPASS": "1"})
    def test_max_results_zero_returns_422(self) -> None:
        """max_results=0 returns 422 (must be >=1)."""
        with (
            patch("sentinel.main._run_startup_gates"),
            patch("sentinel.main.run_migration"),
            patch("sentinel.main.ensure_agent_row"),
        ):
            from sentinel.main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/evidence",
                json={
                    "market_question": "Test?",
                    "query": "test",
                    "max_results": 0,
                },
            )
            assert response.status_code == 422

    @patch.dict(os.environ, {"X402_BYPASS": "1"})
    def test_max_results_above_20_returns_422(self) -> None:
        """max_results=21 returns 422 (max is 20)."""
        with (
            patch("sentinel.main._run_startup_gates"),
            patch("sentinel.main.run_migration"),
            patch("sentinel.main.ensure_agent_row"),
        ):
            from sentinel.main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/evidence",
                json={
                    "market_question": "Test?",
                    "query": "test",
                    "max_results": 21,
                },
            )
            assert response.status_code == 422

    @patch.dict(os.environ, {"X402_BYPASS": "1"})
    def test_empty_body_returns_422(self) -> None:
        """Empty request body returns 422."""
        with (
            patch("sentinel.main._run_startup_gates"),
            patch("sentinel.main.run_migration"),
            patch("sentinel.main.ensure_agent_row"),
        ):
            from sentinel.main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/evidence",
                json={},
            )
            assert response.status_code == 422

    @patch.dict(os.environ, {"X402_BYPASS": "1"})
    def test_wrong_types_return_422(self) -> None:
        """Wrong field types return 422."""
        with (
            patch("sentinel.main._run_startup_gates"),
            patch("sentinel.main.run_migration"),
            patch("sentinel.main.ensure_agent_row"),
        ):
            from sentinel.main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/evidence",
                json={
                    "market_question": 123,
                    "query": ["not", "a", "string"],
                    "max_results": "not_a_number",
                },
            )
            assert response.status_code == 422


# -- VAL-TOOL-003: /evidence is free — no x402 ---------------------------------


class TestEvidenceEndpointFreeNoX402:
    """Tests for VAL-TOOL-003: /evidence is free, never 402."""

    def test_no_x402_bypass_no_payment_returns_200(self) -> None:
        """Without x402 bypass or payment header, /evidence still returns 200."""
        with (
            patch("sentinel.main._run_startup_gates"),
            patch("sentinel.main.run_migration"),
            patch("sentinel.main.ensure_agent_row"),
            patch.dict(os.environ, {"X402_BYPASS": ""}),
        ):
            from sentinel.main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/evidence",
                json={
                    "market_question": "Will it rain?",
                    "query": "weather forecast",
                },
            )
            # Must NOT be 402 — /evidence is free
            assert response.status_code == 200, (
                f"Expected 200 (free endpoint), got {response.status_code}: {response.text}"
            )

    def test_compare_validate_returns_402_evidence_returns_200(self) -> None:
        """/validate returns 402 without payment but /evidence returns 200."""
        with (
            patch("sentinel.main._run_startup_gates"),
            patch("sentinel.main.run_migration"),
            patch("sentinel.main.ensure_agent_row"),
            patch.dict(os.environ, {"X402_BYPASS": ""}),
        ):
            from sentinel.main import app

            client = TestClient(app, raise_server_exceptions=False)

            # /validate without payment → 402
            validate_resp = client.post(
                "/validate",
                json={"trace_uri": "ipfs://QmTest", "trace_hash": "0xabc"},
            )
            assert validate_resp.status_code == 402, (
                f"/validate should be paywalled, got {validate_resp.status_code}"
            )

            # /evidence without payment → 200
            evidence_resp = client.post(
                "/evidence",
                json={"market_question": "Test?", "query": "test"},
            )
            assert evidence_resp.status_code == 200, (
                f"/evidence should be free, got {evidence_resp.status_code}"
            )


# -- VAL-TOOL-004: Returns results from configured provider --------------------


class TestEvidenceEndpointProviderResults:
    """Tests for VAL-TOOL-004: Returns results from configured provider."""

    @patch.dict(os.environ, {"X402_BYPASS": "1"})
    def test_noop_provider_returns_empty_results(self) -> None:
        """With noop provider, /evidence returns empty results gracefully."""
        with (
            patch("sentinel.main._run_startup_gates"),
            patch("sentinel.main.run_migration"),
            patch("sentinel.main.ensure_agent_row"),
            patch("sentinel.main.evidence_provider_from_runtime") as mock_runtime,
        ):
            mock_runtime.return_value = NoopEvidenceProvider()

            from sentinel.main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/evidence",
                json={
                    "market_question": "Test?",
                    "query": "test query",
                },
            )
            assert response.status_code == 200
            body = response.json()
            assert body["results"] == []

    @patch.dict(os.environ, {"X402_BYPASS": "1"})
    def test_static_provider_returns_known_results(self) -> None:
        """A StaticEvidenceProvider returns its injected data."""
        with (
            patch("sentinel.main._run_startup_gates"),
            patch("sentinel.main.run_migration"),
            patch("sentinel.main.ensure_agent_row"),
            patch("sentinel.main.evidence_provider_from_runtime") as mock_runtime,
        ):
            provider = StaticEvidenceProvider(
                {"evidence-query": [_make_result("Result A"), _make_result("Result B")]}
            )
            mock_runtime.return_value = provider

            from sentinel.main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/evidence",
                json={
                    "market_question": "Test?",
                    "query": "test query",
                },
            )
            assert response.status_code == 200
            body = response.json()
            assert len(body["results"]) == 2
            assert body["results"][0]["title"] == "Result A"
            assert body["results"][1]["title"] == "Result B"


# -- VAL-TOOL-005: /evidence respects budget ----------------------------------


class TestEvidenceEndpointBudget:
    """Tests for VAL-TOOL-005: budget_remaining decreases."""

    @patch.dict(os.environ, {"X402_BYPASS": "1"})
    def test_budget_remaining_reflects_provider_call(self) -> None:
        """After a provider call, budget_remaining is less than initial."""
        with (
            patch("sentinel.main._run_startup_gates"),
            patch("sentinel.main.run_migration"),
            patch("sentinel.main.ensure_agent_row"),
            patch("sentinel.main.evidence_provider_from_runtime") as mock_runtime,
        ):
            provider = StaticEvidenceProvider({"evidence-query": [_make_result("Result")]})
            mock_runtime.return_value = provider

            from sentinel.main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/evidence",
                json={
                    "market_question": "Test?",
                    "query": "test query",
                },
            )
            assert response.status_code == 200
            body = response.json()
            # With a budget of 3 and one call, remaining should be 2
            assert body["budget_remaining"] >= 0
            # Budget should have decreased from its initial value
            assert body["budget_remaining"] < 3

    @patch.dict(os.environ, {"X402_BYPASS": "1"})
    def test_budget_exhaustion_returns_empty_with_zero_remaining(self) -> None:
        """When budget is 0, /evidence returns empty results with budget_remaining=0."""
        with (
            patch("sentinel.main._run_startup_gates"),
            patch("sentinel.main.run_migration"),
            patch("sentinel.main.ensure_agent_row"),
            patch("sentinel.main.evidence_provider_from_runtime") as mock_runtime,
            patch("sentinel.main._read_evidence_budget", return_value=0),
        ):
            provider = StaticEvidenceProvider({"evidence-query": [_make_result("Result")]})
            mock_runtime.return_value = provider

            from sentinel.main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/evidence",
                json={
                    "market_question": "Test?",
                    "query": "test query",
                },
            )
            assert response.status_code == 200
            body = response.json()
            assert body["results"] == []
            assert body["budget_remaining"] == 0


# -- VAL-TOOL-006: /evidence uses cache ---------------------------------------


class TestEvidenceEndpointCache:
    """Tests for VAL-TOOL-006: from_cache flags reflect cache hits."""

    @patch.dict(os.environ, {"X402_BYPASS": "1"})
    def test_first_call_from_cache_all_false(self) -> None:
        """First call with a query → all from_cache are False."""
        q = _unique_id()
        with (
            patch("sentinel.main._run_startup_gates"),
            patch("sentinel.main.run_migration"),
            patch("sentinel.main.ensure_agent_row"),
            patch("sentinel.main.evidence_provider_from_runtime") as mock_runtime,
        ):
            provider = StaticEvidenceProvider({"evidence-query": [_make_result("Fresh Result")]})
            mock_runtime.return_value = provider

            from sentinel.main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/evidence",
                json={
                    "market_question": "Test?",
                    "query": q,
                },
            )
            assert response.status_code == 200
            body = response.json()
            # First call — cache miss, from_cache should all be False
            assert len(body["from_cache"]) == len(body["results"])
            if body["results"]:
                assert all(not flag for flag in body["from_cache"]), (
                    f"First call should be cache miss: {body['from_cache']}"
                )

    @patch.dict(os.environ, {"X402_BYPASS": "1"})
    def test_second_call_same_query_from_cache_true(self) -> None:
        """Second call with same query → from_cache=True, budget not consumed."""
        q = _unique_id()
        with (
            patch("sentinel.main._run_startup_gates"),
            patch("sentinel.main.run_migration"),
            patch("sentinel.main.ensure_agent_row"),
            patch("sentinel.main.evidence_provider_from_runtime") as mock_runtime,
        ):
            provider = StaticEvidenceProvider({"evidence-query": [_make_result("Cached Result")]})
            mock_runtime.return_value = provider

            from sentinel.main import app

            client = TestClient(app, raise_server_exceptions=False)

            # First call — cache miss
            resp1 = client.post(
                "/evidence",
                json={"market_question": "Test?", "query": q},
            )
            assert resp1.status_code == 200
            body1 = resp1.json()
            budget_after_first = body1["budget_remaining"]

            # Second call — same query, should be cache hit
            resp2 = client.post(
                "/evidence",
                json={"market_question": "Test?", "query": q},
            )
            assert resp2.status_code == 200
            body2 = resp2.json()

            # Second call should have from_cache=True for all results
            if body2["results"]:
                assert all(flag for flag in body2["from_cache"]), (
                    f"Second call should be cache hit: {body2['from_cache']}"
                )
            # Budget should not have been consumed further (cache hit)
            b2 = body2["budget_remaining"]
            assert b2 == budget_after_first, (
                f"Cache hit should not consume budget: {b2} != {budget_after_first}"
            )


# -- VAL-TOOL-007: /evidence handles provider errors gracefully ----------------


class TestEvidenceEndpointProviderErrors:
    """Tests for VAL-TOOL-007: Provider errors return 200, not 500."""

    @patch.dict(os.environ, {"X402_BYPASS": "1"})
    def test_provider_exception_returns_200_with_empty_results(self) -> None:
        """When provider raises, /evidence returns 200 with empty results."""
        with (
            patch("sentinel.main._run_startup_gates"),
            patch("sentinel.main.run_migration"),
            patch("sentinel.main.ensure_agent_row"),
            patch("sentinel.main.evidence_provider_from_runtime") as mock_runtime,
        ):
            failing = MagicMock()
            failing.search = AsyncMock(side_effect=RuntimeError("simulated failure"))
            mock_runtime.return_value = failing

            from sentinel.main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/evidence",
                json={
                    "market_question": "Test?",
                    "query": "test query",
                },
            )
            assert response.status_code == 200, (
                f"Provider errors should return 200, got {response.status_code}: {response.text}"
            )
            body = response.json()
            assert body["results"] == []
            assert body["budget_remaining"] >= 0


# -- VAL-TOOL-008: /evidence does NOT invoke DSPy pipeline ---------------------


class TestEvidenceEndpointNoDSPy:
    """Tests for VAL-TOOL-008: /evidence does not run DSPy pipeline."""

    @patch.dict(os.environ, {"X402_BYPASS": "1"})
    def test_evidence_does_not_call_generate_verdict(self) -> None:
        """POST /evidence does not invoke generate_verdict."""
        with (
            patch("sentinel.main._run_startup_gates"),
            patch("sentinel.main.run_migration"),
            patch("sentinel.main.ensure_agent_row"),
            patch("sentinel.main.evidence_provider_from_runtime") as mock_runtime,
            patch("sentinel.main.generate_verdict") as mock_gen_verdict,
        ):
            provider = NoopEvidenceProvider()
            mock_runtime.return_value = provider

            from sentinel.main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/evidence",
                json={
                    "market_question": "Test?",
                    "query": "test query",
                },
            )
            assert response.status_code == 200
            # generate_verdict should never have been called
            mock_gen_verdict.assert_not_called()

    @patch.dict(os.environ, {"X402_BYPASS": "1"})
    def test_evidence_does_not_call_resolution_loop(self) -> None:
        """POST /evidence does not invoke generate_verdict_with_resolution."""
        with (
            patch("sentinel.main._run_startup_gates"),
            patch("sentinel.main.run_migration"),
            patch("sentinel.main.ensure_agent_row"),
            patch("sentinel.main.evidence_provider_from_runtime") as mock_runtime,
            patch("sentinel.resolution_loop.generate_verdict_with_resolution") as mock_gen_with_res,
        ):
            provider = NoopEvidenceProvider()
            mock_runtime.return_value = provider

            from sentinel.main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/evidence",
                json={
                    "market_question": "Test?",
                    "query": "test query",
                },
            )
            assert response.status_code == 200
            # generate_verdict_with_resolution should never have been called
            mock_gen_with_res.assert_not_called()
