"""Structured issue ledger helpers for adversarial verdicts.

The LLM still writes natural-language challenges, but Prism needs a deterministic
issue ledger so the resolution loop can decide whether PASS is allowed.  This
module turns free-text critique plus trace metadata into typed challenges and
applies conservative score caps for unresolved blockers.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime

import structlog
from prism_schemas.trace import TradingR1Trace
from prism_schemas.verdict import (
    AdversarialChallenge,
    AdversarialResolutionMetadata,
    ChallengeSeverity,
    ChallengeType,
)

logger = structlog.get_logger("prism.sentinel.issues")

_RESOLVED_STATUSES = frozenset({"resolved", "superseded"})
_DEFAULT_STALE_DAYS = 365
_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def build_structured_challenges(
    *,
    trace_json: str,
    evidence_challenges: list[str],
    thesis_challenges: list[str],
    calibration_critique: str,
) -> list[AdversarialChallenge]:
    """Build typed challenges from LLM critique and deterministic trace checks."""
    challenges: list[AdversarialChallenge] = []

    for index, text in enumerate(evidence_challenges, start=1):
        challenges.append(
            _from_text(
                challenge_id=f"ev-{index}",
                text=text,
                default_type="source_quality",
                claim_ref=f"evidence_challenges[{index - 1}]",
            )
        )

    for index, text in enumerate(thesis_challenges, start=1):
        challenges.append(
            _from_text(
                challenge_id=f"th-{index}",
                text=text,
                default_type="logic",
                claim_ref=f"thesis_challenges[{index - 1}]",
            )
        )

    if calibration_critique.strip():
        challenges.append(
            _from_text(
                challenge_id="cal-1",
                text=calibration_critique,
                default_type="calibration",
                claim_ref="calibration_critique",
            )
        )

    challenges.extend(_deterministic_trace_issues(trace_json))
    return _dedupe_challenges(challenges)


def apply_unresolved_issue_caps(
    *,
    score: int,
    label: str,
    challenges: list[AdversarialChallenge],
    max_rounds: int = 0,
) -> tuple[int, str, AdversarialResolutionMetadata]:
    """Cap verdict score when blocking/material issues remain unresolved."""
    unresolved_blocking = [
        c
        for c in challenges
        if c.blocking_pass and c.resolution_status not in _RESOLVED_STATUSES
    ]
    unresolved_material = [
        c
        for c in challenges
        if c.severity == "material" and c.resolution_status not in _RESOLVED_STATUSES
    ]

    capped_score = score
    stop_reason = "single_shot"

    if unresolved_blocking:
        capped_score = min(capped_score, 50)
        stop_reason = "unresolved_blockers"
    elif unresolved_material:
        # Material concerns can still PASS, but should not ENDORSE until resolved.
        capped_score = min(capped_score, 75)

    capped_label = _label_for_score(capped_score)
    if capped_score != score or capped_label != label:
        logger.info(
            "verdict_score_capped_by_issue_ledger",
            original_score=score,
            original_label=label,
            capped_score=capped_score,
            capped_label=capped_label,
            unresolved_blocking=len(unresolved_blocking),
            unresolved_material=len(unresolved_material),
        )

    confidence = _confidence_from_issues(capped_score, unresolved_blocking, unresolved_material)
    metadata = AdversarialResolutionMetadata(
        confidence=confidence,
        stop_reason=stop_reason,  # type: ignore[arg-type]
        unresolved_blocking_count=len(unresolved_blocking),
        unresolved_material_count=len(unresolved_material),
        max_rounds=max_rounds,
    )
    return capped_score, capped_label, metadata


def _from_text(
    *,
    challenge_id: str,
    text: str,
    default_type: ChallengeType,
    claim_ref: str,
) -> AdversarialChallenge:
    lowered = text.lower()
    issue_type = _classify_type(lowered, default_type)
    severity = _classify_severity(lowered)
    blocking_pass = severity == "blocking"
    return AdversarialChallenge(
        id=challenge_id,
        type=issue_type,
        severity=severity,
        claim_ref=claim_ref,
        question=text.strip(),
        required_resolution=_required_resolution(issue_type, severity),
        blocking_pass=blocking_pass,
    )


def _classify_type(text: str, default_type: ChallengeType) -> ChallengeType:
    if any(word in text for word in ("stale", "outdated", "date", "current", "recent", "temporal")):
        return "temporal"
    if any(word in text for word in ("calibration", "probability", "confidence", "overconfident")):
        return "calibration"
    if any(word in text for word in ("irrelevant", "relevance", "not relevant")):
        return "relevance"
    if any(word in text for word in ("resolved", "closed", "expired", "market")):
        return "market_structure"
    if any(word in text for word in ("risk", "downside", "tail")):
        return "risk"
    if any(word in text for word in ("logic", "contradict", "therefore", "because")):
        return "logic"
    return default_type


def _classify_severity(text: str) -> ChallengeSeverity:
    blocking_terms = ("fabricated", "false", "contradictory", "dangerous", "impossible")
    if any(word in text for word in blocking_terms):
        return "blocking"
    if any(
        word in text
        for word in (
            "stale",
            "outdated",
            "unsupported",
            "unreliable",
            "missing",
            "lacks",
            "does not",
            "undermines",
            "weak",
        )
    ):
        return "material"
    return "minor"


def _required_resolution(issue_type: ChallengeType, severity: ChallengeSeverity) -> str:
    if issue_type == "temporal":
        return "Provide current, date-aligned evidence or revise the action/probability."
    if issue_type == "market_structure":
        return "Verify the market is active, unresolved, and maps to a live event."
    if issue_type == "calibration":
        return "Recompute probability with the challenged uncertainty explicitly handled."
    if issue_type == "source_quality":
        return "Replace or corroborate weak sources with primary or reputable sources."
    if severity == "blocking":
        return "Resolve before PASS is allowed."
    return "Address in the trader response or explain why it does not affect the verdict."


def _deterministic_trace_issues(trace_json: str) -> list[AdversarialChallenge]:
    try:
        raw = json.loads(trace_json)
        trace = TradingR1Trace.model_validate(raw)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("trace_issue_parse_failed", error=str(exc))
        return []

    issues: list[AdversarialChallenge] = []
    stale_days = int(os.environ.get("SENTINEL_EVIDENCE_STALE_DAYS", str(_DEFAULT_STALE_DAYS)))
    stale_indices: list[int] = []
    future_indices: list[int] = []

    created_at = trace.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)

    for index, evidence in enumerate(trace.evidence):
        timestamp = evidence.timestamp
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        age_days = (created_at - timestamp).days
        if age_days > stale_days:
            stale_indices.append(index)
        if age_days < -1:
            future_indices.append(index)

    if stale_indices:
        all_stale = len(stale_indices) == len(trace.evidence)
        severity: ChallengeSeverity = (
            "blocking" if all_stale and trace.action != "HOLD" else "material"
        )
        issues.append(
            AdversarialChallenge(
                id="sys-temporal-stale-evidence",
                type="temporal",
                severity=severity,
                claim_ref=",".join(f"evidence[{i}]" for i in stale_indices),
                question=(
                    f"{len(stale_indices)}/{len(trace.evidence)} evidence items are older than "
                    f"{stale_days} days relative to trace creation."
                ),
                required_resolution="Provide current evidence or revise to HOLD/lower confidence.",
                blocking_pass=severity == "blocking",
            )
        )

    if future_indices:
        issues.append(
            AdversarialChallenge(
                id="sys-temporal-future-evidence",
                type="temporal",
                severity="blocking",
                claim_ref=",".join(f"evidence[{i}]" for i in future_indices),
                question="Evidence timestamps are after the trace creation time.",
                required_resolution="Correct evidence timestamps or remove unsupported claims.",
                blocking_pass=True,
            )
        )

    past_date_issue = _ambiguous_past_event_date_issue(trace.market_question, created_at)
    if past_date_issue is not None:
        issues.append(past_date_issue)

    return issues


def _ambiguous_past_event_date_issue(
    market_question: str,
    created_at: datetime,
) -> AdversarialChallenge | None:
    # Catches market titles like "during the Feb 7 game" when evaluated months later
    # and no explicit future year is present. It is material, not automatically
    # blocking, because some markets reference recurring annual dates.
    if re.search(r"\b20\d{2}\b", market_question):
        return None

    match = re.search(
        r"\b(" + "|".join(_MONTHS.keys()) + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b",
        market_question,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    month = _MONTHS[match.group(1).lower().rstrip(".")]
    day = int(match.group(2))
    try:
        inferred = datetime(created_at.year, month, day, tzinfo=created_at.tzinfo or UTC)
    except ValueError:
        return None

    if (created_at - inferred).days <= 7:
        return None

    return AdversarialChallenge(
        id="sys-market-ambiguous-past-date",
        type="market_structure",
        severity="material",
        claim_ref="market_question",
        question=(
            "The market question references a month/day that appears to be in the past "
            "relative to trace creation and does not include a year."
        ),
        required_resolution="Verify the market event date/end date before trading.",
        blocking_pass=False,
    )


def _dedupe_challenges(challenges: list[AdversarialChallenge]) -> list[AdversarialChallenge]:
    seen: set[str] = set()
    unique: list[AdversarialChallenge] = []
    for challenge in challenges:
        key = challenge.id
        if key in seen:
            continue
        seen.add(key)
        unique.append(challenge)
    return unique


def _label_for_score(score: int) -> str:
    if score <= 25:
        return "REJECT"
    if score <= 50:
        return "WARN"
    if score <= 75:
        return "PASS"
    return "ENDORSE"


def _confidence_from_issues(
    score: int,
    unresolved_blocking: list[AdversarialChallenge],
    unresolved_material: list[AdversarialChallenge],
) -> float:
    base = score / 100
    penalty = (0.25 * len(unresolved_blocking)) + (0.08 * len(unresolved_material))
    return max(0.0, min(1.0, round(base - penalty, 2)))
