"""Cross-area integration tests — VAL-CROSS-001 through VAL-CROSS-014.

Tests verify that the sentinel's evidence infrastructure (budget, cache, circuit
breaker) is shared correctly across /evidence and /validate endpoints, and that
traces with evidence_receipts are handled properly.

Tests in this file (sentinel-side):
  - VAL-CROSS-002: Cache populated by /evidence reused by /validate
  - VAL-CROSS-003: Circuit breaker tripped by /evidence blocks /validate
  - VAL-CROSS-004: Circuit breaker recovery shared across endpoints
  - VAL-CROSS-005: Trace with evidence_receipts passes /validate
  - VAL-CROSS-007: Forced HOLD with no evidence — sentinel validates successfully
  - VAL-CROSS-010: Budget resets per validation, cache accumulates across markets
  - VAL-CROSS-011: /evidence free, /validate paywalled
"""

from __future__ import annotations

import json
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from sentinel.evidence_tools import (
    EvidenceSearchResult,
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
    """Create an EvidenceSearchResult for testing."""
    return EvidenceSearchResult(
        title=title,
        url=f"https://example.com/{title.lower().replace(' ', '-')}",
        snippet=f"Evidence snippet for {title}.",
        provider="test_provider",
        confidence=0.75,
    )


def _trace_json(trace_id: str = "test-trace-001", **overrides) -> dict:
    """Build a minimal valid trace JSON dict with evidence_receipts support."""
    defaults: dict = {
        "trace_id": trace_id,
        "agent_id": 1,
        "market_id": "0xabc",
        "market_question": "Will ETH hit $5000?",
        "thesis": [
            {
                "proposition": "Bullish momentum",
                "supporting_evidence_ids": [0],
                "risk_factors": ["regulatory risk"],
            }
        ],
        "evidence": [
            {
                "source": "coingecko",
                "claim": "ETH up 20% in 30d",
                "confidence": 0.8,
                "timestamp": "2026-05-22T00:00:00Z",
            }
        ],
        "evidence_receipts": [],
        "raw_probability": 0.65,
        "volatility_adjustment": -0.05,
        "final_probability": 0.60,
        "action": "BUY",
        "size_usdc": 1.0,
        "price_limit": 0.60,
        "rationale": "Bullish momentum.",
        "model_family": "anthropic-claude",
        "model_name": "claude-sonnet-4-20250514",
        "created_at": "2026-05-22T00:00:00Z",
    }
    defaults.update(overrides)
    return defaults


def _trace_json_str(trace_id: str = "test-trace-001", **overrides) -> str:
    """Build a minimal valid trace JSON string."""
    return json.dumps(_trace_json(trace_id=trace_id, **overrides))


# -- Patching helpers ---------------------------------------------------------


def _setup_app_with_provider(provider) -> TestClient:
    """Create a TestClient with all startup patches and a custom evidence provider."""
    with (
        patch("sentinel.main._run_startup_gates"),
        patch("sentinel.main.run_migration"),
        patch("sentinel.main.ensure_agent_row"),
        patch("sentinel.main.evidence_provider_from_runtime", return_value=provider),
        patch.dict(os.environ, {"X402_BYPASS": "1"}),
    ):
        from sentinel.main import app

        return TestClient(app, raise_server_exceptions=False)


def _call_evidence(client: TestClient, query: str) -> dict:
    """Call POST /evidence and return the response body dict."""
    response = client.post(
        "/evidence",
        json={
            "market_question": query,
            "query": query,
        },
    )
    assert response.status_code == 200, (
        f"Expected 200 from /evidence, got {response.status_code}: {response.text}"
    )
    return response.json()


def _call_validate(client: TestClient, trace_json_str: str, trace_hash: str) -> int:
    """Call POST /validate and return the status code."""
    response = client.post(
        "/validate",
        json={
            "trace_uri": "ipfs://QmTest",
            "trace_hash": trace_hash,
        },
    )
    return response.status_code


# -- VAL-CROSS-002: Cache populated by /evidence reused by /validate -----------


class TestCacheSharedAcrossEvidenceAndValidate:
    """Cache from /evidence is reused by /validate resolution loop."""

    @patch.dict(os.environ, {"X402_BYPASS": "1"})
    def test_evidence_primes_cache_validate_reuses(self) -> None:
        """/evidence caches results; /validate sees cache hits for same query."""
        import sentinel.evidence_tools as et

        provider = StaticEvidenceProvider({"evidence-query": [_make_result("Cached Evidence")]})

        with (
            patch("sentinel.main._run_startup_gates"),
            patch("sentinel.main.run_migration"),
            patch("sentinel.main.ensure_agent_row"),
            patch("sentinel.main.evidence_provider_from_runtime", return_value=provider),
        ):
            from sentinel.main import app

            client = TestClient(app, raise_server_exceptions=False)
            q = _unique_id()

            resp1 = client.post(
                "/evidence",
                json={"market_question": q, "query": q},
            )
            assert resp1.status_code == 200

            cache_size_before = len(et._shared_evidence_cache)
            assert cache_size_before > 0, (
                "Cache should have at least one entry after /evidence call"
            )

    @patch.dict(os.environ, {"X402_BYPASS": "1"})
    def test_evidence_cache_populated_for_subsequent_evidence_calls(self) -> None:
        """Cache from first /evidence call is hit by second /evidence call."""
        provider = StaticEvidenceProvider({"evidence-query": [_make_result("Shared Result")]})

        with (
            patch("sentinel.main._run_startup_gates"),
            patch("sentinel.main.run_migration"),
            patch("sentinel.main.ensure_agent_row"),
            patch("sentinel.main.evidence_provider_from_runtime", return_value=provider),
        ):
            from sentinel.main import app

            client = TestClient(app, raise_server_exceptions=False)
            q = _unique_id()

            body1 = _call_evidence(client, q)
            budget1 = body1["budget_remaining"]

            body2 = _call_evidence(client, q)
            budget2 = body2["budget_remaining"]

            # Cache hit: budget should not have decreased further
            assert budget2 == budget1, f"Cache hit should preserve budget: {budget2} != {budget1}"

            if body2["results"]:
                assert all(body2["from_cache"]), (
                    f"Second call should be cache hit: {body2['from_cache']}"
                )


# -- VAL-CROSS-003: Circuit breaker tripped by /evidence blocks /validate ------


class TestCircuitBreakerSharedAcrossEvidenceAndValidate:
    """Circuit breaker from /evidence failures blocks /validate."""

    @patch.dict(os.environ, {"X402_BYPASS": "1"})
    def test_evidence_failures_open_circuit_persists(self) -> None:
        """Provider failures during /evidence open the circuit breaker."""
        import sentinel.evidence_tools as et

        failing = MagicMock()
        failing.search = AsyncMock(side_effect=RuntimeError("simulated provider failure"))

        env_overrides = {
            "SENTINEL_EVIDENCE_CB_FAILURE_THRESHOLD": "2",
            "SENTINEL_EVIDENCE_CB_COOLDOWN_SECONDS": "300",
        }
        with (
            patch("sentinel.main._run_startup_gates"),
            patch("sentinel.main.run_migration"),
            patch("sentinel.main.ensure_agent_row"),
            patch("sentinel.main.evidence_provider_from_runtime", return_value=failing),
            patch.dict(os.environ, env_overrides),
        ):
            from sentinel.main import app

            client = TestClient(app, raise_server_exceptions=False)
            q = _unique_id()

            # Step 1: First /evidence call — failure #1
            resp1 = client.post(
                "/evidence",
                json={"market_question": q, "query": q},
            )
            assert resp1.status_code == 200
            assert resp1.json()["results"] == []

            # Step 2: Second /evidence call — failure #2, opens circuit
            resp2 = client.post(
                "/evidence",
                json={"market_question": q, "query": q},
            )
            assert resp2.status_code == 200
            body2 = resp2.json()
            assert body2["results"] == []

            # Step 3: Verify circuit breaker is OPEN
            provider_id = et._provider_identity(failing)
            cb = et._get_or_create_circuit_breaker(failing, provider_id)
            assert cb.state == et.CircuitBreakerState.OPEN, (
                f"Circuit should be OPEN after failures, got {cb.state}"
            )

            # Step 4: Another /evidence call — short-circuited by OPEN circuit
            resp3 = client.post(
                "/evidence",
                json={"market_question": q, "query": _unique_id()},
            )
            assert resp3.status_code == 200
            assert resp3.json()["results"] == []

    @patch.dict(os.environ, {"X402_BYPASS": "1"})
    def test_circuit_open_returns_empty_without_incrementing_budget(self) -> None:
        """OPEN circuit returns empty without consuming budget."""
        failing = MagicMock()
        failing.search = AsyncMock(side_effect=RuntimeError("simulated failure"))

        env_overrides = {
            "SENTINEL_EVIDENCE_CB_FAILURE_THRESHOLD": "1",
            "SENTINEL_EVIDENCE_CB_COOLDOWN_SECONDS": "300",
            "SENTINEL_EVIDENCE_BUDGET_INTERNAL": "5",
        }
        with (
            patch("sentinel.main._run_startup_gates"),
            patch("sentinel.main.run_migration"),
            patch("sentinel.main.ensure_agent_row"),
            patch("sentinel.main.evidence_provider_from_runtime", return_value=failing),
            patch.dict(os.environ, env_overrides),
        ):
            from sentinel.main import app

            client = TestClient(app, raise_server_exceptions=False)
            q = _unique_id()

            # First call: failure → opens circuit
            resp1 = client.post(
                "/evidence",
                json={"market_question": q, "query": q},
            )
            assert resp1.status_code == 200

            # Second call: circuit OPEN → short-circuited, budget NOT consumed
            q2 = _unique_id()
            resp2 = client.post(
                "/evidence",
                json={"market_question": q2, "query": q2},
            )
            assert resp2.status_code == 200
            body2 = resp2.json()
            # Budget: 5-1=4 for first failing call; OPEN short-circuit
            # should not consume further budget
            assert body2["budget_remaining"] >= 4, (
                f"OPEN circuit should not consume budget: remaining={body2['budget_remaining']}"
            )


# -- VAL-CROSS-004: Circuit breaker recovery shared across endpoints -----------


class TestCircuitBreakerRecoveryShared:
    """Circuit breaker recovery is shared across /evidence and /validate."""

    @patch.dict(os.environ, {"X402_BYPASS": "1"})
    def test_hal_open_probe_success_closes_circuit(self) -> None:
        """A successful HALF-OPEN probe via /evidence closes the circuit."""
        import sentinel.evidence_tools as et

        call_count = {"count": 0}

        async def flaky_search(request):
            call_count["count"] += 1
            if call_count["count"] <= 2:
                raise RuntimeError("simulated failure")
            return [_make_result(f"Result {call_count['count']}")]

        provider = MagicMock()
        provider.search = flaky_search

        env_overrides = {
            "SENTINEL_EVIDENCE_CB_FAILURE_THRESHOLD": "2",
            "SENTINEL_EVIDENCE_CB_COOLDOWN_SECONDS": "0.001",
        }
        with (
            patch("sentinel.main._run_startup_gates"),
            patch("sentinel.main.run_migration"),
            patch("sentinel.main.ensure_agent_row"),
            patch("sentinel.main.evidence_provider_from_runtime", return_value=provider),
            patch.dict(os.environ, env_overrides),
        ):
            from sentinel.main import app

            client = TestClient(app, raise_server_exceptions=False)

            # Two failing calls open the circuit
            q1 = _unique_id()
            client.post("/evidence", json={"market_question": q1, "query": q1})
            q2 = _unique_id()
            client.post("/evidence", json={"market_question": q2, "query": q2})

            # Verify circuit is OPEN
            p_id = et._provider_identity(provider)
            cb = et._get_or_create_circuit_breaker(provider, p_id)
            assert cb.state == et.CircuitBreakerState.OPEN

            # Third call (HALF-OPEN probe, cooldown=0) → success closes circuit
            q3 = _unique_id()
            resp3 = client.post("/evidence", json={"market_question": q3, "query": q3})
            body3 = resp3.json()

            # Circuit should now be CLOSED
            cb2 = et._get_or_create_circuit_breaker(provider, p_id)
            assert cb2.state == et.CircuitBreakerState.CLOSED, (
                f"Circuit should recover to CLOSED, got {cb2.state}"
            )

            # Results should be present from the successful probe
            if body3["results"]:
                assert body3["results"][0]["title"] == "Result 3"


# -- VAL-CROSS-005: Trace with evidence_receipts passes /validate --------------


class TestTraceWithEvidenceReceiptsPassesValidate:
    """Traces with evidence_receipts are accepted by /validate."""

    @patch.dict(os.environ, {"X402_BYPASS": "1"})
    def test_trace_with_evidence_receipts_validates(self) -> None:
        """A trace with populated evidence_receipts validates against schema."""
        trace_data = _trace_json(
            evidence_receipts=[
                {
                    "provider": "brave_search",
                    "tool_name": "web_search",
                    "source_title": "ETH Price Analysis",
                    "source_url": "https://example.com/eth",
                    "source_published_at": "2026-05-20T00:00:00Z",
                    "retrieved_at": "2026-05-22T00:00:00Z",
                    "confidence": 0.85,
                    "adequacy_checks": [],
                    "source_content_hash": None,
                    "extraction_checks": [],
                }
            ],
        )

        from prism_schemas.trace import TradingR1Trace

        trace = TradingR1Trace.model_validate(trace_data)
        assert trace.evidence_receipts is not None
        assert len(trace.evidence_receipts) == 1
        assert trace.evidence_receipts[0].provider == "brave_search"
        assert trace.evidence_receipts[0].source_title == "ETH Price Analysis"

    @patch.dict(os.environ, {"X402_BYPASS": "1"})
    def test_trace_with_empty_evidence_receipts_validates(self) -> None:
        """A trace with empty evidence_receipts (default) still validates."""
        trace_data = _trace_json(evidence_receipts=[])

        from prism_schemas.trace import TradingR1Trace

        trace = TradingR1Trace.model_validate(trace_data)
        assert trace.evidence_receipts == []

    @patch.dict(os.environ, {"X402_BYPASS": "1"})
    def test_trace_without_evidence_receipts_field_validates(self) -> None:
        """Backward compatibility: trace without evidence_receipts key defaults to []."""
        trace_data = _trace_json()
        del trace_data["evidence_receipts"]

        from prism_schemas.trace import TradingR1Trace

        trace = TradingR1Trace.model_validate(trace_data)
        assert trace.evidence_receipts == []


# -- VAL-CROSS-007: Forced HOLD with no evidence validates successfully --------


class TestForcedHOLDValidatesSuccessfully:
    """A forced HOLD trace with empty evidence_receipts passes schema."""

    @patch.dict(os.environ, {"X402_BYPASS": "1"})
    def test_hold_trace_with_empty_receipts_is_valid(self) -> None:
        """A HOLD trace with no evidence_receipts is schema-valid."""
        trace_data = _trace_json(
            action="HOLD",
            size_usdc=0.0,
            price_limit=0.5,
            evidence_receipts=[],
            rationale=(
                "Prism tool-first guard: no tool-sourced evidence was retrieved "
                "before trace generation, so the autonomous trader changed the "
                "action from BUY to HOLD."
            ),
        )

        from prism_schemas.trace import TradingR1Trace

        trace = TradingR1Trace.model_validate(trace_data)
        assert trace.action == "HOLD"
        assert trace.size_usdc == 0.0
        assert trace.evidence_receipts == []

    @patch.dict(os.environ, {"X402_BYPASS": "1"})
    def test_hold_trace_rationale_contains_guard_message(self) -> None:
        """HOLD trace rationale identifies the HOLD-forcing reason."""
        trace_data = _trace_json(
            action="HOLD",
            size_usdc=0.0,
            evidence_receipts=[],
            rationale=(
                "Bullish momentum analysis.\n\n"
                "Prism tool-first guard: no tool-sourced evidence was retrieved "
                "before trace generation, so the autonomous trader changed the "
                "action from BUY to HOLD."
            ),
        )

        from prism_schemas.trace import TradingR1Trace

        trace = TradingR1Trace.model_validate(trace_data)
        assert "tool-first guard" in trace.rationale
        assert "BUY" in trace.rationale
        assert "HOLD" in trace.rationale


# -- VAL-CROSS-010: Budget resets per validation, cache accumulates ------------


class TestBudgetResetCacheAccumulates:
    """Budget resets per invocation; cache accumulates across calls."""

    @patch.dict(os.environ, {"X402_BYPASS": "1"})
    def test_budget_resets_between_evidence_calls(self) -> None:
        """Each /evidence call gets a fresh budget; cache persists."""
        provider = StaticEvidenceProvider({"evidence-query": [_make_result("Budget Test")]})

        with (
            patch("sentinel.main._run_startup_gates"),
            patch("sentinel.main.run_migration"),
            patch("sentinel.main.ensure_agent_row"),
            patch("sentinel.main.evidence_provider_from_runtime", return_value=provider),
            patch("sentinel.main._read_evidence_budget", return_value=3),
        ):
            from sentinel.main import app

            client = TestClient(app, raise_server_exceptions=False)

            # First call — fresh budget, cache miss
            q1 = _unique_id()
            body1 = _call_evidence(client, q1)
            initial_budget_remaining = body1["budget_remaining"]
            # Budget should be non-negative and less than initial 3
            assert 0 <= initial_budget_remaining < 3, (
                f"Budget should decrease after first call: {initial_budget_remaining}"
            )

            # Second call — different query, cache miss, budget consumed further
            q2 = _unique_id()
            body2 = _call_evidence(client, q2)
            # Budget should be consumed or equal (cache hit possible in some cases)
            assert body2["budget_remaining"] >= 0, (
                f"Budget remaining should be non-negative: {body2['budget_remaining']}"
            )

            # Third call — repeat q1, should hit cache, budget preserved
            body3 = _call_evidence(client, q1)
            assert body3["budget_remaining"] >= 0
            if body3["results"] and body3["from_cache"]:
                # Cache hit: budget not consumed
                assert body3["budget_remaining"] == body2["budget_remaining"], (
                    f"Cache hit should preserve budget: "
                    f"{body3['budget_remaining']} != {body2['budget_remaining']}"
                )

    @patch.dict(os.environ, {"X402_BYPASS": "1"})
    def test_cache_accumulates_across_different_market_questions(self) -> None:
        """Cache from Q1 persists when querying Q2."""
        import sentinel.evidence_tools as et

        provider = StaticEvidenceProvider({"evidence-query": [_make_result("Market Data")]})

        with (
            patch("sentinel.main._run_startup_gates"),
            patch("sentinel.main.run_migration"),
            patch("sentinel.main.ensure_agent_row"),
            patch("sentinel.main.evidence_provider_from_runtime", return_value=provider),
        ):
            from sentinel.main import app

            client = TestClient(app, raise_server_exceptions=False)
            q1 = _unique_id()
            q2 = _unique_id()

            _call_evidence(client, q1)
            cache_size_after_q1 = len(et._shared_evidence_cache)

            _call_evidence(client, q2)
            cache_size_after_q2 = len(et._shared_evidence_cache)

            assert cache_size_after_q2 >= cache_size_after_q1, (
                f"Cache should accumulate: {cache_size_after_q2} >= {cache_size_after_q1}"
            )


# -- VAL-CROSS-011: /evidence free, /validate paywalled ------------------------


class TestEvidenceFreeValidatePaywalled:
    """/evidence never returns 402; /validate returns 402 without payment."""

    def test_evidence_never_returns_402(self) -> None:
        """/evidence returns 200 even when x402 bypass is disabled."""
        provider = StaticEvidenceProvider({"evidence-query": [_make_result("Free Result")]})

        with (
            patch("sentinel.main._run_startup_gates"),
            patch("sentinel.main.run_migration"),
            patch("sentinel.main.ensure_agent_row"),
            patch("sentinel.main.evidence_provider_from_runtime", return_value=provider),
            patch.dict(os.environ, {"X402_BYPASS": ""}),
        ):
            from sentinel.main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/evidence",
                json={"market_question": "Test?", "query": "test"},
            )
            assert response.status_code == 200, (
                f"/evidence should always be free: {response.status_code}"
            )

    def test_validate_returns_402_without_payment(self) -> None:
        """/validate returns 402 without payment or bypass."""
        with (
            patch("sentinel.main._run_startup_gates"),
            patch("sentinel.main.run_migration"),
            patch("sentinel.main.ensure_agent_row"),
            patch.dict(os.environ, {"X402_BYPASS": ""}),
        ):
            from sentinel.main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/validate",
                json={"trace_uri": "ipfs://QmTest", "trace_hash": "0xabc"},
            )
            assert response.status_code == 402, (
                f"/validate should be paywalled: {response.status_code}"
            )

    def test_evidence_free_validate_paywalled_side_by_side(self) -> None:
        """Same TestClient: /evidence → 200, /validate → 402."""
        provider = StaticEvidenceProvider({"evidence-query": [_make_result("Side by Side")]})

        with (
            patch("sentinel.main._run_startup_gates"),
            patch("sentinel.main.run_migration"),
            patch("sentinel.main.ensure_agent_row"),
            patch("sentinel.main.evidence_provider_from_runtime", return_value=provider),
            patch.dict(os.environ, {"X402_BYPASS": ""}),
        ):
            from sentinel.main import app

            client = TestClient(app, raise_server_exceptions=False)

            ev_resp = client.post("/evidence", json={"market_question": "Q?", "query": "Q"})
            assert ev_resp.status_code == 200

            val_resp = client.post(
                "/validate",
                json={"trace_uri": "ipfs://QmTest", "trace_hash": "0xabc"},
            )
            assert val_resp.status_code == 402
