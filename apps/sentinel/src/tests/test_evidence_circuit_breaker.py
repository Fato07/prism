"""Evidence circuit breaker tests.

Tests for VAL-SENREL-018 through VAL-SENREL-027.
"""

from __future__ import annotations

import time

import pytest
from prism_schemas.verdict import AdversarialChallenge

from sentinel.evidence_tools import (
    CircuitBreakerAwareEvidenceProvider,
    CircuitBreakerState,
    EvidenceSearchRequest,
    EvidenceSearchResult,
    _read_circuit_breaker_cooldown,
    _read_circuit_breaker_threshold,
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
    q = query if query is not None else f"{market_question} latest current evidence status date"
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
    ) -> None:
        self._results = results or []
        self._calls = 0

    async def search(self, request: EvidenceSearchRequest) -> list[EvidenceSearchResult]:
        self._calls += 1
        return list(self._results)

    @property
    def calls(self) -> int:
        return self._calls


class FailingProvider:
    """Provider that raises an exception on every call."""

    def __init__(self, exc_type: type[Exception] | None = None) -> None:
        self._exc_type = exc_type or RuntimeError
        self._calls = 0

    async def search(self, request: EvidenceSearchRequest) -> list[EvidenceSearchResult]:
        self._calls += 1
        raise self._exc_type("simulated provider failure")

    @property
    def calls(self) -> int:
        return self._calls


class FlakyProvider:
    """Provider that alternates between success and failure."""

    def __init__(
        self,
        results: list[EvidenceSearchResult] | None = None,
        *,
        fail_pattern: list[bool] | None = None,
    ) -> None:
        self._results = results or [_make_result()]
        self._fail_pattern = fail_pattern or [True, True, True]  # all fail by default
        self._call_index = 0
        self._calls = 0

    async def search(self, request: EvidenceSearchRequest) -> list[EvidenceSearchResult]:
        idx = self._call_index
        self._call_index += 1
        self._calls += 1
        pattern = self._fail_pattern
        should_fail = pattern[idx % len(pattern)]
        if should_fail:
            raise RuntimeError(f"simulated failure on call {idx + 1}")
        return list(self._results)

    @property
    def calls(self) -> int:
        return self._calls


# -- VAL-SENREL-018: Circuit breaker starts CLOSED ----------------------------


class TestCircuitStartsClosed:
    """Circuit breaker starts CLOSED (VAL-SENREL-018)."""

    @pytest.mark.asyncio
    async def test_initial_state_is_closed(self) -> None:
        """New circuit breaker is in CLOSED state."""
        inner = CountingProvider([_make_result()])
        cb = CircuitBreakerAwareEvidenceProvider(inner, provider_id="test_p")
        assert cb.state is CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_closed_delegates_to_provider(self) -> None:
        """CLOSED circuit delegates to inner provider."""
        inner = CountingProvider([_make_result()])
        cb = CircuitBreakerAwareEvidenceProvider(inner, provider_id="test_p")

        results = await cb.search(_request())
        assert len(results) == 1
        assert inner.calls == 1
        assert cb.state is CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_closed_with_empty_results_is_not_failure(self) -> None:
        """Empty result list from provider does NOT count as failure."""
        inner = CountingProvider([])  # always returns empty
        cb = CircuitBreakerAwareEvidenceProvider(inner, provider_id="test_p")

        for _ in range(5):
            results = await cb.search(_request())
            assert results == []

        # Circuit should still be CLOSED — empty results are NOT failures
        assert cb.state is CircuitBreakerState.CLOSED
        assert cb.consecutive_failures == 0


# -- VAL-SENREL-019: CLOSED to OPEN on consecutive failures -------------------


class TestConsecutiveFailuresOpenCircuit:
    """CLOSED to OPEN on consecutive failures (VAL-SENREL-019)."""

    @pytest.mark.asyncio
    async def test_three_consecutive_failures_opens(self) -> None:
        """Threshold=3, 3 consecutive failures → OPEN on 3rd."""
        inner = FailingProvider()
        cb = CircuitBreakerAwareEvidenceProvider(inner, provider_id="test_p", failure_threshold=3)

        # 1st failure
        r1 = await cb.search(_request())
        assert r1 == []
        assert cb.state is CircuitBreakerState.CLOSED
        assert cb.consecutive_failures == 1

        # 2nd failure
        r2 = await cb.search(_request())
        assert r2 == []
        assert cb.state is CircuitBreakerState.CLOSED
        assert cb.consecutive_failures == 2

        # 3rd failure → OPEN
        r3 = await cb.search(_request())
        assert r3 == []
        assert cb.state is CircuitBreakerState.OPEN
        assert cb.consecutive_failures == 3

    @pytest.mark.asyncio
    async def test_custom_threshold(self) -> None:
        """Threshold=2 → opens after 2 consecutive failures."""
        inner = FailingProvider()
        cb = CircuitBreakerAwareEvidenceProvider(inner, provider_id="test_p", failure_threshold=2)

        await cb.search(_request())
        assert cb.state is CircuitBreakerState.CLOSED
        await cb.search(_request())
        assert cb.state is CircuitBreakerState.OPEN

    @pytest.mark.asyncio
    async def test_logs_failure_count(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Each failure logs the running count."""
        inner = FailingProvider()
        cb = CircuitBreakerAwareEvidenceProvider(inner, provider_id="test_p")

        await cb.search(_request())
        captured = capsys.readouterr().out
        assert "circuit_breaker_failure" in captured

    @pytest.mark.asyncio
    async def test_logs_circuit_opened(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Circuit open logs a specific event."""
        inner = FailingProvider()
        cb = CircuitBreakerAwareEvidenceProvider(inner, provider_id="test_p")

        for _ in range(3):
            await cb.search(_request())

        captured = capsys.readouterr().out
        assert "circuit_breaker_opened" in captured


# -- VAL-SENREL-020: OPEN circuit returns empty immediately -------------------


class TestOpenCircuitReturnsEmpty:
    """OPEN circuit returns [] immediately without calling provider (VAL-SENREL-020)."""

    @pytest.mark.asyncio
    async def test_open_returns_empty_without_provider_call(self) -> None:
        """When OPEN, search() returns [] without calling provider."""
        inner = FailingProvider()
        cb = CircuitBreakerAwareEvidenceProvider(inner, provider_id="test_p")

        # Force circuit open
        for _ in range(3):
            await cb.search(_request())
        assert cb.state is CircuitBreakerState.OPEN

        calls_before = inner.calls
        results = await cb.search(_request())
        assert results == []
        assert inner.calls == calls_before  # provider NOT called

    @pytest.mark.asyncio
    async def test_open_logs_warning(self, capsys: pytest.CaptureFixture[str]) -> None:
        """OPEN circuit emits a circuit_breaker_open warning."""
        inner = FailingProvider()
        cb = CircuitBreakerAwareEvidenceProvider(inner, provider_id="test_p")

        # Open the circuit
        for _ in range(3):
            await cb.search(_request())

        # Clear captured output
        capsys.readouterr()

        # Call while OPEN
        await cb.search(_request())

        captured = capsys.readouterr().out
        assert "circuit_breaker_open" in captured


# -- VAL-SENREL-021: OPEN to HALF-OPEN after cooldown -------------------------


class TestOpenToHalfOpen:
    """OPEN → HALF-OPEN after cooldown (VAL-SENREL-021)."""

    @pytest.mark.asyncio
    async def test_transitions_to_half_open_after_cooldown(self) -> None:
        """After cooldown, next call transitions OPEN → HALF-OPEN."""
        inner = FailingProvider()
        cb = CircuitBreakerAwareEvidenceProvider(inner, provider_id="test_p", cooldown_seconds=0.05)

        # Open the circuit
        for _ in range(3):
            await cb.search(_request())
        assert cb.state is CircuitBreakerState.OPEN

        # Wait for cooldown
        time.sleep(0.1)

        # Next call should transition to HALF_OPEN
        await cb.search(_request())
        assert cb.state is CircuitBreakerState.OPEN  # Still fails, re-opens

    @pytest.mark.asyncio
    async def test_stays_open_before_cooldown(self) -> None:
        """Before cooldown elapses, circuit stays OPEN."""
        inner = FailingProvider()
        cb = CircuitBreakerAwareEvidenceProvider(inner, provider_id="test_p", cooldown_seconds=10.0)

        # Open the circuit
        for _ in range(3):
            await cb.search(_request())
        assert cb.state is CircuitBreakerState.OPEN

        # Immediately call — still OPEN
        results = await cb.search(_request())
        assert results == []
        assert cb.state is CircuitBreakerState.OPEN

    @pytest.mark.asyncio
    async def test_half_open_logs_transition(self, capsys: pytest.CaptureFixture[str]) -> None:
        """HALF_OPEN transition is logged."""
        inner = FailingProvider()
        cb = CircuitBreakerAwareEvidenceProvider(inner, provider_id="test_p", cooldown_seconds=0.01)

        for _ in range(3):
            await cb.search(_request())

        # Wait for cooldown
        time.sleep(0.05)

        # Clear captured output
        capsys.readouterr()

        await cb.search(_request())

        captured = capsys.readouterr().out
        assert "circuit_breaker_half_open" in captured


# -- VAL-SENREL-022: HALF-OPEN success transitions to CLOSED ------------------


class TestHalfOpenSuccessCloses:
    """HALF-OPEN success → CLOSED (VAL-SENREL-022)."""

    @pytest.mark.asyncio
    async def test_half_open_success_closes_circuit(self) -> None:
        """Successful trial call in HALF-OPEN closes the circuit."""
        inner = FlakyProvider(fail_pattern=[True, False])
        cb = CircuitBreakerAwareEvidenceProvider(
            inner, provider_id="test_p4", failure_threshold=1, cooldown_seconds=0.01
        )

        await cb.search(_request())  # fail → OPEN
        assert cb.state is CircuitBreakerState.OPEN

        time.sleep(0.05)

        # Second call should succeed → closes
        results = await cb.search(_request())
        assert len(results) == 1
        assert cb.state is CircuitBreakerState.CLOSED
        assert cb.consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_half_open_success_resets_failure_counter(self) -> None:
        """After HALF_OPEN success, consecutive_failures resets to 0."""
        inner = FlakyProvider(fail_pattern=[True, False])
        cb = CircuitBreakerAwareEvidenceProvider(
            inner, provider_id="test_p", failure_threshold=1, cooldown_seconds=0.01
        )

        await cb.search(_request())  # fail
        assert cb.consecutive_failures == 1
        assert cb.state is CircuitBreakerState.OPEN

        time.sleep(0.05)

        await cb.search(_request())  # succeed
        assert cb.consecutive_failures == 0


# -- VAL-SENREL-023: HALF-OPEN failure re-opens circuit -----------------------


class TestHalfOpenFailureReopens:
    """HALF-OPEN failure re-opens circuit (VAL-SENREL-023)."""

    @pytest.mark.asyncio
    async def test_half_open_failure_reopens_immediately(self) -> None:
        """Failed HALF_OPEN trial re-opens immediately."""
        inner = FlakyProvider(fail_pattern=[True, True])  # fail both times
        cb = CircuitBreakerAwareEvidenceProvider(
            inner, provider_id="test_p", failure_threshold=1, cooldown_seconds=0.01
        )

        await cb.search(_request())  # fail → OPEN
        assert cb.state is CircuitBreakerState.OPEN

        time.sleep(0.05)

        # Second call: HALF_OPEN trial, fails → re-OPEN
        await cb.search(_request())
        assert cb.state is CircuitBreakerState.OPEN

    @pytest.mark.asyncio
    async def test_half_open_failure_logged(self, capsys: pytest.CaptureFixture[str]) -> None:
        """HALF_OPEN failure is logged."""
        inner = FlakyProvider(fail_pattern=[True, True])
        cb = CircuitBreakerAwareEvidenceProvider(
            inner, provider_id="test_p", failure_threshold=1, cooldown_seconds=0.01
        )

        await cb.search(_request())
        time.sleep(0.05)

        capsys.readouterr()  # clear
        await cb.search(_request())

        captured = capsys.readouterr().out
        assert "circuit_breaker_half_open_failed" in captured


# -- VAL-SENREL-024: Per-provider circuit breaker isolation -------------------


class TestPerProviderIsolation:
    """Per-provider circuit breaker isolation (VAL-SENREL-024)."""

    @pytest.mark.asyncio
    async def test_one_provider_open_does_not_affect_another(self) -> None:
        """Provider A OPEN, Provider B still CLOSED and working."""
        inner_a = FailingProvider()
        inner_b = CountingProvider([_make_result()])

        cb_a = CircuitBreakerAwareEvidenceProvider(inner_a, provider_id="provider_A")
        cb_b = CircuitBreakerAwareEvidenceProvider(inner_b, provider_id="provider_B")

        # Open provider A
        for _ in range(3):
            await cb_a.search(_request())

        assert cb_a.state is CircuitBreakerState.OPEN

        # Provider B should still work
        results = await cb_b.search(_request())
        assert len(results) == 1
        assert cb_b.state is CircuitBreakerState.CLOSED
        assert inner_b.calls == 1

    @pytest.mark.asyncio
    async def test_independent_failure_counters(self) -> None:
        """Each provider has its own failure counter."""
        inner_a = FailingProvider()
        inner_b = CountingProvider([_make_result()])

        cb_a = CircuitBreakerAwareEvidenceProvider(inner_a, provider_id="provider_A")
        cb_b = CircuitBreakerAwareEvidenceProvider(inner_b, provider_id="provider_B")

        # Fail A twice
        await cb_a.search(_request())
        await cb_a.search(_request())
        assert cb_a.consecutive_failures == 2

        # B should have 0 failures
        await cb_b.search(_request())
        assert cb_b.consecutive_failures == 0


# -- VAL-SENREL-025: Circuit breaker threshold and cooldown from env ----------


class TestCBParamsFromEnv:
    """Circuit breaker threshold and cooldown from env vars (VAL-SENREL-025)."""

    def test_default_threshold_3(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Default threshold is 3 when env var unset."""
        monkeypatch.delenv("SENTINEL_EVIDENCE_CB_FAILURE_THRESHOLD", raising=False)
        assert _read_circuit_breaker_threshold() == 3

    def test_default_cooldown_60(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Default cooldown is 60 when env var unset."""
        monkeypatch.delenv("SENTINEL_EVIDENCE_CB_COOLDOWN_SECONDS", raising=False)
        assert _read_circuit_breaker_cooldown() == 60.0

    def test_custom_threshold_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Custom threshold value from env."""
        monkeypatch.setenv("SENTINEL_EVIDENCE_CB_FAILURE_THRESHOLD", "5")
        assert _read_circuit_breaker_threshold() == 5

    def test_custom_cooldown_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Custom cooldown value from env."""
        monkeypatch.setenv("SENTINEL_EVIDENCE_CB_COOLDOWN_SECONDS", "30")
        assert _read_circuit_breaker_cooldown() == 30.0

    def test_invalid_threshold_non_numeric_warns(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Non-numeric threshold → warning + default 3."""
        monkeypatch.setenv("SENTINEL_EVIDENCE_CB_FAILURE_THRESHOLD", "abc")
        assert _read_circuit_breaker_threshold() == 3
        captured = capsys.readouterr().out
        assert "invalid_cb_failure_threshold_non_numeric" in captured

    def test_invalid_threshold_non_positive_warns(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Non-positive threshold → warning + default 3."""
        monkeypatch.setenv("SENTINEL_EVIDENCE_CB_FAILURE_THRESHOLD", "0")
        assert _read_circuit_breaker_threshold() == 3
        captured = capsys.readouterr().out
        assert "invalid_cb_failure_threshold_non_positive" in captured

    def test_invalid_cooldown_non_numeric_warns(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Non-numeric cooldown → warning + default 60."""
        monkeypatch.setenv("SENTINEL_EVIDENCE_CB_COOLDOWN_SECONDS", "xyz")
        assert _read_circuit_breaker_cooldown() == 60.0
        captured = capsys.readouterr().out
        assert "invalid_cb_cooldown_non_numeric" in captured

    def test_invalid_cooldown_non_positive_warns(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Non-positive cooldown → warning + default 60."""
        monkeypatch.setenv("SENTINEL_EVIDENCE_CB_COOLDOWN_SECONDS", "-5")
        assert _read_circuit_breaker_cooldown() == 60.0
        captured = capsys.readouterr().out
        assert "invalid_cb_cooldown_non_positive" in captured


# -- VAL-SENREL-026: Provider exceptions count as failures --------------------


class TestExceptionsCountAsFailures:
    """Provider exceptions count as failures (VAL-SENREL-026)."""

    @pytest.mark.asyncio
    async def test_exception_increments_failure_counter(self) -> None:
        """Any exception increments consecutive_failures."""
        inner = FailingProvider()
        cb = CircuitBreakerAwareEvidenceProvider(inner, provider_id="test_p")

        await cb.search(_request())
        assert cb.consecutive_failures == 1
        assert cb.last_call_failed is True

    @pytest.mark.asyncio
    async def test_exception_returns_empty_not_propagated(self) -> None:
        """Exception is caught and [] is returned, not propagated."""
        inner = FailingProvider()
        cb = CircuitBreakerAwareEvidenceProvider(inner, provider_id="test_p")

        # Should NOT raise — circuit breaker catches and returns []
        results = await cb.search(_request())
        assert results == []

    @pytest.mark.asyncio
    async def test_httpx_connect_error_counted(self) -> None:
        """Even connect errors are caught and counted."""
        import httpx

        inner = FailingProvider(exc_type=httpx.ConnectError)
        cb = CircuitBreakerAwareEvidenceProvider(inner, provider_id="test_p")

        results = await cb.search(_request())
        assert results == []
        assert cb.consecutive_failures == 1

    @pytest.mark.asyncio
    async def test_empty_results_not_counted_as_failures(self) -> None:
        """Empty result lists do NOT count as failures."""
        inner = CountingProvider([])  # returns []
        cb = CircuitBreakerAwareEvidenceProvider(inner, provider_id="test_p")

        for _ in range(5):
            await cb.search(_request())

        assert cb.consecutive_failures == 0
        assert cb.state is CircuitBreakerState.CLOSED


# -- VAL-SENREL-027: Non-consecutive failures do not open circuit -------------


class TestNonConsecutiveFailures:
    """Non-consecutive failures do not open circuit (VAL-SENREL-027)."""

    @pytest.mark.asyncio
    async def test_success_resets_consecutive_counter(self) -> None:
        """A success resets the consecutive failure counter."""
        inner = FlakyProvider(fail_pattern=[True, True, False, True, True])
        cb = CircuitBreakerAwareEvidenceProvider(inner, provider_id="test_p")

        # Fail, fail
        await cb.search(_request())
        await cb.search(_request())
        assert cb.consecutive_failures == 2

        # Succeed → reset
        await cb.search(_request())
        assert cb.consecutive_failures == 0

        # Fail, fail again — circuit should still be CLOSED (only 2 consecutive)
        await cb.search(_request())
        await cb.search(_request())
        assert cb.consecutive_failures == 2
        assert cb.state is CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_need_full_threshold_consecutive_failures_to_open(self) -> None:
        """Threshold=3: fail, fail, succeed, fail, fail, fail → OPEN on 3rd consecutive."""
        inner = FlakyProvider(fail_pattern=[True, True, False, True, True, True])
        cb = CircuitBreakerAwareEvidenceProvider(inner, provider_id="test_p", failure_threshold=3)

        # Fail, fail (2 consecutive)
        await cb.search(_request())
        await cb.search(_request())
        assert cb.state is CircuitBreakerState.CLOSED

        # Succeed (resets)
        await cb.search(_request())
        assert cb.consecutive_failures == 0

        # Fail, fail, fail (3 consecutive → OPEN)
        await cb.search(_request())
        await cb.search(_request())
        await cb.search(_request())
        assert cb.state is CircuitBreakerState.OPEN
