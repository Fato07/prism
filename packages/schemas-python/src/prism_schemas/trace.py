"""Trading-R1 reasoning trace schema."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from prism_schemas.verdict import EvidenceToolReceipt


class Evidence(BaseModel):
    """A single piece of evidence supporting the thesis."""

    source: str
    claim: str
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp: datetime


class ThesisStep(BaseModel):
    """A single step in the thesis composition."""

    proposition: str
    supporting_evidence_ids: list[int]
    risk_factors: list[str]


class TradingR1Trace(BaseModel):
    """Complete Trading-R1 structured reasoning trace."""

    trace_id: str
    agent_id: int
    market_id: str
    market_question: str

    thesis: list[ThesisStep]
    evidence: list[Evidence]

    # Tool-sourced evidence receipts — proves which evidence came from
    # real tools (verifiable) vs which the LLM invented (unverifiable).
    # Defaults to empty list for backward compatibility with old traces.
    evidence_receipts: list[EvidenceToolReceipt] = Field(default_factory=list)

    raw_probability: float = Field(ge=0.0, le=1.0)
    volatility_adjustment: float
    final_probability: float = Field(ge=0.0, le=1.0)

    action: Literal["BUY", "SELL", "HOLD"]
    size_usdc: float
    price_limit: float
    rationale: str

    model_family: Literal["anthropic-claude", "openai-gpt"]
    model_name: str
    created_at: datetime

    def content_hash(self) -> bytes:
        """Deterministic hash for on-chain anchoring."""
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True)
        return hashlib.sha256(canonical.encode()).digest()
