"""Schema tests for evidence_receipts field — VAL-TOOL-022 through VAL-TOOL-026."""

from __future__ import annotations

from datetime import datetime, timezone

from prism_schemas.trace import Evidence, ThesisStep, TradingR1Trace
from prism_schemas.verdict import EvidenceToolReceipt

# ---------------------------------------------------------------------------
# VAL-TOOL-022: TradingR1Trace includes evidence_receipts field
# ---------------------------------------------------------------------------


def test_evidence_receipts_field_present() -> None:
    """evidence_receipts is a model field on TradingR1Trace."""
    fields = TradingR1Trace.model_fields
    assert "evidence_receipts" in fields, "evidence_receipts must be a model field"
    field = fields["evidence_receipts"]
    # Not Optional, not list[Any]
    assert field.annotation is not None


def test_evidence_receipts_accepts_evidence_tool_receipts() -> None:
    """evidence_receipts accepts list[EvidenceToolReceipt]."""
    receipt = EvidenceToolReceipt(
        provider="test_provider",
        tool_name="test_tool",
        source_title="Test Title",
        source_url="https://example.com/test",
        source_published_at="2026-05-20T00:00:00Z",
        retrieved_at="2026-05-22T00:00:00Z",
        confidence=0.75,
    )
    trace = _make_trace(evidence_receipts=[receipt])
    trace_validated = TradingR1Trace.model_validate(trace.model_dump())
    assert len(trace_validated.evidence_receipts) == 1
    assert trace_validated.evidence_receipts[0].provider == "test_provider"
    assert trace_validated.evidence_receipts[0].source_title == "Test Title"
    assert trace_validated.evidence_receipts[0].confidence == 0.75


# ---------------------------------------------------------------------------
# VAL-TOOL-023: evidence_receipts defaults to empty list — backward compatible
# ---------------------------------------------------------------------------


def test_evidence_receipts_defaults_to_empty_list() -> None:
    """Trace without evidence_receipts has it default to []."""
    trace = _make_trace()
    assert trace.evidence_receipts == []


def test_old_json_without_evidence_receipts_parses() -> None:
    """model_validate on JSON without evidence_receipts key → field is []."""
    old_json = {
        "trace_id": "test-001",
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
                "timestamp": "2026-05-20T00:00:00Z",
            }
        ],
        "raw_probability": 0.65,
        "volatility_adjustment": -0.05,
        "final_probability": 0.60,
        "action": "BUY",
        "size_usdc": 10.0,
        "price_limit": 0.60,
        "rationale": "Bullish momentum.",
        "model_family": "anthropic-claude",
        "model_name": "claude-sonnet-4-20250514",
        "created_at": "2026-05-20T00:00:00Z",
    }
    trace = TradingR1Trace.model_validate(old_json)
    assert trace.evidence_receipts == []


# ---------------------------------------------------------------------------
# VAL-TOOL-024: Trace with evidence_receipts round-trips through JSON
# ---------------------------------------------------------------------------


def test_evidence_receipts_round_trips_through_json() -> None:
    """A trace with non-empty evidence_receipts serializes and re-parses correctly."""
    receipt = EvidenceToolReceipt(
        provider="brave_search",
        tool_name="web_search",
        source_title="Market News",
        source_url="https://news.example.com/article",
        source_published_at="2026-05-20T00:00:00Z",
        retrieved_at="2026-05-22T00:00:00Z",
        confidence=0.85,
    )
    trace = _make_trace(evidence_receipts=[receipt])
    json_str = trace.model_dump_json()
    reparsed = TradingR1Trace.model_validate_json(json_str)
    assert reparsed.evidence_receipts == trace.evidence_receipts
    assert reparsed.content_hash() == trace.content_hash()


def test_evidence_receipts_key_in_serialized_dict() -> None:
    """evidence_receipts key is present in the serialized dict even when empty."""
    trace = _make_trace()
    serialized = trace.model_dump(mode="json")
    assert "evidence_receipts" in serialized
    assert serialized["evidence_receipts"] == []


# ---------------------------------------------------------------------------
# VAL-TOOL-025: content_hash() changes when evidence_receipts changes
# ---------------------------------------------------------------------------


def test_empty_vs_nonempty_receipts_different_hash() -> None:
    """Two traces identical except evidence_receipts produce different hashes."""
    base = _make_trace(trace_id="hash-test")
    receipt = EvidenceToolReceipt(
        provider="test_provider",
        source_title="Test Title",
        source_url="https://example.com/test",
        confidence=0.75,
    )
    with_receipts = _make_trace(trace_id="hash-test", evidence_receipts=[receipt])
    assert base.content_hash() != with_receipts.content_hash()


def test_different_receipts_different_hash() -> None:
    """Two traces with different evidence_receipts produce different hashes."""
    receipt_a = EvidenceToolReceipt(
        provider="provider_a",
        source_title="Title A",
        source_url="https://a.example.com",
        confidence=0.5,
    )
    receipt_b = EvidenceToolReceipt(
        provider="provider_b",
        source_title="Title B",
        source_url="https://b.example.com",
        confidence=0.9,
    )
    trace_a = _make_trace(trace_id="diff-hash-test", evidence_receipts=[receipt_a])
    trace_b = _make_trace(trace_id="diff-hash-test", evidence_receipts=[receipt_b])
    assert trace_a.content_hash() != trace_b.content_hash()


# ---------------------------------------------------------------------------
# VAL-TOOL-026: EvidenceToolReceipt uses same schema as sentinel verdict receipts
# ---------------------------------------------------------------------------


def test_evidence_tool_receipt_is_same_class() -> None:
    """The EvidenceToolReceipt in TradingR1Trace is from prism_schemas.verdict."""
    from prism_schemas.verdict import EvidenceToolReceipt as VerdictReceipt

    trace = _make_trace(
        evidence_receipts=[
            EvidenceToolReceipt(
                provider="test",
                source_title="Test",
                source_url="https://example.com",
                confidence=0.5,
            )
        ]
    )
    receipt = trace.evidence_receipts[0]
    assert isinstance(receipt, VerdictReceipt)
    assert receipt.provider == "test"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_trace(**overrides) -> TradingR1Trace:
    """Create a TradingR1Trace for testing with sensible defaults."""
    defaults: dict = dict(
        trace_id="test-001",
        agent_id=1,
        market_id="0xabc",
        market_question="Will ETH hit $5000?",
        thesis=[
            ThesisStep(
                proposition="Bullish momentum",
                supporting_evidence_ids=[0],
                risk_factors=["regulatory risk"],
            )
        ],
        evidence=[
            Evidence(
                source="coingecko",
                claim="ETH up 20% in 30d",
                confidence=0.8,
                timestamp=datetime.now(timezone.utc),
            )
        ],
        raw_probability=0.65,
        volatility_adjustment=-0.05,
        final_probability=0.60,
        action="BUY",
        size_usdc=10.0,
        price_limit=0.60,
        rationale="Bullish momentum with manageable risk.",
        model_family="anthropic-claude",
        model_name="claude-sonnet-4-20250514",
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return TradingR1Trace(**defaults)
