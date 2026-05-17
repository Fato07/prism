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
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

import structlog
from prism_schemas.trace import TradingR1Trace
from prism_schemas.verdict import (
    AdversarialChallenge,
    ChallengeResolution,
    EvidenceToolReceipt,
    ResolutionRound,
    SentinelVerdict,
)

from sentinel.adversarial import generate_verdict
from sentinel.evidence_tools import (
    EvidenceProvider,
    EvidenceSearchRequest,
    EvidenceSearchResult,
    evidence_provider_from_runtime,
    query_for_challenge,
)
from sentinel.issues import apply_unresolved_issue_caps

logger = structlog.get_logger("prism.sentinel.resolution_loop")

_RESOLVED_STATUSES = frozenset({"resolved", "superseded"})
_MARKET_EVIDENCE_PROVIDER = "prism_market_evidence_mcp.search"
_MARKET_STATUS_TERMS = frozenset(
    {"active", "closed", "clob", "conditionid", "end date", "resolved", "token"}
)
_SOURCE_QUALITY_TERMS = frozenset(
    {"filing", "government", "official", "original", "primary", "statement"}
)
_SOURCE_QUALITY_NEGATIONS = (
    "no primary source",
    "not a primary source",
    "not primary",
    "secondary source",
    "unverified",
    "scraped data",
    "does not identify primary",
)
_CALIBRATION_TERMS = frozenset({"probability", "odds", "price", "forecast", "%", "percent"})
_STOPWORDS = frozenset(
    {
        "about",
        "after",
        "before",
        "claim",
        "current",
        "evidence",
        "issue",
        "market",
        "provide",
        "question",
        "required",
        "resolution",
        "resolve",
        "source",
        "that",
        "this",
        "what",
        "when",
        "whether",
        "which",
        "will",
        "win",
        "wins",
        "with",
    }
)


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
    best = _select_adequate_result(
        results=results,
        trace=trace,
        challenge=challenge,
    )
    if best is not None:
        public_url = _public_source_url(best.url)
        return ChallengeResolution(
            challenge_id=challenge.id,
            status="resolved",
            responder="evidence_tool",
            response=(
                f"Retrieved issue-matched evidence from {best.provider}: {best.title} "
                f"({public_url}) — {best.snippet}"
            ),
            created_at=datetime.now(UTC),
            tool_receipt=_tool_receipt_for_result(best, trace, challenge),
        )

    if results:
        logger.info(
            "evidence_results_failed_adequacy_gate",
            challenge_id=challenge.id,
            challenge_type=challenge.type,
            result_count=len(results),
        )

    if challenge.blocking_pass:
        status = "conceded"
        if results:
            response = (
                "No additional evidence retrieved that satisfied this issue's required "
                "resolution; the trader must concede or revise before PASS is allowed."
            )
        else:
            response = (
                "No configured evidence provider resolved this blocking issue; "
                "the trader must concede or revise before PASS is allowed."
            )
    else:
        status = "answered"
        response = (
            "No additional evidence retrieved that satisfied this issue's required "
            "resolution; issue remains available for final adjudication."
        )

    return ChallengeResolution(
        challenge_id=challenge.id,
        status=status,  # type: ignore[arg-type]
        responder="system",
        response=response,
        created_at=datetime.now(UTC),
    )


def _select_adequate_result(
    *,
    results: list[EvidenceSearchResult],
    trace: TradingR1Trace | None,
    challenge: AdversarialChallenge,
) -> EvidenceSearchResult | None:
    """Return the first evidence result that can honestly resolve the challenge."""
    for result in results:
        if _evidence_result_is_adequate(result=result, trace=trace, challenge=challenge):
            return result
    return None


def _evidence_result_is_adequate(
    *,
    result: EvidenceSearchResult,
    trace: TradingR1Trace | None,
    challenge: AdversarialChallenge,
) -> bool:
    """Validate that evidence matches the issue type and required resolution."""
    text = _evidence_text(result)
    content_text = _evidence_content_text(result)
    if not text or not content_text:
        return False
    if not _evidence_source_is_usable(result):
        return False
    if not _evidence_content_is_readable(result):
        return False

    if result.provider == _MARKET_EVIDENCE_PROVIDER:
        return (
            _challenge_allows_market_status_evidence(challenge)
            and _contains_any(content_text, _MARKET_STATUS_TERMS)
            and _has_market_question_overlap(result=result, trace=trace)
        )

    challenge_type = challenge.type
    if challenge_type == "market_structure":
        return _contains_any(text, _MARKET_STATUS_TERMS) and _has_topic_overlap(
            result=result,
            trace=trace,
            challenge=challenge,
        )
    if challenge_type == "temporal":
        return _temporal_evidence_is_adequate(result, trace, content_text) and _has_topic_overlap(
            result=result,
            trace=trace,
            challenge=challenge,
        )
    if challenge_type == "source_quality":
        return _source_quality_evidence_is_adequate(
            result=result,
            trace=trace,
            challenge=challenge,
            content_text=content_text,
        )
    if challenge_type == "calibration":
        return _contains_any(text, _CALIBRATION_TERMS) or bool(re.search(r"\d+(?:\.\d+)?%", text))

    return _has_issue_keyword_overlap(result=result, trace=trace, challenge=challenge)


def _tool_receipt_for_result(
    result: EvidenceSearchResult,
    trace: TradingR1Trace | None,
    challenge: AdversarialChallenge,
) -> EvidenceToolReceipt:
    """Build a structured, queryable receipt for the evidence result used."""
    retrieved_at = result.retrieved_at or datetime.now(UTC).isoformat()
    return EvidenceToolReceipt(
        provider=result.provider,
        tool_name=result.tool_name,
        source_title=result.title.strip(),
        source_url=_public_source_url(result.url),
        source_published_at=result.published_at,
        retrieved_at=retrieved_at,
        confidence=result.confidence,
        adequacy_checks=_adequacy_check_labels(result=result, trace=trace, challenge=challenge),
    )


def _adequacy_check_labels(
    *,
    result: EvidenceSearchResult,
    trace: TradingR1Trace | None,
    challenge: AdversarialChallenge,
) -> list[str]:
    """Return labels for adequacy gates satisfied by an accepted result."""
    content_text = _evidence_content_text(result)
    labels = ["source_metadata", "readable_content"]
    if _has_market_question_overlap(result=result, trace=trace):
        labels.append("market_topic_overlap")
    if _has_topic_overlap(result=result, trace=trace, challenge=challenge):
        labels.append("issue_topic_overlap")
    if challenge.type == "temporal" and _published_at_is_recent(result, trace):
        labels.append("temporal_recency")
    if challenge.type == "source_quality":
        if _contains_any(content_text, _SOURCE_QUALITY_TERMS):
            labels.append("source_quality_terms")
        if not _contains_source_quality_negation(content_text):
            labels.append("no_source_quality_negation")
    if challenge.type == "market_structure" and _contains_any(content_text, _MARKET_STATUS_TERMS):
        labels.append("market_structure_terms")
    if challenge.type == "calibration" and (
        _contains_any(_evidence_text(result), _CALIBRATION_TERMS)
        or bool(re.search(r"\d+(?:\.\d+)?%", _evidence_text(result)))
    ):
        labels.append("calibration_terms")
    return labels


def _challenge_allows_market_status_evidence(challenge: AdversarialChallenge) -> bool:
    if challenge.type == "market_structure":
        return True
    if challenge.type != "temporal":
        return False
    text = f"{challenge.id} {challenge.question} {challenge.required_resolution}".lower()
    if "market" not in text:
        return False
    return _contains_any(text, _MARKET_STATUS_TERMS)


def _temporal_evidence_is_adequate(
    result: EvidenceSearchResult,
    trace: TradingR1Trace | None,
    content_text: str,
) -> bool:
    return bool(content_text) and _published_at_is_recent(result, trace)


def _published_at_is_recent(
    result: EvidenceSearchResult,
    trace: TradingR1Trace | None,
) -> bool:
    if not result.published_at:
        return False
    try:
        published_at = datetime.fromisoformat(result.published_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    reference = trace.created_at if trace else datetime.now(UTC)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)
    return published_at >= reference - timedelta(days=365)


def _source_quality_evidence_is_adequate(
    *,
    result: EvidenceSearchResult,
    trace: TradingR1Trace | None,
    challenge: AdversarialChallenge,
    content_text: str,
) -> bool:
    if _contains_source_quality_negation(content_text):
        return False
    if not _contains_any(content_text, _SOURCE_QUALITY_TERMS):
        return False
    return _has_topic_overlap(result=result, trace=trace, challenge=challenge)


def _contains_source_quality_negation(text: str) -> bool:
    return any(negation in text for negation in _SOURCE_QUALITY_NEGATIONS)


def _has_issue_keyword_overlap(
    *,
    result: EvidenceSearchResult,
    trace: TradingR1Trace | None,
    challenge: AdversarialChallenge,
) -> bool:
    result_words = _keywords(_evidence_content_text(result))
    issue_words = _keywords(f"{challenge.question} {challenge.required_resolution}")
    market_words = _keywords(trace.market_question if trace else "")
    issue_overlap = result_words & issue_words
    market_overlap = result_words & market_words
    return len(issue_overlap) >= 2 or (len(issue_overlap) >= 1 and len(market_overlap) >= 2)


def _has_topic_overlap(
    *,
    result: EvidenceSearchResult,
    trace: TradingR1Trace | None,
    challenge: AdversarialChallenge,
) -> bool:
    result_words = _keywords(_evidence_content_text(result))
    issue_words = _keywords(f"{challenge.question} {challenge.required_resolution}")
    return (
        _has_market_question_overlap(result=result, trace=trace)
        or len(result_words & issue_words) >= 2
    )


def _has_market_question_overlap(
    *,
    result: EvidenceSearchResult,
    trace: TradingR1Trace | None,
) -> bool:
    if trace is None:
        return False
    result_words = _keywords(_evidence_content_text(result))
    market_words = _keywords(trace.market_question)
    return len(result_words & market_words) >= 2


def _evidence_source_is_usable(result: EvidenceSearchResult) -> bool:
    """Require minimally useful source metadata before evidence can resolve an issue."""
    if len(result.title.strip()) < 4:
        return False
    if len(result.snippet.strip()) < 20:
        return False
    try:
        parsed = urlsplit(result.url.strip())
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _public_source_url(url: str) -> str:
    """Return a receipt-safe source URL with credentials, query, and fragment removed."""
    raw = url.strip()
    if not raw:
        return "redacted-url"
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError:
        return "redacted-url"
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return "redacted-url"
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    netloc = f"{host}:{port}" if port is not None else host
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def _evidence_content_is_readable(result: EvidenceSearchResult) -> bool:
    """Reject binary-ish or mojibake-heavy provider output before adequacy checks."""
    snippet = result.snippet.strip()
    if not snippet:
        return False
    if "\ufffd" in snippet:
        return False
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", snippet):
        return False
    if len(snippet) < 120:
        return True

    ascii_word_chars = sum(len(token) for token in re.findall(r"[a-z0-9]{2,}", snippet.lower()))
    return (ascii_word_chars / max(len(snippet), 1)) >= 0.35


def _evidence_text(result: EvidenceSearchResult) -> str:
    return " ".join(
        part
        for part in [
            result.title,
            result.url,
            result.snippet,
            result.provider,
            result.published_at,
        ]
        if part
    ).lower()


def _evidence_content_text(result: EvidenceSearchResult) -> str:
    return " ".join(
        part
        for part in [result.title, result.snippet, result.published_at]
        if part
    ).lower()


def _contains_any(text: str, terms: frozenset[str]) -> bool:
    return any(term in text for term in terms)


def _keywords(text: str) -> set[str]:
    words = {word for word in re.findall(r"[a-z0-9]{3,}", text.lower())}
    return {word for word in words if word not in _STOPWORDS}


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
