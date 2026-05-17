"""Schema validation tests."""

import hashlib
import json
from datetime import datetime, timezone

from prism_schemas.connector import ToolConnector, ToolConnectorSmokeReceipt
from prism_schemas.trace import Evidence, ThesisStep, TradingR1Trace
from prism_schemas.verdict import ChallengeResolution, EvidenceToolReceipt, SentinelVerdict


def test_trading_r1_trace_validates():
    trace = TradingR1Trace(
        trace_id="test-001",
        agent_id=1,
        market_id="0xabc",
        market_question="Will ETH hit $5000 by Q3?",
        thesis=[
            ThesisStep(
                proposition="ETH momentum is bullish",
                supporting_evidence_ids=[0],
                risk_factors=["regulatory"],
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
        model_name="claude-opus-4-7",
        created_at=datetime.now(timezone.utc),
    )
    assert trace.content_hash() is not None
    assert len(trace.content_hash()) == 32


def test_sentinel_verdict_validates():
    verdict = SentinelVerdict(
        request_hash="0xdeadbeef",
        trace_id="test-001",
        sentinel_agent_id=2,
        evidence_challenges=["coingecko data may be stale"],
        thesis_challenges=["regulatory risk underweighted"],
        calibration_critique="60% seems reasonable given evidence.",
        verdict_score=72,
        verdict_label="PASS",
        dialogue_messages=[
            {"role": "sentinel", "content": "Challenge: source reliability"}
        ],
        model_family="openai-gpt",
        model_name="gpt-4o-mini",
        created_at=datetime.now(timezone.utc),
    )
    assert verdict.content_hash() is not None
    assert verdict.verdict_label == "PASS"


def test_evidence_tool_receipt_validates_on_resolution():
    resolution = ChallengeResolution(
        challenge_id="ev-1",
        status="resolved",
        responder="evidence_tool",
        response="Retrieved issue-matched evidence from exa_mcp.",
        created_at=datetime.now(timezone.utc),
        tool_receipt=EvidenceToolReceipt(
            provider="exa_mcp",
            tool_name="web_search_exa",
            source_title="Current market evidence",
            source_url="https://example.com/evidence",
            source_published_at="2026-05-16T00:00:00Z",
            confidence=0.91,
            adequacy_checks=["topic_overlap", "temporal_recency"],
        ),
    )

    assert resolution.tool_receipt is not None
    assert resolution.tool_receipt.provider == "exa_mcp"
    assert resolution.tool_receipt.adequacy_checks == ["topic_overlap", "temporal_recency"]


def test_tool_connector_schema_validates_redacted_passport_row():
    receipt = ToolConnectorSmokeReceipt(
        status="passed",
        checked_at=datetime.now(timezone.utc),
        transport_ok=True,
        tool_reachable=True,
        schema_ok=True,
        mapper_ok=True,
        fail_closed_ok=True,
        cost_cap_ok=True,
        evidence_count=2,
    )
    connector = ToolConnector(
        id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        name="Demo MCP evidence",
        transport="mcp_http",
        provider="mcp",
        server_url="https://mcp.example.com",
        tool_name="search",
        input_mapper="query_limit",
        result_mapper="generic_search",
        allowed_tools=["search"],
        timeout_seconds="20.0",
        max_results=5,
        max_usdc="0.05",
        auth_secret_ciphertext="v1:encrypted-token",
        auth_secret_hint="demo…1234",
        smoke_status="passed",
        smoke_receipt=receipt,
        armed=True,
        fail_closed=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    assert connector.connector_kind == "evidence"
    assert connector.smoke_receipt is not None
    assert connector.smoke_receipt.status == "passed"


def test_old_sentinel_verdict_hash_omits_new_default_fields():
    old_verdict_json = {
        "request_hash": "0xdeadbeef",
        "trace_id": "test-001",
        "sentinel_agent_id": 2,
        "evidence_challenges": ["coingecko data may be stale"],
        "thesis_challenges": ["regulatory risk underweighted"],
        "calibration_critique": "60% seems reasonable given evidence.",
        "verdict_score": 72,
        "verdict_label": "PASS",
        "dialogue_messages": [
            {"role": "sentinel", "content": "Challenge: source reliability"}
        ],
        "model_family": "openai-gpt",
        "model_name": "gpt-4o-mini",
        "created_at": "2026-05-16T00:00:00Z",
    }
    expected = hashlib.sha256(
        json.dumps(old_verdict_json, sort_keys=True).encode()
    ).digest()

    verdict = SentinelVerdict.model_validate(old_verdict_json)

    assert verdict.structured_challenges == []
    assert verdict.content_hash() == expected
