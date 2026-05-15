"""Pydantic models for Prism calibration corpus rows."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from prism_schemas.trace import TradingR1Trace
from pydantic import BaseModel, ConfigDict, Field, model_validator

SourceType = Literal["sample", "synthetic", "mutated", "real"]
SplitName = Literal["sample", "pilot", "dev", "holdout", "canary"]
ReviewStatus = Literal[
    "unreviewed",
    "ai_labeled",
    "manual_review",
    "human_reviewed",
    "approved",
    "rejected",
]


class CorpusProvenance(BaseModel):
    """Offline-auditable source metadata for one calibration row."""

    model_config = ConfigDict(extra="forbid")

    source_type: SourceType
    source_ref: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    lineage_id: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    created_at: datetime
    parent_row_id: str | None = None
    mutation_type: str | None = None

    @model_validator(mode="after")
    def require_mutation_parent(self) -> Self:
        """Require parent metadata for mutated rows."""
        if self.source_type == "mutated" and not self.parent_row_id:
            raise ValueError("parent_row_id is required when source_type is mutated")
        if self.source_type == "mutated" and not self.mutation_type:
            raise ValueError("mutation_type is required when source_type is mutated")
        return self


class ReviewState(BaseModel):
    """Review metadata that proves the row has an explicit review state."""

    model_config = ConfigDict(extra="forbid")

    status: ReviewStatus
    rubric_version: str = Field(min_length=1)
    failure_tags: list[str] = Field(default_factory=list)
    notes: str | None = None
    reviewer: str | None = None
    reviewed_at: datetime | None = None


class SplitMetadata(BaseModel):
    """Split assignment metadata for local corpus membership."""

    model_config = ConfigDict(extra="forbid")

    name: SplitName
    policy: str = Field(min_length=1)
    seed: int = Field(ge=0)
    assigned_at: datetime


class CalibrationRow(BaseModel):
    """A canonical local calibration corpus row."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    row_id: str = Field(min_length=1)
    trace: TradingR1Trace
    provenance: CorpusProvenance
    review: ReviewState
    split: SplitMetadata

    @model_validator(mode="after")
    def require_trace_row_alignment(self) -> Self:
        """Ensure provenance and split values are internally consistent."""
        if self.provenance.source_type == "sample" and self.split.name != "sample":
            raise ValueError("sample rows must use split.name=sample")
        return self
