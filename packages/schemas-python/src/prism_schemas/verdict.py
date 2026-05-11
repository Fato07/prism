"""Sentinel verdict schema."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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

    dialogue_messages: list[dict]

    model_family: Literal["anthropic-claude", "openai-gpt"]
    model_name: str
    created_at: datetime

    def content_hash(self) -> bytes:
        """Deterministic hash for on-chain anchoring."""
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True)
        return hashlib.sha256(canonical.encode()).digest()
