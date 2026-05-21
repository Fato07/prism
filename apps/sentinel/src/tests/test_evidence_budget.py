"""Evidence budget wrapper tests.

Tests for VAL-SENREL-001 through VAL-SENREL-008.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from prism_schemas.trace import Evidence, ThesisStep, TradingR1Trace
from prism_schemas.verdict import AdversarialChallenge, SentinelVerdict

from sentinel.evidence_tools import (
    BudgetAwareEvidenceProvider,
    EvidenceSearchRequest,
    EvidenceSearchResult,
    NoopEvidenceProvider,
    StaticEvidenceProvider,
    _read_evidence_budget,
)

# -- helpers ------------------------------------------------------------------


def _challenge(challenge_id: str = "sys-temporal-stale-evidence") -> AdversarialChallenge:
    return AdversarialChallenge(
        id=challenge_id,
        type="temporal",
        severity="blocking",
        question="Evidence is stale.",
        required_resolution="Retrieve current evidence or revise to HOLD.",
        blocking_pass=True,
        claim_ref="evidence[0]",
    )


def _request(
    challenge: AdversarialChallenge | None = None,
    market_question: str = "Will the Fed cut rates by July 2026?",
) -> EvidenceSearchRequest:
    from sentinel.evidence_tools import query_for_challenge

    chal = challenge or _challenge()
    return EvidenceSearchRequest(
        market_question=market_question,
        challenge=chal,
        query=query_for_challenge(market_question, chal),
    )


def _basic_trace() -> TradingR1Trace:
    return TradingR1Trace(
        trace_id="trace-budget-t1",
        agent_id=1,
        market_id="poly-test",
        market_question="Will the Fed cut rates by July 2026?",
        thesis=[
            ThesisStep(
                proposition="Current data supports easing.",
                supporting_evidence_ids=[0],
                risk_factors=["Inflation rebound"],
            )
        ],
        evidence=[
            Evidence(
                source="BLS",
                claim="Recent CPI came in below expectations.",
                confidence=0.85,
                timestamp=datetime(2026, 5, 1, tzinfo=UTC),
            )
        ],
        raw_probability=0.62,
        volatility_adjustment=-0.03,
        final_probability=0.59,
        action="BUY",
        size_usdc=1.0,
        price_limit=0.59,
        rationale="Recent official data supports a small position.",
        model_family="anthropic-claude",
        model_name="claude-sonnet-4-20250514",
        created_at=datetime(2026, 5, 16, tzinfo=UTC),
    )


def _basic_verdict(
    challenges: list[AdversarialChallenge] | None = None,
    max_rounds: int = 3,
) -> SentinelVerdict:
    return SentinelVerdict(
        request_hash="request-budget",
        trace_id="trace-budget-t1",
        sentinel_agent_id=2,
        evidence_challenges=["Evidence needs a current primary-source check."],
        thesis_challenges=["Thesis depends on data freshness."],
        calibration_critique="Probability is acceptable if current data is verified.",
        verdict_score=50,
        verdict_label="WARN",
        dialogue_messages=[{"role": "sentinel", "content": "Need current evidence."}],
        structured_challenges=challenges
        or [
            AdversarialChallenge(
                id="sys-temporal-stale-evidence",
                type="temporal",
                severity="blocking",
                question="The market claim relies on stale evidence.",
                required_resolution="Retrieve current evidence or revise to HOLD.",
                blocking_pass=True,
                claim_ref="evidence[0]",
            )
        ],
        model_family="openai-gpt",
        model_name="gpt-4o-mini",
        created_at=datetime(2026, 5, 16, tzinfo=UTC),
    )


class CountingProvider:
    """Provider that counts how many times search() was called.

    Supports two modes:
    - If results_by_challenge_id is provided, returns results keyed by challenge ID.
    - Otherwise returns the same flat results list for every call.
    """

    def __init__(
        self,
        results: list[EvidenceSearchResult] | None = None,
        results_by_challenge_id: dict[str, list[EvidenceSearchResult]] | None = None,
    ) -> None:
        self._results = results or []
        self._results_by_challenge_id = results_by_challenge_id or {}
        self._calls = 0
        self._call_requests: list[EvidenceSearchRequest] = []

    async def search(
        self, request: EvidenceSearchRequest
    ) -> list[EvidenceSearchResult]:
        self._calls += 1
        self._call_requests.append(request)
        cid = request.challenge.id
        if cid in self._results_by_challenge_id:
            return list(self._results_by_challenge_id[cid])
        return list(self._results)

    @property
    def calls(self) -> int:
        return self._calls


def _make_result(challenge_id: str = "sys-temporal-stale-evidence") -> EvidenceSearchResult:
    return EvidenceSearchResult(
        title="Fed Rate Decision Analysis",
        url="https://www.federalreserve.gov/monetarypolicy/fomc.htm",
        snippet=(
            "The Federal Open Market Committee decided to maintain the target range "
            "for the federal funds rate at 4.25 to 4.5 percent, citing continued "
            "progress on inflation and a solid labor market."
        ),
        provider="test_provider",
        published_at="2026-05-15T00:00:00",
        confidence=0.85,
    )


# -- VAL-SENREL-008: BudgetAwareEvidenceProvider protocol conformance ---------


class TestBudgetAwareEvidenceProviderProtocol:
    """BudgetAwareEvidenceProvider wraps any EvidenceProvider (VAL-SENREL-008)."""

    @pytest.mark.asyncio
    async def test_delegates_when_budget_positive(self) -> None:
        """Budget > 0 → delegates to underlying provider."""
        inner = StaticEvidenceProvider(
            {"ch-1": [_make_result("ch-1")]}
        )
        wrapper = BudgetAwareEvidenceProvider(inner, budget=5)

        results = await wrapper.search(
            _request(_challenge("ch-1"))
        )

        assert len(results) == 1
        assert results[0].provider == "test_provider"
        assert wrapper.remaining == 4

    @pytest.mark.asyncio
    async def test_skips_when_budget_zero(self) -> None:
        """Budget = 0 → returns [], provider not called."""
        inner = CountingProvider([_make_result()])
        wrapper = BudgetAwareEvidenceProvider(inner, budget=0)

        results = await wrapper.search(_request())

        assert results == []
        assert inner.calls == 0
        assert wrapper.remaining == 0

    @pytest.mark.asyncio
    async def test_conforms_to_evidence_provider_protocol(self) -> None:
        """BudgetAwareEvidenceProvider implements EvidenceProvider protocol."""
        inner = NoopEvidenceProvider()
        wrapper = BudgetAwareEvidenceProvider(inner, budget=3)

        # Protocol check: has async search() with correct signature
        assert hasattr(wrapper, "search")
        assert callable(wrapper.search)

    @pytest.mark.asyncio
    async def test_composable_with_static_provider(self) -> None:
        """BudgetAwareEvidenceProvider wraps StaticEvidenceProvider without errors."""
        inner = StaticEvidenceProvider({"ch-1": [_make_result("ch-1")]})
        wrapper = BudgetAwareEvidenceProvider(inner, budget=2)

        r1 = await wrapper.search(_request(_challenge("ch-1")))
        assert len(r1) == 1
        assert wrapper.remaining == 1

        r2 = await wrapper.search(_request(_challenge("ch-2")))
        assert len(r2) == 0  # ch-2 has no results in provider
        assert wrapper.remaining == 0  # still counts as budget unit

    @pytest.mark.asyncio
    async def test_remaining_and_budget_properties(self) -> None:
        """Properties report budget state correctly."""
        inner = NoopEvidenceProvider()
        wrapper = BudgetAwareEvidenceProvider(inner, budget=10)

        assert wrapper.budget == 10
        assert wrapper.remaining == 10

        await wrapper.search(_request())
        assert wrapper.remaining == 9
        assert wrapper.budget == 10  # budget is immutable cap


# -- VAL-SENREL-007: Each search() counts as one budget unit ------------------


class TestEachSearchCountsAsOneUnit:
    """Each provider.search() counts as one regardless of result count (VAL-SENREL-007)."""

    @pytest.mark.asyncio
    async def test_non_empty_results_decrements_budget(self) -> None:
        """Result list with items decrements budget by 1."""
        inner = StaticEvidenceProvider({"ch-1": [_make_result("ch-1")]})
        wrapper = BudgetAwareEvidenceProvider(inner, budget=5)

        results = await wrapper.search(_request(_challenge("ch-1")))
        assert len(results) == 1
        assert wrapper.remaining == 4

    @pytest.mark.asyncio
    async def test_empty_results_still_counts(self) -> None:
        """Empty result list still decrements budget by 1."""
        inner = CountingProvider([])  # returns empty list
        wrapper = BudgetAwareEvidenceProvider(inner, budget=3)

        results = await wrapper.search(_request())
        assert results == []
        assert inner.calls == 1
        assert wrapper.remaining == 2


# -- VAL-SENREL-001: Internal budget enforcement ------------------------------


class TestInternalBudgetEnforcement:
    """Per-validation internal budget enforcement (VAL-SENREL-001)."""

    @pytest.mark.asyncio
    async def test_caps_calls_at_internal_budget(self) -> None:
        """5 challenges, budget=3 → exactly 3 calls, 2 skipped."""
        inner = CountingProvider([_make_result(f"ch-{i}") for i in range(3)])
        wrapper = BudgetAwareEvidenceProvider(inner, budget=3)

        # 5 calls, budget=3
        for i in range(5):
            request = _request(_challenge(f"ch-{i}"))
            await wrapper.search(request)

        assert inner.calls == 3
        assert wrapper.remaining == 0

    @pytest.mark.asyncio
    async def test_budget_exhausted_logged(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Budget exhaustion logs 'budget_exhausted'."""
        inner = CountingProvider([_make_result()])
        wrapper = BudgetAwareEvidenceProvider(inner, budget=1)

        # First call consumes budget
        await wrapper.search(_request())

        # Second call hits exhaustion - structlog outputs to stdout
        results = await wrapper.search(_request())

        assert results == []
        captured = capsys.readouterr().out
        assert "budget_exhausted" in captured


# -- VAL-SENREL-002: Paid budget enforcement ----------------------------------


class TestPaidBudgetEnforcement:
    """Per-validation paid budget enforcement (VAL-SENREL-002)."""

    @pytest.mark.asyncio
    async def test_caps_calls_at_paid_budget(self) -> None:
        """12 challenges, paid budget=10 → exactly 10 calls, 2 skipped."""
        inner = CountingProvider([_make_result(f"ch-{i}") for i in range(10)])
        wrapper = BudgetAwareEvidenceProvider(inner, budget=10)

        for i in range(12):
            request = _request(_challenge(f"ch-{i}"))
            await wrapper.search(request)

        assert inner.calls == 10
        assert wrapper.remaining == 0


# -- VAL-SENREL-003: Budget resets between validations -----------------------


class TestBudgetResetsBetweenValidations:
    """Budget counter resets between validations (VAL-SENREL-003)."""

    @pytest.mark.asyncio
    async def test_second_validation_gets_fresh_budget(self) -> None:
        """Two sequential BudgetAwareEvidenceProviders get independent budgets."""
        # First validation
        inner1 = CountingProvider([_make_result()])
        wrapper1 = BudgetAwareEvidenceProvider(inner1, budget=3)
        for _ in range(3):
            await wrapper1.search(_request())
        assert wrapper1.remaining == 0
        assert inner1.calls == 3

        # Second validation — new wrapper, fresh budget
        inner2 = CountingProvider([_make_result()])
        wrapper2 = BudgetAwareEvidenceProvider(inner2, budget=3)
        for _ in range(3):
            await wrapper2.search(_request())
        assert wrapper2.remaining == 0
        assert inner2.calls == 3


# -- VAL-SENREL-004: Budget exhaustion mid-round ------------------------------


class TestBudgetExhaustionMidRound:
    """Budget exhaustion mid-round (VAL-SENREL-004)."""

    @pytest.mark.asyncio
    async def test_challenges_skipped_after_exhaustion(self) -> None:
        """4 challenges, budget=2 → first 2 get evidence, last 2 skipped."""
        inner = CountingProvider(
            results_by_challenge_id={
                f"ch-{i}": [_make_result(f"ch-{i}")] for i in range(4)
            }
        )
        wrapper = BudgetAwareEvidenceProvider(inner, budget=2)

        results: list[list[EvidenceSearchResult]] = []
        for i in range(4):
            r = await wrapper.search(_request(_challenge(f"ch-{i}")))
            results.append(r)

        # First 2: got results
        assert len(results[0]) == 1
        assert len(results[1]) == 1
        # Last 2: empty (skipped)
        assert results[2] == []
        assert results[3] == []
        assert inner.calls == 2


# -- VAL-SENREL-005: Budget distinction internal vs paid ---------------------


class TestBudgetDistinction:
    """Budget distinction between internal and paid callers (VAL-SENREL-005)."""

    def test_internal_env_var_defaults_to_3(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SENTINEL_EVIDENCE_BUDGET_INTERNAL defaults to 3."""
        monkeypatch.delenv("SENTINEL_EVIDENCE_BUDGET_INTERNAL", raising=False)
        budget = _read_evidence_budget(
            "SENTINEL_EVIDENCE_BUDGET_INTERNAL", default=3
        )
        assert budget == 3

    def test_paid_env_var_defaults_to_10(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SENTINEL_EVIDENCE_BUDGET_PAID defaults to 10."""
        monkeypatch.delenv("SENTINEL_EVIDENCE_BUDGET_PAID", raising=False)
        budget = _read_evidence_budget(
            "SENTINEL_EVIDENCE_BUDGET_PAID", default=10
        )
        assert budget == 10

    def test_custom_internal_budget_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Custom env var value is used."""
        monkeypatch.setenv("SENTINEL_EVIDENCE_BUDGET_INTERNAL", "5")
        budget = _read_evidence_budget(
            "SENTINEL_EVIDENCE_BUDGET_INTERNAL", default=3
        )
        assert budget == 5

    def test_custom_paid_budget_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Custom env var value is used for paid."""
        monkeypatch.setenv("SENTINEL_EVIDENCE_BUDGET_PAID", "20")
        budget = _read_evidence_budget(
            "SENTINEL_EVIDENCE_BUDGET_PAID", default=10
        )
        assert budget == 20


# -- VAL-SENREL-006: Zero or invalid budget defaults to 0 ---------------------


class TestInvalidBudgetDefaults:
    """Zero or invalid budget defaults to no evidence calls (VAL-SENREL-006)."""

    def test_zero_budget_returns_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Budget '0' → 0."""
        monkeypatch.setenv("SENTINEL_EVIDENCE_BUDGET_INTERNAL", "0")
        budget = _read_evidence_budget(
            "SENTINEL_EVIDENCE_BUDGET_INTERNAL", default=3
        )
        assert budget == 0

    def test_negative_budget_returns_zero(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Budget '-1' → 0 with warning."""
        monkeypatch.setenv("SENTINEL_EVIDENCE_BUDGET_INTERNAL", "-1")
        budget = _read_evidence_budget(
            "SENTINEL_EVIDENCE_BUDGET_INTERNAL", default=3
        )
        assert budget == 0
        captured = capsys.readouterr().out
        assert "invalid_evidence_budget_negative" in captured

    def test_non_numeric_budget_returns_zero(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Budget 'abc' → 0 with warning."""
        monkeypatch.setenv("SENTINEL_EVIDENCE_BUDGET_INTERNAL", "abc")
        budget = _read_evidence_budget(
            "SENTINEL_EVIDENCE_BUDGET_INTERNAL", default=3
        )
        assert budget == 0
        captured = capsys.readouterr().out
        assert "invalid_evidence_budget_non_numeric" in captured

    @pytest.mark.asyncio
    async def test_zero_budget_no_calls(self) -> None:
        """Budget=0 → zero provider calls, returns []."""
        inner = CountingProvider([_make_result()])
        wrapper = BudgetAwareEvidenceProvider(inner, budget=0)

        results = await wrapper.search(_request())
        assert results == []
        assert inner.calls == 0
        assert wrapper.remaining == 0


# -- Integration: budget-aware provider through resolution loop ---------------


class TestBudgetIntegration:
    """Integration tests for budget-aware provider in resolution loop.

    These tests verify that the verdict is still produced even when
    the budget is exhausted.
    """

    @pytest.mark.asyncio
    async def test_budget_zero_no_provider_calls(self) -> None:
        """Budget=0 provider → provider is never called, returns []."""
        inner = CountingProvider([_make_result()])
        wrapper = BudgetAwareEvidenceProvider(inner, budget=0)

        for i in range(5):
            results = await wrapper.search(_request(_challenge(f"ch-{i}")))
            assert results == []

        assert inner.calls == 0
        assert wrapper.remaining == 0
