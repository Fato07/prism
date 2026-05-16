"""Deterministic trace-quality metrics for Prism reports."""

from __future__ import annotations

import re

from prism_cli.models import InspectResult, Readiness, ReasoningMetrics, TradingR1Trace

_FALSIFICATION_TERMS = re.compile(
    r"\b(falsif|invalidate|disconfirm|stop loss|stop-loss|exit if|wrong if|counterevidence)\b",
    re.IGNORECASE,
)


def inspect_trace(trace: TradingR1Trace) -> InspectResult:
    """Compute deterministic reasoning metrics for a Trading-R1 trace."""
    evidence_count = len(trace.evidence)
    source_diversity = len({e.source.strip().lower() for e in trace.evidence if e.source.strip()})
    thesis_steps = len(trace.thesis)

    refs: list[int] = []
    valid_refs: set[int] = set()
    unsupported_steps = 0
    invalid_ref_count = 0
    risk_factor_count = 0

    for step in trace.thesis:
        risk_factor_count += len(step.risk_factors)
        step_has_valid_ref = False
        for ref in step.supporting_evidence_ids:
            refs.append(ref)
            if 0 <= ref < evidence_count:
                valid_refs.add(ref)
                step_has_valid_ref = True
            else:
                invalid_ref_count += 1
        if not step_has_valid_ref:
            unsupported_steps += 1

    avg_confidence = (
        sum(e.confidence for e in trace.evidence) / evidence_count if evidence_count else 0.0
    )
    evidence_coverage = len(valid_refs) / evidence_count if evidence_count else 0.0
    probability_delta = abs(trace.final_probability - trace.raw_probability)
    falsification_text = " ".join(
        [trace.rationale, *[" ".join(step.risk_factors) for step in trace.thesis]]
    )
    has_falsification_language = bool(_FALSIFICATION_TERMS.search(falsification_text))

    metrics = ReasoningMetrics(
        evidence_count=evidence_count,
        source_diversity=source_diversity,
        thesis_steps=thesis_steps,
        evidence_reference_count=len(refs),
        evidence_coverage=round(evidence_coverage, 4),
        invalid_evidence_refs=invalid_ref_count,
        unsupported_thesis_steps=unsupported_steps,
        risk_factor_count=risk_factor_count,
        avg_evidence_confidence=round(avg_confidence, 4),
        probability_delta=round(probability_delta, 4),
        has_falsification_language=has_falsification_language,
    )

    warnings = _warnings(metrics)
    return InspectResult(
        trace_id=trace.trace_id,
        market_id=trace.market_id,
        market_question=trace.market_question,
        action=trace.action,
        readiness=_readiness(metrics),
        reasoning_metrics=metrics,
        warnings=warnings,
    )


def _readiness(metrics: ReasoningMetrics) -> Readiness:
    """Classify whether a trace is ready for adversarial validation/routing."""
    if (
        metrics.evidence_count >= 2
        and metrics.thesis_steps >= 1
        and metrics.evidence_coverage >= 0.67
        and metrics.invalid_evidence_refs == 0
        and metrics.unsupported_thesis_steps == 0
        and metrics.risk_factor_count >= 1
    ):
        return "usable"

    if (
        metrics.evidence_count == 0
        or metrics.thesis_steps == 0
        or metrics.invalid_evidence_refs > 0
    ):
        return "not_ready"

    return "needs_review"


def _warnings(metrics: ReasoningMetrics) -> list[str]:
    """Return human-readable warnings for weak deterministic metrics."""
    warnings: list[str] = []
    if metrics.evidence_count < 2:
        warnings.append("Trace has fewer than 2 evidence items.")
    if metrics.source_diversity < 2 and metrics.evidence_count >= 2:
        warnings.append("Evidence comes from fewer than 2 distinct sources.")
    if metrics.evidence_coverage < 0.67:
        warnings.append("Less than two-thirds of evidence is referenced by thesis steps.")
    if metrics.invalid_evidence_refs > 0:
        warnings.append("Trace contains thesis references to missing evidence IDs.")
    if metrics.unsupported_thesis_steps > 0:
        warnings.append("At least one thesis step has no valid supporting evidence reference.")
    if metrics.risk_factor_count == 0:
        warnings.append("Trace lists no risk factors.")
    if not metrics.has_falsification_language:
        warnings.append("Trace does not state clear falsification or exit language.")
    return warnings
