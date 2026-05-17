"""Bounded adversarial resolution loop.

The first milestone keeps the loop deterministic and provider-pluggable:
1. Generate the normal sentinel verdict.
2. Inspect the structured issue ledger.
3. If material/blocking issues remain, run a bounded retrieval/response round.
4. Re-apply issue caps and persist the loop transcript on the verdict.

Future work can replace the deterministic trader response with a dedicated
Mirascope trader-defense call, but the state machine and schemas are already in
place.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

import structlog
from prism_schemas.trace import TradingR1Trace
from prism_schemas.verdict import (
    AdversarialChallenge,
    ChallengeResolution,
    ResolutionRound,
    SentinelVerdict,
)

from sentinel.adversarial import generate_verdict
from sentinel.evidence_tools import (
    EvidenceProvider,
    EvidenceSearchRequest,
    evidence_provider_from_runtime,
    query_for_challenge,
)
from sentinel.issues import apply_unresolved_issue_caps

logger = structlog.get_logger("prism.sentinel.resolution_loop")

_RESOLVED_STATUSES = frozenset({"resolved", "superseded"})


async def generate_verdict_with_resolution(
    *,
    trace_json: str,
    request_hash: str = "",
    trace_id: str = "",
    sentinel_agent_id: int = 0,
    max_rounds: int | None = None,
    evidence_provider: EvidenceProvider | None = None,
) -> SentinelVerdict:
    """Generate a verdict and run bounded issue-resolution rounds if enabled."""
    rounds = _resolve_max_rounds(max_rounds)
    verdict = await generate_verdict(
        trace_json=trace_json,
        request_hash=request_hash,
        trace_id=trace_id,
        sentinel_agent_id=sentinel_agent_id,
        apply_issue_caps=rounds <= 0,
    )
    if rounds <= 0:
        return verdict

    trace = _parse_trace(trace_json)
    provider = evidence_provider or evidence_provider_from_runtime()
    challenge_resolutions = list(verdict.challenge_resolutions)
    resolution_rounds = list(verdict.resolution_rounds)
    challenges = list(verdict.structured_challenges)

    for round_index in range(1, rounds + 1):
        open_challenges = _open_material_or_blocking(challenges)
        if not open_challenges:
            break

        logger.info(
            "resolution_round_started",
            trace_id=verdict.trace_id,
            round_index=round_index,
            open_challenges=len(open_challenges),
        )

        round_resolutions: list[ChallengeResolution] = []
        for challenge in open_challenges:
            resolution = await _attempt_resolution(
                trace=trace,
                challenge=challenge,
                provider=provider,
            )
            round_resolutions.append(resolution)
            _apply_resolution_to_challenge(challenge, resolution)

        challenge_resolutions.extend(round_resolutions)
        resolved_ids = [
            r.challenge_id for r in round_resolutions if r.status in _RESOLVED_STATUSES
        ]
        resolution_rounds.append(
            ResolutionRound(
                round_index=round_index,
                opened_challenge_ids=[c.id for c in open_challenges],
                resolved_challenge_ids=resolved_ids,
                prompt=_round_prompt(open_challenges),
                response=_round_response(round_resolutions),
                created_at=datetime.now(UTC),
            )
        )
        verdict.dialogue_messages.extend(_dialogue_for_round(round_index, round_resolutions))

    score, label, metadata = apply_unresolved_issue_caps(
        score=verdict.verdict_score,
        label=verdict.verdict_label,
        challenges=challenges,
        max_rounds=rounds,
    )
    if _open_blocking(challenges):
        metadata.stop_reason = "unresolved_blockers"
    elif len(resolution_rounds) >= rounds and _open_material_or_blocking(challenges):
        metadata.stop_reason = "max_rounds"
    else:
        metadata.stop_reason = "confidence_reached"

    return verdict.model_copy(
        update={
            "verdict_score": score,
            "verdict_label": label,
            "structured_challenges": challenges,
            "challenge_resolutions": challenge_resolutions,
            "resolution_rounds": resolution_rounds,
            "resolution_metadata": metadata,
            "dialogue_messages": verdict.dialogue_messages,
        }
    )


def _resolve_max_rounds(max_rounds: int | None) -> int:
    if max_rounds is not None:
        return max(0, max_rounds)
    raw = os.environ.get("ADVERSARIAL_RESOLUTION_MAX_ROUNDS", "0")
    try:
        return max(0, int(raw))
    except ValueError:
        logger.warning("invalid_resolution_max_rounds", raw=raw, fallback=0)
        return 0


def _parse_trace(trace_json: str) -> TradingR1Trace | None:
    try:
        return TradingR1Trace.model_validate(json.loads(trace_json))
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("resolution_trace_parse_failed", error=str(exc))
        return None


def _open_material_or_blocking(
    challenges: list[AdversarialChallenge],
) -> list[AdversarialChallenge]:
    return [
        c
        for c in challenges
        if c.resolution_status not in _RESOLVED_STATUSES
        and (c.blocking_pass or c.severity in {"material", "blocking"})
    ]


def _open_blocking(challenges: list[AdversarialChallenge]) -> list[AdversarialChallenge]:
    return [
        c
        for c in challenges
        if c.blocking_pass and c.resolution_status not in _RESOLVED_STATUSES
    ]


async def _attempt_resolution(
    *,
    trace: TradingR1Trace | None,
    challenge: AdversarialChallenge,
    provider: EvidenceProvider,
) -> ChallengeResolution:
    market_question = trace.market_question if trace else ""
    request = EvidenceSearchRequest(
        market_question=market_question,
        challenge=challenge,
        query=query_for_challenge(market_question, challenge),
    )
    results = await provider.search(request)
    if results:
        best = results[0]
        return ChallengeResolution(
            challenge_id=challenge.id,
            status="resolved",
            responder="evidence_tool",
            response=(
                f"Retrieved corroborating evidence from {best.provider}: {best.title} "
                f"({best.url}) — {best.snippet}"
            ),
            created_at=datetime.now(UTC),
        )

    if challenge.blocking_pass:
        status = "conceded"
        response = (
            "No configured evidence provider resolved this blocking issue; "
            "the trader must concede or revise before PASS is allowed."
        )
    else:
        status = "answered"
        response = (
            "No additional evidence retrieved; issue remains available for final "
            "adjudication."
        )

    return ChallengeResolution(
        challenge_id=challenge.id,
        status=status,  # type: ignore[arg-type]
        responder="system",
        response=response,
        created_at=datetime.now(UTC),
    )


def _apply_resolution_to_challenge(
    challenge: AdversarialChallenge,
    resolution: ChallengeResolution,
) -> None:
    if resolution.status in {"resolved", "superseded", "conceded"}:
        challenge.resolution_status = resolution.status


def _round_prompt(challenges: list[AdversarialChallenge]) -> str:
    questions = "; ".join(f"{c.id}: {c.question}" for c in challenges)
    return f"Resolve adversarial issues before final verdict: {questions}"


def _round_response(resolutions: list[ChallengeResolution]) -> str:
    return " | ".join(f"{r.challenge_id}: {r.status}" for r in resolutions)


def _dialogue_for_round(
    round_index: int,
    resolutions: list[ChallengeResolution],
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [
        {
            "role": "sentinel",
            "content": f"Resolution round {round_index}: targeted open issues for follow-up.",
        }
    ]
    for resolution in resolutions:
        messages.append(
            {
                "role": resolution.responder,
                "content": (
                    f"{resolution.challenge_id} → {resolution.status}: "
                    f"{resolution.response}"
                ),
            }
        )
    return messages
