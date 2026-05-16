"""Synthetic trace seeding and mutation generation for calibration rows."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from prism_schemas.trace import Evidence, ThesisStep, TradingR1Trace

from prism_calibration.layout import bootstrap_corpus_root
from prism_calibration.lineage import LoadedRow, load_row_reference
from prism_calibration.models import (
    CalibrationRow,
    CorpusProvenance,
    ReviewState,
    SourceType,
    SplitMetadata,
)
from prism_calibration.splits import ASSIGNED_AT, SPLIT_POLICY, split_for_lineage, write_row

GENERATION_CREATED_AT = datetime(2026, 5, 16, 12, 0, tzinfo=UTC)
RUBRIC_VERSION = "prism-calibration-v1"
DEFAULT_LABEL_SEED = 42

Action = Literal["BUY", "SELL", "HOLD"]


class LabelGenerationError(ValueError):
    """Raised when synthetic or mutation generation inputs are invalid."""


@dataclass(frozen=True)
class SyntheticTemplate:
    """Template describing one deterministic synthetic quality band."""

    quality_band: str
    failure_tags: tuple[str, ...]
    raw_probability: float
    volatility_adjustment: float
    final_probability: float
    action: Action
    evidence_confidence: float
    proposition: str
    evidence_claim: str
    risk_factors: tuple[str, ...]
    rationale: str


@dataclass(frozen=True)
class MutationTemplate:
    """Template describing one deterministic targeted mutation."""

    mutation_type: str
    failure_tag: str


@dataclass(frozen=True)
class WrittenLabelRow:
    """Metadata for one generated row written to disk."""

    row_id: str
    path: Path
    source_type: SourceType
    quality_band: str | None
    failure_tags: tuple[str, ...]
    mutation_type: str | None = None
    parent_row_id: str | None = None


@dataclass(frozen=True)
class LabelGenerationResult:
    """Summary of one labeling generation command."""

    operation: Literal["generate-synthetic", "generate-mutations"]
    run_id: str
    requested_count: int
    manifest_path: Path
    rows: tuple[WrittenLabelRow, ...]
    parent_row_id: str | None = None


SYNTHETIC_TEMPLATES: tuple[SyntheticTemplate, ...] = (
    SyntheticTemplate(
        quality_band="high",
        failure_tags=(),
        raw_probability=0.74,
        volatility_adjustment=-0.03,
        final_probability=0.71,
        action="BUY",
        evidence_confidence=0.9,
        proposition="Multiple independent signals support a carefully sized trade.",
        evidence_claim=(
            "Liquidity, recent pricing, and known market constraints all support the "
            "same directional thesis."
        ),
        risk_factors=(
            "Late-breaking news could invalidate the estimate.",
            "Thin liquidity may widen the effective fill price.",
        ),
        rationale=(
            "This high-quality synthetic trace weighs evidence and risk before taking "
            "a modest BUY stance."
        ),
    ),
    SyntheticTemplate(
        quality_band="medium",
        failure_tags=("weak-evidence",),
        raw_probability=0.61,
        volatility_adjustment=-0.05,
        final_probability=0.56,
        action="HOLD",
        evidence_confidence=0.55,
        proposition="The thesis is plausible but rests on a narrow evidence base.",
        evidence_claim=(
            "One public signal points in the expected direction, but corroboration is "
            "thin."
        ),
        risk_factors=(
            "The trace may overweight one source.",
            "The market can move before stronger evidence arrives.",
        ),
        rationale=(
            "This medium-quality trace recognizes uncertainty and holds rather than "
            "overtrading weak evidence."
        ),
    ),
    SyntheticTemplate(
        quality_band="low",
        failure_tags=("calibration-overconfidence",),
        raw_probability=0.91,
        volatility_adjustment=0.04,
        final_probability=0.95,
        action="BUY",
        evidence_confidence=0.42,
        proposition="The trace jumps from a weak signal to an extreme probability.",
        evidence_claim=(
            "A single anecdotal update is treated as decisive despite low source "
            "confidence."
        ),
        risk_factors=("The probability estimate is not calibrated to evidence strength.",),
        rationale=(
            "This low-quality trace intentionally overstates confidence for calibration "
            "review."
        ),
    ),
    SyntheticTemplate(
        quality_band="low",
        failure_tags=("missing-counterevidence",),
        raw_probability=0.18,
        volatility_adjustment=0.07,
        final_probability=0.25,
        action="SELL",
        evidence_confidence=0.47,
        proposition="The trace makes a directional call while omitting opposing signals.",
        evidence_claim=(
            "A stale bearish datapoint is cited without checking fresh counterevidence."
        ),
        risk_factors=("Important counterevidence is missing from the reasoning trace.",),
        rationale=(
            "This low-quality trace is useful because it preserves schema shape while "
            "surfacing a missing-counterevidence failure."
        ),
    ),
)

MUTATION_TEMPLATES: tuple[MutationTemplate, ...] = (
    MutationTemplate("weak-evidence", "weak-evidence"),
    MutationTemplate("probability-overstatement", "calibration-overconfidence"),
    MutationTemplate("missing-counterevidence", "missing-counterevidence"),
    MutationTemplate("stale-evidence", "stale-evidence"),
)

SYNTHETIC_MARKETS: tuple[tuple[str, str], ...] = (
    (
        "polymarket-calibration-arc-usdc-001",
        "Will Arc testnet USDC settlement remain reliable for Prism demos this week?",
    ),
    (
        "polymarket-calibration-agents-002",
        "Will agent-to-agent validation be highlighted in the next Prism pitch update?",
    ),
    (
        "polymarket-calibration-builder-003",
        "Will builder-code attribution remain visible in Prism paper-trade receipts?",
    ),
    (
        "polymarket-calibration-x402-004",
        "Will an external agent complete a paid x402 validation call before the demo?",
    ),
)


def _safe_identifier(value: str) -> str:
    """Return a filesystem-safe identifier fragment."""
    lowered = value.lower()
    cleaned = "".join(char if char.isalnum() else "-" for char in lowered).strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned or "row"


def _ensure_positive_count(count: int) -> None:
    """Reject non-positive generation counts."""
    if count <= 0:
        raise LabelGenerationError("count must be greater than 0")


def _market_for_index(index: int) -> tuple[str, str]:
    """Return a deterministic synthetic market identity for an index."""
    return SYNTHETIC_MARKETS[index % len(SYNTHETIC_MARKETS)]


def _trace_action(final_probability: float) -> Action:
    """Choose an action from a final probability."""
    if final_probability >= 0.62:
        return "BUY"
    if final_probability <= 0.38:
        return "SELL"
    return "HOLD"


def _clamp_probability(value: float) -> float:
    """Clamp and round a probability into the Prism schema range."""
    return round(min(0.99, max(0.01, value)), 2)


def _row_path(root: Path, row_id: str) -> Path:
    """Return the private corpus row path for a row ID."""
    return root / "rows" / f"{row_id}.json"


def _manifest_path(root: Path, run_id: str) -> Path:
    """Return the manifest path for a generation run."""
    return root / "manifests" / f"{_safe_identifier(run_id)}.json"


def _write_generation_manifest(result: LabelGenerationResult) -> None:
    """Write the machine-readable manifest for a generation result."""
    result.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    result.manifest_path.write_text(
        json.dumps(label_generation_summary(result), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _synthetic_trace(index: int, template: SyntheticTemplate) -> TradingR1Trace:
    """Build one deterministic schema-valid synthetic Trading-R1 trace."""
    market_id, market_question = _market_for_index(index)
    trace_index = index + 1
    evidence = Evidence(
        source=f"prism-synthetic-seed/{template.quality_band}",
        claim=template.evidence_claim,
        confidence=template.evidence_confidence,
        timestamp=GENERATION_CREATED_AT,
    )
    thesis = ThesisStep(
        proposition=template.proposition,
        supporting_evidence_ids=[0],
        risk_factors=list(template.risk_factors),
    )
    return TradingR1Trace(
        trace_id=f"synthetic-trace-{trace_index:04d}",
        agent_id=4140,
        market_id=market_id,
        market_question=market_question,
        thesis=[thesis],
        evidence=[evidence],
        raw_probability=template.raw_probability,
        volatility_adjustment=template.volatility_adjustment,
        final_probability=template.final_probability,
        action=template.action,
        size_usdc=0.0 if template.action == "HOLD" else 5.0,
        price_limit=template.final_probability,
        rationale=template.rationale,
        model_family="anthropic-claude",
        model_name="synthetic-calibration-seed-v1",
        created_at=GENERATION_CREATED_AT,
    )


def _split_metadata(lineage_id: str, *, seed: int) -> SplitMetadata:
    """Return deterministic split metadata for a generated lineage."""
    return SplitMetadata(
        name=split_for_lineage(lineage_id, seed=seed),
        policy=SPLIT_POLICY,
        seed=seed,
        assigned_at=ASSIGNED_AT,
    )


def _synthetic_row(index: int, *, run_id: str, seed: int) -> tuple[CalibrationRow, str]:
    """Build one synthetic calibration row and return its quality band."""
    template = SYNTHETIC_TEMPLATES[index % len(SYNTHETIC_TEMPLATES)]
    row_number = index + 1
    row_id = f"synthetic-{row_number:04d}"
    lineage_id = f"lineage-synthetic-{row_number:04d}"
    trace = _synthetic_trace(index, template)
    content_hash = trace.content_hash().hex()
    row = CalibrationRow(
        row_id=row_id,
        trace=trace,
        provenance=CorpusProvenance(
            source_type="synthetic",
            source_ref=f"synthetic:seed-v1/{template.quality_band}/{row_number:04d}",
            run_id=run_id,
            lineage_id=lineage_id,
            content_hash=content_hash,
            created_at=GENERATION_CREATED_AT,
        ),
        review=ReviewState(
            status="unreviewed",
            rubric_version=RUBRIC_VERSION,
            failure_tags=list(template.failure_tags),
            notes=f"Synthetic seed row for quality_band={template.quality_band}.",
        ),
        split=_split_metadata(lineage_id, seed=seed),
    )
    return row, template.quality_band


def _base_evidence(trace: TradingR1Trace) -> Evidence:
    """Return the first evidence item or a generated placeholder."""
    if trace.evidence:
        return trace.evidence[0]
    return Evidence(
        source="mutation-placeholder",
        claim="Placeholder evidence inserted for mutation generation.",
        confidence=0.5,
        timestamp=GENERATION_CREATED_AT,
    )


def _base_thesis(trace: TradingR1Trace) -> ThesisStep:
    """Return the first thesis step or a generated placeholder."""
    if trace.thesis:
        return trace.thesis[0]
    return ThesisStep(
        proposition="Placeholder thesis inserted for mutation generation.",
        supporting_evidence_ids=[0],
        risk_factors=["Original trace did not include thesis risk factors."],
    )


def _replace_first_evidence(
    trace: TradingR1Trace,
    *,
    claim: str,
    confidence: float,
    source_suffix: str,
    timestamp: datetime = GENERATION_CREATED_AT,
) -> list[Evidence]:
    """Return evidence with the first item mutated and remaining evidence preserved."""
    base = _base_evidence(trace)
    mutated = base.model_copy(
        update={
            "claim": claim,
            "confidence": _clamp_probability(confidence),
            "source": f"{base.source}|mutation:{source_suffix}",
            "timestamp": timestamp,
        }
    )
    return [mutated, *list(trace.evidence[1:])]


def _replace_first_thesis(
    trace: TradingR1Trace,
    *,
    proposition: str,
    risk_factors: list[str],
) -> list[ThesisStep]:
    """Return thesis steps with the first step mutated and remaining steps preserved."""
    base = _base_thesis(trace)
    mutated = base.model_copy(
        update={
            "proposition": proposition,
            "risk_factors": risk_factors,
            "supporting_evidence_ids": base.supporting_evidence_ids or [0],
        }
    )
    return [mutated, *list(trace.thesis[1:])]


def _mutated_trace(
    parent: TradingR1Trace,
    template: MutationTemplate,
    index: int,
) -> TradingR1Trace:
    """Return a mutated trace preserving parent market identity."""
    mutation_index = index + 1
    mutation_type = template.mutation_type
    raw_probability = parent.raw_probability
    final_probability = parent.final_probability
    volatility_adjustment = parent.volatility_adjustment

    if mutation_type == "weak-evidence":
        final_probability = _clamp_probability(parent.final_probability - 0.12)
        raw_probability = _clamp_probability(parent.raw_probability - 0.1)
        evidence = _replace_first_evidence(
            parent,
            claim=(
                "Mutation weakens the parent claim by relying on a single, "
                "uncorroborated signal."
            ),
            confidence=_base_evidence(parent).confidence * 0.45,
            source_suffix=mutation_type,
        )
        thesis = _replace_first_thesis(
            parent,
            proposition="The parent thesis is repeated with materially weaker support.",
            risk_factors=["Evidence quality was intentionally weakened."],
        )
        rationale = "This mutation lowers evidence quality while preserving the market."
    elif mutation_type == "probability-overstatement":
        final_probability = _clamp_probability(parent.final_probability + 0.24)
        raw_probability = _clamp_probability(parent.raw_probability + 0.22)
        evidence = _replace_first_evidence(
            parent,
            claim=(
                "Mutation keeps the parent signal but treats it as nearly decisive "
                "without extra support."
            ),
            confidence=max(_base_evidence(parent).confidence, 0.62),
            source_suffix=mutation_type,
        )
        thesis = _replace_first_thesis(
            parent,
            proposition="The parent thesis is overstated into an aggressive conclusion.",
            risk_factors=["Probability was inflated beyond evidence strength."],
        )
        rationale = "This mutation overstates calibration confidence for review."
    elif mutation_type == "missing-counterevidence":
        final_probability = _clamp_probability(parent.final_probability + 0.14)
        raw_probability = _clamp_probability(parent.raw_probability + 0.12)
        evidence = _replace_first_evidence(
            parent,
            claim=(
                "Mutation cites supporting evidence while omitting the strongest "
                "available counterevidence."
            ),
            confidence=_base_evidence(parent).confidence,
            source_suffix=mutation_type,
        )
        thesis = _replace_first_thesis(
            parent,
            proposition="The parent thesis is narrowed to supporting evidence only.",
            risk_factors=["Counterevidence was intentionally omitted from the trace."],
        )
        rationale = "This mutation removes balanced counterevidence while keeping the market."
    elif mutation_type == "stale-evidence":
        final_probability = _clamp_probability(parent.final_probability - 0.08)
        raw_probability = _clamp_probability(parent.raw_probability - 0.06)
        evidence = _replace_first_evidence(
            parent,
            claim=(
                "Mutation relies on stale evidence that may no longer describe current "
                "market conditions."
            ),
            confidence=min(_base_evidence(parent).confidence, 0.58),
            source_suffix=mutation_type,
            timestamp=datetime(2026, 4, 16, 12, 0, tzinfo=UTC),
        )
        thesis = _replace_first_thesis(
            parent,
            proposition="The parent thesis is rebuilt around stale evidence.",
            risk_factors=["Evidence freshness was intentionally degraded."],
        )
        rationale = "This mutation changes evidence freshness without changing market identity."
    else:
        raise LabelGenerationError(f"Unsupported mutation type: {mutation_type}")

    volatility_adjustment = round(final_probability - raw_probability, 3)
    action = _trace_action(final_probability)
    return parent.model_copy(
        update={
            "trace_id": f"{parent.trace_id}-mutated-{mutation_type}-{mutation_index:04d}",
            "thesis": thesis,
            "evidence": evidence,
            "raw_probability": raw_probability,
            "volatility_adjustment": volatility_adjustment,
            "final_probability": final_probability,
            "action": action,
            "size_usdc": 0.0 if action == "HOLD" else max(parent.size_usdc, 1.0),
            "price_limit": final_probability,
            "rationale": rationale,
            "model_name": f"{parent.model_name}+{mutation_type}",
            "created_at": GENERATION_CREATED_AT,
        }
    )


def _mutation_row(
    *,
    parent: CalibrationRow,
    index: int,
    run_id: str,
    seed: int,
) -> CalibrationRow:
    """Build one mutation row for a parent calibration row."""
    template = MUTATION_TEMPLATES[index % len(MUTATION_TEMPLATES)]
    row_id = f"mutated-{_safe_identifier(parent.row_id)}-{index + 1:04d}-{template.mutation_type}"
    trace = _mutated_trace(parent.trace, template, index)
    content_hash = trace.content_hash().hex()
    lineage_id = parent.provenance.lineage_id
    return CalibrationRow(
        row_id=row_id,
        trace=trace,
        provenance=CorpusProvenance(
            source_type="mutated",
            source_ref=f"mutation:{parent.row_id}/{template.mutation_type}/{index + 1:04d}",
            run_id=run_id,
            lineage_id=lineage_id,
            content_hash=content_hash,
            created_at=GENERATION_CREATED_AT,
            parent_row_id=parent.row_id,
            mutation_type=template.mutation_type,
        ),
        review=ReviewState(
            status="unreviewed",
            rubric_version=RUBRIC_VERSION,
            failure_tags=[template.failure_tag],
            notes=(
                "Generated mutation targeting "
                f"{template.failure_tag} while preserving parent market identity."
            ),
        ),
        split=_split_metadata(lineage_id, seed=seed),
    )


def generate_synthetic_rows(
    *,
    root: Path,
    count: int,
    seed: int = DEFAULT_LABEL_SEED,
) -> LabelGenerationResult:
    """Generate deterministic synthetic calibration rows under the local corpus root."""
    _ensure_positive_count(count)
    layout = bootstrap_corpus_root(root)
    run_id = f"synthetic-seed-v1-count-{count}-seed-{seed}"
    written: list[WrittenLabelRow] = []

    for index in range(count):
        row, quality_band = _synthetic_row(index, run_id=run_id, seed=seed)
        path = _row_path(layout.root, row.row_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_row(path, row)
        written.append(
            WrittenLabelRow(
                row_id=row.row_id,
                path=path,
                source_type=row.provenance.source_type,
                quality_band=quality_band,
                failure_tags=tuple(row.review.failure_tags),
            )
        )

    result = LabelGenerationResult(
        operation="generate-synthetic",
        run_id=run_id,
        requested_count=count,
        manifest_path=_manifest_path(layout.root, run_id),
        rows=tuple(written),
    )
    _write_generation_manifest(result)
    return result


def generate_mutation_rows(
    *,
    root: Path,
    source: Path,
    count: int,
    seed: int = DEFAULT_LABEL_SEED,
) -> LabelGenerationResult:
    """Generate deterministic mutated derivatives for a local parent row."""
    _ensure_positive_count(count)
    layout = bootstrap_corpus_root(root)
    loaded_parent: LoadedRow = load_row_reference(source, layout.root)
    parent = loaded_parent.row
    run_id = f"mutation-seed-v1-parent-{_safe_identifier(parent.row_id)}-count-{count}-seed-{seed}"
    written: list[WrittenLabelRow] = []

    for index in range(count):
        row = _mutation_row(parent=parent, index=index, run_id=run_id, seed=seed)
        path = _row_path(layout.root, row.row_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_row(path, row)
        written.append(
            WrittenLabelRow(
                row_id=row.row_id,
                path=path,
                source_type=row.provenance.source_type,
                quality_band=None,
                failure_tags=tuple(row.review.failure_tags),
                mutation_type=row.provenance.mutation_type,
                parent_row_id=parent.row_id,
            )
        )

    result = LabelGenerationResult(
        operation="generate-mutations",
        run_id=run_id,
        requested_count=count,
        manifest_path=_manifest_path(layout.root, run_id),
        rows=tuple(written),
        parent_row_id=parent.row_id,
    )
    _write_generation_manifest(result)
    return result


def _counter_payload(counter: Counter[str]) -> dict[str, int]:
    """Return a stable JSON payload for a string counter."""
    return dict(sorted(counter.items()))


def label_generation_summary(result: LabelGenerationResult) -> dict[str, object]:
    """Return a deterministic machine-readable generation summary."""
    source_counts: Counter[str] = Counter(row.source_type for row in result.rows)
    quality_bands: Counter[str] = Counter(
        row.quality_band for row in result.rows if row.quality_band is not None
    )
    mutation_types: Counter[str] = Counter(
        row.mutation_type for row in result.rows if row.mutation_type is not None
    )
    failure_tags: Counter[str] = Counter(
        failure_tag for row in result.rows for failure_tag in row.failure_tags
    )

    payload: dict[str, object] = {
        "authority": "local",
        "failure_tags": _counter_payload(failure_tags),
        "manifest_path": str(result.manifest_path),
        "operation": result.operation,
        "quality_bands": _counter_payload(quality_bands),
        "requested_count": result.requested_count,
        "row_ids": [row.row_id for row in result.rows],
        "rows": [
            {
                "failure_tags": list(row.failure_tags),
                "mutation_type": row.mutation_type,
                "parent_row_id": row.parent_row_id,
                "path": str(row.path),
                "quality_band": row.quality_band,
                "row_id": row.row_id,
                "source_type": row.source_type,
            }
            for row in result.rows
        ],
        "run_id": result.run_id,
        "source_counts": _counter_payload(source_counts),
        "written_count": len(result.rows),
    }
    if result.parent_row_id is not None:
        payload["parent_row_id"] = result.parent_row_id
        payload["mutation_types"] = _counter_payload(mutation_types)
    return payload
