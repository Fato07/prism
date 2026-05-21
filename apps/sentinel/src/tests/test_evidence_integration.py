"""Evidence wrapper integration tests.

Tests for VAL-SENREL-028 through VAL-SENREL-037 covering the full wrapper
stack: CircuitBreakerAware → CacheAware → BudgetAware → underlying provider.
"""

from __future__ import annotations

import uuid

import pytest
from cachetools import TTLCache
from prism_schemas.verdict import AdversarialChallenge

from sentinel.evidence_tools import (
    BudgetAwareEvidenceProvider,
    CacheAwareEvidenceProvider,
    CircuitBreakerAwareEvidenceProvider,
    CircuitBreakerState,
    EvidenceProvider,
    EvidenceSearchRequest,
    EvidenceSearchResult,
    NoopEvidenceProvider,
    StaticEvidenceProvider,
    _get_or_create_circuit_breaker,
    _provider_identity,
    build_evidence_provider_stack,
    evidence_provider_from_runtime,
)

# -- Reset shared state before each test to avoid cross-test pollution ----------


@pytest.fixture(autouse=True)
def _reset_shared_cache() -> None:
    """Reset module-level shared cache before each test."""
    import sentinel.evidence_tools as et

    et._shared_evidence_cache = TTLCache(maxsize=256, ttl=300)


@pytest.fixture(autouse=True)
def _reset_cb_registry() -> None:
    """Reset module-level circuit breaker registry before each test."""
    import sentinel.evidence_tools as et

    et._circuit_breaker_registry.clear()


def _unique_id() -> str:
    """Return a short unique string for test isolation."""
    return uuid.uuid4().hex[:8]


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
    query: str | None = None,
) -> EvidenceSearchRequest:
    chal = challenge or _challenge()
    q = query if query is not None else f"{_unique_id()}-{market_question}"
    return EvidenceSearchRequest(
        market_question=market_question,
        challenge=chal,
        query=q,
    )


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


class CountingProvider:
    """Provider that counts calls."""

    def __init__(
        self,
        results: list[EvidenceSearchResult] | None = None,
        results_by_challenge_id: dict[str, list[EvidenceSearchResult]] | None = None,
    ) -> None:
        self._results = results or []
        self._results_by_challenge_id = results_by_challenge_id or {}
        self._calls = 0
        self._call_requests: list[EvidenceSearchRequest] = []

    async def search(self, request: EvidenceSearchRequest) -> list[EvidenceSearchResult]:
        self._calls += 1
        self._call_requests.append(request)
        cid = request.challenge.id
        if cid in self._results_by_challenge_id:
            return list(self._results_by_challenge_id[cid])
        return list(self._results)

    @property
    def calls(self) -> int:
        return self._calls


class FailingProvider:
    """Provider that raises on every call."""

    def __init__(self, exc_type: type[Exception] | None = None) -> None:
        self._exc_type = exc_type or RuntimeError
        self._calls = 0

    async def search(self, request: EvidenceSearchRequest) -> list[EvidenceSearchResult]:
        self._calls += 1
        raise self._exc_type("simulated provider failure")

    @property
    def calls(self) -> int:
        return self._calls


# -- VAL-SENREL-028: Layering order — CB(Cache(Budget(Provider))) --------------


class TestLayeringOrder:
    """Wrappers are composed: CB(Cache(Budget(Provider))) (VAL-SENREL-028)."""

    @pytest.mark.asyncio
    async def test_cache_hit_bypasses_budget(self) -> None:
        """Cache hit returns without consuming budget."""
        uid = _unique_id()
        inner = CountingProvider([_make_result()])

        budget = BudgetAwareEvidenceProvider(inner, budget=2)
        cache = CacheAwareEvidenceProvider(budget, provider_id="test_p")
        cb = CircuitBreakerAwareEvidenceProvider(cache, provider_id="test_p", failure_threshold=3)

        r1 = await cb.search(_request(query=f"q-{uid}"))
        assert len(r1) == 1
        assert inner.calls == 1
        assert budget.remaining == 1

        r2 = await cb.search(_request(query=f"q-{uid}"))
        assert len(r2) == 1
        assert inner.calls == 1
        assert budget.remaining == 1

    @pytest.mark.asyncio
    async def test_circuit_open_bypasses_budget(self) -> None:
        """Circuit-open returns [] without consuming budget."""
        uid = _unique_id()
        inner = FailingProvider()

        budget = BudgetAwareEvidenceProvider(inner, budget=10)
        cache = CacheAwareEvidenceProvider(budget, provider_id=f"test-{uid}")
        cb = CircuitBreakerAwareEvidenceProvider(
            cache, provider_id=f"test-{uid}", failure_threshold=1
        )

        await cb.search(_request(query=f"q1-{uid}"))
        assert cb.state is CircuitBreakerState.OPEN
        assert budget.remaining == 9

        budget_before = budget.remaining
        r2 = await cb.search(_request(query=f"q2-{uid}"))
        assert r2 == []
        assert budget.remaining == budget_before

    @pytest.mark.asyncio
    async def test_protocol_conformance(self) -> None:
        """Full stack implements EvidenceProvider protocol."""
        inner = CountingProvider([_make_result()])
        stack = build_evidence_provider_stack(inner, budget=5)

        assert hasattr(stack, "search")
        assert callable(stack.search)

        results = await stack.search(_request())
        assert len(results) == 1


# -- VAL-SENREL-029: Budget exhaustion still allows cache hits ------------------


class TestBudgetExhaustionAllowsCacheHits:
    """Budget exhaustion still allows cache hits (VAL-SENREL-029)."""

    @pytest.mark.asyncio
    async def test_cache_hit_after_budget_exhaustion(self) -> None:
        """After budget exhausted, cached queries still return results."""
        uid = _unique_id()
        inner = CountingProvider(
            results_by_challenge_id={
                "ch-A": [_make_result("ch-A")],
                "ch-B": [_make_result("ch-B")],
            }
        )

        budget = BudgetAwareEvidenceProvider(inner, budget=1)
        cache = CacheAwareEvidenceProvider(budget, provider_id=f"test-{uid}")
        cb = CircuitBreakerAwareEvidenceProvider(
            cache, provider_id=f"test-{uid}", failure_threshold=3
        )

        r_a = await cb.search(_request(_challenge("ch-A"), query=f"qA-{uid}"))
        assert len(r_a) == 1
        assert budget.remaining == 0

        r_b = await cb.search(_request(_challenge("ch-B"), query=f"qB-{uid}"))
        assert r_b == []

        r_a2 = await cb.search(_request(_challenge("ch-A"), query=f"qA-{uid}"))
        assert len(r_a2) == 1
        assert inner.calls == 1


# -- VAL-SENREL-030: Full wrapper stack implements EvidenceProvider protocol ----


class TestFullStackProtocol:
    """Full wrapper stack is an EvidenceProvider (VAL-SENREL-030)."""

    @pytest.mark.asyncio
    async def test_stack_interchangeable_with_bare_provider(self) -> None:
        """Composed wrapper can be used anywhere a bare provider is expected."""
        inner = CountingProvider([_make_result()])
        stack = build_evidence_provider_stack(inner, budget=5)

        async def use_provider(p: EvidenceProvider) -> list[EvidenceSearchResult]:
            return await p.search(_request())

        results = await use_provider(stack)
        assert len(results) == 1
        assert results[0].provider == "test_provider"

    @pytest.mark.asyncio
    async def test_stack_with_static_provider(self) -> None:
        """StaticEvidenceProvider works through full stack."""
        inner = StaticEvidenceProvider({"ch-1": [_make_result("ch-1")]})
        stack = build_evidence_provider_stack(inner, budget=5)

        results = await stack.search(_request(_challenge("ch-1")))
        assert len(results) == 1
        assert results[0].title == "Fed Rate Decision Analysis"


# -- VAL-SENREL-031: Successful calls through circuit breaker populate cache ----


class TestSuccessfulCallsPopulateCache:
    """Successful calls through circuit breaker populate cache (VAL-SENREL-031)."""

    @pytest.mark.asyncio
    async def test_successful_call_cached(self) -> None:
        """Fresh cache, CLOSED circuit → success → result cached → subsequent hit."""
        uid = _unique_id()
        inner = CountingProvider([_make_result()])

        budget = BudgetAwareEvidenceProvider(inner, budget=5)
        cache = CacheAwareEvidenceProvider(budget, provider_id=f"test-{uid}")
        cb = CircuitBreakerAwareEvidenceProvider(
            cache, provider_id=f"test-{uid}", failure_threshold=3
        )

        r1 = await cb.search(_request(query=f"q-{uid}"))
        assert len(r1) == 1
        assert inner.calls == 1
        assert cache.misses == 1
        assert cache.hits == 0

        r2 = await cb.search(_request(query=f"q-{uid}"))
        assert len(r2) == 1
        assert inner.calls == 1
        assert cache.hits == 1
        assert cb.state is CircuitBreakerState.CLOSED


# -- VAL-SENREL-032: Failed provider calls do NOT populate cache ----------------


class TestFailedCallsNoCache:
    """Failed provider calls do NOT populate cache (VAL-SENREL-032)."""

    @pytest.mark.asyncio
    async def test_failed_call_not_in_cache_verified(self) -> None:
        """Failed call's [] is NOT cached — next call re-invokes provider."""
        uid = _unique_id()
        call_count = [0]

        class FailOnceThenSucceed:
            async def search(self, request: EvidenceSearchRequest) -> list[EvidenceSearchResult]:
                call_count[0] += 1
                if call_count[0] == 1:
                    raise RuntimeError("first call fails")
                return [_make_result()]

        inner = FailOnceThenSucceed()
        budget = BudgetAwareEvidenceProvider(inner, budget=10)
        cache = CacheAwareEvidenceProvider(budget, provider_id=f"test-{uid}")
        cb = CircuitBreakerAwareEvidenceProvider(
            cache, provider_id=f"test-{uid}", failure_threshold=3
        )

        r1 = await cb.search(_request(query=f"q-{uid}"))
        assert r1 == []
        assert cb.consecutive_failures == 1

        r2 = await cb.search(_request(query=f"q-{uid}"))
        assert len(r2) == 1
        assert call_count[0] == 2

        r3 = await cb.search(_request(query=f"q-{uid}"))
        assert len(r3) == 1
        assert call_count[0] == 2  # cached


# -- VAL-SENREL-033: Cache is shared across validations -------------------------


class TestCacheSharedAcrossValidations:
    """Cache persistent across validations (VAL-SENREL-033)."""

    @pytest.mark.asyncio
    async def test_cache_persists_across_validation_instances(self) -> None:
        """Cache entries survive across separate validation contexts."""
        uid = _unique_id()

        inner1 = CountingProvider([_make_result()])
        stack1 = build_evidence_provider_stack(inner1, budget=5)

        r1 = await stack1.search(_request(query=f"shared-{uid}"))
        assert len(r1) == 1
        assert inner1.calls == 1

        inner2 = CountingProvider([_make_result()])
        stack2 = build_evidence_provider_stack(inner2, budget=5)

        r2 = await stack2.search(_request(query=f"shared-{uid}"))
        assert len(r2) == 1
        assert inner2.calls == 0  # cache hit


# -- VAL-SENREL-034: Circuit breaker state persists across validations ----------


class TestCircuitBreakerPersistsAcrossValidations:
    """Circuit breaker state persists across validations (VAL-SENREL-034)."""

    @pytest.mark.asyncio
    async def test_cb_state_persists(self) -> None:
        """Open circuit in validation 1 → still OPEN in validation 2."""
        uid = _unique_id()
        provider_id = f"persist-{uid}"

        cb1 = CircuitBreakerAwareEvidenceProvider(
            FailingProvider(), provider_id, failure_threshold=1
        )
        from sentinel.evidence_tools import _circuit_breaker_registry

        _circuit_breaker_registry[provider_id] = cb1

        await cb1.search(_request())
        assert cb1.state is CircuitBreakerState.OPEN

        cb2 = _get_or_create_circuit_breaker(CountingProvider([_make_result()]), provider_id)
        assert cb2 is cb1
        assert cb2.state is CircuitBreakerState.OPEN


# -- VAL-SENREL-035: Budget exhaustion produces structurally valid verdict ------


class TestBudgetExhaustionValidVerdict:
    """Budget exhaustion does not affect verdict structure (VAL-SENREL-035)."""

    def test_zero_budget_does_not_break_verdict_structure(self) -> None:
        """Budget=0 provider can still be used in resolution flow."""
        inner = CountingProvider([])
        stack = build_evidence_provider_stack(inner, budget=0)

        assert hasattr(stack, "search")
        assert callable(stack.search)

    @pytest.mark.asyncio
    async def test_budget_zero_stack_returns_empty(self) -> None:
        """Budget=0 stack returns [] for all searches."""
        uid = _unique_id()
        inner = CountingProvider([_make_result()])
        stack = build_evidence_provider_stack(inner, budget=0)

        for i in range(3):
            results = await stack.search(_request(query=f"zq-{uid}-{i}"))
            assert results == []

        assert inner.calls == 0


# -- VAL-SENREL-036: NoopEvidenceProvider skips wrappers ------------------------


class TestNoopSkipsWrappers:
    """NoopEvidenceProvider skips wrappers (VAL-SENREL-036)."""

    @pytest.mark.asyncio
    async def test_noop_returned_bare_from_build_stack(self) -> None:
        """NoopEvidenceProvider is returned without wrappers."""
        noop = NoopEvidenceProvider()
        result = build_evidence_provider_stack(noop, budget=5)

        assert result is noop
        assert isinstance(result, NoopEvidenceProvider)

    @pytest.mark.asyncio
    async def test_noop_returned_bare_from_runtime(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """evidence_provider_from_runtime returns Noop bare."""
        monkeypatch.setenv("PRISM_EVIDENCE_PROVIDER", "noop")
        monkeypatch.setenv("PRISM_EVIDENCE_DB_CONNECTORS", "0")
        provider = evidence_provider_from_runtime()
        assert isinstance(provider, NoopEvidenceProvider)
        assert type(provider).__name__ == "NoopEvidenceProvider"


# -- VAL-SENREL-037: StaticEvidenceProvider in tests bypasses wrappers ----------


class TestStaticProviderBypassesWrappers:
    """StaticEvidenceProvider in tests bypasses wrappers (VAL-SENREL-037)."""

    @pytest.mark.asyncio
    async def test_static_provider_works_without_wrappers(self) -> None:
        """StaticEvidenceProvider direct use works without wrapper interference."""
        inner = StaticEvidenceProvider({"ch-1": [_make_result("ch-1")]})

        results = await inner.search(_request(_challenge("ch-1")))
        assert len(results) == 1
        assert results[0].title == "Fed Rate Decision Analysis"

    @pytest.mark.asyncio
    async def test_static_provider_through_build_stack(self) -> None:
        """StaticEvidenceProvider through build_stack works correctly."""
        uid = _unique_id()
        inner = StaticEvidenceProvider({"ch-1": [_make_result("ch-1")]})
        stack = build_evidence_provider_stack(inner, budget=5)

        results = await stack.search(_request(_challenge("ch-1"), query=f"q-{uid}"))
        assert len(results) == 1
        assert results[0].title == "Fed Rate Decision Analysis"

    @pytest.mark.asyncio
    async def test_budget_applied_to_static_provider(self) -> None:
        """Budget wrapping still works with StaticEvidenceProvider."""
        uid = _unique_id()
        inner = StaticEvidenceProvider({"ch-1": [_make_result("ch-1")]})
        stack = build_evidence_provider_stack(inner, budget=2)

        r1 = await stack.search(_request(_challenge("ch-1"), query=f"qA-{uid}"))
        assert len(r1) == 1

        r2 = await stack.search(_request(_challenge("ch-1"), query=f"qB-{uid}"))
        assert len(r2) == 1

        r3 = await stack.search(_request(_challenge("ch-1"), query=f"qC-{uid}"))
        assert r3 == []


# -- Additional integration: provider identity, stack behavior ------------------


class TestProviderIdentity:
    """_provider_identity correctly identifies providers."""

    def test_known_providers(self) -> None:
        """Known providers return correct identity."""
        from sentinel.evidence_tools import BraveSearchEvidenceProvider

        brave = BraveSearchEvidenceProvider(api_key="test_key")
        assert _provider_identity(brave) == "brave_search"

    def test_noop_identity(self) -> None:
        """Noop returns 'noop'."""
        noop = NoopEvidenceProvider()
        assert _provider_identity(noop) == "noop"

    def test_static_identity(self) -> None:
        """Static returns 'static'."""
        static = StaticEvidenceProvider({})
        assert _provider_identity(static) == "static"


class TestBuildEvidenceProviderStack:
    """build_evidence_provider_stack creates correctly composed stacks."""

    @pytest.mark.asyncio
    async def test_stack_honors_budget(self) -> None:
        """Stack respects budget limits."""
        uid = _unique_id()
        inner = CountingProvider([_make_result()])
        stack = build_evidence_provider_stack(inner, budget=2)

        await stack.search(_request(query=f"a-{uid}"))
        await stack.search(_request(query=f"b-{uid}"))

        r3 = await stack.search(_request(query=f"c-{uid}"))
        assert r3 == []
        assert inner.calls == 2

    @pytest.mark.asyncio
    async def test_stack_caches_results(self) -> None:
        """Stack caches results through CacheAware layer."""
        uid = _unique_id()
        inner = CountingProvider([_make_result()])
        stack = build_evidence_provider_stack(inner, budget=5)

        await stack.search(_request(query=f"cq-{uid}"))
        assert inner.calls == 1

        await stack.search(_request(query=f"cq-{uid}"))
        assert inner.calls == 1

    @pytest.mark.asyncio
    async def test_stack_circuit_breaker_opens_on_failures(self) -> None:
        """Stack circuit breaker opens after consecutive failures."""
        uid = _unique_id()
        inner = FailingProvider()
        stack = build_evidence_provider_stack(inner, budget=20)

        for i in range(3):
            r = await stack.search(_request(query=f"fq-{uid}-{i}"))
            assert r == []

        assert isinstance(stack, CircuitBreakerAwareEvidenceProvider)
        assert stack.state is CircuitBreakerState.OPEN

        calls_before = inner.calls
        r4 = await stack.search(_request(query=f"fq-{uid}-4"))
        assert r4 == []
        assert inner.calls == calls_before
