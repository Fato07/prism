"""Evidence cache wrapper tests.

Tests for VAL-SENREL-009 through VAL-SENREL-017.
"""

from __future__ import annotations

import time

import pytest
from prism_schemas.verdict import AdversarialChallenge

from sentinel.evidence_tools import (
    BudgetAwareEvidenceProvider,
    CacheAwareEvidenceProvider,
    EvidenceSearchRequest,
    EvidenceSearchResult,
    StaticEvidenceProvider,
    _cache_key,
    _read_cache_maxsize,
    _read_cache_ttl,
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
    query: str | None = None,
) -> EvidenceSearchRequest:
    chal = challenge or _challenge()
    q = query if query is not None else (f"{market_question} latest current evidence status date")
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
    """Provider that counts how many times search() was called."""

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


# -- VAL-SENREL-009: Cache hit bypasses network call --------------------------


class TestCacheHitBypassesProvider:
    """Cache hit returns results without calling underlying provider (VAL-SENREL-009)."""

    @pytest.mark.asyncio
    async def test_prime_cache_then_hit(self) -> None:
        """Prime the cache, then verify second call is a hit with no provider call."""
        inner = CountingProvider([_make_result()])
        wrapper = CacheAwareEvidenceProvider(inner, provider_id="test_provider")

        # First call: miss, populates cache
        r1 = await wrapper.search(_request())
        assert len(r1) == 1
        assert r1[0].provider == "test_provider"
        assert inner.calls == 1
        assert wrapper.misses == 1
        assert wrapper.hits == 0

        # Second call with same query: should be a cache hit
        r2 = await wrapper.search(_request())
        assert len(r2) == 1
        assert r2[0].title == "Fed Rate Decision Analysis"
        # Underlying provider NOT called again
        assert inner.calls == 1
        assert wrapper.hits == 1
        assert wrapper.misses == 1

    @pytest.mark.asyncio
    async def test_cache_hit_returns_equal_results(self) -> None:
        """Cache hit returns results structurally equal to the originals."""
        inner = StaticEvidenceProvider({"ch-1": [_make_result("ch-1")]})
        wrapper = CacheAwareEvidenceProvider(inner, provider_id="test_provider")

        r1 = await wrapper.search(_request(_challenge("ch-1")))
        r2 = await wrapper.search(_request(_challenge("ch-1")))

        assert r1 == r2
        assert len(r1) == len(r2)
        for a, b in zip(r1, r2, strict=True):
            assert a.model_dump() == b.model_dump()

    @pytest.mark.asyncio
    async def test_different_query_is_miss(self) -> None:
        """A different query triggers a cache miss even for the same provider."""
        inner = CountingProvider([_make_result()])
        wrapper = CacheAwareEvidenceProvider(inner, provider_id="test_provider")

        await wrapper.search(_request(query="query A"))
        assert inner.calls == 1
        assert wrapper.misses == 1

        await wrapper.search(_request(query="query B"))
        assert inner.calls == 2
        assert wrapper.misses == 2
        assert wrapper.hits == 0


# -- VAL-SENREL-010: Cache miss triggers provider call and stores result ------


class TestCacheMissTriggersProvider:
    """Cache miss delegates to provider and stores result (VAL-SENREL-010)."""

    @pytest.mark.asyncio
    async def test_uncached_query_calls_provider(self) -> None:
        """Uncached query triggers provider call exactly once."""
        inner = CountingProvider([_make_result()])
        wrapper = CacheAwareEvidenceProvider(inner, provider_id="test_provider")

        results = await wrapper.search(_request())
        assert len(results) == 1
        assert inner.calls == 1
        assert wrapper.misses == 1
        assert wrapper.hits == 0

    @pytest.mark.asyncio
    async def test_result_stored_for_future_hits(self) -> None:
        """After miss, the result is cached for subsequent identical queries."""
        inner = CountingProvider([_make_result()])
        wrapper = CacheAwareEvidenceProvider(inner, provider_id="test_provider")

        # Miss
        await wrapper.search(_request())
        assert inner.calls == 1

        # Hit
        await wrapper.search(_request())
        assert inner.calls == 1  # not incremented


# -- VAL-SENREL-011: Cache TTL expiry -----------------------------------------


class TestCacheTTLExpiry:
    """Expired TTL entries treated as misses with fresh provider call (VAL-SENREL-011)."""

    @pytest.mark.asyncio
    async def test_ttl_expiry_becomes_miss(self) -> None:
        """After TTL elapses, entry is treated as miss."""
        inner = CountingProvider([_make_result()])
        # Short TTL = 1 second
        wrapper = CacheAwareEvidenceProvider(inner, provider_id="test_provider", ttl=1, maxsize=10)

        # Prime cache
        await wrapper.search(_request())
        assert inner.calls == 1
        assert wrapper.misses == 1

        # Wait for TTL to expire
        time.sleep(1.1)

        # Should be a miss again
        await wrapper.search(_request())
        assert inner.calls == 2
        assert wrapper.misses == 2
        assert wrapper.hits == 0

    @pytest.mark.asyncio
    async def test_within_ttl_still_hit(self) -> None:
        """Within TTL window, entry is still a hit."""
        inner = CountingProvider([_make_result()])
        wrapper = CacheAwareEvidenceProvider(inner, provider_id="test_provider", ttl=60, maxsize=10)

        await wrapper.search(_request())
        assert inner.calls == 1

        # Immediate re-query: hit
        await wrapper.search(_request())
        assert inner.calls == 1
        assert wrapper.hits == 1


# -- VAL-SENREL-012: Cache max size LRU eviction ------------------------------


class TestCacheMaxSizeLRUEviction:
    """Maxsize eviction uses LRU policy (VAL-SENREL-012)."""

    @pytest.mark.asyncio
    async def test_lru_eviction_on_maxsize(self) -> None:
        """maxsize=2: insert A, B, C → A evicted, B and C remain."""
        inner = CountingProvider([_make_result()])
        wrapper = CacheAwareEvidenceProvider(inner, provider_id="test_provider", ttl=600, maxsize=2)

        # Insert A
        await wrapper.search(_request(query="query-A"))
        # Insert B (accesses A, making B MRU)
        await wrapper.search(_request(query="query-B"))
        # Insert C → exceeds maxsize, evicts LRU (A)
        await wrapper.search(_request(query="query-C"))
        assert inner.calls == 3

        # Re-query B: should be hit
        hits_before = wrapper.hits
        await wrapper.search(_request(query="query-B"))
        assert wrapper.hits == hits_before + 1
        assert inner.calls == 3  # no provider call

        # Re-query C: should be hit
        hits_before = wrapper.hits
        await wrapper.search(_request(query="query-C"))
        assert wrapper.hits == hits_before + 1
        assert inner.calls == 3  # no provider call

        # Re-query A: should be miss (evicted)
        await wrapper.search(_request(query="query-A"))
        assert inner.calls == 4  # provider called again

    @pytest.mark.asyncio
    async def test_lru_access_pattern(self) -> None:
        """Re-accessing an entry promotes it, preventing eviction."""
        inner = CountingProvider([_make_result()])
        wrapper = CacheAwareEvidenceProvider(inner, provider_id="test_provider", ttl=600, maxsize=2)

        await wrapper.search(_request(query="query-A"))
        await wrapper.search(_request(query="query-B"))
        # Re-access A (promotes it above B in LRU order)
        await wrapper.search(_request(query="query-A"))
        assert inner.calls == 2  # A was a hit

        # Insert C → evicts LRU which is now B (since A was re-accessed)
        await wrapper.search(_request(query="query-C"))
        assert inner.calls == 3

        # A should still be cached
        hits_before = wrapper.hits
        await wrapper.search(_request(query="query-A"))
        assert wrapper.hits == hits_before + 1
        assert inner.calls == 3

        # B should be evicted
        await wrapper.search(_request(query="query-B"))
        assert inner.calls == 4  # B was evicted, provider called again


# -- VAL-SENREL-013: Cache key is (provider_id, query_hash) -------------------


class TestCacheKeyProviderScoping:
    """Cache key is ``(provider_id, query_hash)`` provider-scoped and query-deterministic."""

    @pytest.mark.asyncio
    async def test_two_providers_same_query_distinct_entries(self) -> None:
        """Two different providers with same query → two cache entries."""
        inner1 = CountingProvider([_make_result()])
        inner2 = CountingProvider([_make_result()])
        wrapper1 = CacheAwareEvidenceProvider(inner1, provider_id="provider_A")
        wrapper2 = CacheAwareEvidenceProvider(inner2, provider_id="provider_B")

        q = "Will the Fed cut rates?"

        _ = await wrapper1.search(_request(query=q))
        _ = await wrapper2.search(_request(query=q))

        # Both were misses (distinct providers)
        assert inner1.calls == 1
        assert inner2.calls == 1
        assert wrapper1.misses == 1
        assert wrapper2.misses == 1

        # Re-query both: each gets its own hit
        await wrapper1.search(_request(query=q))
        await wrapper2.search(_request(query=q))
        assert wrapper1.hits == 1
        assert wrapper2.hits == 1
        assert inner1.calls == 1  # no additional call
        assert inner2.calls == 1  # no additional call

    @pytest.mark.asyncio
    async def test_same_provider_same_query_one_entry(self) -> None:
        """Same provider + same query → one cache entry, second call is hit."""
        inner = CountingProvider([_make_result()])
        wrapper = CacheAwareEvidenceProvider(inner, provider_id="test_provider")

        q = "same query text"
        await wrapper.search(_request(query=q))
        await wrapper.search(_request(query=q))
        # Second call was a hit
        assert inner.calls == 1
        assert wrapper.hits == 1

    def test_cache_key_is_tuple_of_strings(self) -> None:
        """_cache_key returns (provider_id, sha256_hex)."""
        key = _cache_key("provider_X", "hello world")
        assert isinstance(key, tuple)
        assert len(key) == 2
        assert key[0] == "provider_X"
        # Verify it's a valid hex string
        assert len(key[1]) == 64
        int(key[1], 16)  # should not raise

    def test_cache_key_is_deterministic(self) -> None:
        """Same inputs → same key every time."""
        k1 = _cache_key("p", "query")
        k2 = _cache_key("p", "query")
        assert k1 == k2

    def test_cache_key_different_query_different_hash(self) -> None:
        """Different queries produce different hashes."""
        k1 = _cache_key("p", "query A")
        k2 = _cache_key("p", "query B")
        assert k1[0] == k2[0]  # same provider
        assert k1[1] != k2[1]  # different hash


# -- VAL-SENREL-014: Cache hit does not count against budget ------------------


class TestCacheHitNoBudgetConsumption:
    """Cache hits do NOT consume budget (VAL-SENREL-014).

    Cache sits outermost so hits short-circuit before the budget wrapper
    is consulted at all.
    """

    @pytest.mark.asyncio
    async def test_cache_hit_preserves_budget(self) -> None:
        """Budget not decremented on cache hits."""
        inner = CountingProvider([_make_result()])
        # Cache is outermost: hit → returns immediately, budget never checked
        budget_wrapper = BudgetAwareEvidenceProvider(inner, budget=2)
        cache_wrapper = CacheAwareEvidenceProvider(budget_wrapper, provider_id="test_provider")

        # First: cache miss → delegates to budget → decrements budget
        r1 = await cache_wrapper.search(_request())
        assert len(r1) == 1
        assert budget_wrapper.remaining == 1
        assert inner.calls == 1

        # Second (same query): cache hit → budget NOT decremented
        r2 = await cache_wrapper.search(_request())
        assert len(r2) == 1
        assert budget_wrapper.remaining == 1  # unchanged!
        assert inner.calls == 1  # no provider call

    @pytest.mark.asyncio
    async def test_budget_exhaustion_allows_cache_hits(self) -> None:
        """After budget exhaustion, cached queries still return results."""
        inner = CountingProvider(
            results_by_challenge_id={
                "ch-A": [_make_result("ch-A")],
                "ch-B": [_make_result("ch-B")],
                "ch-C": [_make_result("ch-C")],
            }
        )
        # Cache outermost: cache hit returns without budget check
        budget_wrapper = BudgetAwareEvidenceProvider(inner, budget=1)
        cache_wrapper = CacheAwareEvidenceProvider(budget_wrapper, provider_id="test_provider")

        # Challenge A: cache miss → budget 1→0
        r_a = await cache_wrapper.search(_request(_challenge("ch-A"), query="q-A"))
        assert len(r_a) == 1
        assert budget_wrapper.remaining == 0
        # cache_wrapper has A cached now

        # Challenge B: also a miss (not cached) → budget already 0 → empty
        r_b = await cache_wrapper.search(_request(_challenge("ch-B"), query="q-B"))
        assert r_b == []  # budget exhausted, not cached

        # Challenge A again: cache hit despite budget=0
        r_a2 = await cache_wrapper.search(_request(_challenge("ch-A"), query="q-A"))
        assert len(r_a2) == 1  # got results from cache despite budget=0
        assert inner.calls == 1  # only one provider call ever made (ch-A miss)

        # Challenge C: not cached, budget=0 → empty
        r_c = await cache_wrapper.search(_request(_challenge("ch-C"), query="q-C"))
        assert r_c == []  # budget exhausted, not cached


# -- VAL-SENREL-015: Cache stats logged per validation -----------------------


class TestCacheStatsLogged:
    """Cache hit/miss counts logged per validation (VAL-SENREL-015)."""

    @pytest.mark.asyncio
    async def test_hit_and_miss_logged(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Validation with 2 misses and 1 hit logs both."""
        inner = CountingProvider([_make_result()])
        wrapper = CacheAwareEvidenceProvider(inner, provider_id="test_provider")

        # 2 misses
        await wrapper.search(_request(query="q1"))
        await wrapper.search(_request(query="q2"))
        # 1 hit
        await wrapper.search(_request(query="q1"))

        captured = capsys.readouterr().out
        assert "evidence_cache_miss" in captured
        assert "evidence_cache_hit" in captured
        assert wrapper.misses == 2
        assert wrapper.hits == 1

    @pytest.mark.asyncio
    async def test_all_misses_logged(self, capsys: pytest.CaptureFixture[str]) -> None:
        """All-miss validation logs misses but no hits."""
        inner = CountingProvider([_make_result()])
        wrapper = CacheAwareEvidenceProvider(inner, provider_id="test_provider")

        await wrapper.search(_request(query="q1"))
        await wrapper.search(_request(query="q2"))

        captured = capsys.readouterr().out
        assert "evidence_cache_miss" in captured
        assert wrapper.misses == 2
        assert wrapper.hits == 0

    @pytest.mark.asyncio
    async def test_all_hits_logged(self, capsys: pytest.CaptureFixture[str]) -> None:
        """All-hit validation logs hits but no misses (after priming)."""
        inner = CountingProvider([_make_result()])
        wrapper = CacheAwareEvidenceProvider(inner, provider_id="test_provider")

        # Prime
        await wrapper.search(_request(query="q1"))

        # Reset capsys to only capture the hit log
        capsys.readouterr()  # discard prime output

        # Hit
        await wrapper.search(_request(query="q1"))

        captured = capsys.readouterr().out
        assert "evidence_cache_hit" in captured
        assert wrapper.hits == 1


# -- VAL-SENREL-016: Cache TTL and maxsize from environment -------------------


class TestCacheParamsFromEnv:
    """Cache TTL and maxsize from environment (VAL-SENREL-016)."""

    def test_default_ttl_300(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Default TTL is 300 seconds when env var unset."""
        monkeypatch.delenv("SENTINEL_EVIDENCE_CACHE_TTL", raising=False)
        assert _read_cache_ttl() == 300

    def test_default_maxsize_256(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Default maxsize is 256 when env var unset."""
        monkeypatch.delenv("SENTINEL_EVIDENCE_CACHE_MAXSIZE", raising=False)
        assert _read_cache_maxsize() == 256

    def test_custom_ttl_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Custom TTL value is read from env."""
        monkeypatch.setenv("SENTINEL_EVIDENCE_CACHE_TTL", "600")
        assert _read_cache_ttl() == 600

    def test_custom_maxsize_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Custom maxsize value is read from env."""
        monkeypatch.setenv("SENTINEL_EVIDENCE_CACHE_MAXSIZE", "128")
        assert _read_cache_maxsize() == 128

    def test_invalid_ttl_non_numeric_warns_and_defaults(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Non-numeric TTL → warning + default 300."""
        monkeypatch.setenv("SENTINEL_EVIDENCE_CACHE_TTL", "abc")
        assert _read_cache_ttl() == 300
        captured = capsys.readouterr().out
        assert "invalid_evidence_cache_ttl_non_numeric" in captured

    def test_invalid_ttl_non_positive_warns_and_defaults(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Non-positive TTL → warning + default 300."""
        monkeypatch.setenv("SENTINEL_EVIDENCE_CACHE_TTL", "-1")
        assert _read_cache_ttl() == 300
        captured = capsys.readouterr().out
        assert "invalid_evidence_cache_ttl_non_positive" in captured

    def test_invalid_ttl_zero_warns_and_defaults(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """TTL=0 → warning + default 300."""
        monkeypatch.setenv("SENTINEL_EVIDENCE_CACHE_TTL", "0")
        assert _read_cache_ttl() == 300
        captured = capsys.readouterr().out
        assert "invalid_evidence_cache_ttl_non_positive" in captured

    def test_invalid_maxsize_non_numeric_warns_and_defaults(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Non-numeric maxsize → warning + default 256."""
        monkeypatch.setenv("SENTINEL_EVIDENCE_CACHE_MAXSIZE", "xyz")
        assert _read_cache_maxsize() == 256
        captured = capsys.readouterr().out
        assert "invalid_evidence_cache_maxsize_non_numeric" in captured

    def test_invalid_maxsize_negative_warns_and_defaults(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Negative maxsize → warning + default 256."""
        monkeypatch.setenv("SENTINEL_EVIDENCE_CACHE_MAXSIZE", "-5")
        assert _read_cache_maxsize() == 256
        captured = capsys.readouterr().out
        assert "invalid_evidence_cache_maxsize_negative" in captured

    def test_maxsize_zero_disables_caching(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """maxsize=0 is valid — disables caching entirely."""
        monkeypatch.setenv("SENTINEL_EVIDENCE_CACHE_MAXSIZE", "0")
        assert _read_cache_maxsize() == 0


# -- VAL-SENREL-017: Empty result lists are cached ----------------------------


class TestEmptyResultsCached:
    """Empty result lists are cached (VAL-SENREL-017)."""

    @pytest.mark.asyncio
    async def test_empty_list_cached_and_returned(self) -> None:
        """Provider returns []; empty list cached; subsequent query is hit with []."""
        inner = CountingProvider([])  # always returns empty
        wrapper = CacheAwareEvidenceProvider(inner, provider_id="test_provider")

        # First call: miss, returns []
        r1 = await wrapper.search(_request(query="empty-query"))
        assert r1 == []
        assert inner.calls == 1
        assert wrapper.misses == 1

        # Second call: hit, returns [] from cache, provider NOT called
        r2 = await wrapper.search(_request(query="empty-query"))
        assert r2 == []
        assert inner.calls == 1  # still 1!
        assert wrapper.hits == 1

    @pytest.mark.asyncio
    async def test_empty_cache_prevents_repeated_failing_calls(self) -> None:
        """Empty cache prevents repeated provider calls for same query."""
        inner = CountingProvider([])
        wrapper = CacheAwareEvidenceProvider(inner, provider_id="test_provider")

        # 5 identical queries
        for _ in range(5):
            await wrapper.search(_request(query="failing-query"))

        # Only 1 provider call
        assert inner.calls == 1
        assert wrapper.hits == 4
        assert wrapper.misses == 1

    @pytest.mark.asyncio
    async def test_empty_cache_is_provider_scoped(self) -> None:
        """Empty cache for one provider doesn't affect another."""
        inner1 = CountingProvider([])
        inner2 = CountingProvider([_make_result()])
        wrapper1 = CacheAwareEvidenceProvider(inner1, provider_id="provider_A")
        wrapper2 = CacheAwareEvidenceProvider(inner2, provider_id="provider_B")

        # Provider A: empty result cached
        r1a = await wrapper1.search(_request(query="same-query"))
        r1b = await wrapper1.search(_request(query="same-query"))
        assert r1a == []
        assert r1b == []  # cache hit
        assert inner1.calls == 1

        # Provider B: same query, different provider, real result
        r2 = await wrapper2.search(_request(query="same-query"))
        assert len(r2) == 1
        assert inner2.calls == 1  # miss for B


# -- Cache disabled behavior --------------------------------------------------


class TestCacheDisabled:
    """maxsize=0 disables caching entirely."""

    @pytest.mark.asyncio
    async def test_maxsize_zero_disables_caching(self) -> None:
        """When maxsize=0, every call delegates to provider."""
        inner = CountingProvider([_make_result()])
        wrapper = CacheAwareEvidenceProvider(inner, provider_id="test_provider", maxsize=0)

        assert wrapper.disabled is True

        # Three identical queries — all go to provider
        await wrapper.search(_request(query="q"))
        await wrapper.search(_request(query="q"))
        await wrapper.search(_request(query="q"))

        assert inner.calls == 3
        assert wrapper.misses == 3
        assert wrapper.hits == 0

    @pytest.mark.asyncio
    async def test_disabled_returns_results(self) -> None:
        """Even when caching is disabled, results are still returned."""
        inner = StaticEvidenceProvider({"ch-1": [_make_result("ch-1")]})
        wrapper = CacheAwareEvidenceProvider(inner, provider_id="test_provider", maxsize=0)

        results = await wrapper.search(_request(_challenge("ch-1")))
        assert len(results) == 1
        assert results[0].title == "Fed Rate Decision Analysis"
