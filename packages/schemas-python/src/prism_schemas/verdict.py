"""Sentinel verdict schema."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ChallengeType = Literal[
    "temporal",
    "source_quality",
    "relevance",
    "calibration",
    "logic",
    "market_structure",
    "risk",
]
ChallengeSeverity = Literal["minor", "material", "blocking"]
ChallengeResolutionStatus = Literal["open", "answered", "resolved", "conceded", "superseded"]
ResolutionStopReason = Literal[
    "single_shot",
    "confidence_reached",
    "max_rounds",
    "unresolved_blockers",
    "insufficient_evidence",
]


class AdversarialChallenge(BaseModel):
    """A structured issue raised by the sentinel against a trace."""

    id: str
    type: ChallengeType
    severity: ChallengeSeverity
    question: str
    required_resolution: str
    blocking_pass: bool = False
    claim_ref: str | None = None
    resolution_status: ChallengeResolutionStatus = "open"


class EvidenceToolReceipt(BaseModel):
    """Structured provenance for evidence used to resolve an issue."""

    provider: str
    tool_name: str | None = None
    source_title: str
    source_url: str
    source_published_at: str | None = None
    retrieved_at: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    adequacy_checks: list[str] = Field(default_factory=list)


class ChallengeResolution(BaseModel):
    """Trader or tool response that attempts to resolve one challenge."""

    challenge_id: str
    status: ChallengeResolutionStatus
    responder: Literal["trader", "sentinel", "evidence_tool", "system"]
    response: str
    created_at: datetime
    tool_receipt: EvidenceToolReceipt | None = None


class ResolutionRound(BaseModel):
    """One bounded adversarial dialogue round."""

    round_index: int = Field(ge=0)
    opened_challenge_ids: list[str]
    resolved_challenge_ids: list[str]
    prompt: str
    response: str
    created_at: datetime


class AdversarialResolutionMetadata(BaseModel):
    """Summary of the adversarial resolution loop state."""

    confidence: float = Field(ge=0.0, le=1.0)
    stop_reason: ResolutionStopReason
    unresolved_blocking_count: int = Field(ge=0)
    unresolved_material_count: int = Field(ge=0)
    max_rounds: int = Field(ge=0)


class SentinelVerdict(BaseModel):
    """Adversarial validation verdict from the sentinel."""

    request_hash: str
    trace_id: str
    sentinel_agent_id: int

    evidence_challenges: list[str]
    thesis_challenges: list[str]
    calibration_critique: str

    verdict_score: int = Field(ge=0, le=100)
    verdict_label: Literal["REJECT", "WARN", "PASS", "ENDORSE"]

    dialogue_messages: list[dict[str, Any]]

    structured_challenges: list[AdversarialChallenge] = Field(default_factory=list)
    challenge_resolutions: list[ChallengeResolution] = Field(default_factory=list)
    resolution_rounds: list[ResolutionRound] = Field(default_factory=list)
    resolution_metadata: AdversarialResolutionMetadata | None = None

    model_family: Literal["anthropic-claude", "openai-gpt"]
    model_name: str
    created_at: datetime

    requester_address: str | None = None

    def content_hash(self) -> bytes:
        """Deterministic hash for on-chain anchoring.

        `exclude_defaults=True` preserves the canonical bytes of older pinned
        verdict JSON that did not contain newer optional fields. New verdicts
        that set non-default issue-ledger fields still include them in the hash.
        """
        canonical = json.dumps(
            self.model_dump(mode="json", exclude_defaults=True),
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode()).digest()
