"""Pydantic models for Prism CLI I/O boundaries."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Readiness = Literal["usable", "needs_review", "not_ready"]
VerdictLabel = Literal["REJECT", "WARN", "PASS", "ENDORSE"]


class Evidence(BaseModel):
    """A single trace evidence item."""

    source: str
    claim: str
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp: datetime | str


class ThesisStep(BaseModel):
    """A single thesis step in a Trading-R1 trace."""

    proposition: str
    supporting_evidence_ids: list[int]
    risk_factors: list[str]


class TradingR1Trace(BaseModel):
    """Minimal Trading-R1 trace model used by the CLI inspector."""

    trace_id: str
    agent_id: int
    market_id: str
    market_question: str
    thesis: list[ThesisStep]
    evidence: list[Evidence]
    raw_probability: float = Field(ge=0.0, le=1.0)
    volatility_adjustment: float
    final_probability: float = Field(ge=0.0, le=1.0)
    action: Literal["BUY", "SELL", "HOLD"]
    size_usdc: float
    price_limit: float
    rationale: str
    model_family: Literal["anthropic-claude", "openai-gpt"]
    model_name: str
    created_at: datetime | str


class ReasoningMetrics(BaseModel):
    """Deterministic quality metrics extracted from a trace without an LLM call."""

    evidence_count: int
    source_diversity: int
    thesis_steps: int
    evidence_reference_count: int
    evidence_coverage: float
    invalid_evidence_refs: int
    unsupported_thesis_steps: int
    risk_factor_count: int
    avg_evidence_confidence: float
    probability_delta: float
    has_falsification_language: bool


class InspectResult(BaseModel):
    """Result returned by `prism inspect`."""

    trace_id: str
    market_id: str
    market_question: str
    action: str
    readiness: Readiness
    reasoning_metrics: ReasoningMetrics
    warnings: list[str] = Field(default_factory=list)


class PublicStatsResponse(BaseModel):
    """Public dashboard stats API response."""

    generated_at: str
    stats: dict[str, Any]


class PublicHistoryEntry(BaseModel):
    """A recent public validation entry returned by the dashboard API."""

    trace_id: str
    market_id: str
    verdict_score: int
    verdict_label: VerdictLabel
    created_at: str
    dashboard_url: str
    trace_ipfs_cid: str | None = None
    trace_tx_hash: str | None = None
    validation_tx_hash: str | None = None
    response_uri: str | None = None


class PublicHistoryResponse(BaseModel):
    """Public dashboard history API response."""

    generated_at: str
    limit: int
    entries: list[PublicHistoryEntry]


class PublicTraceReport(BaseModel):
    """Trace report returned by the public dashboard report API."""

    generated_at: str
    trace: dict[str, Any]
    validation: dict[str, Any] | None
    reasoning_metrics: ReasoningMetrics | None
    readiness: Readiness | None
    warnings: list[str] = Field(default_factory=list)
    receipts: dict[str, Any]


class MarketOutcome(BaseModel):
    """A Polymarket CLOB outcome with token ID."""

    model_config = ConfigDict(populate_by_name=True)

    outcome: str
    price: float
    token_id: str = Field(alias="tokenId")


class TokenResolution(BaseModel):
    """Auditable token resolution returned by Prism's Polymarket gateway."""

    model_config = ConfigDict(populate_by_name=True)

    status: Literal["resolved", "unresolved"]
    token_id: str | None = Field(alias="tokenId")
    condition_id: str | None = Field(alias="conditionId")
    confidence: float
    source: str
    matched_question: str | None = Field(default=None, alias="matchedQuestion")
    reason: str | None = None


class MarketData(BaseModel):
    """A surfaced Polymarket market."""

    model_config = ConfigDict(populate_by_name=True)

    condition_id: str = Field(alias="conditionId")
    question: str
    outcomes: list[MarketOutcome]
    yes_token_id: str | None = Field(alias="yesTokenId")
    no_token_id: str | None = Field(default=None, alias="noTokenId")
    end_date: str | None = Field(alias="endDate")
    active: bool
    accepting_orders: bool = Field(default=True, alias="acceptingOrders")
    token_resolution: TokenResolution = Field(alias="tokenResolution")
    surface_reason: str = Field(alias="surfaceReason")
    surface_score: int | float = Field(alias="surfaceScore")


class MarketListResponse(BaseModel):
    """Gateway market list response."""

    markets: list[MarketData]
    count: int
    filters: dict[str, Any] | None = None


class MarketResolveResponse(BaseModel):
    """Gateway market resolution response."""

    model_config = ConfigDict(populate_by_name=True)

    query: str
    market_question: str | None = Field(default=None, alias="marketQuestion")
    resolution: TokenResolution
