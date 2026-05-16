"""Pydantic models for Prism calibration corpus rows."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from prism_schemas.trace import TradingR1Trace
from pydantic import BaseModel, ConfigDict, Field, model_validator

SourceType = Literal["sample", "synthetic", "mutated", "real"]
SplitName = Literal["sample", "pilot", "dev", "holdout", "canary"]
ValidationStatus = Literal["validated", "unvalidated"]
VerdictBand = Literal["REJECT", "WARN", "PASS", "ENDORSE"]
ReviewDestination = Literal["manual_review", "auto_resolved"]
ReviewRouteReason = Literal[
    "low_confidence",
    "label_disagreement",
    "holdout_locked",
    "high_confidence_consensus",
    "needs_manual_review",
]
ReviewStatus = Literal[
    "unreviewed",
    "ai_labeled",
    "ai_resolved",
    "manual_review",
    "human_reviewed",
    "approved",
    "rejected",
]


class HarvestedTraceProvenance(BaseModel):
    """Upstream Neon/IPFS trace metadata preserved on real harvested rows."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(min_length=1)
    agent_id: int
    market_id: str = Field(min_length=1)
    ipfs_cid: str = Field(min_length=1)
    ipfs_uri: str = Field(min_length=1)
    db_content_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    normalized_content_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    trace_tx_hash: str | None = None
    db_created_at: datetime
    payload_created_at: datetime


class HarvestValidationProvenance(BaseModel):
    """Optional validation/requester context attached to real harvested rows."""

    model_config = ConfigDict(extra="forbid")

    status: ValidationStatus
    request_hash: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    sentinel_agent_id: int | None = None
    verdict_score: int | None = Field(default=None, ge=0, le=100)
    response_uri: str | None = None
    response_cid: str | None = None
    requester_address: str | None = None
    tx_hash: str | None = None
    created_at: datetime | None = None

    @model_validator(mode="after")
    def require_validated_fields(self) -> Self:
        """Require core validation fields when a trace is marked validated."""
        if self.status == "validated":
            missing: list[str] = []
            if self.request_hash is None:
                missing.append("request_hash")
            if self.sentinel_agent_id is None:
                missing.append("sentinel_agent_id")
            if self.verdict_score is None:
                missing.append("verdict_score")
            if missing:
                missing_fields = ", ".join(missing)
                raise ValueError(
                    "validated harvest provenance requires: " + missing_fields
                )
        return self


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
    harvested_trace: HarvestedTraceProvenance | None = None
    validation: HarvestValidationProvenance | None = None

    @model_validator(mode="after")
    def require_source_specific_metadata(self) -> Self:
        """Require source-specific metadata for mutated and real rows."""
        if self.source_type == "mutated" and not self.parent_row_id:
            raise ValueError("parent_row_id is required when source_type is mutated")
        if self.source_type == "mutated" and not self.mutation_type:
            raise ValueError("mutation_type is required when source_type is mutated")
        if self.source_type == "real" and self.harvested_trace is None:
            raise ValueError("harvested_trace is required when source_type is real")
        if self.source_type == "real" and self.validation is None:
            raise ValueError("validation is required when source_type is real")
        return self


class RubricPreLabel(BaseModel):
    """Normalized Prism-compatible AI rubric output for one calibration row."""

    model_config = ConfigDict(extra="forbid")

    reasoning_quality: int = Field(ge=0, le=100)
    evidence_quality: int = Field(ge=0, le=100)
    calibration_quality: int = Field(ge=0, le=100)
    verdict_band: VerdictBand
    failure_tags: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    model_family: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    labeled_at: datetime


class ReviewRouting(BaseModel):
    """Routing metadata that explains whether a row needs manual review."""

    model_config = ConfigDict(extra="forbid")

    destination: ReviewDestination
    route_reasons: list[ReviewRouteReason] = Field(default_factory=list)
    routed_at: datetime


class ReviewState(BaseModel):
    """Review metadata that proves the row has an explicit review state."""

    model_config = ConfigDict(extra="forbid")

    status: ReviewStatus
    rubric_version: str = Field(min_length=1)
    failure_tags: list[str] = Field(default_factory=list)
    ai_labels: list[RubricPreLabel] = Field(default_factory=list)
    canonical_label: RubricPreLabel | None = None
    routing: ReviewRouting | None = None
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
